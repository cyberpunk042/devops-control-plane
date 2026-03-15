"""
Timeline domain registration — wires all timeline nodes into the mediator tree.

Registers 14 nodes in 3 categories::

    Source nodes    (6)  — raw data, mtime-watched or ttl-polled
    Aggregate node  (1)  — single UI data surface (entries + facets + chains + calendar)
    Feed nodes      (7)  — curated outputs consumed by M2-M5

Dependency graph::

    scan_activity ─┐
    cli_ops        │
    git_log        ├──→ timeline.data (aggregate)
    ledger_runs    │
    ledger_audits  │
    chat           ┘

    timeline.data ──→ feed.security_posture
    timeline.data ──→ feed.pkg_health
    timeline.data ──→ feed.tool_lifecycle
    timeline.data ──→ feed.stack_health
    timeline.data ──→ feed.readiness
    timeline.data ──→ feed.changelog
    timeline.data ──→ feed.notifications

The aggregate node follows the proven double-cache pattern:
  - persist=True  → disk shard for warm start
  - single TTL    → all data consistent by construction
  - injected via __INITIAL_STATE__ → storeGet() instant first paint
  - SSE cache:done → storeSet() live updates

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
    Actor,
    ChainRole,
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
    "timeline.source.runs",
    "timeline.source.mediator",
    "timeline.source.github",
    "timeline.source.operations",
]

_LOCAL_SOURCES = [
    "timeline.source.scan_activity",
    "timeline.source.cli_ops",
    "timeline.source.runs",
    "timeline.source.mediator",
    "timeline.source.operations",
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



def _get_entries_by_adapter(
    mediator: QueryMediator,
) -> list[tuple[str, TimelineEntry]]:
    """Fetch entries from all sources, tagged with their adapter name.

    Returns a list of (adapter_name, entry) tuples.

    For most sources, adapter name is the short name from the path:
      timeline.source.git_log → "git_log"

    For mediator entries, the adapter name is derived from the entry's
    ref (mediator path) using _MEDIATOR_DOMAIN_MAP so entries appear
    under their domain: devops.docker → "docker", posture.full → "posture".
    """
    result: list[tuple[str, TimelineEntry]] = []
    for path in _ALL_SOURCES:
        adapter_name = path.split(".")[-1]  # e.g. "scan_activity"
        try:
            data = mediator.get(path)["data"]
            if isinstance(data, list):
                for entry in data:
                    if adapter_name in ("mediator", "operations") and entry.ref:
                        # Tag by domain, not generic "mediator"/"operations"
                        domain = _mediator_domain(entry.ref)
                        result.append((domain, entry))
                    else:
                        result.append((adapter_name, entry))
        except Exception as exc:
            logger.warning("timeline: failed to get %s: %s", path, exc)
    return result


# ── Mediator path → domain mapping ───────────────────────────────────
#
# devops.* nodes use the suffix as domain (devops.docker → "docker")
# All other prefixes use the prefix as domain (audit.scores → "audit")

_DEVOPS_LIKE = ("devops.", "catalog.")


def _mediator_domain(ref: str) -> str:
    """Derive the domain adapter name from a mediator path.

    devops.docker → "docker"   (suffix — devops is a bag of integrations)
    catalog.tools → "tools"    (suffix — same pattern)
    audit.scores  → "audit"    (prefix — audit is a cohesive domain)
    posture.full  → "posture"  (prefix)
    github.pulls  → "github"   (prefix)
    index.scan    → "index"    (prefix)
    """
    if "." not in ref:
        return ref
    prefix, suffix = ref.split(".", 1)
    if any(ref.startswith(p) for p in _DEVOPS_LIKE):
        return suffix
    return prefix


def _build_facets(
    tagged_entries: list[tuple[str, TimelineEntry]],
) -> dict[str, Any]:
    """Compute facet counts from adapter-tagged entries.

    Returns:
        by_source:   {source_value: count}
        by_status:   {status_value: count}
        by_severity: {severity_value: count}
        by_adapter:  {adapter_name: {subtype_value: count}}
    """
    by_source: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_adapter: dict[str, dict[str, int]] = {}

    for adapter, e in tagged_entries:
        src = e.source.value
        sub = e.subtype or ""
        by_source[src] = by_source.get(src, 0) + 1
        by_status[e.status.value] = by_status.get(e.status.value, 0) + 1
        sev_key = e.severity.value if e.severity else "none"
        by_severity[sev_key] = by_severity.get(sev_key, 0) + 1

        # Nested: adapter → subtype
        if adapter not in by_adapter:
            by_adapter[adapter] = {}
        by_adapter[adapter][sub] = by_adapter[adapter].get(sub, 0) + 1

    return {
        "by_source": by_source,
        "by_status": by_status,
        "by_severity": by_severity,
        "by_adapter": by_adapter,
    }


def _build_chains(entries: list[TimelineEntry]) -> list[dict[str, Any]]:
    """Build chain summaries from entries that have a chain_id."""
    chain_map: dict[str, dict] = {}
    member_map: dict[str, list[dict]] = {}

    for e in entries:
        if e.chain_id is None:
            continue

        # Chain summary
        if e.chain_id not in chain_map:
            # For cycle/operation chains, use the chain_id as the label
            default_summary = e.chain_id if e.chain_id.startswith(("cycle-", "run_")) else e.summary
            chain_map[e.chain_id] = {
                "chain_id": e.chain_id,
                "entry_count": 0,
                "first_ts": e.ts,
                "last_ts": e.ts,
                "summary": default_summary,
                "sources": set(),
            }
        c = chain_map[e.chain_id]
        c["entry_count"] += 1
        c["first_ts"] = min(c["first_ts"], e.ts)
        c["last_ts"] = max(c["last_ts"], e.ts)
        c["sources"].add(e.source.value)
        if e.chain_role == ChainRole.ORIGIN and c["entry_count"] == 1:
            # Only use origin summary if it's the first (and thus only) entry so far
            c["summary"] = e.summary

        # Chain member
        member_map.setdefault(e.chain_id, []).append({
            "id":               e.id,
            "ts":               e.ts,
            "source":           e.source.value if e.source else "",
            "subtype":          e.subtype or "",
            "status":           e.status.value if e.status else "ok",
            "locality":         e.locality.value if e.locality else "local",
            "summary":          e.summary or "",
            "chain_role":       e.chain_role.value if e.chain_role else "",
            "chain_parent_ref": e.chain_parent_ref,
        })

    for members in member_map.values():
        members.sort(key=lambda m: m["ts"], reverse=True)
        # If no member has role=origin, promote the earliest to origin
        has_origin = any(m["chain_role"] == "origin" for m in members)
        if not has_origin and members:
            members[0]["chain_role"] = "origin"
            members[0]["chain_parent_ref"] = None

    result = []
    for c in sorted(chain_map.values(), key=lambda x: x["last_ts"], reverse=True):
        # Only include chains with 2+ members — solo entries are not chains
        if c["entry_count"] < 2:
            continue
        members = member_map.get(c["chain_id"], [])
        result.append({
            **c,
            "sources": sorted(c["sources"]),
            "members": members,
        })
    return result


def _build_calendar(entries: list[TimelineEntry]) -> list[dict[str, Any]]:
    """Build per-day counts for the Calendar navigator."""
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


# ── Registration ────────────────────────────────────────────────────


def register_timeline(mediator: QueryMediator) -> None:
    """Register all timeline.* nodes in the mediator tree.

    Must be called after register_all() installs other domains,
    as timeline feed nodes may eventually depend on devops/audit data.

    Registration order: source nodes first (no deps), then the
    aggregate node (depends on sources), then feed nodes (depend
    on aggregate).
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

    tree.register(TreeRegistration(
        path="timeline.source.runs",
        resolver=lambda: __import__(
            "src.core.services.timeline.adapters",
            fromlist=["RunsAdapter"],
        ).RunsAdapter(root).load(),
        mtime_paths=[".state/runs.jsonl"],
        persist=False,
        size=2,
    ))

    tree.register(TreeRegistration(
        path="timeline.source.mediator",
        resolver=lambda: __import__(
            "src.core.services.mediator.subscribers.mediator_timeline",
            fromlist=["get_entries"],
        ).get_entries(),
        ttl=10,
        persist=False,
        size=3,
    ))

    tree.register(TreeRegistration(
        path="timeline.source.github",
        resolver=lambda: __import__(
            "src.core.services.timeline.adapters",
            fromlist=["GitHubAdapter"],
        ).GitHubAdapter(root).load(),
        ttl=120,
        persist=False,
        size=2,
    ))

    def _resolve_operations():
        """Return timeline entries from the operation tracker."""
        tracker = mediator._tracker
        if tracker is None:
            return []
        return tracker.get_timeline_entries()

    tree.register(TreeRegistration(
        path="timeline.source.operations",
        resolver=_resolve_operations,
        ttl=10,
        persist=False,
        size=3,
    ))

    # ================================================================
    # CATEGORY 2 — Aggregate node (1)
    # Single UI data surface. Replaces the 10 view nodes.
    # Follows the proven double-cache pattern (persist=True).
    # ================================================================

    def _resolve_data() -> dict[str, Any]:
        """Single computation: entries + facets + chains + calendar.

        All data comes from the same source fetch — guaranteed consistent.
        Entries are sorted newest-first, no time filter (the full dataset).
        Filtering (time, source, status, etc.) happens client-side or in
        TimelineService.query() for the paginated API.
        """
        tagged = _get_entries_by_adapter(mediator)
        tagged.sort(key=lambda t: t[1].ts, reverse=True)

        entries = [e for _, e in tagged]
        entry_dicts = []
        for adapter, e in tagged:
            d = e.to_dict()
            d["adapter"] = adapter
            entry_dicts.append(d)

        return {
            "entries": entry_dicts,
            "facets": _build_facets(tagged),
            "chains": _build_chains(entries),
            "calendar": _build_calendar(entries),
        }

    tree.register(TreeRegistration(
        path="timeline.data",
        resolver=_resolve_data,
        ttl=30,
        persist=True,
        size=5,
        depends_on=_ALL_SOURCES,
    ))

    # ================================================================
    # CATEGORY 3 — Feed nodes (7)
    # Curated outputs for downstream milestones (M2-M5).
    # All depend on timeline.data (the aggregate).
    # ================================================================

    def _resolve_security_posture() -> list[TimelineEntry]:
        """Security posture signals: SECURITY, AUDIT, POSTURE entries with severity."""
        raw = (mediator.peek("timeline.data") or {}).get("data", {"entries": []})
        entries = [TimelineEntry.from_dict(d) for d in raw["entries"]]
        return [e for e in entries
                if e.source in _SECURITY_SOURCES_SET and e.severity is not None]

    tree.register(TreeRegistration(
        path="timeline.feed.security_posture",
        resolver=_resolve_security_posture,
        ttl=300,
        persist=False,
        size=1,
        depends_on=["timeline.data"],
    ))

    def _resolve_pkg_health() -> list[TimelineEntry]:
        """Package health signals: PKG entries with warning or failed status."""
        raw = (mediator.peek("timeline.data") or {}).get("data", {"entries": []})
        entries = [TimelineEntry.from_dict(d) for d in raw["entries"]]
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
        depends_on=["timeline.data"],
    ))

    def _resolve_tool_lifecycle() -> list[TimelineEntry]:
        """Tool lifecycle signals: TOOLS and STACK entries."""
        raw = (mediator.peek("timeline.data") or {}).get("data", {"entries": []})
        entries = [TimelineEntry.from_dict(d) for d in raw["entries"]]
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
        depends_on=["timeline.data"],
    ))

    def _resolve_stack_health() -> list[TimelineEntry]:
        """Stack health signals: STACK entries with non-ok status."""
        raw = (mediator.peek("timeline.data") or {}).get("data", {"entries": []})
        entries = [TimelineEntry.from_dict(d) for d in raw["entries"]]
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
        depends_on=["timeline.data"],
    ))

    def _resolve_readiness() -> dict[str, Any]:
        """Readiness score derived from failures and stats.

        Returns a simple dict with score (0-100) and contributing signals.
        Full scoring formula is designed in E9 (M4) — this is the data surface.
        """
        raw = (mediator.peek("timeline.data") or {}).get("data", {"entries": []})
        entries = [TimelineEntry.from_dict(d) for d in raw["entries"]]
        failures = [e for e in entries
                    if e.status in (EntryStatus.FAILED, EntryStatus.WARNING, EntryStatus.ATTENTION)]
        total = len(entries)

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
        depends_on=["timeline.data"],
    ))

    def _resolve_changelog() -> list[dict[str, Any]]:
        """Changelog feed: GIT + PLAN entries formatted for changelog rendering."""
        raw = (mediator.peek("timeline.data") or {}).get("data", {"entries": []})
        entries = [TimelineEntry.from_dict(d) for d in raw["entries"]]
        result = []
        for e in sorted(entries, key=lambda x: x.ts, reverse=True):
            if e.source in (Source.GIT, Source.PLAN):
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
        depends_on=["timeline.data"],
    ))

    def _resolve_notifications() -> list[dict[str, Any]]:
        """Notification candidates: failures + security posture with severity."""
        raw = (mediator.peek("timeline.data") or {}).get("data", {"entries": []})
        entries = [TimelineEntry.from_dict(d) for d in raw["entries"]]
        failures = [e for e in entries
                    if e.status in (EntryStatus.FAILED, EntryStatus.WARNING, EntryStatus.ATTENTION)]
        posture = [e for e in entries
                   if e.source in _SECURITY_SOURCES_SET and e.severity is not None]

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
        depends_on=["timeline.data"],
    ))

    logger.debug("registered timeline.* nodes (14 total)")
