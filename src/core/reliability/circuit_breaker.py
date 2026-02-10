"""
Circuit breaker — protect adapters from cascading failures.

States:
    CLOSED  → Normal operation. Failures counted.
    OPEN    → All calls rejected. Timer running.
    HALF_OPEN → One probe call allowed to test recovery.

Transitions:
    CLOSED → OPEN:     failure_count >= threshold
    OPEN → HALF_OPEN:  recovery_timeout elapsed
    HALF_OPEN → CLOSED: probe succeeds
    HALF_OPEN → OPEN:   probe fails
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(StrEnum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Per-adapter circuit breaker.

    Args:
        name: Identifier (typically the adapter name).
        failure_threshold: Failures before opening the circuit.
        recovery_timeout: Seconds before trying a probe call.
        success_threshold: Consecutive successes needed to close from half-open.
    """

    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    success_threshold: int = 1

    # ── Internal state ───────────────────────────────────────────
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    last_state_change: float = field(default_factory=time.monotonic)
    total_rejections: int = 0

    def allow_request(self) -> bool:
        """Check if a request is allowed through the circuit.

        Returns:
            True if the request should proceed, False if rejected.
        """
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            elapsed = time.monotonic() - self.last_failure_time
            if elapsed >= self.recovery_timeout:
                self._transition(CircuitState.HALF_OPEN)
                return True
            self.total_rejections += 1
            return False

        # HALF_OPEN: allow one probe call
        return self.state == CircuitState.HALF_OPEN

    def record_success(self) -> None:
        """Record a successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self._transition(CircuitState.CLOSED)
        elif self.state == CircuitState.CLOSED:
            # Reset consecutive failure count on success
            self.failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self.last_failure_time = time.monotonic()

        if self.state == CircuitState.HALF_OPEN:
            # Probe failed — back to open
            self.success_count = 0
            self._transition(CircuitState.OPEN)
        elif self.state == CircuitState.CLOSED:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self._transition(CircuitState.OPEN)

    def reset(self) -> None:
        """Force-reset the circuit breaker to closed state."""
        self._transition(CircuitState.CLOSED)
        self.failure_count = 0
        self.success_count = 0
        self.total_rejections = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the circuit breaker state."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "total_rejections": self.total_rejections,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }

    def _transition(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old = self.state
        self.state = new_state
        self.last_state_change = time.monotonic()
        if new_state == CircuitState.CLOSED:
            self.failure_count = 0
            self.success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self.success_count = 0
        logger.info(
            "Circuit breaker '%s': %s → %s",
            self.name,
            old.value,
            new_state.value,
        )


@dataclass
class CircuitBreakerRegistry:
    """Manages circuit breakers for all adapters."""

    breakers: dict[str, CircuitBreaker] = field(default_factory=dict)
    default_threshold: int = 5
    default_timeout: float = 30.0

    def get_or_create(self, name: str) -> CircuitBreaker:
        """Get or create a circuit breaker for the named adapter."""
        if name not in self.breakers:
            self.breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=self.default_threshold,
                recovery_timeout=self.default_timeout,
            )
        return self.breakers[name]

    def get_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all circuit breakers."""
        return {name: cb.to_dict() for name, cb in self.breakers.items()}

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for cb in self.breakers.values():
            cb.reset()
