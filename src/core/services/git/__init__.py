"""
Git domain — Git operations, authentication, and GitHub CLI integration.

Public API re-exports for backward compatibility.
Import from here or from individual submodules.
"""

# ── Git core operations ──────────────────────────────────────────────
from src.core.services.git.ops import (  # noqa: F401
    run_git,
    run_gh,
    repo_slug,
    git_status,
    git_log,
    git_commit,
    git_pull,
    git_push,
)

# ── Git authentication (SSH / HTTPS) ────────────────────────────────
from src.core.services.git.auth import (  # noqa: F401
    detect_remote_type,
    get_remote_url,
    find_ssh_key,
    key_has_passphrase,
    check_auth,
    add_ssh_key,
    add_https_credentials,
    git_env,
    is_auth_ok,
    is_auth_tested,
)

# ── GitHub API queries ───────────────────────────────────────────────
from src.core.services.git.gh_api import (  # noqa: F401
    gh_status,
    gh_pulls,
    gh_actions_runs,
    gh_actions_dispatch,
    gh_actions_workflows,
    gh_user,
    gh_repo_info,
)

# ── GitHub authentication ────────────────────────────────────────────
from src.core.services.git.gh_auth import (  # noqa: F401
    gh_auth_logout,
    gh_auth_login,
    gh_auth_token,
    gh_auth_device_start,
    gh_auth_device_poll,
)

# ── GitHub repo & remote management ──────────────────────────────────
from src.core.services.git.gh_repo import (  # noqa: F401
    gh_repo_create,
    gh_repo_set_visibility,
    gh_repo_set_default_branch,
    git_remote_remove,
    git_remotes,
    git_remote_add,
    git_remote_rename,
    git_remote_set_url,
)
