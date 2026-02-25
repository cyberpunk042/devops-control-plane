"""
L4 Execution — ``__init__.py`` re-exports all execution functions.

These functions WRITE to the system: subprocess calls, file writes,
config modifications, plan state persistence.
"""

from src.core.services.tool_install.execution.backup import (  # noqa: F401
    _backup_before_step,
)
from src.core.services.tool_install.execution.build_helpers import (  # noqa: F401
    _autotools_plan,
    _cargo_git_plan,
    _check_build_resources,
    _cmake_plan,
    _execute_build_step,
    _execute_source_step,
    _substitute_build_vars,
    _substitute_install_vars,
    _validate_toolchain,
)
from src.core.services.tool_install.execution.config import (  # noqa: F401
    _render_template,
    _shell_config_line,
)
from src.core.services.tool_install.execution.download import (  # noqa: F401
    _resolve_github_release_url,
    _verify_checksum,
)
from src.core.services.tool_install.execution.plan_state import (  # noqa: F401
    _plan_state_dir,
    archive_plan,
    cancel_plan,
    list_pending_plans,
    load_plan_state,
    resume_plan,
    save_plan_state,
)
from src.core.services.tool_install.execution.step_executors import (  # noqa: F401
    _execute_cleanup_step,
    _execute_command_step,
    _execute_config_step,
    _execute_download_step,
    _execute_github_release_step,
    _execute_install_step,
    _execute_notification_step,
    _execute_package_step,
    _execute_repo_step,
    _execute_rollback,
    _execute_service_step,
    _execute_shell_config_step,
    _execute_verify_step,
)
from src.core.services.tool_install.execution.subprocess_runner import (  # noqa: F401
    _run_subprocess,
)
from src.core.services.tool_install.execution.tool_management import (  # noqa: F401
    remove_tool,
    update_tool,
)
