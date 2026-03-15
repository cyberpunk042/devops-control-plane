"""
Server lifecycle routes — status and restart.

Blueprint: server_bp
Prefix: /api
"""

from __future__ import annotations

import logging

from flask import Blueprint, current_app, jsonify, request

from src.core.services.run_tracker import run_tracked

logger = logging.getLogger(__name__)

server_bp = Blueprint("server", __name__)


@server_bp.route("/server/status")
def server_status_route():  # type: ignore[no-untyped-def]
    """Return server process status — PID, uptime, CWD, port."""
    from src.core.services.server_lifecycle import server_status

    root = current_app.config["PROJECT_ROOT"]
    host = current_app.config.get("SERVER_HOST", "")
    port = current_app.config.get("SERVER_PORT", 0)
    result = server_status(root, host=host, port=port)
    # Include port fallback info for frontend banner
    fallback = current_app.config.get("PORT_FALLBACK", {})
    result["fallback_mode"] = fallback.get("active", False)
    if fallback.get("active"):
        result["preferred_port"] = fallback["preferred_port"]
        result["actual_port"] = fallback["actual_port"]
        result["config_path"] = fallback.get("config_path", "project.yml")
    return jsonify(result)


@server_bp.route("/server/restart", methods=["POST"])
@run_tracked("setup", "setup:server_restart")
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

    # request_restart() schedules os._exit(42) after a short delay
    # and returns immediately so we can send a proper HTTP response.
    # It only returns an error dict if the signal file can't be written.
    result = request_restart(root, new_cwd=new_cwd)

    if result and "error" in result:
        return jsonify(result), 500
    return jsonify(result)


@server_bp.route("/server/factory-reset", methods=["POST"])
@run_tracked("destroy", "destroy:factory_reset")
def server_factory_reset_route():  # type: ignore[no-untyped-def]
    """Factory reset: clear .state/ folder and restart.

    Writes a ``.factory-reset-signal`` file and triggers a restart.
    On next startup, the server detects this signal and clears ``.state/``
    BEFORE initializing anything — no race with background workers.

    Does NOT touch project.yml, source code, git history, .ledger/ data,
    or .agent/ docs.
    """
    from src.core.services.server_lifecycle import request_restart

    root = current_app.config["PROJECT_ROOT"]
    signal_path = root / ".factory-reset-signal"

    logger.warning("Factory reset requested — writing signal file")

    try:
        signal_path.write_text("factory-reset\n", encoding="utf-8")
    except Exception as exc:
        logger.exception("Factory reset: failed to write signal file")
        return jsonify({"error": str(exc)}), 500

    result = request_restart(root)
    if result and "error" in result:
        return jsonify(result), 500
    return jsonify({"status": "factory_reset", "message": "Signal written, restarting"})


# ── Server settings (feature toggles) ──────────────────────────


@server_bp.route("/server/settings", methods=["GET"])
def server_settings_get():  # type: ignore[no-untyped-def]
    """Return server-side feature toggle settings."""
    from src.core.services.server_settings import load_settings

    root = current_app.config["PROJECT_ROOT"]
    return jsonify(load_settings(root))


@server_bp.route("/server/settings", methods=["PUT"])
@run_tracked("setup", "setup:server_settings")
def server_settings_put():  # type: ignore[no-untyped-def]
    """Update server-side feature toggle settings.

    JSON body: partial dict of settings to update.
    Returns the full merged settings after save.

    NOTE: Changing ``peek_index_enabled`` controls peek + symbols only.
    The index watcher always runs. Takes effect on next cycle.
    """
    from src.core.services.server_settings import (
        load_settings,
        save_settings,
        toggle_file_logging,
    )

    root = current_app.config["PROJECT_ROOT"]
    data = request.get_json(silent=True) or {}

    old = load_settings(root)
    merged = save_settings(root, {**old, **data})

    # peek_index_enabled takes effect on next index watcher cycle (no restart needed)
    # file_logging_enabled takes effect immediately
    if old.get("file_logging_enabled") != merged.get("file_logging_enabled"):
        toggle_file_logging(root, merged["file_logging_enabled"])

    return jsonify({
        "settings": merged,
        "needs_restart": False,  # no settings currently require restart
    })


# ── Accept fallback port (update project.yml) ──────────────────


@server_bp.route("/server/accept-port", methods=["POST"])
def server_accept_port():  # type: ignore[no-untyped-def]
    """Update web.port in project.yml to the given port.

    JSON body:
        port: int — the new port to write into project.yml

    Returns ``{"ok": True}`` on success, ``{"error": "..."}`` on failure.
    The caller should offer a restart afterward.
    """
    import yaml

    data = request.get_json(silent=True) or {}
    new_port = data.get("port")
    if not isinstance(new_port, int) or new_port < 1:
        return jsonify({"error": "Invalid port"}), 400

    root = current_app.config["PROJECT_ROOT"]
    yml_path = root / "project.yml"

    try:
        raw = yml_path.read_text(encoding="utf-8")
        cfg = yaml.safe_load(raw) or {}

        # Ensure web section exists
        if "web" not in cfg:
            cfg["web"] = {}
        cfg["web"]["port"] = new_port

        yaml_content = yaml.dump(
            cfg,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
        yml_path.write_text(yaml_content, encoding="utf-8")
    except Exception as e:
        return jsonify({"error": f"Failed to update project.yml: {e}"}), 500

    return jsonify({"ok": True, "port": new_port})
