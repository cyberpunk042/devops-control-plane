"""
Secrets Vault I/O — backward-compatible re-export shim.

The canonical vault_io logic now lives in ``src.core.services.vault_io``.
This module re-exports every public symbol so existing imports
continue to work without modification.
"""

# ── Re-export everything from the canonical location ─────────────────
from src.core.services.vault_io import (  # noqa: F401
    export_vault_file,
    import_vault_file,
    detect_secret_files,
    list_env_keys,
    list_env_sections,
    SECRET_FILE_PATTERNS,
    _parse_env_lines,
    _parse_meta_tags,
)
