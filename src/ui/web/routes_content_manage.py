"""
Admin API — Content management endpoints (key setup, save, rename, move, release).

Thin HTTP wrappers over ``src.core.services.content_file_ops``
and ``src.core.services.content_release``.

Blueprint: content_bp (imported from routes_content)
Prefix: /api
Routes:
    /api/content/setup-enc-key          — set/generate encryption key in .env
    /api/content/save                   — save text content to a file
    /api/content/rename                 — rename a file in-place
    /api/content/move                   — move a file to another folder
    /api/content/release-status         — poll all release upload statuses
    /api/content/release-status/<id>    — poll single upload status
    /api/content/release-cancel/<id>    — cancel a release upload
    /api/content/restore-large          — restore large files from release
    /api/content/release-inventory      — cross-ref local sidecars vs remote assets
    /api/content/clean-release-sidecar  — delete a stale .release.json sidecar
"""

from __future__ import annotations

import logging

from flask import jsonify, request

from src.core.services import content_file_ops

from .routes_content import (
    content_bp,
    _project_root,
    _resolve_safe_path,
)

logger = logging.getLogger(__name__)


# ── Generate / set encryption key ──────────────────────────────────


@content_bp.route("/content/setup-enc-key", methods=["POST"])
def content_setup_enc_key():  # type: ignore[no-untyped-def]
    """Set CONTENT_VAULT_ENC_KEY in .env."""
    data = request.get_json(silent=True) or {}

    result = content_file_ops.setup_enc_key(
        _project_root(),
        key_value=data.get("key", "").strip(),
        generate=data.get("generate", False),
    )

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


# ── Save file content ──────────────────────────────────────────────


@content_bp.route("/content/save", methods=["POST"])
def content_save():  # type: ignore[no-untyped-def]
    """Save text content to a file."""
    data = request.get_json(silent=True) or {}

    result = content_file_ops.save_content_file(
        _project_root(),
        rel_path=data.get("path", "").strip(),
        file_content=data.get("content", ""),
    )

    if "error" in result:
        code = result.pop("_status", 400)
        return jsonify(result), code

    return jsonify(result)


# ── Rename file ─────────────────────────────────────────────────────


@content_bp.route("/content/rename", methods=["POST"])
def content_rename():  # type: ignore[no-untyped-def]
    """Rename a file in-place."""
    data = request.get_json(silent=True) or {}

    result = content_file_ops.rename_content_file(
        _project_root(),
        rel_path=data.get("path", "").strip(),
        new_name=data.get("new_name", "").strip(),
    )

    if "error" in result:
        code = result.pop("_status", 400)
        return jsonify(result), code

    return jsonify(result)


# ── Move file ───────────────────────────────────────────────────────


@content_bp.route("/content/move", methods=["POST"])
def content_move():  # type: ignore[no-untyped-def]
    """Move a file to another content folder."""
    data = request.get_json(silent=True) or {}

    result = content_file_ops.move_content_file(
        _project_root(),
        rel_path=data.get("path", "").strip(),
        dest_folder=data.get("destination", "").strip(),
    )

    if "error" in result:
        code = result.pop("_status", 400)
        return jsonify(result), code

    return jsonify(result)


# ── GitHub Release upload for large files ───────────────────────────


@content_bp.route("/content/release-status")
def content_release_status():  # type: ignore[no-untyped-def]
    """Poll the status of all background release uploads."""
    from src.core.services.content_release import get_all_release_statuses

    return jsonify(get_all_release_statuses())


@content_bp.route("/content/release-status/<file_id>")
def content_release_status_single(file_id):  # type: ignore[no-untyped-def]
    """Poll the status of a specific background release upload."""
    from src.core.services.content_release import get_release_status

    status = get_release_status(file_id)
    if not status:
        return jsonify({"status": "unknown", "message": "No upload tracked"}), 404
    return jsonify(status)


@content_bp.route("/content/release-cancel/<file_id>", methods=["POST"])
def content_release_cancel(file_id):  # type: ignore[no-untyped-def]
    """Cancel a running release upload."""
    from src.core.services.content_release import cancel_release_upload

    result = cancel_release_upload(file_id)
    return jsonify(result)


@content_bp.route("/content/restore-large", methods=["POST"])
def content_restore_large():  # type: ignore[no-untyped-def]
    """Download missing large files from the 'content-vault' GitHub Release."""
    result = content_file_ops.restore_large_files_from_release(_project_root())
    return jsonify(result)


@content_bp.route("/content/release-inventory")
def content_release_inventory():  # type: ignore[no-untyped-def]
    """Cross-reference local release sidecars with actual GitHub assets."""
    from src.core.services.content_release import release_inventory

    result = release_inventory(_project_root())
    # Strip raw meta dicts from response (too verbose for the API)
    for lst_key in ("orphaned", "synced", "local_sidecars"):
        for item in result.get(lst_key, []):
            item.pop("meta", None)
    return jsonify(result)


@content_bp.route("/content/clean-release-sidecar", methods=["POST"])
def content_clean_release_sidecar():  # type: ignore[no-untyped-def]
    """Delete a stale .release.json sidecar without touching the content file."""
    from src.core.services.content_release import remove_orphaned_sidecar

    data = request.get_json(silent=True) or {}
    rel_path = data.get("path", "").strip()
    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    target = _resolve_safe_path(rel_path)
    if target is None or not target.is_file():
        return jsonify({"error": "File not found"}), 404

    result = remove_orphaned_sidecar(target)
    if "error" in result:
        return jsonify(result), 404
    return jsonify({**result, "path": rel_path, "message": "Sidecar removed"})
