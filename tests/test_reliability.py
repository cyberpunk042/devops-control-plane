"""
Tests for reliability — circuit breaker + retry queue.
"""

import time
from pathlib import Path

from src.core.reliability.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitState,
)
from src.core.reliability.retry_queue import RetryItem, RetryQueue

# ── Circuit Breaker State Machine ────────────────────────────────────


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        cb = CircuitBreaker(name="test")
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request()

    def test_closed_allows_requests(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        assert cb.allow_request()
        cb.record_failure()
        assert cb.allow_request()  # still closed, under threshold

    def test_transitions_to_open_after_threshold(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()  # 3rd failure
        assert cb.state == CircuitState.OPEN

    def test_open_rejects_requests(self):
        cb = CircuitBreaker(name="test", failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert not cb.allow_request()
        assert cb.total_rejections == 1

    def test_open_to_half_open_after_timeout(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.05)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.06)
        assert cb.allow_request()  # triggers HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_to_closed_on_success(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        cb.allow_request()  # → HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_half_open_to_open_on_failure(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        cb.allow_request()  # → HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2
        cb.record_success()
        assert cb.failure_count == 0

    def test_success_threshold(self):
        cb = CircuitBreaker(
            name="test", failure_threshold=1, recovery_timeout=0.01, success_threshold=2
        )
        cb.record_failure()
        time.sleep(0.02)
        cb.allow_request()  # → HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN  # need 2 successes
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_reset(self):
        cb = CircuitBreaker(name="test", failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_to_dict(self):
        cb = CircuitBreaker(name="shell", failure_threshold=5)
        cb.record_failure()
        d = cb.to_dict()
        assert d["name"] == "shell"
        assert d["state"] == "closed"
        assert d["failure_count"] == 1


# ── Circuit Breaker Registry ────────────────────────────────────────


class TestCircuitBreakerRegistry:
    def test_get_or_create(self):
        reg = CircuitBreakerRegistry()
        cb1 = reg.get_or_create("shell")
        cb2 = reg.get_or_create("shell")
        assert cb1 is cb2  # same object

    def test_different_adapters_different_breakers(self):
        reg = CircuitBreakerRegistry()
        cb1 = reg.get_or_create("shell")
        cb2 = reg.get_or_create("docker")
        assert cb1 is not cb2

    def test_uses_defaults(self):
        reg = CircuitBreakerRegistry(default_threshold=10, default_timeout=60.0)
        cb = reg.get_or_create("shell")
        assert cb.failure_threshold == 10
        assert cb.recovery_timeout == 60.0

    def test_get_status(self):
        reg = CircuitBreakerRegistry()
        reg.get_or_create("shell")
        reg.get_or_create("docker")
        status = reg.get_status()
        assert "shell" in status
        assert "docker" in status

    def test_reset_all(self):
        reg = CircuitBreakerRegistry(default_threshold=1)
        cb = reg.get_or_create("shell")
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        reg.reset_all()
        assert cb.state == CircuitState.CLOSED


# ── Retry Item ───────────────────────────────────────────────────────


class TestRetryItem:
    def test_initial_state(self):
        item = RetryItem(id="r1", action_id="a1", adapter="shell")
        assert item.attempt == 0
        assert not item.exhausted

    def test_exhaustion(self):
        item = RetryItem(id="r1", action_id="a1", adapter="shell", max_attempts=2)
        item.attempt = 2
        assert item.exhausted

    def test_schedule_retry_backoff(self):
        item = RetryItem(id="r1", action_id="a1", adapter="shell")
        t_before = time.time()
        item.schedule_retry(base_delay=0.01, max_delay=60.0)
        assert item.attempt == 1
        assert item.next_retry_at >= t_before

    def test_roundtrip(self):
        item = RetryItem(id="r1", action_id="a1", adapter="shell", last_error="fail")
        d = item.to_dict()
        restored = RetryItem.from_dict(d)
        assert restored.id == "r1"
        assert restored.last_error == "fail"


# ── Retry Queue ──────────────────────────────────────────────────────


class TestRetryQueue:
    def test_enqueue(self):
        q = RetryQueue(max_attempts=3, base_delay=0.001)
        item = q.enqueue("r1", action_id="a1", adapter="shell", error="fail")
        assert q.size == 1
        assert item.attempt == 1

    def test_enqueue_existing_increments(self):
        q = RetryQueue(max_attempts=3, base_delay=0.001)
        q.enqueue("r1", action_id="a1", adapter="shell", error="fail")
        q.enqueue("r1", action_id="a1", adapter="shell", error="fail again")
        assert q.size == 1  # still one item

    def test_dequeue_ready(self):
        q = RetryQueue(max_attempts=3, base_delay=0.001, max_delay=0.001)
        q.enqueue("r1", action_id="a1", adapter="shell")
        time.sleep(0.01)  # wait for it to become ready
        ready = q.dequeue_ready()
        assert len(ready) == 1

    def test_complete_removes_item(self):
        q = RetryQueue(max_attempts=3, base_delay=0.001)
        q.enqueue("r1", action_id="a1", adapter="shell")
        q.complete("r1")
        assert q.size == 0

    def test_fail_schedules_next(self):
        q = RetryQueue(max_attempts=3, base_delay=0.001)
        q.enqueue("r1", action_id="a1", adapter="shell")
        item = q.fail("r1", error="still failing")
        assert item is not None
        assert item.last_error == "still failing"

    def test_remove_exhausted(self):
        q = RetryQueue(max_attempts=1, base_delay=0.001)
        q.enqueue("r1", action_id="a1", adapter="shell")  # attempt → 1 = max
        exhausted = q.remove_exhausted()
        assert len(exhausted) == 1
        assert q.size == 0

    def test_clear(self):
        q = RetryQueue(max_attempts=3, base_delay=0.001)
        q.enqueue("r1", action_id="a1", adapter="shell")
        q.enqueue("r2", action_id="a2", adapter="shell")
        q.clear()
        assert q.size == 0

    def test_get_status(self):
        q = RetryQueue(max_attempts=3, base_delay=0.001)
        q.enqueue("r1", action_id="a1", adapter="shell")
        status = q.get_status()
        assert status["total"] == 1
        assert isinstance(status["items"], list)

    def test_persistence(self, tmp_path: Path):
        path = tmp_path / "retry.json"
        q1 = RetryQueue(path=path, max_attempts=3, base_delay=0.001)
        q1.enqueue("r1", action_id="a1", adapter="shell", error="fail")
        assert path.is_file()

        # Load from disk
        q2 = RetryQueue(path=path, max_attempts=3, base_delay=0.001)
        assert q2.size == 1

    def test_persistence_survives_restart(self, tmp_path: Path):
        path = tmp_path / "retry.json"
        q1 = RetryQueue(path=path, max_attempts=3, base_delay=0.001)
        q1.enqueue("r1", action_id="a1", adapter="shell")
        q1.enqueue("r2", action_id="a2", adapter="docker")

        # Simulate restart
        q2 = RetryQueue(path=path, max_attempts=3, base_delay=0.001)
        assert q2.size == 2

    def test_fail_nonexistent(self):
        q = RetryQueue(max_attempts=3, base_delay=0.001)
        result = q.fail("nonexistent")
        assert result is None
