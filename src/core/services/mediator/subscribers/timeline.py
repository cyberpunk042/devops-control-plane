"""
Timeline bus transformer subscriber.

Subscribes to mediator ``"computed"`` events for ``timeline.source.*`` nodes.
For each new source computation, normalizes the result into ``TimelineEntry``
objects and publishes ``timeline:entry`` events to the event bus.

The frontend SSE handler listens for ``timeline:entry`` and prepends new
entries to the live list with an 800ms batch buffer.

Pattern follows: eventbus_bridge.py (mediator → bus) and activity.py (filters).
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.services.mediator.core import QueryMediator

logger = logging.getLogger(__name__)

# Only react to source node computations — view/feed nodes aggregate from these
_SOURCE_PREFIX = "timeline.source."


def _on_computed(event: dict[str, Any]) -> None:
    """Forward new timeline source entries to the event bus.

    Fires on every ``"computed"`` event.  Filters to ``timeline.source.*``
    paths only — view/feed node computations are not forwarded directly
    (the frontend fetches those via REST when it needs them).

    Each entry in the resolver result is published individually so the
    frontend can process them one-by-one with its batch buffer.
    """
    if event.get("type") != "computed":
        return

    paths = event.get("paths", [])
    if not paths or not paths[0].startswith(_SOURCE_PREFIX):
        return

    meta = event.get("compute_meta")
    if meta is None:
        return

    data = meta.get("data")
    if not isinstance(data, list) or not data:
        return

    try:
        from src.core.services.event_bus import bus
    except Exception:
        return  # EventBus not available (e.g. during tests)

    try:
        from src.core.services.timeline.models import TimelineEntry
    except Exception as exc:
        logger.warning("timeline subscriber: cannot import TimelineEntry: %s", exc)
        return

    path = paths[0]

    for item in data:
        if not isinstance(item, TimelineEntry):
            continue
        try:
            bus.publish(
                "timeline:entry",
                key=path,
                data=item.to_dict(),
            )
        except Exception as exc:
            logger.warning(
                "timeline subscriber: failed to publish entry %s: %s",
                item.id, exc,
            )


def register_timeline_subscriber(mediator: QueryMediator) -> str:
    """Register the timeline bus transformer on the mediator.

    Subscribes to ``timeline.source.*`` paths.  Returns the subscription ID.
    Called from ``register_all()`` after all domain nodes are registered.
    """
    sub_id = mediator.subscribe("timeline.source.*", _on_computed)
    logger.info(
        "mediator: timeline subscriber registered (sub_id=%s)", sub_id,
    )
    return sub_id
