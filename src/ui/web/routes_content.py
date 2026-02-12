"""
Admin API — Content vault core module.

Blueprint: content_bp
Prefix: /api

This module defines the blueprint, shared helpers, and core listing/crypto
endpoints. Route handlers are split across sub-modules for maintainability:

    routes_content.py             — (this file) blueprint, helpers, folders, list, encrypt, decrypt, metadata
    routes_content_files.py       — create folder, delete, download, upload, enc key status, optimize
    routes_content_preview.py     — preview, preview encrypted, save encrypted
    routes_content_manage.py      — setup enc key, save, rename, move, release status

Routes (this file):
    /api/content/folders       — detect content folders
    /api/content/all-folders   — list all project directories
    /api/content/list          — list files in a folder
    /api/content/encrypt       — encrypt a file
    /api/content/decrypt       — decrypt a .enc file
    /api/content/metadata      — read .enc metadata (no key needed)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

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
    from src.core.services.secrets_ops import fresh_env

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
        check_release: if "true", cross-ref release sidecars with GitHub
    """
    rel_path = request.args.get("path", "").strip()
    recursive = request.args.get("recursive", "").lower() == "true"
    check_release = request.args.get("check_release", "").lower() == "true"
    if not rel_path:
        return jsonify({"error": "Missing 'path' parameter"}), 400

    folder = _resolve_safe_path(rel_path)
    if folder is None:
        return jsonify({"error": "Invalid path"}), 400
    if not folder.is_dir():
        return jsonify({"error": f"Not a directory: {rel_path}"}), 404

    root = _project_root()

    # Optionally fetch remote release assets for orphan detection
    # ra=None means "skip orphan check", ra=set() means "check assets"
    ra: set[str] | None = None
    if check_release:
        from .content_release import list_release_assets
        remote = list_release_assets(root)
        if remote.get("available"):
            ra = {a["name"] for a in remote["assets"]}
        else:
            # Release doesn't exist → every sidecar is orphaned
            # (unless the upload is still in progress, handled downstream)
            ra = set()

    if recursive:
        files = list_folder_contents_recursive(folder, root, remote_assets=ra)
    else:
        files = list_folder_contents(folder, root, remote_assets=ra)

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
            from .content_release import cleanup_release_sidecar, upload_to_release_bg

            # Remove old release metadata + asset
            cleanup_release_sidecar(source, _project_root())

            # Upload new encrypted version
            file_id = output.stem
            upload_to_release_bg(file_id, output, _project_root())
            new_meta = output.parent / f"{output.name}.release.json"
            new_meta.write_text(json.dumps({
                "file_id": file_id,
                "asset_name": output.name,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "status": "uploading",
            }, indent=2))
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
            from .content_release import cleanup_release_sidecar, upload_to_release_bg

            # Remove old release metadata + asset
            cleanup_release_sidecar(vault_file, _project_root())

            # Upload new decrypted version
            file_id = output.stem
            upload_to_release_bg(file_id, output, _project_root())
            new_meta = output.parent / f"{output.name}.release.json"
            new_meta.write_text(json.dumps({
                "file_id": file_id,
                "asset_name": output.name,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "status": "uploading",
            }, indent=2))
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


# ── Import sub-modules to register their routes on content_bp ──────
# These imports MUST come after content_bp is defined (circular import guard).

from . import routes_content_files    # noqa: E402, F401 — registers routes
from . import routes_content_preview  # noqa: E402, F401 — registers routes
from . import routes_content_manage   # noqa: E402, F401 — registers routes
