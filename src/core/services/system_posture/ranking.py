"""
Ranking engine — computes deprecation rank from version and EOL data.

Pure logic, no I/O.  The ``load_*`` helpers read the static JSON
databases shipped in ``data/``.  Everything else is deterministic
computation on version tuples and date arithmetic.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import PostureItem, RankLevel

_DATA_DIR = Path(__file__).parent / "data"


# ── Data loaders ────────────────────────────────────────────────


def load_os_lifecycle() -> dict[str, Any]:
    """Load OS lifecycle data from ``data/os_lifecycle.json``.

    Returns a nested dict keyed by distro name, then version string.
    Each entry has at minimum an ``eol`` field (YYYY-MM format).
    """
    path = _DATA_DIR / "os_lifecycle.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_tool_lifecycle() -> dict[str, Any]:
    """Load tool lifecycle data from ``data/tool_lifecycle.json``.

    Returns a dict keyed by tool name.  Each entry has:
      - ``current``: latest stable version string
      - ``min_supported``: minimum version still supported (optional)
      - ``version_scheme``: ``"semver"`` or ``"semver_minor"``
      - ``eol_versions``: dict of version → EOL date or detail object
    """
    path = _DATA_DIR / "tool_lifecycle.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# ── EOL-based ranking ──────────────────────────────────────────


def rank_by_eol(eol_str: str | None) -> RankLevel:
    """Compute rank from an end-of-life date string.

    Args:
        eol_str: EOL date in YYYY-MM format, or ``None``.

    Returns:
        RankLevel based on how far away the EOL date is.

    Thresholds::

        > now + 24 months:  Current   (🟢)
        > now + 6 months:   Aging     (🔵)
        > now:              Outdated  (🟡)  still alive but ending
        > now - 12 months:  Deprecated(🟠)  EOL within last year
        ≤ now - 12 months:  Dangerous (🔴)  EOL over a year ago
    """
    if not eol_str:
        return RankLevel.UNKNOWN

    try:
        parts = eol_str.split("-")
        eol_date = datetime(int(parts[0]), int(parts[1]), 1, tzinfo=timezone.utc)
    except (ValueError, IndexError):
        return RankLevel.UNKNOWN

    now = datetime.now(timezone.utc)
    delta_months = (eol_date.year - now.year) * 12 + (eol_date.month - now.month)

    if delta_months > 24:
        return RankLevel.CURRENT
    elif delta_months > 6:
        return RankLevel.AGING
    elif delta_months > 0:
        return RankLevel.OUTDATED
    elif delta_months > -12:
        return RankLevel.DEPRECATED
    else:
        return RankLevel.DANGEROUS


# ── Version parsing ─────────────────────────────────────────────


def parse_semver(version_str: str) -> tuple[int, ...] | None:
    """Parse a version string into a comparable tuple of ints.

    Handles common formats::

        "1.31.4"   → (1, 31, 4)
        "27.5.1"   → (27, 5, 1)
        "3.13"     → (3, 13)
        "0.14.11"  → (0, 14, 11)

    Returns ``None`` if the string cannot be parsed.
    """
    m = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", version_str)
    if not m:
        return None
    parts = [int(m.group(1)), int(m.group(2))]
    if m.group(3) is not None:
        parts.append(int(m.group(3)))
    return tuple(parts)


# ── Tool version ranking ───────────────────────────────────────


def rank_tool_version(
    installed: str,
    lifecycle: dict[str, Any],
) -> tuple[RankLevel, str]:
    """Rank a tool's installed version against its lifecycle data.

    This is the core ranking function for the toolchain pillar.
    It checks, in order:

    1. Is this exact version in the EOL list?  → rank by EOL date + CVEs
    2. Is there a known current version?       → rank by version gap
    3. Is there a minimum supported version?   → rank if below minimum

    Args:
        installed:  Installed version string (e.g. ``"1.24.0"``).
        lifecycle:  Entry from ``tool_lifecycle.json`` for this tool.

    Returns:
        Tuple of ``(RankLevel, detail_string)`` where detail_string
        is a human-readable explanation like ``"7 minor versions behind"``.
    """
    current_str = lifecycle.get("current", "")
    min_supported_str = lifecycle.get("min_supported", "")
    eol_versions: dict[str, Any] = lifecycle.get("eol_versions", {})

    installed_v = parse_semver(installed)
    current_v = parse_semver(current_str) if current_str else None

    if not installed_v:
        return RankLevel.UNKNOWN, f"Cannot parse version: {installed}"

    # ── Step 1: Check if this version is explicitly EOL ─────────
    major_minor = f"{installed_v[0]}.{installed_v[1]}"
    major_only = str(installed_v[0])

    eol_entry = (
        eol_versions.get(installed)
        or eol_versions.get(major_minor)
        or eol_versions.get(major_only)
    )

    if eol_entry:
        if isinstance(eol_entry, str):
            # Simple string EOL date
            eol_date = eol_entry
            cves: list[str] = []
        else:
            # Dict with eol + optional cves
            eol_date = eol_entry.get("eol", "")
            cves = eol_entry.get("cves", [])

        if cves:
            return RankLevel.DANGEROUS, f"EOL {eol_date}, {len(cves)} known CVE(s)"

        rank = rank_by_eol(eol_date)
        if rank.severity >= RankLevel.DEPRECATED.severity:
            return rank, f"EOL since {eol_date}"
        return rank, f"EOL {eol_date}"

    # ── Step 2: Compare against current version ─────────────────
    if current_v:
        if installed_v >= current_v:
            return RankLevel.CURRENT, "Up to date"

        scheme = lifecycle.get("version_scheme", "semver")

        if scheme == "semver_minor":
            # Treat the version as a release train where major bumps
            # are incremental (e.g. Docker 24→25→26→27, kubectl 1.29→1.30→1.31).
            # Compute a flat "releases behind" count.
            if installed_v[0] == current_v[0]:
                # Same major — count minor gap directly
                gap = current_v[1] - installed_v[1]
            else:
                # Different major — count only major gap.
                # For Docker (24.0 → 27.5), the gap is 3 (not 3+5=8).
                # Minor versions within a different major are irrelevant.
                gap = current_v[0] - installed_v[0]
            if gap <= 2:
                return RankLevel.AGING, f"{gap} release(s) behind"
            elif gap <= 4:
                return RankLevel.OUTDATED, f"{gap} releases behind"
            elif gap <= 8:
                return RankLevel.DEPRECATED, f"{gap} releases behind"
            else:
                return RankLevel.DANGEROUS, f"{gap} releases behind ({installed} → {current_str})"

        else:
            # Standard semver — major first, then minor
            if installed_v[0] < current_v[0]:
                major_diff = current_v[0] - installed_v[0]
                return (
                    RankLevel.DANGEROUS,
                    f"{major_diff} major version(s) behind ({installed} → {current_str})",
                )
            minor_diff = current_v[1] - installed_v[1]
            if minor_diff <= 2:
                return RankLevel.AGING, f"{minor_diff} minor version(s) behind"
            elif minor_diff <= 5:
                return RankLevel.OUTDATED, f"{minor_diff} minor versions behind"
            else:
                return RankLevel.DEPRECATED, f"{minor_diff} minor versions behind"

    # ── Step 3: Check minimum supported ─────────────────────────
    if min_supported_str:
        min_v = parse_semver(min_supported_str)
        if min_v and installed_v < min_v:
            return (
                RankLevel.DEPRECATED,
                f"Below minimum supported ({min_supported_str})",
            )

    return RankLevel.UNKNOWN, "No lifecycle data available"


# ── Aggregate helpers ───────────────────────────────────────────


def worst_rank(items: list[PostureItem]) -> RankLevel:
    """Return the worst (highest severity) rank from a list of items.

    Ignores items with rank NA or UNKNOWN — these don't affect
    the aggregate.  Returns UNKNOWN if no scoreable items exist.
    """
    scoreable = [
        item.rank for item in items
        if item.rank not in (RankLevel.NA, RankLevel.UNKNOWN)
    ]
    if not scoreable:
        return RankLevel.UNKNOWN
    return max(scoreable, key=lambda r: r.severity)
