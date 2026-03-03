"""requires_gh_auth decorator — reusable gate for routes that need GitHub CLI."""

from __future__ import annotations

import logging
import shutil
from functools import wraps

from flask import jsonify

logger = logging.getLogger(__name__)


def requires_gh_auth(fn):  # type: ignore[no-untyped-def]
    """Decorator for Flask routes that require GitHub CLI (gh) installed + authenticated.

    Checks ``shutil.which('gh')`` and ``gh auth status`` before calling
    the handler.  If gh is missing or not authenticated, the decorator:

      1. Returns HTTP 401 with a JSON body containing ``needs``:
         - ``"gh_install"``  — gh CLI is not installed
         - ``"gh_auth"``     — gh CLI installed but not authenticated
      2. Publishes an ``auth:needed`` event so the frontend can react.

    Usage::

        @bp.route("/gh/pulls")
        @requires_gh_auth
        def gh_pulls():
            ...
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
        # 1. Is gh installed?
        if not shutil.which("gh"):
            status = {"ok": False, "needs": "gh_install",
                      "error": "GitHub CLI (gh) is not installed"}
            _publish_auth_needed(status)
            return jsonify(status), 401

        # 2. Is gh authenticated?
        # If GH_TOKEN is set (device flow saved to .env), skip gh auth status
        # entirely — it's broken on headless systems and GH_TOKEN can't
        # bypass migration on all gh versions.
        from src.core.services.git.ops import get_stored_gh_token
        if get_stored_gh_token():
            return fn(*args, **kwargs)

        import subprocess
        try:
            r = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode != 0:
                status = {"ok": False, "needs": "gh_auth",
                          "error": "GitHub CLI is not authenticated"}
                _publish_auth_needed(status)
                return jsonify(status), 401
        except Exception:
            status = {"ok": False, "needs": "gh_auth",
                      "error": "Failed to check gh auth status"}
            _publish_auth_needed(status)
            return jsonify(status), 401

        # All good — proceed
        return fn(*args, **kwargs)

    return wrapper


def _publish_auth_needed(status: dict) -> None:
    """Best-effort publish auth:needed event via EventBus."""
    try:
        from src.core.services.event_bus import bus
        bus.publish("auth:needed", key="gh", data=status)
    except Exception:
        logger.debug("EventBus publish failed (non-fatal)")
