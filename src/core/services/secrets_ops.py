# ── Backward-compatibility shim ─────────────────────────────────────
# Real implementation lives in src/core/services/secrets/
# This file exists so old ``from src.core.services.secrets_ops import X``
# and ``from src.core.services import secrets_ops`` paths keep working.
# New code should import from the secrets package.

from src.core.services.secrets.ops import (  # noqa: F401
    classify_key,
    fresh_env,
    gh_repo_flag,
    env_path_for,
    read_env_values,
    gh_status,
    gh_auto_detect,
    generate_key,
)

# Re-exports from sub-modules (was at bottom of original secrets_ops.py)
from src.core.services.secrets.env_ops import (  # noqa: F401
    list_environments,
    create_environment,
    cleanup_environment,
    seed_environments,
)

from src.core.services.secrets.gh_ops import (  # noqa: F401
    list_gh_secrets,
    set_secret,
    remove_secret,
    push_secrets,
)
