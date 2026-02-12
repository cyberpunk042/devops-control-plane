"""
Admin API — Backup archive management endpoints.

Thin HTTP wrappers over ``src.core.services.backup_ops``.

Blueprint: backup_bp (imported from routes_backup)
Prefix: /api
Routes:
    /api/backup/export           — create a backup archive from selected items
    /api/backup/list             — list backups in .backup/ of a target folder
    /api/backup/preview          — list files inside a backup archive
    /api/backup/download/<fn>    — download a backup archive
    /api/backup/upload           — upload an archive into a folder's .backup/
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from flask import jsonify, request, send_file

from src.core.services import backup_ops
from .routes_backup import backup_bp, _project_root

logger = logging.getLogger(__name__)


# ── Export (from selected paths) ───────────────────────────────────


@backup_bp.route("/backup/export", methods=["POST"])
def api_export():  # type: ignore[no-untyped-def]
    """Create a backup archive from selected files/folders."""
    data = request.get_json(silent=True) or {}

    result = backup_ops.create_backup(
        _project_root(),
        data.get("target_folder", "").strip(),
        data.get("paths", []),
        label=data.get("label", "admin_export"),
        decrypt_enc=data.get("decrypt_enc", False),
        encrypt_archive_flag=data.get("encrypt_archive", False),
        custom_name=data.get("custom_name", "").strip(),
    )

    if "error" in result:
        code = 404 if "not found" in result["error"].lower() else 400
        return jsonify(result), code
    return jsonify(result)


# ── List backups for a folder ──────────────────────────────────────


@backup_bp.route("/backup/list")
def api_list():  # type: ignore[no-untyped-def]
    """List backups in a folder's .backup/ directory."""
    rel_path = request.args.get("path", "").strip()
    check_release = request.args.get("check_release", "").lower() == "true"

    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    result = backup_ops.list_backups(_project_root(), rel_path, check_release=check_release)
    return jsonify(result)


# ── Preview contents of a backup archive ───────────────────────────


@backup_bp.route("/backup/preview")
def api_preview():  # type: ignore[no-untyped-def]
    """Preview the file tree inside a backup archive."""
    backup_path = request.args.get("path", "").strip()
    if not backup_path:
        return jsonify({"error": "Missing 'path'"}), 400

    result = backup_ops.preview_backup(_project_root(), backup_path)

    if "error" in result:
        code = 404 if "not found" in result["error"].lower() else 400
        return jsonify(result), code
    return jsonify(result)


# ── Download ────────────────────────────────────────────────────────


@backup_bp.route("/backup/download/<path:filepath>")
def api_download(filepath: str):  # type: ignore[no-untyped-def]
    """Download a backup archive by its relative path."""
    root = _project_root()
    file_path = (root / filepath).resolve()

    # Security
    try:
        file_path.relative_to(root)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not file_path.exists() or not (
        file_path.name.endswith(".tar.gz") or file_path.name.endswith(".tar.gz.enc")
    ):
        return jsonify({"error": "File not found"}), 404

    return send_file(
        file_path,
        mimetype="application/gzip",
        as_attachment=True,
        download_name=file_path.name,
    )


# ── Upload ──────────────────────────────────────────────────────────


@backup_bp.route("/backup/upload", methods=["POST"])
def api_upload():  # type: ignore[no-untyped-def]
    """Upload a backup archive into a folder's .backup/."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    target_folder = request.form.get("target_folder", "docs")

    if not file.filename or not file.filename.endswith((".tar.gz", ".gz", ".tar.gz.enc", ".enc")):
        return jsonify({"error": "File must be a .tar.gz or .tar.gz.enc archive"}), 400

    folder = backup_ops.resolve_folder(_project_root(), target_folder)
    if folder is None:
        return jsonify({"error": f"Folder not found: {target_folder}"}), 404

    root = _project_root()
    bak_dir = backup_ops.backup_dir_for(folder)

    # Generate safe name
    if backup_ops.safe_backup_name(file.filename):
        dest_name = file.filename
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        is_enc = file.filename.endswith(".enc")
        dest_name = f"backup_{ts}.tar.gz{'.enc' if is_enc else ''}"

    dest = bak_dir / dest_name
    file.save(str(dest))

    # Try to read manifest (only works for unencrypted archives)
    manifest = None
    is_encrypted = dest.name.endswith(".enc")
    if not is_encrypted:
        manifest = backup_ops.read_manifest(dest)
        if not manifest:
            dest.unlink()
            return jsonify({"error": "Invalid archive: no backup_manifest.json found"}), 400

    return jsonify({
        "success": True,
        "filename": dest_name,
        "folder": target_folder,
        "full_path": str(dest.relative_to(root)),
        "size_bytes": dest.stat().st_size,
        "encrypted": is_encrypted,
        "manifest": manifest,
    })
