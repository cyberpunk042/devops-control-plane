"""
Shared event emission utility.

Single entry point for emitting events from background threads
and streaming operations that can't use the @tracked decorator.

Usage::

    from src.core.services.events.emit import emit_event

    emit_event(
        "pages.build.completed",
        summary="Build complete: docs — 3 stages (5400ms)",
        correlation_id="pages-build:abc123",
        status="ok",
        duration_ms=5400,
        detail={"segment": "docs", "stages": 3},
    )

For Flask route handlers, use @tracked instead — it handles
request context, response parsing, and correlation automatically.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def emit_event(
    event_type: str,
    *,
    summary: str,
    correlation_id: str = "",
    status: str = "ok",
    duration_ms: int = 0,
    detail: dict[str, Any] | None = None,
    origin: str = "user",
    actor: str = "user",
    invalidate_timeline: bool = True,
) -> None:
    """Emit an event to the event store. Fail-safe — never raises.

    Args:
        event_type: Dotted event type (e.g. ``"plan.completed"``).
        summary: Human-readable one-line summary for the timeline.
        correlation_id: Chain ID linking related events.
        status: ``"ok"`` or ``"error"``.
        duration_ms: How long the operation took.
        detail: Structured metadata dict.
        origin: ``"user"`` or ``"system"``.
        actor: ``"user"``, ``"automation"``, or ``"scheduler"``.
        invalidate_timeline: If True, invalidate timeline.data so
            the next access recomputes it with the new event.
    """
    try:
        from src.core.services.mediator import get_mediator
        from src.core.services.events.models import Event

        m = get_mediator()
        if not m or not getattr(m, "_event_store", None):
            return

        m._event_store.append(Event(
            id="",
            ts=time.time(),
            type=event_type,
            correlation_id=correlation_id,
            source="route",
            path=event_type,
            status=status,
            duration_ms=duration_ms,
            summary=summary,
            detail=detail or {},
            origin=origin,
            actor=actor,
        ))

        if invalidate_timeline:
            try:
                m.invalidate("timeline.data")
            except Exception:
                pass

    except Exception:
        logger.debug("emit_event failed for %s", event_type, exc_info=True)
