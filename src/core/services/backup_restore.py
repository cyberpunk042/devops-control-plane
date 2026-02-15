"""Backup restore, import, wipe, and in-place encryption operations."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tarfile
import tempfile
from pathlib import Path

from src.core.services.backup_common import (
    backup_dir_for, resolve_folder, read_manifest,
    get_enc_key, encrypt_archive, decrypt_archive,
)

logger = logging.getLogger(__name__)

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
