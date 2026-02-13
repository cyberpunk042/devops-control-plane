"""
Docker & Compose operations — channel-independent service.

Provides Docker status, container listing, image management, compose
operations, log viewing, and config file generation without any
Flask or HTTP dependency.

Follows the same pattern as ``git_ops.py``: pure functions calling
the docker CLI via subprocess.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


# Names of docker-compose files we recognise (checked in order).
_COMPOSE_FILENAMES = [
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
]


# ═══════════════════════════════════════════════════════════════════
#  Low-level runners
# ═══════════════════════════════════════════════════════════════════


def run_docker(
    *args: str,
    cwd: Path,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    """Run a docker command and return the result."""
    return subprocess.run(
        ["docker", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def run_compose(
    *args: str,
    cwd: Path,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Run a docker compose command and return the result."""
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ═══════════════════════════════════════════════════════════════════
#  Detect
# ═══════════════════════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════════════════════
#  Observe
# ═══════════════════════════════════════════════════════════════════


def docker_containers(project_root: Path, *, all_: bool = True) -> dict:
    """List containers.

    Args:
        all_: Include stopped containers (default True).

    Returns:
        {"available": True, "containers": [{name, image, status, ports, id}, ...]}
    """
    args = [
        "ps",
        "--format", "{{json .}}",
    ]
    if all_:
        args.insert(1, "-a")

    r = run_docker(*args, cwd=project_root, timeout=10)
    if r.returncode != 0:
        return {"available": False, "error": r.stderr.strip() or "Docker not available"}

    containers = []
    for line in r.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            info = json.loads(line)
            containers.append({
                "id": info.get("ID", ""),
                "name": info.get("Names", ""),
                "image": info.get("Image", ""),
                "status": info.get("Status", ""),
                "state": info.get("State", ""),
                "ports": info.get("Ports", ""),
                "created": info.get("CreatedAt", ""),
            })
        except json.JSONDecodeError:
            continue

    return {"available": True, "containers": containers}


def docker_images(project_root: Path) -> dict:
    """List local images.

    Returns:
        {"available": True, "images": [{repo, tag, id, size, created}, ...]}
    """
    r = run_docker(
        "images", "--format", "{{json .}}",
        cwd=project_root,
        timeout=10,
    )
    if r.returncode != 0:
        return {"available": False, "error": r.stderr.strip() or "Docker not available"}

    images = []
    for line in r.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            info = json.loads(line)
            images.append({
                "id": info.get("ID", ""),
                "repository": info.get("Repository", ""),
                "tag": info.get("Tag", ""),
                "size": info.get("Size", ""),
                "created": info.get("CreatedSince", ""),
            })
        except json.JSONDecodeError:
            continue

    return {"available": True, "images": images}


def docker_compose_status(project_root: Path) -> dict:
    """Compose-specific service status.

    Returns:
        {"available": True, "services": [{name, state, status, ports}, ...]}
    """
    compose_file = find_compose_file(project_root)
    if not compose_file:
        return {"available": False, "error": "No compose file found"}

    r = run_compose(
        "ps", "--format", "json",
        cwd=project_root,
        timeout=15,
    )
    if r.returncode != 0:
        return {"available": False, "error": r.stderr.strip() or "Compose not available"}

    services = []
    # docker compose ps --format json may output a JSON array or line-delimited
    output = r.stdout.strip()
    if not output:
        return {"available": True, "services": []}

    try:
        # Try JSON array first
        parsed = json.loads(output)
        if isinstance(parsed, list):
            raw_list = parsed
        else:
            raw_list = [parsed]
    except json.JSONDecodeError:
        # Fallback: line-delimited JSON
        raw_list = []
        for line in output.splitlines():
            try:
                raw_list.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    for svc in raw_list:
        services.append({
            "name": svc.get("Service", svc.get("Name", "")),
            "state": svc.get("State", ""),
            "status": svc.get("Status", ""),
            "ports": svc.get("Ports", svc.get("Publishers", "")),
            "image": svc.get("Image", ""),
        })

    return {"available": True, "services": services}


