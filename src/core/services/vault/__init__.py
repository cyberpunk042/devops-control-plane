"""
Vault domain — public API.

Re-exports every public symbol from the vault submodules so consumers
can import from ``src.core.services.vault`` directly.
"""

# ── core.py — crypto, lock/unlock, session, auto-lock ──────────────
from src.core.services.vault.core import (  # noqa: F401
    # Constants
    KDF_ITERATIONS,
    SALT_BYTES,
    IV_BYTES,
    KEY_BYTES,
    TAG_BYTES,
    VAULT_SUFFIX,
    EXPORT_FORMAT,
    EXPORT_KDF_ITERATIONS,
    # Session state
    get_passphrase,
    has_any_passphrase,
    touch_activity,
    # Core operations
    vault_status,
    lock_vault,
    unlock_vault,
    auto_lock,
    register_passphrase,
    set_auto_lock_minutes,
    # Project root delegates
    set_project_root,
    get_project_root,
    # Internal — used by io.py and env_ops.py
    _vault_path_for,
    _derive_key,
)

# ── io.py — export/import, detection, .env parsing ─────────────────
from src.core.services.vault.io import (  # noqa: F401
    export_vault_file,
    import_vault_file,
    detect_secret_files,
    list_env_keys,
    list_env_sections,
    _parse_env_lines,
)

# ── env_ops.py — .env file operations ──────────────────────────────
from src.core.services.vault.env_ops import (  # noqa: F401
    ENV_TEMPLATE_SECTIONS,
    read_env_values,
    read_active_env,
    activate_env,
    list_keys_enriched,
    get_templates,
    create_env,
    classify_key,
    # Re-exported from env_crud via env_ops
    add_keys,
    update_key,
    delete_key,
    get_raw_value,
    move_key,
    rename_section,
    toggle_local_only,
    set_meta,
)
