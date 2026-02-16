"""Backup archive operations — create, list, preview, delete, rename."""

from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.core.services.backup_common import (
    classify_file, backup_dir_for, safe_backup_name, resolve_folder,
    read_manifest, get_enc_key, encrypt_archive,
    SKIP_DIRS, MEDIA_EXT, DOC_EXT,
)

logger = logging.getLogger(__name__)


from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("backup")

def folder_tree(project_root: Path, *, max_depth: int = 6) -> list[dict]:
    """Return the full recursive directory tree for folder selection."""
    max_depth = min(max_depth, 10)

    def _scan_dirs(directory: Path, depth: int) -> list[dict]:
        if depth > max_depth:
            return []
        items: list[dict] = []
        try:
            entries = sorted(directory.iterdir(), key=lambda e: e.name.lower())
        except PermissionError:
            return []

        for entry in entries:
            if not entry.is_dir():
                continue
            if entry.name.startswith(".") or entry.name in SKIP_DIRS:
                continue

            rel = str(entry.relative_to(project_root))
            direct_files = sum(
                1 for f in entry.iterdir()
                if f.is_file() and not f.name.startswith(".")
            )
            children = _scan_dirs(entry, depth + 1)
            has_backup = (entry / ".backup").is_dir()

            items.append({
                "name": entry.name,
                "path": rel,
                "files": direct_files,
                "has_backup": has_backup,
                "children": children,
            })
        return items

    return _scan_dirs(project_root, 0)


def list_folders(project_root: Path) -> list[dict]:
    """Flat list of all top-level scannable folders."""
    folders: list[dict] = []
    for entry in sorted(project_root.iterdir()):
        if not entry.is_dir() or entry.name.startswith(".") or entry.name in SKIP_DIRS:
            continue
        folders.append({"name": entry.name, "path": entry.name})
    return folders


# ═══════════════════════════════════════════════════════════════════
#  Archive operations
# ═══════════════════════════════════════════════════════════════════


