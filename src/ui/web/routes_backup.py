"""
Admin API — Backup & Restore endpoints.

Blueprint: backup_bp
Prefix: /api
Routes:
    /api/backup/folders             — list all scannable project folders
    /api/backup/folder-tree         — recursive directory tree for selection
    /api/backup/tree                — get expandable tree filtered by type
    /api/backup/export              — create a backup archive from selected items
    /api/backup/list                — list backups in .backup/ of a target folder
    /api/backup/preview             — list files inside a backup archive
    /api/backup/download/<fn>       — download a backup archive
    /api/backup/restore             — restore (overwrite) from a .backup/ archive
    /api/backup/wipe                — factory-reset a folder (with optional backup)
    /api/backup/delete              — delete a .backup/ archive
    /api/backup/upload              — upload an archive into a folder's .backup/
    /api/backup/import              — import (additive) from an archive
    /api/backup/upload-release      — upload archive to GitHub Release
    /api/backup/encrypt             — encrypt an existing .tar.gz backup
    /api/backup/decrypt             — decrypt an existing .tar.gz.enc backup
    /api/backup/delete-release      — delete a backup's GitHub Release artifact
    /api/backup/rename              — rename a backup file
    /api/backup/mark-special        — git add -f a backup (≤25 MB)
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    jsonify,
    request,
    send_file,
)

backup_bp = Blueprint("backup", __name__)
logger = logging.getLogger(__name__)

# Folders to skip when scanning project root
_SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".mypy_cache", ".ruff_cache", ".pytest_cache", ".tox",
    "dist", "build", ".egg-info", ".idea", ".vscode",
    ".gemini", ".agent", "state",
})


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"]).resolve()


# ── File type classification ───────────────────────────────────────

MEDIA_EXT = frozenset({
    ".mp4", ".webm", ".mov", ".avi", ".mkv",
    ".mp3", ".wav", ".flac", ".ogg", ".aac",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".tiff",
})

DOC_EXT = frozenset({
    ".md", ".txt", ".pdf", ".json", ".yaml", ".yml", ".xml",
    ".csv", ".docx", ".rst", ".html", ".htm", ".toml", ".ini",
})


def _classify(path: Path) -> str:
    """Classify a file by type using the shared content vault classifier."""
    from .content_crypto import classify_file
    return classify_file(path)


def _backup_dir_for(folder: Path) -> Path:
    """Get / create a .backup/ directory inside the given folder."""
    d = folder / ".backup"
    d.mkdir(exist_ok=True)
    return d


def _safe_backup_name(name: str) -> bool:
    """Validate backup filename pattern."""
    return bool(re.match(r"^backup_\d{8}T\d{6}\.tar\.gz(\.enc)?$", name))


def _resolve_folder(rel_path: str) -> Path | None:
    """Resolve a relative folder safely within project root."""
    root = _project_root()
    target = (root / rel_path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    if not target.is_dir():
        return None
    return target


def _read_manifest(archive_path: Path) -> dict | None:
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


def _get_enc_key() -> str:
    """Read CONTENT_VAULT_ENC_KEY from .env."""
    try:
        from .helpers import fresh_env
        env = fresh_env(_project_root())
        return env.get("CONTENT_VAULT_ENC_KEY", "").strip()
    except Exception:
        return ""


def _encrypt_archive(archive_path: Path, passphrase: str) -> Path:
    """Encrypt a .tar.gz archive using COVAULT format. Returns path to .tar.gz.enc."""
    from .content_crypto import encrypt_file
    enc_path = encrypt_file(archive_path, passphrase)
    # Remove the unencrypted archive
    archive_path.unlink()
    return enc_path


def _decrypt_archive(enc_path: Path, passphrase: str) -> Path:
    """Decrypt a .tar.gz.enc archive to a temp file. Returns path to the decrypted .tar.gz.
    Caller is responsible for cleaning up the returned temp file."""
    from .content_crypto import decrypt_file
    # Write decrypted file to temp directory so we don't pollute .backup/
    tmp_path = Path(tempfile.mktemp(suffix=".tar.gz"))
    dec_path = decrypt_file(enc_path, passphrase, output_path=tmp_path)
    return dec_path


# ── Folder tree endpoint ───────────────────────────────────────────


@backup_bp.route("/backup/folder-tree")
def api_folder_tree():  # type: ignore[no-untyped-def]
    """Return the full recursive directory tree for folder selection.

    Excludes dot-dirs (.git, .backup, .venv, etc.) and known tool dirs.
    Returns nested children so the UI can render a collapsible tree.
    """
    root = _project_root()
    max_depth = min(int(request.args.get("depth", "6")), 10)

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
            if entry.name.startswith(".") or entry.name in _SKIP_DIRS:
                continue

            rel = str(entry.relative_to(root))
            # Count direct files only (fast)
            direct_files = sum(1 for f in entry.iterdir() if f.is_file() and not f.name.startswith("."))
            children = _scan_dirs(entry, depth + 1)
            # Has .backup/?
            has_backup = (entry / ".backup").is_dir()

            items.append({
                "name": entry.name,
                "path": rel,
                "files": direct_files,
                "has_backup": has_backup,
                "children": children,
            })
        return items

    tree = _scan_dirs(root, 0)
    return jsonify({"tree": tree})


# Also keep the flat endpoint for simple usage
@backup_bp.route("/backup/folders")
def api_folders():  # type: ignore[no-untyped-def]
    """Flat list of all top-level scannable folders."""
    root = _project_root()
    folders: list[dict] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith(".") or entry.name in _SKIP_DIRS:
            continue
        folders.append({"name": entry.name, "path": entry.name})
    return jsonify({"folders": folders})


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


# ── Tree endpoint ──────────────────────────────────────────────────


@backup_bp.route("/backup/tree")
def api_tree():  # type: ignore[no-untyped-def]
    """Return an expandable file tree filtered by type.

    Query params:
        path:       root folder to scan (relative to project root)
        types:      comma-separated types to include (docs,media,encrypted,other)
                    defaults to all
        depth:      max recursion depth (default 5)
        gitignore:  if 'true', exclude files matched by .gitignore
    """
    rel_path = request.args.get("path", "").strip()
    type_filter = request.args.get("types", "document,code,script,config,data,image,video,audio,archive,encrypted,other")
    max_depth = min(int(request.args.get("depth", "5")), 10)
    allowed_types = set(type_filter.split(","))
    respect_gitignore = request.args.get("gitignore", "").lower() == "true"

    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    folder = _resolve_folder(rel_path)
    if folder is None:
        return jsonify({"error": f"Folder not found: {rel_path}"}), 404

    root = _project_root()

    # Build set of allowed files if respecting gitignore
    gitignore_allowed: set[str] | None = None
    if respect_gitignore:
        try:
            import subprocess
            result = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                gitignore_allowed = set(result.stdout.strip().splitlines())
        except Exception:
            pass  # Fall back to no filtering if git not available

    def _scan(directory: Path, depth: int) -> list[dict]:
        if depth > max_depth:
            return []

        items: list[dict] = []
        try:
            entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return []

        for entry in entries:
            # Skip hidden dirs, .backup, and tool directories
            if entry.name.startswith(".") or entry.name in _SKIP_DIRS:
                continue

            if entry.is_dir():
                children = _scan(entry, depth + 1)
                if children:  # only include dirs that have matching files
                    items.append({
                        "name": entry.name,
                        "path": str(entry.resolve().relative_to(root)),
                        "type": "directory",
                        "children": children,
                        "count": sum(
                            c.get("count", 1) if c["type"] == "directory" else 1
                            for c in children
                        ),
                    })
            elif entry.is_file():
                # Skip files excluded by .gitignore
                if gitignore_allowed is not None:
                    rel_file = str(entry.resolve().relative_to(root))
                    if rel_file not in gitignore_allowed:
                        continue
                ftype = _classify(entry)
                if ftype in allowed_types:
                    items.append({
                        "name": entry.name,
                        "path": str(entry.resolve().relative_to(root)),
                        "type": ftype,
                        "size": entry.stat().st_size,
                    })

        return items

    tree = _scan(folder, 0)

    # Count totals
    def _count(nodes: list[dict]) -> dict:
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

    return jsonify({
        "root": rel_path,
        "tree": tree,
        "counts": counts,
    })


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
        path:  target folder (relative to project root)
    """
    rel_path = request.args.get("path", "").strip()
    root = _project_root()

    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    folder = _resolve_folder(rel_path)
    if folder is None:
        return jsonify({"backups": []})

    backup_dir = folder / ".backup"
    if not backup_dir.is_dir():
        return jsonify({"backups": []})

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
                                # Update the stored metadata
                                release_meta_path.write_text(json.dumps(release_meta, indent=2))
                    except ImportError:
                        pass
                entry["release"] = release_meta
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

    file_path.unlink()
    logger.info("Deleted backup: %s", backup_path)
    return jsonify({"success": True, "deleted": backup_path})
