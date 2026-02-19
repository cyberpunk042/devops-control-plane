"""
Trace API routes — session tracing for the Debugging tab.

Blueprint: trace_bp
Prefix: /api (applied by server.py)

Endpoints:
    /api/trace/start            — start a recording session
    /api/trace/stop             — stop a recording session
    /api/trace/active           — list active recordings
    /api/trace/list             — list saved traces
    /api/trace/get              — get a single trace by ID
    /api/trace/events           — get events for a trace
    /api/trace/share            — share a trace (commit to git)
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services.trace import (
    active_recordings,
    get_trace,
    get_trace_events,
    list_traces,
    save_trace,
    share_trace,
    start_recording,
    stop_recording,
    unshare_trace,
    update_trace,
)

logger = logging.getLogger(__name__)

trace_bp = Blueprint("trace", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


# ── Start recording ───────────────────────────────────────────────

@trace_bp.route("/trace/start", methods=["POST"])
def trace_start():
    """Start a recording session.

    Body (JSON):
        name           — human-readable name (optional)
        classification — category: deployment, debugging, config, exploration (optional)
    """
    try:
        root = _project_root()
        body = request.get_json(silent=True) or {}
        name = body.get("name", "")
        classification = body.get("classification", "")

        trace_id = start_recording(
            root,
            name=name,
            classification=classification,
        )
        return jsonify({"trace_id": trace_id})
    except Exception as e:
        logger.exception("Failed to start recording")
        return jsonify({"error": str(e)}), 500


# ── Stop recording ────────────────────────────────────────────────

@trace_bp.route("/trace/stop", methods=["POST"])
def trace_stop():
    """Stop a recording session and optionally save to ledger.

    Body (JSON):
        trace_id  — the active recording to stop (required)
        save      — save to ledger (default true)
    """
    try:
        root = _project_root()
        body = request.get_json(silent=True) or {}
        trace_id = body.get("trace_id", "")
        do_save = body.get("save", True)

        if not trace_id:
            return jsonify({"error": "trace_id is required"}), 400

        trace = stop_recording(trace_id)
        if trace is None:
            return jsonify({"error": f"No active recording: {trace_id}"}), 404

        # Save to ledger
        if do_save:
            save_trace(root, trace)

        return jsonify({
            "trace_id": trace.trace_id,
            "name": trace.name,
            "event_count": trace.event_count,
            "duration_s": trace.duration_s,
            "auto_summary": trace.auto_summary,
            "saved": do_save,
        })
    except Exception as e:
        logger.exception("Failed to stop recording")
        return jsonify({"error": str(e)}), 500


# ── Active recordings ────────────────────────────────────────────

@trace_bp.route("/trace/active")
def trace_active():
    """List active (in-progress) recording trace_ids."""
    try:
        ids = active_recordings()
        return jsonify({"active": ids})
    except Exception as e:
        logger.exception("Failed to list active recordings")
        return jsonify({"error": str(e)}), 500


# ── List saved traces ────────────────────────────────────────────

@trace_bp.route("/trace/list")
def trace_list():
    """List saved traces (newest-first).

    Query params:
        n — max results (default 20)
    """
    try:
        root = _project_root()
        n = request.args.get("n", 20, type=int)
        traces = list_traces(root, n=n)
        return jsonify({
            "traces": [t.model_dump(mode="json") for t in traces],
        })
    except Exception as e:
        logger.exception("Failed to list traces")
        return jsonify({"error": str(e)}), 500


# ── Get single trace ─────────────────────────────────────────────

@trace_bp.route("/trace/get")
def trace_get():
    """Get a single saved trace by ID.

    Query params:
        trace_id — the trace to retrieve (required)
    """
    try:
        root = _project_root()
        trace_id = request.args.get("trace_id", "")
        if not trace_id:
            return jsonify({"error": "trace_id is required"}), 400

        trace = get_trace(root, trace_id)
        if trace is None:
            return jsonify({"error": f"Trace not found: {trace_id}"}), 404

        return jsonify({
            "trace": trace.model_dump(mode="json"),
        })
    except Exception as e:
        logger.exception("Failed to get trace")
        return jsonify({"error": str(e)}), 500


# ── Get trace events ─────────────────────────────────────────────

@trace_bp.route("/trace/events")
def trace_events():
    """Get events for a saved trace.

    Query params:
        trace_id — the trace to retrieve events for (required)
    """
    try:
        root = _project_root()
        trace_id = request.args.get("trace_id", "")
        if not trace_id:
            return jsonify({"error": "trace_id is required"}), 400

        events = get_trace_events(root, trace_id)
        return jsonify({
            "trace_id": trace_id,
            "events": events,
        })
    except Exception as e:
        logger.exception("Failed to get trace events")
        return jsonify({"error": str(e)}), 500


# ── Share trace ─────────────────────────────────────────────────────────

@trace_bp.route("/trace/share", methods=["POST"])
def trace_share():
    """Share a trace — commit to git so it’s visible to others.

    Body (JSON):
        trace_id — the trace to share (required)
    """
    try:
        root = _project_root()
        body = request.get_json(silent=True) or {}
        trace_id = body.get("trace_id", "")
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
                post_trace_to_chat(root, trace)
            except Exception as e:
                logger.warning("Failed to post trace to chat: %s", e)

        # Push in background so other machines see it
        from src.core.services.ledger.worktree import push_ledger_branch
        threading.Thread(target=push_ledger_branch, args=(root,), daemon=True).start()

        return jsonify({"trace_id": trace_id, "shared": True})
    except Exception as e:
        logger.exception("Failed to share trace")
        return jsonify({"error": str(e)}), 500


# ── Unshare trace ───────────────────────────────────────────────────────

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
        from src.core.services.ledger.worktree import push_ledger_branch
        threading.Thread(target=push_ledger_branch, args=(root,), daemon=True).start()

        return jsonify({"trace_id": trace_id, "shared": False})
    except Exception as e:
        logger.exception("Failed to unshare trace")
        return jsonify({"error": str(e)}), 500


# ── Update trace ────────────────────────────────────────────────────────

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
