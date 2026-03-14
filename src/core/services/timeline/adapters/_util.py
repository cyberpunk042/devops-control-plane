"""
Shared utilities for timeline adapters.
"""

from __future__ import annotations

from datetime import datetime, timezone


def iso_to_ts(iso: str) -> float:
    """Convert an ISO 8601 timestamp string to a unix epoch float.

    Handles strings with or without timezone info.
    Returns 0.0 on parse failure.
    """
    if not iso:
        return 0.0
    try:
        # Python 3.11+ handles 'Z' suffix; earlier versions do not
        iso_clean = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, OverflowError):
        return 0.0
