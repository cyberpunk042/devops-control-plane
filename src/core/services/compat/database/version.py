"""Version parsing and comparison — per-language.

Each language has its own version format:
  Python: "3.8", "3.11"    → (3, 8), (3, 11)
  JS:     "ES2020"          → (2020,) or Node "18" → (18,)
  Go:     "1.21"            → (1, 21)
  Rust:   "1.75.0"          → (1, 75, 0)
  Java:   "17"              → (17,)
  Ruby:   "3.2"             → (3, 2)
  C#:     "12"              → (12,)
  PHP:    "8.2"             → (8, 2)
  Elixir: "1.15"            → (1, 15)
"""

from __future__ import annotations

import re


def parse_version(language: str, version_str: str) -> tuple[int, ...] | None:
    """Parse a version string into a comparable tuple.

    Returns None if the version can't be parsed.
    """
    if not version_str:
        return None

    version_str = version_str.strip()

    # JavaScript ES year format: "ES2020" → (2020,)
    if language in ("javascript", "typescript"):
        es_match = re.match(r"^ES(\d{4})$", version_str, re.IGNORECASE)
        if es_match:
            return (int(es_match.group(1)),)
        # Node.js version: "18" or "18.17"
        return _parse_dotted(version_str)

    # Rust edition: "edition_2021" or "edition2021" → (2021,)
    if language == "rust":
        ed_match = re.match(r"^edition[_]?(\d{4})$", version_str, re.IGNORECASE)
        if ed_match:
            return (int(ed_match.group(1)),)
        return _parse_dotted(version_str)

    # All others: dotted numeric "3.8", "1.21", "17", "8.2"
    return _parse_dotted(version_str)


def _parse_dotted(version_str: str) -> tuple[int, ...] | None:
    """Parse a dotted version string: "3.8" → (3, 8), "17" → (17,)."""
    parts = version_str.split(".")
    try:
        return tuple(int(p) for p in parts)
    except (ValueError, TypeError):
        return None


def version_above(language: str, version: str, target: str) -> bool:
    """Is `version` strictly above `target`?

    Returns False if either can't be parsed.
    """
    v = parse_version(language, version)
    t = parse_version(language, target)
    if v is None or t is None:
        return False
    return v > t


def version_at_or_above(language: str, version: str, target: str) -> bool:
    """Is `version` at or above `target`?"""
    v = parse_version(language, version)
    t = parse_version(language, target)
    if v is None or t is None:
        return False
    return v >= t


def version_below(language: str, version: str, target: str) -> bool:
    """Is `version` strictly below `target`?"""
    v = parse_version(language, version)
    t = parse_version(language, target)
    if v is None or t is None:
        return False
    return v < t


def version_compare(language: str, a: str, b: str) -> int:
    """Compare two versions. Returns -1, 0, or 1."""
    va = parse_version(language, a)
    vb = parse_version(language, b)
    if va is None or vb is None:
        return 0
    if va < vb:
        return -1
    if va > vb:
        return 1
    return 0
