"""Rollback — snapshot and restore files before/after fixes.

Every file is snapshotted before modification. If verification fails,
the file is restored to its exact pre-fix state. No half-fixed files.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FileSnapshot:
    """Saved state of a file before modification."""
    file_path: str
    original_content: str
    original_hash: str
    taken_at: str
    discarded: bool = False


class SnapshotManager:
    """Manage file snapshots for rollback."""

    def __init__(self) -> None:
        self._snapshots: dict[str, FileSnapshot] = {}

    def take(self, file_path: Path) -> str:
        """Take a snapshot of a file before modification.

        Returns the file path as the snapshot key.
        If a snapshot already exists for this file, it's kept
        (we want the ORIGINAL state, not an intermediate).
        """
        key = str(file_path)

        if key in self._snapshots and not self._snapshots[key].discarded:
            return key  # Already have a snapshot — keep the original

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("Cannot snapshot %s: %s", file_path, exc)
            return key

        self._snapshots[key] = FileSnapshot(
            file_path=key,
            original_content=content,
            original_hash=hashlib.sha256(content.encode()).hexdigest()[:16],
            taken_at=datetime.now(timezone.utc).isoformat(),
        )

        return key

    def rollback(self, file_path: Path) -> bool:
        """Restore a file to its pre-fix state.

        Returns True if restored, False if no snapshot exists.
        """
        key = str(file_path)
        snapshot = self._snapshots.get(key)

        if not snapshot or snapshot.discarded:
            logger.warning("No snapshot for rollback: %s", file_path)
            return False

        try:
            file_path.write_text(snapshot.original_content, encoding="utf-8")
            logger.info("Rolled back: %s", file_path)
            return True
        except Exception as exc:
            logger.error("Rollback failed for %s: %s", file_path, exc)
            return False

    def rollback_all(self) -> list[str]:
        """Rollback all snapshotted files. Returns list of rolled-back paths."""
        rolled_back = []
        for key, snapshot in self._snapshots.items():
            if not snapshot.discarded:
                path = Path(snapshot.file_path)
                if self.rollback(path):
                    rolled_back.append(key)
        return rolled_back

    def discard(self, file_path: Path) -> None:
        """Discard snapshot — fix was verified, no rollback needed."""
        key = str(file_path)
        snapshot = self._snapshots.get(key)
        if snapshot:
            snapshot.discarded = True

    def discard_all(self) -> None:
        """Discard all snapshots."""
        for snapshot in self._snapshots.values():
            snapshot.discarded = True

    def has_snapshot(self, file_path: Path) -> bool:
        """Check if a snapshot exists for a file."""
        key = str(file_path)
        snap = self._snapshots.get(key)
        return snap is not None and not snap.discarded

    def active_snapshots(self) -> list[str]:
        """List files with active (undiscarded) snapshots."""
        return [
            key for key, snap in self._snapshots.items()
            if not snap.discarded
        ]

    def stats(self) -> dict:
        """Snapshot statistics."""
        total = len(self._snapshots)
        active = sum(1 for s in self._snapshots.values() if not s.discarded)
        discarded = total - active
        return {"total": total, "active": active, "discarded": discarded}
