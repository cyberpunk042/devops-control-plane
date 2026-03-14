"""
Timeline data models — unified entry contract and query/response shapes.

Defines the single normalized data contract that every source adapter maps
into, and the query/response shapes used by TimelineService and the API route.

Follows project patterns:
  - ``StrEnum`` for string enums (matches ``RankLevel`` in system_posture)
  - ``@dataclass`` with ``to_dict()`` / ``from_dict()`` for serializable models
  - ``from __future__ import annotations`` throughout
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


# ═══════════════════════════════════════════════════════════════════
#  Enums
# ═══════════════════════════════════════════════════════════════════


class Source(StrEnum):
    """Domain of origin for a timeline entry — 17 sources covering all platform domains."""

    GIT = "git"
    AUDIT = "audit"
    PKG = "pkg"
    VAULT = "vault"
    ENV = "env"
    TOOLS = "tools"
    STACK = "stack"
    CI = "ci"
    TESTS = "tests"
    BACKUP = "backup"
    CHAT = "chat"
    PLAN = "plan"
    PLATFORM = "platform"
    POSTURE = "posture"
    SECURITY = "security"
    WIZARD = "wizard"
    CONFIG = "config"


class EntryStatus(StrEnum):
    """Outcome status of a timeline entry."""

    OK = "ok"
    WARNING = "warning"
    ATTENTION = "attention"
    FAILED = "failed"


class Severity(StrEnum):
    """Severity level — null/absent for neutral/informational entries."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Locality(StrEnum):
    """Locality of the event — where it exists.

    ``local``  — exists only in ``.state/`` on this machine
    ``shared`` — committed to git (ledger branch or project repo)
    """

    LOCAL = "local"
    SHARED = "shared"


class Actor(StrEnum):
    """What triggered this event."""

    USER = "user"
    SCHEDULER = "scheduler"
    PLATFORM = "platform"
    AUTOMATION = "automation"


class ChainRole(StrEnum):
    """Position of this entry within its lifecycle chain.

    ``origin``   — first event that started the chain (e.g. local audit ran)
    ``step``     — intermediate event (e.g. CI started, scan staged)
    ``terminal`` — final event in the chain (e.g. committed, passed, resolved)
    """

    ORIGIN = "origin"
    STEP = "step"
    TERMINAL = "terminal"


class SortBy(StrEnum):
    """Sort key options for timeline queries."""

    TS = "ts"
    SEVERITY = "severity"
    SOURCE = "source"
    STATUS = "status"


class SortDir(StrEnum):
    """Sort direction for timeline queries."""

    ASC = "asc"
    DESC = "desc"


# ═══════════════════════════════════════════════════════════════════
#  TimelineEntry — the unified normalized event record
# ═══════════════════════════════════════════════════════════════════


