"""
Backup & Restore — archive creation, restore, release integration.

Sub-modules::

    common.py    — shared helpers (classify, enc key, archive encrypt/decrypt)
    archive.py   — folder scanning, archive CRUD, upload
    restore.py   — restore, import, wipe, in-place encrypt/decrypt
    extras.py    — git tracking, file tree, release upload/delete

Public re-exports below keep ``from src.core.services.backup import X`` working.
"""

from __future__ import annotations

# ── Common helpers & constants ──
from .common import (  # noqa: F401
    classify_file,
    backup_dir_for,
    safe_backup_name,
    resolve_folder,
    read_manifest,
    get_enc_key,
    encrypt_archive,
    decrypt_archive,
    SKIP_DIRS,
    MEDIA_EXT,
    DOC_EXT,
)

# ── Folder scanning + archive CRUD ──
from .archive import (  # noqa: F401
    folder_tree,
    list_folders,
    create_backup,
    list_backups,
    preview_backup,
    delete_backup,
    rename_backup,
    sanitize_backup_name,
    upload_backup,
)

# ── Restore / import / wipe / in-place encrypt ──
from .restore import (  # noqa: F401
    restore_backup,
    import_backup,
    wipe_folder,
    encrypt_backup_inplace,
    decrypt_backup_inplace,
)

# ── Git tracking + file tree + release ops ──
from .extras import (  # noqa: F401
    mark_special,
    file_tree_scan,
    upload_backup_to_release,
    delete_backup_release,
    _cleanup_release_sidecar,
)
