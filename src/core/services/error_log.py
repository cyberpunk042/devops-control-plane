"""
Error log — append-only NDJSON error store with rotation.

Records backend and frontend errors to ``.state/error_log.ndjson``
for display in the admin panel's Error Log tab.  Errors that would
otherwise be silently swallowed (unhandled exceptions, failed API
calls, background task crashes) are captured here so the user sees
them.

Storage format: one JSON object per line (NDJSON / JSON Lines).
Append-only for safety — no read-modify-write on each error.
Rotation keeps the newest ``_MAX_ERRORS`` entries.

Each error has:
    - id:        Unique identifier (``err-<8-char-hex>``)
    - source:    ``"backend"`` or ``"frontend"``
    - level:     ``"error"`` or ``"warning"``
    - message:   Human-readable summary
    - detail:    Full traceback or stack trace (expandable in UI)
    - endpoint:  Request path or page URL (context)
    - ts:        Epoch seconds (float)
    - acked:     Whether the user has seen it (opened Error Log tab)

Event bus integration: ``log_error()`` publishes ``error:new`` so
connected browsers can pulse the error badge in real time.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ERROR_LOG_FILE = ".state/error_log.ndjson"
_MAX_ERRORS = 1000   # rotation: when exceeded, keep newest _KEEP_ERRORS
_KEEP_ERRORS = 800   # how many to keep after rotation


# ── Internal I/O ────────────────────────────────────────────


def _log_path(project_root: Path) -> Path:
    """Return the path to the error log file."""
    return project_root / _ERROR_LOG_FILE


def _read_all(project_root: Path) -> list[dict[str, Any]]:
    """Read all error entries from disk.

    Returns an empty list if the file is missing or unreadable.
    Each line is independently parsed — corrupt lines are skipped.
    """
    path = _log_path(project_root)
    if not path.is_file():
        return []

    entries: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # skip corrupt lines
    except OSError:
        return []

    return entries


def _append(project_root: Path, entry: dict[str, Any]) -> None:
    """Append a single error entry to the log file.

    Creates ``.state/`` if it does not exist.
    """
    path = _log_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def _rotate_if_needed(project_root: Path) -> None:
    """If the file exceeds ``_MAX_ERRORS`` lines, trim to ``_KEEP_ERRORS``.

    Keeps the newest entries (last lines in the file = most recent).
    """
    path = _log_path(project_root)
    if not path.is_file():
        return

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > _MAX_ERRORS:
            trimmed = lines[-_KEEP_ERRORS:]
            path.write_text(
                "\n".join(trimmed) + "\n",
                encoding="utf-8",
            )
            logger.info(
                "Error log rotated: %d → %d entries",
                len(lines),
                len(trimmed),
            )
    except Exception as exc:
        logger.warning("Error log rotation failed: %s", exc)


def _publish(event_type: str, **kw: Any) -> None:
    """Publish an error lifecycle event to the SSE bus.

    Fail-safe: if the bus is unavailable or publish raises, the
    error is silently swallowed.  Error logging must never break
    because of observability.
    """
    try:
        from src.core.services.event_bus import bus

        bus.publish(event_type, **kw)
    except Exception:
        pass  # observability must never break error logging


def _make_id() -> str:
    """Generate a unique error ID."""
    return "err-" + uuid.uuid4().hex[:8]


# ── Public API ──────────────────────────────────────────────


def log_error(
    project_root: Path,
    *,
    source: str,
    message: str,
    detail: str = "",
    endpoint: str = "",
    level: str = "error",
) -> dict[str, Any]:
    """Append an error to the log.

    Parameters
    ----------
    project_root : Path
        Project root directory.
    source : str
        Origin — ``"backend"`` or ``"frontend"``.
    message : str
        Human-readable error summary.
    detail : str
        Full traceback or stack trace (expandable in UI).
    endpoint : str
        Request path or page URL for context.
    level : str
        ``"error"`` or ``"warning"``.

    Returns
    -------
    dict
        The error entry that was logged.
    """
    entry: dict[str, Any] = {
        "id": _make_id(),
        "source": source,
        "level": level,
        "message": message,
        "detail": detail,
        "endpoint": endpoint,
        "ts": time.time(),
        "acked": False,
    }

    _append(project_root, entry)
    _rotate_if_needed(project_root)

    logger.info(
        "Error logged: id=%s source=%s endpoint=%s msg=%s",
        entry["id"],
        source,
        endpoint or "-",
        message[:100],
    )

    _publish("error:new", key=entry["id"], data=entry)

    return entry


def get_errors(
    project_root: Path,
    *,
    page: int = 1,
    per_page: int = 20,
) -> dict[str, Any]:
    """Return paginated errors, newest first.

    Parameters
    ----------
    page : int
        1-indexed page number.
    per_page : int
        Items per page (default 20).

    Returns
    -------
    dict
        ``{ errors: [...], total: N, page: N, pages: N }``
    """
    all_entries = _read_all(project_root)

    # Newest first (last in file = most recent)
    all_entries.reverse()

    total = len(all_entries)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, pages))

    start = (page - 1) * per_page
    end = start + per_page

    return {
        "errors": all_entries[start:end],
        "total": total,
        "page": page,
        "pages": pages,
    }


def ack_errors(project_root: Path) -> int:
    """Mark all errors as acknowledged.

    This is called when the user opens the Error Log tab.
    The ``acked`` flag is used to calculate the unacked count
    for the badge pulse.

    Returns the count of errors that were newly acknowledged.
    """
    path = _log_path(project_root)
    if not path.is_file():
        return 0

    entries = _read_all(project_root)
    acked_count = 0

    for entry in entries:
        if not entry.get("acked"):
            entry["acked"] = True
            acked_count += 1

    if acked_count > 0:
        # Rewrite the file with updated acked flags
        try:
            lines = [
                json.dumps(e, ensure_ascii=False, default=str)
                for e in entries
            ]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to write acked errors: %s", exc)
            return 0

    return acked_count


def get_unacked_count(project_root: Path) -> int:
    """Return count of unacknowledged errors (for badge)."""
    entries = _read_all(project_root)
    return sum(1 for e in entries if not e.get("acked"))
