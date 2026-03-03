"""
BACKWARD COMPATIBILITY SHIM — imports have moved to ``src.core.services.git``.

This file exists only so existing ``from src.core.services.git_ops import X``
statements continue to work.  New code should import from
``src.core.services.git`` or its submodules directly.
"""

from src.core.services.git.ops import (  # noqa: F401
    run_git,
    run_gh,
    repo_slug,
    git_status,
    git_log,
    git_commit,
    git_pull,
    git_push,
    git_diff,
    git_diff_file,
    git_stash,
    git_stash_pop,
    git_stash_list,
    git_merge_status,
    git_merge_abort,
    git_checkout_file,
)

from src.core.services.git.gh_api import (  # noqa: F401
    gh_status,
    gh_pulls,
    gh_actions_runs,
    gh_actions_dispatch,
    gh_actions_workflows,
    gh_user,
    gh_repo_info,
)

from src.core.services.git.gh_auth import (  # noqa: F401
    gh_auth_logout,
    gh_auth_login,
    gh_auth_token,
    gh_auth_device_start,
    gh_auth_device_poll,
    detect_platform_capabilities,
    gh_auth_device_start_http,
    gh_auth_device_poll_http,
)

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
