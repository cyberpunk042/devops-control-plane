"""
Admin API — Content file operations (create, delete, download, upload, optimize).

Split from routes_content.py. Handles CRUD operations on content files.

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

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from flask import jsonify, request, send_file

from .routes_content import (
    content_bp,
    _project_root,
    _resolve_safe_path,
    _get_enc_key,
    _guess_mime,
)
from .content_crypto import DEFAULT_CONTENT_DIRS

from src.core.services import devops_cache

logger = logging.getLogger(__name__)


# ── Create a content folder ─────────────────────────────────────────


@content_bp.route("/content/create-folder", methods=["POST"])
def content_create_folder():  # type: ignore[no-untyped-def]
    """Create a content folder in the project root.

    JSON body:
        name: folder name (e.g., "docs", "media")
    """
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()

    if not name:
        return jsonify({"error": "Missing 'name'"}), 400

    # Sanitize: only allow simple names (no path separators)
    if "/" in name or "\\" in name or ".." in name:
        return jsonify({"error": "Invalid folder name"}), 400

    folder = _project_root() / name
    if folder.exists():
        return jsonify({"error": f"Folder '{name}' already exists"}), 409

    folder.mkdir(parents=True, exist_ok=True)

    # Create a .gitkeep so git tracks it
    (folder / ".gitkeep").touch()

    devops_cache.record_event(
        _project_root(),
        label="📁 Folder Created",
        summary=f"Content folder '{name}' created",
        detail={"folder": name},
        card="content",
    )

    logger.info("Created content folder: %s", name)
    return jsonify({
        "success": True,
        "name": name,
        "path": name,
    })


# ── Delete a file ───────────────────────────────────────────────────


@content_bp.route("/content/delete", methods=["POST"])
def content_delete():  # type: ignore[no-untyped-def]
    """Delete a file from a content folder.

    JSON body:
        path: relative path to the file
    """
    data = request.get_json(silent=True) or {}
    rel_path = data.get("path", "").strip()

    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    target = _resolve_safe_path(rel_path)
    if target is None:
        return jsonify({"error": "Invalid path"}), 400

    # Safety: only allow deletion within known content folders
    root = _project_root()
    try:
        rel = target.relative_to(root)
        top_dir = rel.parts[0] if rel.parts else ""
        if top_dir not in DEFAULT_CONTENT_DIRS:
            return jsonify({
                "error": f"Can only delete files within content folders ({', '.join(DEFAULT_CONTENT_DIRS)})"
            }), 403
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not target.exists():
        return jsonify({"error": f"File not found: {rel_path}"}), 404

    # Clean up release sidecar + GitHub asset if present (any tier)
    from .content_release import cleanup_release_sidecar
    cleanup_release_sidecar(target, _project_root())

    is_dir = target.is_dir()
    if is_dir:
        shutil.rmtree(target)
        logger.info("Deleted directory: %s", rel_path)
    else:
        target.unlink()
        logger.info("Deleted file: %s", rel_path)

    devops_cache.record_event(
        root,
        label="🗑️ File Deleted",
        summary=f"{'Directory' if is_dir else 'File'} '{rel_path}' deleted",
        detail={"path": rel_path, "type": "directory" if is_dir else "file"},
        card="content",
    )

    return jsonify({
        "success": True,
        "path": rel_path,
    })


# ── Download / preview a file ───────────────────────────────────────


@content_bp.route("/content/download")
def content_download():  # type: ignore[no-untyped-def]
    """Download or preview a content file.

    Query params:
        path: relative path to the file
    """
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

MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


@content_bp.route("/content/upload", methods=["POST"])
def content_upload():  # type: ignore[no-untyped-def]
    """Upload a file to a content folder.

    Every file goes through the optimization pipeline automatically:
    - Images → WebP
    - Video  → H.264 MP4  (via ffmpeg)
    - Audio  → AAC M4A    (via ffmpeg)
    - Text   → gzip       (if > 100 KB)

    After optimization, storage tier is determined:
    - ≤ 2 MB  → folder/ (git-tracked)
    - > 2 MB  → folder/.large/ (gitignored, hidden)

    Multipart form data:
        file: the file to upload (required)
        folder: target folder path (required)
    """
    from werkzeug.utils import secure_filename

    from .content_optimize import classify_storage, optimize_media

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    uploaded = request.files["file"]
    if not uploaded.filename:
        return jsonify({"error": "No filename"}), 400

    folder_rel = request.form.get("folder", "").strip()
    if not folder_rel:
        return jsonify({"error": "Missing 'folder'"}), 400

    folder = _resolve_safe_path(folder_rel)
    if folder is None:
        return jsonify({"error": "Invalid folder path"}), 400

    folder.mkdir(parents=True, exist_ok=True)

    safe_name = secure_filename(uploaded.filename)
    if not safe_name:
        safe_name = "upload"

    # Read raw bytes + resolve MIME type
    raw_data = uploaded.read()
    original_size = len(raw_data)
    mime = _guess_mime(safe_name)

    # ── Optimize ──
    opt_data, opt_mime, opt_ext, was_optimized = optimize_media(
        raw_data, mime, safe_name,
    )
    final_size = len(opt_data)

    # Keep original filename when format didn't change,
    # only rename when optimization changed the extension
    original_ext = Path(safe_name).suffix.lower()
    if opt_ext == original_ext:
        final_name = safe_name
    else:
        final_name = Path(safe_name).stem + opt_ext

    # ── Storage tier ──
    tier = classify_storage(final_size)
    if tier == "large":
        target_folder = folder / ".large"
        target_folder.mkdir(exist_ok=True)
    else:
        target_folder = folder

    dest = target_folder / final_name

    # Avoid overwriting
    if dest.exists():
        counter = 1
        while dest.exists():
            dest = target_folder / f"{stem}_{counter}{opt_ext}"
            counter += 1

    # Write optimized file
    dest.write_bytes(opt_data)

    root = _project_root()
    rel_result = str(dest.relative_to(root))

    result = {
        "success": True,
        "name": dest.name,
        "path": rel_result,
        "original_name": safe_name,
        "original_size": original_size,
        "size": final_size,
        "optimized": was_optimized,
        "tier": tier,
        "mime": opt_mime,
    }

    if was_optimized:
        savings = original_size - final_size
        result["savings"] = savings
        result["savings_pct"] = round(
            (1 - final_size / original_size) * 100, 1,
        ) if original_size > 0 else 0

    logger.info(
        "Upload: %s → %s  (%s → %s, %s, tier=%s)",
        safe_name, dest.name,
        f"{original_size:,}", f"{final_size:,}",
        "optimized" if was_optimized else "as-is",
        tier,
    )

    devops_cache.record_event(
        root,
        label="⬆️ File Uploaded",
        summary=f"{safe_name} uploaded to {folder_rel}"
                + (f" (optimized {result.get('savings_pct', 0)}%)" if was_optimized else "")
                + (f" [tier={tier}]" if tier == "large" else ""),
        detail={
            "file": safe_name,
            "folder": folder_rel,
            "original_size": original_size,
            "final_size": final_size,
            "optimized": was_optimized,
            "tier": tier,
        },
        card="content",
    )

    # Backup large files to GitHub Releases
    if tier == "large":
        from .content_release import upload_to_release_bg

        file_id = dest.stem  # use filename (sans ext) as ID
        upload_to_release_bg(file_id, dest, _project_root())
        result["release_upload"] = file_id

        # Write release metadata (same pattern as backups)
        meta_path = dest.parent / f"{dest.name}.release.json"
        meta = {
            "file_id": file_id,
            "asset_name": dest.name,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "status": "uploading",
        }
        meta_path.write_text(json.dumps(meta, indent=2))

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
    from .content_optimize import get_optimization_status

    return jsonify(get_optimization_status())


@content_bp.route("/content/optimize-cancel", methods=["POST"])
def content_optimize_cancel():  # type: ignore[no-untyped-def]
    """Cancel the active optimization (kills ffmpeg)."""
    from .content_optimize import cancel_active_optimization

    killed = cancel_active_optimization()
    return jsonify({"cancelled": killed})
