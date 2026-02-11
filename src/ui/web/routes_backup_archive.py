"""
Admin API — Backup archive management endpoints.

Split from routes_backup.py. Handles export (create backup), list backups,
preview backup contents, download, and upload backup archives.

Blueprint: backup_bp (imported from routes_backup)
Prefix: /api
Routes:
    /api/backup/export           — create a backup archive from selected items
    /api/backup/list             — list backups in .backup/ of a target folder
    /api/backup/preview          — list files inside a backup archive
    /api/backup/download/<fn>    — download a backup archive
    /api/backup/upload           — upload an archive into a folder's .backup/
"""

from __future__ import annotations

import io
import json
import logging
import re
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from flask import jsonify, request, send_file

from .routes_backup import (
    backup_bp,
    _project_root,
    _resolve_folder,
    _backup_dir_for,
    _safe_backup_name,
    _read_manifest,
    _get_enc_key,
    _encrypt_archive,
    _decrypt_archive,
    _classify,
)

logger = logging.getLogger(__name__)


# ── Export (from selected paths) ───────────────────────────────────


@backup_bp.route("/backup/export", methods=["POST"])
def api_export():  # type: ignore[no-untyped-def]
    """Create a backup archive from selected files/folders.

    JSON body:
        target_folder:    root folder context (backup stored in target_folder/.backup/)
        paths:            list of relative paths to include
        label:            optional label for the backup
        decrypt_enc:      if true, decrypt .enc files into their plaintext form in the archive
        encrypt_archive:  if true, encrypt the entire .tar.gz with COVAULT format
    """
    data = request.get_json(silent=True) or {}
    target_folder = data.get("target_folder", "").strip()
    paths = data.get("paths", [])
    label = data.get("label", "admin_export")
    decrypt_enc = data.get("decrypt_enc", False)
    encrypt_archive = data.get("encrypt_archive", False)

    if not target_folder:
        return jsonify({"error": "Missing 'target_folder'"}), 400
    if not paths:
        return jsonify({"error": "No paths selected"}), 400

    folder = _resolve_folder(target_folder)
    if folder is None:
        return jsonify({"error": f"Folder not found: {target_folder}"}), 404

    root = _project_root()
    enc_key = _get_enc_key() if (decrypt_enc or encrypt_archive) else ""

    if (decrypt_enc or encrypt_archive) and not enc_key:
        return jsonify({"error": "CONTENT_VAULT_ENC_KEY not set — configure in Secrets tab"}), 400

    # Resolve all selected paths to actual files
    files: list[tuple[Path, str]] = []  # (abs_path, arcname)
    for p in paths:
        abs_p = (root / p).resolve()
        # Security check
        try:
            abs_p.relative_to(root)
        except ValueError:
            continue

        if abs_p.is_file():
            files.append((abs_p, p))
        elif abs_p.is_dir():
            for f in sorted(abs_p.rglob("*")):
                if f.is_file() and not any(part.startswith(".") for part in f.relative_to(root).parts):
                    files.append((f, str(f.relative_to(root))))

    if not files:
        return jsonify({"error": "No files found in selection"}), 400

    # Create archive in .backup/ of target folder
    backup_dir = _backup_dir_for(folder)
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%S")

    # Allow custom backup name from the user
    custom_name = data.get("custom_name", "").strip()
    if custom_name:
        # Sanitise: keep only safe chars, ensure it ends with .tar.gz
        safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', custom_name)
        if not safe_name.endswith(".tar.gz"):
            safe_name += ".tar.gz"
        archive_name = safe_name
    else:
        archive_name = f"backup_{timestamp}.tar.gz"
    archive_path = backup_dir / archive_name

    # Count by type
    counts: dict[str, int] = {}
    total_bytes = 0
    for f, _ in files:
        ftype = _classify(f)
        counts[ftype] = counts.get(ftype, 0) + 1
        total_bytes += f.stat().st_size

    manifest = {
        "format_version": 2,
        "created_at": now.isoformat(),
        "trigger": label,
        "target_folder": target_folder,
        "decrypt_enc": decrypt_enc,
        "encrypt_archive": encrypt_archive,
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
                    # Decrypt .enc files inline into the archive
                    try:
                        from .content_crypto import decrypt_file_to_memory
                        plain_bytes, meta = decrypt_file_to_memory(file_path, enc_key)
                        # Use original filename from envelope if available
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

        # Optionally encrypt the entire archive
        final_path = archive_path
        final_name = archive_name
        if encrypt_archive and enc_key:
            final_path = _encrypt_archive(archive_path, enc_key)
            final_name = final_path.name  # e.g. backup_XXX.tar.gz.enc

        logger.info(
            "Backup created: %s/%s (%d files, %d bytes)",
            target_folder, final_name, len(files), final_path.stat().st_size,
        )

        return jsonify({
            "success": True,
            "filename": final_name,
            "backup_folder": str(backup_dir.relative_to(root)),
            "full_path": str(final_path.relative_to(root)),
            "size_bytes": final_path.stat().st_size,
            "encrypted": encrypt_archive,
            "manifest": manifest,
        })

    except Exception as e:
        logger.exception("Failed to create backup")
        if archive_path.exists():
            archive_path.unlink()
        return jsonify({"error": f"Export failed: {e}"}), 500


# ── List backups for a folder ──────────────────────────────────────


@backup_bp.route("/backup/list")
def api_list():  # type: ignore[no-untyped-def]
    """List backups in a folder's .backup/ directory.

    Query params:
        path:            target folder (relative to project root)
        check_release:   if "true", cross-ref release sidecars with GitHub
    """
    rel_path = request.args.get("path", "").strip()
    check_release = request.args.get("check_release", "").lower() == "true"
    root = _project_root()

    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    folder = _resolve_folder(rel_path)
    if folder is None:
        return jsonify({"backups": []})

    backup_dir = folder / ".backup"
    if not backup_dir.is_dir():
        return jsonify({"backups": []})

    # Optionally fetch remote release assets for orphan detection
    remote_assets: set[str] | None = None
    if check_release:
        from .content_release import list_release_assets
        remote = list_release_assets(root)
        if remote.get("available"):
            remote_assets = {a["name"] for a in remote["assets"]}

    all_backups: list[dict] = []
    # Include both .tar.gz and .tar.gz.enc (encrypted archives)
    # Support both backup_* and custom-named archives
    all_archives: set[Path] = set()
    for pattern in ("backup_*.tar.gz", "backup_*.tar.gz.enc", "*.tar.gz", "*.tar.gz.enc"):
        all_archives.update(backup_dir.glob(pattern))
    # Filter out metadata files
    archives = sorted(
        [a for a in all_archives if not a.name.endswith(".release.json")],
        key=lambda a: a.name,
        reverse=True,
    )

    # Check git tracking in batch (single git command)
    import subprocess
    git_tracked: set[str] = set()
    try:
        result = subprocess.run(
            ["git", "ls-files", str(backup_dir)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                git_tracked.add(Path(line).name)
    except Exception:
        pass

    for a in archives:
        is_encrypted = a.name.endswith(".enc")
        entry: dict = {
            "filename": a.name,
            "folder": rel_path,
            "full_path": str(a.relative_to(root)),
            "size_bytes": a.stat().st_size,
            "encrypted": is_encrypted,
            "git_tracked": a.name in git_tracked,
        }
        if not is_encrypted:
            manifest = _read_manifest(a)
            if manifest:
                entry["manifest"] = manifest

        # Check for release metadata (.release.json)
        release_meta_path = a.parent / f"{a.name}.release.json"
        if release_meta_path.exists():
            try:
                release_meta = json.loads(release_meta_path.read_text())
                # Check live upload status if file_id is known
                file_id = release_meta.get("file_id", "")
                if file_id:
                    try:
                        from .content_release import _release_upload_status
                        live_status = _release_upload_status.get(file_id, {})
                        if live_status:
                            release_meta["status"] = live_status.get("status", release_meta.get("status"))
                            if live_status.get("status") == "done":
                                release_meta["status"] = "done"
                                release_meta_path.write_text(json.dumps(release_meta, indent=2))
                        elif release_meta.get("status") == "uploading":
                            # No active thread → stale upload
                            release_meta["status"] = "stale"
                    except ImportError:
                        if release_meta.get("status") == "uploading":
                            release_meta["status"] = "stale"
                entry["release"] = release_meta

                # Orphan detection: skip only genuinely active uploads
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

    return jsonify({"backups": all_backups})


# ── Preview contents of a backup archive ───────────────────────────


@backup_bp.route("/backup/preview")
def api_preview():  # type: ignore[no-untyped-def]
    """Preview the file tree inside a backup archive (for selective restore).

    Query params:
        path:  relative path to the .tar.gz
    """
    backup_path = request.args.get("path", "").strip()
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

    # If encrypted, need to decrypt first to preview
    is_encrypted = file_path.name.endswith(".enc")
    tar_path = file_path
    tmp_dec = None

    if is_encrypted:
        enc_key = _get_enc_key()
        if not enc_key:
            return jsonify({"error": "CONTENT_VAULT_ENC_KEY not set — cannot preview encrypted backup"}), 400
        try:
            tmp_dec = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
            tmp_dec.close()
            tar_path = _decrypt_archive(file_path, enc_key)
        except Exception as e:
            return jsonify({"error": f"Failed to decrypt archive: {e}"}), 500

    manifest = _read_manifest(tar_path)
    files: list[dict] = []

    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile() or member.name == "backup_manifest.json":
                    continue
                ftype = _classify(Path(member.name))
                files.append({
                    "name": Path(member.name).name,
                    "path": member.name,
                    "type": ftype,
                    "size": member.size,
                })
    except Exception as e:
        return jsonify({"error": f"Failed to read archive: {e}"}), 500
    finally:
        # Clean up temp decrypted file if we created one
        if is_encrypted and tmp_dec and Path(tmp_dec.name).exists():
            try:
                Path(tmp_dec.name).unlink()
            except OSError:
                pass

    return jsonify({
        "backup_path": backup_path,
        "encrypted": is_encrypted,
        "manifest": manifest,
        "files": files,
        "total": len(files),
    })


# ── Download ────────────────────────────────────────────────────────


@backup_bp.route("/backup/download/<path:filepath>")
def api_download(filepath: str):  # type: ignore[no-untyped-def]
    """Download a backup archive by its relative path."""
    root = _project_root()
    file_path = (root / filepath).resolve()

    # Security
    try:
        file_path.relative_to(root)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not file_path.exists() or not (file_path.name.endswith(".tar.gz") or file_path.name.endswith(".tar.gz.enc")):
        return jsonify({"error": "File not found"}), 404

    return send_file(
        file_path,
        mimetype="application/gzip",
        as_attachment=True,
        download_name=file_path.name,
    )


# ── Upload ──────────────────────────────────────────────────────────


@backup_bp.route("/backup/upload", methods=["POST"])
def api_upload():  # type: ignore[no-untyped-def]
    """Upload a backup archive into a folder's .backup/.

    Form fields:
        file:           the .tar.gz or .tar.gz.enc file
        target_folder:  folder to store the backup in (default: "docs")
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    target_folder = request.form.get("target_folder", "docs")

    if not file.filename or not file.filename.endswith((".tar.gz", ".gz", ".tar.gz.enc", ".enc")):
        return jsonify({"error": "File must be a .tar.gz or .tar.gz.enc archive"}), 400

    folder = _resolve_folder(target_folder)
    if folder is None:
        return jsonify({"error": f"Folder not found: {target_folder}"}), 404

    root = _project_root()
    backup_dir = _backup_dir_for(folder)

    # Generate safe name
    if _safe_backup_name(file.filename):
        dest_name = file.filename
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        is_enc = file.filename.endswith(".enc")
        dest_name = f"backup_{ts}.tar.gz{'.enc' if is_enc else ''}"

    dest = backup_dir / dest_name
    file.save(str(dest))

    # Try to read manifest (only works for unencrypted archives)
    manifest = None
    is_encrypted = dest.name.endswith(".enc")
    if not is_encrypted:
        manifest = _read_manifest(dest)
        if not manifest:
            dest.unlink()
            return jsonify({"error": "Invalid archive: no backup_manifest.json found"}), 400

    return jsonify({
        "success": True,
        "filename": dest_name,
        "folder": target_folder,
        "full_path": str(dest.relative_to(root)),
        "size_bytes": dest.stat().st_size,
        "encrypted": is_encrypted,
        "manifest": manifest,
    })
