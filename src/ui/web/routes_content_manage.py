"""
Admin API — Content management endpoints (key setup, save, rename, move, release).

Split from routes_content.py. Handles encryption key setup, file saving,
renaming, moving, and GitHub Release status polling.

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

import json
import logging
import shutil
from pathlib import Path

from flask import jsonify, request

from .routes_content import (
    content_bp,
    _project_root,
    _resolve_safe_path,
    _get_enc_key,
)
from .content_crypto import DEFAULT_CONTENT_DIRS

from src.core.services import devops_cache

logger = logging.getLogger(__name__)


# ── Generate / set encryption key ──────────────────────────────────


@content_bp.route("/content/setup-enc-key", methods=["POST"])
def content_setup_enc_key():  # type: ignore[no-untyped-def]
    """Set CONTENT_VAULT_ENC_KEY in .env.

    JSON body:
        key: the encryption key value (user-provided or auto-generated)
        generate: if true, ignore 'key' and generate a random one

    The key is placed under a '# ── Content Vault ──' section in .env.
    """
    import re
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

    devops_cache.record_event(
        _project_root(),
        label="🔐 Enc Key Configured",
        summary="CONTENT_VAULT_ENC_KEY " + ("auto-generated" if should_generate else "set manually"),
        detail={"generated": should_generate},
        card="content",
        action="configured",
        target="CONTENT_VAULT_ENC_KEY",
    )

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
    import difflib

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

    # ── Capture before-state for audit ──
    old_content = target.read_text(encoding="utf-8") if target.is_file() else ""
    old_lines = old_content.count("\n") + (1 if old_content else 0)
    old_size = len(old_content.encode("utf-8"))

    # ── Write ──
    target.write_text(file_content, encoding="utf-8")
    new_size = len(file_content.encode("utf-8"))
    new_lines = file_content.count("\n") + (1 if file_content else 0)

    # ── Compute unified diff ──
    old_lines_list = old_content.splitlines()
    new_lines_list = file_content.splitlines()
    diff_lines = list(difflib.unified_diff(
        old_lines_list, new_lines_list,
        fromfile=f"a/{rel_path}", tofile=f"b/{rel_path}",
        lineterm="",
    ))
    added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
    # Keep diff compact — cap at 50 lines to avoid bloating the log
    diff_text = "\n".join(diff_lines[:50])
    if len(diff_lines) > 50:
        diff_text += f"\n... ({len(diff_lines) - 50} more lines)"

    devops_cache.record_event(
        root,
        label="📝 File Modified",
        summary=f"{rel_path}: +{added} -{removed} lines ({old_size:,} → {new_size:,} bytes)",
        detail={
            "file": rel_path,
            "lines_added": added,
            "lines_removed": removed,
            "diff": diff_text,
        },
        card="content",
        action="modified",
        target=rel_path,
        before_state={"lines": old_lines, "size": old_size},
        after_state={"lines": new_lines, "size": new_size},
    )

    logger.info("Saved file: %s (%d bytes, +%d -%d lines)", rel_path, new_size, added, removed)
    return jsonify({
        "success": True,
        "path": rel_path,
        "size": new_size,
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

    # Move release metadata sidecar if it exists
    old_meta = source.parent / f"{source.name}.release.json"
    if old_meta.exists():
        new_meta = dest.parent / f"{dest.name}.release.json"
        try:
            meta = json.loads(old_meta.read_text())
            if "old_asset_name" not in meta:
                meta["old_asset_name"] = meta.get("asset_name", source.name)
            meta["asset_name"] = dest.name
            new_meta.write_text(json.dumps(meta, indent=2))
            old_meta.unlink(missing_ok=True)
        except Exception:
            old_meta.rename(new_meta)

    logger.info("Renamed: %s → %s", rel_path, new_name)

    devops_cache.record_event(
        root,
        label="✏️ File Renamed",
        summary=f"{rel_path} → {new_name}",
        detail={"old_path": rel_path, "new_name": new_name},
        card="content",
        action="renamed",
        target=rel_path,
        before_state={"name": source.name},
        after_state={"name": new_name, "path": str(dest.relative_to(root))},
    )

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

    # Move release metadata sidecar if it exists
    old_meta = source.parent / f"{source.name}.release.json"
    if old_meta.exists():
        new_meta = dest.parent / f"{dest.name}.release.json"
        shutil.move(str(old_meta), str(new_meta))

    logger.info("Moved: %s → %s", rel_path, str(dest.relative_to(root)))

    devops_cache.record_event(
        root,
        label="📦 File Moved",
        summary=f"{rel_path} → {dest_folder}/{source.name}",
        detail={
            "old_path": rel_path,
            "new_path": str(dest.relative_to(root)),
            "destination": dest_folder,
        },
        card="content",
        action="moved",
        target=rel_path,
        before_state={"path": rel_path},
        after_state={"path": str(dest.relative_to(root))},
    )

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

    root = _project_root()
    result = restore_large_files(root)

    devops_cache.record_event(
        root,
        label="⬇️ Large Files Restored",
        summary=f"{result.get('restored', 0)} large files downloaded from release",
        detail={
            "restored": result.get("restored", 0),
            "skipped": result.get("skipped", 0),
            "failed": result.get("failed", 0),
        },
        card="content",
        action="restored",
        target="content-vault",
        after_state={
            "restored": result.get("restored", 0),
            "skipped": result.get("skipped", 0),
            "failed": result.get("failed", 0),
        },
    )

    return jsonify({"success": True, **result})


@content_bp.route("/content/release-inventory")
def content_release_inventory():  # type: ignore[no-untyped-def]
    """Cross-reference local release sidecars with actual GitHub assets.

    Returns orphaned files (sidecar exists, asset gone), synced files,
    and extra remote assets (on GitHub but no local sidecar).
    """
    from .content_release import release_inventory

    result = release_inventory(_project_root())
    # Strip raw meta dicts from response (too verbose for the API)
    for lst_key in ("orphaned", "synced", "local_sidecars"):
        for item in result.get(lst_key, []):
            item.pop("meta", None)
    return jsonify(result)


@content_bp.route("/content/clean-release-sidecar", methods=["POST"])
def content_clean_release_sidecar():  # type: ignore[no-untyped-def]
    """Delete a stale .release.json sidecar without touching the content file.

    JSON body:
        path: relative path to the content file (not the sidecar itself)
    """
    data = request.get_json(silent=True) or {}
    rel_path = data.get("path", "").strip()
    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    target = _resolve_safe_path(rel_path)
    if target is None or not target.is_file():
        return jsonify({"error": "File not found"}), 404

    meta_path = target.parent / f"{target.name}.release.json"
    if not meta_path.exists():
        return jsonify({"error": "No sidecar found"}), 404

    meta_path.unlink(missing_ok=True)
    logger.info("Cleaned orphaned release sidecar: %s", meta_path)
    return jsonify({
        "success": True,
        "path": rel_path,
        "message": "Sidecar removed",
    })

