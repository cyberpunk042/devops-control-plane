"""
Output parser — protocol and base implementation.

Each ecosystem has its own parser that receives raw stdout/stderr
lines during command execution and emits structured ``OpEvent``s.

Subclasses override ``_match_line()`` for ecosystem-specific patterns.
The base class handles generic fallback detection (ERROR, WARNING, FAIL)
and accumulates resolved/warning/error counts.

Usage::

    parser = adapter.create_output_parser(scope="pip:.")
    for line in subprocess_output:
        events = parser.feed_line(line)
        for ev in events:
            yield ev
    final_events = parser.finalize(exit_code=0)
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Literal

from ..models import OpEvent


# ═════════════════════════════════════════════════════════════════
#  Protocol
# ═════════════════════════════════════════════════════════════════


class OutputParser(ABC):
    """Abstract base for ecosystem output parsers.

    One instance per operation.  Stateful — accumulates results
    as lines are fed in.

    Subclasses must implement ``_match_line()``.
    Optionally override ``_finalize()`` for ecosystem-specific
    summary logic (e.g. npm reports total count only at the end).
    """

    @abstractmethod
    def feed_line(
        self, line: str, stream: Literal["stdout", "stderr", "merged"] = "merged",
    ) -> list[OpEvent]:
        """Process one output line.  Return zero or more parsed events.

        Most lines produce nothing (raw log only).  Pattern matches
        produce ``package_resolved``, ``warning``, ``error``, or
        ``progress`` events.
        """

    @abstractmethod
    def finalize(self, exit_code: int) -> list[OpEvent]:
        """Called after subprocess exits.  Emit final summary events.

        Use this for parsers that accumulate state (e.g. npm reports
        total added count only at the end).
        """

    @property
    @abstractmethod
    def resolved_count(self) -> int:
        """Number of packages resolved so far."""

    @property
    @abstractmethod
    def warnings(self) -> list[OpEvent]:
        """All warning events emitted so far."""

    @property
    @abstractmethod
    def errors(self) -> list[OpEvent]:
        """All error events emitted so far."""


# ═════════════════════════════════════════════════════════════════
#  Base implementation
# ═════════════════════════════════════════════════════════════════


class BaseOutputParser(OutputParser):
    """Shared logic for all ecosystem parsers.

    Subclasses override:
    - ``_match_line()`` — ecosystem-specific pattern matching
    - ``_finalize()`` (optional) — ecosystem-specific summary

    Base class handles:
    - Event construction with timestamps and scope
    - Warning/error/resolved accumulation
    - Generic fallback patterns (ERROR, WARNING, FAIL in any output)
    """

    def __init__(self, scope: str, ecosystem: str) -> None:
        self._scope = scope
        self._ecosystem = ecosystem
        self._resolved: list[OpEvent] = []
        self._warnings: list[OpEvent] = []
        self._errors: list[OpEvent] = []

    # ── Public API ────────────────────────────────────────────

    def feed_line(
        self, line: str, stream: Literal["stdout", "stderr", "merged"] = "merged",
    ) -> list[OpEvent]:
        """Feed one output line.  Returns parsed events (may be empty)."""
        # Try ecosystem-specific patterns first
        events = self._match_line(line, stream)
        # Fall back to generic pattern detection
        if not events:
            events = self._match_generic(line, stream)
        # Accumulate by type
        for ev in events:
            if ev.type == "package_resolved":
                self._resolved.append(ev)
            elif ev.type == "warning":
                self._warnings.append(ev)
            elif ev.type == "error":
                self._errors.append(ev)
        return events

    def finalize(self, exit_code: int) -> list[OpEvent]:
        """Called after subprocess exits.  Override ``_finalize()`` in subclass."""
        return self._finalize(exit_code)

    @property
    def resolved_count(self) -> int:
        return len(self._resolved)

    @property
    def warnings(self) -> list[OpEvent]:
        return list(self._warnings)

    @property
    def errors(self) -> list[OpEvent]:
        return list(self._errors)

    # ── Subclass hooks ────────────────────────────────────────

    def _match_line(
        self, line: str, stream: Literal["stdout", "stderr", "merged"],
    ) -> list[OpEvent]:
        """Override in subclass.  Return empty list for unrecognized lines."""
        return []

    def _finalize(self, exit_code: int) -> list[OpEvent]:
        """Override in subclass.  Called once after subprocess exits."""
        return []

    # ── Generic fallback ──────────────────────────────────────

    def _match_generic(
        self, line: str, stream: Literal["stdout", "stderr", "merged"],
    ) -> list[OpEvent]:
        """Detect ERROR/WARNING/DEPRECATED in any ecosystem output.

        Only fires when the subclass ``_match_line()`` returned nothing.
        Avoids false positives by requiring specific keywords.
        """
        stripped = line.strip()
        if not stripped:
            return []

        upper = stripped.upper()

        # Error patterns
        if any(kw in upper for kw in ("ERROR:", "FATAL:", "FAILED:", "EXCEPTION:")):
            return [self._make_event(
                "error",
                message=stripped,
                severity="error",
                category="generic",
            )]

        # Warning / deprecation patterns
        if any(kw in upper for kw in ("WARNING:", "WARN ", "DEPRECATED")):
            return [self._make_event(
                "warning",
                message=stripped,
                severity="warning",
                category="deprecated" if "DEPRECATED" in upper else "generic",
            )]

        return []

    # ── Event construction helpers ────────────────────────────

    def _make_event(self, event_type: str, **kwargs: str | int | dict) -> OpEvent:
        """Construct an OpEvent with scope and timestamp pre-filled."""
        return OpEvent(
            type=event_type,
            ts=time.time(),
            scope=self._scope,
            **kwargs,  # type: ignore[arg-type]
        )

    def _resolved_event(
        self, package: str, version: str, action: str = "installed",
    ) -> OpEvent:
        """Shorthand for a ``package_resolved`` event."""
        return self._make_event(
            "package_resolved",
            package=package,
            version=version,
            action=action,
        )

    def _warning_event(
        self, message: str, *, category: str = "", package: str = "",
    ) -> OpEvent:
        """Shorthand for a ``warning`` event."""
        return self._make_event(
            "warning",
            message=message,
            severity="warning",
            category=category,
            package=package,
        )

    def _error_event(
        self, message: str, *, category: str = "", package: str = "",
    ) -> OpEvent:
        """Shorthand for an ``error`` event."""
        return self._make_event(
            "error",
            message=message,
            severity="error",
            category=category,
            package=package,
        )

    def _progress_event(self, message: str) -> OpEvent:
        """Shorthand for a ``progress`` event."""
        return self._make_event("progress", message=message)
