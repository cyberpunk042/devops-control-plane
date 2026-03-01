"""requires_git_auth decorator — reusable gate for routes that hit git remote."""

from __future__ import annotations

import logging
from functools import wraps
from pathlib import Path

from flask import current_app, jsonify

from src.core.services.git_auth import check_auth, is_auth_ok

logger = logging.getLogger(__name__)


def requires_git_auth(fn):
    """Decorator for Flask routes that require git network auth.

    Checks ``is_auth_ok()`` before calling the handler.  If auth is
    not ready (SSH key needs passphrase, HTTPS needs token), the
    decorator:

      1. Runs ``check_auth()`` to get the detailed status dict.
      2. Publishes an ``auth:needed`` event on the EventBus so the
         client can reactively show the passphrase modal.
      3. Returns HTTP 401 with the status dict as JSON.

    Usage::

        @bp.route("/git/push", methods=["POST"])
        @requires_git_auth
        @run_tracked("git", "git:push")
        def git_push():
            ...
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if is_auth_ok():
            return fn(*args, **kwargs)

        # Auth not ready — gather details & notify client via SSE
        try:
            root = Path(current_app.config["PROJECT_ROOT"])
            status = check_auth(root)
        except Exception:
            status = {"ok": False, "needs": "ssh_passphrase"}

        try:
            from src.core.services.event_bus import bus
            bus.publish("auth:needed", key="git", data=status)
        except Exception:
            logger.debug("EventBus publish failed (non-fatal)")

        return jsonify(status), 401

    return wrapper
