"""
Trace models — data shapes for session traces and trace events.

Pure Pydantic models with no I/O.
"""

from __future__ import annotations

import secrets
import string
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _make_trace_id() -> str:
    """Generate a unique trace ID: trace_<timestamp>_<4char>."""
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    return f"trace_{ts}_{suffix}"


class TraceEvent(BaseModel):
    """A single event within a session trace.

    Captured from the event bus during recording.
    """

    seq: int = 0
    ts: str = ""
    type: str = ""                                 # event bus type (e.g. "cache:done")
    key: str = ""                                  # resource identifier
    target: str = ""                               # what was acted on
    result: str = ""                               # ok, failed, skipped
    duration_ms: int = 0
    detail: dict[str, Any] = Field(default_factory=dict)


class SessionTrace(BaseModel):
    """A recorded session.

    Storage:
      - Local (unshared):  .state/traces/<trace_id>/ (trace.json + events.jsonl)
      - Shared (git):      .ledger/traces/<trace_id>/ (committed)
    """

    trace_id: str = ""
    name: str = ""
    classification: str = ""                       # deployment, debugging, config, exploration
    started_at: str = Field(default_factory=_now_iso)
    ended_at: str = ""
    user: str = ""
    code_ref: str = ""                             # HEAD at recording start
    events: list[TraceEvent] = Field(default_factory=list)
    auto_summary: str = ""
    audit_refs: list[str] = Field(default_factory=list)  # linked audit operation_ids
    event_count: int = 0
    duration_s: float = 0.0
    shared: bool = False                             # True = committed to git

    def ensure_id(self) -> str:
        """Ensure trace_id is set, generating one if empty."""
        if not self.trace_id:
            self.trace_id = _make_trace_id()
        return self.trace_id
