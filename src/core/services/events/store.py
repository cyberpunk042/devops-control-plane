"""
EventStore — append-only, immutable, ordered event log.

The single source of truth for everything the tool does.

Hot storage: in-memory deque (last 5000 events, instant access).
Cold storage: JSONL file per day (.state/events/YYYY-MM-DD.jsonl).

Thread-safe. Fail-safe (store errors logged, never crash the caller).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from src.core.services.events.models import Event

logger = logging.getLogger(__name__)

_HOT_MAX = 5000


class EventStore:
    """Append-only event store with in-memory hot cache and JSONL cold storage."""

    def __init__(self, state_dir: Path) -> None:
        self._state_dir = state_dir
        self._events_dir = state_dir / "events"
        self._events_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._hot: deque[Event] = deque(maxlen=_HOT_MAX)
        self._seq = 0
        self._subscribers: list[Callable[[Event], None]] = []

    # ── Write ─────────────────────────────────────────────────────

    def append(self, event: Event) -> Event:
        """Append an event. Assigns ID if not set. Thread-safe.

        Returns the event (with ID assigned).
        """
        with self._lock:
            if not event.id or event.id.startswith("evt-0"):
                # Assign monotonic ID
                self._seq += 1
                event = Event(
                    id=f"evt-{self._seq}",
                    ts=event.ts or time.time(),
                    type=event.type,
                    correlation_id=event.correlation_id,
                    causation_id=event.causation_id,
                    source=event.source,
                    path=event.path,
                    status=event.status,
                    duration_ms=event.duration_ms,
                    summary=event.summary,
                    detail=event.detail,
                    origin=event.origin,
                    actor=event.actor,
                )

            self._hot.append(event)

        # Persist to disk (outside lock — non-blocking)
        try:
            self._persist(event)
        except Exception:
            logger.debug("Event persist failed for %s", event.id, exc_info=True)

        # Notify subscribers (outside lock)
        for sub in self._subscribers:
            try:
                sub(event)
            except Exception:
                logger.debug("Event subscriber failed", exc_info=True)

        return event

    def _persist(self, event: Event) -> None:
        """Append event to the day's JSONL file."""
        day = datetime.fromtimestamp(event.ts, tz=UTC).strftime("%Y-%m-%d")
        path = self._events_dir / f"{day}.jsonl"
        line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(line)

    # ── Read ──────────────────────────────────────────────────────

    def query(
        self,
        *,
        since_ts: float = 0,
        types: list[str] | None = None,
        correlation_id: str | None = None,
        limit: int = 5000,
    ) -> list[Event]:
        """Query events. Reads from hot cache first, falls back to disk.

        Args:
            since_ts: Only events after this timestamp.
            types: Filter by event type prefix (e.g., ["mediator.", "index."]).
            correlation_id: Filter by correlation ID.
            limit: Max events to return.
        """
        # Try hot cache first
        with self._lock:
            candidates = list(self._hot)

        results = self._filter(candidates, since_ts, types, correlation_id)

        # If hot cache doesn't cover since_ts, read from disk
        if since_ts > 0 and (not candidates or candidates[0].ts > since_ts):
            cold = self._read_cold(since_ts)
            cold_filtered = self._filter(cold, since_ts, types, correlation_id)
            # Merge (cold first, then hot), dedup by ID
            seen = set()
            merged = []
            for e in cold_filtered + results:
                if e.id not in seen:
                    seen.add(e.id)
                    merged.append(e)
            results = merged

        # Sort newest first, apply limit
        results.sort(key=lambda e: e.ts, reverse=True)
        return results[:limit]

    def all_events(self) -> list[Event]:
        """Return all events in hot cache (newest first)."""
        with self._lock:
            result = list(self._hot)
        result.sort(key=lambda e: e.ts, reverse=True)
        return result

    def count(self) -> int:
        """Number of events in hot cache."""
        with self._lock:
            return len(self._hot)

    def _filter(
        self,
        events: list[Event],
        since_ts: float,
        types: list[str] | None,
        correlation_id: str | None,
    ) -> list[Event]:
        result = []
        for e in events:
            if e.ts < since_ts:
                continue
            if types and not any(e.type.startswith(t) for t in types):
                continue
            if correlation_id and e.correlation_id != correlation_id:
                continue
            result.append(e)
        return result

    def _read_cold(self, since_ts: float) -> list[Event]:
        """Read events from JSONL files on disk."""
        events = []
        if not self._events_dir.exists():
            return events

        for jsonl_file in sorted(self._events_dir.glob("*.jsonl")):
            try:
                with jsonl_file.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            evt = Event.from_dict(d)
                            if evt.ts >= since_ts:
                                events.append(evt)
                        except Exception:
                            continue
            except Exception:
                continue

        return events

    # ── Subscribe ─────────────────────────────────────────────────

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        """Register a callback that fires on every append."""
        self._subscribers.append(callback)

    # ── Maintenance ───────────────────────────────────────────────

    _SNAPSHOT_FILE = "_snapshot.pkl"

    def load_cold(self, days: int = 30) -> None:
        """Pre-load recent cold events into hot cache (startup warm-up).

        Delta-driven: persists a snapshot of the hot cache + byte offsets
        per JSONL file. On restart, loads the snapshot (fast), then reads
        only NEW lines appended after the snapshot was saved.

        First run: full JSONL parse, saves snapshot for next time.
        Subsequent runs: snapshot load (<50ms) + delta parse (~0ms if clean shutdown).
        """
        import pickle

        snapshot_path = self._events_dir / self._SNAPSHOT_FILE
        cutoff = time.time() - (days * 86400)
        file_offsets: dict[str, int] = {}  # filename → byte offset already processed

        # ── Step 1: Load snapshot (fast path) ─────────────────
        snapshot_loaded = False
        if snapshot_path.is_file():
            try:
                t0 = time.time()
                with snapshot_path.open("rb") as f:
                    snapshot = pickle.load(f)

                events = snapshot.get("events", [])
                snapshot_seq = snapshot.get("seq", 0)
                file_offsets = snapshot.get("file_offsets", {})

                # Filter to cutoff window (drop events older than `days`)
                events = [e for e in events if e.ts >= cutoff]

                with self._lock:
                    self._hot.extend(events)
                    self._seq = max(self._seq, snapshot_seq)

                snapshot_loaded = True
                elapsed_ms = int((time.time() - t0) * 1000)
                logger.info(
                    "EventStore: snapshot loaded — %d events in %dms "
                    "(tracking %d file offsets)",
                    len(events), elapsed_ms, len(file_offsets),
                )
            except Exception as exc:
                logger.warning("EventStore: snapshot load failed, full reload: %s", exc)
                file_offsets = {}

        # ── Step 2: Read delta from JSONL files ───────────────
        # Only parse bytes AFTER the recorded offset per file.
        # Files not in the offset map are parsed fully.
        delta_loaded = 0
        new_offsets: dict[str, int] = {}

        if self._events_dir.exists():
            for jsonl_file in sorted(self._events_dir.glob("*.jsonl")):
                fname = jsonl_file.name
                try:
                    file_size = jsonl_file.stat().st_size
                except OSError:
                    continue

                prev_offset = file_offsets.get(fname, 0)
                new_offsets[fname] = file_size  # track current end

                if file_size <= prev_offset:
                    continue  # no new data in this file

                # Parse only the new bytes
                try:
                    with jsonl_file.open("r", encoding="utf-8") as f:
                        if prev_offset > 0:
                            f.seek(prev_offset)

                        new_events = []
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                d = json.loads(line)
                                evt = Event.from_dict(d)
                                if evt.ts >= cutoff:
                                    new_events.append(evt)
                            except Exception:
                                continue

                    if new_events:
                        with self._lock:
                            existing_ids = {e.id for e in self._hot}
                            for e in new_events:
                                if e.id not in existing_ids:
                                    self._hot.append(e)
                                    existing_ids.add(e.id)
                                    delta_loaded += 1
                                try:
                                    seq = int(e.id.split("-")[1])
                                    self._seq = max(self._seq, seq)
                                except (IndexError, ValueError):
                                    pass
                except Exception:
                    continue

        if delta_loaded > 0:
            logger.info("EventStore: delta loaded %d new events from JSONL", delta_loaded)
        elif not snapshot_loaded:
            logger.info("EventStore: cold start — no snapshot, no events")

        # ── Step 3: Save snapshot for next restart ────────────
        self._save_snapshot(snapshot_path, new_offsets)

    def _save_snapshot(self, snapshot_path: Path, file_offsets: dict[str, int]) -> None:
        """Persist hot cache + file offsets as pickle snapshot."""
        import pickle

        try:
            with self._lock:
                events = list(self._hot)
                seq = self._seq

            tmp = snapshot_path.with_suffix(".tmp")
            with tmp.open("wb") as f:
                pickle.dump({
                    "events": events,
                    "seq": seq,
                    "saved_at": time.time(),
                    "file_offsets": file_offsets,
                }, f, protocol=pickle.HIGHEST_PROTOCOL)
            tmp.rename(snapshot_path)
            logger.debug("EventStore: snapshot saved (%d events, %d file offsets)",
                         len(events), len(file_offsets))
        except Exception as exc:
            logger.warning("EventStore: snapshot save failed: %s", exc)
