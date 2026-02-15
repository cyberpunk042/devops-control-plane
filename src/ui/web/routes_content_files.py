"""
Admin API — Content file operations (create, delete, download, upload, optimize).

Thin HTTP wrappers over ``src.core.services.content_file_ops``.

Blueprint: content_bp (imported from routes_content)
Prefix: /api
Routes:
    /api/content/create-folder      — create a content folder
    /api/content/delete             — delete a file
    /api/content/download           — download a file
    /api/content/upload             — upload a file (with optimization pipeline)
    /api/content/enc-key-status     — check encryption key status
    /api/content/optimize-status    — poll optimization progress
    /api/content/optimize-cancel    — cancel active optimization
"""

from __future__ import annotations

from flask import jsonify, request, send_file

from src.core.services import content_file_ops

from .routes_content import (
    content_bp,
    _project_root,
    _resolve_safe_path,
    _get_enc_key,
)


# ── Create a content folder ─────────────────────────────────────────


@content_bp.route("/content/create-folder", methods=["POST"])
def content_create_folder():  # type: ignore[no-untyped-def]
    """Create a content folder in the project root."""
    data = request.get_json(silent=True) or {}

    result = content_file_ops.create_content_folder(
        _project_root(),
        name=data.get("name", "").strip(),
    )

    if "error" in result:
        code = result.pop("_status", 400)
        return jsonify(result), code

    return jsonify(result)


# ── Delete a file ───────────────────────────────────────────────────


@content_bp.route("/content/delete", methods=["POST"])
def content_delete():  # type: ignore[no-untyped-def]
    """Delete a file from a content folder."""
    data = request.get_json(silent=True) or {}

    result = content_file_ops.delete_content_file(
        _project_root(),
        rel_path=data.get("path", "").strip(),
    )

    if "error" in result:
        code = result.pop("_status", 400)
        return jsonify(result), code

    return jsonify(result)


# ── Download / preview a file ───────────────────────────────────────


@content_bp.route("/content/download")
def content_download():  # type: ignore[no-untyped-def]
    """Download or preview a content file."""
    rel_path = request.args.get("path", "").strip()
    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    target = _resolve_safe_path(rel_path)
    if target is None or not target.is_file():
        return jsonify({"error": "File not found"}), 404

    return send_file(
        target,
        as_attachment=request.args.get("download", "0") == "1",
    )


# ── File upload ─────────────────────────────────────────────────────


@content_bp.route("/content/upload", methods=["POST"])
def content_upload():  # type: ignore[no-untyped-def]
    """Upload a file to a content folder."""
    from werkzeug.utils import secure_filename

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    uploaded = request.files["file"]
    if not uploaded.filename:
        return jsonify({"error": "No filename"}), 400

    folder_rel = request.form.get("folder", "").strip()
    safe_name = secure_filename(uploaded.filename) or "upload"

    result = content_file_ops.upload_content_file(
        _project_root(),
        folder_rel=folder_rel,
        filename=safe_name,
        raw_data=uploaded.read(),
    )

    if "error" in result:
        code = result.pop("_status", 400)
        return jsonify(result), code

    return jsonify(result)


# ── Encryption key status ───────────────────────────────────────────


@content_bp.route("/content/enc-key-status")
def content_enc_key_status():  # type: ignore[no-untyped-def]
    """Check if CONTENT_VAULT_ENC_KEY is configured in .env."""
    key = _get_enc_key()
    return jsonify({
        "configured": bool(key),
        "key_name": "CONTENT_VAULT_ENC_KEY",
    })


# ── Media optimization progress (polled by frontend during upload) ──


@content_bp.route("/content/optimize-status")
def content_optimize_status():  # type: ignore[no-untyped-def]
    """Poll optimization progress (used by frontend during upload)."""
    from src.core.services.content_optimize import get_optimization_status

    return jsonify(get_optimization_status())


@content_bp.route("/content/optimize-cancel", methods=["POST"])
def content_optimize_cancel():  # type: ignore[no-untyped-def]
    """Cancel the active optimization (kills ffmpeg)."""
    from src.core.services.content_optimize import cancel_active_optimization

    killed = cancel_active_optimization()
    return jsonify({"cancelled": killed})
