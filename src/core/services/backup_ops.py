"""
Backup & Restore operations — channel-independent service.

Creates, lists, previews, restores, and manages `.tar.gz` backup
archives. No Flask dependency.

Extracted from ``src/ui/web/routes_backup*.py``.
"""

from __future__ import annotations

import io
import json
import logging
import re
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════

SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".mypy_cache", ".ruff_cache", ".pytest_cache", ".tox",
    "dist", "build", ".egg-info", ".idea", ".vscode",
    ".gemini", ".agent", "state",
})

MEDIA_EXT = frozenset({
    ".mp4", ".webm", ".mov", ".avi", ".mkv",
    ".mp3", ".wav", ".flac", ".ogg", ".aac",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".tiff",
})

DOC_EXT = frozenset({
    ".md", ".txt", ".pdf", ".json", ".yaml", ".yml", ".xml",
    ".csv", ".docx", ".rst", ".html", ".htm", ".toml", ".ini",
})


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def classify_file(path: Path) -> str:
    """Classify a file by type using the shared content vault classifier."""
    from src.core.services.content_crypto import classify_file as _classify
    return _classify(path)


def backup_dir_for(folder: Path) -> Path:
    """Get / create a .backup/ directory inside the given folder."""
    d = folder / ".backup"
    d.mkdir(exist_ok=True)
    return d


def safe_backup_name(name: str) -> bool:
    """Validate backup filename pattern."""
    return bool(re.match(r"^backup_\d{8}T\d{6}\.tar\.gz(\.enc)?$", name))


def resolve_folder(project_root: Path, rel_path: str) -> Path | None:
    """Resolve a relative folder safely within project root."""
    target = (project_root / rel_path).resolve()
    try:
        target.relative_to(project_root)
    except ValueError:
        return None
    if not target.is_dir():
        return None
    return target


def read_manifest(archive_path: Path) -> dict | None:
    """Read backup_manifest.json from a tar.gz archive."""
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            try:
                member = tar.getmember("backup_manifest.json")
                fobj = tar.extractfile(member)
                if fobj:
                    return json.loads(fobj.read().decode("utf-8"))
            except KeyError:
                return None
    except Exception:
        return None
    return None


