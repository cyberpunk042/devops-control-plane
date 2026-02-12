"""
Admin API — Backup restore / import / wipe / delete endpoints.

Thin HTTP wrappers over ``src.core.services.backup_ops``.

Blueprint: backup_bp (imported from routes_backup)
Prefix: /api
Routes:
    /api/backup/restore  — restore (overwrite) from a .backup/ archive
    /api/backup/import   — import (additive) from an archive
    /api/backup/wipe     — factory-reset a folder (with optional backup)
    /api/backup/delete   — delete a .backup/ archive
"""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import backup_ops
from .routes_backup import backup_bp, _project_root


# ── Restore ────────────────────────────────────────────────────────


@backup_bp.route("/backup/restore", methods=["POST"])
def api_restore():  # type: ignore[no-untyped-def]
    """Restore (OVERRIDE) files from a backup archive."""
    data = request.get_json(silent=True) or {}

    result = backup_ops.restore_backup(
        _project_root(),
        data.get("backup_path", "").strip(),
        paths=data.get("paths"),
        wipe_first=data.get("wipe_first", False),
        target_folder=data.get("target_folder", "").strip(),
        encrypt_restored=data.get("encrypt_restored", False),
        decrypt_restored=data.get("decrypt_restored", False),
    )

    if "error" in result:
        code = 404 if "not found" in result["error"].lower() else 400
        return jsonify(result), code
    return jsonify(result)


# ── Import (additive) ──────────────────────────────────────────────


@backup_bp.route("/backup/import", methods=["POST"])
def api_import():  # type: ignore[no-untyped-def]
    """Import (ADDITIVE) from a backup archive. Existing files are skipped."""
    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "").strip()

    if not backup_path:
        return jsonify({"error": "Missing 'backup_path'"}), 400

    result = backup_ops.import_backup(_project_root(), backup_path)

    if "error" in result:
        code = 404 if "not found" in result["error"].lower() else 400
        return jsonify(result), code
    return jsonify(result)


# ── Wipe (Factory Reset) ──────────────────────────────────────────


@backup_bp.route("/backup/wipe", methods=["POST"])
def api_wipe():  # type: ignore[no-untyped-def]
    """Factory-reset a folder: optionally back up first, then delete selected files."""
    data = request.get_json(silent=True) or {}

    result = backup_ops.wipe_folder(
        _project_root(),
        data.get("target_folder", "").strip(),
        data.get("paths", []),
        create_backup_first=data.get("create_backup", True),
    )

    if "error" in result:
        code = 404 if "not found" in result["error"].lower() else 400
        return jsonify(result), code
    return jsonify(result)


# ── Delete a backup ────────────────────────────────────────────────


@backup_bp.route("/backup/delete", methods=["POST"])
def api_delete():  # type: ignore[no-untyped-def]
    """Delete a backup archive."""
    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "").strip()

    if not backup_path:
        return jsonify({"error": "Missing 'backup_path'"}), 400

    root = _project_root()
    file_path = (root / backup_path).resolve()

    try:
        file_path.relative_to(root)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if ".backup" not in file_path.parts:
        return jsonify({"error": "Can only delete files in .backup/ directories"}), 400

    # This route has extra validation (.backup check) beyond what backup_ops.delete_backup does,
    # plus it calls cleanup_release_sidecar directly. Keep the domain call.
    from src.core.services.content_release import cleanup_release_sidecar
    cleanup_release_sidecar(file_path, root)

    result = backup_ops.delete_backup(root, backup_path)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"success": True, "deleted": backup_path})
