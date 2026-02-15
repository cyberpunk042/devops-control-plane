from __future__ import annotations

import logging

from flask import jsonify, request

from src.core.services import backup_ops
from .routes_backup import backup_bp, _project_root

logger = logging.getLogger(__name__)


# ── Upload to GitHub Release ──────────────────────────────────────


@backup_bp.route("/backup/upload-release", methods=["POST"])
def api_upload_release():  # type: ignore[no-untyped-def]
    """Upload a file to a GitHub Release as an artifact."""
    data = request.get_json(silent=True) or {}
    backup_path = (data.get("path") or data.get("backup_path", "")).strip()

    result = backup_ops.upload_backup_to_release(_project_root(), backup_path)

    if "error" in result:
        code = result.pop("_status", 400)
        return jsonify(result), code
    return jsonify(result)


# ── Encrypt / Decrypt existing backups ─────────────────────────────


@backup_bp.route("/backup/encrypt", methods=["POST"])
def api_encrypt_backup():  # type: ignore[no-untyped-def]
    """Encrypt an existing .tar.gz backup in place."""
    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "").strip()
    root = _project_root()

    if not backup_path:
        return jsonify({"error": "Missing 'backup_path'"}), 400

    result = backup_ops.encrypt_backup_inplace(root, backup_path)
    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@backup_bp.route("/backup/decrypt", methods=["POST"])
def api_decrypt_backup():  # type: ignore[no-untyped-def]
    """Decrypt an existing .tar.gz.enc backup in place."""
    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "").strip()
    root = _project_root()

    if not backup_path:
        return jsonify({"error": "Missing 'backup_path'"}), 400

    result = backup_ops.decrypt_backup_inplace(root, backup_path)
    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


# ── Delete release artifact ────────────────────────────────────────


@backup_bp.route("/backup/delete-release", methods=["POST"])
def api_delete_release():  # type: ignore[no-untyped-def]
    """Delete a file's GitHub Release artifact."""
    data = request.get_json(silent=True) or {}
    backup_path = (data.get("path") or data.get("backup_path", "")).strip()

    result = backup_ops.delete_backup_release(_project_root(), backup_path)

    if "error" in result:
        code = result.pop("_status", 400)
        return jsonify(result), code
    return jsonify(result)


# ── Rename a backup ────────────────────────────────────────────────


@backup_bp.route("/backup/rename", methods=["POST"])
def api_rename_backup():  # type: ignore[no-untyped-def]
    """Rename a backup archive file."""
    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "").strip()
    new_name = data.get("new_name", "").strip()

    if not backup_path or not new_name:
        return jsonify({"error": "Missing 'backup_path' or 'new_name'"}), 400

    safe_name = backup_ops.sanitize_backup_name(
        new_name, is_encrypted=backup_path.endswith(".enc"),
    )

    result = backup_ops.rename_backup(_project_root(), backup_path, safe_name)
    if "error" in result:
        code = 409 if "already exists" in result.get("error", "") else 400
        return jsonify(result), code

    return jsonify({"success": True, **result})


# ── Mark backup as git-tracked (special) ───────────────────────────


@backup_bp.route("/backup/mark-special", methods=["POST"])
def api_mark_special():  # type: ignore[no-untyped-def]
    """Force-add a backup to git (git add -f), bypassing .gitignore."""
    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "").strip()
    unmark = data.get("unmark", False)

    if not backup_path:
        return jsonify({"error": "Missing 'backup_path'"}), 400

    root = _project_root()
    result = backup_ops.mark_special(root, backup_path, unmark=unmark)
    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)
