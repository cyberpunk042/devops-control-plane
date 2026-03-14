"""Tests for WorkQueue — priority queue with weighted semaphore.

Tests cover:
    - Priority ordering (CRITICAL > HIGH > NORMAL > LOW > IDLE)
    - Size-based capacity admission (WeightedSemaphore)
    - Batch completion tracking with on_complete callbacks
    - Web request yield signaling
    - submit_and_wait synchronous mode
    - Shutdown and poison-pill exit
    - Diagnostic snapshot
"""

from __future__ import annotations

import threading
import time

import pytest

from src.core.services.mediator.work_queue import (
    Priority,
    WeightedSemaphore,
    WorkItem,
    WorkQueue,
    current_yield_check,
)


# ── WeightedSemaphore ──────────────────────────────────────────────


class TestWeightedSemaphore:
    """Unit tests for capacity-based admission control."""

    def test_acquire_release(self) -> None:
        """Basic acquire/release cycle."""
        sem = WeightedSemaphore(capacity=4)
        assert sem.available == 4
        assert sem.used == 0

        assert sem.acquire(2) is True
        assert sem.available == 2
        assert sem.used == 2

        sem.release(2)
        assert sem.available == 4
        assert sem.used == 0

    def test_acquire_blocks_when_full(self) -> None:
        """acquire blocks when insufficient capacity."""
        sem = WeightedSemaphore(capacity=2)
        sem.acquire(2)
        # Should timeout because no capacity available
        assert sem.acquire(1, timeout=0.05) is False

    def test_acquire_unblocks_on_release(self) -> None:
        """acquire unblocks when capacity is released."""
        sem = WeightedSemaphore(capacity=2)
        sem.acquire(2)

        released = threading.Event()
        acquired = threading.Event()

        def releaser():
            released.wait()
            sem.release(2)

        def acquirer():
            assert sem.acquire(1, timeout=2.0) is True
            acquired.set()

        t1 = threading.Thread(target=releaser)
        t2 = threading.Thread(target=acquirer)
        t1.start()
        t2.start()

        released.set()
        acquired.wait(timeout=2.0)

        assert acquired.is_set()
        t1.join(timeout=1)
        t2.join(timeout=1)

    def test_force_acquire_overcapacity(self) -> None:
        """force_acquire allows temporary over-capacity."""
        sem = WeightedSemaphore(capacity=2)
        sem.acquire(2)
        sem.force_acquire(3)
        # Now at 5/2 — over capacity
        assert sem.used == 5
        assert sem.available == -3  # negative

    def test_release_clamps(self) -> None:
        """release cannot go below 0 used."""
        sem = WeightedSemaphore(capacity=4)
        sem.acquire(1)
        sem.release(5)  # more than acquired — should clamp
        assert sem.used == 0

    def test_invalid_capacity_raises(self) -> None:
        """capacity < 1 raises ValueError."""
        with pytest.raises(ValueError, match="capacity"):
            WeightedSemaphore(capacity=0)

    def test_invalid_weight_raises(self) -> None:
        """weight < 1 raises ValueError."""
        sem = WeightedSemaphore(capacity=4)
        with pytest.raises(ValueError, match="weight"):
            sem.acquire(0)


# ── Priority ordering ──────────────────────────────────────────────


class TestPriority:
    """Test that priority levels sort correctly."""

    def test_ordering(self) -> None:
        """Lower number = higher priority."""
        assert Priority.CRITICAL < Priority.HIGH
        assert Priority.HIGH < Priority.NORMAL
        assert Priority.NORMAL < Priority.LOW
        assert Priority.LOW < Priority.IDLE

    def test_work_item_comparison(self) -> None:
        """WorkItems sort by priority, then sequence."""
        a = WorkItem(priority=Priority.IDLE, size=1, path="a", resolver=lambda: 1, seq=1)
        b = WorkItem(priority=Priority.CRITICAL, size=1, path="b", resolver=lambda: 2, seq=2)
        c = WorkItem(priority=Priority.IDLE, size=1, path="c", resolver=lambda: 3, seq=3)

        assert b < a   # CRITICAL < IDLE
        assert a < c   # same priority, lower seq


# ── WorkQueue ──────────────────────────────────────────────────────


