"""
pip output parser — extracts structured events from pip command output.

Patterns recognized (in matching priority order):

1. ``Successfully installed flask-3.0.1 requests-2.31.0``
   → ``package_resolved`` × N
2. ``Requirement already satisfied: flask>=3.0 in /path``
   → ``package_resolved`` (action=satisfied)
3. ``Collecting flask>=3.0``
   → ``progress``
4. ``Downloading`` / ``Using cached``
   → ``progress``
5. ``DEPRECATION: ...``
   → ``warning`` (deprecated)
6. ``WARNING: ...``
   → ``warning`` (generic)
7. ``ERROR: No matching distribution found for X``
   → ``error`` (missing_dep)
8. ``ERROR: Could not find a version that satisfies``
   → ``error`` (conflict)
9. ``error: subprocess-exited-with-error``
   → ``error`` (build_error)
10. ``pip's dependency resolver does not currently take into account``
    → ``warning`` (conflict)

The "Successfully installed" line is the most important — it lists
every package that was actually installed with exact versions.
"""

from __future__ import annotations

import re
from typing import Literal

from ..models import OpEvent
from .base import BaseOutputParser


# ── Compiled regexes ──────────────────────────────────────────

# "Successfully installed flask-3.0.1 requests-2.31.0 ..."
_RE_INSTALLED = re.compile(r"^Successfully installed (.+)$", re.IGNORECASE)

# "Requirement already satisfied: flask>=3.0 in /usr/lib/..."
_RE_SATISFIED = re.compile(
    r"^Requirement already satisfied:\s+([a-zA-Z0-9_.-]+)", re.IGNORECASE,
)

# "Collecting flask>=3.0 (from -r requirements.txt ...)"
_RE_COLLECTING = re.compile(
    r"^Collecting\s+([a-zA-Z0-9_.\[\]-]+)", re.IGNORECASE,
)

# "  Downloading flask-3.0.1-py3-none-any.whl (100 kB)"
_RE_DOWNLOADING = re.compile(r"^\s+Downloading\s+", re.IGNORECASE)

# "  Using cached flask-3.0.1-py3-none-any.whl"
_RE_CACHED = re.compile(r"^\s+Using cached\s+", re.IGNORECASE)

# "DEPRECATION: ..."
_RE_DEPRECATION = re.compile(r"^DEPRECATION:\s*(.+)", re.IGNORECASE)

# "WARNING: ..."
_RE_WARNING = re.compile(r"^WARNING:\s*(.+)", re.IGNORECASE)

# "ERROR: No matching distribution found for X"
_RE_NO_MATCH = re.compile(
    r"^ERROR:\s*No matching distribution found for\s+(\S+)", re.IGNORECASE,
)

# "ERROR: Could not find a version that satisfies the requirement X"
_RE_NO_VERSION = re.compile(
    r"^ERROR:\s*Could not find a version that satisfies.*?(\S+)\s*$", re.IGNORECASE,
)

# "error: subprocess-exited-with-error"
_RE_BUILD_ERROR = re.compile(r"subprocess-exited-with-error", re.IGNORECASE)

# "pip's dependency resolver does not currently take into account"
_RE_RESOLVER_WARN = re.compile(r"dependency resolver", re.IGNORECASE)


class PipParser(BaseOutputParser):
    """Parser for pip install/update/rollback command output."""

    def __init__(self, scope: str) -> None:
        super().__init__(scope, "pip")

    def _match_line(
        self, line: str, stream: Literal["stdout", "stderr", "merged"],
    ) -> list[OpEvent]:
        stripped = line.strip()
        if not stripped:
            return []

        # 1. Successfully installed (highest priority — the actual result)
        m = _RE_INSTALLED.match(stripped)
        if m:
            return self._parse_installed_line(m.group(1))

        # 2. Requirement already satisfied
        m = _RE_SATISFIED.match(stripped)
        if m:
            return [self._resolved_event(m.group(1), "", action="satisfied")]

        # 3. Collecting
        m = _RE_COLLECTING.match(stripped)
        if m:
            return [self._progress_event(f"Collecting {m.group(1)}")]

        # 4. Downloading
        if _RE_DOWNLOADING.match(stripped):
            return [self._progress_event(stripped.strip())]

        # 5. Using cached
        if _RE_CACHED.match(stripped):
            return [self._progress_event(stripped.strip())]

        # 6. DEPRECATION
        m = _RE_DEPRECATION.match(stripped)
        if m:
            return [self._warning_event(m.group(1), category="deprecated")]

        # 7. WARNING
        m = _RE_WARNING.match(stripped)
        if m:
            msg = m.group(1)
            # Dependency resolver warning is a specific category
            if _RE_RESOLVER_WARN.search(msg):
                return [self._warning_event(msg, category="conflict")]
            return [self._warning_event(msg, category="generic")]

        # 8. No matching distribution
        m = _RE_NO_MATCH.match(stripped)
        if m:
            return [self._error_event(
                stripped, category="missing_dep", package=m.group(1),
            )]

        # 9. No version satisfies
        m = _RE_NO_VERSION.match(stripped)
        if m:
            return [self._error_event(
                stripped, category="conflict", package=m.group(1),
            )]

        # 10. Build error
        if _RE_BUILD_ERROR.search(stripped):
            return [self._error_event(stripped, category="build_error")]

        # No match — let generic fallback in base class handle it
        return []

    def _parse_installed_line(self, packages_str: str) -> list[OpEvent]:
        """Parse the ``Successfully installed X-1.0 Y-2.0 ...`` payload.

        Each token is ``package_name-version``.  The split point is the
        last hyphen before a digit: ``python-dotenv-1.0.0`` → name=``python-dotenv``, ver=``1.0.0``.
        """
        events: list[OpEvent] = []
        for token in packages_str.split():
            name, version = _split_package_version(token)
            if name:
                events.append(self._resolved_event(name, version, action="installed"))
        return events


def _split_package_version(token: str) -> tuple[str, str]:
    """Split ``name-version`` token from pip's installed line.

    The version starts at the last hyphen followed by a digit.
    Examples::

        flask-3.0.1           → ("flask", "3.0.1")
        python-dotenv-1.0.0   → ("python-dotenv", "1.0.0")
        Jinja2-3.1.3          → ("Jinja2", "3.1.3")
        MarkupSafe-2.1.5      → ("MarkupSafe", "2.1.5")
    """
    # Walk backwards to find the last '-' followed by a digit
    for i in range(len(token) - 1, 0, -1):
        if token[i] == "-" and i + 1 < len(token) and token[i + 1].isdigit():
            return token[:i], token[i + 1:]
    # No version found — return the whole thing as name
    return token, ""