def create_backup(
    project_root: Path,
    target_folder: str,
    paths: list[str],
    *,
    label: str = "admin_export",
    decrypt_enc: bool = False,
    encrypt_archive_flag: bool = False,
    custom_name: str = "",
) -> dict:
    """Create a backup archive from selected files/folders.

    Returns dict with success/error info and manifest.
    """
    if not target_folder:
        return {"error": "Missing 'target_folder'"}
    if not paths:
        return {"error": "No paths selected"}

    folder = resolve_folder(project_root, target_folder)
    if folder is None:
        return {"error": f"Folder not found: {target_folder}"}

    enc_key = get_enc_key(project_root) if (decrypt_enc or encrypt_archive_flag) else ""
    if (decrypt_enc or encrypt_archive_flag) and not enc_key:
        return {"error": "CONTENT_VAULT_ENC_KEY not set — configure in Secrets tab"}

    # Resolve all selected paths to actual files
    files: list[tuple[Path, str]] = []  # (abs_path, arcname)
    for p in paths:
        abs_p = (project_root / p).resolve()
        try:
            abs_p.relative_to(project_root)
        except ValueError:
            continue

        if abs_p.is_file():
            files.append((abs_p, p))
        elif abs_p.is_dir():
            for f in sorted(abs_p.rglob("*")):
                if f.is_file() and not any(
                    part.startswith(".") for part in f.relative_to(project_root).parts
                ):
                    files.append((f, str(f.relative_to(project_root))))

    if not files:
        return {"error": "No files found in selection"}

    bak_dir = backup_dir_for(folder)
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%S")

    if custom_name:
        safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', custom_name)
        if not safe_name.endswith(".tar.gz"):
            safe_name += ".tar.gz"
        archive_name = safe_name
    else:
        archive_name = f"backup_{timestamp}.tar.gz"
    archive_path = bak_dir / archive_name

    # Count by type
    counts: dict[str, int] = {}
    total_bytes = 0
    for f, _ in files:
        ftype = classify_file(f)
        counts[ftype] = counts.get(ftype, 0) + 1
        total_bytes += f.stat().st_size

    manifest = {
        "format_version": 2,
        "created_at": now.isoformat(),
        "trigger": label,
        "target_folder": target_folder,
        "decrypt_enc": decrypt_enc,
        "encrypt_archive": encrypt_archive_flag,
        "stats": {
            "total_files": len(files),
            "total_bytes": total_bytes,
            **{f"{k}_count": v for k, v in counts.items()},
        },
        "files": [p for _, p in files],
    }

    try:
        with tarfile.open(archive_path, "w:gz") as tar:
            # Manifest
            manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
            info = tarfile.TarInfo(name="backup_manifest.json")
            info.size = len(manifest_bytes)
            info.mtime = int(now.timestamp())
            tar.addfile(info, io.BytesIO(manifest_bytes))

            for file_path, arcname in files:
                if decrypt_enc and file_path.suffix.lower() == ".enc" and enc_key:
                    try:
                        from src.core.services.content_crypto import decrypt_file_to_memory
                        plain_bytes, meta = decrypt_file_to_memory(file_path, enc_key)
                        plain_name = arcname
                        if plain_name.endswith(".enc"):
                            plain_name = plain_name[:-4]
                        member = tarfile.TarInfo(name=plain_name)
                        member.size = len(plain_bytes)
                        member.mtime = int(now.timestamp())
                        tar.addfile(member, io.BytesIO(plain_bytes))
                    except Exception as e:
                        logger.warning("Could not decrypt %s, adding as-is: %s", arcname, e)
                        tar.add(str(file_path), arcname=arcname)
                else:
                    tar.add(str(file_path), arcname=arcname)

        final_path = archive_path
        final_name = archive_name
        if encrypt_archive_flag and enc_key:
            final_path = encrypt_archive(archive_path, enc_key)
            final_name = final_path.name

        logger.info(
            "Backup created: %s/%s (%d files, %d bytes)",
            target_folder, final_name, len(files), final_path.stat().st_size,
        )

        result = {
            "success": True,
            "filename": final_name,
            "backup_folder": str(bak_dir.relative_to(project_root)),
            "full_path": str(final_path.relative_to(project_root)),
            "size_bytes": final_path.stat().st_size,
            "encrypted": encrypt_archive_flag,
            "manifest": manifest,
        }
        _audit(
            "📦 Backup Created",
            f"{target_folder} → {final_name} ({len(files)} files, {final_path.stat().st_size:,} B)"
            + (" · encrypted" if encrypt_archive_flag else ""),
            action="created",
            target=final_name,
            detail={"files": [p for _, p in files]},
            before_state={
                "source_folder": target_folder,
                "selected_files": len(files),
                "total_size": f"{total_bytes:,} B",
                **({
                    "decrypt_enc_files": True,
                } if decrypt_enc else {}),
            },
            after_state={
                "archive": final_name,
                "archive_size": f"{final_path.stat().st_size:,} B",
                "encrypted": encrypt_archive_flag,
                **{f"{k}_count": v for k, v in counts.items()},
            },
        )
        return result

    except Exception as e:
        logger.exception("Failed to create backup")
        _audit(
            "❌ Backup Export Failed",
            f"{target_folder}: {e}",
            before_state={"source_folder": target_folder, "attempted_files": len(files)},
        )
        if archive_path.exists():
            archive_path.unlink()
        return {"error": f"Export failed: {e}"}


