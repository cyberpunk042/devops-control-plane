"""
Secrets domain — public API.

Re-exports every public symbol from the secrets submodules so consumers
can import from ``src.core.services.secrets`` directly.
"""

# ── ops.py — helpers, gh status, key generators ────────────────────
from src.core.services.secrets.ops import (  # noqa: F401
    # Shared helpers
    classify_key,
    fresh_env,
    gh_repo_flag,
    env_path_for,
    read_env_values,
    # gh CLI status
    gh_status,
    gh_auto_detect,
    # Key generators
    generate_key,
)

# ── env_ops.py — GitHub environment management ─────────────────────
from src.core.services.secrets.env_ops import (  # noqa: F401
    list_environments,
    create_environment,
    cleanup_environment,
    seed_environments,
)

# ── gh_ops.py — GitHub secrets/variables CRUD ──────────────────────
from src.core.services.secrets.gh_ops import (  # noqa: F401
    list_gh_secrets,
    set_secret,
    remove_secret,
    push_secrets,
)
