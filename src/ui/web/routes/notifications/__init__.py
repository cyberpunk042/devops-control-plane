"""
Notifications & Error Log API routes.

Provides REST endpoints for:
- Listing, dismissing, and deleting notifications
- Logging frontend errors, listing errors with pagination, acknowledging errors
- Getting combined badge counts (for navbar icon)

All endpoints are prefixed with ``/api`` via the blueprint registration
in ``server.py``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

notifications_bp = Blueprint("notifications", __name__)
logger = logging.getLogger(__name__)


def _root() -> Path:
    """Get the project root from Flask app config."""
    return Path(current_app.config["PROJECT_ROOT"])


# ═══════════════════════════════════════════════════════════════════
#  Notifications
# ═══════════════════════════════════════════════════════════════════


@notifications_bp.route("/notifications")
def list_notifications():
    """List notifications.

    Query params:
        all (bool): Include dismissed notifications. Default: active only.

    Returns::

        {
            "notifications": [ ... ],
            "unread_count": 3
        }
    """
    from src.core.services.notifications import (
        get_active_notifications,
        get_all_notifications,
    )

    show_all = request.args.get("all", "").lower() in ("1", "true", "yes")

    if show_all:
        notifications = get_all_notifications(_root())
    else:
        notifications = get_active_notifications(_root())

    unread_count = sum(
        1 for n in get_active_notifications(_root())
    )

    return jsonify({
        "notifications": notifications,
        "unread_count": unread_count,
    })


@notifications_bp.route("/notifications/dismiss", methods=["POST"])
def dismiss():
    """Dismiss a notification.

    Request body::

        { "id": "notif-abcd1234" }

    Returns::

        { "success": true }
    """
    from src.core.services.notifications import dismiss_notification

    data = request.get_json(silent=True) or {}
    notif_id = data.get("id", "")
    if not notif_id:
        return jsonify({"success": False, "error": "Missing 'id'"}), 400

    found = dismiss_notification(_root(), notif_id)
    if not found:
        return jsonify({"success": False, "error": "Not found"}), 404

    return jsonify({"success": True})


@notifications_bp.route("/notifications/<notif_id>", methods=["DELETE"])
def delete(notif_id: str):
    """Delete a notification permanently.

    Returns::

        { "success": true }
    """
    from src.core.services.notifications import delete_notification

    found = delete_notification(_root(), notif_id)
    if not found:
        return jsonify({"success": False, "error": "Not found"}), 404

    return jsonify({"success": True})


# ═══════════════════════════════════════════════════════════════════
#  Error Log
# ═══════════════════════════════════════════════════════════════════


@notifications_bp.route("/errors")
def list_errors():
    """List errors with pagination.

    Query params:
        page (int): Page number, 1-indexed. Default: 1.
        per_page (int): Items per page. Default: 20.

    Returns::

        {
            "errors": [ ... ],
            "total": 42,
            "page": 1,
            "pages": 3,
            "unacked_count": 5
        }
    """
    from src.core.services.error_log import get_errors, get_unacked_count

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    # Clamp per_page to reasonable bounds
    per_page = max(1, min(per_page, 100))

    result = get_errors(_root(), page=page, per_page=per_page)
    result["unacked_count"] = get_unacked_count(_root())

    return jsonify(result)


@notifications_bp.route("/errors", methods=["POST"])
def log_frontend_error():
    """Log a frontend error reported by the browser.

    Request body::

        {
            "message": "TypeError: Cannot read undefined",
            "detail": "at renderCard (dashboard.js:142)\\n...",
            "endpoint": "/#devops"
        }

    Returns::

        { "success": true, "id": "err-abcd1234" }
    """
    from src.core.services.error_log import log_error

    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"success": False, "error": "Missing 'message'"}), 400

    entry = log_error(
        _root(),
        source="frontend",
        message=message,
        detail=data.get("detail", ""),
        endpoint=data.get("endpoint", ""),
        level=data.get("level", "error"),
    )

    return jsonify({"success": True, "id": entry["id"]})


@notifications_bp.route("/errors/ack", methods=["POST"])
def ack():
    """Acknowledge all errors (user opened the Error Log tab).

    Returns::

        { "success": true, "acked": 5 }
    """
    from src.core.services.error_log import ack_errors

    count = ack_errors(_root())
    return jsonify({"success": True, "acked": count})


# ═══════════════════════════════════════════════════════════════════
#  Combined Badge Count
# ═══════════════════════════════════════════════════════════════════


@notifications_bp.route("/notifications/badge")
def badge():
    """Get combined badge data for the navbar icon.

    Returns::

        {
            "notification_count": 3,
            "error_count": 2
        }

    Used by the frontend on boot to set the initial badge state
    without fetching the full notification and error lists.
    """
    from src.core.services.error_log import get_unacked_count
    from src.core.services.notifications import get_active_notifications

    return jsonify({
        "notification_count": len(get_active_notifications(_root())),
        "error_count": get_unacked_count(_root()),
    })
