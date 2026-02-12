"""
Vault API routes — REST endpoints for the secrets vault.

Thin HTTP wrappers over ``src.core.services.vault`` and
``src.core.services.vault_env_ops``.

Blueprint: vault_bp
Prefix: /api/vault
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import vault_env_ops
from . import vault

vault_bp = Blueprint("vault", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"]).resolve()


def _env_path() -> Path:
    """Resolve .env file path from optional ``?env=`` query param."""
    env_name = request.args.get("env", "").strip().lower()
    root = _project_root()
    if not env_name:
        return root / ".env"
    return root / f".env.{env_name}"


# ── Status ───────────────────────────────────────────────────────────


@vault_bp.route("/vault/status")
def vault_status():
    """Get vault status for the default .env."""
    root = _project_root()
    return jsonify(vault.vault_status(root / ".env"))


# ── Active environment (file swapping) ───────────────────────────


@vault_bp.route("/vault/active-env")
def vault_active_env():
    """Return the currently active environment name."""
    active = vault_env_ops.read_active_env(_project_root())
    return jsonify({"active": active})


@vault_bp.route("/vault/activate-env", methods=["POST"])
def vault_activate_env():
    """Swap .env files to make a different environment active."""
    data = request.get_json(silent=True) or {}

    result = vault_env_ops.activate_env(
        _project_root(),
        data.get("name", "").strip(),
        vault_module=vault,
    )

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── Lock ─────────────────────────────────────────────────────────────


@vault_bp.route("/vault/lock", methods=["POST"])
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


# ── Unlock ───────────────────────────────────────────────────────────


@vault_bp.route("/vault/unlock", methods=["POST"])
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


# ── Register Passphrase ──────────────────────────────────────────────


@vault_bp.route("/vault/register", methods=["POST"])
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


# ── Auto-lock Config ─────────────────────────────────────────────────


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

    vault.set_auto_lock_minutes(minutes)
    return jsonify({
        "success": True,
        "auto_lock_minutes": minutes,
        "message": f"Auto-lock set to {minutes}min"
                   if minutes > 0 else "Auto-lock disabled",
    })


# ── Detect Secret Files ─────────────────────────────────────────────


@vault_bp.route("/vault/secrets")
def vault_secrets():
    """List detected secret files and their vault status."""
    root = _project_root()
    files = vault.detect_secret_files(root)
    return jsonify({"files": files})


# ── Read .env Keys (masked) ─────────────────────────────────────────


@vault_bp.route("/vault/keys")
def vault_keys():
    """List .env keys with masked values (no raw secrets exposed)."""
    env_path = _env_path()
    vault_path = vault._vault_path_for(env_path)

    result = vault_env_ops.list_keys_enriched(env_path, vault_path)
    return jsonify(result)


# ── .env Template Sections ───────────────────────────────────────────


@vault_bp.route("/vault/templates")
def vault_templates():
    """Return available .env template sections."""
    return jsonify({"sections": vault_env_ops.get_templates()})


# ── Create .env ──────────────────────────────────────────────────────


@vault_bp.route("/vault/create", methods=["POST"])
def vault_create():
    """Create a new .env file from template sections and/or key-value pairs."""
    data = request.get_json(silent=True) or {}

    result = vault_env_ops.create_env(
        _env_path(),
        entries=data.get("entries", []),
        template_sections=data.get("template_sections", []),
    )

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── Add Keys to .env ────────────────────────────────────────────────


@vault_bp.route("/vault/add-keys", methods=["POST"])
def vault_add_keys():
    """Add or update key-value pairs in an existing .env file."""
    data = request.get_json(silent=True) or {}

    result = vault_env_ops.add_keys(
        _env_path(),
        data.get("entries", []),
        section=data.get("section", "").strip(),
    )

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── Move Key ────────────────────────────────────────────────────────


@vault_bp.route("/vault/move-key", methods=["POST"])
def vault_move_key():
    """Move a key from its current section to a different one."""
    data = request.get_json(silent=True) or {}

    result = vault_env_ops.move_key(
        _env_path(),
        data.get("key", "").strip(),
        data.get("section", "").strip(),
    )

    if "error" in result:
        code = 404 if "not found" in result.get("error", "") else 400
        return jsonify(result), code
    return jsonify(result)


# ── Rename Section ──────────────────────────────────────────────────


@vault_bp.route("/vault/rename-section", methods=["POST"])
def vault_rename_section():
    """Rename a section comment in .env."""
    data = request.get_json(silent=True) or {}

    result = vault_env_ops.rename_section(
        _env_path(),
        data.get("old_name", "").strip(),
        data.get("new_name", "").strip(),
    )

    if "error" in result:
        code = 404 if "not found" in result.get("error", "") else 400
        return jsonify(result), code
    return jsonify(result)


# ── Update Key ──────────────────────────────────────────────────────


@vault_bp.route("/vault/update-key", methods=["POST"])
def vault_update_key():
    """Update a single key's value in the .env file."""
    data = request.get_json(silent=True) or {}

    result = vault_env_ops.update_key(
        _env_path(),
        data.get("key", "").strip(),
        data.get("value", ""),
    )

    if "error" in result:
        code = 404 if "not found" in result.get("error", "") else 400
        return jsonify(result), code
    return jsonify(result)


