"""
Admin API — Backup single-file operations.

Split from routes_backup.py. Handles release upload/delete, encrypt/decrypt
backup archives, rename backup files, and git-add (mark-special).

Blueprint: backup_bp (imported from routes_backup)
Prefix: /api
Routes:
    /api/backup/upload-release  — upload a file to GitHub Release
    /api/backup/encrypt         — encrypt a .tar.gz backup in place
    /api/backup/decrypt         — decrypt a .tar.gz.enc backup in place
    /api/backup/delete-release  — delete a file's GitHub Release artifact
    /api/backup/rename          — rename a backup archive file
    /api/backup/mark-special    — git add -f a backup (≤25 MB)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from flask import jsonify, request

from .routes_backup import (
    backup_bp,
    _project_root,
    _get_enc_key,
    _encrypt_archive,
    _decrypt_archive,
)

logger = logging.getLogger(__name__)


# ── Upload to GitHub Release ──────────────────────────────────────


@backup_bp.route("/backup/upload-release", methods=["POST"])
def api_upload_release():  # type: ignore[no-untyped-def]
    """Upload a file to a GitHub Release as an artifact.

    JSON body:
        path (or backup_path):  relative path to the file
    """
    data = request.get_json(silent=True) or {}
    backup_path = (data.get("path") or data.get("backup_path", "")).strip()

    if not backup_path:
        return jsonify({"error": "Missing 'path'"}), 400

    root = _project_root()
    file_path = (root / backup_path).resolve()

    try:
        file_path.relative_to(root)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not file_path.exists():
        return jsonify({"error": "File not found"}), 404

    try:
        from .content_release import upload_to_release_bg
        file_id = f"backup_{file_path.stem}"
        upload_to_release_bg(file_id, file_path, root)

        # Save release metadata alongside the backup
        meta_path = file_path.parent / f"{file_path.name}.release.json"
        meta = {
            "file_id": file_id,
            "asset_name": file_path.name,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "status": "uploading",
        }
        meta_path.write_text(json.dumps(meta, indent=2))

        return jsonify({
            "success": True,
            "file_id": file_id,
            "message": f"Upload started for {file_path.name}",
        })
    except Exception as e:
        logger.exception("Failed to start release upload")
        return jsonify({"error": f"Upload failed: {e}"}), 500


# ── Encrypt / Decrypt existing backups ─────────────────────────────


@backup_bp.route("/backup/encrypt", methods=["POST"])
def api_encrypt_backup():  # type: ignore[no-untyped-def]
    """Encrypt an existing .tar.gz backup in place.

    JSON body:
        backup_path:  relative path to the .tar.gz
    """
    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "").strip()

    if not backup_path:
        return jsonify({"error": "Missing 'backup_path'"}), 400

    passphrase = _get_enc_key()
    if not passphrase:
        return jsonify({"error": "No CONTENT_VAULT_ENC_KEY configured"}), 400

    root = _project_root()
    file_path = (root / backup_path).resolve()

    try:
        file_path.relative_to(root)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not file_path.exists():
        return jsonify({"error": "File not found"}), 404

    if file_path.name.endswith(".enc"):
        return jsonify({"error": "Already encrypted"}), 400

    try:
        enc_path = _encrypt_archive(file_path, passphrase)
        return jsonify({
            "success": True,
            "filename": enc_path.name,
            "full_path": str(enc_path.relative_to(root)),
            "size_bytes": enc_path.stat().st_size,
        })
    except Exception as e:
        logger.exception("Failed to encrypt backup")
        return jsonify({"error": f"Encryption failed: {e}"}), 500


@backup_bp.route("/backup/decrypt", methods=["POST"])
def api_decrypt_backup():  # type: ignore[no-untyped-def]
    """Decrypt an existing .tar.gz.enc backup in place.

    JSON body:
        backup_path:  relative path to the .tar.gz.enc
    """
    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "").strip()

    if not backup_path:
        return jsonify({"error": "Missing 'backup_path'"}), 400

    passphrase = _get_enc_key()
    if not passphrase:
        return jsonify({"error": "No CONTENT_VAULT_ENC_KEY configured"}), 400

    root = _project_root()
    file_path = (root / backup_path).resolve()

    try:
        file_path.relative_to(root)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not file_path.exists():
        return jsonify({"error": "File not found"}), 404

    if not file_path.name.endswith(".enc"):
        return jsonify({"error": "Not an encrypted archive"}), 400

    try:
        # Decrypt to a temp file, then move into place
        dec_tmp = _decrypt_archive(file_path, passphrase)
        # Target: same name without .enc
        dec_final = file_path.parent / file_path.name[:-4]  # strip .enc
        dec_tmp.rename(dec_final)
        # Remove the encrypted version
        file_path.unlink()
        return jsonify({
            "success": True,
            "filename": dec_final.name,
            "full_path": str(dec_final.relative_to(root)),
            "size_bytes": dec_final.stat().st_size,
        })
    except Exception as e:
        logger.exception("Failed to decrypt backup")
        return jsonify({"error": f"Decryption failed: {e}"}), 500


# ── Delete release artifact ────────────────────────────────────────


@backup_bp.route("/backup/delete-release", methods=["POST"])
def api_delete_release():  # type: ignore[no-untyped-def]
    """Delete a file's GitHub Release artifact.

    JSON body:
        path (or backup_path):  relative path to the file
    """
    data = request.get_json(silent=True) or {}
    backup_path = (data.get("path") or data.get("backup_path", "")).strip()

    if not backup_path:
        return jsonify({"error": "Missing 'backup_path'"}), 400

    root = _project_root()
    file_path = (root / backup_path).resolve()

    try:
        file_path.relative_to(root)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    # Read release metadata
    meta_path = file_path.parent / f"{file_path.name}.release.json"
    if not meta_path.exists():
        return jsonify({"error": "No release metadata found for this backup"}), 404

    try:
        meta = json.loads(meta_path.read_text())
    except Exception:
        return jsonify({"error": "Could not read release metadata"}), 500

    asset_name = meta.get("old_asset_name") or meta.get("asset_name", file_path.name)

    try:
        from .content_release import delete_release_asset
        delete_release_asset(asset_name, root)
        # Remove metadata file
        meta_path.unlink(missing_ok=True)
        return jsonify({
            "success": True,
            "message": f"Queued deletion of release asset: {asset_name}",
        })
    except Exception as e:
        logger.exception("Failed to delete release asset")
        return jsonify({"error": f"Deletion failed: {e}"}), 500


# ── Rename a backup ────────────────────────────────────────────────


@backup_bp.route("/backup/rename", methods=["POST"])
def api_rename_backup():  # type: ignore[no-untyped-def]
    """Rename a backup archive file.

    JSON body:
        backup_path:  current relative path to the backup
        new_name:     new filename (without directory)
    """
    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "").strip()
    new_name = data.get("new_name", "").strip()

    if not backup_path or not new_name:
        return jsonify({"error": "Missing 'backup_path' or 'new_name'"}), 400

    # Sanitise new name
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', new_name)
    if not (safe_name.endswith(".tar.gz") or safe_name.endswith(".tar.gz.enc")):
        if backup_path.endswith(".enc"):
            safe_name += ".tar.gz.enc"
        else:
            safe_name += ".tar.gz"

    root = _project_root()
    old_path = (root / backup_path).resolve()

    try:
        old_path.relative_to(root)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not old_path.exists():
        return jsonify({"error": "File not found"}), 404

    new_path = old_path.parent / safe_name
    if new_path.exists():
        return jsonify({"error": f"A file named '{safe_name}' already exists"}), 409

    try:
        old_path.rename(new_path)

        # Move associated metadata files
        old_release = old_path.parent / f"{old_path.name}.release.json"
        if old_release.exists():
            new_release = old_path.parent / f"{safe_name}.release.json"
            old_release.rename(new_release)
            # Preserve old_asset_name so delete-release can still find the GitHub asset
            try:
                meta = json.loads(new_release.read_text())
                if "old_asset_name" not in meta:
                    meta["old_asset_name"] = meta.get("asset_name", old_path.name)
                meta["asset_name"] = safe_name
                new_release.write_text(json.dumps(meta, indent=2))
            except Exception:
                pass

        return jsonify({
            "success": True,
            "filename": safe_name,
            "full_path": str(new_path.relative_to(root)),
        })
    except Exception as e:
        logger.exception("Failed to rename backup")
        return jsonify({"error": f"Rename failed: {e}"}), 500


# ── Mark backup as git-tracked (special) ───────────────────────────


_SPECIAL_MAX_BYTES = 25 * 1024 * 1024  # 25 MB limit for git tracking


@backup_bp.route("/backup/mark-special", methods=["POST"])
def api_mark_special():  # type: ignore[no-untyped-def]
    """Force-add a backup to git (git add -f), bypassing .gitignore.

    JSON body:
        backup_path:  relative path to the backup archive
        unmark:       if True, remove from git tracking (git rm --cached)
    """
    import subprocess

    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "").strip()
    unmark = data.get("unmark", False)

    if not backup_path:
        return jsonify({"error": "Missing 'backup_path'"}), 400

    root = _project_root()
    file_path = (root / backup_path).resolve()

    try:
        file_path.relative_to(root)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not file_path.exists():
        return jsonify({"error": "File not found"}), 404

    if unmark:
        # Remove from git tracking (keep on disk)
        try:
            subprocess.run(
                ["git", "rm", "--cached", str(file_path)],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=15,
            )
            return jsonify({"success": True, "message": "Removed from git tracking"})
        except Exception as e:
            return jsonify({"error": f"git rm --cached failed: {e}"}), 500

    # Check size
    size = file_path.stat().st_size
    if size > _SPECIAL_MAX_BYTES:
        size_mb = size / (1024 * 1024)
        return jsonify({
            "error": (
                f"File too large for git ({size_mb:.1f} MB). "
                f"Maximum is {_SPECIAL_MAX_BYTES // (1024 * 1024)} MB. "
                "Use '🚀 Upload to Release' instead."
            ),
        }), 400

    try:
        result = subprocess.run(
            ["git", "add", "-f", str(file_path)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return jsonify({"error": f"git add -f failed: {result.stderr[:200]}"}), 500

        return jsonify({
            "success": True,
            "message": f"Added to git (force): {file_path.name}",
            "size_bytes": size,
        })
    except Exception as e:
        logger.exception("Failed to mark backup as special")
        return jsonify({"error": f"git add -f failed: {e}"}), 500
