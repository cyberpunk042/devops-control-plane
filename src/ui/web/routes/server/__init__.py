"""
Server lifecycle routes — status and restart.

Blueprint: server_bp
Prefix: /api
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

server_bp = Blueprint("server", __name__)


@server_bp.route("/server/status")
def server_status_route():  # type: ignore[no-untyped-def]
    """Return server process status — PID, uptime, CWD, port."""
    from src.core.services.server_lifecycle import server_status

    root = current_app.config["PROJECT_ROOT"]
    return jsonify(server_status(root))


@server_bp.route("/server/restart", methods=["POST"])
def server_restart_route():  # type: ignore[no-untyped-def]
    """Request a graceful server restart.

    JSON body (all optional):
        new_cwd: new working directory (e.g. after folder rename)

    The server writes a .restart-signal file and exits with code 42.
    The manage.sh wrapper catches this and re-launches the server.
    """
    from src.core.services.server_lifecycle import request_restart

    data = request.get_json(silent=True) or {}
    new_cwd = data.get("new_cwd")

    root = current_app.config["PROJECT_ROOT"]

    # request_restart() calls os._exit(42) — this never returns
    # It only returns a dict on error (e.g. can't write signal file)
    result = request_restart(root, new_cwd=new_cwd)

    # If we get here, there was an error
    if result and "error" in result:
        return jsonify(result), 500
    return jsonify({"ok": True, "message": "Restarting..."})
