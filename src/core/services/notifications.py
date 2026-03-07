"""
Notification store — server-side persistent notifications.

Provides CRUD operations for notifications displayed in the admin
panel's notification panel.  Notifications are persisted to
``.state/notifications.json`` and survive server restarts.

Each notification has:
    - id:         Unique identifier (``notif-<8-char-hex>``)
    - type:       Category string for dedup + filtering
                  (e.g. ``cdp_suggestion``, ``session_expiring``)
    - title:      Short title shown in the panel header
    - message:    Full message body
    - created_at: Epoch seconds (float)
    - dismissed:  Whether the user dismissed it (still in file)
    - meta:       Optional dict of type-specific data

Deduplication: ``create_notification(dedup=True)`` skips creation if
an active (non-dismissed) notification of the same ``type`` already
exists.  This prevents spamming (e.g. "Enable CDP" on every tab switch).

Event bus integration: create/dismiss/delete publish SSE events so
all connected browsers update in real time.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_NOTIF_FILE = ".state/notifications.json"

# ── File format ─────────────────────────────────────────────
#
# {
#     "version": 1,
#     "notifications": [ ... ]
# }
#
# Notifications are stored newest-first (prepended on create).


# ── Internal I/O ────────────────────────────────────────────


def _load_raw(project_root: Path) -> list[dict[str, Any]]:
    """Load the raw notifications list from disk.

    Returns an empty list if the file is missing or corrupt.
    """
    path = project_root / _NOTIF_FILE
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("notifications"), list):
            return data["notifications"]
        # Tolerate bare list (forward compat)
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, IOError) as exc:
        logger.warning("Failed to load notifications: %s", exc)
        return []


def _save_raw(project_root: Path, notifications: list[dict[str, Any]]) -> None:
    """Write the notifications list to disk.

    Creates ``.state/`` if it does not exist.
    """
    path = project_root / _NOTIF_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "notifications": notifications,
    }
    path.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )


def _publish(event_type: str, **kw: Any) -> None:
    """Publish a notification lifecycle event to the SSE bus.

    Fail-safe: if the bus is unavailable or publish raises, the
    error is silently swallowed.  Notification CRUD must never
    break because of observability.
    """
    try:
        from src.core.services.event_bus import bus

        bus.publish(event_type, **kw)
    except Exception:
        pass  # observability must never break notifications


def _make_id() -> str:
    """Generate a unique notification ID."""
    return "notif-" + uuid.uuid4().hex[:8]


# ── Public API ──────────────────────────────────────────────


def load_notifications(project_root: Path) -> list[dict[str, Any]]:
    """Load all notifications from disk.

    Returns ``[]`` if the file is missing or corrupt.
    """
    return _load_raw(project_root)


def save_notifications(
    project_root: Path,
    notifications: list[dict[str, Any]],
) -> None:
    """Write the notifications list to disk.

    Creates ``.state/`` directory if needed.
    """
    _save_raw(project_root, notifications)


def create_notification(
    project_root: Path,
    *,
    notif_type: str,
    title: str,
    message: str,
    meta: dict[str, Any] | None = None,
    dedup: bool = True,
) -> dict[str, Any] | None:
    """Create a notification.

    Parameters
    ----------
    project_root : Path
        Project root directory.
    notif_type : str
        Category string (e.g. ``"cdp_suggestion"``).  Used for
        deduplication and filtering.
    title : str
        Short title displayed in the notification panel.
    message : str
        Full message body.
    meta : dict | None
        Optional type-specific data (e.g. ``{"action_url": "#debugging"}``).
    dedup : bool
        If ``True``, skip creation if an active (non-dismissed)
        notification of the same ``type`` already exists.

    Returns
    -------
    dict | None
        The created notification dict, or ``None`` if deduped.
    """
    notifications = _load_raw(project_root)

    # Deduplication: check for active notification of same type
    if dedup:
        for existing in notifications:
            if existing.get("type") == notif_type and not existing.get("dismissed"):
                logger.debug(
                    "Notification deduped: type=%s already active (id=%s)",
                    notif_type,
                    existing.get("id"),
                )
                return None

    notif: dict[str, Any] = {
        "id": _make_id(),
        "type": notif_type,
        "title": title,
        "message": message,
        "created_at": time.time(),
        "dismissed": False,
        "meta": meta or {},
    }

    # Prepend (newest first)
    notifications.insert(0, notif)
    _save_raw(project_root, notifications)

    logger.info("Notification created: id=%s type=%s", notif["id"], notif_type)
    _publish("notification:new", key=notif["id"], data=notif)

    return notif


def dismiss_notification(project_root: Path, notif_id: str) -> bool:
    """Mark a notification as dismissed.

    The notification stays in the file but is excluded from
    ``get_active_notifications()``.

    Returns ``True`` if the notification was found and dismissed.
    """
    notifications = _load_raw(project_root)
    found = False

    for notif in notifications:
        if notif.get("id") == notif_id:
            notif["dismissed"] = True
            found = True
            break

    if found:
        _save_raw(project_root, notifications)
        logger.info("Notification dismissed: id=%s", notif_id)
        _publish("notification:dismissed", key=notif_id)

    return found


def delete_notification(project_root: Path, notif_id: str) -> bool:
    """Permanently remove a notification from the file.

    Returns ``True`` if the notification was found and deleted.
    """
    notifications = _load_raw(project_root)
    original_len = len(notifications)
    notifications = [n for n in notifications if n.get("id") != notif_id]

    if len(notifications) < original_len:
        _save_raw(project_root, notifications)
        logger.info("Notification deleted: id=%s", notif_id)
        _publish("notification:deleted", key=notif_id)
        return True

    return False


def get_active_notifications(project_root: Path) -> list[dict[str, Any]]:
    """Return only non-dismissed notifications, newest first."""
    return [
        n
        for n in _load_raw(project_root)
        if not n.get("dismissed")
    ]


def get_all_notifications(project_root: Path) -> list[dict[str, Any]]:
    """Return all notifications (including dismissed), newest first.

    The list is stored newest-first, so no re-sorting is needed.
    """
    return _load_raw(project_root)
