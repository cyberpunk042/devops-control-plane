"""
Content — encryption, file ops, listing, optimization, release management.

Sub-modules::

    crypto.py           — COVAULT envelope encryption/decryption, file classification
    crypto_ops.py       — high-level encrypt/decrypt with audit integration
    file_ops.py         — CRUD operations on content files (upload, delete, rename, move)
    file_advanced.py    — advanced file ops (restore from release, sidecar checks)
    listing.py          — folder detection, file listing, size formatting
    optimize.py         — image/text optimization, storage classification
    optimize_video.py   — video/audio optimization with ffmpeg
    release.py          — GitHub release upload/cleanup, sidecar management
    release_sync.py     — restore large files from releases, release inventory

Public re-exports below keep ``from src.core.services.content import X`` working.
"""

from __future__ import annotations

# ── Crypto ──
from .crypto import (  # noqa: F401
    encrypt_file,
    decrypt_file,
    decrypt_file_to_memory,
    read_metadata,
    classify_file,
    is_covault_file,
    _guess_mime,
    _EXT_MIME,
    DEFAULT_CONTENT_DIRS,
    detect_content_folders,
    list_folder_contents,
    list_folder_contents_recursive,
    format_size,
    encrypt_content_file,
    decrypt_content_file,
)

# ── File Ops ──
from .file_ops import (  # noqa: F401
    resolve_safe_path,
    create_content_folder,
    delete_content_file,
    upload_content_file,
    setup_enc_key,
    save_content_file,
    rename_content_file,
    move_content_file,
    list_all_project_folders,
    check_release_sidecar,
    save_encrypted_content,
)

# ── Listing ──
# (already re-exported through crypto.py)

# ── Optimize ──
from .optimize import (  # noqa: F401
    optimize_media,
    optimize_image,
    optimize_text,
    classify_storage,
    should_optimize_image,
    get_optimization_status,
    cancel_active_optimization,
)

# ── Release ──
from .release import (  # noqa: F401
    upload_to_release_bg,
    cleanup_release_sidecar,
    remove_orphaned_sidecar,
    get_release_status,
    get_all_release_statuses,
    cancel_release_upload,
    delete_release_asset,
    restore_large_files,
    list_release_assets,
    release_inventory,
)
