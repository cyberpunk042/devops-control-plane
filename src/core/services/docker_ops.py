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
    if compose_path:
        compose_services = _parse_compose_services(compose_path)

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


def docker_build(project_root: Path, *, service: str | None = None) -> dict:
    """Build images via compose.

    Args:
        service: Optional specific service to build (default: all).

    Returns:
        {"ok": True, "output": "..."} or {"error": "..."}
    """
    compose_file = find_compose_file(project_root)
    if not compose_file:
        return {"error": "No compose file found"}

    args = ["build"]
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

