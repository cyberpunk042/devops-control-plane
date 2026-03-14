"""
Timeline domain registration — wires all timeline nodes into the mediator tree.

Registers 23 nodes in 3 categories::

    Source nodes (6)  — raw data, mtime-watched or ttl-polled
    View nodes   (10) — pre-aggregated slices of the merged feed
    Feed nodes   (7)  — curated outputs consumed by M2-M5

Dependency graph::

    scan_activity ─┐
    cli_ops        │
    git_log        ├──→ view.recent / today / week / month
    ledger_runs    │    view.local / shared / failures / security
    ledger_audits  │    view.chains / stats
    chat           ┘

    view.failures + feed.security_posture ──→ feed.notifications
    view.*                                ──→ feed.readiness
    git_log                               ──→ feed.changelog

All resolvers call the adapter layer or perform in-memory aggregation
over source node results.  No adapter is called more than once per
mediator resolution cycle — sources are cached by the mediator.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.tree import TreeRegistration
from src.core.services.timeline.models import (
    EntryStatus,
    Locality,
    Severity,
    Source,
    TimelineEntry,
)

logger = logging.getLogger(__name__)

# ── Path constants ──────────────────────────────────────────────────

_ALL_SOURCES = [
    "timeline.source.scan_activity",
    "timeline.source.cli_ops",
    "timeline.source.git_log",
    "timeline.source.ledger_runs",
    "timeline.source.ledger_audits",
    "timeline.source.chat",
]

_LOCAL_SOURCES = [
    "timeline.source.scan_activity",
    "timeline.source.cli_ops",
]

_SHARED_SOURCES = [
    "timeline.source.git_log",
    "timeline.source.ledger_runs",
    "timeline.source.ledger_audits",
    "timeline.source.chat",
]

_SECURITY_SOURCES_SET = frozenset({
    Source.SECURITY, Source.AUDIT, Source.POSTURE, Source.VAULT,
})

_ALL_VIEW_PATHS = [
    "timeline.view.recent",
    "timeline.view.today",
    "timeline.view.week",
    "timeline.view.month",
    "timeline.view.local",
    "timeline.view.shared",
    "timeline.view.failures",
    "timeline.view.security",
    "timeline.view.chains",
    "timeline.view.stats",
]


# ── Helpers ─────────────────────────────────────────────────────────


def _get_entries(mediator: QueryMediator, paths: list[str]) -> list[TimelineEntry]:
    """Collect and merge TimelineEntry lists from multiple mediator nodes."""
    merged: list[TimelineEntry] = []
    for path in paths:
        try:
            data = mediator.get(path)["data"]
            if isinstance(data, list):
                merged.extend(data)
        except Exception as exc:
            logger.warning("timeline: failed to get %s: %s", path, exc)
    return merged


def _today_start_ts() -> float:
    """Return unix epoch of today's midnight (local time, UTC)."""
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp()


# ── Registration ────────────────────────────────────────────────────