class TestWorkQueue:
    """Integration tests for the priority work queue."""

    def test_submit_and_callback(self) -> None:
        """Submitted item is executed and callback fires."""
        wq = WorkQueue(num_workers=1, capacity=4)

        result_box: dict = {}
        done = threading.Event()

        def on_result(val):
            result_box["value"] = val
            done.set()

        wq.submit(WorkItem(
            priority=Priority.NORMAL,
            size=1,
            path="test.simple",
            resolver=lambda: 42,
            callback=on_result,
        ))

        done.wait(timeout=5.0)
        wq.shutdown(wait=True)

        assert result_box.get("value") == 42

    def test_priority_ordering(self) -> None:
        """Higher priority items execute first."""
        wq = WorkQueue(num_workers=1, capacity=6)

        # Block the single worker with a gate
        gate = threading.Event()
        order: list[str] = []
        lock = threading.Lock()
        done = threading.Event()

        def blocking_resolver():
            gate.wait(timeout=5.0)
            return "gate"

        def make_resolver(name):
            def resolver():
                with lock:
                    order.append(name)
                return name
            return resolver

        # Submit blocker first to hold the worker
        wq.submit(WorkItem(
            priority=Priority.CRITICAL,
            size=1,
            path="blocker",
            resolver=blocking_resolver,
        ))
        time.sleep(0.05)  # let worker pick up blocker

        # Queue items at different priorities (all queued while worker is busy)
        wq.submit(WorkItem(
            priority=Priority.IDLE,
            size=1,
            path="idle",
            resolver=make_resolver("idle"),
        ))
        wq.submit(WorkItem(
            priority=Priority.HIGH,
            size=1,
            path="high",
            resolver=make_resolver("high"),
        ))
        wq.submit(WorkItem(
            priority=Priority.LOW,
            size=1,
            path="low",
            resolver=make_resolver("low"),
        ))

        # Release the gate
        gate.set()
        time.sleep(0.3)  # let queue drain

        wq.shutdown(wait=True)

        # Order should be: high → low → idle (priority ordering)
        assert order == ["high", "low", "idle"]

    def test_submit_and_wait(self) -> None:
        """submit_and_wait blocks until result is available."""
        wq = WorkQueue(num_workers=2, capacity=4)

        result = wq.submit_and_wait(WorkItem(
            priority=Priority.NORMAL,
            size=1,
            path="test.sync",
            resolver=lambda: "sync-result",
        ), timeout=5.0)

        assert result == "sync-result"
        wq.shutdown(wait=True)

    def test_submit_and_wait_error(self) -> None:
        """submit_and_wait raises on resolver failure."""
        wq = WorkQueue(num_workers=1, capacity=4)

        def failing():
            raise ValueError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            wq.submit_and_wait(WorkItem(
                priority=Priority.NORMAL,
                size=1,
                path="test.fail",
                resolver=failing,
            ), timeout=5.0)

        wq.shutdown(wait=True)

    def test_batch_on_complete(self) -> None:
        """Batch completion callback fires when all items complete."""
        wq = WorkQueue(num_workers=2, capacity=4)

        completed = threading.Event()
        results: list[str] = []
        lock = threading.Lock()

        def make_resolver(name):
            def resolver():
                with lock:
                    results.append(name)
                return name
            return resolver

        def on_batch_complete():
            completed.set()

        wq.submit_batch(
            items=[
                WorkItem(priority=Priority.NORMAL, size=1, path="b.1",
                         resolver=make_resolver("item1")),
                WorkItem(priority=Priority.NORMAL, size=1, path="b.2",
                         resolver=make_resolver("item2")),
                WorkItem(priority=Priority.NORMAL, size=1, path="b.3",
                         resolver=make_resolver("item3")),
            ],
            on_complete=on_batch_complete,
        )

        completed.wait(timeout=5.0)
        wq.shutdown(wait=True)

        assert completed.is_set()
        assert sorted(results) == ["item1", "item2", "item3"]

    def test_empty_batch_fires_immediately(self) -> None:
        """Empty batch fires on_complete immediately."""
        wq = WorkQueue(num_workers=1, capacity=4)

        fired = threading.Event()
        wq.submit_batch(items=[], on_complete=fired.set)

        assert fired.is_set()
        wq.shutdown(wait=True)


# ── Yield flag ─────────────────────────────────────────────────────


