"""
Timeline API route handlers.

Routes registered on timeline_bp.

All routes are thin: parse query params → build TimelineQuery → call service → return JSON.
No business logic here.
"""

from __future__ import annotations

import logging

from flask import jsonify, request

from src.core.services.timeline.models import (
    Actor,
    ChainRole,
    EntryStatus,
    Locality,
    Severity,
    SortBy,
    SortDir,
    Source,
    TimelineQuery,
)
from src.core.services.timeline.service import TimelineService

from . import timeline_bp

logger = logging.getLogger(__name__)

_service = TimelineService()


# ── Helpers ──────────────────────────────────────────────────────────

def _get_list(key: str) -> list[str]:
    """Extract a multi-value query param (key[] or key)."""
    values = request.args.getlist(f"{key}[]") or request.args.getlist(key)
    return [v.strip() for v in values if v.strip()]


def _parse_float(key: str) -> float | None:
    raw = request.args.get(key)
    if raw is None:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def _parse_int(key: str, default: int) -> int:
    raw = request.args.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


def _parse_sources() -> list[Source]:
    raws = _get_list("source")
    result = []
    for r in raws:
        try:
            result.append(Source(r.lower()))
        except ValueError:
            pass
    return result


def _parse_statuses() -> list[EntryStatus]:
    raws = _get_list("status")
    result = []
    for r in raws:
        try:
            result.append(EntryStatus(r.lower()))
        except ValueError:
            pass
    return result


def _parse_severities() -> list[Severity | None]:
    raws = _get_list("severity")
    result: list[Severity | None] = []
    for r in raws:
        if r.lower() == "none":
            result.append(None)
        else:
            try:
                result.append(Severity(r.lower()))
            except ValueError:
                pass
    return result


def _parse_actors() -> list[Actor]:
    raws = _get_list("actor")
    result = []
    for r in raws:
        try:
            result.append(Actor(r.lower()))
        except ValueError:
            pass
    return result


def _parse_chain_roles() -> list[ChainRole]:
    raws = _get_list("chain_role")
    result = []
    for r in raws:
        try:
            result.append(ChainRole(r.lower()))
        except ValueError:
            pass
    return result


def _parse_locality() -> Locality | None:
    raw = request.args.get("locality")
    if not raw:
        return None
    try:
        return Locality(raw.lower())
    except ValueError:
        return None


def _parse_sort_by() -> SortBy:
    raw = request.args.get("sort_by", "ts")
    try:
        return SortBy(raw.lower())
    except ValueError:
        return SortBy.TS


def _parse_sort_dir() -> SortDir:
    raw = request.args.get("sort_dir", "desc")
    try:
        return SortDir(raw.lower())
    except ValueError:
        return SortDir.DESC


def _build_query() -> TimelineQuery:
    return TimelineQuery(
        sources=_parse_sources(),
        subtypes=_get_list("subtype"),
        statuses=_parse_statuses(),
        severities=_parse_severities(),
        locality=_parse_locality(),
        envs=_get_list("env"),
        modules=_get_list("module"),
        actors=_parse_actors(),
        date_from=_parse_float("date_from"),
        date_to=_parse_float("date_to"),
        chain_id=request.args.get("chain_id") or None,
        chain_roles=_parse_chain_roles(),
        q=request.args.get("q") or None,
        before_ts=_parse_float("before_ts"),
        after_ts=_parse_float("after_ts"),
        limit=_parse_int("limit", 50),
        sort_by=_parse_sort_by(),
        sort_dir=_parse_sort_dir(),
    )


# ── Routes ───────────────────────────────────────────────────────────

@timeline_bp.get("/timeline")
def timeline_query():
    """GET /api/timeline — paginated timeline query.

    Query params: see TimelineQuery fields.
    Returns: TimelinePage JSON.
    """
    try:
        q = _build_query()
        page = _service.query(q)
        return jsonify(page.to_dict())
    except Exception as exc:
        logger.exception("timeline: query error")
        return jsonify({"error": str(exc)}), 500


@timeline_bp.get("/timeline/data")
def timeline_data():
    """GET /api/timeline/data — full aggregate (entries + facets + chains + calendar).

    This is the primary data endpoint for the timeline UI.
    Returns the timeline.data mediator node — single source of truth.
    Fallback for cold start when __INITIAL_STATE__ is not populated.
    """
    try:
        data = _service.data()
        return jsonify(data)
    except Exception as exc:
        logger.exception("timeline: data error")
        return jsonify({"error": str(exc)}), 500


@timeline_bp.get("/timeline/chains")
def timeline_chains():
    """GET /api/timeline/chains — chain summaries for left navigator.

    Returns: list of chain dicts sorted by last_ts desc.
    Reads from timeline.data aggregate.
    """
    try:
        data = _service.data()
        return jsonify({"chains": data.get("chains", [])})
    except Exception as exc:
        logger.exception("timeline: chains error")
        return jsonify({"error": str(exc)}), 500


@timeline_bp.get("/timeline/domains")
def timeline_domains():
    """GET /api/timeline/domains — per-source entry counts.

    Returns: dict of source_value → count.
    Reads from timeline.data aggregate facets.
    """
    try:
        data = _service.data()
        return jsonify({"domains": data.get("facets", {}).get("by_source", {})})
    except Exception as exc:
        logger.exception("timeline: domains error")
        return jsonify({"error": str(exc)}), 500


@timeline_bp.get("/timeline/calendar")
def timeline_calendar():
    """GET /api/timeline/calendar — per-day entry counts for Calendar mode.

    Returns: list of {date, count, has_failure} sorted by date desc.
    Reads from timeline.data aggregate.
    """
    try:
        data = _service.data()
        return jsonify({"days": data.get("calendar", [])})
    except Exception as exc:
        logger.exception("timeline: calendar error")
        return jsonify({"error": str(exc)}), 500


@timeline_bp.get("/timeline/stats")
def timeline_stats():
    """GET /api/timeline/stats — aggregate counts.

    Returns: facets from timeline.data aggregate.
    """
    try:
        data = _service.data()
        facets = data.get("facets", {})
        return jsonify({
            "total": sum(facets.get("by_source", {}).values()),
            **facets,
        })
    except Exception as exc:
        logger.exception("timeline: stats error")
        return jsonify({"error": str(exc)}), 500
