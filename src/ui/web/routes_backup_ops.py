"""
Admin API — Backup single-file operations.

Thin HTTP wrappers over ``src.core.services.backup_ops``.

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
from datetime import datetime, timezone

from flask import jsonify, request

from src.core.services import backup_ops, devops_cache
from .routes_backup import backup_bp, _project_root

logger = logging.getLogger(__name__)


# ── Upload to GitHub Release ──────────────────────────────────────


@backup_bp.route("/backup/upload-release", methods=["POST"])
def api_upload_release():  # type: ignore[no-untyped-def]
    """Upload a file to a GitHub Release as an artifact."""
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
        from src.core.services.content_release import upload_to_release_bg
        file_id = f"backup_{file_path.stem}"
        upload_to_release_bg(file_id, file_path, root)

        meta_path = file_path.parent / f"{file_path.name}.release.json"
        meta = {
            "file_id": file_id,
            "asset_name": file_path.name,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "status": "uploading",
        }
        meta_path.write_text(json.dumps(meta, indent=2))

        devops_cache.record_event(
            root,
            label="☁️ Backup Release Upload",
            summary=f"{file_path.name} upload started to GitHub Release",
            detail={"file": backup_path, "file_id": file_id},
            card="backup",
        )

        return jsonify({
            "success": True,
            "file_id": file_id,
            "message": f"Upload started for {file_path.name}",
        })
    except Exception as e:
        logger.exception("Failed to start release upload")
        devops_cache.record_event(
            root,
            label="❌ Backup Release Upload Failed",
            summary=f"{file_path.name}: {e}",
            detail={"file": backup_path, "error": str(e)},
            card="backup",
        )
        return jsonify({"error": f"Upload failed: {e}"}), 500


# ── Encrypt / Decrypt existing backups ─────────────────────────────


@backup_bp.route("/backup/encrypt", methods=["POST"])
def api_encrypt_backup():  # type: ignore[no-untyped-def]
    """Encrypt an existing .tar.gz backup in place."""
    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "").strip()
    root = _project_root()

    if not backup_path:
        return jsonify({"error": "Missing 'backup_path'"}), 400

    result = backup_ops.encrypt_backup_inplace(root, backup_path)
    if "error" in result:
        return jsonify(result), 400

    devops_cache.record_event(
        root,
        label="🔐 Backup Encrypted",
        summary=f"{backup_path} encrypted in place",
        detail={"backup": backup_path},
        card="backup",
    )
    return jsonify(result)


@backup_bp.route("/backup/decrypt", methods=["POST"])
def api_decrypt_backup():  # type: ignore[no-untyped-def]
    """Decrypt an existing .tar.gz.enc backup in place."""
    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "").strip()
    root = _project_root()

    if not backup_path:
        return jsonify({"error": "Missing 'backup_path'"}), 400

    result = backup_ops.decrypt_backup_inplace(root, backup_path)
    if "error" in result:
        return jsonify(result), 400

    devops_cache.record_event(
        root,
        label="🔓 Backup Decrypted",
        summary=f"{backup_path} decrypted in place",
        detail={"backup": backup_path},
        card="backup",
    )
    return jsonify(result)


# ── Delete release artifact ────────────────────────────────────────


@backup_bp.route("/backup/delete-release", methods=["POST"])
def api_delete_release():  # type: ignore[no-untyped-def]
    """Delete a file's GitHub Release artifact."""
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

    meta_path = file_path.parent / f"{file_path.name}.release.json"
    if not meta_path.exists():
        return jsonify({"error": "No release metadata found for this backup"}), 404

    try:
        meta = json.loads(meta_path.read_text())
    except Exception:
        return jsonify({"error": "Could not read release metadata"}), 500

    asset_name = meta.get("old_asset_name") or meta.get("asset_name", file_path.name)

    try:
        from src.core.services.content_release import delete_release_asset
        delete_release_asset(asset_name, root)
        meta_path.unlink(missing_ok=True)

        devops_cache.record_event(
            root,
            label="☁️❌ Release Asset Deleted",
            summary=f"Release asset '{asset_name}' deletion queued",
            detail={"backup": backup_path, "asset": asset_name},
            card="backup",
        )

        return jsonify({
            "success": True,
            "message": f"Queued deletion of release asset: {asset_name}",
        })
    except Exception as e:
        logger.exception("Failed to delete release asset")
        devops_cache.record_event(
            root,
            label="❌ Release Delete Failed",
            summary=f"{asset_name}: {e}",
            detail={"backup": backup_path, "asset": asset_name, "error": str(e)},
            card="backup",
        )
        return jsonify({"error": f"Deletion failed: {e}"}), 500


# ── Rename a backup ────────────────────────────────────────────────


@backup_bp.route("/backup/rename", methods=["POST"])
def api_rename_backup():  # type: ignore[no-untyped-def]
    """Rename a backup archive file."""
    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "").strip()
    new_name = data.get("new_name", "").strip()

    if not backup_path or not new_name:
        return jsonify({"error": "Missing 'backup_path' or 'new_name'"}), 400

    root = _project_root()

    # Ensure proper extension
    import re
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', new_name)
    if not (safe_name.endswith(".tar.gz") or safe_name.endswith(".tar.gz.enc")):
        if backup_path.endswith(".enc"):
            safe_name += ".tar.gz.enc"
        else:
            safe_name += ".tar.gz"

    result = backup_ops.rename_backup(root, backup_path, safe_name)
    if "error" in result:
        code = 409 if "already exists" in result.get("error", "") else 400
        return jsonify(result), code

    devops_cache.record_event(
        root,
        label="✏️ Backup Renamed",
        summary=f"{backup_path} → {safe_name}",
        detail={"old_name": backup_path, "new_name": safe_name},
        card="backup",
    )
    return jsonify({"success": True, **result})


# ── Mark backup as git-tracked (special) ───────────────────────────


@backup_bp.route("/backup/mark-special", methods=["POST"])
def api_mark_special():  # type: ignore[no-untyped-def]
    """Force-add a backup to git (git add -f), bypassing .gitignore."""
    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "").strip()
    unmark = data.get("unmark", False)

    if not backup_path:
        return jsonify({"error": "Missing 'backup_path'"}), 400

    root = _project_root()
    result = backup_ops.mark_special(root, backup_path, unmark=unmark)
    if "error" in result:
        return jsonify(result), 400

    devops_cache.record_event(
        root,
        label="📌 Backup " + ("Unmarked" if unmark else "Marked"),
        summary=f"{backup_path} {'removed from' if unmark else 'added to'} git tracking",
        detail={"backup": backup_path, "unmark": unmark},
        card="backup",
    )
    return jsonify(result)
