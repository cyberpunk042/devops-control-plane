# ── Backward-compatibility shim ─────────────────────────────────────
# Real implementation lives in src/core/services/secrets/env_ops.py
# This file exists so old ``from src.core.services.secrets_env_ops import X``
# paths keep working.  New code should import from the secrets package.

from src.core.services.secrets.env_ops import (  # noqa: F401
    list_environments,
    create_environment,
    cleanup_environment,
    seed_environments,
)