def docker_logs(
    project_root: Path,
    service: str,
    *,
    tail: int = 100,
) -> dict:
    """Get logs for a compose service.

    Args:
        service: Compose service name.
        tail: Number of lines from the end.

    Returns:
        {"ok": True, "logs": "..."} or {"error": "..."}
    """
    compose_file = find_compose_file(project_root)
    if not compose_file:
        return {"error": "No compose file found"}

    r = run_compose(
        "logs", "--tail", str(tail), "--no-color", service,
        cwd=project_root,
        timeout=15,
    )
    if r.returncode != 0:
        return {"error": r.stderr.strip() or f"Failed to get logs for '{service}'"}

    return {"ok": True, "service": service, "logs": r.stdout}


def docker_stats(project_root: Path) -> dict:
    """One-shot resource usage for running containers.

    Returns:
        {"available": True, "stats": [{name, cpu, memory, net_io, block_io}, ...]}
    """
    r = run_docker(
        "stats", "--no-stream", "--format", "{{json .}}",
        cwd=project_root,
        timeout=15,
    )
    if r.returncode != 0:
        return {"available": False, "error": r.stderr.strip() or "Docker not available"}

    stats = []
    for line in r.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            info = json.loads(line)
            stats.append({
                "name": info.get("Name", ""),
                "cpu": info.get("CPUPerc", ""),
                "memory": info.get("MemUsage", ""),
                "memory_pct": info.get("MemPerc", ""),
                "net_io": info.get("NetIO", ""),
                "block_io": info.get("BlockIO", ""),
                "pids": info.get("PIDs", ""),
            })
        except json.JSONDecodeError:
            continue

    return {"available": True, "stats": stats}


# ═══════════════════════════════════════════════════════════════════
#  Act
# ═══════════════════════════════════════════════════════════════════


def docker_build(project_root: Path, *, service: str | None = None, no_cache: bool = False) -> dict:
    """Build images via compose.

    Args:
        service: Optional specific service to build (default: all).
        no_cache: If True, pass --no-cache to docker compose build.

    Returns:
        {"ok": True, "output": "..."} or {"error": "..."}
    """
    compose_file = find_compose_file(project_root)
    if not compose_file:
        return {"error": "No compose file found"}

    args = ["build"]
    if no_cache:
        args.append("--no-cache")
    if service:
        args.append(service)

    r = run_compose(*args, cwd=project_root, timeout=600)
    if r.returncode != 0:
        return {"error": r.stderr.strip() or "Build failed"}

    return {"ok": True, "service": service or "all", "output": r.stdout.strip()}


def docker_up(project_root: Path, *, service: str | None = None, detach: bool = True) -> dict:
    """Start compose services.

    Args:
        service: Optional specific service (default: all).
        detach: Run in background (default True).

    Returns:
        {"ok": True, "output": "..."} or {"error": "..."}
    """
    compose_file = find_compose_file(project_root)
    if not compose_file:
        return {"error": "No compose file found"}

    args = ["up"]
    if detach:
        args.append("-d")
    if service:
        args.append(service)

    r = run_compose(*args, cwd=project_root, timeout=120)
    if r.returncode != 0:
        return {"error": r.stderr.strip() or "Failed to start services"}

    return {"ok": True, "service": service or "all", "output": r.stdout.strip() or r.stderr.strip()}


def docker_down(project_root: Path, *, volumes: bool = False) -> dict:
    """Stop and remove compose services.

    Args:
        volumes: Also remove named volumes (default False).

    Returns:
        {"ok": True, "output": "..."} or {"error": "..."}
    """
    compose_file = find_compose_file(project_root)
    if not compose_file:
        return {"error": "No compose file found"}

    args = ["down"]
    if volumes:
        args.append("-v")

    r = run_compose(*args, cwd=project_root, timeout=60)
    if r.returncode != 0:
        return {"error": r.stderr.strip() or "Failed to stop services"}

    return {"ok": True, "output": r.stdout.strip() or r.stderr.strip()}


def docker_restart(project_root: Path, *, service: str | None = None) -> dict:
    """Restart compose services.

    Args:
        service: Optional specific service (default: all).

    Returns:
        {"ok": True, "output": "..."} or {"error": "..."}
    """
    compose_file = find_compose_file(project_root)
    if not compose_file:
        return {"error": "No compose file found"}

    args = ["restart"]
    if service:
        args.append(service)

    r = run_compose(*args, cwd=project_root, timeout=60)
    if r.returncode != 0:
        return {"error": r.stderr.strip() or "Restart failed"}

    return {"ok": True, "service": service or "all", "output": r.stdout.strip() or r.stderr.strip()}


