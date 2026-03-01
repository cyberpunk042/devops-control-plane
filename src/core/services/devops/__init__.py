"""
DevOps — cache, activity log, preferences.

Sub-modules::

    cache.py     — card-level caching, invalidation, event recording, prefs
    activity.py  — activity event log (view, seed, manage)

Public re-exports below keep ``from src.core.services.devops import X`` working.
The ``devops_cache`` module-level import pattern is preserved via shim.
"""

from __future__ import annotations

# ── Cache ──
from .cache import (  # noqa: F401
    get_cached,
    invalidate,
    invalidate_all,
    invalidate_scope,
    invalidate_with_cascade,
    register_compute,
    recompute_all,
    record_event,
    load_prefs,
    save_prefs,
    _load_cache,
    _save_cache,
    _max_mtime,
    _WATCH_PATHS,
)

# ── Activity ──
from .activity import (  # noqa: F401
    load_activity,
    record_scan_activity,
)
