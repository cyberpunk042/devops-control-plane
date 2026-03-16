"""
Data models for system posture assessment.

Defines the ranking levels, individual item assessments,
pillar-level results, and the aggregate system posture.

Follows the project's existing patterns:
  - ``StrEnum`` for string enums (matches ``CircuitState``)
  - ``@dataclass`` with ``to_dict()`` (matches ``ComponentHealth``)
  - ``datetime.now(UTC).isoformat()`` for timestamps
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# ── Rank levels ─────────────────────────────────────────────────


class RankLevel(StrEnum):
    """Deprecation rank for a system component.

    Ordered from best to worst.  The overall rank of a pillar
    (or the entire system) is the WORST rank among its items.

    Values::

        CURRENT    → 🟢  Up to date, fully supported
        AGING      → 🔵  Supported but approaching end-of-life
        OUTDATED   → 🟡  Past EOL < 1 year, likely still works
        DEPRECATED → 🟠  Past EOL > 1 year, expect breakage
        DANGEROUS  → 🔴  Known CVEs, critical risk
        UNKNOWN    → ⚪  Cannot determine version/status
        NA         → —   Not applicable (not installed, not configured)
    """

    CURRENT = "current"
    AGING = "aging"
    OUTDATED = "outdated"
    DEPRECATED = "deprecated"
    DANGEROUS = "dangerous"
    UNKNOWN = "unknown"
    NA = "na"

    @property
    def severity(self) -> int:
        """Numeric severity for comparison.  Higher = worse."""
        return _SEVERITY[self]

    @property
    def emoji(self) -> str:
        """Emoji indicator for this rank."""
        return _EMOJI[self]

    @property
    def css_class(self) -> str:
        """CSS status-badge class for this rank.

        Maps to the existing badge classes used throughout the UI:
        ``ok``, ``degraded``, ``failed``, or empty for neutral.
        """
        return _CSS_CLASS[self]


_SEVERITY: dict[RankLevel, int] = {
    RankLevel.NA: -1,
    RankLevel.UNKNOWN: 0,
    RankLevel.CURRENT: 1,
    RankLevel.AGING: 2,
    RankLevel.OUTDATED: 3,
    RankLevel.DEPRECATED: 4,
    RankLevel.DANGEROUS: 5,
}

_EMOJI: dict[RankLevel, str] = {
    RankLevel.CURRENT: "🟢",
    RankLevel.AGING: "🔵",
    RankLevel.OUTDATED: "🟡",
    RankLevel.DEPRECATED: "🟠",
    RankLevel.DANGEROUS: "🔴",
    RankLevel.UNKNOWN: "⚪",
    RankLevel.NA: "—",
}

_CSS_CLASS: dict[RankLevel, str] = {
    RankLevel.CURRENT: "ok",
    RankLevel.AGING: "ok",
    RankLevel.OUTDATED: "degraded",
    RankLevel.DEPRECATED: "failed",
    RankLevel.DANGEROUS: "failed",
    RankLevel.UNKNOWN: "",
    RankLevel.NA: "",
}


# ── Data models ─────────────────────────────────────────────────


@dataclass
class PostureItem:
    """A single assessed component (e.g. "Ubuntu 22.04" or "kubectl 1.24").

    Attributes:
        name:             Display name — "Ubuntu", "kubectl", "glibc".
        value:            Detected value — "22.04", "1.24.0", "2.35".
        rank:             Computed deprecation rank.
        detail:           Human note — "EOL April 2027", "7 minor behind".
        current_version:  Latest known version (tools only).
        eol_date:         End-of-life date if known (YYYY-MM format).
        cves:             Known CVE identifiers for this version.
    """

    name: str
    value: str
    rank: RankLevel
    detail: str = ""
    current_version: str = ""
    eol_date: str = ""
    cves: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict.

        Only includes optional fields when they have values,
        keeping the response payload compact.
        """
        d: dict[str, Any] = {
            "name": self.name,
            "value": self.value,
            "rank": self.rank.value,
            "rank_emoji": self.rank.emoji,
            "detail": self.detail,
        }
        if self.current_version:
            d["current_version"] = self.current_version
        if self.eol_date:
            d["eol_date"] = self.eol_date
        if self.cves:
            d["cves"] = self.cves
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PostureItem:
        """Deserialize from a dict (e.g. loaded from cache file)."""
        return cls(
            name=d.get("name", ""),
            value=d.get("value", ""),
            rank=RankLevel(d.get("rank", "unknown")),
            detail=d.get("detail", ""),
            current_version=d.get("current_version", ""),
            eol_date=d.get("eol_date", ""),
            cves=d.get("cves", []),
        )


