"""
Admin API — Backup & Restore core module.

Blueprint: backup_bp
Prefix: /api

This module defines the blueprint, re-exports helpers from
``src.core.services.backup_ops``, and hosts the folder-tree endpoints.

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

import logging
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    jsonify,
    request,
)

from src.core.services import backup_ops

backup_bp = Blueprint("backup", __name__)
logger = logging.getLogger(__name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"]).resolve()


# ── Re-exported helpers (used by sub-route modules) ────────────────
# Sub-modules import these from here to avoid importing backup_ops directly.
# This keeps the transition incremental and avoids circular imports.

# Constants
_SKIP_DIRS = backup_ops.SKIP_DIRS
MEDIA_EXT = backup_ops.MEDIA_EXT
DOC_EXT = backup_ops.DOC_EXT

# Helpers
_classify = backup_ops.classify_file
_backup_dir_for = backup_ops.backup_dir_for
_safe_backup_name = backup_ops.safe_backup_name
_read_manifest = backup_ops.read_manifest


def _resolve_folder(rel_path: str) -> Path | None:
    """Resolve a relative folder — wraps backup_ops with _project_root()."""
    return backup_ops.resolve_folder(_project_root(), rel_path)


def _get_enc_key() -> str:
    """Read CONTENT_VAULT_ENC_KEY from .env."""
    return backup_ops.get_enc_key(_project_root())


def _encrypt_archive(archive_path: Path, passphrase: str) -> Path:
    """Encrypt a .tar.gz archive using COVAULT format."""
    return backup_ops.encrypt_archive(archive_path, passphrase)


def _decrypt_archive(enc_path: Path, passphrase: str) -> Path:
    """Decrypt a .tar.gz.enc archive to a temp file."""
    return backup_ops.decrypt_archive(enc_path, passphrase)


# ── Folder tree endpoint ───────────────────────────────────────────


@backup_bp.route("/backup/folder-tree")
def api_folder_tree():  # type: ignore[no-untyped-def]
    """Return the full recursive directory tree for folder selection."""
    max_depth = min(int(request.args.get("depth", "6")), 10)
    tree = backup_ops.folder_tree(_project_root(), max_depth=max_depth)
    return jsonify({"tree": tree})


@backup_bp.route("/backup/folders")
def api_folders():  # type: ignore[no-untyped-def]
    """Flat list of all top-level scannable folders."""
    folders = backup_ops.list_folders(_project_root())
    return jsonify({"folders": folders})


# ── Import sub-modules to register their routes on backup_bp ──────
# These imports MUST come after backup_bp is defined (circular import guard).

from . import routes_backup_ops       # noqa: E402, F401 — registers routes
from . import routes_backup_tree      # noqa: E402, F401 — registers routes
from . import routes_backup_archive   # noqa: E402, F401 — registers routes
from . import routes_backup_restore   # noqa: E402, F401 — registers routes
