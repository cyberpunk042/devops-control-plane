"""
Calendar projection — groups events by date.

Produces per-day counts with failure flags for the calendar view.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.core.services.events.store import EventStore
from src.core.services.events.projections.timeline import _should_suppress


class CalendarProjection:
    """Builds day-by-day counts from event store."""

    def __init__(self, store: EventStore) -> None:
        self._store = store

    def build(self) -> list[dict[str, Any]]:
        """Build calendar entries from events."""
        events = self._store.all_events()

        days: dict[str, dict] = {}

        for event in events:
            if _should_suppress(event):
                continue

            day = datetime.fromtimestamp(event.ts, tz=UTC).strftime("%Y-%m-%d")
            if day not in days:
                days[day] = {"date": day, "count": 0, "has_failure": False}

            days[day]["count"] += 1
            if event.status in ("error", "failed"):
                days[day]["has_failure"] = True

        result = sorted(days.values(), key=lambda d: d["date"], reverse=True)
        return result
