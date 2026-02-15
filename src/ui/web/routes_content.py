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

import logging
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services.content_crypto import (
    classify_file,
    decrypt_file_to_memory,
    detect_content_folders,
    encrypt_content_file,
    decrypt_content_file,
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


@content_bp.route("/content/all-folders")
def content_all_folders():  # type: ignore[no-untyped-def]
    """List all top-level directories in the project."""
    from src.core.services.content_file_ops import list_all_project_folders

    folders = list_all_project_folders(_project_root())
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
        from src.core.services.content_release import list_release_assets
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
    """Encrypt a file using COVAULT format."""
    data = request.get_json(silent=True) or {}
    rel_path = data.get("path", "").strip()
    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    result = encrypt_content_file(
        _project_root(),
        rel_path,
        _get_enc_key() or "",
        delete_original=data.get("delete_original", False),
    )

    if "error" in result:
        code = result.pop("_status", 400)
        if "not found" in result["error"].lower():
            code = 404
        return jsonify(result), code
    return jsonify(result)


# ── Decrypt a file ──────────────────────────────────────────────────


@content_bp.route("/content/decrypt", methods=["POST"])
def content_decrypt():  # type: ignore[no-untyped-def]
    """Decrypt a .enc file."""
    data = request.get_json(silent=True) or {}
    rel_path = data.get("path", "").strip()
    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    result = decrypt_content_file(
        _project_root(),
        rel_path,
        _get_enc_key() or "",
        delete_encrypted=data.get("delete_encrypted", False),
    )

    if "error" in result:
        code = result.pop("_status", 400)
        if "not found" in result["error"].lower():
            code = 404
        return jsonify(result), code
    return jsonify(result)


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
