"""
Admin API — Backup restore / import / wipe / delete endpoints.

Split from routes_backup.py. Handles restoring from archives, additive imports,
factory-reset (wipe), and deleting backup archives.

Blueprint: backup_bp (imported from routes_backup)
Prefix: /api
Routes:
    /api/backup/restore  — restore (overwrite) from a .backup/ archive
    /api/backup/import   — import (additive) from an archive
    /api/backup/wipe     — factory-reset a folder (with optional backup)
    /api/backup/delete   — delete a .backup/ archive
"""

from __future__ import annotations

import io
import json
import logging
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from flask import jsonify, request

from .routes_backup import (
    backup_bp,
    _project_root,
    _resolve_folder,
    _backup_dir_for,
    _read_manifest,
    _get_enc_key,
    _decrypt_archive,
    _classify,
)

logger = logging.getLogger(__name__)


# ── Restore ────────────────────────────────────────────────────────


@backup_bp.route("/backup/restore", methods=["POST"])
def api_restore():  # type: ignore[no-untyped-def]
    """Restore (OVERRIDE) files from a backup archive.

    JSON body:
        backup_path:      relative path to the .tar.gz
        paths:            optional list of specific file paths within the archive
                          to restore. If empty, restore all files.
        wipe_first:       if true, delete all files in target_folder before restore
        target_folder:    folder to wipe (used with wipe_first; relative to root)
        encrypt_restored: encrypt plain files during restore
        decrypt_restored: decrypt .enc files during restore
    """
    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "").strip()
    selected_paths = set(data.get("paths", []))  # empty = all
    encrypt_restored = data.get("encrypt_restored", False)
    decrypt_restored = data.get("decrypt_restored", False)
    wipe_first = data.get("wipe_first", False)
    target_folder = data.get("target_folder", "").strip()

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

    # Encryption key for enc/dec options
    enc_key = ""
    if encrypt_restored or decrypt_restored:
        enc_key = _get_enc_key()
        if not enc_key:
            return jsonify({"error": "CONTENT_VAULT_ENC_KEY not set — cannot encrypt/decrypt during restore"}), 400

    # Handle encrypted archives
    is_encrypted = file_path.name.endswith(".enc")
    tar_path = file_path

    if is_encrypted:
        archive_key = _get_enc_key()
        if not archive_key:
            return jsonify({"error": "CONTENT_VAULT_ENC_KEY not set — cannot restore encrypted backup"}), 400
        try:
            tar_path = _decrypt_archive(file_path, archive_key)
        except Exception as e:
            return jsonify({"error": f"Failed to decrypt archive: {e}"}), 500

    # ── Wipe before restore ──────────────────────────────────────
    wiped_count = 0
    if wipe_first and target_folder:
        wipe_folder = _resolve_folder(target_folder)
        if wipe_folder is None:
            return jsonify({"error": f"Wipe folder not found: {target_folder}"}), 404

        # Collect files to wipe (excluding protected dirs)
        _protected = {".backup", ".git", ".github", ".venv", "venv", "__pycache__",
                       "node_modules", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
        to_wipe: list[Path] = []
        for f in sorted(wipe_folder.rglob("*")):
            if not f.is_file():
                continue
            # Skip if any part of the path is a protected directory
            parts = set(f.relative_to(wipe_folder).parts)
            if parts & _protected:
                continue
            to_wipe.append(f)

        if to_wipe:
            # Create safety backup before wipe
            safety_dir = _backup_dir_for(wipe_folder)
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
                return jsonify({"error": f"Pre-wipe backup failed (restore aborted): {e}"}), 500

            # Delete files
            for f in to_wipe:
                try:
                    # Clean up release sidecar + GitHub asset if present
                    from .content_release import cleanup_release_sidecar
                    cleanup_release_sidecar(f, root)

                    f.unlink()
                    wiped_count += 1
                except Exception:
                    pass

            # Clean up empty directories (bottom-up)
            for d in sorted(
                (d for d in wipe_folder.rglob("*") if d.is_dir()),
                reverse=True,
            ):
                if d.name in _protected:
                    continue
                try:
                    d.rmdir()  # only removes if empty
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

                # Selective restore: skip files not in selection
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

                    # Decrypt .enc files if requested
                    if decrypt_restored and member.name.endswith(".enc") and enc_key:
                        try:
                            # Write enc content to temp, decrypt it
                            import tempfile as _tmpmod
                            tmp_enc = Path(_tmpmod.mktemp(suffix=".enc"))
                            tmp_enc.write_bytes(content)
                            from .content_crypto import decrypt_file_to_memory
                            plaintext, _meta = decrypt_file_to_memory(tmp_enc, enc_key)
                            content = plaintext
                            # Strip .enc from destination
                            final_dest = root / member.name[:-4]
                            final_dest.parent.mkdir(parents=True, exist_ok=True)
                            tmp_enc.unlink(missing_ok=True)
                        except Exception:
                            pass  # fall through to write as-is

                    # Encrypt plain files if requested (skip already encrypted)
                    elif encrypt_restored and not member.name.endswith(".enc") and enc_key:
                        try:
                            import tempfile as _tmpmod
                            tmp_plain = Path(_tmpmod.mktemp(suffix=Path(member.name).suffix))
                            tmp_plain.write_bytes(content)
                            from .content_crypto import encrypt_file
                            enc_result = encrypt_file(tmp_plain, enc_key)
                            content = enc_result.read_bytes()
                            enc_result.unlink(missing_ok=True)
                            tmp_plain.unlink(missing_ok=True)
                            final_dest = root / (member.name + ".enc")
                            final_dest.parent.mkdir(parents=True, exist_ok=True)
                        except Exception:
                            pass  # fall through to write as-is

                    final_dest.write_bytes(content)
                    restored.append(str(final_dest.relative_to(root)))
                else:
                    skipped.append(member.name)

        logger.info("Restore: %d restored, %d skipped from %s", len(restored), len(skipped), backup_path)
        return jsonify({"success": True, "restored": restored, "skipped": skipped, "wiped_count": wiped_count})

    except Exception as e:
        logger.exception("Restore failed")
        return jsonify({"error": f"Restore failed: {e}"}), 500
    finally:
        # Clean up decrypted temp file
        if is_encrypted and tar_path != file_path and tar_path.exists():
            try:
                tar_path.unlink()
            except OSError:
                pass


# ── Import (additive) ──────────────────────────────────────────────


@backup_bp.route("/backup/import", methods=["POST"])
def api_import():  # type: ignore[no-untyped-def]
    """Import (ADDITIVE) from a backup archive. Existing files are skipped.

    JSON body:
        backup_path:  relative path to the .tar.gz
    """
    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "").strip()

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

    # Handle encrypted archives
    is_encrypted = file_path.name.endswith(".enc")
    tar_path = file_path

    if is_encrypted:
        enc_key = _get_enc_key()
        if not enc_key:
            return jsonify({"error": "CONTENT_VAULT_ENC_KEY not set"}), 400
        try:
            tar_path = _decrypt_archive(file_path, enc_key)
        except Exception as e:
            return jsonify({"error": f"Failed to decrypt archive: {e}"}), 500

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
        return jsonify({"success": True, "imported": imported, "skipped": skipped})

    except Exception as e:
        logger.exception("Import failed")
        return jsonify({"error": f"Import failed: {e}"}), 500
    finally:
        if is_encrypted and tar_path != file_path and tar_path.exists():
            try:
                tar_path.unlink()
            except OSError:
                pass


