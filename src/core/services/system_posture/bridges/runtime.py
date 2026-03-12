"""
Runtime bridge — wraps circuit breaker and retry queue health.

The runtime pillar reflects the CURRENT state of in-memory
reliability components:
  - Circuit breakers (from ``CircuitBreakerRegistry``)
  - Retry queue (pending / exhausted items)

This data is always fresh (TTL=0 in cache) because it reflects
transient in-memory state, not on-disk data.

Unlike scanners, this module does NOT run subprocess calls — it
reads in-memory registries directly.
"""

from __future__ import annotations

import logging

from ..models import PillarResult, PostureItem, RankLevel

logger = logging.getLogger(__name__)


def bridge_runtime() -> PillarResult:
    """Bridge existing runtime health into posture format.

    Reads circuit breaker states and retry queue status from
    the observability layer.

    Returns:
        PillarResult with items for circuit breakers and retry queue.
        If no reliability components are registered, returns a
        healthy result with an informational message.
    """
    items: list[PostureItem] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    # ── Circuit breakers ────────────────────────────────────────
    cb_item = _check_circuit_breakers()
    if cb_item:
        items.append(cb_item)
        if cb_item.rank.severity >= RankLevel.OUTDATED.severity:
            warnings.append(f"Circuit breakers: {cb_item.detail}")
            recommendations.append("Check integration health — some circuits are open")

    # ── Retry queue ─────────────────────────────────────────────
    rq_item = _check_retry_queue()
    if rq_item:
        items.append(rq_item)
        if rq_item.rank.severity >= RankLevel.OUTDATED.severity:
            warnings.append(f"Retry queue: {rq_item.detail}")
            recommendations.append("Check retry queue — exhausted items need attention")

    # ── Assemble ────────────────────────────────────────────────
    if not items:
        return PillarResult(
            pillar="runtime",
            rank=RankLevel.CURRENT,
            items=[PostureItem(
                name="runtime",
                value="nominal",
                rank=RankLevel.CURRENT,
                detail="No reliability components active",
            )],
        )

    from ..ranking import worst_rank

    return PillarResult(
        pillar="runtime",
        rank=worst_rank(items),
        items=items,
        warnings=warnings,
        recommendations=recommendations,
    )


def _check_circuit_breakers() -> PostureItem | None:
    """Check circuit breaker registry state.

    Returns a PostureItem summarizing circuit breaker health,
    or None if the registry is not available.
    """
    try:
        from src.core.observability.health import (
            check_circuit_breakers,
        )
        from src.core.reliability.circuit_breaker import CircuitBreakerRegistry

        registry = CircuitBreakerRegistry()
        health = check_circuit_breakers(registry)

        rank = _status_to_rank(health.status)
        total = len(registry.breakers)

        return PostureItem(
            name="circuit_breakers",
            value=health.status,
            rank=rank,
            detail=health.message if total > 0 else "No circuits registered",
        )

    except Exception as exc:
        logger.debug("circuit breaker check failed: %s", exc)
        return None


def _check_retry_queue() -> PostureItem | None:
    """Check retry queue state.

    Returns a PostureItem summarizing retry queue health,
    or None if the queue is not available.
    """
    try:
        from src.core.context import get_project_root
        from src.core.observability.health import check_retry_queue
        from src.core.reliability.retry_queue import RetryQueue

        root = get_project_root()
        if not root:
            return None

        retry_path = root / "state" / "retry_queue.json"
        queue = RetryQueue(path=retry_path)
        health = check_retry_queue(queue)

        rank = _status_to_rank(health.status)

        return PostureItem(
            name="retry_queue",
            value=health.status,
            rank=rank,
            detail=health.message,
        )

    except Exception as exc:
        logger.debug("retry queue check failed: %s", exc)
        return None


def _status_to_rank(status: str) -> RankLevel:
    """Map ComponentHealth status to RankLevel.

    ComponentHealth uses: healthy, degraded, unhealthy, unknown.
    """
    return {
        "healthy": RankLevel.CURRENT,
        "degraded": RankLevel.OUTDATED,
        "unhealthy": RankLevel.DANGEROUS,
        "unknown": RankLevel.UNKNOWN,
    }.get(status, RankLevel.UNKNOWN)
