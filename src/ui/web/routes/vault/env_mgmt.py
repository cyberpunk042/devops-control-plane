"""Vault environment management — active env, templates, create .env."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import vault, vault_env_ops
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import project_root as _project_root

from . import vault_bp
from .helpers import _env_path


@vault_bp.route("/vault/active-env")
def vault_active_env():
    """Return the currently active environment name."""
    active = vault_env_ops.read_active_env(_project_root())
    return jsonify({"active": active})


@vault_bp.route("/vault/activate-env", methods=["POST"])
def vault_activate_env():
    """Swap .env files to make a different environment active."""
    data = request.get_json(silent=True) or {}
    root = _project_root()
    name = data.get("name", "").strip()

    result = vault_env_ops.activate_env(root, name, vault_module=vault)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@vault_bp.route("/vault/templates")
def vault_templates():
    """Return available .env template sections."""
    return jsonify({"sections": vault_env_ops.get_templates()})


@vault_bp.route("/vault/create", methods=["POST"])
@run_tracked("setup", "setup:vault")
def vault_create():
    """Create a new .env file from template sections and/or key-value pairs."""
    data = request.get_json(silent=True) or {}
    env_path = _env_path()
    entries = data.get("entries", [])
    sections = data.get("template_sections", [])

    result = vault_env_ops.create_env(
        env_path,
        entries=entries,
        template_sections=sections,
    )

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)
