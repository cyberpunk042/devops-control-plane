"""
Automation handlers for module upgrade/downgrade steps.

Each handler takes (ctx: UpgradeContext, mode: str) and returns a dict.
Mode is "preview" (show what would change) or "execute" (do it).

Registry maps automation_id → handler function.
All imports are lazy to prevent circular dependencies.
"""

from __future__ import annotations


def get_handler_registry() -> dict:
    """Return the automation handler registry.

    Lazy imports keep startup fast and prevent circular chains.
    """
    from .code_scanner import (
        handle_add_future_annotations,
        handle_modernize_type_hints,
        handle_remove_future_annotations,
        handle_scan_breaking_changes,
        handle_scan_incompatible_features,
        handle_update_ci_matrix,
    )
    from .config_editor import (
        handle_edit_pyproject_requires_python,
        handle_edit_setup_cfg_python_requires,
        handle_edit_setup_py_python_requires,
    )
    from .dep_checker import (
        handle_check_dep_compat_pypi,
        handle_update_deps_interactive,
    )
    from .executor import handle_rescan_module

    return {
        # Config editors
        "edit_pyproject_requires_python": handle_edit_pyproject_requires_python,
        "edit_setup_py_python_requires": handle_edit_setup_py_python_requires,
        "edit_setup_cfg_python_requires": handle_edit_setup_cfg_python_requires,
        # Dependency checking
        "check_dep_compat_pypi": handle_check_dep_compat_pypi,
        "update_deps_interactive": handle_update_deps_interactive,
        # Code scanning & modification
        "scan_breaking_changes": handle_scan_breaking_changes,
        "scan_incompatible_features": handle_scan_incompatible_features,
        "remove_future_annotations": handle_remove_future_annotations,
        "add_future_annotations": handle_add_future_annotations,
        "modernize_type_hints": handle_modernize_type_hints,
        # CI
        "update_ci_matrix": handle_update_ci_matrix,
        # Verification
        "rescan_module": handle_rescan_module,
    }
