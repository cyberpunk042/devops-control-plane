"""Docker SSE streaming — real-time output for long-running operations."""

from __future__ import annotations

import json

from flask import Response, jsonify, request

from src.core.services import docker_ops
from src.ui.web.helpers import project_root as _project_root

from . import docker_bp


_ALLOWED_STREAM_ACTIONS = frozenset({"up", "down", "restart", "build", "build-nc", "prune"})


@docker_bp.route("/docker/stream/<action>", methods=["POST"])
def docker_stream(action: str):  # type: ignore[no-untyped-def]
    """SSE stream for a Docker action (up, down, restart, build, prune).

    Streams real-time output as text/event-stream events so the browser
    can display progress without hitting a timeout.
    """
    if action not in _ALLOWED_STREAM_ACTIONS:
        return jsonify({"error": f"Unknown action: {action}"}), 400

    data = request.get_json(silent=True) or {}
    service = data.get("service")  # optional: target a specific service
    root = _project_root()

    def sse():  # type: ignore[no-untyped-def]
        for event in docker_ops.docker_action_stream(root, action, service=service):
            yield f"data: {json.dumps(event)}\n\n"

    return Response(sse(), mimetype="text/event-stream")
