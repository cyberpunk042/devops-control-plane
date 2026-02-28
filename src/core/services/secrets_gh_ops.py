# ── Backward-compatibility shim ─────────────────────────────────────
# Real implementation lives in src/core/services/secrets/gh_ops.py
# This file exists so old ``from src.core.services.secrets_gh_ops import X``
# paths keep working.  New code should import from the secrets package.

from src.core.services.secrets.gh_ops import (  # noqa: F401
    list_gh_secrets,
    set_secret,
    remove_secret,
    push_secrets,
)
