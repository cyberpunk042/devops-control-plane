# ── Backward-compatibility shim ─────────────────────────────────────
# Real implementation lives in src/core/services/vault/io.py
# This file exists so old ``from src.core.services.vault_io import X``
# paths keep working.  New code should import from the vault package.

from src.core.services.vault.io import (  # noqa: F401
    export_vault_file,
    import_vault_file,
    detect_secret_files,
    list_env_keys,
    list_env_sections,
    _parse_env_lines,
    _parse_meta_tags,
    _secret_file_patterns,
)
