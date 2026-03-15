"""
EventBus compatibility bridge for the mediator.

Bridges mediator ``"computed"`` events to legacy ``cache:done``
and ``cache:error`` events that the frontend SSE stream consumes.

The frontend's ``_event_stream.html`` listens for:
- ``cache:done``  → updates the SSE state store, refreshes cards
- ``cache:error`` → clears loading spinners, shows error state
- ``cache:miss``  → sets loading spinners  (only from get_cached)
- ``cache:bust``  → clears state store     (only from invalidate)

This bridge handles ``cache:done`` and ``cache:error`` — the two
events that come from successful/failed computation.  ``cache:miss``
and ``cache:bust`` are still emitted by ``get_cached()`` and
``invalidate()`` during the transition; once those are removed
(Chunks 8-10), equivalent events will be added here.

This is Chunk 4 of the mediator v2 infrastructure plan.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.services.mediator.core import QueryMediator

logger = logging.getLogger(__name__)


def _on_computed(event: dict[str, Any]) -> None:
    """Bridge mediator computed events to legacy cache:* EventBus events.

    Fires on every ``"computed"`` event from ``get()``.  Translates to:
    - ``cache:done`` when the resolver returned valid data
    - ``cache:error`` when the data contains an ``error`` key
    """
    if event.get("type") != "computed":
        return

    meta = event.get("compute_meta")
    if meta is None:
        return

    paths = event.get("paths", [])
    if not paths:
        return

    path = paths[0]
    card_key = _path_to_card_key(path)
    data = meta.get("data", {})
    elapsed_s = meta.get("elapsed_s", 0.0)

    try:
        from src.core.services.event_bus import bus
    except Exception:
        return  # EventBus not available

    if isinstance(data, dict) and "error" in data and isinstance(data["error"], str):
        bus.publish(
            "cache:error",
            key=card_key,
            error=str(data.get("error", ""))[:200],
            duration_s=elapsed_s,
        )
    else:
        bus.publish(
            "cache:done",
            key=card_key,
            data=data if isinstance(data, dict) else {},
            duration_s=elapsed_s,
        )


def _path_to_card_key(path: str) -> str:
    """Convert mediator path to legacy card key.

    Delegates to the activity subscriber's mapping (single source
    of truth for path↔key conversion).
    """
    from src.core.services.mediator.subscribers.activity import (
        _path_to_card_key as _convert,
    )
    return _convert(path)


def register_eventbus_bridge(mediator: QueryMediator) -> str:
    """Register the EventBus compatibility bridge on the mediator.

    Subscribes to all paths (``"*"``) and filters in the callback
    to only process ``"computed"`` events.

    Returns the subscription ID.
    """
    sub_id = mediator.subscribe("*", _on_computed)
    logger.info(
        "mediator: EventBus bridge registered (sub_id=%s)", sub_id,
    )
    return sub_id
