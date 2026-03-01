"""Trace queries — list, get, events."""

from __future__ import annotations

import logging

from flask import jsonify, request

from src.core.services.trace import get_trace, get_trace_events, list_traces
from src.ui.web.helpers import project_root as _project_root

from . import trace_bp

logger = logging.getLogger(__name__)


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
