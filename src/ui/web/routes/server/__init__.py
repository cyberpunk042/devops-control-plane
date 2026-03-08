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


# ── Server settings (feature toggles) ──────────────────────────


@server_bp.route("/server/settings", methods=["GET"])
def server_settings_get():  # type: ignore[no-untyped-def]
    """Return server-side feature toggle settings."""
    from src.core.services.server_settings import load_settings

    root = current_app.config["PROJECT_ROOT"]
    return jsonify(load_settings(root))


@server_bp.route("/server/settings", methods=["PUT"])
def server_settings_put():  # type: ignore[no-untyped-def]
    """Update server-side feature toggle settings.

    JSON body: partial dict of settings to update.
    Returns the full merged settings after save.

    NOTE: Changing ``peek_index_enabled`` takes effect on next
    server restart.  ``file_logging_enabled`` takes effect immediately.
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

    # Detect if a restart-requiring setting changed
    needs_restart = (
        old.get("peek_index_enabled") != merged.get("peek_index_enabled")
    )

    # Apply file logging toggle immediately (no restart needed)
    if old.get("file_logging_enabled") != merged.get("file_logging_enabled"):
        toggle_file_logging(root, merged["file_logging_enabled"])

    return jsonify({
        "settings": merged,
        "needs_restart": needs_restart,
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
