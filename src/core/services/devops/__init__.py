"""
DevOps — preferences and activity log.

Sub-modules::

    cache.py     — card preferences (auto / manual / hidden)
    activity.py  — activity event log (view, seed, manage)

Public re-exports below keep ``from src.core.services.devops import X`` working.
"""

from __future__ import annotations

# ── Preferences ──
from .cache import (  # noqa: F401
    record_event,
    load_prefs,
    save_prefs,
)

# ── Activity ──
from .activity import (  # noqa: F401
    load_activity,
    record_scan_activity,
)
