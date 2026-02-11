"""
Admin API — Content vault endpoints.

Blueprint: content_bp
Prefix: /api
Routes:
    /api/content/folders       — detect content folders
    /api/content/list          — list files in a folder
    /api/content/upload        — upload a file to a folder
    /api/content/encrypt       — encrypt a file
    /api/content/decrypt       — decrypt a .enc file
    /api/content/metadata      — read .enc metadata (no key needed)
    /api/content/create-folder — create a content folder
    /api/content/delete        — delete a file
    /api/content/enc-key-status — check if CONTENT_VAULT_ENC_KEY is set
    /api/content/preview       — preview a file's content
    /api/content/download      — download a file
    /api/content/release-status         — poll all release upload statuses
    /api/content/release-status/<id>    — poll single upload status
    /api/content/release-cancel/<id>    — cancel a release upload
    /api/content/restore-large          — restore large files from release
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file

from .content_crypto import (
    classify_file,
    decrypt_file,
    decrypt_file_to_memory,
    detect_content_folders,
    encrypt_file,
    format_size,
    is_covault_file,
    list_folder_contents,
    list_folder_contents_recursive,
    read_metadata,
    DEFAULT_CONTENT_DIRS,
    DOC_EXTS,
    CODE_EXTS,
    SCRIPT_EXTS,
    CONFIG_EXTS,
    DATA_EXTS,
)

logger = logging.getLogger(__name__)

content_bp = Blueprint("content", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"]).resolve()


def _resolve_safe_path(relative: str) -> Path | None:
    """Resolve a relative path safely, preventing directory traversal."""
    root = _project_root()
    try:
        resolved = (root / relative).resolve()
        # Ensure it's within the project root
        resolved.relative_to(root.resolve())
        return resolved
    except (ValueError, RuntimeError):
        return None


def _get_enc_key() -> str:
    """Read CONTENT_VAULT_ENC_KEY from .env."""
    from .helpers import fresh_env

    env = fresh_env(_project_root())
    return env.get("CONTENT_VAULT_ENC_KEY", "").strip()


# Extension → MIME lookup (stdlib mimetypes doesn't know .webp, .mkv, etc.)
_EXT_MIME: dict[str, str] = {
    # Images
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
    ".bmp": "image/bmp", ".ico": "image/x-icon", ".tiff": "image/tiff",
    ".tif": "image/tiff", ".avif": "image/avif",
    # Video
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".avi": "video/x-msvideo", ".mkv": "video/x-matroska",
    ".ogv": "video/ogg", ".3gp": "video/3gpp", ".ts": "video/mp2t",
    # Audio
    ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac",
    ".ogg": "audio/ogg", ".wav": "audio/wav", ".flac": "audio/flac",
    ".weba": "audio/webm", ".wma": "audio/x-ms-wma", ".opus": "audio/opus",
    # Documents
    ".pdf": "application/pdf", ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    # Archives
    ".zip": "application/zip", ".gz": "application/gzip",
    ".tar": "application/x-tar", ".7z": "application/x-7z-compressed",
    ".rar": "application/x-rar-compressed",
    # Text (supplement — stdlib usually handles these)
    ".md": "text/markdown", ".json": "application/json",
    ".xml": "application/xml", ".yaml": "application/x-yaml",
    ".yml": "application/x-yaml", ".csv": "text/csv",
    ".toml": "application/toml", ".txt": "text/plain",
}


def _guess_mime(filename: str) -> str:
    """Resolve MIME type from filename.

    Handles encrypted files: ``photo.webp.enc`` → uses ``.webp``.
    Uses a hardcoded lookup first (stdlib misses .webp, .mkv, etc.),
    then falls back to ``mimetypes.guess_type``.
    """
    import mimetypes

    name = filename
    # Strip .enc to get the real extension
    if name.lower().endswith(".enc"):
        name = name[:-4]

    ext = Path(name).suffix.lower()
    if ext in _EXT_MIME:
        return _EXT_MIME[ext]

    # Fallback to stdlib
    guessed = mimetypes.guess_type(name)[0]
    return guessed or "application/octet-stream"


# ── Detect content folders ──────────────────────────────────────────


@content_bp.route("/content/folders")
def content_folders():  # type: ignore[no-untyped-def]
    """Detect content folders in the project.

    Returns list of detected folders with file counts and categories.
    """
    root = _project_root()
    folders = detect_content_folders(root)

    # Also return which default folder names don't exist yet
    existing = {f["name"] for f in folders}
    suggestions = [d for d in DEFAULT_CONTENT_DIRS if d not in existing]

    return jsonify({
        "folders": folders,
        "suggestions": suggestions,
    })


# ── List all project directories (for "Explore All") ───────────────


_EXCLUDED_DIRS = {
    ".git", ".github", ".vscode", ".idea", ".proj", ".agent", ".gemini",
    "__pycache__", "node_modules", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "build", "dist", ".tox", ".eggs",
}


@content_bp.route("/content/all-folders")
def content_all_folders():  # type: ignore[no-untyped-def]
    """List all top-level directories in the project.

    Returns a lightweight list for the "Explore All" feature.
    Hidden/build/cache directories are excluded.
    """
    root = _project_root()
    folders = []
    try:
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            name = entry.name
            if name.startswith(".") and name not in (".backup",):
                continue
            if name in _EXCLUDED_DIRS:
                continue
            folders.append({"name": name, "path": name})
    except OSError:
        pass

    return jsonify({"folders": folders})


# ── List folder contents ────────────────────────────────────────────


@content_bp.route("/content/list")
def content_list():  # type: ignore[no-untyped-def]
    """List files in a content folder.

    Query params:
        path: relative folder path (e.g., "docs", "media/images")
        recursive: if "true", list all files in all subdirectories (flat)
    """
    rel_path = request.args.get("path", "").strip()
    recursive = request.args.get("recursive", "").lower() == "true"
    if not rel_path:
        return jsonify({"error": "Missing 'path' parameter"}), 400

    folder = _resolve_safe_path(rel_path)
    if folder is None:
        return jsonify({"error": "Invalid path"}), 400
    if not folder.is_dir():
        return jsonify({"error": f"Not a directory: {rel_path}"}), 404

    root = _project_root()
    if recursive:
        files = list_folder_contents_recursive(folder, root)
    else:
        files = list_folder_contents(folder, root)

    # Compute summary
    total_size = sum(f.get("size", 0) for f in files if not f.get("is_dir"))
    file_count = sum(1 for f in files if not f.get("is_dir"))
    dir_count = sum(1 for f in files if f.get("is_dir"))
    encrypted_count = sum(1 for f in files if f.get("encrypted"))

    return jsonify({
        "path": rel_path,
        "recursive": recursive,
        "files": files,
        "summary": {
            "file_count": file_count,
            "dir_count": dir_count,
            "total_size": total_size,
            "total_size_human": format_size(total_size),
            "encrypted_count": encrypted_count,
        },
    })


# ── Encrypt a file ──────────────────────────────────────────────────


@content_bp.route("/content/encrypt", methods=["POST"])
def content_encrypt():  # type: ignore[no-untyped-def]
    """Encrypt a file using COVAULT format.

    JSON body:
        path: relative path to the source file
        delete_original: whether to delete the original after encryption (default: false)

    Uses CONTENT_VAULT_ENC_KEY from .env as the encryption key.
    """
    data = request.get_json(silent=True) or {}
    rel_path = data.get("path", "").strip()
    delete_original = data.get("delete_original", False)

    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    source = _resolve_safe_path(rel_path)
    if source is None:
        return jsonify({"error": "Invalid path"}), 400
    if not source.is_file():
        return jsonify({"error": f"File not found: {rel_path}"}), 404

    passphrase = _get_enc_key()
    if not passphrase:
        return jsonify({"error": "CONTENT_VAULT_ENC_KEY is not set in .env", "needs_key": True}), 400

    try:
        output = encrypt_file(source, passphrase)
        result = {
            "success": True,
            "source": rel_path,
            "output": str(output.relative_to(_project_root())),
            "original_size": source.stat().st_size,
            "encrypted_size": output.stat().st_size,
        }

        if delete_original:
            source.unlink()
            result["original_deleted"] = True

        # Update release artifact if file is in .large/
        if ".large" in source.parts:
            from .content_release import delete_release_asset, upload_to_release_bg

            delete_release_asset(source.name, _project_root())
            file_id = output.stem
            upload_to_release_bg(file_id, output, _project_root())
            result["release_updated"] = True

        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Failed to encrypt %s", rel_path)
        return jsonify({"error": f"Encryption failed: {e}"}), 500


# ── Decrypt a file ──────────────────────────────────────────────────


@content_bp.route("/content/decrypt", methods=["POST"])
def content_decrypt():  # type: ignore[no-untyped-def]
    """Decrypt a .enc file.

    JSON body:
        path: relative path to the .enc file
        delete_encrypted: whether to delete the .enc after decryption (default: false)

    Uses CONTENT_VAULT_ENC_KEY from .env as the decryption key.
    """
    data = request.get_json(silent=True) or {}
    rel_path = data.get("path", "").strip()
    delete_encrypted = data.get("delete_encrypted", False)

    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    vault_file = _resolve_safe_path(rel_path)
    if vault_file is None:
        return jsonify({"error": "Invalid path"}), 400
    if not vault_file.is_file():
        return jsonify({"error": f"File not found: {rel_path}"}), 404

    passphrase = _get_enc_key()
    if not passphrase:
        return jsonify({"error": "CONTENT_VAULT_ENC_KEY is not set in .env", "needs_key": True}), 400

    try:
        output = decrypt_file(vault_file, passphrase)
        result = {
            "success": True,
            "source": rel_path,
            "output": str(output.relative_to(_project_root())),
            "decrypted_size": output.stat().st_size,
        }

        if delete_encrypted:
            vault_file.unlink()
            result["encrypted_deleted"] = True

        # Update release artifact if file is in .large/
        if ".large" in vault_file.parts:
            from .content_release import delete_release_asset, upload_to_release_bg

            delete_release_asset(vault_file.name, _project_root())
            file_id = output.stem
            upload_to_release_bg(file_id, output, _project_root())
            result["release_updated"] = True

        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Failed to decrypt %s", rel_path)
        return jsonify({"error": f"Decryption failed: {e}"}), 500


# ── Read metadata (no passphrase needed) ─────────────────────────────


@content_bp.route("/content/metadata")
def content_metadata():  # type: ignore[no-untyped-def]
    """Read metadata from a .enc file without decrypting.

    Query params:
        path: relative path to the .enc file
    """
    rel_path = request.args.get("path", "").strip()
    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    vault_file = _resolve_safe_path(rel_path)
    if vault_file is None:
        return jsonify({"error": "Invalid path"}), 400
    if not vault_file.is_file():
        return jsonify({"error": f"File not found: {rel_path}"}), 404

    try:
        meta = read_metadata(vault_file)
        meta["encrypted_size_human"] = format_size(meta["encrypted_size"])
        return jsonify(meta)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


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

    # If file is in a large/ directory, also delete from GitHub Release
    is_large = ".large" in target.parts
    asset_name = target.name

    if target.is_dir():
        shutil.rmtree(target)
        logger.info("Deleted directory: %s", rel_path)
    else:
        target.unlink()
        logger.info("Deleted file: %s", rel_path)

    if is_large:
        from .content_release import delete_release_asset
        delete_release_asset(asset_name, _project_root())

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

    # Backup large files to GitHub Releases
    if tier == "large":
        from .content_release import upload_to_release_bg

        file_id = dest.stem  # use filename (sans ext) as ID
        upload_to_release_bg(file_id, dest, _project_root())
        result["release_upload"] = file_id

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


# ── File preview ────────────────────────────────────────────────────

_TEXT_EXTS = (
    DOC_EXTS | CODE_EXTS | SCRIPT_EXTS | CONFIG_EXTS | DATA_EXTS
    | {".log", ".gitignore", ".dockerignore", ".editorconfig",
       "Makefile", "Dockerfile", "Procfile", "Vagrantfile"}
)

_MAX_PREVIEW_BYTES = 512 * 1024  # 512 KB


@content_bp.route("/content/preview")
def content_preview():  # type: ignore[no-untyped-def]
    """Preview a file's text content.

    Query params:
        path: relative path to the file

    Returns text content for previewable files, or an error for binary.
    """
    rel_path = request.args.get("path", "").strip()
    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    target = _resolve_safe_path(rel_path)
    if target is None or not target.is_file():
        return jsonify({"error": "File not found"}), 404

    suffix = target.suffix.lower()
    mime = _guess_mime(target.name)

    # Check if text-previewable
    is_text = suffix in _TEXT_EXTS or mime.startswith("text/")

    if not is_text:
        # For images, return a URL to the download endpoint for inline display
        if mime.startswith("image/"):
            return jsonify({
                "type": "image",
                "mime": mime,
                "url": f"/api/content/download?path={rel_path}",
            })
        # Video — return a URL for the <video> player
        if mime.startswith("video/"):
            return jsonify({
                "type": "video",
                "mime": mime,
                "url": f"/api/content/download?path={rel_path}",
                "size": target.stat().st_size,
            })
        # Audio — return a URL for the <audio> player
        if mime.startswith("audio/"):
            return jsonify({
                "type": "audio",
                "mime": mime,
                "url": f"/api/content/download?path={rel_path}",
                "size": target.stat().st_size,
            })
        return jsonify({
            "type": "binary",
            "mime": mime,
            "error": "Cannot preview binary files",
        })

    # Read text content (limited)
    size = target.stat().st_size
    if size > _MAX_PREVIEW_BYTES:
        content = target.read_text(encoding="utf-8", errors="replace")[:_MAX_PREVIEW_BYTES]
        truncated = True
    else:
        content = target.read_text(encoding="utf-8", errors="replace")
        truncated = False

    return jsonify({
        "type": "markdown" if suffix == ".md" else "text",
        "mime": mime or "text/plain",
        "content": content,
        "truncated": truncated,
        "size": size,
        "line_count": content.count("\n") + 1,
    })


# ── Preview encrypted file (in-memory decrypt) ────────────────────


@content_bp.route("/content/preview-encrypted", methods=["POST"])
def content_preview_encrypted():  # type: ignore[no-untyped-def]
    """Decrypt a .enc file in memory and return its content for preview.

    JSON body:
        path: relative path to the .enc file
        key: (optional) override key — if not provided, uses CONTENT_VAULT_ENC_KEY

    No file is written to disk.
    """
    data = request.get_json(silent=True) or {}
    rel_path = data.get("path", "").strip()
    override_key = data.get("key", "").strip()

    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    target = _resolve_safe_path(rel_path)
    if target is None or not target.is_file():
        return jsonify({"error": "File not found"}), 404

    # Determine which key to use
    passphrase = override_key or _get_enc_key()
    if not passphrase:
        return jsonify({"error": "No encryption key available", "needs_key": True}), 400

    try:
        plaintext, meta = decrypt_file_to_memory(target, passphrase)
    except ValueError as e:
        error_msg = str(e)
        is_wrong_key = "Wrong key" in error_msg or "decryption failed" in error_msg
        return jsonify({
            "error": error_msg,
            "wrong_key": is_wrong_key,
        }), 400

    original_name = meta["filename"]
    mime = meta["mime_type"]
    size = len(plaintext)

    # Determine type from original filename
    suffix = Path(original_name).suffix.lower()

    # Image — return as base64 data URL
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico"}:
        import base64
        b64 = base64.b64encode(plaintext).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        return jsonify({
            "type": "image",
            "url": data_url,
            "original_name": original_name,
            "mime": mime,
            "size": size,
        })

    # Video — return as base64 data URL for inline playback
    if suffix in {".mp4", ".webm", ".mov", ".avi", ".mkv"}:
        import base64
        b64 = base64.b64encode(plaintext).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        return jsonify({
            "type": "video",
            "url": data_url,
            "original_name": original_name,
            "mime": mime,
            "size": size,
        })

    # Audio — return as base64 data URL for inline playback
    if suffix in {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma"}:
        import base64
        b64 = base64.b64encode(plaintext).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        return jsonify({
            "type": "audio",
            "url": data_url,
            "original_name": original_name,
            "mime": mime,
            "size": size,
        })

    # Text / markdown
    TEXT_SUFFIXES = {
        ".md", ".txt", ".rst", ".csv", ".json", ".yaml", ".yml",
        ".toml", ".ini", ".cfg", ".conf", ".sh", ".bash", ".py",
        ".js", ".ts", ".html", ".css", ".xml", ".sql", ".log",
        ".env", ".gitignore", ".dockerfile",
    }

    if suffix in TEXT_SUFFIXES or mime.startswith("text/"):
        max_preview = 512 * 1024
        text = plaintext[:max_preview].decode("utf-8", errors="replace")
        truncated = size > max_preview

        return jsonify({
            "type": "markdown" if suffix == ".md" else "text",
            "original_name": original_name,
            "mime": mime,
            "content": text,
            "truncated": truncated,
            "size": size,
            "line_count": text.count("\n") + 1,
        })

    # Binary — no preview content
    return jsonify({
        "type": "binary",
        "original_name": original_name,
        "mime": mime,
        "size": size,
    })


# ── Save encrypted file (re-encrypt edited content) ──────────────


@content_bp.route("/content/save-encrypted", methods=["POST"])
def content_save_encrypted():  # type: ignore[no-untyped-def]
    """Save edited content back to an encrypted file.

    Decrypts in memory to get the original metadata (filename, mime),
    then re-encrypts with the new content and writes back.

    JSON body:
        path: relative path to the .enc file
        content: the edited plaintext content
        key: (optional) override key — if not provided, uses CONTENT_VAULT_ENC_KEY
    """
    data = request.get_json(silent=True) or {}
    rel_path = data.get("path", "").strip()
    content = data.get("content", "")
    override_key = data.get("key", "").strip() if data.get("key") else ""

    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    target = _resolve_safe_path(rel_path)
    if target is None or not target.is_file():
        return jsonify({"error": "File not found"}), 404

    passphrase = override_key or _get_enc_key()
    if not passphrase:
        return jsonify({"error": "No encryption key available"}), 400

    try:
        # Verify we can decrypt with this key first
        _, meta = decrypt_file_to_memory(target, passphrase)

        # Now re-encrypt the edited content as bytes
        import tempfile
        import os

        # Write plaintext to a temp file, encrypt, then clean up
        original_name = meta["filename"]
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=Path(original_name).suffix,
            prefix=Path(original_name).stem + "_",
        ) as tmp:
            tmp.write(content.encode("utf-8"))
            tmp_path = Path(tmp.name)

        try:
            # Encrypt from temp → overwrite the .enc file
            encrypt_file(tmp_path, passphrase, output_path=target)
        finally:
            tmp_path.unlink(missing_ok=True)

        return jsonify({
            "success": True,
            "size": target.stat().st_size,
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Failed to save encrypted %s", rel_path)
        return jsonify({"error": f"Save failed: {e}"}), 500


# ── Generate / set encryption key ──────────────────────────────────


@content_bp.route("/content/setup-enc-key", methods=["POST"])
def content_setup_enc_key():  # type: ignore[no-untyped-def]
    """Set CONTENT_VAULT_ENC_KEY in .env.

    JSON body:
        key: the encryption key value (user-provided or auto-generated)
        generate: if true, ignore 'key' and generate a random one

    The key is placed under a '# ── Content Vault ──' section in .env.
    """
    import secrets as py_secrets

    data = request.get_json(silent=True) or {}
    should_generate = data.get("generate", False)
    key_value = data.get("key", "").strip()

    if should_generate:
        # Generate a 32-byte (256-bit) URL-safe random key
        key_value = py_secrets.token_urlsafe(32)

    if not key_value or len(key_value) < 8:
        return jsonify({"error": "Encryption key must be at least 8 characters"}), 400

    # Use the vault/add-keys mechanism to write to .env
    env_path = _project_root() / ".env"
    if not env_path.exists():
        return jsonify({"error": ".env does not exist"}), 400

    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Check if key already exists — update it
    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _, _ = stripped.partition("=")
            if k.strip() == "CONTENT_VAULT_ENC_KEY":
                lines[i] = f"CONTENT_VAULT_ENC_KEY={key_value}"
                found = True
                break

    if not found:
        # Find or create the Content Vault section
        import re
        section_re = re.compile(r"^#\s*[─━═—]+\s*Content\s*Vault\s*[─━═—]*", re.IGNORECASE)
        insert_idx = None

        for i, line in enumerate(lines):
            if section_re.match(line.strip()):
                # Insert after this section header
                insert_idx = i + 1
                break

        if insert_idx is None:
            # Create the section at the end
            lines.append("")
            lines.append("# ── Content Vault ──────────────────────────────")
            lines.append(f"CONTENT_VAULT_ENC_KEY={key_value}")
        else:
            lines.insert(insert_idx, f"CONTENT_VAULT_ENC_KEY={key_value}")

    final = "\n".join(lines)
    if not final.endswith("\n"):
        final += "\n"
    env_path.write_text(final, encoding="utf-8")

    logger.info("Set CONTENT_VAULT_ENC_KEY in .env (generated=%s)", should_generate)
    return jsonify({
        "success": True,
        "generated": should_generate,
        "key_value": key_value,
    })


# ── Save file content ──────────────────────────────────────────────


@content_bp.route("/content/save", methods=["POST"])
def content_save():  # type: ignore[no-untyped-def]
    """Save text content to a file.

    JSON body:
        path: relative path to the file
        content: the text content to write
    """
    data = request.get_json(silent=True) or {}
    rel_path = data.get("path", "").strip()
    file_content = data.get("content", "")

    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    target = _resolve_safe_path(rel_path)
    if target is None:
        return jsonify({"error": "Invalid path"}), 400
    if not target.is_file():
        return jsonify({"error": f"File not found: {rel_path}"}), 404

    # Safety: only allow editing within content folders
    root = _project_root()
    try:
        rel = target.relative_to(root)
        top_dir = rel.parts[0] if rel.parts else ""
        if top_dir not in DEFAULT_CONTENT_DIRS:
            return jsonify({
                "error": f"Can only edit files within content folders ({', '.join(DEFAULT_CONTENT_DIRS)})"
            }), 403
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    target.write_text(file_content, encoding="utf-8")

    logger.info("Saved file: %s (%d bytes)", rel_path, len(file_content))
    return jsonify({
        "success": True,
        "path": rel_path,
        "size": len(file_content.encode("utf-8")),
    })


# ── Rename file ─────────────────────────────────────────────────────


@content_bp.route("/content/rename", methods=["POST"])
def content_rename():  # type: ignore[no-untyped-def]
    """Rename a file in-place.

    JSON body:
        path: relative path to the file
        new_name: new filename (just the name, not a path)
    """
    data = request.get_json(silent=True) or {}
    rel_path = data.get("path", "").strip()
    new_name = data.get("new_name", "").strip()

    if not rel_path or not new_name:
        return jsonify({"error": "Missing 'path' or 'new_name'"}), 400

    if "/" in new_name or "\\" in new_name:
        return jsonify({"error": "New name must not contain path separators"}), 400

    source = _resolve_safe_path(rel_path)
    if source is None or not source.exists():
        return jsonify({"error": "File not found"}), 404

    dest = source.parent / new_name
    if dest.exists():
        return jsonify({"error": f"A file named '{new_name}' already exists"}), 409

    source.rename(dest)
    root = _project_root()

    logger.info("Renamed: %s → %s", rel_path, new_name)
    return jsonify({
        "success": True,
        "old_path": rel_path,
        "new_path": str(dest.relative_to(root)),
        "new_name": new_name,
    })


# ── Move file ───────────────────────────────────────────────────────


@content_bp.route("/content/move", methods=["POST"])
def content_move():  # type: ignore[no-untyped-def]
    """Move a file to another content folder.

    JSON body:
        path: relative path to the file
        destination: relative folder path (e.g., "archive", "media")
    """
    data = request.get_json(silent=True) or {}
    rel_path = data.get("path", "").strip()
    dest_folder = data.get("destination", "").strip()

    if not rel_path or not dest_folder:
        return jsonify({"error": "Missing 'path' or 'destination'"}), 400

    source = _resolve_safe_path(rel_path)
    if source is None or not source.is_file():
        return jsonify({"error": "File not found"}), 404

    dest_dir = _resolve_safe_path(dest_folder)
    if dest_dir is None:
        return jsonify({"error": "Invalid destination"}), 400

    if not dest_dir.is_dir():
        dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / source.name
    if dest.exists():
        return jsonify({"error": f"'{source.name}' already exists in {dest_folder}"}), 409

    shutil.move(str(source), str(dest))
    root = _project_root()

    logger.info("Moved: %s → %s", rel_path, str(dest.relative_to(root)))
    return jsonify({
        "success": True,
        "old_path": rel_path,
        "new_path": str(dest.relative_to(root)),
    })


# ── GitHub Release upload for large files ───────────────────────────


@content_bp.route("/content/release-status")
def content_release_status():  # type: ignore[no-untyped-def]
    """Poll the status of all background release uploads."""
    from .content_release import get_all_release_statuses

    return jsonify(get_all_release_statuses())


@content_bp.route("/content/release-status/<file_id>")
def content_release_status_single(file_id):  # type: ignore[no-untyped-def]
    """Poll the status of a specific background release upload."""
    from .content_release import get_release_status

    status = get_release_status(file_id)
    if not status:
        return jsonify({"status": "unknown", "message": "No upload tracked"}), 404
    return jsonify(status)


@content_bp.route("/content/release-cancel/<file_id>", methods=["POST"])
def content_release_cancel(file_id):  # type: ignore[no-untyped-def]
    """Cancel a running release upload."""
    from .content_release import cancel_release_upload

    result = cancel_release_upload(file_id)
    return jsonify(result)


@content_bp.route("/content/restore-large", methods=["POST"])
def content_restore_large():  # type: ignore[no-untyped-def]
    """Download missing large files from the 'content-vault' GitHub Release."""
    from .content_release import restore_large_files

    result = restore_large_files(_project_root())
    return jsonify({"success": True, **result})
