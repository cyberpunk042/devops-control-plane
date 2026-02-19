"""Docker detection — compose parsing, service details, status probes."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

from src.core.services.docker_common import run_docker, run_compose

import re

logger = logging.getLogger(__name__)

_COMPOSE_FILENAMES = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)

def find_compose_file(project_root: Path) -> Path | None:
    """Return the first compose file found, or None."""
    for name in _COMPOSE_FILENAMES:
        path = project_root / name
        if path.is_file():
            return path
    return None


def docker_status(project_root: Path) -> dict:
    """Docker integration status: availability, version, project files.

    File detection (Dockerfiles, compose) always runs regardless of CLI
    availability so the return shape is consistent.

    Returns:
        {
            "available": bool,
            "version": str | None,
            "daemon_running": bool,
            "compose_available": bool,
            "has_dockerfile": bool,
            "has_compose": bool,
            "compose_file": str | None,
            "dockerfiles": [str, ...],
            "compose_services": [str, ...],
            "compose_service_details": [dict, ...],
            "services_count": int,
        }
    """
    # ── File detection (always runs) ──────────────────────────────
    dockerfiles: list[str] = []
    if (project_root / "Dockerfile").is_file():
        dockerfiles.append("Dockerfile")
    for p in project_root.rglob("Dockerfile*"):
        rel = str(p.relative_to(project_root))
        if rel not in dockerfiles and ".git" not in rel and "node_modules" not in rel:
            dockerfiles.append(rel)
            if len(dockerfiles) >= 20:
                break

    # Parse Dockerfile content
    dockerfile_details: list[dict] = []
    for df in dockerfiles:
        dockerfile_details.append(_parse_dockerfile(project_root / df, df))

    compose_path = find_compose_file(project_root)
    compose_services: list[str] = []
    compose_service_details: list[dict] = []
    if compose_path:
        compose_services = _parse_compose_services(compose_path)
        compose_service_details = _parse_compose_service_details(compose_path)

    # .dockerignore
    dockerignore_path = project_root / ".dockerignore"
    dockerignore_patterns: list[str] = []
    if dockerignore_path.is_file():
        try:
            content = dockerignore_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    dockerignore_patterns.append(stripped)
        except Exception:
            logger.debug("Failed to read .dockerignore: %s", dockerignore_path, exc_info=True)

    file_info = {
        "has_dockerfile": len(dockerfiles) > 0,
        "has_compose": compose_path is not None,
        "compose_file": str(compose_path.relative_to(project_root)) if compose_path else None,
        "dockerfiles": dockerfiles,
        "dockerfile_details": dockerfile_details,
        "compose_services": compose_services,
        "compose_service_details": compose_service_details,
        "services_count": len(compose_services),
        "has_dockerignore": dockerignore_path.is_file(),
        "dockerignore_patterns": dockerignore_patterns,
    }

    # ── CLI detection ─────────────────────────────────────────────
    docker_path = shutil.which("docker")
    if not docker_path:
        from src.core.services.tool_requirements import check_required_tools
        return {
            "available": False,
            "error": "Docker CLI not installed",
            "daemon_running": False,
            "compose_available": False,
            "missing_tools": check_required_tools(["docker", "docker-compose"]),
            **file_info,
        }

    # Version
    r_ver = run_docker("--version", cwd=project_root, timeout=5)
    version = r_ver.stdout.strip() if r_ver.returncode == 0 else None

    # Daemon check
    r_info = run_docker("info", "--format", "{{.ServerVersion}}", cwd=project_root, timeout=10)
    daemon_running = r_info.returncode == 0

    # Compose available
    r_compose = run_docker("compose", "version", "--short", cwd=project_root, timeout=5)
    compose_available = r_compose.returncode == 0
    compose_version = r_compose.stdout.strip() if compose_available else None

    from src.core.services.tool_requirements import check_required_tools
    return {
        "available": True,
        "version": version,
        "daemon_running": daemon_running,
        "compose_available": compose_available,
        "compose_version": compose_version,
        "missing_tools": check_required_tools(["docker", "docker-compose"]),
        **file_info,
    }


def _parse_dockerfile(path: Path, rel_path: str) -> dict:
    """Parse a Dockerfile and extract key information.

    Returns:
        {
            "path": str,            # relative path
            "base_images": [str],   # FROM image references
            "stages": [str],        # stage names (FROM ... AS name)
            "stage_count": int,     # number of FROM lines
            "ports": [int],         # EXPOSE ports
            "warnings": [str],      # validation warnings
        }
    """
    result: dict[str, Any] = {
        "path": rel_path,
        "base_images": [],
        "stages": [],
        "stage_count": 0,
        "ports": [],
        "warnings": [],
    }
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        logger.debug("Failed to read Dockerfile: %s", path, exc_info=True)
        result["warnings"].append(f"Could not read file: {rel_path}")
        return result

    has_content = False
    for line in content.splitlines():
        stripped = line.strip()
        # Skip comments and empty lines
        if not stripped or stripped.startswith("#"):
            continue
        has_content = True

        upper = stripped.upper()

        # FROM lines
        if upper.startswith("FROM "):
            parts = stripped.split()
            if len(parts) >= 2:
                image = parts[1]
                result["base_images"].append(image)
                result["stage_count"] += 1
                # Check for AS alias
                if len(parts) >= 4 and parts[2].upper() == "AS":
                    result["stages"].append(parts[3])

        # EXPOSE lines
        elif upper.startswith("EXPOSE "):
            tokens = stripped.split()[1:]
            for token in tokens:
                # Remove protocol suffix (e.g. 8080/tcp)
                port_str = token.split("/")[0]
                try:
                    result["ports"].append(int(port_str))
                except ValueError:
                    pass  # skip non-numeric (e.g. $PORT)

    # Validation warnings
    if not has_content:
        result["warnings"].append("Dockerfile is empty")
    elif result["stage_count"] == 0:
        result["warnings"].append("No FROM instruction found")

    return result


def _parse_compose_services(compose_path: Path) -> list[str]:
    """Extract service names from a compose file."""
    try:
        import yaml  # already a project dependency

        data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "services" in data:
            return sorted(data["services"].keys())
    except Exception:
        logger.debug("Failed to parse compose file: %s", compose_path, exc_info=True)
    return []


def _parse_compose_service_details(compose_path: Path) -> list[dict]:
    """Extract full service specifications from a compose file.

    Returns a list of dicts, one per service, with 42 normalised fields.
    Excludes Security (cap_add, cap_drop, security_opt) and Limits
    (ulimits, sysctls) per project scope.

    Fields by category::

        Original 14:
            name, image, build, ports, environment, volumes, depends_on,
            command, entrypoint, restart, healthcheck, deploy, networks, labels

        Identity (5):
            container_name, hostname, domainname, platform, profiles

        Runtime (9):
            user, working_dir, stdin_open, tty, privileged, init,
            read_only, pid, shm_size

        Networking (5):
            network_mode, dns, dns_search, extra_hosts, expose

        Files (5):
            env_file, configs, secrets, tmpfs, devices

        Logging (1):
            logging  →  {"driver": str, "options": dict}

        Lifecycle (3):
            stop_signal, stop_grace_period, pull_policy
    """
    try:
        import yaml

        raw = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "services" not in raw:
            return []
    except Exception:
        logger.debug(
            "Failed to parse compose file for details: %s",
            compose_path,
            exc_info=True,
        )
        return []

    result: list[dict] = []
    for name, svc in raw["services"].items():
        if not isinstance(svc, dict):
            continue

        detail: dict = {"name": name}

        # ── Image ──────────────────────────────────────────────────
        detail["image"] = svc.get("image") or None

        # ── Build ──────────────────────────────────────────────────
        build_raw = svc.get("build")
        if isinstance(build_raw, str):
            detail["build"] = {
                "context": build_raw,
                "dockerfile": None,
                "args": None,
            }
        elif isinstance(build_raw, dict):
            build_args = build_raw.get("args")
            if isinstance(build_args, list):
                # ["KEY=VAL", ...] → dict
                build_args = _env_list_to_dict(build_args)
            detail["build"] = {
                "context": build_raw.get("context", "."),
                "dockerfile": build_raw.get("dockerfile"),
                "args": build_args if isinstance(build_args, dict) else None,
            }
        else:
            detail["build"] = None

        # ── Ports ──────────────────────────────────────────────────
        detail["ports"] = _normalise_ports(svc.get("ports"))

        # ── Environment ────────────────────────────────────────────
        env_raw = svc.get("environment")
        if isinstance(env_raw, dict):
            detail["environment"] = {
                str(k): str(v) if v is not None else ""
                for k, v in env_raw.items()
            }
        elif isinstance(env_raw, list):
            detail["environment"] = _env_list_to_dict(env_raw)
        else:
            detail["environment"] = {}

        # ── Volumes ────────────────────────────────────────────────
        vols = svc.get("volumes")
        if isinstance(vols, list):
            detail["volumes"] = [
                str(v) if isinstance(v, str) else _long_volume_to_str(v)
                for v in vols
            ]
        else:
            detail["volumes"] = []

        # ── Depends on ─────────────────────────────────────────────
        deps = svc.get("depends_on")
        if isinstance(deps, list):
            detail["depends_on"] = list(deps)
        elif isinstance(deps, dict):
            # {svc_name: {condition: ...}} → just the names
            detail["depends_on"] = sorted(deps.keys())
        else:
            detail["depends_on"] = []

        # ── Command / Entrypoint ───────────────────────────────────
        cmd = svc.get("command")
        if isinstance(cmd, list):
            detail["command"] = " ".join(str(c) for c in cmd)
        elif cmd is not None:
            detail["command"] = str(cmd)
        else:
            detail["command"] = None

        ep = svc.get("entrypoint")
        if isinstance(ep, list):
            detail["entrypoint"] = " ".join(str(e) for e in ep)
        elif ep is not None:
            detail["entrypoint"] = str(ep)
        else:
            detail["entrypoint"] = None

        # ── Restart policy ─────────────────────────────────────────
        detail["restart"] = svc.get("restart") or None

        # ── Health check ───────────────────────────────────────────
        hc = svc.get("healthcheck")
        if isinstance(hc, dict):
            test = hc.get("test")
            if isinstance(test, list):
                # ["CMD-SHELL", "curl ..."] → just the command part
                test = " ".join(str(t) for t in test[1:]) if len(test) > 1 else str(test[0])
            detail["healthcheck"] = {
                "test": str(test) if test else None,
                "interval": hc.get("interval"),
                "timeout": hc.get("timeout"),
                "retries": hc.get("retries"),
            }
        else:
            detail["healthcheck"] = None

        # ── Deploy / Resources ─────────────────────────────────────
        deploy = svc.get("deploy")
        if isinstance(deploy, dict):
            resources = deploy.get("resources", {})
            limits = resources.get("limits", {}) if isinstance(resources, dict) else {}
            reservations = (
                resources.get("reservations", {})
                if isinstance(resources, dict)
                else {}
            )
            detail["deploy"] = {
                "replicas": deploy.get("replicas"),
                "cpu_limit": limits.get("cpus"),
                "memory_limit": limits.get("memory"),
                "cpu_request": reservations.get("cpus"),
                "memory_request": reservations.get("memory"),
            }
        else:
            detail["deploy"] = None

        # ── Networks ───────────────────────────────────────────────
        nets = svc.get("networks")
        if isinstance(nets, list):
            detail["networks"] = list(nets)
        elif isinstance(nets, dict):
            detail["networks"] = sorted(nets.keys())
        else:
            detail["networks"] = []

        # ── Labels ─────────────────────────────────────────────────
        labels = svc.get("labels")
        if isinstance(labels, dict):
            detail["labels"] = {str(k): str(v) for k, v in labels.items()}
        elif isinstance(labels, list):
            detail["labels"] = _env_list_to_dict(labels)
        else:
            detail["labels"] = {}

        # ── Identity (5) ───────────────────────────────────────────
        detail["container_name"] = svc.get("container_name") or None
        detail["hostname"] = svc.get("hostname") or None
        detail["domainname"] = svc.get("domainname") or None
        detail["platform"] = svc.get("platform") or None
        profiles = svc.get("profiles")
        detail["profiles"] = list(profiles) if isinstance(profiles, list) else []

        # ── Runtime (9) ────────────────────────────────────────────
        detail["user"] = str(svc["user"]) if "user" in svc and svc["user"] is not None else None
        detail["working_dir"] = svc.get("working_dir") or None
        detail["stdin_open"] = bool(svc.get("stdin_open", False))
        detail["tty"] = bool(svc.get("tty", False))
        detail["privileged"] = bool(svc.get("privileged", False))
        detail["init"] = bool(svc.get("init", False))
        detail["read_only"] = bool(svc.get("read_only", False))
        detail["pid"] = svc.get("pid") or None
        shm = svc.get("shm_size")
        detail["shm_size"] = str(shm) if shm is not None else None

        # ── Networking (5) ─────────────────────────────────────────
        detail["network_mode"] = svc.get("network_mode") or None
        dns_raw = svc.get("dns")
        if isinstance(dns_raw, str):
            detail["dns"] = [dns_raw]
        elif isinstance(dns_raw, list):
            detail["dns"] = list(dns_raw)
        else:
            detail["dns"] = []
        dns_search_raw = svc.get("dns_search")
        if isinstance(dns_search_raw, str):
            detail["dns_search"] = [dns_search_raw]
        elif isinstance(dns_search_raw, list):
            detail["dns_search"] = list(dns_search_raw)
        else:
            detail["dns_search"] = []
        extra_hosts_raw = svc.get("extra_hosts")
        if isinstance(extra_hosts_raw, list):
            detail["extra_hosts"] = [str(h) for h in extra_hosts_raw]
        else:
            detail["extra_hosts"] = []
        expose_raw = svc.get("expose")
        if isinstance(expose_raw, list):
            detail["expose"] = [int(p) for p in expose_raw]
        else:
            detail["expose"] = []

        # ── Files (5) ──────────────────────────────────────────────
        env_file_raw = svc.get("env_file")
        if isinstance(env_file_raw, str):
            detail["env_file"] = [env_file_raw]
        elif isinstance(env_file_raw, list):
            detail["env_file"] = list(env_file_raw)
        else:
            detail["env_file"] = []
        configs_raw = svc.get("configs")
        if isinstance(configs_raw, list):
            # configs can be strings or dicts; normalise to strings
            detail["configs"] = [
                c if isinstance(c, str) else c.get("source", str(c))
                for c in configs_raw
            ]
        else:
            detail["configs"] = []
        secrets_raw = svc.get("secrets")
        if isinstance(secrets_raw, list):
            detail["secrets"] = [
                s if isinstance(s, str) else s.get("source", str(s))
                for s in secrets_raw
            ]
        else:
            detail["secrets"] = []
        tmpfs_raw = svc.get("tmpfs")
        if isinstance(tmpfs_raw, str):
            detail["tmpfs"] = [tmpfs_raw]
        elif isinstance(tmpfs_raw, list):
            detail["tmpfs"] = list(tmpfs_raw)
        else:
            detail["tmpfs"] = []
        devices_raw = svc.get("devices")
        if isinstance(devices_raw, list):
            detail["devices"] = [str(d) for d in devices_raw]
        else:
            detail["devices"] = []

        # ── Logging (1) ────────────────────────────────────────────
        logging_raw = svc.get("logging")
        if isinstance(logging_raw, dict):
            detail["logging"] = {
                "driver": logging_raw.get("driver"),
                "options": logging_raw.get("options", {}),
            }
        else:
            detail["logging"] = None

        # ── Lifecycle (3) ──────────────────────────────────────────
        detail["stop_signal"] = svc.get("stop_signal") or None
        detail["stop_grace_period"] = svc.get("stop_grace_period") or None
        detail["pull_policy"] = svc.get("pull_policy") or None

        result.append(detail)

    return result


def _env_list_to_dict(items: list) -> dict[str, str]:
    """Convert ``["KEY=VAL", ...]`` to ``{"KEY": "VAL", ...}``."""
    out: dict[str, str] = {}
    for item in items:
        s = str(item)
        eq = s.find("=")
        if eq > 0:
            out[s[:eq]] = s[eq + 1 :]
        else:
            out[s] = ""
    return out


def _normalise_ports(ports_raw: list | None) -> list[dict]:
    """Normalise compose port mappings to ``[{"host": N, "container": N, "protocol": "tcp"}]``."""
    if not ports_raw:
        return []
    result: list[dict] = []
    for entry in ports_raw:
        if isinstance(entry, (int, float)):
            result.append({"host": int(entry), "container": int(entry), "protocol": "tcp"})
        elif isinstance(entry, str):
            # Formats: "8080", "8080:80", "8080:80/udp", "127.0.0.1:8080:80"
            proto = "tcp"
            s = entry
            if "/" in s:
                s, proto = s.rsplit("/", 1)
            parts = s.split(":")
            if len(parts) == 1:
                p = int(parts[0])
                result.append({"host": p, "container": p, "protocol": proto})
            elif len(parts) == 2:
                result.append({"host": int(parts[0]), "container": int(parts[1]), "protocol": proto})
            elif len(parts) >= 3:
                # host_ip:host_port:container_port
                result.append({"host": int(parts[1]), "container": int(parts[2]), "protocol": proto})
        elif isinstance(entry, dict):
            # Long-form: {target: 80, published: 8080, protocol: tcp}
            result.append({
                "host": int(entry.get("published", entry.get("target", 0))),
                "container": int(entry.get("target", 0)),
                "protocol": entry.get("protocol", "tcp"),
            })
    return result


def _long_volume_to_str(vol: dict) -> str:
    """Convert a long-form compose volume dict to a short string."""
    if not isinstance(vol, dict):
        return str(vol)
    src = vol.get("source", "")
    tgt = vol.get("target", "")
    mode = vol.get("read_only")
    suffix = ":ro" if mode else ""
    return f"{src}:{tgt}{suffix}" if src else tgt
