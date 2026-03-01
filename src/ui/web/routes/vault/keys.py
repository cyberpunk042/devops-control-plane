"""Vault key management — CRUD on .env entries."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import vault_env_ops

from . import vault_bp
from .helpers import _env_path


@vault_bp.route("/vault/keys")
def vault_keys():
    """List .env keys with masked values (no raw secrets exposed)."""
    result = vault_env_ops.list_keys_enriched(_env_path())
    return jsonify(result)


@vault_bp.route("/vault/add-keys", methods=["POST"])
def vault_add_keys():
    """Add or update key-value pairs in an existing .env file."""
    data = request.get_json(silent=True) or {}
    env_path = _env_path()
    entries = data.get("entries", [])
    section = data.get("section", "").strip()

    result = vault_env_ops.add_keys(
        env_path,
        entries,
        section=section,
    )

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@vault_bp.route("/vault/update-key", methods=["POST"])
def vault_update_key():
    """Update a single key's value in the .env file."""
    data = request.get_json(silent=True) or {}
    env_path = _env_path()
    key = data.get("key", "").strip()

    result = vault_env_ops.update_key(env_path, key, data.get("value", ""))

    if "error" in result:
        code = 404 if "not found" in result.get("error", "") else 400
        return jsonify(result), code

    return jsonify(result)


@vault_bp.route("/vault/delete-key", methods=["POST"])
def vault_delete_key():
    """Remove a key from the .env file."""
    data = request.get_json(silent=True) or {}
    env_path = _env_path()
    key = data.get("key", "").strip()

    result = vault_env_ops.delete_key(env_path, key)

    if "error" in result:
        code = 404 if "not found" in result.get("error", "") else 400
        return jsonify(result), code

    return jsonify(result)


@vault_bp.route("/vault/move-key", methods=["POST"])
def vault_move_key():
    """Move a key from its current section to a different one."""
    data = request.get_json(silent=True) or {}
    env_path = _env_path()
    key = data.get("key", "").strip()
    section = data.get("section", "").strip()

    result = vault_env_ops.move_key(env_path, key, section)

    if "error" in result:
        code = 404 if "not found" in result.get("error", "") else 400
        return jsonify(result), code

    return jsonify(result)


@vault_bp.route("/vault/rename-section", methods=["POST"])
def vault_rename_section():
    """Rename a section comment in .env."""
    data = request.get_json(silent=True) or {}
    env_path = _env_path()
    old_name = data.get("old_name", "").strip()
    new_name = data.get("new_name", "").strip()

    result = vault_env_ops.rename_section(env_path, old_name, new_name)

    if "error" in result:
        code = 404 if "not found" in result.get("error", "") else 400
        return jsonify(result), code

    return jsonify(result)


@vault_bp.route("/vault/raw-value", methods=["POST"])
def vault_raw_value():
    """Return the raw value of a single .env key."""
    data = request.get_json(silent=True) or {}

    result = vault_env_ops.get_raw_value(
        _env_path(),
        data.get("key", "").strip(),
    )

    if "error" in result:
        code = 404 if "not found" in result.get("error", "") else 400
        return jsonify(result), code
    return jsonify(result)


@vault_bp.route("/vault/toggle-local-only", methods=["POST"])
def vault_toggle_local_only():
    """Toggle the # local-only comment on a .env key."""
    data = request.get_json(silent=True) or {}
    env_path = _env_path()
    key = data.get("key", "").strip()
    local_only = data.get("local_only", True)

    result = vault_env_ops.toggle_local_only(env_path, key, local_only=local_only)

    if "error" in result:
        code = 404 if "not found" in result.get("error", "") else 400
        return jsonify(result), code

    return jsonify(result)


@vault_bp.route("/vault/set-meta", methods=["POST"])
def vault_set_meta():
    """Set or update @ metadata tags on a .env key."""
    data = request.get_json(silent=True) or {}
    env_path = _env_path()
    key = data.get("key", "").strip()
    meta_tags = data.get("meta_tags", "").strip()

    result = vault_env_ops.set_meta(env_path, key, meta_tags)

    if "error" in result:
        code = 404 if "not found" in result.get("error", "") else 400
        return jsonify(result), code

    return jsonify(result)