def docker_prune(project_root: Path) -> dict:
    """Remove unused containers, images, networks, and build cache.

    Returns:
        {"ok": True, "output": "..."} or {"error": "..."}
    """
    r = run_docker("system", "prune", "-f", cwd=project_root, timeout=120)
    if r.returncode != 0:
        return {"error": r.stderr.strip() or "Prune failed"}

    return {"ok": True, "output": r.stdout.strip()}


def docker_networks(project_root: Path) -> dict:
    """List Docker networks.

    Returns:
        {"available": True, "networks": [{name, driver, scope, id}, ...]}
    """
    r = run_docker(
        "network", "ls", "--format", "{{json .}}",
        cwd=project_root, timeout=10,
    )
    if r.returncode != 0:
        return {"available": False, "error": r.stderr.strip() or "Docker not available"}

    networks = []
    for line in r.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            info = json.loads(line)
            networks.append({
                "id": info.get("ID", ""),
                "name": info.get("Name", ""),
                "driver": info.get("Driver", ""),
                "scope": info.get("Scope", ""),
            })
        except json.JSONDecodeError:
            continue

    return {"available": True, "networks": networks}


def docker_volumes(project_root: Path) -> dict:
    """List Docker volumes.

    Returns:
        {"available": True, "volumes": [{name, driver, mountpoint}, ...]}
    """
    r = run_docker(
        "volume", "ls", "--format", "{{json .}}",
        cwd=project_root, timeout=10,
    )
    if r.returncode != 0:
        return {"available": False, "error": r.stderr.strip() or "Docker not available"}

    volumes = []
    for line in r.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            info = json.loads(line)
            volumes.append({
                "name": info.get("Name", ""),
                "driver": info.get("Driver", ""),
                "mountpoint": info.get("Mountpoint", ""),
                "labels": info.get("Labels", ""),
            })
        except json.JSONDecodeError:
            continue

    return {"available": True, "volumes": volumes}


def docker_inspect(project_root: Path, container_id: str) -> dict:
    """Inspect a Docker container.

    Args:
        container_id: Container ID or name.

    Returns:
        {"ok": True, "detail": {...}} or {"error": "..."}
    """
    if not container_id:
        return {"error": "Missing container ID"}

    r = run_docker("inspect", container_id, cwd=project_root, timeout=10)
    if r.returncode != 0:
        return {"error": r.stderr.strip() or f"Cannot inspect '{container_id}'"}

    try:
        data = json.loads(r.stdout)
        if isinstance(data, list) and len(data) > 0:
            raw = data[0]
            return {
                "ok": True,
                "detail": {
                    "id": raw.get("Id", "")[:12],
                    "name": (raw.get("Name", "") or "").lstrip("/"),
                    "image": raw.get("Config", {}).get("Image", ""),
                    "state": raw.get("State", {}),
                    "created": raw.get("Created", ""),
                    "platform": raw.get("Platform", ""),
                    "restart_policy": raw.get("HostConfig", {}).get("RestartPolicy", {}),
                    "ports": raw.get("NetworkSettings", {}).get("Ports", {}),
                    "mounts": [
                        {"source": m.get("Source", ""), "destination": m.get("Destination", ""), "mode": m.get("Mode", "")}
                        for m in raw.get("Mounts", [])
                    ],
                    "env": raw.get("Config", {}).get("Env", []),
                    "cmd": raw.get("Config", {}).get("Cmd", []),
                    "labels": raw.get("Config", {}).get("Labels", {}),
                },
            }
        return {"error": "Empty inspect result"}
    except json.JSONDecodeError:
        return {"error": "Failed to parse inspect output"}


def docker_pull(project_root: Path, image: str) -> dict:
    """Pull a Docker image.

    Args:
        image: Image name (e.g., 'nginx:latest').

    Returns:
        {"ok": True, "output": "..."} or {"error": "..."}
    """
    if not image:
        return {"error": "Missing image name"}

    r = run_docker("pull", image, cwd=project_root, timeout=300)
    if r.returncode != 0:
        return {"error": r.stderr.strip() or f"Failed to pull '{image}'"}

    return {"ok": True, "image": image, "output": r.stdout.strip()}


