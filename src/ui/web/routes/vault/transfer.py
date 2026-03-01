"""Vault transfer — export and import encrypted vault files."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import vault
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import project_root as _project_root

from . import vault_bp


@vault_bp.route("/vault/export", methods=["POST"])
@run_tracked("backup", "backup:vault")
def vault_export():
    """Create an encrypted export of a secret file."""
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    filename = data.get("filename", ".env")
    root = _project_root()

    if not password:
        return jsonify({"error": "Missing password"}), 400

    file_path = root / filename

    try:
        envelope = vault.export_vault_file(file_path, password)
        return jsonify({"success": True, "envelope": envelope})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@vault_bp.route("/vault/import", methods=["POST"])
@run_tracked("restore", "restore:vault")
def vault_import():
    """Import and decrypt an exported vault file."""
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    vault_data = data.get("vault_data")
    target = data.get("target", ".env")
    dry_run = data.get("dry_run", False)
    root = _project_root()

    if not password:
        return jsonify({"error": "Missing password"}), 400
    if not vault_data:
        return jsonify({"error": "Missing vault_data"}), 400

    target_path = root / target

    try:
        result = vault.import_vault_file(
            vault_data, target_path, password, dry_run=dry_run,
        )
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