# ── Delete Key ──────────────────────────────────────────────────────


@vault_bp.route("/vault/delete-key", methods=["POST"])
def vault_delete_key():
    """Remove a key from the .env file."""
    data = request.get_json(silent=True) or {}

    result = vault_env_ops.delete_key(
        _env_path(),
        data.get("key", "").strip(),
    )

    if "error" in result:
        code = 404 if "not found" in result.get("error", "") else 400
        return jsonify(result), code
    return jsonify(result)


# ── Get raw value for a single key ───────────────────────────────────


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


# ── Toggle local-only ────────────────────────────────────────────────


@vault_bp.route("/vault/toggle-local-only", methods=["POST"])
def vault_toggle_local_only():
    """Toggle the # local-only comment on a .env key."""
    data = request.get_json(silent=True) or {}

    result = vault_env_ops.toggle_local_only(
        _env_path(),
        data.get("key", "").strip(),
        local_only=data.get("local_only", True),
    )

    if "error" in result:
        code = 404 if "not found" in result.get("error", "") else 400
        return jsonify(result), code
    return jsonify(result)


# ── Set metadata tags ────────────────────────────────────────────────


@vault_bp.route("/vault/set-meta", methods=["POST"])
def vault_set_meta():
    """Set or update @ metadata tags on a .env key."""
    data = request.get_json(silent=True) or {}

    result = vault_env_ops.set_meta(
        _env_path(),
        data.get("key", "").strip(),
        data.get("meta_tags", "").strip(),
    )

    if "error" in result:
        code = 404 if "not found" in result.get("error", "") else 400
        return jsonify(result), code
    return jsonify(result)


# ── Export ───────────────────────────────────────────────────────────


@vault_bp.route("/vault/export", methods=["POST"])
def vault_export():
    """Create an encrypted export of a secret file."""
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    filename = data.get("filename", ".env")

    if not password:
        return jsonify({"error": "Missing password"}), 400

    file_path = _project_root() / filename

    try:
        envelope = vault.export_vault_file(file_path, password)
        return jsonify({"success": True, "envelope": envelope})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ── Import ───────────────────────────────────────────────────────────


@vault_bp.route("/vault/import", methods=["POST"])
def vault_import():
    """Import and decrypt an exported vault file."""
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    vault_data = data.get("vault_data")
    target = data.get("target", ".env")
    dry_run = data.get("dry_run", False)

    if not password:
        return jsonify({"error": "Missing password"}), 400
    if not vault_data:
        return jsonify({"error": "Missing vault_data"}), 400

    target_path = _project_root() / target

    try:
        result = vault.import_vault_file(
            vault_data, target_path, password, dry_run=dry_run,
        )
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
