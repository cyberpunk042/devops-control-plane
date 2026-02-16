"""
DevOps wizard — setup actions (generate configs, apply settings).

Blueprint: devops_bp (imported from routes_devops)
Prefix: /api

Thin HTTP wrappers over ``src.core.services.wizard_ops``.

Endpoints:
    POST    /wizard/setup   — execute a setup action
    DELETE  /wizard/config  — delete wizard-generated config files
"""

from __future__ import annotations

from pathlib import Path

from flask import current_app, jsonify, request

from src.ui.web.routes_devops import devops_bp


def _project_root() -> Path:
    return current_app.config["PROJECT_ROOT"]


@devops_bp.route("/wizard/setup", methods=["POST"])
def wizard_setup():  # type: ignore[no-untyped-def]
    """Execute a setup action using user-provided configuration."""
    from src.core.services.wizard_ops import wizard_setup as _setup

    data = request.get_json(silent=True) or {}
    action = data.get("action", "")
    root = _project_root()

    if not action:
        return jsonify({"ok": False, "error": "No action specified"}), 400

    try:
        result = _setup(root, action, data)
        if not result.get("ok"):
            return jsonify(result), 400
        return jsonify(result)

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@devops_bp.route("/wizard/config", methods=["DELETE"])
def wizard_delete_config():  # type: ignore[no-untyped-def]
    """Delete wizard-generated config files.

    Body: {"target": "docker" | "k8s" | "ci" | "terraform" | "all"}
    """
    from src.core.services.wizard_ops import delete_generated_configs

    data = request.get_json(silent=True) or {}
    target = data.get("target", "")

    if not target:
        return jsonify({"ok": False, "error": "Missing 'target'"}), 400

    result = delete_generated_configs(_project_root(), target)
    return jsonify(result)
