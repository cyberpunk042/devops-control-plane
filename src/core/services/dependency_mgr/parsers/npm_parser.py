"""
npm output parser — extracts structured events from npm command output.

Handles both npm 6 (``npm WARN``/``npm ERR!``) and npm 7+
(``npm warn``/``npm error``) output formats via case-insensitive matching.

Patterns recognized:

1. ``added N packages in Xs``            → package_resolved (batch)
2. ``removed N packages in Xs``          → package_resolved (batch, action=removed)
3. ``changed N packages in Xs``          → package_resolved (batch, action=changed)
4. ``up to date in Xs``                  → progress
5. ``npm warn deprecated <pkg>: <msg>``  → warning (deprecated)
6. ``npm warn <pkg> requires a peer``    → warning (peer_dep)
7. ``npm warn optional SKIPPING``        → warning (optional_skip)
8. ``npm error code ERESOLVE``           → error (conflict)
9. ``npm error code ENOENT``             → error (missing_dep)
10. ``npm error ...``                    → error (generic)
"""

from __future__ import annotations

import re
from typing import Literal

from ..models import OpEvent
from .base import BaseOutputParser


# ── Compiled regexes ──────────────────────────────────────────

# "added 47 packages in 12.3s"  /  "added 47 packages, removed 2 packages in 4s"
_RE_ADDED = re.compile(r"^added\s+(\d+)\s+package", re.IGNORECASE)

# "removed 3 packages in 2s"
_RE_REMOVED = re.compile(r"^removed\s+(\d+)\s+package", re.IGNORECASE)

# "changed 5 packages in 3s"
_RE_CHANGED = re.compile(r"^changed\s+(\d+)\s+package", re.IGNORECASE)

# "up to date in 0.5s"  /  "up to date, audited 120 packages in 1s"
_RE_UP_TO_DATE = re.compile(r"^up to date", re.IGNORECASE)

# "npm warn deprecated inflight@1.0.6: This module is not supported"
# npm 6: "npm WARN deprecated inflight@1.0.6: ..."
_RE_DEPRECATED = re.compile(
    r"^npm\s+(?:WARN|warn)\s+deprecated\s+(\S+?):\s*(.+)", re.IGNORECASE,
)

# "npm warn <pkg> requires a peer of <dep>@<ver>"
_RE_PEER = re.compile(
    r"^npm\s+(?:WARN|warn)\s+(\S+)\s+requires\s+a\s+peer", re.IGNORECASE,
)

# "npm warn optional SKIPPING OPTIONAL DEPENDENCY: <pkg>"
_RE_OPTIONAL_SKIP = re.compile(
    r"^npm\s+(?:WARN|warn)\s+optional\s+SKIPPING", re.IGNORECASE,
)

# Any other "npm warn ..."
_RE_WARN = re.compile(r"^npm\s+(?:WARN|warn)\s+(.+)", re.IGNORECASE)

# "npm error code ERESOLVE"
_RE_ERESOLVE = re.compile(r"^npm\s+(?:ERR!|error)\s+code\s+ERESOLVE", re.IGNORECASE)

# "npm error code ENOENT"
_RE_ENOENT = re.compile(r"^npm\s+(?:ERR!|error)\s+code\s+ENOENT", re.IGNORECASE)

# Any "npm error ..." / "npm ERR! ..."
_RE_ERR = re.compile(r"^npm\s+(?:ERR!|error)\s+(.+)", re.IGNORECASE)


class NpmParser(BaseOutputParser):
    """Parser for npm install/update command output."""

    def __init__(self, scope: str) -> None:
        super().__init__(scope, "npm")
        self._batch_count = 0

    def _match_line(
        self, line: str, stream: Literal["stdout", "stderr", "merged"],
    ) -> list[OpEvent]:
        stripped = line.strip()
        if not stripped:
            return []

        # 1. added N packages
        m = _RE_ADDED.match(stripped)
        if m:
            count = int(m.group(1))
            self._batch_count += count
            return [self._make_event(
                "package_resolved",
                message=stripped,
                count=count,
                action="installed",
            )]

        # 2. removed N packages
        m = _RE_REMOVED.match(stripped)
        if m:
            return [self._make_event(
                "package_resolved",
                message=stripped,
                count=int(m.group(1)),
                action="removed",
            )]

        # 3. changed N packages
        m = _RE_CHANGED.match(stripped)
        if m:
            count = int(m.group(1))
            self._batch_count += count
            return [self._make_event(
                "package_resolved",
                message=stripped,
                count=count,
                action="changed",
            )]

        # 4. up to date
        if _RE_UP_TO_DATE.match(stripped):
            return [self._progress_event(stripped)]

        # 5. npm warn deprecated <pkg>@<ver>: <msg>
        m = _RE_DEPRECATED.match(stripped)
        if m:
            pkg_ver = m.group(1)  # "inflight@1.0.6"
            msg = m.group(2)
            pkg = pkg_ver.split("@")[0] if "@" in pkg_ver else pkg_ver
            return [self._warning_event(
                f"{pkg_ver}: {msg}", category="deprecated", package=pkg,
            )]

        # 6. peer dependency warning
        m = _RE_PEER.match(stripped)
        if m:
            return [self._warning_event(stripped, category="peer_dep", package=m.group(1))]

        # 7. optional skip
        if _RE_OPTIONAL_SKIP.match(stripped):
            return [self._warning_event(stripped, category="optional_skip")]

        # 8. ERESOLVE (version conflict)
        if _RE_ERESOLVE.match(stripped):
            return [self._error_event(stripped, category="conflict")]

        # 9. ENOENT (file not found)
        if _RE_ENOENT.match(stripped):
            return [self._error_event(stripped, category="missing_dep")]

        # 10. Any other npm error
        m = _RE_ERR.match(stripped)
        if m:
            return [self._error_event(stripped, category="generic")]

        # 11. Any other npm warn (catch-all after specific patterns)
        m = _RE_WARN.match(stripped)
        if m:
            return [self._warning_event(stripped, category="generic")]

        return []

    @property
    def resolved_count(self) -> int:
        """For npm, use batch count since we get summary lines, not per-package."""
        return self._batch_count if self._batch_count > 0 else len(self._resolved)