# ── Wipe (Factory Reset) ──────────────────────────────────────────


@backup_bp.route("/backup/wipe", methods=["POST"])
def api_wipe():  # type: ignore[no-untyped-def]
    """Factory-reset a folder: optionally back up first, then delete selected files.

    JSON body:
        target_folder:  folder to wipe (relative to project root)
        paths:          list of relative paths to delete (REQUIRED, no auto-wipe)
        create_backup:  whether to create a backup first (default: true)
    """
    data = request.get_json(silent=True) or {}
    target_folder = data.get("target_folder", "").strip()
    paths = data.get("paths", [])
    create_backup = data.get("create_backup", True)

    if not target_folder:
        return jsonify({"error": "Missing 'target_folder'"}), 400

    folder = _resolve_folder(target_folder)
    if folder is None:
        return jsonify({"error": f"Folder not found: {target_folder}"}), 404

    root = _project_root()

    if not paths:
        return jsonify({"error": "No paths specified — select files to wipe"}), 400

    # Determine what to wipe
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
        return jsonify({"error": "Nothing to wipe"}), 400

    # Optional backup first
    backup_info = None
    if create_backup:
        backup_dir = _backup_dir_for(folder)
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%dT%H%M%S")
        archive_name = f"backup_{timestamp}.tar.gz"
        archive_path = backup_dir / archive_name

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
                    arcname = str(f.relative_to(root))
                    tar.add(str(f), arcname=arcname)

            backup_info = {
                "filename": archive_name,
                "full_path": str(archive_path.relative_to(root)),
                "size_bytes": archive_path.stat().st_size,
            }
        except Exception as e:
            logger.exception("Pre-wipe backup failed")
            return jsonify({"error": f"Backup failed (wipe aborted): {e}"}), 500

    # Delete the files
    deleted: list[str] = []
    errors: list[str] = []
    for f in to_delete:
        try:
            # Clean up release sidecar + GitHub asset if present
            from .content_release import cleanup_release_sidecar
            cleanup_release_sidecar(f, root)

            f.unlink()
            deleted.append(str(f.relative_to(root)))
        except Exception as e:
            errors.append(f"{f.relative_to(root)}: {e}")

    # Clean up empty directories (bottom-up), but keep .backup/
    for dirpath in sorted(set(f.parent for f in to_delete), key=lambda d: -len(d.parts)):
        try:
            if dirpath.is_dir() and dirpath != folder and dirpath.name != ".backup":
                remaining = [x for x in dirpath.iterdir() if x.name != ".backup"]
                if not remaining:
                    dirpath.rmdir()
        except OSError:
            pass

    logger.info("Wipe: %d deleted, %d errors in %s", len(deleted), len(errors), target_folder)

    return jsonify({
        "success": True,
        "deleted": deleted,
        "errors": errors,
        "backup": backup_info,
    })


# ── Delete a backup ────────────────────────────────────────────────


@backup_bp.route("/backup/delete", methods=["POST"])
def api_delete():  # type: ignore[no-untyped-def]
    """Delete a backup archive.

    JSON body:
        backup_path:  relative path to the .tar.gz
    """
    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "").strip()

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

    if ".backup" not in file_path.parts:
        return jsonify({"error": "Can only delete files in .backup/ directories"}), 400

    # Clean up release sidecar + GitHub asset if present
    from .content_release import cleanup_release_sidecar
    cleanup_release_sidecar(file_path, root)

    file_path.unlink()
    logger.info("Deleted backup: %s", backup_path)
    return jsonify({"success": True, "deleted": backup_path})
