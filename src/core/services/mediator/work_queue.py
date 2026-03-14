"""
WorkQueue — priority-aware, size-weighted task scheduler.

Replaces the flat ``ThreadPoolExecutor`` with a scheduler that:

1. **Prioritizes web requests** — CRITICAL priority tasks run before
   any background work, bypassing capacity limits if necessary.
2. **Tracks task size** — heavy tasks (security scan, AST parsing)
   consume more capacity units, preventing them from monopolising
   the worker pool.
3. **Yield flag** — signals background workers to pause briefly
   when web requests are in flight, releasing the GIL.
4. **Batch completion** — tracks groups of tasks and fires callbacks
   when all tasks in a group complete (used for tiered dispatch).

Thread safety
─────────────
- ``WeightedSemaphore`` uses a ``Condition`` for capacity gating.
- ``WorkQueue._queue`` is ``queue.PriorityQueue`` (thread-safe).
- The yield flag uses ``threading.Event`` (thread-safe).
- Web-request counter uses a ``Lock`` for atomic increment/decrement.

Integration
───────────
- Created in ``mediator/__init__.py`` instead of ``ThreadPoolExecutor``.
- ``QueryMediator.dispatch()`` submits ``WorkItem`` instances.
- ``QueryMediator.get()`` detects Flask request context and submits
  at CRITICAL priority via ``submit_and_wait()``.
- Ops functions call ``current_yield_check()`` in CPU-bound loops.

Design patterns
───────────────
- Priority Queue with weighted semaphore (admission control)
- Cooperative yielding via shared flag (backpressure)
- Poison pill shutdown (graceful worker termination)
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Priority levels ────────────────────────────────────────────────


class Priority(IntEnum):
    """Task urgency levels.  Lower number = higher urgency.

    CRITICAL (0)
        Web request — user is waiting for a response.  Bypasses
        capacity limits.  Must run immediately.

    HIGH (1)
        User-initiated refresh — explicit "refresh" button click
        or force-recompute API call.

    NORMAL (2)
        FS trigger — index watcher detected a file change and
        dispatched downstream recomputation.

    LOW (3)
        Cold start background fill — initial population of devops
        card data after server startup.

    IDLE (4)
        Heavy background tasks — security scan, test pipeline,
        AST symbol parsing.  Runs last, yields to everything.
    """

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    IDLE = 4


# ── Work item ──────────────────────────────────────────────────────


@dataclass
class WorkItem:
    """A single unit of work submitted to the queue.

    Attributes
    ----------
    priority : int
        Urgency level (see ``Priority`` enum).
    size : int
        Capacity units consumed (1=light, 2=medium, 3=heavy).
        Heavy tasks consume more capacity, limiting how many can
        run concurrently.
    path : str
        Mediator node path (e.g. ``"devops.security"``).  Used for
        logging and deduplication.
    resolver : Callable
        Function that produces the result.  Signature: ``() -> Any``.
    callback : Callable | None
        Called with the result after successful execution.
        Signature: ``(result: Any) -> None``.  May be ``None``.
    error_callback : Callable | None
        Called with the exception if the resolver raises.
        Signature: ``(exc: Exception) -> None``.  May be ``None``.
    group_id : str | None
        Batch group identifier.  When all items in a group complete,
        the group's ``on_complete`` callback fires (see
        ``WorkQueue.submit_batch``).
    seq : int
        Monotonic sequence number, set by the queue on submission.
        Breaks priority ties: lower seq = submitted earlier (FIFO).
    """

    priority: int
    size: int
    path: str
    resolver: Callable[[], Any]
    callback: Callable[[Any], None] | None = None
    error_callback: Callable[[Exception], None] | None = None
    group_id: str | None = None
    seq: int = 0

    def __lt__(self, other: WorkItem) -> bool:
        """Priority queue ordering: lower priority number first,
        then lower seq (FIFO within same priority)."""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.seq < other.seq


# ── Sentinel for shutdown ──────────────────────────────────────────

_POISON = WorkItem(
    priority=999,
    size=0,
    path="__shutdown__",
    resolver=lambda: None,
)


# ── Weighted semaphore ─────────────────────────────────────────────


class WeightedSemaphore:
    """Capacity-based admission control.

    Tracks total acquired "weight units" instead of a simple count.
    ``acquire(n)`` blocks until ``n`` units are available.
    ``release(n)`` returns ``n`` units.

    Parameters
    ----------
    capacity : int
        Maximum total weight units that can be held simultaneously.
    """

    __slots__ = ("_capacity", "_used", "_lock", "_condition")

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError(f"capacity must be >= 1, got {capacity}")
        self._capacity = capacity
        self._used = 0
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)

    @property
    def capacity(self) -> int:
        """Total capacity units."""
        return self._capacity

    @property
    def available(self) -> int:
        """Currently available capacity units."""
        with self._lock:
            return self._capacity - self._used

    @property
    def used(self) -> int:
        """Currently acquired capacity units."""
        with self._lock:
            return self._used

    def acquire(self, weight: int, timeout: float | None = None) -> bool:
        """Block until ``weight`` units are available.

        Parameters
        ----------
        weight : int
            Number of capacity units to acquire.
        timeout : float | None
            Maximum seconds to wait.  ``None`` = wait forever.

        Returns
        -------
        bool
            ``True`` if acquired, ``False`` if timed out.
        """
        if weight < 1:
            raise ValueError(f"weight must be >= 1, got {weight}")

        deadline = None if timeout is None else time.monotonic() + timeout

        with self._condition:
            while self._used + weight > self._capacity:
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return False
                    self._condition.wait(timeout=remaining)
                else:
                    self._condition.wait()

            self._used += weight
            return True

    def force_acquire(self, weight: int) -> None:
        """Acquire regardless of capacity — for CRITICAL tasks.

        Allows temporary over-capacity.  The over-capacity resolves
        as tasks complete and release their units.

        Parameters
        ----------
        weight : int
            Number of capacity units to acquire.
        """
        with self._lock:
            self._used += weight

    def release(self, weight: int) -> None:
        """Return ``weight`` units to the pool.

        Parameters
        ----------
        weight : int
            Number of capacity units to release.

        Raises
        ------
        ValueError
            If releasing more units than currently held (indicates
            a bug in the caller).
        """
        with self._condition:
            if weight > self._used:
                logger.warning(
                    "WeightedSemaphore.release(%d) but only %d used — "
                    "clamping to %d",
                    weight, self._used, self._used,
                )
                weight = self._used
            self._used -= weight
            self._condition.notify_all()


# ── Yield flag — cooperative backpressure ──────────────────────────

# Thread-local storage for the yield-check function.
# Workers set this before calling resolvers.  Ops functions call
# ``current_yield_check()`` in their CPU-bound loops to cooperate
# with web request priority.

_tls = threading.local()


def current_yield_check() -> bool:
    """Check if the current background thread should yield.

    Returns ``True`` if web requests are in flight and the current
    thread should briefly pause (``time.sleep(0.01)``) to release
    the GIL.

    Returns ``False`` if:
    - No web requests are pending, or
    - The caller is not running inside a WorkQueue worker thread.

    Intended usage in CPU-bound loops::

        from src.core.services.mediator.work_queue import current_yield_check

        for i, filepath in enumerate(files):
            if i % 10 == 0 and current_yield_check():
                time.sleep(0.01)  # release GIL for web request
            process(filepath)
    """
    fn = getattr(_tls, "yield_check", None)
    return fn() if fn is not None else False


# ── Batch tracking ─────────────────────────────────────────────────


@dataclass
class _BatchGroup:
    """Tracks completion of a group of work items."""

    group_id: str
    total: int
    completed: int = 0
    failed: int = 0
    on_complete: Callable[[], None] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record_completion(self, success: bool) -> bool:
        """Record one item completing.  Returns True if the entire
        group is now complete."""
        with self._lock:
            if success:
                self.completed += 1
            else:
                self.failed += 1
            return (self.completed + self.failed) >= self.total


# ── WorkQueue ──────────────────────────────────────────────────────


class WorkQueue:
    """Priority-aware, size-weighted task scheduler.

    Parameters
    ----------
    num_workers : int
        Number of worker threads.
    capacity : int
        Total capacity units for the ``WeightedSemaphore``.
        Example: capacity=6 allows 6 × size-1, or 2 × size-3,
        or 1 × size-3 + 1 × size-2 + 1 × size-1.
    thread_name_prefix : str
        Prefix for worker thread names (for debugging).

    Example
    -------
    ::

        wq = WorkQueue(num_workers=4, capacity=6)

        wq.submit(WorkItem(
            priority=Priority.LOW,
            size=1,
            path="devops.git",
            resolver=lambda: git_status(root),
        ))

        result = wq.submit_and_wait(WorkItem(
            priority=Priority.CRITICAL,
            size=1,
            path="devops.git",
            resolver=lambda: git_status(root),
        ))

        wq.shutdown(wait=True)
    """

    def __init__(
        self,
        num_workers: int = 4,
        capacity: int = 6,
        thread_name_prefix: str = "wq",
    ) -> None:
        self._queue: queue.PriorityQueue[WorkItem] = queue.PriorityQueue()
        self._semaphore = WeightedSemaphore(capacity)
        self._num_workers = num_workers

        # Yield flag — set when web requests are in flight
        self._yield_flag = threading.Event()
        self._web_request_count = 0
        self._web_request_lock = threading.Lock()

        # Sequence counter for FIFO tiebreaking within same priority
        self._seq = 0
        self._seq_lock = threading.Lock()

        # Batch group tracking
        self._groups: dict[str, _BatchGroup] = {}
        self._groups_lock = threading.Lock()

        # Shutdown flag
        self._shutdown = False
        self._shutdown_event = threading.Event()

        # Start worker threads
        self._workers: list[threading.Thread] = []
        for i in range(num_workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"{thread_name_prefix}-{i}",
                daemon=True,
            )
            t.start()
            self._workers.append(t)

        logger.info(
            "WorkQueue started: %d workers, capacity=%d",
            num_workers, capacity,
        )

    # ── Public API ─────────────────────────────────────────────

    def submit(self, item: WorkItem) -> None:
        """Submit a work item to the queue.

        The item is queued by priority.  Workers pull highest-priority
        items first, then acquire semaphore capacity before executing.

        Parameters
        ----------
        item : WorkItem
            The work item to submit.

        Raises
        ------
        RuntimeError
            If the queue has been shut down.
        """
        if self._shutdown:
            raise RuntimeError("WorkQueue is shut down")

        with self._seq_lock:
            self._seq += 1
            item.seq = self._seq

        self._queue.put(item)

    def submit_and_wait(self, item: WorkItem, timeout: float = 30.0) -> Any:
        """Submit at CRITICAL priority and block until the result.

        Used for web requests that need synchronous computation.
        The item is submitted with CRITICAL priority and its resolver
        is executed by a worker thread.  The caller blocks until the
        result is available.

        Parameters
        ----------
        item : WorkItem
            The work item.  ``priority`` is forced to CRITICAL.
        timeout : float
            Maximum seconds to wait for the result.

        Returns
        -------
        Any
            The resolver's return value.

        Raises
        ------
        TimeoutError
            If the result isn't available within ``timeout``.
        RuntimeError
            If the resolver raised an exception.
        """
        item.priority = Priority.CRITICAL

        result_event = threading.Event()
        result_box: dict[str, Any] = {}

        original_callback = item.callback
        original_error_callback = item.error_callback

        def _on_result(result: Any) -> None:
            result_box["value"] = result
            result_box["ok"] = True
            if original_callback is not None:
                try:
                    original_callback(result)
                except Exception:
                    pass
            result_event.set()

        def _on_error(exc: Exception) -> None:
            result_box["error"] = exc
            result_box["ok"] = False
            if original_error_callback is not None:
                try:
                    original_error_callback(exc)
                except Exception:
                    pass
            result_event.set()

        item.callback = _on_result
        item.error_callback = _on_error

        self.submit(item)

        if not result_event.wait(timeout=timeout):
            raise TimeoutError(
                f"WorkQueue.submit_and_wait timed out after {timeout}s "
                f"for {item.path!r}"
            )

        if result_box.get("ok"):
            return result_box["value"]
        else:
            raise RuntimeError(
                f"Resolver failed for {item.path!r}: {result_box.get('error')}"
            ) from result_box.get("error")

    def submit_batch(
        self,
        items: list[WorkItem],
        on_complete: Callable[[], None] | None = None,
        group_id: str | None = None,
    ) -> str:
        """Submit a batch of items with a completion callback.

        All items are assigned the same ``group_id``.  When all items
        in the group have completed (success or failure), the
        ``on_complete`` callback fires.

        Parameters
        ----------
        items : list[WorkItem]
            Work items to submit as a group.
        on_complete : Callable | None
            Called (in a worker thread) when all items complete.
        group_id : str | None
            Explicit group ID.  If ``None``, auto-generated.

        Returns
        -------
        str
            The group ID for this batch.
        """
        if not items:
            # Empty batch — fire callback immediately
            if on_complete is not None:
                on_complete()
            return group_id or "empty"

        if group_id is None:
            with self._seq_lock:
                self._seq += 1
                group_id = f"batch-{self._seq}"

        group = _BatchGroup(
            group_id=group_id,
            total=len(items),
            on_complete=on_complete,
        )

        with self._groups_lock:
            self._groups[group_id] = group

        for item in items:
            item.group_id = group_id
            self.submit(item)

        return group_id

    # ── Web request priority ───────────────────────────────────

    def begin_web_request(self) -> None:
        """Signal that a web request is in flight.

        Sets the yield flag so background workers pause at their
        next checkpoint.  Call ``end_web_request()`` when the
        request completes.
        """
        with self._web_request_lock:
            self._web_request_count += 1
            self._yield_flag.set()

    def end_web_request(self) -> None:
        """Signal that a web request has completed.

        Clears the yield flag when all web requests have finished.
        """
        with self._web_request_lock:
            self._web_request_count = max(0, self._web_request_count - 1)
            if self._web_request_count == 0:
                self._yield_flag.clear()

    def should_yield(self) -> bool:
        """Check if background workers should yield for web requests.

        Cheap to call (~50ns) — checks a ``threading.Event``.
        """
        return self._yield_flag.is_set()

    @property
    def web_requests_active(self) -> int:
        """Number of web requests currently in flight."""
        with self._web_request_lock:
            return self._web_request_count

    # ── Diagnostics ────────────────────────────────────────────

    @property
    def pending(self) -> int:
        """Approximate number of items waiting in the queue."""
        return self._queue.qsize()

    @property
    def semaphore_used(self) -> int:
        """Capacity units currently acquired."""
        return self._semaphore.used

    @property
    def semaphore_available(self) -> int:
        """Capacity units currently available."""
        return self._semaphore.available

    def diag(self) -> dict[str, Any]:
        """Diagnostic snapshot of queue state."""
        active_groups: dict[str, dict] = {}
        with self._groups_lock:
            for gid, g in self._groups.items():
                active_groups[gid] = {
                    "total": g.total,
                    "completed": g.completed,
                    "failed": g.failed,
                }

        return {
            "pending": self.pending,
            "semaphore_capacity": self._semaphore.capacity,
            "semaphore_used": self.semaphore_used,
            "semaphore_available": self.semaphore_available,
            "web_requests_active": self.web_requests_active,
            "yield_flag": self._yield_flag.is_set(),
            "workers": self._num_workers,
            "shutdown": self._shutdown,
            "active_groups": active_groups,
        }

    # ── Shutdown ───────────────────────────────────────────────

    def shutdown(self, wait: bool = True, timeout: float = 30.0) -> None:
        """Stop the queue.  No new submissions accepted after this.

        Parameters
        ----------
        wait : bool
            If ``True``, block until all workers exit.
        timeout : float
            Maximum seconds to wait for workers to drain.
        """
        self._shutdown = True

        # Send poison pills — one per worker
        for _ in self._workers:
            try:
                self._queue.put(_POISON)
            except Exception:
                pass

        if wait:
            deadline = time.monotonic() + timeout
            for t in self._workers:
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    t.join(timeout=remaining)
                if t.is_alive():
                    logger.warning(
                        "WorkQueue worker %s did not exit within timeout",
                        t.name,
                    )

        self._shutdown_event.set()
        logger.info("WorkQueue shut down")

    # ── Worker loop (private) ──────────────────────────────────

    def _worker_loop(self) -> None:
        """Main loop for each worker thread.

        1. Pull highest-priority item from queue
        2. Acquire semaphore capacity (CRITICAL bypasses limit)
        3. Set thread-local yield check
        4. Execute resolver
        5. Call callback with result (or error_callback on failure)
        6. Release semaphore capacity
        7. Record batch completion if applicable
        8. Loop
        """
        while True:
            try:
                item = self._queue.get()
            except Exception:
                if self._shutdown:
                    break
                continue

            # Poison pill — exit the loop
            if item.path == "__shutdown__":
                self._queue.task_done()
                break

            # ── Acquire capacity ───────────────────────────────
            is_critical = item.priority <= Priority.CRITICAL
            if is_critical:
                # CRITICAL tasks bypass capacity limits
                self._semaphore.force_acquire(item.size)
            else:
                # Background tasks wait for capacity
                self._semaphore.acquire(item.size)

            # ── Set thread-local yield check ───────────────────
            _tls.yield_check = self.should_yield

            result = None
            success = True

            try:
                t0 = time.monotonic()
                result = item.resolver()
                elapsed = time.monotonic() - t0

                logger.debug(
                    "[WorkQueue] %s completed in %.1fms "
                    "(priority=%d, size=%d)",
                    item.path,
                    elapsed * 1000,
                    item.priority,
                    item.size,
                )

                if item.callback is not None:
                    try:
                        item.callback(result)
                    except Exception:
                        logger.exception(
                            "[WorkQueue] callback failed for %s",
                            item.path,
                        )

            except Exception as exc:
                success = False
                logger.exception(
                    "[WorkQueue] resolver failed for %s", item.path,
                )
                if item.error_callback is not None:
                    try:
                        item.error_callback(exc)
                    except Exception:
                        logger.exception(
                            "[WorkQueue] error_callback failed for %s",
                            item.path,
                        )

            finally:
                # ── Release capacity ───────────────────────────
                self._semaphore.release(item.size)

                # ── Clear thread-local ─────────────────────────
                _tls.yield_check = None

                # ── Batch completion tracking ──────────────────
                if item.group_id is not None:
                    self._record_group_completion(
                        item.group_id, success,
                    )

                self._queue.task_done()

    def _record_group_completion(
        self, group_id: str, success: bool,
    ) -> None:
        """Record a single item's completion within its batch group.

        If the entire group is now complete, fire the ``on_complete``
        callback and clean up the group.
        """
        with self._groups_lock:
            group = self._groups.get(group_id)
            if group is None:
                return

        all_done = group.record_completion(success)

        if all_done:
            # Clean up
            with self._groups_lock:
                self._groups.pop(group_id, None)

            if group.on_complete is not None:
                try:
                    group.on_complete()
                except Exception:
                    logger.exception(
                        "[WorkQueue] on_complete failed for group %s",
                        group_id,
                    )

            logger.debug(
                "[WorkQueue] group %s complete: %d ok, %d failed",
                group_id, group.completed, group.failed,
            )
