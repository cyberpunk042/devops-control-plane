"""
Go output parser — extracts structured events from go mod commands.

Go output is clean and predictable:

1. ``go: downloading github.com/foo/bar v1.2.3``  → package_resolved
2. ``go: added github.com/foo/bar v1.2.3``        → package_resolved
3. ``go: upgraded github.com/foo/bar v1.2.3``      → package_resolved (action=updated)
4. ``go: finding module for package X``             → progress
5. ``go: found X in Y``                            → progress
6. ``go: module X: not found``                     → error (missing_dep)
7. ``go: X@v1: requires go >= 1.22``               → warning (compat)
8. ``verifying X: checksum mismatch``              → error (checksum)
"""

from __future__ import annotations

import re
from typing import Literal

from ..models import OpEvent
from .base import BaseOutputParser

_RE_DOWNLOADING = re.compile(r"^go:\s+downloading\s+(\S+)\s+(\S+)")
_RE_ADDED = re.compile(r"^go:\s+added\s+(\S+)\s+(\S+)")
_RE_UPGRADED = re.compile(r"^go:\s+upgraded\s+(\S+)\s+\S+\s*=>\s*(\S+)")
_RE_FINDING = re.compile(r"^go:\s+finding\s+", re.IGNORECASE)
_RE_FOUND = re.compile(r"^go:\s+found\s+", re.IGNORECASE)
_RE_NOT_FOUND = re.compile(r"^go:\s+(\S+).*not found", re.IGNORECASE)
_RE_REQUIRES_GO = re.compile(r"^go:\s+.*requires\s+go\s+>=", re.IGNORECASE)
_RE_CHECKSUM = re.compile(r"checksum\s+mismatch", re.IGNORECASE)


class GoParser(BaseOutputParser):
    """Parser for go mod download/get command output."""

    def __init__(self, scope: str) -> None:
        super().__init__(scope, "go")

    def _match_line(
        self, line: str, stream: Literal["stdout", "stderr", "merged"],
    ) -> list[OpEvent]:
        stripped = line.strip()
        if not stripped:
            return []

        m = _RE_DOWNLOADING.match(stripped)
        if m:
            return [self._resolved_event(m.group(1), m.group(2), action="installed")]

        m = _RE_ADDED.match(stripped)
        if m:
            return [self._resolved_event(m.group(1), m.group(2), action="installed")]

        m = _RE_UPGRADED.match(stripped)
        if m:
            return [self._resolved_event(m.group(1), m.group(2), action="updated")]

        if _RE_FINDING.match(stripped) or _RE_FOUND.match(stripped):
            return [self._progress_event(stripped)]

        m = _RE_NOT_FOUND.match(stripped)
        if m:
            return [self._error_event(stripped, category="missing_dep", package=m.group(1))]

        if _RE_REQUIRES_GO.match(stripped):
            return [self._warning_event(stripped, category="compat")]

        if _RE_CHECKSUM.search(stripped):
            return [self._error_event(stripped, category="checksum")]

        return []
