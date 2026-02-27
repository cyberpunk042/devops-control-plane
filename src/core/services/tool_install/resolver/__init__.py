"""
L2 Resolver — ``__init__.py`` re-exports all resolver functions.

These functions transform L0 data + L1 domain logic into
concrete install plans. They bridge recipes → executable steps.
"""

from src.core.services.tool_install.resolver.choice_resolution import (  # noqa: F401
    _apply_choices,
    _apply_inputs,
    _input_condition_met,
    _resolve_choice_option,
    _resolve_single_choice,
    resolve_choices,
)
from src.core.services.tool_install.resolver.dependency_collection import (  # noqa: F401
    _can_reach,
    _collect_deps,
)
from src.core.services.tool_install.resolver.method_selection import (  # noqa: F401
    _build_pkg_install_cmd,
    _extract_packages_from_cmd,
    _is_batchable,
    _pick_install_method,
    _pick_method_command,
    _wrap_with_env,
    get_update_map,
)
from src.core.services.tool_install.resolver.plan_resolution import (  # noqa: F401
    resolve_install_plan,
    resolve_install_plan_with_choices,
)
