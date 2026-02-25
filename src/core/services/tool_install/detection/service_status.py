"""
L3 Detection — Service and data pack status.

Read-only probes: systemctl status, file timestamps, disk usage.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from src.core.services.tool_install.data.recipes import TOOL_RECIPES
from src.core.services.tool_install.domain.download_helpers import _fmt_size


# ── Data pack storage conventions ──

DATA_DIRS: dict[str, str] = {
    "vulnerability_db": "~/.cache/trivy",
    "language_model": "~/.cache/spacy",
    "ml_model": "~/.cache/whisper",
    "container_image": "/var/lib/docker",
    "geoip": "~/.local/share/geoip",
    "fonts": "~/.local/share/fonts",
}

DATA_UPDATE_SCHEDULES: dict[str, int | None] = {
    "daily": 86400,
    "weekly": 604800,
    "monthly": 2592000,
    "manual": None,
}


def check_data_freshness(pack_id: str) -> dict:
    """Check if a data pack needs updating.

    Reads the timestamp marker written by _execute_download_step()
    and compares against the recipe's update_schedule.

    Returns::

        {"stale": True/False, "schedule": "daily", "age_seconds": N}
    """
    recipe = TOOL_RECIPES.get(pack_id, {})
    schedule = recipe.get("update_schedule", "manual")
    ttl = DATA_UPDATE_SCHEDULES.get(schedule)

    if ttl is None:
        return {"stale": False, "schedule": "manual"}

    marker = Path(f"~/.cache/devops-cp/data-stamps/{pack_id}").expanduser()
    if not marker.exists():
        return {"stale": True, "reason": "Never downloaded", "schedule": schedule}

    try:
        age = time.time() - marker.stat().st_mtime
    except OSError:
        return {"stale": True, "reason": "Cannot read timestamp", "schedule": schedule}

    return {
        "stale": age > ttl,
        "age_seconds": int(age),
        "schedule": schedule,
        "next_update": max(0, int(ttl - age)),
    }


def get_data_pack_usage() -> list[dict]:
    """Report disk usage of known data pack directories.

    Returns a list of dicts with type, path, size_bytes, size_human.
    """
    usage: list[dict] = []
    for pack_type, base_dir in DATA_DIRS.items():
        path = Path(base_dir).expanduser()
        if path.exists():
            try:
                size = sum(
                    f.stat().st_size
                    for f in path.rglob("*")
                    if f.is_file()
                )
                usage.append({
                    "type": pack_type,
                    "path": str(path),
                    "size_bytes": size,
                    "size_human": _fmt_size(size),
                })
            except OSError:
                pass
    return usage


# ── Init system detection ──

def _detect_init_system() -> str:
    """Detect the init system (systemd, openrc, initd, or unknown)."""
    if Path("/run/systemd/system").exists():
        return "systemd"
    if shutil.which("rc-service"):
        return "openrc"
    if Path("/etc/init.d").exists():
        return "initd"
    return "unknown"


def get_service_status(service: str) -> dict:
    """Get comprehensive service status (systemd only).

    Returns active state, sub-state, load state for systemd services.
    Falls back to a simple active check for other init systems.
    """
    init = _detect_init_system()

    if init == "systemd":
        result: dict = {}
        for prop in ("ActiveState", "SubState", "LoadState"):
            try:
                r = subprocess.run(
                    ["systemctl", "show", service, f"--property={prop}"],
                    capture_output=True, text=True, timeout=5,
                )
                key, _, val = r.stdout.strip().partition("=")
                result[key.lower()] = val
            except Exception:
                pass

        return {
            "service": service,
            "init_system": "systemd",
            "active": result.get("activestate") == "active",
            "state": result.get("activestate", "unknown"),
            "sub_state": result.get("substate", "unknown"),
            "loaded": result.get("loadstate") == "loaded",
        }

    return {"service": service, "init_system": init, "active": None, "state": "unknown"}
