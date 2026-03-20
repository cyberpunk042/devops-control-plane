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

    def load_cold(self, days: int = 30) -> None:
        """Pre-load recent cold events into hot cache (startup warm-up).

        Uses a snapshot cache (.state/events/_snapshot.pkl) for fast reload.
        On first run or when new JSONL data exists after the snapshot,
        re-parses only the delta and updates the snapshot.
        """
        import pickle

        snapshot_path = self._events_dir / "_snapshot.pkl"
        cutoff = time.time() - (days * 86400)
        snapshot_loaded = False
        snapshot_ts = 0.0

        # ── Try loading the snapshot first (fast path) ──────────
        if snapshot_path.is_file():
            try:
                with snapshot_path.open("rb") as f:
                    snapshot = pickle.load(f)
                events = snapshot.get("events", [])
                snapshot_ts = snapshot.get("saved_at", 0.0)
                snapshot_seq = snapshot.get("seq", 0)

                # Filter to cutoff window
                events = [e for e in events if e.ts >= cutoff]

                with self._lock:
                    self._hot.extend(events)
                    self._seq = max(self._seq, snapshot_seq)
                snapshot_loaded = True
                logger.info(
                    "EventStore: loaded %d events from snapshot (%.1fs old)",
                    len(events), time.time() - snapshot_ts,
                )
            except Exception as exc:
                logger.warning("EventStore: snapshot load failed: %s", exc)
                snapshot_loaded = False

        # ── Load only JSONL lines newer than the snapshot ──────
        # If no snapshot, load everything (full cold start)
        since_ts = snapshot_ts if snapshot_loaded else cutoff
        cold = self._read_cold(since_ts)

        if cold:
            with self._lock:
                existing_ids = {e.id for e in self._hot}
                loaded = 0
                max_seq = self._seq
                for e in cold:
                    if e.id not in existing_ids:
                        self._hot.append(e)
                        existing_ids.add(e.id)
                        loaded += 1
                    try:
                        seq = int(e.id.split("-")[1])
                        max_seq = max(max_seq, seq)
                    except (IndexError, ValueError):
                        pass
                self._seq = max_seq
            if loaded > 0:
                logger.info("EventStore: loaded %d new events from JSONL (delta)",
                            loaded)

        # ── Save updated snapshot for next restart ────────────
        self._save_snapshot(snapshot_path)

    def _save_snapshot(self, snapshot_path: Path) -> None:
        """Persist the hot cache as a pickle snapshot for fast reload."""
        import pickle

        try:
            with self._lock:
                events = list(self._hot)
                seq = self._seq

            tmp = snapshot_path.with_suffix(".tmp")
            with tmp.open("wb") as f:
                pickle.dump({
                    "events": events,
                    "saved_at": time.time(),
                    "seq": seq,
                }, f, protocol=pickle.HIGHEST_PROTOCOL)
            tmp.rename(snapshot_path)
            logger.debug("EventStore: snapshot saved (%d events)", len(events))
        except Exception as exc:
            logger.warning("EventStore: snapshot save failed: %s", exc)
