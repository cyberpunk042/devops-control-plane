"""
Domain projection — builds by_adapter facets from events.

Groups events by domain → subtype → count.
Also produces by_source, by_status, by_severity facets.
"""

from __future__ import annotations

from typing import Any

from src.core.services.events.store import EventStore
from src.core.services.events.projections.timeline import (
    _should_suppress,
    _derive_source,
    _derive_subtype,
    _derive_domain,
    _map_status,
)
from src.core.services.timeline.models import Severity, EntryStatus, Source


class DomainProjection:
    """Builds facet counts from event store."""

    def __init__(self, store: EventStore) -> None:
        self._store = store

    def build(self) -> dict[str, Any]:
        """Build all facets from events."""
        events = self._store.all_events()

        by_source: dict[str, int] = {}
        by_status: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        by_adapter: dict[str, dict[str, int]] = {}

        for event in events:
            if _should_suppress(event):
                continue

            source = _derive_source(event)
            subtype = _derive_subtype(event)
            domain = _derive_domain(event)
            status = _map_status(event.status)

            src_val = source.value
            by_source[src_val] = by_source.get(src_val, 0) + 1
            by_status[status.value] = by_status.get(status.value, 0) + 1

            sev_key = "none"
            if status == EntryStatus.FAILED:
                sev_key = "medium"
                if source in (Source.SECURITY, Source.AUDIT):
                    sev_key = "high"
            by_severity[sev_key] = by_severity.get(sev_key, 0) + 1

            # Domain → subtype
            if domain not in by_adapter:
                by_adapter[domain] = {}
            by_adapter[domain][subtype] = by_adapter[domain].get(subtype, 0) + 1

        return {
            "by_source": by_source,
            "by_status": by_status,
            "by_severity": by_severity,
            "by_adapter": by_adapter,
        }
