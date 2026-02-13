"""
Audit ledger — append-only execution log.

Every operation writes an entry to an NDJSON (newline-delimited JSON) file.
This is the project's execution history, useful for debugging, compliance,
and understanding what happened and when.

The ledger is append-only: entries are never modified or deleted.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Default audit directory
DEFAULT_AUDIT_DIR = ".state"
DEFAULT_AUDIT_FILE = "audit.ndjson"


class AuditEntry(BaseModel):
    """A single audit log entry."""

    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    operation_id: str = ""
    operation_type: str = ""       # detect, automate, scaffold, etc.

    # What happened
    automation: str = ""
    environment: str = ""
    modules_affected: list[str] = Field(default_factory=list)

    # Results
    status: str = ""               # ok, partial, failed
    actions_total: int = 0
    actions_succeeded: int = 0
    actions_failed: int = 0
    duration_ms: int = 0

    # Errors (if any)
    errors: list[str] = Field(default_factory=list)

    # Extensible context
    context: dict[str, Any] = Field(default_factory=dict)


class AuditWriter:
    """Append-only audit ledger writer.

    Each call to write() appends a single JSON line to the ledger file.
    The file is created if it doesn't exist.
    """

    def __init__(self, path: Path | None = None, project_root: Path | None = None):
        if path is not None:
            self._path = path
        elif project_root is not None:
            self._path = project_root / DEFAULT_AUDIT_DIR / DEFAULT_AUDIT_FILE
        else:
            self._path = Path(DEFAULT_AUDIT_DIR) / DEFAULT_AUDIT_FILE

    @property
    def path(self) -> Path:
        return self._path

    def write(self, entry: AuditEntry) -> None:
        """Append an audit entry to the ledger.

        Args:
            entry: The entry to write.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)

        data = entry.model_dump(mode="json")
        line = json.dumps(data, ensure_ascii=False) + "\n"

        try:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line)
            logger.debug("Audit entry written: %s/%s", entry.operation_type, entry.operation_id)
        except OSError as e:
            logger.error("Failed to write audit entry: %s", e)

    def read_all(self) -> list[AuditEntry]:
        """Read all entries from the ledger.

        Returns:
            List of audit entries, oldest first.
        """
        if not self._path.is_file():
            return []

        entries = []
        try:
            with self._path.open("r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entries.append(AuditEntry.model_validate(data))
                    except (json.JSONDecodeError, Exception) as e:
                        logger.warning("Skipping corrupt audit entry at line %d: %s", line_num, e)
        except OSError as e:
            logger.error("Failed to read audit ledger: %s", e)

        return entries

    def read_recent(self, n: int = 20) -> list[AuditEntry]:
        """Read the most recent N entries.

        Not the most efficient for large files, but simple and correct.
        For a production system with huge ledgers, consider tail-reading.
        """
        all_entries = self.read_all()
        return all_entries[-n:]

    def entry_count(self) -> int:
        """Count entries without loading them all into memory."""
        if not self._path.is_file():
            return 0
        try:
            with self._path.open("r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except OSError:
            return 0