def get_enc_key(project_root: Path) -> str:
    """Read CONTENT_VAULT_ENC_KEY from .env."""
    env_path = project_root / ".env"
    if not env_path.is_file():
        return ""
    try:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("CONTENT_VAULT_ENC_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def encrypt_archive(archive_path: Path, passphrase: str) -> Path:
    """Encrypt a .tar.gz archive using COVAULT format. Returns path to .tar.gz.enc."""
    from src.core.services.content_crypto import encrypt_file
    enc_path = encrypt_file(archive_path, passphrase)
    archive_path.unlink()
    return enc_path


def decrypt_archive(enc_path: Path, passphrase: str) -> Path:
    """Decrypt a .tar.gz.enc archive to a temp file.

    Caller is responsible for cleaning up the returned temp file.
    """
    from src.core.services.content_crypto import decrypt_file
    tmp_path = Path(tempfile.mktemp(suffix=".tar.gz"))
    dec_path = decrypt_file(enc_path, passphrase, output_path=tmp_path)
    return dec_path


# ═══════════════════════════════════════════════════════════════════
#  Folder scanning
# ═══════════════════════════════════════════════════════════════════


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

        return {
            "success": True,
            "filename": final_name,
            "backup_folder": str(bak_dir.relative_to(project_root)),
            "full_path": str(final_path.relative_to(project_root)),
            "size_bytes": final_path.stat().st_size,
            "encrypted": encrypt_archive_flag,
            "manifest": manifest,
        }

    except Exception as e:
        logger.exception("Failed to create backup")
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

    file_path.unlink()

    # Also remove release sidecar if present
    release_meta = file_path.parent / f"{file_path.name}.release.json"
    if release_meta.exists():
        release_meta.unlink()

    logger.info("Backup deleted: %s", backup_path)
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
    return {
        "ok": True,
        "old_name": file_path.name,
        "new_name": safe_name,
        "full_path": str(new_path.relative_to(project_root)),
    }


# ═══════════════════════════════════════════════════════════════════
#  Restore / Import / Wipe
# ═══════════════════════════════════════════════════════════════════

_PROTECTED_DIRS = frozenset({
    ".backup", ".git", ".github", ".venv", "venv", "__pycache__",
    "node_modules", ".mypy_cache", ".ruff_cache", ".pytest_cache",
})


def restore_backup(
    project_root: Path,
    backup_path: str,
    *,
    paths: list[str] | None = None,
    wipe_first: bool = False,
    target_folder: str = "",
    encrypt_restored: bool = False,
    decrypt_restored: bool = False,
) -> dict:
    """Restore (OVERRIDE) files from a backup archive."""
    if not backup_path:
        return {"error": "Missing 'backup_path'"}

    root = project_root
    file_path = (root / backup_path).resolve()

    try:
        file_path.relative_to(root)
    except ValueError:
        return {"error": "Invalid path"}

    if not file_path.exists():
        return {"error": "File not found"}

    selected_paths = set(paths) if paths else set()

    # Encryption key for enc/dec options
    enc_key = ""
    if encrypt_restored or decrypt_restored:
        enc_key = get_enc_key(root)
        if not enc_key:
            return {"error": "CONTENT_VAULT_ENC_KEY not set — cannot encrypt/decrypt during restore"}

    # Handle encrypted archives
    is_encrypted = file_path.name.endswith(".enc")
    tar_path = file_path

    if is_encrypted:
        archive_key = get_enc_key(root)
        if not archive_key:
            return {"error": "CONTENT_VAULT_ENC_KEY not set — cannot restore encrypted backup"}
        try:
            tar_path = decrypt_archive(file_path, archive_key)
        except Exception as e:
            return {"error": f"Failed to decrypt archive: {e}"}

    # Wipe before restore
    wiped_count = 0
    if wipe_first and target_folder:
        wipe_folder_path = resolve_folder(root, target_folder)
        if wipe_folder_path is None:
            return {"error": f"Wipe folder not found: {target_folder}"}

        to_wipe: list[Path] = []
        for f in sorted(wipe_folder_path.rglob("*")):
            if not f.is_file():
                continue
            parts = set(f.relative_to(wipe_folder_path).parts)
            if parts & _PROTECTED_DIRS:
                continue
            to_wipe.append(f)

        if to_wipe:
            # Safety backup
            safety_dir = backup_dir_for(wipe_folder_path)
            now = datetime.now(timezone.utc)
            safety_name = f"backup_{now.strftime('%Y%m%dT%H%M%S')}_pre_wipe.tar.gz"
            safety_path = safety_dir / safety_name
            try:
                with tarfile.open(safety_path, "w:gz") as tar:
                    manifest = {
                        "format_version": 2,
                        "created_at": now.isoformat(),
                        "trigger": "pre_wipe_restore",
                        "target_folder": target_folder,
                        "stats": {"total_files": len(to_wipe)},
                        "files": [str(f.relative_to(root)) for f in to_wipe],
                    }
                    mb = json.dumps(manifest, indent=2).encode("utf-8")
                    info_m = tarfile.TarInfo(name="backup_manifest.json")
                    info_m.size = len(mb)
                    info_m.mtime = int(now.timestamp())
                    tar.addfile(info_m, io.BytesIO(mb))
                    for f in to_wipe:
                        tar.add(str(f), arcname=str(f.relative_to(root)))
            except Exception as e:
                logger.exception("Pre-wipe backup failed — aborting restore")
                return {"error": f"Pre-wipe backup failed (restore aborted): {e}"}

            for f in to_wipe:
                try:
                    _cleanup_release_sidecar(f, root)
                    f.unlink()
                    wiped_count += 1
                except Exception:
                    pass

            # Clean up empty directories
            for d in sorted(
                (d for d in wipe_folder_path.rglob("*") if d.is_dir()),
                reverse=True,
            ):
                if d.name in _PROTECTED_DIRS:
                    continue
                try:
                    d.rmdir()
                except OSError:
                    pass

            logger.info("Pre-restore wipe: %d files deleted from %s", wiped_count, target_folder)

    restored: list[str] = []
    skipped: list[str] = []

    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile() or member.name == "backup_manifest.json":
                    continue

                if selected_paths and member.name not in selected_paths:
                    continue

                dest = root / member.name
                try:
                    dest.resolve().relative_to(root)
                except ValueError:
                    skipped.append(member.name)
                    continue

                dest.parent.mkdir(parents=True, exist_ok=True)
                fobj = tar.extractfile(member)
                if fobj:
                    content = fobj.read()
                    final_dest = dest

                    if decrypt_restored and member.name.endswith(".enc") and enc_key:
                        try:
                            tmp_enc = Path(tempfile.mktemp(suffix=".enc"))
                            tmp_enc.write_bytes(content)
                            from src.core.services.content_crypto import decrypt_file_to_memory
                            plaintext, _meta = decrypt_file_to_memory(tmp_enc, enc_key)
                            content = plaintext
                            final_dest = root / member.name[:-4]
                            final_dest.parent.mkdir(parents=True, exist_ok=True)
                            tmp_enc.unlink(missing_ok=True)
                        except Exception:
                            pass

                    elif encrypt_restored and not member.name.endswith(".enc") and enc_key:
                        try:
                            tmp_plain = Path(tempfile.mktemp(suffix=Path(member.name).suffix))
                            tmp_plain.write_bytes(content)
                            from src.core.services.content_crypto import encrypt_file
                            enc_result = encrypt_file(tmp_plain, enc_key)
                            content = enc_result.read_bytes()
                            enc_result.unlink(missing_ok=True)
                            tmp_plain.unlink(missing_ok=True)
                            final_dest = root / (member.name + ".enc")
                            final_dest.parent.mkdir(parents=True, exist_ok=True)
                        except Exception:
                            pass

                    final_dest.write_bytes(content)
                    restored.append(str(final_dest.relative_to(root)))
                else:
                    skipped.append(member.name)

        logger.info("Restore: %d restored, %d skipped from %s", len(restored), len(skipped), backup_path)
        return {"success": True, "restored": restored, "skipped": skipped, "wiped_count": wiped_count}

    except Exception as e:
        logger.exception("Restore failed")
        return {"error": f"Restore failed: {e}"}
    finally:
        if is_encrypted and tar_path != file_path and tar_path.exists():
            try:
                tar_path.unlink()
            except OSError:
                pass


def import_backup(project_root: Path, backup_path: str) -> dict:
    """Import (ADDITIVE) from a backup archive. Existing files are skipped."""
    if not backup_path:
        return {"error": "Missing 'backup_path'"}

    root = project_root
    file_path = (root / backup_path).resolve()

    try:
        file_path.relative_to(root)
    except ValueError:
        return {"error": "Invalid path"}

    if not file_path.exists():
        return {"error": "File not found"}

    is_encrypted = file_path.name.endswith(".enc")
    tar_path = file_path

    if is_encrypted:
        enc_key = get_enc_key(root)
        if not enc_key:
            return {"error": "CONTENT_VAULT_ENC_KEY not set"}
        try:
            tar_path = decrypt_archive(file_path, enc_key)
        except Exception as e:
            return {"error": f"Failed to decrypt archive: {e}"}

    imported: list[str] = []
    skipped: list[str] = []

    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile() or member.name == "backup_manifest.json":
                    continue

                dest = root / member.name
                try:
                    dest.resolve().relative_to(root)
                except ValueError:
                    skipped.append(f"{member.name} (path traversal)")
                    continue

                if dest.exists():
                    skipped.append(f"{member.name} (exists)")
                    continue

                dest.parent.mkdir(parents=True, exist_ok=True)
                fobj = tar.extractfile(member)
                if fobj:
                    dest.write_bytes(fobj.read())
                    imported.append(member.name)
                else:
                    skipped.append(f"{member.name} (empty)")

        logger.info("Import: %d imported, %d skipped from %s", len(imported), len(skipped), backup_path)
        return {"success": True, "imported": imported, "skipped": skipped}

    except Exception as e:
        logger.exception("Import failed")
        return {"error": f"Import failed: {e}"}
    finally:
        if is_encrypted and tar_path != file_path and tar_path.exists():
            try:
                tar_path.unlink()
            except OSError:
                pass


def wipe_folder(
    project_root: Path,
    target_folder: str,
    paths: list[str],
    *,
    create_backup_first: bool = True,
) -> dict:
    """Factory-reset a folder: optionally back up first, then delete selected files."""
    if not target_folder:
        return {"error": "Missing 'target_folder'"}
    if not paths:
        return {"error": "No paths specified — select files to wipe"}

    folder = resolve_folder(project_root, target_folder)
    if folder is None:
        return {"error": f"Folder not found: {target_folder}"}

    root = project_root

    to_delete: list[Path] = []
    for p in paths:
        abs_p = (root / p).resolve()
        try:
            abs_p.relative_to(root)
        except ValueError:
            continue
        if abs_p.is_file():
            to_delete.append(abs_p)
        elif abs_p.is_dir() and abs_p.name != ".backup":
            for f in sorted(abs_p.rglob("*")):
                if f.is_file() and ".backup" not in f.parts:
                    to_delete.append(f)

    if not to_delete:
        return {"error": "Nothing to wipe"}

    backup_info = None
    if create_backup_first:
        bak_dir = backup_dir_for(folder)
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%dT%H%M%S")
        archive_name = f"backup_{timestamp}.tar.gz"
        archive_path = bak_dir / archive_name

        manifest = {
            "format_version": 2,
            "created_at": now.isoformat(),
            "trigger": "factory_reset",
            "target_folder": target_folder,
            "stats": {
                "total_files": len(to_delete),
                "total_bytes": sum(f.stat().st_size for f in to_delete),
            },
            "files": [str(f.relative_to(root)) for f in to_delete],
        }

        try:
            with tarfile.open(archive_path, "w:gz") as tar:
                manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
                info = tarfile.TarInfo(name="backup_manifest.json")
                info.size = len(manifest_bytes)
                info.mtime = int(now.timestamp())
                tar.addfile(info, io.BytesIO(manifest_bytes))
                for f in to_delete:
                    tar.add(str(f), arcname=str(f.relative_to(root)))
            backup_info = {
                "filename": archive_name,
                "full_path": str(archive_path.relative_to(root)),
                "size_bytes": archive_path.stat().st_size,
            }
        except Exception as e:
            logger.exception("Pre-wipe backup failed")
            return {"error": f"Backup failed (wipe aborted): {e}"}

    deleted: list[str] = []
    errors: list[str] = []
    for f in to_delete:
        try:
            _cleanup_release_sidecar(f, root)
            f.unlink()
            deleted.append(str(f.relative_to(root)))
        except Exception as e:
            errors.append(f"{f.relative_to(root)}: {e}")

    for dirpath in sorted(set(f.parent for f in to_delete), key=lambda d: -len(d.parts)):
        try:
            if dirpath.is_dir() and dirpath != folder and dirpath.name != ".backup":
                remaining = [x for x in dirpath.iterdir() if x.name != ".backup"]
                if not remaining:
                    dirpath.rmdir()
        except OSError:
            pass

    logger.info("Wipe: %d deleted, %d errors in %s", len(deleted), len(errors), target_folder)
    return {"success": True, "deleted": deleted, "errors": errors, "backup": backup_info}


# ═══════════════════════════════════════════════════════════════════
#  In-place encrypt / decrypt
# ═══════════════════════════════════════════════════════════════════


def encrypt_backup_inplace(project_root: Path, backup_path: str) -> dict:
    """Encrypt an existing .tar.gz backup in place."""
    if not backup_path:
        return {"error": "Missing 'backup_path'"}

    passphrase = get_enc_key(project_root)
    if not passphrase:
        return {"error": "No CONTENT_VAULT_ENC_KEY configured"}

    file_path = (project_root / backup_path).resolve()
    try:
        file_path.relative_to(project_root)
    except ValueError:
        return {"error": "Invalid path"}

    if not file_path.exists():
        return {"error": "File not found"}

    if file_path.name.endswith(".enc"):
        return {"error": "Already encrypted"}

    try:
        enc_path = encrypt_archive(file_path, passphrase)
        return {
            "success": True,
            "filename": enc_path.name,
            "full_path": str(enc_path.relative_to(project_root)),
            "size_bytes": enc_path.stat().st_size,
        }
    except Exception as e:
        logger.exception("Failed to encrypt backup")
        return {"error": f"Encryption failed: {e}"}


def decrypt_backup_inplace(project_root: Path, backup_path: str) -> dict:
    """Decrypt an existing .tar.gz.enc backup in place."""
    if not backup_path:
        return {"error": "Missing 'backup_path'"}

    passphrase = get_enc_key(project_root)
    if not passphrase:
        return {"error": "No CONTENT_VAULT_ENC_KEY configured"}

    file_path = (project_root / backup_path).resolve()
    try:
        file_path.relative_to(project_root)
    except ValueError:
        return {"error": "Invalid path"}

    if not file_path.exists():
        return {"error": "File not found"}

    if not file_path.name.endswith(".enc"):
        return {"error": "Not an encrypted archive"}

    try:
        dec_tmp = decrypt_archive(file_path, passphrase)
        dec_final = file_path.parent / file_path.name[:-4]
        dec_tmp.rename(dec_final)
        file_path.unlink()
        return {
            "success": True,
            "filename": dec_final.name,
            "full_path": str(dec_final.relative_to(project_root)),
            "size_bytes": dec_final.stat().st_size,
        }
    except Exception as e:
        logger.exception("Failed to decrypt backup")
        return {"error": f"Decryption failed: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  Git tracking (mark-special)
# ═══════════════════════════════════════════════════════════════════

_SPECIAL_MAX_BYTES = 25 * 1024 * 1024  # 25 MB


def mark_special(project_root: Path, backup_path: str, *, unmark: bool = False) -> dict:
    """Force-add a backup to git (git add -f), or unmark (git rm --cached)."""
    if not backup_path:
        return {"error": "Missing 'backup_path'"}

    file_path = (project_root / backup_path).resolve()
    try:
        file_path.relative_to(project_root)
    except ValueError:
        return {"error": "Invalid path"}

    if not file_path.exists():
        return {"error": "File not found"}

    if unmark:
        try:
            subprocess.run(
                ["git", "rm", "--cached", str(file_path)],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=15,
            )
            return {"success": True, "message": "Removed from git tracking"}
        except Exception as e:
            return {"error": f"git rm --cached failed: {e}"}

    size = file_path.stat().st_size
    if size > _SPECIAL_MAX_BYTES:
        size_mb = size / (1024 * 1024)
        return {
            "error": (
                f"File too large for git ({size_mb:.1f} MB). "
                f"Maximum is {_SPECIAL_MAX_BYTES // (1024 * 1024)} MB. "
                "Use '🚀 Upload to Release' instead."
            ),
        }

    try:
        result = subprocess.run(
            ["git", "add", "-f", str(file_path)],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return {"error": f"git add -f failed: {result.stderr[:200]}"}
        return {
            "success": True,
            "message": f"Added to git (force): {file_path.name}",
            "size_bytes": size,
        }
    except Exception as e:
        logger.exception("Failed to mark backup as special")
        return {"error": f"git add -f failed: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  File tree scan (for archive panel)
# ═══════════════════════════════════════════════════════════════════


def file_tree_scan(
    project_root: Path,
    rel_path: str,
    *,
    allowed_types: set[str] | None = None,
    max_depth: int = 5,
    respect_gitignore: bool = False,
) -> dict:
    """Return an expandable file tree filtered by type."""
    if not rel_path:
        return {"error": "Missing 'path'"}

    folder = resolve_folder(project_root, rel_path)
    if folder is None:
        return {"error": f"Folder not found: {rel_path}"}

    if allowed_types is None:
        allowed_types = {
            "document", "code", "script", "config", "data",
            "image", "video", "audio", "archive", "encrypted", "other",
        }

    max_depth = min(max_depth, 10)

    # Build set of allowed files if respecting gitignore
    gitignore_allowed: set[str] | None = None
    if respect_gitignore:
        try:
            result = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                gitignore_allowed = set(result.stdout.strip().splitlines())
        except Exception:
            pass

    def _scan(directory: Path, depth: int) -> list[dict]:
        if depth > max_depth:
            return []
        items: list[dict] = []
        try:
            entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return []

        for entry in entries:
            if entry.name.startswith(".") or entry.name in SKIP_DIRS:
                continue

            if entry.is_dir():
                children = _scan(entry, depth + 1)
                if children:
                    items.append({
                        "name": entry.name,
                        "path": str(entry.resolve().relative_to(project_root)),
                        "type": "directory",
                        "children": children,
                        "count": sum(
                            c.get("count", 1) if c["type"] == "directory" else 1
                            for c in children
                        ),
                    })
            elif entry.is_file():
                if gitignore_allowed is not None:
                    rel_file = str(entry.resolve().relative_to(project_root))
                    if rel_file not in gitignore_allowed:
                        continue
                ftype = classify_file(entry)
                if ftype in allowed_types:
                    items.append({
                        "name": entry.name,
                        "path": str(entry.resolve().relative_to(project_root)),
                        "type": ftype,
                        "size": entry.stat().st_size,
                    })
        return items

    tree = _scan(folder, 0)

    def _count(nodes: list[dict]) -> dict[str, int]:
        c: dict[str, int] = {}
        for n in nodes:
            if n["type"] == "directory":
                sub = _count(n["children"])
                for k, v in sub.items():
                    c[k] = c.get(k, 0) + v
            else:
                c[n["type"]] = c.get(n["type"], 0) + 1
        return c

    counts = _count(tree)
    return {"root": rel_path, "tree": tree, "counts": counts}


# ═══════════════════════════════════════════════════════════════════
#  Internal helpers
# ═══════════════════════════════════════════════════════════════════


def _cleanup_release_sidecar(file_path: Path, project_root: Path) -> None:
    """Clean up release sidecar + GitHub asset if present."""
    try:
        from src.core.services.content_release import cleanup_release_sidecar
        cleanup_release_sidecar(file_path, project_root)
    except (ImportError, Exception):
        pass
