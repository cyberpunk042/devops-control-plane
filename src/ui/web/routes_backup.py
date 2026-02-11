"""
Admin API — Backup & Restore core module.

Blueprint: backup_bp
Prefix: /api

This module defines the blueprint, shared helpers, and core folder endpoints.
Route handlers are split across sub-modules for maintainability:

    routes_backup.py          — (this file) blueprint, helpers, folder-tree, folders
    routes_backup_ops.py      — upload-release, encrypt, decrypt, delete-release, rename, mark-special
    routes_backup_tree.py     — expandable file tree filtered by type
    routes_backup_archive.py  — export, list, preview, download, upload
    routes_backup_restore.py  — restore, import, wipe, delete

Routes (this file):
    /api/backup/folders      — list all scannable project folders
    /api/backup/folder-tree  — recursive directory tree for selection
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    jsonify,
    request,
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
    import re
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
    import tarfile
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


# ── Import sub-modules to register their routes on backup_bp ──────
# These imports MUST come after backup_bp is defined (circular import guard).

from . import routes_backup_ops       # noqa: E402, F401 — registers routes
from . import routes_backup_tree      # noqa: E402, F401 — registers routes
from . import routes_backup_archive   # noqa: E402, F401 — registers routes
from . import routes_backup_restore   # noqa: E402, F401 — registers routes
