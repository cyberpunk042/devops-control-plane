"""Docker container & compose operations — observe and act."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.core.services.docker_common import run_docker, run_compose
from src.core.services.docker_detect import find_compose_file

logger = logging.getLogger(__name__)

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
