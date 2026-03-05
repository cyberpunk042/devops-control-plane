"""
Server settings — server-side feature toggles.

Persisted to ``.state/server_settings.json``.  These are server-level
settings that affect background services and API behaviour — separate
from browser preferences (localStorage) and devops card prefs.

Current settings:
    peek_index_enabled: bool
        Controls whether the project index (background AST parse,
        symbol index, peek cache) runs on the server.  When disabled,
        peek-refs returns empty and no background index thread starts.
        Does NOT affect Docusaurus build-time peek (that uses its own
        feature flag in project.yml → pages → segments → features).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SETTINGS_FILE = ".state/server_settings.json"

# ── Defaults ────────────────────────────────────────────────────

_DEFAULTS: dict[str, Any] = {
    "peek_index_enabled": True,
}


# ── Public API ──────────────────────────────────────────────────


def load_settings(project_root: Path) -> dict[str, Any]:
    """Load server settings, merging with defaults."""
    path = project_root / _SETTINGS_FILE
    if not path.is_file():
        return dict(_DEFAULTS)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        merged = dict(_DEFAULTS)
        merged.update(raw)
        return merged
    except (json.JSONDecodeError, IOError):
        return dict(_DEFAULTS)


def save_settings(project_root: Path, settings: dict[str, Any]) -> dict[str, Any]:
    """Save server settings.  Returns the validated/merged result."""
    merged = dict(_DEFAULTS)
    # Only accept known keys
    for key in _DEFAULTS:
        if key in settings:
            merged[key] = settings[key]

    path = project_root / _SETTINGS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2), encoding="utf-8")

    return merged


def is_peek_index_enabled(project_root: Path) -> bool:
    """Quick check: is the peek/index feature enabled?"""
    return bool(load_settings(project_root).get("peek_index_enabled", True))