def list_backups(project_root: Path, rel_path: str, *, check_release: bool = False) -> dict:
    """List backups in a folder's .backup/ directory."""
    if not rel_path:
        return {"error": "Missing 'path'"}

    folder = resolve_folder(project_root, rel_path)
    if folder is None:
        return {"backups": []}

    backup_dir = folder / ".backup"
    if not backup_dir.is_dir():
        return {"backups": []}

    # Optionally fetch remote release assets
    remote_assets: set[str] | None = None
    if check_release:
        from src.core.services.content_release import list_release_assets
        remote = list_release_assets(project_root)
        if remote.get("available"):
            remote_assets = {a["name"] for a in remote["assets"]}

    all_archives: set[Path] = set()
    for pattern in ("backup_*.tar.gz", "backup_*.tar.gz.enc", "*.tar.gz", "*.tar.gz.enc"):
        all_archives.update(backup_dir.glob(pattern))

    archives = sorted(
        [a for a in all_archives if not a.name.endswith(".release.json")],
        key=lambda a: a.name,
        reverse=True,
    )

    # Check git tracking in batch
    git_tracked: set[str] = set()
    try:
        result = subprocess.run(
            ["git", "ls-files", str(backup_dir)],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                git_tracked.add(Path(line).name)
    except Exception:
        pass

    all_backups: list[dict] = []
    for a in archives:
        is_encrypted = a.name.endswith(".enc")
        entry: dict = {
            "filename": a.name,
            "folder": rel_path,
            "full_path": str(a.relative_to(project_root)),
            "size_bytes": a.stat().st_size,
            "encrypted": is_encrypted,
            "git_tracked": a.name in git_tracked,
        }
        if not is_encrypted:
            manifest = read_manifest(a)
            if manifest:
                entry["manifest"] = manifest

        # Check for release metadata
        release_meta_path = a.parent / f"{a.name}.release.json"
        if release_meta_path.exists():
            try:
                release_meta = json.loads(release_meta_path.read_text())
                file_id = release_meta.get("file_id", "")
                if file_id:
                    try:
                        from src.core.services.content_release import _release_upload_status
                        live_status = _release_upload_status.get(file_id, {})
                        if live_status:
                            release_meta["status"] = live_status.get("status", release_meta.get("status"))
                            if live_status.get("status") == "done":
                                release_meta["status"] = "done"
                                release_meta_path.write_text(json.dumps(release_meta, indent=2))
                        elif release_meta.get("status") == "uploading":
                            release_meta["status"] = "stale"
                    except ImportError:
                        if release_meta.get("status") == "uploading":
                            release_meta["status"] = "stale"
                entry["release"] = release_meta

                _rs = release_meta.get("status", "")
                if remote_assets is not None and _rs != "uploading":
                    asset_name = (
                        release_meta.get("old_asset_name")
                        or release_meta.get("asset_name")
                        or a.name
                    )
                    if asset_name not in remote_assets:
                        entry["release_orphaned"] = True
            except Exception:
                pass

        all_backups.append(entry)

    return {"backups": all_backups}


def preview_backup(project_root: Path, backup_path: str) -> dict:
    """Preview the file tree inside a backup archive."""
    if not backup_path:
        return {"error": "Missing 'path'"}

    file_path = (project_root / backup_path).resolve()
    try:
        file_path.relative_to(project_root)
    except ValueError:
        return {"error": "Invalid path"}

    if not file_path.exists():
        return {"error": "File not found"}

    is_encrypted = file_path.name.endswith(".enc")
    tar_path = file_path
    tmp_dec_path: Path | None = None

    if is_encrypted:
        enc_key = get_enc_key(project_root)
        if not enc_key:
            return {"error": "CONTENT_VAULT_ENC_KEY not set — cannot preview encrypted backup"}
        try:
            tar_path = decrypt_archive(file_path, enc_key)
            tmp_dec_path = tar_path
        except Exception as e:
            return {"error": f"Failed to decrypt archive: {e}"}

    manifest = read_manifest(tar_path)
    files: list[dict] = []

    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile() or member.name == "backup_manifest.json":
                    continue
                ftype = classify_file(Path(member.name))
                files.append({
                    "name": Path(member.name).name,
                    "path": member.name,
                    "type": ftype,
                    "size": member.size,
                })
    except Exception as e:
        return {"error": f"Failed to read archive: {e}"}
    finally:
        if tmp_dec_path and tmp_dec_path.exists():
            try:
                tmp_dec_path.unlink()
            except OSError:
                pass

    return {
        "backup_path": backup_path,
        "encrypted": is_encrypted,
        "manifest": manifest,
        "files": files,
        "total": len(files),
    }


def delete_backup(project_root: Path, backup_path: str) -> dict:
    """Delete a backup archive."""
    if not backup_path:
        return {"error": "Missing 'backup_path'"}

    file_path = (project_root / backup_path).resolve()
    try:
        file_path.relative_to(project_root)
    except ValueError:
        return {"error": "Invalid path"}

    if not file_path.exists():
        return {"error": "File not found"}

    # Clean up any GitHub Release asset + sidecar before deleting file
    try:
        from src.core.services.content_release import cleanup_release_sidecar
        cleanup_release_sidecar(file_path, project_root)
    except (ImportError, Exception):
        pass  # best-effort

    file_path.unlink()

    # Belt-and-suspenders: remove release sidecar if cleanup missed it
    release_meta = file_path.parent / f"{file_path.name}.release.json"
    if release_meta.exists():
        release_meta.unlink()

    logger.info("Backup deleted: %s", backup_path)
    _audit(
        "🗑️ Backup Deleted",
        f"{backup_path} permanently deleted",
        action="deleted",
        target=backup_path,
        before_state={"file": backup_path},
    )
    return {"ok": True, "deleted": backup_path}


def rename_backup(project_root: Path, backup_path: str, new_name: str) -> dict:
    """Rename a backup archive file."""
    if not backup_path or not new_name:
        return {"error": "Missing fields"}

    file_path = (project_root / backup_path).resolve()
    try:
        file_path.relative_to(project_root)
    except ValueError:
        return {"error": "Invalid path"}

    if not file_path.exists():
        return {"error": "File not found"}

    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', new_name)
    new_path = file_path.parent / safe_name

    if new_path.exists():
        return {"error": f"A file named '{safe_name}' already exists"}

    file_path.rename(new_path)

    # Move release sidecar if present
    old_sidecar = file_path.parent / f"{file_path.name}.release.json"
    new_sidecar = file_path.parent / f"{safe_name}.release.json"
    if old_sidecar.exists():
        # Update asset_name inside the sidecar
        try:
            meta = json.loads(old_sidecar.read_text())
            meta["old_asset_name"] = meta.get("asset_name", file_path.name)
            meta["asset_name"] = safe_name
            new_sidecar.write_text(json.dumps(meta, indent=2))
            old_sidecar.unlink()
        except Exception:
            old_sidecar.rename(new_sidecar)

    logger.info("Backup renamed: %s → %s", backup_path, safe_name)
    _audit(
        "✏️ Backup Renamed",
        f"{file_path.name} → {safe_name}",
        action="renamed",
        target=backup_path,
        before_state={"name": file_path.name},
        after_state={"name": safe_name},
    )
    return {
        "ok": True,
        "old_name": file_path.name,
        "new_name": safe_name,
        "full_path": str(new_path.relative_to(project_root)),
    }


def sanitize_backup_name(name: str, *, is_encrypted: bool = False) -> str:
    """Sanitize a backup archive name.

    Strips unsafe characters and ensures proper .tar.gz or .tar.gz.enc extension.

    Args:
        name: Raw filename to sanitize.
        is_encrypted: Whether the archive is encrypted.

    Returns:
        Safe filename string.
    """
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', name)
    if not (safe_name.endswith(".tar.gz") or safe_name.endswith(".tar.gz.enc")):
        if is_encrypted:
            safe_name += ".tar.gz.enc"
        else:
            safe_name += ".tar.gz"
    return safe_name


def upload_backup(
    project_root: Path,
    file_bytes: bytes,
    filename: str,
    target_folder: str,
) -> dict:
    """Upload a backup archive into a folder's .backup/.

    Validates the archive (manifest must exist for unencrypted archives),
    generates a safe filename, saves to disk, and records an audit event.

    Args:
        project_root: Project root directory.
        file_bytes: Raw bytes of the uploaded file.
        filename: Original filename of the upload.
        target_folder: Target folder name (e.g. "docs").

    Returns:
        Dict with success info, filename, metadata, or error.
    """
    if not filename or not filename.endswith((".tar.gz", ".gz", ".tar.gz.enc", ".enc")):
        return {"error": "File must be a .tar.gz or .tar.gz.enc archive"}

    folder = resolve_folder(project_root, target_folder)
    if folder is None:
        return {"error": f"Folder not found: {target_folder}", "_status": 404}

    bak_dir = backup_dir_for(folder)

    # Generate safe name
    if safe_backup_name(filename):
        dest_name = filename
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        is_enc = filename.endswith(".enc")
        dest_name = f"backup_{ts}.tar.gz{'.enc' if is_enc else ''}"

    dest = bak_dir / dest_name
    dest.write_bytes(file_bytes)

    # Try to read manifest (only works for unencrypted archives)
    manifest = None
    is_encrypted = dest.name.endswith(".enc")
    if not is_encrypted:
        manifest = read_manifest(dest)
        if not manifest:
            dest.unlink()
            return {"error": "Invalid archive: no backup_manifest.json found"}

    size_bytes = dest.stat().st_size

    _audit(
        "📤 Backup Uploaded",
        f"{dest_name} uploaded to {target_folder}/.backup/ ({size_bytes:,} bytes)"
        + (" (encrypted)" if is_encrypted else ""),
        action="uploaded",
        target=dest_name,
        detail={
            "filename": dest_name,
            "folder": target_folder,
            "size_bytes": size_bytes,
            "encrypted": is_encrypted,
        },
        after_state={"size": size_bytes, "encrypted": is_encrypted},
    )

    return {
        "success": True,
        "filename": dest_name,
        "folder": target_folder,
        "full_path": str(dest.relative_to(project_root)),
        "size_bytes": size_bytes,
        "encrypted": is_encrypted,
        "manifest": manifest,
    }
