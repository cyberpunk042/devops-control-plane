"""
Content Vault — backward-compatible re-export shim.

The canonical content crypto logic now lives in
``src.core.services.content_crypto``. This module re-exports every
public symbol so existing imports (routes, backups) continue to work.
"""

# ── Re-export everything from the canonical location ─────────────────
from src.core.services.content_crypto import (  # noqa: F401
    # Functions
    encrypt_file,
    decrypt_file,
    decrypt_file_to_memory,
    read_metadata,
    classify_file,
    is_covault_file,
    detect_content_folders,
    list_folder_contents,
    list_folder_contents_recursive,
    format_size,
    # Constants
    MAGIC,
    MAGIC_LEN,
    KDF_ITERATIONS,
    KDF_ITERATIONS_EXPORT,
    SALT_LEN,
    IV_LEN,
    TAG_LEN,
    SHA256_LEN,
    LEN_FIELD,
    IMAGE_EXTS,
    VIDEO_EXTS,
    AUDIO_EXTS,
    DOC_EXTS,
    CODE_EXTS,
    SCRIPT_EXTS,
    CONFIG_EXTS,
    DATA_EXTS,
    ARCHIVE_EXTS,
    DEFAULT_CONTENT_DIRS,
    # Internal helpers (used by some routes)
    _guess_mime,
    _derive_key,
    _parse_envelope,
    _scan_folder,
    _CONFIG_FILENAMES,
    _EXT_MIME,
)
