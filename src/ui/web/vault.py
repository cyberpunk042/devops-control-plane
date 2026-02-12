"""
Secrets Vault — backward-compatible re-export shim.

The canonical vault logic now lives in ``src.core.services.vault``.
This module re-exports every public symbol so existing imports
(routes, tests, server.py) continue to work without modification.

Module-level mutable globals (_auto_lock_minutes, _failed_attempts, etc.)
are proxied via __getattr__ / __setattr__ so that direct attribute
access on this module reads/writes the canonical module's state.
"""

import src.core.services.vault as _canonical

# ── Re-export all callable / constant symbols ────────────────────────
from src.core.services.vault import (  # noqa: F401
    # Constants
    KDF_ITERATIONS,
    SALT_BYTES,
    IV_BYTES,
    KEY_BYTES,
    TAG_BYTES,
    VAULT_SUFFIX,
    EXPORT_FORMAT,
    EXPORT_KDF_ITERATIONS,
    # Session / state
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
    # Project root
    set_project_root,
    get_project_root,
    # Internal (used by routes_vault.py via vault._vault_path_for)
    _vault_path_for,
    _pp_key,
    _derive_key,
    _secure_delete,
    _check_rate_limit,
    _record_failed_attempt,
    _reset_rate_limit,
    _start_auto_lock_timer,
    _cancel_auto_lock_timer,
    # Re-exports from vault_io (callers use vault.xxx)
    export_vault_file,
    import_vault_file,
    detect_secret_files,
    list_env_keys,
    list_env_sections,
    SECRET_FILE_PATTERNS,
    _parse_env_lines,
)

# ── Mutable module globals — proxy to canonical module ───────────────
# Python's `from X import y` copies the binding for scalar types
# (int, float, None). To let `vault._auto_lock_minutes = 15`
# propagate to the canonical module, we intercept attribute access.

_PROXIED_GLOBALS = frozenset({
    "_session_passphrases",
    "_session_passphrase",   # legacy alias used in one test
    "_auto_lock_timer",
    "_auto_lock_minutes",
    "_lock",
    "_failed_attempts",
    "_last_failed_time",
    "_project_root_ref",
})


def __getattr__(name: str):  # type: ignore[misc]
    if name in _PROXIED_GLOBALS:
        return getattr(_canonical, name, None)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Module-level __setattr__ requires Python 3.7+; we override via
# sys.modules trick: install a custom module wrapper.
import sys as _sys
import types as _types


class _VaultProxy(_types.ModuleType):
    """Thin module proxy that forwards mutable global writes to canonical."""

    def __setattr__(self, name: str, value):  # type: ignore[override]
        if name in _PROXIED_GLOBALS:
            setattr(_canonical, name, value)
        else:
            super().__setattr__(name, value)

    def __getattr__(self, name: str):
        if name in _PROXIED_GLOBALS:
            return getattr(_canonical, name, None)
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Replace ourselves in sys.modules with the proxy
_self = _sys.modules[__name__]
_proxy = _VaultProxy(__name__, __doc__)
_proxy.__dict__.update({k: v for k, v in _self.__dict__.items() if not k.startswith("_VaultProxy")})
_proxy.__file__ = __file__
_proxy.__package__ = __package__
_proxy.__path__ = getattr(_self, "__path__", [])
_proxy.__spec__ = getattr(_self, "__spec__", None)
_sys.modules[__name__] = _proxy
