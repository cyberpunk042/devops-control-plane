"""
DevOps — card preferences and activity log.

Manages per-card user preferences (auto / manual / hidden / visible)
stored in ``.state/devops_prefs.json``.

Activity logging and cache data are handled by the mediator
(see ``src.core.services.mediator``).  This module retains only
the preference and activity-log APIs that route/wizard code uses.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PREFS_FILE = ".state/devops_prefs.json"

# ── Default card preferences ────────────────────────────────────
# Covers both DevOps tab cards and Integrations tab cards.
# Values: "auto" | "manual" | "hidden" | "visible"

_DEFAULT_PREFS: dict[str, str] = {
    # DevOps tab
    "security": "auto",
    "testing": "auto",
    "quality": "auto",
    "packages": "auto",
    "env": "auto",
    "docs": "auto",
    "k8s": "auto",
    "terraform": "auto",
    "dns": "hidden",       # No integration card yet — hide by default
    # Integrations tab
    "int:git": "auto",
    "int:github": "auto",
    "int:ci": "auto",
    "int:docker": "auto",
    "int:k8s": "auto",
    "int:terraform": "auto",
    "int:pages": "auto",
    "int:scripts": "auto",
}


# ── Internal helpers ────────────────────────────────────────────

def _prefs_path(project_root: Path) -> Path:
    return project_root / _PREFS_FILE


# ── Audit scan activity log (delegated) ─────────────────────────

from .activity import (  # noqa: F401, E402
    record_scan_activity as _record_scan_activity,
    record_event,
    load_activity,
    _extract_summary,
    _card_label,
    _activity_path,
)


def _record_activity(
    project_root: Path,
    card_key: str,
    status: str,
    elapsed_s: float,
    data: dict,
    error_msg: str = "",
    *,
    bust: bool = False,
) -> None:
    """Thin wrapper — delegates to devops_activity.record_scan_activity."""
    _record_scan_activity(
        project_root, card_key, status, elapsed_s, data, error_msg, bust=bust,
    )


# ── Public API: preferences ─────────────────────────────────────


# Valid pref values
_VALID_PREFS = ("auto", "manual", "hidden", "visible")


def load_prefs(project_root: Path) -> dict:
    """Load card preferences (auto / manual / visible / hidden per card)."""
    pf = _prefs_path(project_root)
    if not pf.exists():
        return dict(_DEFAULT_PREFS)
    try:
        raw = json.loads(pf.read_text(encoding="utf-8"))
        merged = dict(_DEFAULT_PREFS)
        for k, v in raw.items():
            if v in _VALID_PREFS:
                merged[k] = v
        return merged
    except (json.JSONDecodeError, IOError):
        return dict(_DEFAULT_PREFS)


def save_prefs(project_root: Path, prefs: dict) -> dict:
    """Save card preferences.  Returns the validated result."""
    merged = dict(_DEFAULT_PREFS)
    for k, v in prefs.items():
        if v in _VALID_PREFS:
            merged[k] = v

    pf = _prefs_path(project_root)
    pf.parent.mkdir(parents=True, exist_ok=True)
    pf.write_text(json.dumps(merged, indent=2), encoding="utf-8")

    return merged
