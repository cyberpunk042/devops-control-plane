"""
Mediator configuration — runtime-tunable settings.

Persisted to ``.state/mediator_config.json``.  These settings
control the worker pool, filesystem watcher, and tier dispatch
pipeline.  Changes are applied live where possible; some settings
(like ``num_workers``) require a server restart.

Public API
----------
- ``load_config(project_root)``  → dict (merged with defaults)
- ``save_config(project_root, data)``  → dict (validated + saved)
- ``get_defaults()``  → dict (factory defaults)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CONFIG_FILE = ".state/mediator_config.json"

# ── Defaults ────────────────────────────────────────────────────

_DEFAULTS: dict[str, Any] = {
    "workers": {
        "num_workers": 4,
        "capacity": 6,
        "yield_to_web": True,
    },
    "watcher": {
        "poll_interval": 5.0,
        "smart_dispatch": True,
        "enabled": True,
    },
    "tiers": {
        "T1:visible":   {"priority": 1},
        "T2:infra":     {"priority": 2},
        "T3:heavy":     {"priority": 2},
        "T4:index":     {"priority": 3},
        "T5:aggregate": {"priority": 4},
        "T6:deep":      {"priority": 4},
    },
}


# ── Public API ──────────────────────────────────────────────────


def get_defaults() -> dict[str, Any]:
    """Return factory defaults (deep copy)."""
    import copy
    return copy.deepcopy(_DEFAULTS)


def load_config(project_root: Path) -> dict[str, Any]:
    """Load mediator config, merging with defaults.

    Missing keys get filled from ``_DEFAULTS``.  Extra keys
    in the file are preserved (forward compatibility).
    """
    config_path = project_root / _CONFIG_FILE
    defaults = get_defaults()

    if not config_path.exists():
        return defaults

    try:
        raw = config_path.read_text(encoding="utf-8")
        saved = json.loads(raw) if raw.strip() else {}
    except Exception as exc:
        logger.warning("Failed to read mediator config: %s", exc)
        return defaults

    # Deep merge: defaults ← saved
    merged = _deep_merge(defaults, saved)

    # Validate & clamp values
    merged = _validate(merged)
    return merged


def save_config(
    project_root: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Save mediator config.  Returns the validated/merged result."""
    config_path = project_root / _CONFIG_FILE
    validated = _validate(config)

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(validated, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info("Mediator config saved to %s", config_path)
    except Exception as exc:
        logger.error("Failed to save mediator config: %s", exc)

    return validated


# ── Internal helpers ────────────────────────────────────────────


def _deep_merge(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    """Recursively merge override into base (base is mutated)."""
    for key, val in override.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(val, dict)
        ):
            _deep_merge(base[key], val)
        else:
            base[key] = val
    return base


def _validate(config: dict[str, Any]) -> dict[str, Any]:
    """Validate and clamp config values to safe ranges."""
    w = config.get("workers", {})
    w["num_workers"] = max(1, min(16, int(w.get("num_workers", 4))))
    w["capacity"] = max(1, min(32, int(w.get("capacity", 6))))
    w["yield_to_web"] = bool(w.get("yield_to_web", True))
    config["workers"] = w

    wt = config.get("watcher", {})
    wt["poll_interval"] = max(1.0, min(60.0, float(wt.get("poll_interval", 5.0))))
    wt["smart_dispatch"] = bool(wt.get("smart_dispatch", True))
    wt["enabled"] = bool(wt.get("enabled", True))
    config["watcher"] = wt

    tiers = config.get("tiers", {})
    for tier_name in list(tiers.keys()):
        tier = tiers[tier_name]
        if isinstance(tier, dict) and "priority" in tier:
            tier["priority"] = max(0, min(4, int(tier["priority"])))
    config["tiers"] = tiers

    return config