class TestYieldFlag:
    """Test cooperative yielding via web request signaling."""

    def test_yield_flag_lifecycle(self) -> None:
        """Yield flag follows begin/end_web_request."""
        wq = WorkQueue(num_workers=1, capacity=4)

        assert wq.should_yield() is False

        wq.begin_web_request()
        assert wq.should_yield() is True
        assert wq.web_requests_active == 1

        wq.begin_web_request()
        assert wq.web_requests_active == 2

        wq.end_web_request()
        assert wq.should_yield() is True  # still 1 active
        assert wq.web_requests_active == 1

        wq.end_web_request()
        assert wq.should_yield() is False
        assert wq.web_requests_active == 0

        wq.shutdown(wait=True)

    def test_current_yield_check_outside_worker(self) -> None:
        """current_yield_check returns False outside worker thread."""
        assert current_yield_check() is False

    def test_current_yield_check_inside_worker(self) -> None:
        """current_yield_check returns True inside worker when flag set."""
        wq = WorkQueue(num_workers=1, capacity=4)

        yield_results: list[bool] = []
        done = threading.Event()

        def resolver():
            # Inside worker thread — yield_check is set
            wq.begin_web_request()  # set the flag
            yield_results.append(current_yield_check())
            wq.end_web_request()
            yield_results.append(current_yield_check())
            done.set()
            return "ok"

        wq.submit(WorkItem(
            priority=Priority.NORMAL,
            size=1,
            path="test.yield",
            resolver=resolver,
        ))

        done.wait(timeout=5.0)
        wq.shutdown(wait=True)

        assert yield_results == [True, False]


# ── Diagnostics ────────────────────────────────────────────────────


class TestDiagnostics:
    """Test diagnostic snapshot."""

    def test_diag_keys(self) -> None:
        """diag() returns all expected keys."""
        wq = WorkQueue(num_workers=1, capacity=6)

        info = wq.diag()
        assert "pending" in info
        assert "semaphore_capacity" in info
        assert "semaphore_used" in info
        assert "semaphore_available" in info
        assert "web_requests_active" in info
        assert "yield_flag" in info
        assert "workers" in info
        assert "shutdown" in info
        assert "active_groups" in info

        assert info["semaphore_capacity"] == 6
        assert info["workers"] == 1
        assert info["shutdown"] is False

        wq.shutdown(wait=True)


# ── Shutdown ───────────────────────────────────────────────────────


class TestShutdown:
    """Test graceful shutdown."""

    def test_shutdown_rejects_new(self) -> None:
        """After shutdown, submit raises RuntimeError."""
        wq = WorkQueue(num_workers=1, capacity=4)
        wq.shutdown(wait=True)

        with pytest.raises(RuntimeError, match="shut down"):
            wq.submit(WorkItem(
                priority=Priority.NORMAL,
                size=1,
                path="test.rejected",
                resolver=lambda: 1,
            ))

    def test_shutdown_drains(self) -> None:
        """Shutdown waits for in-flight items to complete."""
        wq = WorkQueue(num_workers=2, capacity=4)

        results: list[int] = []
        lock = threading.Lock()

        for i in range(5):
            def make_r(n):
                def resolver():
                    time.sleep(0.02)
                    with lock:
                        results.append(n)
                    return n
                return resolver

            wq.submit(WorkItem(
                priority=Priority.NORMAL,
                size=1,
                path=f"test.drain.{i}",
                resolver=make_r(i),
            ))

        wq.shutdown(wait=True, timeout=10.0)
        assert len(results) == 5


# ── Capacity gating ───────────────────────────────────────────────


class TestCapacityGating:
    """Test that heavy tasks are gated by capacity."""

    def test_heavy_task_waits_for_capacity(self) -> None:
        """A size-3 task blocks until 3 units are free."""
        wq = WorkQueue(num_workers=2, capacity=3)

        running = threading.Event()
        gate = threading.Event()

        def heavy_resolver():
            running.set()
            gate.wait(timeout=5.0)
            return "heavy"

        # Submit size-3 task — fills all capacity
        wq.submit(WorkItem(
            priority=Priority.NORMAL,
            size=3,
            path="heavy",
            resolver=heavy_resolver,
        ))

        running.wait(timeout=2.0)
        assert running.is_set()

        # Submit size-1 task — should be queued, no capacity
        results: list[str] = []
        light_done = threading.Event()

        def light_resolver():
            results.append("light")
            light_done.set()
            return "light"

        wq.submit(WorkItem(
            priority=Priority.NORMAL,
            size=1,
            path="light",
            resolver=light_resolver,
        ))

        # After 100ms, light should NOT have run (heavy occupies all capacity)
        assert not light_done.wait(timeout=0.1)

        # Release the heavy task
        gate.set()

        # Now light should run
        light_done.wait(timeout=2.0)
        assert results == ["light"]

        wq.shutdown(wait=True)
