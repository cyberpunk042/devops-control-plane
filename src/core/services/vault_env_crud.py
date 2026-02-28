# ── Backward-compatibility shim ─────────────────────────────────────
# Real implementation lives in src/core/services/vault/env_crud.py
# This file exists so old ``from src.core.services.vault_env_crud import X``
# paths keep working.  New code should import from the vault package.

from src.core.services.vault.env_crud import (  # noqa: F401
    add_keys,
    update_key,
    delete_key,
    get_raw_value,
    move_key,
    rename_section,
    toggle_local_only,
    set_meta,
)
