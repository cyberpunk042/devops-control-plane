"""
Event model — immutable record of something that happened.

Every operation in the system produces an Event. Events are appended
to the EventStore and never modified or deleted.

The event type is a dotted string. The prefix IS the domain:
    "vault.unlocked"       → domain: vault
    "mediator.computed"    → domain: mediator
    "index.cycle.started"  → domain: index

Correlation IDs group related events into chains:
    All events in an index cycle share correlation_id = "cycle:{ts}"
    All events in a vault session share correlation_id = "vault-session:{ts}"
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Event:
    """Immutable record of an operation."""

    id: str                          # monotonic: "evt-{seq}"
    ts: float                        # when it happened (time.time())
    type: str                        # dotted string: "mediator.computed", "vault.unlocked"
    correlation_id: str              # groups related events (the chain)
    causation_id: str | None = None  # parent event ID that caused this one
    source: str = ""                 # who emitted: "mediator", "route", "watcher", "cli"
    path: str = ""                   # what was affected: mediator path, route path
    status: str = "ok"               # "ok", "error", "warning"
    duration_ms: int = 0             # how long it took
    summary: str = ""                # human-readable one-liner
    detail: dict[str, Any] = field(default_factory=dict)  # event-specific payload
    origin: str = "system"           # "system" or "user"
    actor: str = "scheduler"         # "scheduler", "user", "automation"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict."""
        return {
            "id": self.id,
            "ts": self.ts,
            "type": self.type,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "source": self.source,
            "path": self.path,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "summary": self.summary,
            "detail": self.detail,
            "origin": self.origin,
            "actor": self.actor,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Event:
        """Deserialize from dict."""
        return cls(
            id=d["id"],
            ts=d["ts"],
            type=d["type"],
            correlation_id=d.get("correlation_id", ""),
            causation_id=d.get("causation_id"),
            source=d.get("source", ""),
            path=d.get("path", ""),
            status=d.get("status", "ok"),
            duration_ms=d.get("duration_ms", 0),
            summary=d.get("summary", ""),
            detail=d.get("detail", {}),
            origin=d.get("origin", "system"),
            actor=d.get("actor", "scheduler"),
        )
