"""
Cargo output parser — extracts structured events from cargo commands.

Cargo writes progress to stderr (compilation lines). Our subprocess
merges stderr by default, so all lines come through.

Patterns:

1. ``Downloading crates...``                     → progress
2. ``Downloaded serde v1.0.200``                 → package_resolved
3. ``Compiling serde v1.0.200``                  → package_resolved (action=compiled)
4. ``Updating crates.io index``                  → progress
5. ``warning: ...``                              → warning
6. ``error[E0433]: ...``                         → error (compile)
7. ``error: could not compile``                  → error (build_error)
"""

from __future__ import annotations

import re
from typing import Literal

from ..models import OpEvent
from .base import BaseOutputParser

_RE_DOWNLOADED = re.compile(r"^\s*Downloaded\s+(\S+)\s+v(\S+)")
_RE_COMPILING = re.compile(r"^\s*Compiling\s+(\S+)\s+v(\S+)")
_RE_UPDATING = re.compile(r"^\s*Updating\s+", re.IGNORECASE)
_RE_DOWNLOADING = re.compile(r"^\s*Downloading\s+", re.IGNORECASE)
_RE_WARNING = re.compile(r"^\s*warning(?:\[.*?\])?:\s*(.+)", re.IGNORECASE)
_RE_ERROR_CODE = re.compile(r"^\s*error\[E\d+\]:\s*(.+)")
_RE_COULD_NOT = re.compile(r"^\s*error:\s*could not compile", re.IGNORECASE)
_RE_ERROR = re.compile(r"^\s*error:\s*(.+)", re.IGNORECASE)


class CargoParser(BaseOutputParser):
    """Parser for cargo fetch/update/build command output."""

    def __init__(self, scope: str) -> None:
        super().__init__(scope, "cargo")

    def _match_line(
        self, line: str, stream: Literal["stdout", "stderr", "merged"],
    ) -> list[OpEvent]:
        stripped = line.strip()
        if not stripped:
            return []

        m = _RE_DOWNLOADED.match(stripped)
        if m:
            return [self._resolved_event(m.group(1), m.group(2), action="installed")]

        m = _RE_COMPILING.match(stripped)
        if m:
            return [self._resolved_event(m.group(1), m.group(2), action="compiled")]

        if _RE_UPDATING.match(stripped) or _RE_DOWNLOADING.match(stripped):
            return [self._progress_event(stripped)]

        # Cargo warnings (before errors — warnings are more common)
        m = _RE_WARNING.match(stripped)
        if m:
            return [self._warning_event(m.group(1), category="generic")]

        # error[E0433]: ...
        m = _RE_ERROR_CODE.match(stripped)
        if m:
            return [self._error_event(stripped, category="compile")]

        # error: could not compile
        if _RE_COULD_NOT.match(stripped):
            return [self._error_event(stripped, category="build_error")]

        # Any other error: line
        m = _RE_ERROR.match(stripped)
        if m:
            return [self._error_event(stripped, category="generic")]

        return []