def register_timeline(mediator: QueryMediator) -> None:
    """Register all 23 timeline.* nodes in the mediator tree.

    Must be called after register_all() installs other domains,
    as timeline feed nodes may eventually depend on devops/audit data.

    Registration order: source nodes first (no deps), then view nodes
    (depend on sources), then feed nodes (depend on views/sources).
    """
    tree = mediator.tree
    root = mediator.project_root

    # ================================================================
    # CATEGORY 1 — Source nodes (6)
    # Raw data readers. Each wraps an adapter.load() call.
    # ================================================================

    tree.register(TreeRegistration(
        path="timeline.source.scan_activity",
        resolver=lambda: __import__(
            "src.core.services.timeline.adapters",
            fromlist=["ScanActivityAdapter"],
        ).ScanActivityAdapter(root).load(),
        mtime_paths=[".state/audit_activity.json"],
        persist=False,
        size=1,
    ))

    tree.register(TreeRegistration(
        path="timeline.source.cli_ops",
        resolver=lambda: __import__(
            "src.core.services.timeline.adapters",
            fromlist=["CliOpsAdapter"],
        ).CliOpsAdapter(root).load(),
        mtime_paths=[".state/audit.ndjson"],
        persist=False,
        size=2,
    ))

    tree.register(TreeRegistration(
        path="timeline.source.git_log",
        resolver=lambda: __import__(
            "src.core.services.timeline.adapters",
            fromlist=["GitLogAdapter"],
        ).GitLogAdapter(root).load(),
        ttl=60,
        persist=False,
        size=3,
    ))

    tree.register(TreeRegistration(
        path="timeline.source.ledger_runs",
        resolver=lambda: __import__(
            "src.core.services.timeline.adapters",
            fromlist=["LedgerRunsAdapter"],
        ).LedgerRunsAdapter(root).load(),
        ttl=120,
        persist=False,
        size=2,
    ))

    tree.register(TreeRegistration(
        path="timeline.source.ledger_audits",
        resolver=lambda: __import__(
            "src.core.services.timeline.adapters",
            fromlist=["LedgerAuditsAdapter"],
        ).LedgerAuditsAdapter(root).load(),
        ttl=120,
        persist=False,
        size=2,
    ))

    tree.register(TreeRegistration(
        path="timeline.source.chat",
        resolver=lambda: __import__(
            "src.core.services.timeline.adapters",
            fromlist=["ChatAdapter"],
        ).ChatAdapter(root).load(),
        ttl=120,
        persist=False,
        size=1,
    ))

    # ================================================================
    # CATEGORY 2 — View nodes (10)
    # In-memory aggregations over source nodes.
    # ================================================================

    def _resolve_recent() -> list[TimelineEntry]:
        """All entries from the last 24 hours, newest-first."""
        cutoff = time.time() - 86_400
        entries = _get_entries(mediator, _ALL_SOURCES)
        return sorted(
            (e for e in entries if e.ts >= cutoff),
            key=lambda e: e.ts, reverse=True,
        )

    tree.register(TreeRegistration(
        path="timeline.view.recent",
        resolver=_resolve_recent,
        ttl=30,
        persist=False,
        size=2,
        depends_on=_ALL_SOURCES,
    ))

    def _resolve_today() -> list[TimelineEntry]:
        """All entries from today (UTC midnight onward), newest-first."""
        cutoff = _today_start_ts()
        entries = _get_entries(mediator, _ALL_SOURCES)
        return sorted(
            (e for e in entries if e.ts >= cutoff),
            key=lambda e: e.ts, reverse=True,
        )

    tree.register(TreeRegistration(
        path="timeline.view.today",
        resolver=_resolve_today,
        ttl=30,
        persist=False,
        size=1,
        depends_on=_ALL_SOURCES,
    ))

    def _resolve_week() -> list[TimelineEntry]:
        """All entries from the last 7 days, newest-first."""
        cutoff = time.time() - 7 * 86_400
        entries = _get_entries(mediator, _ALL_SOURCES)
        return sorted(
            (e for e in entries if e.ts >= cutoff),
            key=lambda e: e.ts, reverse=True,
        )

    tree.register(TreeRegistration(
        path="timeline.view.week",
        resolver=_resolve_week,
        ttl=60,
        persist=False,
        size=2,
        depends_on=_ALL_SOURCES,
    ))

    def _resolve_month() -> list[TimelineEntry]:
        """All entries from the last 30 days, newest-first."""
        cutoff = time.time() - 30 * 86_400
        entries = _get_entries(mediator, _ALL_SOURCES)
        return sorted(
            (e for e in entries if e.ts >= cutoff),
            key=lambda e: e.ts, reverse=True,
        )

    tree.register(TreeRegistration(
        path="timeline.view.month",
        resolver=_resolve_month,
        ttl=300,
        persist=False,
        size=2,
        depends_on=_ALL_SOURCES,
    ))

    def _resolve_local() -> list[TimelineEntry]:
        """All local-only entries (scan_activity + cli_ops), newest-first."""
        entries = _get_entries(mediator, _LOCAL_SOURCES)
        return sorted(entries, key=lambda e: e.ts, reverse=True)

    tree.register(TreeRegistration(
        path="timeline.view.local",
        resolver=_resolve_local,
        ttl=30,
        persist=False,
        size=1,
        depends_on=_LOCAL_SOURCES,
    ))

    def _resolve_shared() -> list[TimelineEntry]:
        """All shared entries (git + ledger + chat), newest-first."""
        entries = _get_entries(mediator, _SHARED_SOURCES)
        return sorted(entries, key=lambda e: e.ts, reverse=True)

    tree.register(TreeRegistration(
        path="timeline.view.shared",
        resolver=_resolve_shared,
        ttl=60,
        persist=False,
        size=1,
        depends_on=_SHARED_SOURCES,
    ))

    def _resolve_failures() -> list[TimelineEntry]:
        """All entries with failed or warning status, newest-first."""
        entries = _get_entries(mediator, _ALL_SOURCES)
        return sorted(
            (e for e in entries if e.status in (EntryStatus.FAILED, EntryStatus.WARNING, EntryStatus.ATTENTION)),
            key=lambda e: e.ts, reverse=True,
        )

    tree.register(TreeRegistration(
        path="timeline.view.failures",
        resolver=_resolve_failures,
        ttl=30,
        persist=False,
        size=1,
        depends_on=_ALL_SOURCES,
    ))

    def _resolve_security() -> list[TimelineEntry]:
        """All security-related entries (SECURITY, AUDIT, POSTURE, VAULT), newest-first."""
        entries = _get_entries(mediator, ["timeline.source.scan_activity"])
        return sorted(
            (e for e in entries if e.source in _SECURITY_SOURCES_SET),
            key=lambda e: e.ts, reverse=True,
        )

    tree.register(TreeRegistration(
        path="timeline.view.security",
        resolver=_resolve_security,
        ttl=60,
        persist=False,
        size=1,
        depends_on=["timeline.source.scan_activity"],
    ))

    def _resolve_chains() -> list[TimelineEntry]:
        """All entries that belong to a chain (chain_id is set), newest-first."""
        entries = _get_entries(mediator, _ALL_SOURCES)
        return sorted(
            (e for e in entries if e.chain_id is not None),
            key=lambda e: e.ts, reverse=True,
        )

    tree.register(TreeRegistration(
        path="timeline.view.chains",
        resolver=_resolve_chains,
        ttl=60,
        persist=False,
        size=2,
        depends_on=_ALL_SOURCES,
    ))

    def _resolve_stats() -> dict[str, Any]:
        """Aggregate counts: total, by source, by status, by locality."""
        entries = _get_entries(mediator, _ALL_SOURCES)
        by_source: dict[str, int] = {}
        by_status: dict[str, int] = {}
        local_count = 0
        shared_count = 0
        chain_count = len({e.chain_id for e in entries if e.chain_id})

        for e in entries:
            by_source[e.source.value] = by_source.get(e.source.value, 0) + 1
            by_status[e.status.value] = by_status.get(e.status.value, 0) + 1
            if e.locality == Locality.LOCAL:
                local_count += 1
            else:
                shared_count += 1

        return {
            "total": len(entries),
            "by_source": by_source,
            "by_status": by_status,
            "local": local_count,
            "shared": shared_count,
            "chains": chain_count,
        }

    tree.register(TreeRegistration(
        path="timeline.view.stats",
        resolver=_resolve_stats,
        ttl=300,
        persist=False,
        size=1,
        depends_on=_ALL_SOURCES,
    ))

    # ================================================================
    # CATEGORY 3 — Feed nodes (7)
    # Curated outputs for downstream milestones (M2-M5).
    # ================================================================

    def _resolve_security_posture() -> list[TimelineEntry]:
        """Security posture signals: SECURITY, AUDIT, POSTURE entries with severity."""
        entries = mediator.get("timeline.view.security")["data"]
        return [e for e in entries if e.severity is not None]

    tree.register(TreeRegistration(
        path="timeline.feed.security_posture",
        resolver=_resolve_security_posture,
        ttl=300,
        persist=False,
        size=1,
        depends_on=["timeline.view.security"],
    ))

    def _resolve_pkg_health() -> list[TimelineEntry]:
        """Package health signals: PKG entries with warning or failed status."""
        entries = _get_entries(mediator, ["timeline.source.scan_activity"])
        return sorted(
            (e for e in entries if e.source == Source.PKG and e.status != EntryStatus.OK),
            key=lambda e: e.ts, reverse=True,
        )

    tree.register(TreeRegistration(
        path="timeline.feed.pkg_health",
        resolver=_resolve_pkg_health,
        ttl=300,
        persist=False,
        size=1,
        depends_on=["timeline.source.scan_activity"],
    ))

    def _resolve_tool_lifecycle() -> list[TimelineEntry]:
        """Tool lifecycle signals: TOOLS and STACK entries."""
        entries = _get_entries(mediator, _LOCAL_SOURCES)
        return sorted(
            (e for e in entries if e.source in (Source.TOOLS, Source.STACK)),
            key=lambda e: e.ts, reverse=True,
        )

    tree.register(TreeRegistration(
        path="timeline.feed.tool_lifecycle",
        resolver=_resolve_tool_lifecycle,
        ttl=300,
        persist=False,
        size=1,
        depends_on=_LOCAL_SOURCES,
    ))

    def _resolve_stack_health() -> list[TimelineEntry]:
        """Stack health signals: STACK entries with non-ok status."""
        entries = _get_entries(mediator, ["timeline.source.scan_activity"])
        return sorted(
            (e for e in entries if e.source == Source.STACK and e.status != EntryStatus.OK),
            key=lambda e: e.ts, reverse=True,
        )

    tree.register(TreeRegistration(
        path="timeline.feed.stack_health",
        resolver=_resolve_stack_health,
        ttl=300,
        persist=False,
        size=1,
        depends_on=["timeline.source.scan_activity"],
    ))

    def _resolve_readiness() -> dict[str, Any]:
        """Readiness score derived from failures and security posture.

        Returns a simple dict with score (0-100) and contributing signals.
        Full scoring formula is designed in E9 (M4) — this is the data surface.
        """
        failures = mediator.get("timeline.view.failures")["data"]
        stats = mediator.get("timeline.view.stats")["data"]
        total = stats.get("total", 0)

        critical = sum(1 for e in failures if e.severity == Severity.CRITICAL)
        high = sum(1 for e in failures if e.severity == Severity.HIGH)
        medium = sum(1 for e in failures if e.severity == Severity.MEDIUM)

        # Rough score: start at 100, deduct for open issues
        score = max(0, 100 - (critical * 20) - (high * 10) - (medium * 3))

        return {
            "score": score,
            "total_entries": total,
            "open_failures": len(failures),
            "critical": critical,
            "high": high,
            "medium": medium,
        }

    tree.register(TreeRegistration(
        path="timeline.feed.readiness",
        resolver=_resolve_readiness,
        ttl=300,
        persist=False,
        size=2,
        depends_on=["timeline.view.failures", "timeline.view.stats"],
    ))

    def _resolve_changelog() -> list[dict[str, Any]]:
        """Changelog feed: GIT + PLAN entries formatted for changelog rendering."""
        entries = _get_entries(mediator, ["timeline.source.git_log"])
        result = []
        for e in sorted(entries, key=lambda x: x.ts, reverse=True):
            result.append({
                "ts": e.ts,
                "ref": e.ref,
                "summary": e.summary,
                "source": e.source.value,
                "subtype": e.subtype,
                "detail": e.detail,
            })
        return result

    tree.register(TreeRegistration(
        path="timeline.feed.changelog",
        resolver=_resolve_changelog,
        ttl=600,
        persist=False,
        size=2,
        depends_on=["timeline.source.git_log"],
    ))

    def _resolve_notifications() -> list[dict[str, Any]]:
        """Notification candidates: failures + security posture with severity."""
        failures = mediator.get("timeline.view.failures")["data"]
        posture = mediator.get("timeline.feed.security_posture")["data"]

        # Deduplicate by id, sort by severity then ts
        seen: set[str] = set()
        candidates: list[TimelineEntry] = []
        for e in failures + posture:
            if e.id not in seen:
                seen.add(e.id)
                candidates.append(e)

        severity_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            None: 4,
        }
        candidates.sort(key=lambda e: (severity_order.get(e.severity, 4), -e.ts))

        return [
            {
                "id": e.id,
                "ts": e.ts,
                "source": e.source.value,
                "summary": e.summary,
                "status": e.status.value,
                "severity": e.severity.value if e.severity else None,
            }
            for e in candidates
        ]

    tree.register(TreeRegistration(
        path="timeline.feed.notifications",
        resolver=_resolve_notifications,
        ttl=60,
        persist=False,
        size=1,
        depends_on=["timeline.view.failures", "timeline.feed.security_posture"],
    ))

    logger.debug("registered timeline.* nodes (23 total)")