@dataclass
class PillarResult:
    """Assessment result for one of the four pillars.

    Attributes:
        pillar:           Pillar key — "platform", "toolchain", "project", "runtime".
        rank:             Worst rank across all items in this pillar.
        items:            Individual component assessments.
        warnings:         Human-readable warning messages.
        recommendations:  Actionable suggestions for improvement.
    """

    pillar: str
    rank: RankLevel
    items: list[PostureItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pillar": self.pillar,
            "rank": self.rank.value,
            "rank_emoji": self.rank.emoji,
            "css_class": self.rank.css_class,
            "items": [i.to_dict() for i in self.items],
            "warnings": self.warnings,
            "recommendations": self.recommendations,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PillarResult:
        """Deserialize from a dict (e.g. loaded from cache file)."""
        return cls(
            pillar=d.get("pillar", ""),
            rank=RankLevel(d.get("rank", "unknown")),
            items=[PostureItem.from_dict(i) for i in d.get("items", [])],
            warnings=d.get("warnings", []),
            recommendations=d.get("recommendations", []),
        )


@dataclass
class SystemPosture:
    """Full system posture assessment across all four pillars.

    Attributes:
        overall_rank:     Worst rank across all pillars.
        overall_status:   Human label — "healthy", "attention", "degraded", "unhealthy".
        timestamp:        ISO timestamp of when this assessment was computed.
        pillars:          Per-pillar results keyed by pillar name.
        summary:          One-line human summary of findings.
        scan_duration_ms: Time taken for the full scan in milliseconds.
    """

    overall_rank: RankLevel = RankLevel.UNKNOWN
    overall_status: str = "unknown"
    timestamp: str = ""
    pillars: dict[str, PillarResult] = field(default_factory=dict)
    summary: str = ""
    scan_duration_ms: int = 0

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()

    def recompute_overall(self) -> None:
        """Recalculate overall_rank and overall_status from pillar ranks.

        The overall rank is the WORST rank across all pillars
        (excluding NA and UNKNOWN).  The overall status is a
        human-friendly label mapped from the rank.
        """
        if not self.pillars:
            self.overall_rank = RankLevel.UNKNOWN
            self.overall_status = "unknown"
            return

        # Ensure pillars are PillarResult objects (disk hydration may leave dicts)
        for key, val in list(self.pillars.items()):
            if isinstance(val, dict):
                self.pillars[key] = PillarResult.from_dict(val)

        scoreable = [
            p.rank for p in self.pillars.values()
            if p.rank not in (RankLevel.NA, RankLevel.UNKNOWN)
        ]
        if not scoreable:
            self.overall_rank = RankLevel.UNKNOWN
            self.overall_status = "unknown"
            return

        self.overall_rank = max(scoreable, key=lambda r: r.severity)
        self.overall_status = _STATUS_MAP.get(self.overall_rank, "unknown")

        # Build one-line summary
        parts: list[str] = []
        for p in self.pillars.values():
            n_warn = len(p.warnings)
            if n_warn:
                label = p.pillar
                parts.append(
                    f"{n_warn} {label} warning{'s' if n_warn != 1 else ''}"
                )
        self.summary = " · ".join(parts) if parts else "All systems nominal"

    def to_dict(self) -> dict[str, Any]:
        """Full serialization — used by ``GET /api/posture``."""
        return {
            "overall_rank": self.overall_rank.value,
            "overall_status": self.overall_status,
            "overall_css_class": self.overall_rank.css_class,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "scan_duration_ms": self.scan_duration_ms,
            "pillars": {k: v.to_dict() for k, v in self.pillars.items()},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SystemPosture:
        """Deserialize from a dict (e.g. loaded from cache file)."""
        return cls(
            overall_rank=RankLevel(d.get("overall_rank", "unknown")),
            overall_status=d.get("overall_status", "unknown"),
            timestamp=d.get("timestamp", ""),
            pillars={
                k: PillarResult.from_dict(v)
                for k, v in d.get("pillars", {}).items()
            },
            summary=d.get("summary", ""),
            scan_duration_ms=d.get("scan_duration_ms", 0),
        )

    def to_summary_dict(self) -> dict[str, Any]:
        """Lightweight summary — used by ``GET /api/posture/summary``.

        Returns only the overall status and per-pillar ranks,
        without individual item details.  Fast for the nav badge.
        """
        return {
            "overall_rank": self.overall_rank.value,
            "overall_status": self.overall_status,
            "overall_css_class": self.overall_rank.css_class,
            "summary": self.summary,
            "timestamp": self.timestamp,
            "pillar_ranks": {
                k: {
                    "rank": v.rank.value,
                    "rank_emoji": v.rank.emoji,
                    "css_class": v.rank.css_class,
                }
                for k, v in self.pillars.items()
            },
        }


# ── Status mapping ──────────────────────────────────────────────

_STATUS_MAP: dict[RankLevel, str] = {
    RankLevel.CURRENT: "healthy",
    RankLevel.AGING: "healthy",
    RankLevel.OUTDATED: "attention",
    RankLevel.DEPRECATED: "degraded",
    RankLevel.DANGEROUS: "unhealthy",
    RankLevel.UNKNOWN: "unknown",
}
