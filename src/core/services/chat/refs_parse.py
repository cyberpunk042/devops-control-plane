"""
Chat @-reference parsing — extract and parse @-references from message text.

Supports references like:
    @run:run_20260217T120000Z_detect_a1b2
    @thread:thread_20260217T120000Z_c3d4
    @trace:trace_20260217T120000Z_e5f6
    @user:JohnDoe

This module is the low-level parsing layer. It extracts reference strings,
validates them, and splits them into (type, id) parts. No I/O, no resolution.

Resolution lives in ``refs_resolve.py``.
Autocomplete lives in ``refs_autocomplete.py``.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone


# ── Reference pattern ───────────────────────────────────────────
#
#   @<type>:<id>
#
# Type must be one of the valid reference types below.
# ID is a non-whitespace string of alphanumeric + underscore + dash + dots + slashes
#
_REF_PATTERN = re.compile(
    r"@(run|thread|trace|user|commit|branch|audit|code"
    r"|doc|media|release|file):([A-Za-z0-9_\-/.]+)"
)

# Valid reference types
_VALID_TYPES = frozenset({
    "run", "thread", "trace", "user",
    "commit", "branch", "audit", "code",
    "doc", "media", "release", "file",
})


def _relative_time(iso_str: str) -> str:
    """Convert an ISO timestamp to a relative time string like '2h ago'."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = datetime.now(timezone.utc) - dt
        secs = int(diff.total_seconds())
        if secs < 60:
            return "just now"
        if secs < 3600:
            m = secs // 60
            return f"{m}m ago"
        if secs < 86400:
            h = secs // 3600
            return f"{h}h ago"
        d = secs // 86400
        if d == 1:
            return "1 day ago"
        return f"{d} days ago"
    except Exception:
        return iso_str


def parse_refs(text: str) -> list[str]:
    """Extract @-references from message text.

    Args:
        text: Message text to scan.

    Returns:
        List of unique reference strings (e.g. ["@run:run_xxx", "@thread:thread_yyy"]).
        Order is preserved (first occurrence).

    Examples:
        >>> parse_refs("Deployed @run:run_123 to staging")
        ['@run:run_123']
        >>> parse_refs("See @thread:t1 and @trace:tr1")
        ['@thread:t1', '@trace:tr1']
        >>> parse_refs("No references here")
        []
    """
    seen: set[str] = set()
    refs: list[str] = []
    for match in _REF_PATTERN.finditer(text):
        ref = f"@{match.group(1)}:{match.group(2)}"
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def parse_ref_parts(ref: str) -> tuple[str, str] | None:
    """Parse a reference string into (type, id).

    Args:
        ref: Reference string like "@run:run_123".

    Returns:
        Tuple of (type, id) or None if invalid.
    """
    if not ref.startswith("@"):
        return None
    match = _REF_PATTERN.fullmatch(ref)
    if not match:
        return None
    return match.group(1), match.group(2)
