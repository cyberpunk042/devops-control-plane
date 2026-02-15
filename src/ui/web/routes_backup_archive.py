from __future__ import annotations

from flask import jsonify, request, send_file

from src.core.services import backup_ops
from .routes_backup import backup_bp, _project_root


# ── Export (from selected paths) ───────────────────────────────────


@backup_bp.route("/backup/export", methods=["POST"])
def api_export():  # type: ignore[no-untyped-def]
    """Create a backup archive from selected files/folders."""
    data = request.get_json(silent=True) or {}
    root = _project_root()
    target_folder = data.get("target_folder", "").strip()
    paths = data.get("paths", [])
    encrypt_flag = data.get("encrypt_archive", False)

    result = backup_ops.create_backup(
        root,
        target_folder,
        paths,
        label=data.get("label", "admin_export"),
        decrypt_enc=data.get("decrypt_enc", False),
        encrypt_archive_flag=encrypt_flag,
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

    result = backup_ops.upload_backup(
        _project_root(),
        file.read(),
        file.filename or "",
        target_folder,
    )

    if "error" in result:
        code = result.pop("_status", 400)
        return jsonify(result), code
    return jsonify(result)