def docker_exec_cmd(project_root: Path, container_id: str, command: str) -> dict:
    """Execute a command in a running container.

    Args:
        container_id: Container ID or name.
        command: Command to execute (e.g., 'ls -la /app').

    Returns:
        {"ok": True, "output": "...", "exit_code": int} or {"error": "..."}
    """
    if not container_id:
        return {"error": "Missing container ID"}
    if not command:
        return {"error": "Missing command"}

    # Split command into args — simple split, good enough for most cases
    cmd_args = command.split()
    r = run_docker("exec", container_id, *cmd_args, cwd=project_root, timeout=30)

    return {
        "ok": r.returncode == 0,
        "container": container_id,
        "command": command,
        "output": r.stdout.strip(),
        "stderr": r.stderr.strip() if r.returncode != 0 else "",
        "exit_code": r.returncode,
    }


def docker_rm(project_root: Path, container_id: str, *, force: bool = False) -> dict:
    """Remove a Docker container.

    Args:
        container_id: Container ID or name.
        force: Force remove running container (default False).

    Returns:
        {"ok": True} or {"error": "..."}
    """
    if not container_id:
        return {"error": "Missing container ID"}

    args = ["rm"]
    if force:
        args.append("-f")
    args.append(container_id)

    r = run_docker(*args, cwd=project_root, timeout=15)
    if r.returncode != 0:
        return {"error": r.stderr.strip() or f"Failed to remove '{container_id}'"}

    return {"ok": True, "container": container_id}


def docker_rmi(project_root: Path, image: str, *, force: bool = False) -> dict:
    """Remove a Docker image.

    Args:
        image: Image ID or name:tag.
        force: Force remove (default False).

    Returns:
        {"ok": True} or {"error": "..."}
    """
    if not image:
        return {"error": "Missing image name"}

    args = ["rmi"]
    if force:
        args.append("-f")
    args.append(image)

    r = run_docker(*args, cwd=project_root, timeout=30)
    if r.returncode != 0:
        return {"error": r.stderr.strip() or f"Failed to remove '{image}'"}

    return {"ok": True, "image": image, "output": r.stdout.strip()}


# ═══════════════════════════════════════════════════════════════════
#  Facilitate (generate)
# ═══════════════════════════════════════════════════════════════════


def generate_dockerfile(project_root: Path, stack_name: str) -> dict:
    """Generate a Dockerfile for the given stack.

    Returns:
        {"ok": True, "file": {...}} or {"error": "..."}
    """
    from src.core.services.generators.dockerfile import generate_dockerfile as _gen

    result = _gen(project_root, stack_name)
    if result is None:
        from src.core.services.generators.dockerfile import supported_stacks

        return {
            "error": f"No Dockerfile template for stack '{stack_name}'",
            "supported": supported_stacks(),
        }

    return {"ok": True, "file": result.model_dump()}


def generate_dockerignore(project_root: Path, stack_names: list[str]) -> dict:
    """Generate a .dockerignore for the given stacks.

    Returns:
        {"ok": True, "file": {...}}
    """
    from src.core.services.generators.dockerignore import generate_dockerignore as _gen

    result = _gen(project_root, stack_names)
    return {"ok": True, "file": result.model_dump()}


def generate_compose(
    project_root: Path,
    modules: list[dict],
    *,
    project_name: str = "",
) -> dict:
    """Generate a docker-compose.yml from detected modules.

    Returns:
        {"ok": True, "file": {...}} or {"error": "..."}
    """
    from src.core.services.generators.compose import generate_compose as _gen

    result = _gen(project_root, modules, project_name=project_name)
    if result is None:
        return {"error": "No eligible modules for compose generation"}

    return {"ok": True, "file": result.model_dump()}


