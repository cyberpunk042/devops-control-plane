"""Vault security — lock, unlock, register passphrase, auto-lock."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import vault
from src.core.services.run_tracker import run_tracked

from . import vault_bp
from .helpers import _env_path


@vault_bp.route("/vault/lock", methods=["POST"])
@run_tracked("setup", "setup:vault_lock")
def vault_lock():
    """Lock (encrypt) the .env file."""
    data = request.get_json(silent=True) or {}
    passphrase = data.get("passphrase", "")
    env_path = _env_path()

    if not passphrase:
        return jsonify({"error": "Missing passphrase"}), 400

    try:
        result = vault.lock_vault(env_path, passphrase)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@vault_bp.route("/vault/unlock", methods=["POST"])
@run_tracked("setup", "setup:vault_unlock")
def vault_unlock():
    """Unlock (decrypt) the .env.vault file."""
    data = request.get_json(silent=True) or {}
    passphrase = data.get("passphrase", "")
    env_path = _env_path()

    if not passphrase:
        return jsonify({"error": "Missing passphrase"}), 400

    try:
        result = vault.unlock_vault(env_path, passphrase)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@vault_bp.route("/vault/register", methods=["POST"])
@run_tracked("setup", "setup:vault_register")
def vault_register():
    """Register passphrase for auto-lock without modifying files."""
    data = request.get_json(silent=True) or {}
    passphrase = data.get("passphrase", "")
    env_path = _env_path()

    if not passphrase:
        return jsonify({"error": "Missing passphrase"}), 400

    try:
        result = vault.register_passphrase(passphrase, env_path)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@vault_bp.route("/vault/auto-lock", methods=["POST"])
def vault_auto_lock():
    """Configure auto-lock timeout."""
    data = request.get_json(silent=True) or {}
    minutes = data.get("minutes")

    if minutes is None:
        return jsonify({"error": "Missing 'minutes' field"}), 400

    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return jsonify({"error": "'minutes' must be an integer"}), 400

    result = vault.set_auto_lock_minutes(minutes)
    return jsonify(result)
