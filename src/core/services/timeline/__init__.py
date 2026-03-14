"""
Timeline service — unified chronological view of all platform events.

Aggregates 17 event sources into a single normalized, filterable,
chain-aware feed via the mediator and work queue.

Public API::

    from src.core.services.timeline.models import (
        TimelineEntry,
        TimelineQuery,
        TimelinePage,
        Source,
        EntryStatus,
        Severity,
        Locality,
        Actor,
        ChainRole,
        SortBy,
        SortDir,
    )
"""

from src.core.services.timeline.models import (
    Actor,
    ChainRole,
    EntryStatus,
    Locality,
    Severity,
    SortBy,
    SortDir,
    Source,
    TimelineEntry,
    TimelinePage,
    TimelineQuery,
)

__all__ = [
    "Actor",
    "ChainRole",
    "EntryStatus",
    "Locality",
    "Severity",
    "SortBy",
    "SortDir",
    "Source",
    "TimelineEntry",
    "TimelinePage",
    "TimelineQuery",
]