def generate_compose_from_wizard(
    project_root: Path,
    services: list[dict],
    *,
    project_name: str = "",
) -> dict:
    """Generate a docker-compose.yml from user-defined service specifications.

    Args:
        project_root: Project root directory.
        services: List of service dicts with:
            name, image, build_context, dockerfile, ports, volumes,
            environment, depends_on, restart, command, networks.
        project_name: Optional project name for compose.

    Returns:
        {"ok": True, "file": {...}} or {"error": "..."}
    """
    from src.core.models.template import GeneratedFile

    if not services:
        return {"error": "At least one service is required"}

    import yaml

    compose: dict = {"services": {}}
    if project_name:
        compose["name"] = project_name

    all_networks: set[str] = set()

    for svc in services:
        name = (svc.get("name") or "").strip()
        if not name:
            continue

        spec: dict = {}

        # Image vs build
        image = (svc.get("image") or "").strip()
        build_ctx = (svc.get("build_context") or "").strip()
        dockerfile = (svc.get("dockerfile") or "").strip()

        if image and not build_ctx:
            spec["image"] = image
        elif build_ctx:
            build_def: dict = {"context": build_ctx}
            if dockerfile:
                build_def["dockerfile"] = dockerfile
            spec["build"] = build_def
            if image:
                spec["image"] = image
        elif not image and not build_ctx:
            spec["image"] = name  # fallback

        # Ports
        ports = svc.get("ports", [])
        if ports:
            spec["ports"] = [str(p) for p in ports if p]

        # Volumes
        volumes = svc.get("volumes", [])
        if volumes:
            spec["volumes"] = [str(v) for v in volumes if v]

        # Environment
        env = svc.get("environment", {})
        if isinstance(env, dict) and env:
            spec["environment"] = {k: str(v) for k, v in env.items()}
        elif isinstance(env, list) and env:
            spec["environment"] = [str(e) for e in env if e]

        # Depends on
        deps = svc.get("depends_on", [])
        if deps:
            spec["depends_on"] = [str(d) for d in deps if d]

        # Restart
        restart = (svc.get("restart") or "unless-stopped").strip()
        if restart:
            spec["restart"] = restart

        # Command
        command = (svc.get("command") or "").strip()
        if command:
            spec["command"] = command

        # Networks
        networks = svc.get("networks", [])
        if networks:
            spec["networks"] = [str(n) for n in networks if n]
            all_networks.update(n for n in networks if n)

        # Container name
        container_name = (svc.get("container_name") or "").strip()
        if container_name:
            spec["container_name"] = container_name

        # Health check
        healthcheck = svc.get("healthcheck")
        if isinstance(healthcheck, dict) and healthcheck:
            spec["healthcheck"] = healthcheck

        # Build args
        build_args = svc.get("build_args")
        if isinstance(build_args, dict) and build_args:
            if "build" in spec and isinstance(spec["build"], dict):
                spec["build"]["args"] = {k: str(v) for k, v in build_args.items()}
            elif "build" in spec:
                spec["build"] = {"context": spec["build"], "args": {k: str(v) for k, v in build_args.items()}}

        # Platform
        platform = (svc.get("platform") or "").strip()
        if platform:
            spec["platform"] = platform

        compose["services"][name] = spec

    # Add top-level networks if any
    if all_networks:
        compose["networks"] = {n: {} for n in sorted(all_networks)}

    content = "# Generated by DevOps Control Plane — Compose Wizard\n"
    content += yaml.dump(
        compose,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )

    file_data = GeneratedFile(
        path="docker-compose.yml",
        content=content,
        overwrite=False,
        reason=f"Compose wizard: {len(compose['services'])} service(s)",
    )

    return {"ok": True, "file": file_data.model_dump()}


def write_generated_file(project_root: Path, file_data: dict) -> dict:
    """Write a GeneratedFile to disk.

    Args:
        project_root: Project root directory.
        file_data: Dict with 'path', 'content', 'overwrite'.

    Returns:
        {"ok": True, "path": "...", "written": True} or {"error": "..."}
    """
    rel_path = file_data.get("path", "")
    content = file_data.get("content", "")
    overwrite = file_data.get("overwrite", False)

    if not rel_path or not content:
        return {"error": "Missing path or content"}

    target = project_root / rel_path

    if target.exists() and not overwrite:
        return {
            "error": f"File already exists: {rel_path} (use overwrite=true to replace)",
            "path": rel_path,
            "written": False,
        }

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    logger.info("Wrote generated file: %s", target)

    return {"ok": True, "path": rel_path, "written": True}

