"""
Content file operations — create folder, delete file, upload file.

Channel-independent: no Flask or HTTP dependency.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Audit helper ────────────────────────────────────────────────


def _audit(label: str, summary: str, **kwargs: Any) -> None:
    """Record an audit event if a project root is registered."""
    try:
        from src.core.context import get_project_root
        root = get_project_root()
    except Exception:
        return
    if root is None:
        return
    from src.core.services.devops_cache import record_event
    record_event(root, label=label, summary=summary, card="content", **kwargs)


# ── Path safety ─────────────────────────────────────────────────


def resolve_safe_path(project_root: Path, relative: str) -> Path | None:
    """Resolve a relative path safely, preventing directory traversal."""
    try:
        resolved = (project_root / relative).resolve()
        resolved.relative_to(project_root.resolve())
        return resolved
    except (ValueError, RuntimeError):
        return None


# ── Create Folder ───────────────────────────────────────────────


def create_content_folder(project_root: Path, name: str) -> dict:
    """Create a content folder in the project root.

    Args:
        project_root: Project root directory.
        name: Simple folder name (no path separators).

    Returns:
        {"success": True, "name": ..., "path": ...} or {"error": ...}.
    """
    if not name:
        return {"error": "Missing 'name'"}

    if "/" in name or "\\" in name or ".." in name:
        return {"error": "Invalid folder name"}

    folder = project_root / name
    if folder.exists():
        return {"error": f"Folder '{name}' already exists", "_status": 409}

    folder.mkdir(parents=True, exist_ok=True)
    (folder / ".gitkeep").touch()

    logger.info("Created content folder: %s", name)

    _audit(
        "📁 Folder Created",
        f"Content folder '{name}' created",
        action="created",
        target=name,
        detail={"folder": name},
        after_state={"type": "directory"},
    )

    return {"success": True, "name": name, "path": name}


# ── Delete File ─────────────────────────────────────────────────


def delete_content_file(project_root: Path, rel_path: str) -> dict:
    """Delete a file or directory from a content folder.

    Args:
        project_root: Project root directory.
        rel_path: Relative path to the file/directory.

    Returns:
        {"success": True, "path": ...} or {"error": ...}.
    """
    from src.core.services.content_crypto import DEFAULT_CONTENT_DIRS

    if not rel_path:
        return {"error": "Missing 'path'"}

    target = resolve_safe_path(project_root, rel_path)
    if target is None:
        return {"error": "Invalid path"}

    # Safety: only allow deletion within known content folders
    try:
        rel = target.relative_to(project_root)
        top_dir = rel.parts[0] if rel.parts else ""
        if top_dir not in DEFAULT_CONTENT_DIRS:
            return {
                "error": f"Can only delete files within content folders "
                f"({', '.join(DEFAULT_CONTENT_DIRS)})",
                "_status": 403,
            }
    except ValueError:
        return {"error": "Invalid path"}

    if not target.exists():
        return {"error": f"File not found: {rel_path}", "_status": 404}

    # Clean up release sidecar + GitHub asset if present
    from src.core.services.content_release import cleanup_release_sidecar
    cleanup_release_sidecar(target, project_root)

    is_dir = target.is_dir()

    # Capture before-state for audit
    before: dict[str, Any] = {"type": "directory" if is_dir else "file"}
    if is_dir:
        children = list(target.rglob("*"))
        before["children"] = len(children)
        before["size"] = sum(f.stat().st_size for f in children if f.is_file())
    else:
        stat = target.stat()
        before["size"] = stat.st_size
        try:
            content = target.read_text(encoding="utf-8")
            before["lines"] = content.count("\n") + (1 if content else 0)
        except (UnicodeDecodeError, OSError):
            pass  # binary file — no line count

    if is_dir:
        shutil.rmtree(target)
        logger.info("Deleted directory: %s", rel_path)
    else:
        target.unlink()
        logger.info("Deleted file: %s", rel_path)

    _audit(
        "🗑️ File Deleted",
        f"{'Directory' if is_dir else 'File'} '{rel_path}' deleted"
        + (
            f" ({before.get('children', 0)} items, {before['size']:,} bytes)"
            if is_dir
            else f" ({before['size']:,} bytes"
            + (f", {before['lines']} lines" if "lines" in before else "")
            + ")"
        ),
        action="deleted",
        target=rel_path,
        detail={"path": rel_path, "type": "directory" if is_dir else "file"},
        before_state=before,
    )

    return {"success": True, "path": rel_path}


# ── Upload File ─────────────────────────────────────────────────


def upload_content_file(
    project_root: Path,
    folder_rel: str,
    filename: str,
    raw_data: bytes,
) -> dict:
    """Upload a file to a content folder with automatic optimization.

    Every file goes through the optimization pipeline:
    - Images → WebP
    - Video  → H.264 MP4 (via ffmpeg)
    - Audio  → AAC M4A  (via ffmpeg)
    - Text   → gzip     (if > 100 KB)

    After optimization, storage tier is determined:
    - ≤ 2 MB  → folder/ (git-tracked)
    - > 2 MB  → folder/.large/ (gitignored, hidden)

    Args:
        project_root: Project root directory.
        folder_rel: Relative path to target folder.
        filename: Original filename (sanitized by caller).
        raw_data: Raw file bytes.

    Returns:
        {"success": True, "name": ..., ...} or {"error": ...}.
    """
    import mimetypes

    from src.core.services.content_optimize import classify_storage, optimize_media

    if not folder_rel:
        return {"error": "Missing 'folder'"}

    folder = resolve_safe_path(project_root, folder_rel)
    if folder is None:
        return {"error": "Invalid folder path"}

    folder.mkdir(parents=True, exist_ok=True)

    safe_name = filename
    if not safe_name:
        safe_name = "upload"

    original_size = len(raw_data)
    mime = _guess_mime(safe_name)

    # Optimize
    opt_data, opt_mime, opt_ext, was_optimized = optimize_media(
        raw_data, mime, safe_name,
    )
    final_size = len(opt_data)

    # Keep original filename when format didn't change
    original_ext = Path(safe_name).suffix.lower()
    if opt_ext == original_ext:
        final_name = safe_name
    else:
        final_name = Path(safe_name).stem + opt_ext

    # Storage tier
    tier = classify_storage(final_size)
    if tier == "large":
        target_folder = folder / ".large"
        target_folder.mkdir(exist_ok=True)
    else:
        target_folder = folder

    dest = target_folder / final_name

    # Avoid overwriting
    if dest.exists():
        stem = Path(safe_name).stem
        counter = 1
        while dest.exists():
            dest = target_folder / f"{stem}_{counter}{opt_ext}"
            counter += 1

    # Write optimized file
    dest.write_bytes(opt_data)

    rel_result = str(dest.relative_to(project_root))

    result: dict[str, Any] = {
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
        result["savings_pct"] = (
            round((1 - final_size / original_size) * 100, 1)
            if original_size > 0
            else 0
        )

    logger.info(
        "Upload: %s → %s  (%s → %s, %s, tier=%s)",
        safe_name,
        dest.name,
        f"{original_size:,}",
        f"{final_size:,}",
        "optimized" if was_optimized else "as-is",
        tier,
    )

    _audit(
        "⬆️ File Uploaded",
        f"{safe_name} uploaded to {folder_rel}"
        + (f" (optimized {result.get('savings_pct', 0)}%)" if was_optimized else "")
        + (f" [tier={tier}]" if tier == "large" else ""),
        action="created",
        target=rel_result,
        detail={
            "file": safe_name,
            "folder": folder_rel,
            "original_size": original_size,
            "final_size": final_size,
            "optimized": was_optimized,
            "tier": tier,
        },
        after_state={
            "size": final_size,
            "original_size": original_size,
            "optimized": was_optimized,
            "tier": tier,
            "mime": opt_mime,
        },
    )

    # Large files → background upload to GitHub Releases
    if tier == "large":
        from src.core.services.content_release import upload_to_release_bg

        file_id = dest.stem
        upload_to_release_bg(file_id, dest, project_root)
        result["release_upload"] = file_id

        # Write release metadata sidecar
        meta_path = dest.parent / f"{dest.name}.release.json"
        meta = {
            "file_id": file_id,
            "asset_name": dest.name,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "status": "uploading",
        }
        meta_path.write_text(json.dumps(meta, indent=2))

    return result


# ── Setup Enc Key ───────────────────────────────────────────────


def setup_enc_key(
    project_root: Path,
    key_value: str = "",
    generate: bool = False,
) -> dict:
    """Set or generate CONTENT_VAULT_ENC_KEY in .env.

    Args:
        project_root: Project root directory.
        key_value: User-provided key value.
        generate: If True, ignore key_value and generate a random one.

    Returns:
        {"success": True, "generated": ..., "key_value": ...} or {"error": ...}.
    """
    import re
    import secrets as py_secrets

    if generate:
        key_value = py_secrets.token_urlsafe(32)

    if not key_value or len(key_value) < 8:
        return {"error": "Encryption key must be at least 8 characters"}

    env_path = project_root / ".env"
    if not env_path.exists():
        return {"error": ".env does not exist"}

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
        section_re = re.compile(
            r"^#\s*[─━═—]+\s*Content\s*Vault\s*[─━═—]*", re.IGNORECASE,
        )
        insert_idx = None

        for i, line in enumerate(lines):
            if section_re.match(line.strip()):
                insert_idx = i + 1
                break

        if insert_idx is None:
            lines.append("")
            lines.append("# ── Content Vault ──────────────────────────────")
            lines.append(f"CONTENT_VAULT_ENC_KEY={key_value}")
        else:
            lines.insert(insert_idx, f"CONTENT_VAULT_ENC_KEY={key_value}")

    final = "\n".join(lines)
    if not final.endswith("\n"):
        final += "\n"
    env_path.write_text(final, encoding="utf-8")

    logger.info("Set CONTENT_VAULT_ENC_KEY in .env (generated=%s)", generate)

    _audit(
        "🔐 Enc Key Configured",
        "CONTENT_VAULT_ENC_KEY " + ("auto-generated" if generate else "set manually"),
        action="configured",
        target="CONTENT_VAULT_ENC_KEY",
        detail={"generated": generate},
    )

    return {"success": True, "generated": generate, "key_value": key_value}


# ── Save Content File ───────────────────────────────────────────


def save_content_file(
    project_root: Path,
    rel_path: str,
    file_content: str,
) -> dict:
    """Save text content to an existing file.

    Args:
        project_root: Project root directory.
        rel_path: Relative path to the file.
        file_content: The text content to write.

    Returns:
        {"success": True, "path": ..., "size": ...} or {"error": ...}.
    """
    import difflib

    from src.core.services.content_crypto import DEFAULT_CONTENT_DIRS

    if not rel_path:
        return {"error": "Missing 'path'"}

    target = resolve_safe_path(project_root, rel_path)
    if target is None:
        return {"error": "Invalid path"}
    if not target.is_file():
        return {"error": f"File not found: {rel_path}", "_status": 404}

    # Safety: only allow editing within content folders
    try:
        rel = target.relative_to(project_root)
        top_dir = rel.parts[0] if rel.parts else ""
        if top_dir not in DEFAULT_CONTENT_DIRS:
            return {
                "error": f"Can only edit files within content folders "
                f"({', '.join(DEFAULT_CONTENT_DIRS)})",
                "_status": 403,
            }
    except ValueError:
        return {"error": "Invalid path"}

    # Capture before-state
    old_content = target.read_text(encoding="utf-8") if target.is_file() else ""
    old_lines = old_content.count("\n") + (1 if old_content else 0)
    old_size = len(old_content.encode("utf-8"))

    # Write
    target.write_text(file_content, encoding="utf-8")
    new_size = len(file_content.encode("utf-8"))
    new_lines = file_content.count("\n") + (1 if file_content else 0)

    # Compute unified diff
    old_lines_list = old_content.splitlines()
    new_lines_list = file_content.splitlines()
    diff_lines = list(difflib.unified_diff(
        old_lines_list, new_lines_list,
        fromfile=f"a/{rel_path}", tofile=f"b/{rel_path}",
        lineterm="",
    ))
    added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
    diff_text = "\n".join(diff_lines[:50])
    if len(diff_lines) > 50:
        diff_text += f"\n... ({len(diff_lines) - 50} more lines)"

    _audit(
        "📝 File Modified",
        f"{rel_path}: +{added} -{removed} lines ({old_size:,} → {new_size:,} bytes)",
        action="modified",
        target=rel_path,
        detail={
            "file": rel_path,
            "lines_added": added,
            "lines_removed": removed,
            "diff": diff_text,
        },
        before_state={"lines": old_lines, "size": old_size},
        after_state={"lines": new_lines, "size": new_size},
    )

    logger.info("Saved file: %s (%d bytes, +%d -%d lines)", rel_path, new_size, added, removed)
    return {"success": True, "path": rel_path, "size": new_size}


# ── Rename Content File ─────────────────────────────────────────


def rename_content_file(
    project_root: Path,
    rel_path: str,
    new_name: str,
) -> dict:
    """Rename a file in-place.

    Args:
        project_root: Project root directory.
        rel_path: Relative path to the file.
        new_name: New filename (just the name, not a path).

    Returns:
        {"success": True, ...} or {"error": ...}.
    """
    if not rel_path or not new_name:
        return {"error": "Missing 'path' or 'new_name'"}

    if "/" in new_name or "\\" in new_name:
        return {"error": "New name must not contain path separators"}

    source = resolve_safe_path(project_root, rel_path)
    if source is None or not source.exists():
        return {"error": "File not found", "_status": 404}

    dest = source.parent / new_name
    if dest.exists():
        return {"error": f"A file named '{new_name}' already exists", "_status": 409}

    source.rename(dest)

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

    _audit(
        "✏️ File Renamed",
        f"{rel_path} → {new_name}",
        action="renamed",
        target=rel_path,
        detail={"old_path": rel_path, "new_name": new_name},
        before_state={"name": source.name},
        after_state={"name": new_name, "path": str(dest.relative_to(project_root))},
    )

    return {
        "success": True,
        "old_path": rel_path,
        "new_path": str(dest.relative_to(project_root)),
        "new_name": new_name,
    }


# ── Move Content File ───────────────────────────────────────────


def move_content_file(
    project_root: Path,
    rel_path: str,
    dest_folder: str,
) -> dict:
    """Move a file to another content folder.

    Args:
        project_root: Project root directory.
        rel_path: Relative path to the file.
        dest_folder: Relative folder path (e.g., "archive", "media").

    Returns:
        {"success": True, ...} or {"error": ...}.
    """
    if not rel_path or not dest_folder:
        return {"error": "Missing 'path' or 'destination'"}

    source = resolve_safe_path(project_root, rel_path)
    if source is None or not source.is_file():
        return {"error": "File not found", "_status": 404}

    dest_dir = resolve_safe_path(project_root, dest_folder)
    if dest_dir is None:
        return {"error": "Invalid destination"}

    if not dest_dir.is_dir():
        dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / source.name
    if dest.exists():
        return {
            "error": f"'{source.name}' already exists in {dest_folder}",
            "_status": 409,
        }

    shutil.move(str(source), str(dest))

    # Move release metadata sidecar if it exists
    old_meta = source.parent / f"{source.name}.release.json"
    if old_meta.exists():
        new_meta = dest.parent / f"{dest.name}.release.json"
        shutil.move(str(old_meta), str(new_meta))

    logger.info("Moved: %s → %s", rel_path, str(dest.relative_to(project_root)))

    _audit(
        "📦 File Moved",
        f"{rel_path} → {dest_folder}/{source.name}",
        action="moved",
        target=rel_path,
        detail={
            "old_path": rel_path,
            "new_path": str(dest.relative_to(project_root)),
            "destination": dest_folder,
        },
        before_state={"path": rel_path},
        after_state={"path": str(dest.relative_to(project_root))},
    )

    return {
        "success": True,
        "old_path": rel_path,
        "new_path": str(dest.relative_to(project_root)),
    }


# ── Restore Large Files ─────────────────────────────────────────


def restore_large_files_from_release(project_root: Path) -> dict:
    """Download missing large files from the 'content-vault' GitHub Release.

    Returns:
        {"success": True, "restored": N, "skipped": N, "failed": N}.
    """
    from src.core.services.content_release import restore_large_files

    result = restore_large_files(project_root)

    _audit(
        "⬇️ Large Files Restored",
        f"{result.get('restored', 0)} large files downloaded from release",
        action="restored",
        target="content-vault",
        detail={
            "restored": result.get("restored", 0),
            "skipped": result.get("skipped", 0),
            "failed": result.get("failed", 0),
        },
        after_state={
            "restored": result.get("restored", 0),
            "skipped": result.get("skipped", 0),
            "failed": result.get("failed", 0),
        },
    )

    return {"success": True, **result}


# ── MIME lookup (delegated to content_crypto) ──────────────────

from src.core.services.content_crypto import _EXT_MIME, _guess_mime  # noqa: F401


# ── List all project directories ────────────────────────────────

_EXCLUDED_DIRS = {
    ".git", ".github", ".vscode", ".idea", ".proj", ".agent", ".gemini",
    "__pycache__", "node_modules", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "build", "dist", ".tox", ".eggs",
}


def list_all_project_folders(project_root: Path) -> list[dict[str, str]]:
    """List all top-level directories in the project.

    Hidden/build/cache directories are excluded.
    Used by the "Explore All" feature.
    """
    folders: list[dict[str, str]] = []
    try:
        for entry in sorted(project_root.iterdir()):
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
    return folders


# ── Release sidecar check ──────────────────────────────────────


def check_release_sidecar(
    target: Path,
    project_root: Path,
) -> dict[str, object]:
    """Check for a release sidecar and detect stale/orphaned states.

    Args:
        target: Absolute path to the content file.
        project_root: Project root directory.

    Returns:
        {"has_release": bool, "release_status": str, "release_orphaned": bool}
    """
    meta_path = target.parent / f"{target.name}.release.json"
    has_release = meta_path.exists()
    release_orphaned = False
    release_status = ""

    if not has_release:
        return {
            "has_release": False,
            "release_status": "",
            "release_orphaned": False,
        }

    try:
        import json as _json

        sidecar = _json.loads(meta_path.read_text())
        release_status = sidecar.get("status", "unknown")

        # Detect stale "uploading" — no active upload thread
        if release_status == "uploading":
            _fid = sidecar.get("file_id", "")
            try:
                from src.core.services.content_release import (
                    _release_upload_status,
                )

                live = _release_upload_status.get(_fid, {})
                if not live or live.get("status") not in (
                    "uploading",
                    "queued",
                ):
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
            from src.core.services.content_release import list_release_assets

            remote = list_release_assets(project_root)
            if remote.get("available"):
                remote_names = {a["name"] for a in remote["assets"]}
                if asset_name not in remote_names:
                    release_orphaned = True
            else:
                # Release tag doesn't exist → sidecar is orphaned
                release_orphaned = True
    except Exception:
        pass

    return {
        "has_release": has_release,
        "release_status": release_status,
        "release_orphaned": release_orphaned,
    }


# ── Save encrypted file (re-encrypt edited content) ────────────


def save_encrypted_content(
    target: Path,
    content: str,
    passphrase: str,
    rel_path: str,
) -> dict[str, object]:
    """Decrypt, re-encrypt with new content, compute diff and audit.

    Args:
        target: Absolute path to the .enc file.
        content: Edited plaintext content.
        passphrase: Encryption passphrase.
        rel_path: Relative path (for audit logging).

    Returns:
        {"success": True, "size": int} on success.

    Raises:
        ValueError: On decryption failure or wrong key.
    """
    import difflib
    import tempfile

    from src.core.services.content_crypto import (
        decrypt_file_to_memory,
        encrypt_file,
    )

    # Decrypt to get old content + metadata
    old_plaintext, meta = decrypt_file_to_memory(target, passphrase)
    original_name = meta["filename"]

    old_text = old_plaintext.decode("utf-8", errors="replace")
    old_size = len(old_plaintext)
    old_lines = old_text.count("\n") + (1 if old_text else 0)

    # Re-encrypt the edited content
    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=Path(original_name).suffix,
        prefix=Path(original_name).stem + "_",
    ) as tmp:
        tmp.write(content.encode("utf-8"))
        tmp_path = Path(tmp.name)

    try:
        encrypt_file(
            tmp_path,
            passphrase,
            output_path=target,
            original_filename=original_name,
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    new_enc_size = target.stat().st_size
    new_size = len(content.encode("utf-8"))
    new_lines = content.count("\n") + (1 if content else 0)

    # Compute unified diff
    old_lines_list = old_text.splitlines()
    new_lines_list = content.splitlines()
    diff_lines = list(
        difflib.unified_diff(
            old_lines_list,
            new_lines_list,
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
            lineterm="",
        )
    )
    added = sum(
        1 for ln in diff_lines if ln.startswith("+") and not ln.startswith("+++")
    )
    removed = sum(
        1 for ln in diff_lines if ln.startswith("-") and not ln.startswith("---")
    )
    diff_text = "\n".join(diff_lines[:50])
    if len(diff_lines) > 50:
        diff_text += f"\n... ({len(diff_lines) - 50} more lines)"

    # Audit
    _audit(
        "📝 File Modified",
        f"{rel_path}: +{added} -{removed} lines"
        f" ({old_size:,} → {new_size:,} bytes, encrypted)",
        action="modified",
        target=rel_path,
        detail={
            "file": rel_path,
            "original_name": original_name,
            "encrypted": True,
            "lines_added": added,
            "lines_removed": removed,
            "diff": diff_text,
        },
        before_state={"lines": old_lines, "size": old_size},
        after_state={"lines": new_lines, "size": new_size, "enc_size": new_enc_size},
    )

    logger.info(
        "Saved encrypted file: %s (%d bytes, +%d -%d lines)",
        rel_path,
        new_size,
        added,
        removed,
    )
    return {"success": True, "size": new_enc_size}

