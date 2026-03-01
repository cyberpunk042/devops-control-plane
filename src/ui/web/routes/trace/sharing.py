"""Trace sharing — share, unshare, update, delete."""

from __future__ import annotations

import logging
import threading

from flask import jsonify, request

from src.core.services.git_auth import is_auth_ok
from src.core.services.trace import (
    delete_trace,
    share_trace,
    unshare_trace,
    update_trace,
)
from src.ui.web.helpers import project_root as _project_root

from . import trace_bp

logger = logging.getLogger(__name__)


@trace_bp.route("/trace/share", methods=["POST"])
def trace_share():
    """Share a trace — commit to git so it's visible to others.

    Body (JSON):
        trace_id  — the trace to share (required)
        thread_id — chat thread to post to (default: general)
    """
    try:
        root = _project_root()
        body = request.get_json(silent=True) or {}
        trace_id = body.get("trace_id", "")
        thread_id = body.get("thread_id") or None
        if not trace_id:
            return jsonify({"error": "trace_id is required"}), 400

        ok = share_trace(root, trace_id)
        if not ok:
            return jsonify({"error": f"Trace not found: {trace_id}"}), 404

        # Post trace to chat so it appears in the Content → Chat view
        from src.core.services.trace.trace_recorder import get_trace, post_trace_to_chat
        trace = get_trace(root, trace_id)
        if trace:
            try:
                post_trace_to_chat(root, trace, thread_id=thread_id)
            except Exception as e:
                logger.warning("Failed to post trace to chat: %s", e)

        # Push in background so other machines see it
        if is_auth_ok():
            from src.core.services.ledger.worktree import push_ledger_branch
            threading.Thread(target=push_ledger_branch, args=(root,), daemon=True).start()

        return jsonify({"trace_id": trace_id, "shared": True})
    except Exception as e:
        logger.exception("Failed to share trace")
        return jsonify({"error": str(e)}), 500


@trace_bp.route("/trace/unshare", methods=["POST"])
def trace_unshare():
    """Mark a trace as local-only (unshare from git).

    Body (JSON):
        trace_id — the trace to unshare (required)
    """
    try:
        root = _project_root()
        body = request.get_json(silent=True) or {}
        trace_id = body.get("trace_id", "")
        if not trace_id:
            return jsonify({"error": "trace_id is required"}), 400

        ok = unshare_trace(root, trace_id)
        if not ok:
            return jsonify({"error": f"Trace not found: {trace_id}"}), 404

        # Push in background so other machines see the flag change
        if is_auth_ok():
            from src.core.services.ledger.worktree import push_ledger_branch
            threading.Thread(target=push_ledger_branch, args=(root,), daemon=True).start()

        return jsonify({"trace_id": trace_id, "shared": False})
    except Exception as e:
        logger.exception("Failed to unshare trace")
        return jsonify({"error": str(e)}), 500


@trace_bp.route("/trace/update", methods=["POST"])
def trace_update():
    """Update trace metadata (name, classification).

    Body (JSON):
        trace_id       — the trace to update (required)
        name           — new name (optional)
        classification — new classification (optional)
    """
    try:
        root = _project_root()
        body = request.get_json(silent=True) or {}
        trace_id = body.get("trace_id", "")
        if not trace_id:
            return jsonify({"error": "trace_id is required"}), 400

        ok = update_trace(
            root, trace_id,
            name=body.get("name"),
            classification=body.get("classification"),
        )
        if not ok:
            return jsonify({"error": f"Trace not found: {trace_id}"}), 404

        return jsonify({"trace_id": trace_id, "updated": True})
    except Exception as e:
        logger.exception("Failed to update trace")
        return jsonify({"error": str(e)}), 500


@trace_bp.route("/trace/delete", methods=["POST"])
def trace_delete():
    """Delete a trace from local storage.

    Removes the trace from .state/traces/ only.
    The ledger copy (if shared) stays — use unshare to remove from ledger.

    Body (JSON):
        trace_id — the trace to delete (required)
    """
    try:
        root = _project_root()
        body = request.get_json(silent=True) or {}
        trace_id = body.get("trace_id", "")
        if not trace_id:
            return jsonify({"error": "trace_id is required"}), 400

        ok = delete_trace(root, trace_id)
        if not ok:
            return jsonify({"error": f"Trace not found locally: {trace_id}"}), 404

        return jsonify({"trace_id": trace_id, "deleted": True})
    except Exception as e:
        logger.exception("Failed to delete trace")
        return jsonify({"error": str(e)}), 500
