"""Trace recording — start, stop, active."""

from __future__ import annotations

import logging

from flask import jsonify, request

from src.core.services.trace import (
    active_recordings,
    save_trace,
    start_recording,
    stop_recording,
)
from src.ui.web.helpers import project_root as _project_root

from . import trace_bp

logger = logging.getLogger(__name__)


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


@trace_bp.route("/trace/active")
def trace_active():
    """List active (in-progress) recording trace_ids."""
    try:
        ids = active_recordings()
        return jsonify({"active": ids})
    except Exception as e:
        logger.exception("Failed to list active recordings")
        return jsonify({"error": str(e)}), 500
