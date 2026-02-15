"""
Backup & Restore operations — backward-compat re-export hub.

Shared helpers live in ``backup_common``.
Feature code lives in ``backup_archive``, ``backup_restore``,
and ``backup_extras``.
"""

from __future__ import annotations

# ── Common helpers & constants ──
from src.core.services.backup_common import (  # noqa: F401
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
from src.core.services.backup_archive import (  # noqa: F401
    folder_tree,
    list_folders,
    create_backup,
    list_backups,
    preview_backup,
    delete_backup,
    rename_backup,
)

# ── Restore / import / wipe / in-place encrypt ──
from src.core.services.backup_restore import (  # noqa: F401
    restore_backup,
    import_backup,
    wipe_folder,
    encrypt_backup_inplace,
    decrypt_backup_inplace,
)

# ── Git tracking + file tree ──
from src.core.services.backup_extras import (  # noqa: F401
    mark_special,
    file_tree_scan,
    _cleanup_release_sidecar,
)
