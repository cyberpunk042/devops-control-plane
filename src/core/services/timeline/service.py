"""
TimelineService — aggregates timeline entries from mediator view nodes.

Accepts a TimelineQuery, dispatches to the appropriate mediator view node,
applies remaining in-memory filter axes, sorts, paginates with cursor,
and returns a TimelinePage.

This is the only layer that knows about the query API.
Adapters and mediator nodes are purely data — no query logic there.
"""

from __future__ import annotations

import logging
from pathlib import Path

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

# ── View node selection ──────────────────────────────────────────────
# When no time constraint is given, we use view.recent (last 24 h) as the
# default starting point.  The caller can push further back with before_ts.
# Specific source/locality filters map to the narrower view nodes to avoid
# loading the full merged set unnecessarily.

_ALL_SOURCE_PATH = "timeline.source.scan_activity"  # fallback for direct source reads

_LOCALITY_VIEW = {
    Locality.LOCAL: "timeline.view.local",
    Locality.SHARED: "timeline.view.shared",
}


def _pick_view_path(q: TimelineQuery) -> str:
    """Choose the best mediator view node for this query.

    Rules (first match wins):
    1. chain_id filter → load timeline.view.chains (all chained entries)
    2. locality=LOCAL  → timeline.view.local
    3. locality=SHARED → timeline.view.shared
    4. date_from with window > 7d → timeline.view.month
    5. date_from with window > 1d → timeline.view.week
    6. default          → timeline.view.recent (last 24h)

    The service applies all remaining filters in-memory after the mediator
    call, so these view paths are optimisations — correctness is guaranteed
    by the in-memory filter pass.
    """
    if q.chain_id:
        return "timeline.view.chains"

    if q.locality == Locality.LOCAL:
        return "timeline.view.local"
    if q.locality == Locality.SHARED:
        return "timeline.view.shared"

    import time
    if q.date_from is not None:
        age = time.time() - q.date_from
        if age > 7 * 86_400:
            return "timeline.view.month"
        if age > 86_400:
            return "timeline.view.week"

    return "timeline.view.recent"


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

    # severity filter
    if q.severities:
        if entry.severity is None or entry.severity not in q.severities:
            return False

    # locality filter (already handled by view selection — kept for correctness)
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
    """Aggregates timeline entries from mediator nodes.

    Usage::

        svc = TimelineService()
        page = svc.query(TimelineQuery(sources=[Source.GIT], limit=50))
    """

    def query(self, q: TimelineQuery) -> TimelinePage:
        """Execute a timeline query and return a paginated page.

        Steps:
        1. Pick best view node for this query
        2. Call mediator.get(view_path)["data"] to get cached entries
        3. Apply all filter axes in-memory
        4. Sort
        5. Apply cursor bounds (before_ts / after_ts)
        6. Paginate (limit + has_more)
        7. Build and return TimelinePage
        """
        from src.core.services.mediator import get_mediator

        mediator = get_mediator()
        view_path = _pick_view_path(q)

        try:
            entries: list[TimelineEntry] = mediator.get(view_path)["data"]
        except Exception as exc:
            logger.warning("timeline: mediator.get(%s) failed: %s", view_path, exc)
            entries = []

        # Ensure we have a list of TimelineEntry objects
        if not isinstance(entries, list):
            entries = []

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

    def stats(self) -> dict:
        """Return aggregate counts from timeline.view.stats."""
        from src.core.services.mediator import get_mediator

        mediator = get_mediator()
        try:
            return mediator.get("timeline.view.stats")["data"]
        except Exception as exc:
            logger.warning("timeline: stats failed: %s", exc)
            return {}

    def domains(self) -> dict:
        """Return per-source entry counts.

        Used by the /api/timeline/domains endpoint (left navigator Domains mode).
        """
        stats = self.stats()
        return stats.get("by_source", {})

    def chains(self, q: TimelineQuery | None = None) -> list[dict]:
        """Return chain summaries for the left navigator Chains mode.

        Each chain dict has: chain_id, entry_count, first_ts, last_ts,
        summary (from ORIGIN entry), sources (set of source values).
        """
        from src.core.services.mediator import get_mediator

        mediator = get_mediator()
        try:
            entries: list[TimelineEntry] = mediator.get("timeline.view.chains")["data"]
        except Exception as exc:
            logger.warning("timeline: chains failed: %s", exc)
            return []

        # Group by chain_id
        chain_map: dict[str, dict] = {}
        for e in entries:
            if e.chain_id is None:
                continue
            if e.chain_id not in chain_map:
                chain_map[e.chain_id] = {
                    "chain_id": e.chain_id,
                    "entry_count": 0,
                    "first_ts": e.ts,
                    "last_ts": e.ts,
                    "summary": e.summary,
                    "sources": set(),
                }
            c = chain_map[e.chain_id]
            c["entry_count"] += 1
            c["first_ts"] = min(c["first_ts"], e.ts)
            c["last_ts"] = max(c["last_ts"], e.ts)
            c["sources"].add(e.source.value)
            # Prefer ORIGIN entry's summary as chain summary
            from src.core.services.timeline.models import ChainRole
            if e.chain_role == ChainRole.ORIGIN:
                c["summary"] = e.summary

        # Collect members per chain (lightweight — id, ts, source, subtype, status, locality, summary, chain_role)
        member_map: dict[str, list[dict]] = {}
        for e in entries:
            if e.chain_id is None:
                continue
            member_map.setdefault(e.chain_id, []).append({
                "id":              e.id,
                "ts":              e.ts,
                "source":          e.source.value if e.source else "",
                "subtype":         e.subtype or "",
                "status":          e.status.value if e.status else "ok",
                "locality":        e.locality.value if e.locality else "local",
                "summary":         e.summary or "",
                "chain_role":      e.chain_role.value if e.chain_role else "",
                "chain_parent_ref": e.chain_parent_ref,
            })

        # Sort each chain's members by ts ascending
        for members in member_map.values():
            members.sort(key=lambda m: m["ts"])

        # Serialize (sets are not JSON-safe)
        result = []
        for c in sorted(chain_map.values(), key=lambda x: x["last_ts"], reverse=True):
            result.append({
                **c,
                "sources": sorted(c["sources"]),
                "members": member_map.get(c["chain_id"], []),
            })
        return result

    def calendar(self) -> list[dict]:
        """Return per-day entry counts for the Calendar mode navigator.

        Reads timeline.view.month to cover 30 days.
        Returns list of {date: 'YYYY-MM-DD', count: int, has_failure: bool}
        sorted by date descending.
        """
        from src.core.services.mediator import get_mediator
        from datetime import datetime, timezone

        mediator = get_mediator()
        try:
            entries: list[TimelineEntry] = mediator.get("timeline.view.month")["data"]
        except Exception as exc:
            logger.warning("timeline: calendar failed: %s", exc)
            return []

        day_map: dict[str, dict] = {}
        for e in entries:
            d = datetime.fromtimestamp(e.ts, tz=timezone.utc)
            key = d.strftime("%Y-%m-%d")
            if key not in day_map:
                day_map[key] = {"date": key, "count": 0, "has_failure": False}
            day_map[key]["count"] += 1
            if e.status and e.status.value in ("failed", "attention", "warning"):
                day_map[key]["has_failure"] = True

        return sorted(day_map.values(), key=lambda x: x["date"], reverse=True)
