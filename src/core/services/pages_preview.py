"""
Pages preview — manages preview server processes.

Handles starting, stopping, and listing preview servers for
built page segments.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from src.core.services.pages_builders import get_builder
from src.core.services.pages_engine import PAGES_WORKSPACE, get_segment

# In-memory tracking — survives within a single server process
_preview_servers: dict[str, dict] = {}  # name -> {proc, port, started_at}
_MAX_PREVIEWS = 3


def start_preview(project_root: Path, name: str) -> dict:
    """Start a preview server for a segment.

    Returns:
        Dict with {ok, port, error}.
    """
    # Check if already running
    if name in _preview_servers:
        info = _preview_servers[name]
        proc = info["proc"]
        if proc.poll() is None:  # Still running
            return {"ok": True, "port": info["port"], "already_running": True}
        # Dead — clean up
        del _preview_servers[name]

    # Enforce max concurrency
    _cleanup_dead_previews()
    if len(_preview_servers) >= _MAX_PREVIEWS:
        return {"ok": False, "error": f"Max {_MAX_PREVIEWS} concurrent previews. Stop one first."}

    segment = get_segment(project_root, name)
    if segment is None:
        return {"ok": False, "error": f"Segment '{name}' not found"}

    builder = get_builder(segment.builder)
    if builder is None:
        return {"ok": False, "error": f"Builder '{segment.builder}' not found"}

    workspace = project_root / PAGES_WORKSPACE / name

    # Resolve source for the builder
    source_path = (project_root / segment.source).resolve()
    segment.source = str(source_path)

    # Ensure scaffolded
    if not workspace.exists():
        builder.scaffold(segment, workspace)

    try:
        proc, port = builder.preview(segment, workspace)
        _preview_servers[name] = {
            "proc": proc,
            "port": port,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        return {"ok": True, "port": port}
    except NotImplementedError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Failed to start preview: {e}"}


def stop_preview(name: str) -> dict:
    """Stop a preview server.

    Returns:
        Dict with {ok, error}.
    """
    if name not in _preview_servers:
        return {"ok": False, "error": f"No preview running for '{name}'"}

    info = _preview_servers.pop(name)
    proc = info["proc"]
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    return {"ok": True}


def list_previews() -> list[dict]:
    """List all running preview servers."""
    _cleanup_dead_previews()
    result = []
    for name, info in _preview_servers.items():
        result.append({
            "name": name,
            "port": info["port"],
            "started_at": info["started_at"],
            "running": info["proc"].poll() is None,
        })
    return result


def _cleanup_dead_previews() -> None:
    """Remove entries for processes that have died."""
    dead = [name for name, info in _preview_servers.items() if info["proc"].poll() is not None]
    for name in dead:
        del _preview_servers[name]
