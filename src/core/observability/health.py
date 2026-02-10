"""
Health checker — aggregate system health from components.

Reports the health of adapters, circuit breakers, retry queue,
and the overall system. Used by the CLI `health` command and
potentially a web endpoint.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.core.reliability.circuit_breaker import CircuitBreakerRegistry, CircuitState
from src.core.reliability.retry_queue import RetryQueue

logger = logging.getLogger(__name__)


@dataclass
class ComponentHealth:
    """Health of a single component."""

    name: str
    status: str = "unknown"  # healthy, degraded, unhealthy, unknown
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class SystemHealth:
    """Aggregate health of the entire system."""

    status: str = "healthy"
    timestamp: str = ""
    components: list[ComponentHealth] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()

    def add(self, component: ComponentHealth) -> None:
        self.components.append(component)
        self._recalculate()

    def _recalculate(self) -> None:
        """Recalculate overall status from components."""
        statuses = [c.status for c in self.components]
        if any(s == "unhealthy" for s in statuses):
            self.status = "unhealthy"
        elif any(s == "degraded" for s in statuses):
            self.status = "degraded"
        elif all(s == "healthy" for s in statuses):
            self.status = "healthy"
        else:
            self.status = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "timestamp": self.timestamp,
            "components": [c.to_dict() for c in self.components],
        }


def check_circuit_breakers(registry: CircuitBreakerRegistry) -> ComponentHealth:
    """Check the health of circuit breakers."""
    if not registry.breakers:
        return ComponentHealth(
            name="circuit_breakers",
            status="healthy",
            message="No circuit breakers registered",
        )

    open_count = sum(
        1 for cb in registry.breakers.values() if cb.state == CircuitState.OPEN
    )
    half_open_count = sum(
        1 for cb in registry.breakers.values() if cb.state == CircuitState.HALF_OPEN
    )
    total = len(registry.breakers)

    if open_count > 0:
        status = "unhealthy"
        message = f"{open_count}/{total} circuits open"
    elif half_open_count > 0:
        status = "degraded"
        message = f"{half_open_count}/{total} circuits half-open"
    else:
        status = "healthy"
        message = f"All {total} circuits closed"

    return ComponentHealth(
        name="circuit_breakers",
        status=status,
        message=message,
        details=registry.get_status(),
    )


def check_retry_queue(queue: RetryQueue) -> ComponentHealth:
    """Check the health of the retry queue."""
    status_data = queue.get_status()
    total = status_data["total"]
    exhausted = status_data["exhausted"]

    if exhausted > 0:
        status = "degraded"
        message = f"{exhausted} exhausted items, {total} total"
    elif total > 0:
        status = "healthy"
        message = f"{total} items pending retry"
    else:
        status = "healthy"
        message = "Queue empty"

    return ComponentHealth(
        name="retry_queue",
        status=status,
        message=message,
        details=status_data,
    )


def check_system_health(
    cb_registry: CircuitBreakerRegistry | None = None,
    retry_queue: RetryQueue | None = None,
) -> SystemHealth:
    """Run all health checks and return aggregate status."""
    health = SystemHealth()

    if cb_registry is not None:
        health.add(check_circuit_breakers(cb_registry))

    if retry_queue is not None:
        health.add(check_retry_queue(retry_queue))

    return health
