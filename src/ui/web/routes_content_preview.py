"""
Admin API — Content preview endpoints.

Split from routes_content.py. Handles text/image/video/audio preview for both
plain and encrypted files, and saving encrypted file edits.

Blueprint: content_bp (imported from routes_content)
Prefix: /api
Routes:
    /api/content/preview            — preview a file's content
    /api/content/preview-encrypted  — decrypt + preview in memory
    /api/content/save-encrypted     — re-encrypt edited content
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import jsonify, request

from .routes_content import (
    content_bp,
    _project_root,
    _resolve_safe_path,
    _get_enc_key,
    _guess_mime,
)
from .content_crypto import (
    decrypt_file_to_memory,
    encrypt_file,
    DOC_EXTS,
    CODE_EXTS,
    SCRIPT_EXTS,
    CONFIG_EXTS,
    DATA_EXTS,
)

logger = logging.getLogger(__name__)


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

    # Check release sidecar
    meta_path = target.parent / f"{target.name}.release.json"
    has_release = meta_path.exists()
    release_orphaned = False
    release_status = ""

    if has_release:
        try:
            import json
            sidecar = json.loads(meta_path.read_text())
            release_status = sidecar.get("status", "unknown")

            # Detect stale "uploading" — no active upload thread
            if release_status == "uploading":
                _fid = sidecar.get("file_id", "")
                try:
                    from .content_release import _release_upload_status
                    live = _release_upload_status.get(_fid, {})
                    if not live or live.get("status") not in ("uploading", "queued"):
                        release_status = "stale"
                except ImportError:
                    release_status = "stale"

            # Orphan check: skip only genuinely active uploads
            if release_status != "uploading":
                asset_name = (
                    sidecar.get("old_asset_name")
                    or sidecar.get("asset_name")
                    or target.name
                )
                from .content_release import list_release_assets
                remote = list_release_assets(_project_root())
                if remote.get("available"):
                    remote_names = {a["name"] for a in remote["assets"]}
                    if asset_name not in remote_names:
                        release_orphaned = True
                else:
                    # Release tag doesn't exist → sidecar is orphaned
                    release_orphaned = True
        except Exception:
            pass

    if not is_text:
        # For images, return a URL to the download endpoint for inline display
        if mime.startswith("image/"):
            return jsonify({
                "type": "image",
                "mime": mime,
                "url": f"/api/content/download?path={rel_path}",
                "has_release": has_release,
                "release_status": release_status,
                "release_orphaned": release_orphaned,
            })
        # Video — return a URL for the <video> player
        if mime.startswith("video/"):
            return jsonify({
                "type": "video",
                "mime": mime,
                "url": f"/api/content/download?path={rel_path}",
                "size": target.stat().st_size,
                "has_release": has_release,
                "release_status": release_status,
                "release_orphaned": release_orphaned,
            })
        # Audio — return a URL for the <audio> player
        if mime.startswith("audio/"):
            return jsonify({
                "type": "audio",
                "mime": mime,
                "url": f"/api/content/download?path={rel_path}",
                "size": target.stat().st_size,
                "has_release": has_release,
                "release_status": release_status,
                "release_orphaned": release_orphaned,
            })
        return jsonify({
            "type": "binary",
            "mime": mime,
            "error": "Cannot preview binary files",
            "has_release": has_release,
            "release_status": release_status,
            "release_orphaned": release_orphaned,
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
        "has_release": has_release,
        "release_status": release_status,
        "release_orphaned": release_orphaned,
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
