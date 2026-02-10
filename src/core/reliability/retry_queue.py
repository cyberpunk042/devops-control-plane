"""
Retry queue — persistent queue for failed operations.

Uses exponential backoff with jitter. Queue items are serialized
to disk so they survive restarts.
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RetryItem:
    """A single item in the retry queue."""

    id: str
    action_id: str
    adapter: str
    params: dict[str, Any] = field(default_factory=dict)
    attempt: int = 0
    max_attempts: int = 3
    next_retry_at: float = 0.0
    created_at: float = field(default_factory=time.time)
    last_error: str = ""

    @property
    def exhausted(self) -> bool:
        """Whether all retry attempts have been used."""
        return self.attempt >= self.max_attempts

    @property
    def ready(self) -> bool:
        """Whether it's time to retry this item."""
        return time.time() >= self.next_retry_at

    def schedule_retry(self, base_delay: float = 1.0, max_delay: float = 60.0) -> None:
        """Schedule the next retry with exponential backoff + jitter."""
        self.attempt += 1
        delay = min(base_delay * (2 ** (self.attempt - 1)), max_delay)
        jitter = random.uniform(0, delay * 0.3)
        self.next_retry_at = time.time() + delay + jitter
        logger.debug(
            "Retry item '%s' scheduled: attempt %d/%d, delay %.1fs",
            self.id,
            self.attempt,
            self.max_attempts,
            delay + jitter,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action_id": self.action_id,
            "adapter": self.adapter,
            "params": self.params,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "next_retry_at": self.next_retry_at,
            "created_at": self.created_at,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetryItem:
        return cls(**data)


class RetryQueue:
    """Persistent retry queue with exponential backoff.

    Items are stored in-memory and persisted to a JSON file on disk.
    The queue survives process restarts.
    """

    def __init__(
        self,
        path: Path | None = None,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ):
        self._path = path
        self._items: dict[str, RetryItem] = {}
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._max_delay = max_delay

        if path and path.is_file():
            self._load()

    @property
    def size(self) -> int:
        return len(self._items)

    @property
    def ready_count(self) -> int:
        return sum(1 for item in self._items.values() if item.ready and not item.exhausted)

    def enqueue(
        self,
        item_id: str,
        action_id: str,
        adapter: str,
        error: str = "",
        params: dict[str, Any] | None = None,
    ) -> RetryItem:
        """Add an item to the retry queue.

        If the item already exists, increments its attempt counter.
        """
        if item_id in self._items:
            item = self._items[item_id]
            item.last_error = error
            item.schedule_retry(self._base_delay, self._max_delay)
        else:
            item = RetryItem(
                id=item_id,
                action_id=action_id,
                adapter=adapter,
                params=params or {},
                max_attempts=self._max_attempts,
                last_error=error,
            )
            item.schedule_retry(self._base_delay, self._max_delay)
            self._items[item_id] = item

        self._save()
        return item

    def dequeue_ready(self) -> list[RetryItem]:
        """Get all items that are ready for retry."""
        ready = [
            item
            for item in self._items.values()
            if item.ready and not item.exhausted
        ]
        return sorted(ready, key=lambda i: i.next_retry_at)

    def complete(self, item_id: str) -> None:
        """Remove an item after successful retry."""
        self._items.pop(item_id, None)
        self._save()

    def fail(self, item_id: str, error: str = "") -> RetryItem | None:
        """Record a retry failure. Returns None if exhausted."""
        item = self._items.get(item_id)
        if item is None:
            return None

        item.last_error = error
        if item.exhausted:
            logger.warning("Retry item '%s' exhausted after %d attempts", item_id, item.attempt)
            return item

        item.schedule_retry(self._base_delay, self._max_delay)
        self._save()
        return item

    def remove_exhausted(self) -> list[RetryItem]:
        """Remove and return all exhausted items."""
        exhausted = [item for item in self._items.values() if item.exhausted]
        for item in exhausted:
            del self._items[item.id]
        if exhausted:
            self._save()
        return exhausted

    def clear(self) -> None:
        """Clear the entire queue."""
        self._items.clear()
        self._save()

    def get_status(self) -> dict[str, Any]:
        """Queue status summary."""
        return {
            "total": self.size,
            "ready": self.ready_count,
            "exhausted": sum(1 for i in self._items.values() if i.exhausted),
            "items": [item.to_dict() for item in self._items.values()],
        }

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [item.to_dict() for item in self._items.values()]
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        if self._path is None or not self._path.is_file():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for item_data in data:
                item = RetryItem.from_dict(item_data)
                self._items[item.id] = item
            logger.info("Loaded %d retry items from %s", len(self._items), self._path)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load retry queue: %s", e)
