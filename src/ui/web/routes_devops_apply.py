"""
DevOps wizard — setup actions (generate configs, apply settings).

Blueprint: devops_bp (imported from routes_devops)
Prefix: /api

Thin HTTP wrappers over ``src.core.services.wizard_ops``.

Endpoints:
    POST    /wizard/setup       — execute a setup action
    POST    /wizard/compose-ci  — compose CI/CD workflow files
    POST    /wizard/validate    — validate wizard state before generation
    POST    /wizard/check-tools — check required CLI tools for wizard state
    DELETE  /wizard/config      — delete wizard-generated config files
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

    Body: {"target": "docker" | "k8s" | "ci" | "skaffold" | "terraform" | "all"}
    """
    from src.core.services.wizard_ops import delete_generated_configs

    data = request.get_json(silent=True) or {}
    target = data.get("target", "")

    if not target:
        return jsonify({"ok": False, "error": "Missing 'target'"}), 400

    result = delete_generated_configs(_project_root(), target)
    return jsonify(result)


@devops_bp.route("/wizard/compose-ci", methods=["POST"])
def wizard_compose_ci():  # type: ignore[no-untyped-def]
    """Compose CI/CD workflow files from wizard state.

    Body: {
        "state": { ... wizard state dict ... },
        "strategy": "unified" | "split" (default: "unified"),
        "project_name": "MyProject" (optional),
    }

    Returns:
        {"ok": true, "files": [{"path": "...", "content": "..."}]}
    """
    from src.core.services.ci_compose import compose_ci_workflows

    data = request.get_json(silent=True)
    if not data or "state" not in data:
        return jsonify({"ok": False, "error": "Missing 'state' in body"}), 400

    state = data["state"]
    strategy = data.get("strategy", "unified")
    project_name = data.get("project_name", "")

    try:
        files = compose_ci_workflows(
            state, strategy=strategy, project_name=project_name,
        )
        return jsonify({
            "ok": True,
            "files": [
                {"path": f.path, "content": f.content}
                for f in files
            ],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@devops_bp.route("/wizard/validate", methods=["POST"])
def wizard_validate():  # type: ignore[no-untyped-def]
    """Validate wizard state before generation.

    Body: {"state": { ... wizard state dict ... }}

    Returns:
        {"ok": true/false, "errors": [...], "warnings": [...]}
    """
    from src.core.services.wizard_validate import validate_wizard_state

    data = request.get_json(silent=True)
    if not data or "state" not in data:
        return jsonify({"ok": False, "error": "Missing 'state' in body"}), 400

    result = validate_wizard_state(
        data["state"], project_root=_project_root(),
    )
    return jsonify(result)


@devops_bp.route("/wizard/check-tools", methods=["POST"])
def wizard_check_tools():  # type: ignore[no-untyped-def]
    """Check required CLI tools for the given wizard state.

    Body: {"state": { ... wizard state dict ... }}

    Returns:
        {"ok": true/false, "tools": {...}, "missing": [...],
         "install_available": [...]}
    """
    from src.core.services.wizard_validate import check_required_tools

    data = request.get_json(silent=True)
    if not data or "state" not in data:
        return jsonify({"ok": False, "error": "Missing 'state' in body"}), 400

    result = check_required_tools(data["state"])
    return jsonify(result)
