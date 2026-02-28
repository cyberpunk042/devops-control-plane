# ── Backward-compatibility shim ─────────────────────────────────────
# Real implementation lives in src/core/services/vault/env_ops.py
# This file exists so old ``from src.core.services.vault_env_ops import X``
# paths keep working.  New code should import from the vault package.

from src.core.services.vault.env_ops import (  # noqa: F401
    # Constants & helpers
    ENV_TEMPLATE_SECTIONS,
    classify_key,
    read_env_values,
    _find_section_end,
    _write_env,
    _ensure_templates,
    # Environment activation
    read_active_env,
    activate_env,
    # Key listing
    list_keys_enriched,
    # Templates
    get_templates,
    # Create
    create_env,
    # Re-exports from env_crud (via env_ops)
    add_keys,
    update_key,
    delete_key,
    get_raw_value,
    move_key,
    rename_section,
    toggle_local_only,
    set_meta,
)
