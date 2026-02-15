"""
EventBus — thread-safe, in-process pub/sub with bounded replay.

This is the central nervous system for real-time state communication.
All state changes (cache lifecycle, system events, future file-watcher
and git/CI events) publish through this bus.

SSE clients subscribe and receive a live stream of events.  On
reconnect, the bus replays missed events from a bounded ring buffer,
or sends a full state snapshot if the client was away too long.

Thread safety model
───────────────────
- ``_lock`` protects ``_seq``, ``_buffer``, ``_subscribers``,
  ``_latest`` (all writes go through the lock).
- Each subscriber gets its own ``queue.Queue`` — the publisher
  pushes into all queues under the lock; each SSE generator
  consumes from its own queue independently.
- ``publish()`` is O(N) where N = active SSE connections (1–3).

Message standard (v1)
─────────────────────
Every event is a dict with these fields::

    {
        "v": 1,                     # schema version (immutable)
        "ts": 1739648400.123,       # server timestamp (immutable)
        "seq": 47,                  # monotonic sequence (immutable)
        "type": "cache:done",       # <domain>:<action> (stable)
        "key": "docker",            # resource identifier (stable)
        "data": { ... },            # event-specific payload (varies)
    }

Optional fields: ``error``, ``duration_s``, ``meta``.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from typing import Any, Generator

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1


class EventBus:
    """Thread-safe, in-process pub/sub with bounded replay buffer.

    Parameters
    ----------
    buffer_size : int
        Maximum number of events to keep in the replay ring buffer.
        Older events are silently discarded.  Clients that reconnect
        after their ``Last-Event-Id`` has been evicted receive a
        full ``state:snapshot`` instead of incremental replay.
    subscriber_queue_size : int
        Maximum backlog per SSE client.  If a client can't consume
        fast enough, its queue fills and the subscriber is dropped.
    """

    def __init__(
        self,
        *,
        buffer_size: int = 500,
        subscriber_queue_size: int = 200,
    ) -> None:
        self._lock = threading.Lock()
        self._seq: int = 0
        self._buffer: deque[dict] = deque(maxlen=buffer_size)
        self._subscribers: list[queue.Queue[dict]] = []
        self._subscriber_queue_size = subscriber_queue_size
        self._instance_id: str = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._latest: dict[str, dict] = {}  # key → latest cache:done payload

    # ── Properties ──────────────────────────────────────────────

    @property
    def instance_id(self) -> str:
        """Server instance identifier (boot timestamp)."""
        return self._instance_id

    @property
    def seq(self) -> int:
        """Current sequence number (monotonically increasing)."""
        with self._lock:
            return self._seq

    @property
    def subscriber_count(self) -> int:
        """Number of active SSE subscribers."""
        with self._lock:
            return len(self._subscribers)

    # ── Publishing ──────────────────────────────────────────────

    def publish(
        self,
        event_type: str,
        *,
        key: str = "",
        data: dict[str, Any] | None = None,
        **kw: Any,
    ) -> dict:
        """Broadcast an event to all connected SSE clients.

        Parameters
        ----------
        event_type : str
            Event type in ``<domain>:<action>`` format.
        key : str
            Resource identifier (cache key, etc.).  Empty for system events.
        data : dict | None
            Event-specific payload.
        **kw :
            Additional top-level fields (``error``, ``duration_s``, ``meta``).

        Returns
        -------
        dict
            The full event dict with ``seq`` assigned.
        """
        with self._lock:
            self._seq += 1
            event: dict[str, Any] = {
                "v": _SCHEMA_VERSION,
                "ts": time.time(),
                "seq": self._seq,
                "type": event_type,
                "key": key,
                "data": data or {},
                **kw,
            }
            self._buffer.append(event)

            # Track latest data per key for snapshots
            if event_type == "cache:done" and key:
                self._latest[key] = {
                    "data": data,
                    "cached_at": event["ts"],
                }
            elif event_type == "cache:bust":
                scope = (data or {}).get("scope", "")
                if scope == "all":
                    self._latest.clear()
                elif scope:
                    for k in scope.split(","):
                        self._latest.pop(k.strip(), None)

            # Push to all subscriber queues
            dead: list[queue.Queue[dict]] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                self._subscribers.remove(q)
                logger.info("Dropped unresponsive SSE subscriber (queue full)")

        # Log outside the lock (avoids holding lock during I/O)
        if event_type != "sys:heartbeat":
            extra = ""
            if "duration_s" in kw:
                extra = f" ({kw['duration_s']:.2f}s)"
            elif "error" in kw:
                extra = f" error={kw['error'][:80]}"
            logger.debug("event %s key=%s%s", event_type, key or "-", extra)

        return event

    # ── Subscribing ─────────────────────────────────────────────

    def subscribe(
        self,
        *,
        since: int = 0,
        heartbeat_interval: float = 30.0,
    ) -> Generator[dict, None, None]:
        """Yield events for an SSE client.  Blocks between events.

        Parameters
        ----------
        since : int
            Sequence number to resume from (``Last-Event-Id``).
            Events with ``seq > since`` are replayed from the buffer.
            If ``since`` is 0 or too old for the buffer, a full
            ``state:snapshot`` is sent instead.
        heartbeat_interval : float
            Seconds between heartbeat events when idle.

        Yields
        ------
        dict
            Event dicts ready for SSE serialization.
        """
        q: queue.Queue[dict] = queue.Queue(maxsize=self._subscriber_queue_size)
        need_snapshot = True

        with self._lock:
            if since > 0 and self._buffer:
                min_seq = self._buffer[0]["seq"]
                if since >= min_seq:
                    # Client's position is within buffer — replay missed events
                    need_snapshot = False
                    for event in self._buffer:
                        if event["seq"] > since:
                            try:
                                q.put_nowait(event)
                            except queue.Full:
                                # Too many events to replay; fall back to snapshot
                                need_snapshot = True
                                # Drain whatever we put in
                                while not q.empty():
                                    try:
                                        q.get_nowait()
                                    except queue.Empty:
                                        break
                                break

            self._subscribers.append(q)

        logger.info(
            "SSE client connected (since=%d, snapshot=%s, subscribers=%d)",
            since, need_snapshot, len(self._subscribers),
        )

        try:
            # Always send sys:ready first
            yield self._make_ready_event()

            # Send snapshot if needed (new connection or buffer exhausted)
            if need_snapshot:
                yield self._make_snapshot_event()

            # Stream events as they arrive
            while True:
                try:
                    event = q.get(timeout=heartbeat_interval)
                    yield event
                except queue.Empty:
                    # No events for heartbeat_interval — send keep-alive
                    yield self.publish("sys:heartbeat")
        finally:
            with self._lock:
                if q in self._subscribers:
                    self._subscribers.remove(q)
            logger.info("SSE client disconnected (subscribers=%d)", len(self._subscribers))

    # ── Snapshot ────────────────────────────────────────────────

    def snapshot(self) -> dict[str, dict]:
        """Return current state for pre-injection into HTML.

        Returns a dict mapping cache keys to their latest data::

            {
                "docker": {"data": {...}, "cached_at": 1739648400, "age_s": 42},
                "testing": {"data": {...}, "cached_at": 1739648100, "age_s": 342},
            }
        """
        with self._lock:
            now = time.time()
            result: dict[str, dict] = {}
            for key, entry in self._latest.items():
                result[key] = {
                    "data": entry["data"],
                    "cached_at": entry["cached_at"],
                    "age_s": round(now - entry["cached_at"]),
                }
            return result

    # ── Internal helpers ────────────────────────────────────────

    def _make_ready_event(self) -> dict:
        """Create a sys:ready event (NOT broadcast — only for the connecting client)."""
        with self._lock:
            self._seq += 1
            event = {
                "v": _SCHEMA_VERSION,
                "ts": time.time(),
                "seq": self._seq,
                "type": "sys:ready",
                "key": "",
                "data": {
                    "instance_id": self._instance_id,
                    "cache_keys": sorted(self._latest.keys()),
                },
            }
            # Don't append to buffer — sys:ready is per-client, not broadcast
            return event

    def _make_snapshot_event(self) -> dict:
        """Create a state:snapshot event (NOT broadcast — only for the connecting client)."""
        with self._lock:
            self._seq += 1
            now = time.time()
            snapshot_data: dict[str, dict] = {}
            for key, entry in self._latest.items():
                snapshot_data[key] = {
                    "data": entry["data"],
                    "cached_at": entry["cached_at"],
                    "age_s": round(now - entry["cached_at"]),
                }
            event = {
                "v": _SCHEMA_VERSION,
                "ts": now,
                "seq": self._seq,
                "type": "state:snapshot",
                "key": "",
                "data": snapshot_data,
            }
            # Don't append to buffer — snapshot is per-client
            return event


# ── Module-level singleton ──────────────────────────────────────

bus = EventBus()
"""The global event bus instance.

Import and use::

    from src.core.services.event_bus import bus
    bus.publish("cache:done", key="docker", data={...}, duration_s=2.51)
"""
