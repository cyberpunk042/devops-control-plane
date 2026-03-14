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


# ── Tier path classification ────────────────────────────────────
# Single source of truth for which paths belong to which tier.
# Imported by core.py (dispatch) and index_watcher.py (cycle dispatch).

TIER_PATHS: dict[str, frozenset[str]] = {
    "T1:visible": frozenset({
        "devops.git", "devops.ci", "devops.packages",
        "devops.quality", "devops.docs", "devops.dns",
    }),
    "T2:infra": frozenset({
        "devops.docker", "devops.k8s", "devops.terraform",
        "devops.env", "devops.github",
    }),
    "T3:heavy": frozenset({
        "devops.security", "devops.testing",
    }),
    "T5:aggregate": frozenset({
        "devops.status",
    }),
}

# Prefix-based tier classification (paths that match by prefix)
TIER_PREFIXES: dict[str, list[str]] = {
    "T1:visible":   ["catalog."],
    "T2:infra":     ["github."],
    "T4:index":     ["index."],
    "T5:aggregate": ["posture."],
}

# Audit tiers (separate sets for clarity)
AUDIT_L0L1 = frozenset({
    "audit.scores", "audit.system", "audit.deps",
    "audit.structure", "audit.clients",
})
AUDIT_L2 = frozenset({
    "audit.system_deep", "audit.l2_structure",
    "audit.l2_quality", "audit.l2_repo",
    "audit.l2_risks", "audit.scores_enriched",
})


def tier_for_path(path: str) -> str:
    """Classify a mediator path into its tier name.

    Returns the tier name (e.g. ``"T1:visible"``) or ``"T4:index"``
    as fallback for unclassified paths.
    """
    # Check exact-match sets first
    for tier_name, path_set in TIER_PATHS.items():
        if path in path_set:
            return tier_name

    # Check prefix-based classification
    for tier_name, prefixes in TIER_PREFIXES.items():
        for prefix in prefixes:
            if path.startswith(prefix):
                return tier_name

    # Audit classification
    if path in AUDIT_L0L1:
        return "T5:aggregate"
    if path in AUDIT_L2:
        return "T6:deep"

    # Fallback
    return "T4:index"


def tier_priority_for_path(
    path: str,
    config: dict[str, Any] | None = None,
) -> int:
    """Return the work queue priority for a mediator path.

    Looks up the path's tier, then reads the tier's priority from
    config.  If no config is provided, uses the defaults.

    Parameters
    ----------
    path : str
        Mediator node path (e.g. ``"devops.git"``).
    config : dict | None
        Mediator config dict (from ``load_config``).  If ``None``,
        uses ``_DEFAULTS``.

    Returns
    -------
    int
        Priority value (0=CRITICAL … 4=IDLE).
    """
    tier_name = tier_for_path(path)
    tiers = (config or _DEFAULTS).get("tiers", {})
    tier_cfg = tiers.get(tier_name, {})
    return tier_cfg.get("priority", 3)  # fallback to LOW


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
