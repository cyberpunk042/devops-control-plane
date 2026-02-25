"""
L4 Execution — Offline / airgapped install cache.

L14: Pre-download plan artifacts to a local cache so installations
can proceed without network access. Supports binary downloads,
pip wheels, npm tarballs, and generic URLs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default cache directory — under the project's .state directory
_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "devops-cp" / "install-cache"


def get_cache_dir() -> Path:
    """Return (and create if needed) the offline install cache directory."""
    cache = Path(os.environ.get("DEVOPS_INSTALL_CACHE", str(_DEFAULT_CACHE_DIR)))
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def cache_plan(
    plan: dict,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    """Pre-download all artifacts needed by a plan.

    Walks the plan steps and downloads:
    - ``github_release`` steps → binary/archive to cache
    - ``download`` steps → file to cache
    - ``tool`` steps with curl commands → install script to cache
    - ``packages`` steps → deferred (can't easily pre-download OS packages)

    Args:
        plan: Resolved install plan from ``resolve_install_plan()``.
        cache_dir: Override cache directory.

    Returns::

        {
            "ok": True,
            "cached": 3,
            "failed": 0,
            "artifacts": [
                {"step_id": "...", "type": "script", "path": "...", "sha256": "..."},
                ...
            ],
            "cache_dir": "/home/user/.cache/devops-cp/install-cache",
        }
    """
    from src.core.services.tool_install.execution.script_verify import (
        is_curl_pipe_command,
        extract_script_url,
        download_and_verify_script,
    )

    cdir = cache_dir or get_cache_dir()
    tool = plan.get("tool", "unknown")
    tool_cache = cdir / tool
    tool_cache.mkdir(parents=True, exist_ok=True)

    artifacts: list[dict] = []
    failed: list[dict] = []

    for i, step in enumerate(plan.get("steps", [])):
        step_id = step.get("id", f"step_{i}")
        step_type = step.get("type", "")

        # curl-pipe-bash scripts
        command = step.get("command", [])
        if isinstance(command, list) and is_curl_pipe_command(command):
            url = extract_script_url(command)
            if url:
                dl = download_and_verify_script(url)
                if dl["ok"]:
                    # Move to cache
                    cached_path = tool_cache / f"{step_id}.sh"
                    shutil.move(dl["path"], str(cached_path))
                    artifacts.append({
                        "step_id": step_id,
                        "type": "script",
                        "url": url,
                        "path": str(cached_path),
                        "sha256": dl["sha256"],
                        "size_bytes": dl["size_bytes"],
                    })
                else:
                    failed.append({"step_id": step_id, "error": dl["error"]})
                continue

        # download steps (data packs, binaries)
        if step_type == "download":
            url = step.get("url", "")
            if url:
                dest = tool_cache / f"{step_id}_{Path(url).name}"
                result = _download_to_cache(url, dest, step.get("checksum"))
                if result["ok"]:
                    artifacts.append({
                        "step_id": step_id,
                        "type": "download",
                        "url": url,
                        "path": str(dest),
                        "sha256": result["sha256"],
                        "size_bytes": result["size_bytes"],
                    })
                else:
                    failed.append({"step_id": step_id, "error": result["error"]})

        # github_release steps
        if step_type == "github_release":
            repo = step.get("repo")
            if repo:
                # We can pre-resolve and cache the URL
                artifacts.append({
                    "step_id": step_id,
                    "type": "github_release",
                    "repo": repo,
                    "status": "deferred",
                    "note": "GitHub release URLs are version-specific; "
                            "use cache_github_release() for explicit versions.",
                })

    # Write manifest
    manifest = {
        "tool": tool,
        "plan_steps": len(plan.get("steps", [])),
        "cached": len(artifacts),
        "failed": len(failed),
        "artifacts": artifacts,
    }
    manifest_path = tool_cache / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return {
        "ok": len(failed) == 0,
        "cached": len(artifacts),
        "failed": len(failed),
        "errors": failed if failed else None,
        "artifacts": artifacts,
        "cache_dir": str(tool_cache),
        "manifest": str(manifest_path),
    }


def load_cached_artifacts(
    tool: str,
    cache_dir: Path | None = None,
) -> dict[str, dict] | None:
    """Load cached artifacts manifest for a tool.

    Returns:
        Dict mapping step_id → artifact info, or None if no cache.
    """
    cdir = cache_dir or get_cache_dir()
    manifest_path = cdir / tool / "manifest.json"
    if not manifest_path.exists():
        return None

    try:
        manifest = json.loads(manifest_path.read_text())
        return {a["step_id"]: a for a in manifest.get("artifacts", [])}
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def install_from_cache(
    step: dict,
    cached_artifact: dict,
) -> dict[str, Any]:
    """Modify a step to use its cached artifact instead of downloading.

    Args:
        step: Original step dict from the plan.
        cached_artifact: Artifact info from ``load_cached_artifacts()``.

    Returns:
        Modified step dict that uses the local file.
    """
    from src.core.services.tool_install.execution.script_verify import (
        rewrite_curl_pipe_to_safe,
    )

    atype = cached_artifact.get("type")
    path = cached_artifact.get("path", "")

    if not Path(path).exists():
        return {
            "ok": False,
            "error": f"Cached artifact missing: {path}",
        }

    if atype == "script":
        # Rewrite curl-pipe-bash to use local file
        command = step.get("command", [])
        step = {**step, "command": rewrite_curl_pipe_to_safe(command, path)}
        step["_cached"] = True
        return step

    if atype == "download":
        # Point download step at local file
        step = {**step, "url": f"file://{path}", "_cached": True}
        return step

    return step


def clear_cache(
    tool: str | None = None,
    cache_dir: Path | None = None,
) -> dict:
    """Clear the install cache for a specific tool or all tools.

    Args:
        tool: Tool ID to clear, or None to clear everything.
        cache_dir: Override cache directory.

    Returns:
        ``{"ok": True, "cleared": "kubectl"}`` or
        ``{"ok": True, "cleared": "all"}``.
    """
    cdir = cache_dir or get_cache_dir()

    if tool:
        target = cdir / tool
        if target.exists():
            shutil.rmtree(target)
        return {"ok": True, "cleared": tool}
    else:
        if cdir.exists():
            shutil.rmtree(cdir)
            cdir.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "cleared": "all"}


def cache_status(cache_dir: Path | None = None) -> dict:
    """Return summary of cached tools and their sizes.

    Returns::

        {
            "cache_dir": "/home/user/.cache/devops-cp/install-cache",
            "tools": {"kubectl": {"files": 3, "size_mb": 12.3}, ...},
            "total_size_mb": 45.6,
        }
    """
    cdir = cache_dir or get_cache_dir()
    tools: dict[str, dict] = {}
    total_bytes = 0

    if cdir.exists():
        for item in cdir.iterdir():
            if item.is_dir():
                files = list(item.rglob("*"))
                size = sum(f.stat().st_size for f in files if f.is_file())
                tools[item.name] = {
                    "files": len([f for f in files if f.is_file()]),
                    "size_mb": round(size / (1024 * 1024), 1),
                }
                total_bytes += size

    return {
        "cache_dir": str(cdir),
        "tools": tools,
        "total_size_mb": round(total_bytes / (1024 * 1024), 1),
    }


# ── Private helpers ───────────────────────────────────────

def _download_to_cache(
    url: str,
    dest: Path,
    expected_checksum: str | None = None,
    timeout: int = 60,
) -> dict:
    """Download a URL to a local file with optional checksum verification."""
    try:
        result = subprocess.run(
            ["curl", "-fsSL", "--max-time", str(timeout), "-o", str(dest), url],
            capture_output=True, text=True, timeout=timeout + 10,
        )
        if result.returncode != 0:
            return {"ok": False, "error": f"curl failed: {result.stderr[:200]}"}

        # Compute checksum
        hasher = hashlib.sha256()
        with open(dest, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        actual_sha = hasher.hexdigest()

        if expected_checksum:
            expected = expected_checksum.removeprefix("sha256:").lower()
            if actual_sha != expected:
                dest.unlink(missing_ok=True)
                return {
                    "ok": False,
                    "error": f"Checksum mismatch: expected {expected}, got {actual_sha}",
                }

        return {
            "ok": True,
            "sha256": actual_sha,
            "size_bytes": dest.stat().st_size,
        }
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"ok": False, "error": str(exc)}