@dataclass
class TimelineEntry:
    """A single normalized timeline event.

    Every source adapter maps its raw records into this shape.
    The aggregator, API, and frontend all speak this model exclusively.

    Identity:
        id:   Stable unique ID per entry — ``source:subtype:ref`` or hash.
        ts:   Unix epoch float — the single sort key across all sources.
        ref:  Back-link to the original record (run_id, commit hash, thread_id, ...).

    Classification:
        source:   Domain of origin (one of 17 Source values).
        subtype:  Source-specific subdivision (L2, npm, pip, staging→prod, ...).
        actor:    What triggered this event.

    Outcome:
        status:   Entry outcome — ok, warning, attention, or failed.
        severity: Severity level — None for neutral/informational events.

    Locality:
        locality: local = .state/ only on this machine; shared = in git.

    Scope:
        env:     Environments involved — empty list if not applicable.
        modules: Affected modules/domains — empty list if project-wide.

    Content:
        summary: One-line human-readable description — always present.
        detail:  Source-specific payload, opaque to aggregator. Structure
                 is defined per source in the Source Taxonomy (§2).

    Lifecycle chain:
        chain_id:         Groups related entries across sources and localities.
        chain_role:       Position within the chain (origin / step / terminal).
        chain_parent_ref: ref of the entry that directly caused this one —
                          enables tree-shaped chains (one commit → multiple CI runs).

    Origin metadata:
        hostname: Machine where the event was produced.
        os:       OS identifier (linux, darwin, win32).
        platform: Platform context if relevant (wsl2, docker, native, ...).
    """

    # -- Identity
    id: str = ""
    ts: float = 0.0
    ref: str | None = None

    # -- Classification
    source: Source = Source.PLATFORM
    subtype: str | None = None
    actor: Actor = Actor.PLATFORM

    # -- Outcome
    status: EntryStatus = EntryStatus.OK
    severity: Severity | None = None

    # -- Locality
    locality: Locality = Locality.LOCAL

    # -- Scope
    env: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)

    # -- Content
    summary: str = ""
    detail: dict[str, Any] | None = None

    # -- Lifecycle chain
    chain_id: str | None = None
    chain_role: ChainRole | None = None
    chain_parent_ref: str | None = None

    # -- Origin metadata
    hostname: str | None = None
    os: str | None = None
    platform: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict for API responses."""
        d: dict[str, Any] = {
            "id": self.id,
            "ts": self.ts,
            "source": self.source.value,
            "actor": self.actor.value,
            "status": self.status.value,
            "locality": self.locality.value,
            "env": self.env,
            "modules": self.modules,
            "summary": self.summary,
        }
        if self.ref is not None:
            d["ref"] = self.ref
        if self.subtype is not None:
            d["subtype"] = self.subtype
        if self.severity is not None:
            d["severity"] = self.severity.value
        if self.detail is not None:
            d["detail"] = self.detail
        if self.chain_id is not None:
            d["chain_id"] = self.chain_id
        if self.chain_role is not None:
            d["chain_role"] = self.chain_role.value
        if self.chain_parent_ref is not None:
            d["chain_parent_ref"] = self.chain_parent_ref
        if self.hostname is not None:
            d["hostname"] = self.hostname
        if self.os is not None:
            d["os"] = self.os
        if self.platform is not None:
            d["platform"] = self.platform
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TimelineEntry:
        """Deserialize from a dict (e.g. loaded from mediator cache)."""
        severity_raw = d.get("severity")
        chain_role_raw = d.get("chain_role")
        return cls(
            id=d.get("id", ""),
            ts=d.get("ts", 0.0),
            ref=d.get("ref"),
            source=Source(d.get("source", Source.PLATFORM)),
            subtype=d.get("subtype"),
            actor=Actor(d.get("actor", Actor.PLATFORM)),
            status=EntryStatus(d.get("status", EntryStatus.OK)),
            severity=Severity(severity_raw) if severity_raw else None,
            locality=Locality(d.get("locality", Locality.LOCAL)),
            env=d.get("env", []),
            modules=d.get("modules", []),
            summary=d.get("summary", ""),
            detail=d.get("detail"),
            chain_id=d.get("chain_id"),
            chain_role=ChainRole(chain_role_raw) if chain_role_raw else None,
            chain_parent_ref=d.get("chain_parent_ref"),
            hostname=d.get("hostname"),
            os=d.get("os"),
            platform=d.get("platform"),
        )


# ═══════════════════════════════════════════════════════════════════
#  TimelineQuery — all 13 filter axes + pagination + sort
# ═══════════════════════════════════════════════════════════════════


@dataclass
class TimelineQuery:
    """Query parameters for the timeline aggregator.

    All filter axes are optional and combinable. Empty list means
    "no filter on this axis" (include all values).

    Filter axes (13):
        sources:     Filter by Source domain — multi-select.
        subtypes:    Filter by source-specific subtype — multi-select.
        statuses:    Filter by outcome status — multi-select.
        severities:  Filter by severity level — multi-select.
        locality:    Filter by locality — single value or None for all.
        envs:        Filter by environment name — multi-select.
        modules:     Filter by affected module — multi-select.
        actors:      Filter by triggering actor — multi-select.
        date_from:   Unix epoch lower bound — inclusive.
        date_to:     Unix epoch upper bound — inclusive.
        chain_id:    Return all entries in this chain — full chain always loaded.
        chain_roles: Filter by chain role — multi-select.
        q:           Free-text search against summary + detail fields.

    Pagination:
        before_ts:  Load entries older than this timestamp (scroll into past).
        after_ts:   Load entries newer than this timestamp (live refresh from top).
        limit:      Entries per page — default 50, max 200.

    Sort:
        sort_by:  Sort key — ts (default), severity, source, or status.
        sort_dir: Sort direction — desc (default) or asc.
    """

    # -- Filter axes (13)
    sources: list[Source] = field(default_factory=list)
    subtypes: list[str] = field(default_factory=list)
    statuses: list[EntryStatus] = field(default_factory=list)
    severities: list[Severity | None] = field(default_factory=list)
    locality: Locality | None = None
    envs: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    actors: list[Actor] = field(default_factory=list)
    date_from: float | None = None
    date_to: float | None = None
    chain_id: str | None = None
    chain_roles: list[ChainRole] = field(default_factory=list)
    q: str | None = None

    # -- Pagination
    before_ts: float | None = None
    after_ts: float | None = None
    limit: int = 50

    # -- Sort
    sort_by: SortBy = SortBy.TS
    sort_dir: SortDir = SortDir.DESC

    def __post_init__(self) -> None:
        if self.limit > 200:
            self.limit = 200
        if self.limit < 1:
            self.limit = 1


# ═══════════════════════════════════════════════════════════════════
#  TimelinePage — paginated API response envelope
# ═══════════════════════════════════════════════════════════════════


@dataclass
class TimelinePage:
    """A single page of timeline results returned by TimelineService.

    Attributes:
        entries:     The timeline entries for this page.
        has_more:    True if more entries exist beyond this page.
        next_cursor: ``ts`` of the oldest entry in this page — use as
                     ``before_ts`` to load the next (older) page.
        prev_cursor: ``ts`` of the newest entry in this page — use as
                     ``after_ts`` for live refresh from the top.
        total_hint:  Approximate total matching entries. Best-effort,
                     not guaranteed to be exact.
    """

    entries: list[TimelineEntry] = field(default_factory=list)
    has_more: bool = False
    next_cursor: float | None = None
    prev_cursor: float | None = None
    total_hint: int | None = None
    facets: dict[str, dict[str, int]] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict for API responses."""
        d: dict[str, Any] = {
            "entries": [e.to_dict() for e in self.entries],
            "has_more": self.has_more,
            "next_cursor": self.next_cursor,
            "prev_cursor": self.prev_cursor,
            "total_hint": self.total_hint,
        }
        if self.facets is not None:
            d["facets"] = self.facets
        return d
