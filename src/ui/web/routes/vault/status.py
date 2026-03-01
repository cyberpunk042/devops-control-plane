"""Vault status — detection endpoints."""

from __future__ import annotations

from flask import jsonify

from src.core.services import vault
from src.ui.web.helpers import project_root as _project_root

from . import vault_bp
from .helpers import _env_path


@vault_bp.route("/vault/status")
def vault_status():
    """Get vault status — respects ``?env=`` for multi-env mode."""
    return jsonify(vault.vault_status(_env_path()))


@vault_bp.route("/vault/secrets")
def vault_secrets():
    """List detected secret files and their vault status."""
    root = _project_root()
    files = vault.detect_secret_files(root)
    return jsonify({"files": files})
