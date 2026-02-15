"""Docker detection — compose parsing, service details, status probes."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

from src.core.services.docker_common import run_docker, run_compose

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
        }
    """
    docker_path = shutil.which("docker")
    if not docker_path:
        return {
            "available": False,
            "error": "Docker CLI not installed",
            "daemon_running": False,
            "compose_available": False,
            "has_dockerfile": False,
            "has_compose": False,
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

    # Find Dockerfiles
    dockerfiles = []
    if (project_root / "Dockerfile").is_file():
        dockerfiles.append("Dockerfile")
    # Check common patterns
    for p in project_root.rglob("Dockerfile*"):
        rel = str(p.relative_to(project_root))
        if rel not in dockerfiles and ".git" not in rel and "node_modules" not in rel:
            dockerfiles.append(rel)
            if len(dockerfiles) >= 20:
                break

    # Compose file
    compose_path = find_compose_file(project_root)
    compose_services: list[str] = []
    compose_service_details: list[dict] = []
    if compose_path:
        compose_services = _parse_compose_services(compose_path)
        compose_service_details = _parse_compose_service_details(compose_path)

    return {
        "available": True,
        "version": version,
        "daemon_running": daemon_running,
        "compose_available": compose_available,
        "compose_version": compose_version,
        "has_dockerfile": len(dockerfiles) > 0,
        "has_compose": compose_path is not None,
        "compose_file": str(compose_path.relative_to(project_root)) if compose_path else None,
        "dockerfiles": dockerfiles,
        "compose_services": compose_services,
        "compose_service_details": compose_service_details,
    }


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

    Returns a list of dicts, one per service, with normalised fields::

        {
            "name":        str,             # service key
            "image":       str | None,      # explicit image tag
            "build":       {                # build config (if present)
                "context":    str,
                "dockerfile": str | None,
                "args":       {str: str} | None,
            } | None,
            "ports":       [                # normalised port mappings
                {"host": int, "container": int, "protocol": "tcp"|"udp"},
            ],
            "environment": {str: str},      # merged env vars (list or dict)
            "volumes":     [str],           # raw volume strings
            "depends_on":  [str],           # dependency service names
            "command":     str | None,      # command override
            "entrypoint":  str | None,      # entrypoint override
            "restart":     str | None,      # restart policy
            "healthcheck": {               # health check (if present)
                "test":     str | None,
                "interval": str | None,
                "timeout":  str | None,
                "retries":  int | None,
            } | None,
            "deploy":      {               # deploy resources (if present)
                "replicas":       int | None,
                "cpu_limit":      str | None,
                "memory_limit":   str | None,
                "cpu_request":    str | None,
                "memory_request": str | None,
            } | None,
            "networks":    [str],           # network names
            "labels":      {str: str},      # labels dict
        }
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
