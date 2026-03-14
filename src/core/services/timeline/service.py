"""
TimelineService — reads from the timeline.data aggregate mediator node.

The aggregate node (timeline.data) is the single source of truth.
It contains entries, facets, chains, and calendar — all computed from
the same source fetch, guaranteed consistent.

The service provides:
  - data()  → full aggregate dict (for store injection + /api/timeline/data)
  - query() → paginated/filtered TimelinePage (for /api/timeline advanced queries)
"""

from __future__ import annotations

import logging

from src.core.services.timeline.models import (
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

logger = logging.getLogger(__name__)


# ── Filter helpers ───────────────────────────────────────────────────

def _matches(entry: TimelineEntry, q: TimelineQuery) -> bool:
    """Return True if entry passes all active filter axes."""
    # source filter
    if q.sources and entry.source not in q.sources:
        return False

    # subtype filter
    if q.subtypes and entry.subtype not in q.subtypes:
        return False

    # status filter
    if q.statuses and entry.status not in q.statuses:
        return False

    # severity filter (None in q.severities matches entries with no severity)
    if q.severities:
        if entry.severity not in q.severities:
            return False

    # locality filter
    if q.locality and entry.locality != q.locality:
        return False

    # envs filter (entry.env is a list — match if any overlap)
    if q.envs and not any(env in entry.env for env in q.envs):
        return False

    # modules filter
    if q.modules and not any(mod in entry.modules for mod in q.modules):
        return False

    # actor filter
    if q.actors and entry.actor not in q.actors:
        return False

    # date range
    if q.date_from is not None and entry.ts < q.date_from:
        return False
    if q.date_to is not None and entry.ts > q.date_to:
        return False

    # chain_id filter
    if q.chain_id and entry.chain_id != q.chain_id:
        return False

    # chain_roles filter
    if q.chain_roles and entry.chain_role not in q.chain_roles:
        return False

    # free-text search (summary + subtype + ref)
    if q.q:
        needle = q.q.lower()
        haystack = " ".join(filter(None, [
            entry.summary or "",
            entry.subtype or "",
            entry.ref or "",
            entry.source.value if entry.source else "",
        ])).lower()
        if needle not in haystack:
            return False

    return True


def _sort_key(entry: TimelineEntry, sort_by: SortBy):
    """Return the sort key for the given sort field."""
    if sort_by == SortBy.TS:
        return entry.ts
    if sort_by == SortBy.SOURCE:
        return entry.source.value if entry.source else ""
    if sort_by == SortBy.STATUS:
        _order = {
            EntryStatus.FAILED: 0,
            EntryStatus.ATTENTION: 1,
            EntryStatus.WARNING: 2,
            EntryStatus.OK: 3,
        }
        return _order.get(entry.status, 99)
    if sort_by == SortBy.SEVERITY:
        _sev_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            None: 99,
        }
        return _sev_order.get(entry.severity, 99)
    return entry.ts


# ── Service ──────────────────────────────────────────────────────────


class TimelineService:
    """Reads from the timeline.data aggregate mediator node.

    Usage::

        svc = TimelineService()
        full = svc.data()                    # full aggregate for store
        page = svc.query(TimelineQuery(...)) # paginated for API
    """

    def data(self) -> dict:
        """Return the full timeline.data aggregate dict.

        Used by:
          - /api/timeline/data (cold start fallback)
          - /api/timeline/chains, /domains, /calendar, /stats (thin wrappers)
          - __INITIAL_STATE__ injection via _KEY_TO_MEDIATOR + peek()
        """
        from src.core.services.mediator import get_mediator

        mediator = get_mediator()
        try:
            return mediator.get("timeline.data")["data"]
        except Exception as exc:
            logger.warning("timeline: data failed: %s", exc)
            return {"entries": [], "facets": {}, "chains": [], "calendar": []}

    def query(self, q: TimelineQuery) -> TimelinePage:
        """Execute a timeline query and return a paginated page.

        Reads entries from timeline.data, applies all filter axes
        in-memory, sorts, paginates with cursor, returns TimelinePage.
        """
        raw = self.data()
        entries = [TimelineEntry.from_dict(d) for d in raw.get("entries", [])]

        # Apply in-memory filters
        filtered = [e for e in entries if _matches(e, q)]

        # Sort
        reverse = q.sort_dir == SortDir.DESC
        filtered.sort(key=lambda e: _sort_key(e, q.sort_by), reverse=reverse)

        # Apply cursor bounds (after_ts = live-reload lower bound, before_ts = scroll-back upper bound)
        if q.after_ts is not None:
            filtered = [e for e in filtered if e.ts > q.after_ts]
        if q.before_ts is not None:
            filtered = [e for e in filtered if e.ts < q.before_ts]

        # Paginate
        limit = q.limit
        has_more = len(filtered) > limit
        page_entries = filtered[:limit]

        next_cursor = page_entries[-1].ts if (has_more and page_entries) else None
        prev_cursor = page_entries[0].ts if page_entries else None

        return TimelinePage(
            entries=page_entries,
            has_more=has_more,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
            total_hint=len(filtered),
        )
