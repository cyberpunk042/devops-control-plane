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
        handle_fix_compat_auto,
        handle_guide_incompatible_syntax,
        handle_modernize_type_hints,
        handle_remove_future_annotations,
        handle_scan_breaking_changes,
        handle_scan_incompatible_features,
        handle_update_ci_matrix,
    )
    from .config_editor import (
        handle_edit_cargo_toml_rust_version,
        handle_edit_composer_php_version,
        handle_edit_csproj_target,
        handle_edit_gemfile_ruby_version,
        handle_edit_go_mod_directive,
        handle_edit_mix_elixir_version,
        handle_edit_package_json_engines,
        handle_edit_pom_java_version,
        handle_edit_pyproject_requires_python,
        handle_edit_setup_cfg_python_requires,
        handle_edit_setup_py_python_requires,
        handle_generate_module_toml,
    )
    from .dep_checker import (
        handle_check_dep_compat_crates,
        handle_check_dep_compat_hex,
        handle_check_dep_compat_npm,
        handle_check_dep_compat_packagist,
        handle_check_dep_compat_pypi,
        handle_check_dep_compat_rubygems,
        handle_discover_missing_deps,
        handle_update_deps_crates,
        handle_update_deps_hex,
        handle_update_deps_interactive,
        handle_update_deps_npm,
        handle_update_deps_packagist,
        handle_update_deps_rubygems,
    )
    from .executor import (
        handle_generate_smart_tests,
        handle_rescan_module,
        handle_scaffold_module_tests,
        handle_scaffold_parent_tests,
    )
    from .test_env import handle_run_isolated_tests, handle_setup_test_env
    from .subprocess_ops import (
        handle_run_bundle_exec_rspec,
        handle_run_bundle_update,
        handle_run_cargo_check,
        handle_run_cargo_test,
        handle_run_composer_test,
        handle_run_composer_update,
        handle_run_dotnet_restore,
        handle_run_dotnet_test,
        handle_run_go_mod_tidy,
        handle_run_pip_install,
        handle_run_go_test,
        handle_run_mix_deps_get,
        handle_run_mix_test,
        handle_run_mvn_test,
        handle_run_npm_install,
        handle_run_npm_test,
        handle_run_pytest,
    )

    return {
        # ── Python config ────────────────────────────────────────
        "edit_pyproject_requires_python": handle_edit_pyproject_requires_python,
        "edit_setup_py_python_requires": handle_edit_setup_py_python_requires,
        "edit_setup_cfg_python_requires": handle_edit_setup_cfg_python_requires,
        # ── Node.js config ───────────────────────────────────────
        "edit_package_json_engines": handle_edit_package_json_engines,
        # ── Go config ────────────────────────────────────────────
        "edit_go_mod_directive": handle_edit_go_mod_directive,
        # ── Rust config ──────────────────────────────────────────
        "edit_cargo_toml_rust_version": handle_edit_cargo_toml_rust_version,
        # ── Ruby config ──────────────────────────────────────────
        "edit_gemfile_ruby_version": handle_edit_gemfile_ruby_version,
        # ── Java config ──────────────────────────────────────────
        "edit_pom_java_version": handle_edit_pom_java_version,
        # ── C# / .NET config ────────────────────────────────────
        "edit_csproj_target": handle_edit_csproj_target,
        # ── PHP config ───────────────────────────────────────────
        "edit_composer_php_version": handle_edit_composer_php_version,
        # ── Elixir config ────────────────────────────────────────
        "edit_mix_elixir_version": handle_edit_mix_elixir_version,
        # ── Python dep checking ──────────────────────────────────
        "check_dep_compat_pypi": handle_check_dep_compat_pypi,
        "discover_missing_deps": handle_discover_missing_deps,
        "update_deps_interactive": handle_update_deps_interactive,
        # ── Node.js dep checking ─────────────────────────────────
        "check_dep_compat_npm": handle_check_dep_compat_npm,
        "update_deps_npm": handle_update_deps_npm,
        # ── Rust dep checking ────────────────────────────────────
        "check_dep_compat_crates": handle_check_dep_compat_crates,
        "update_deps_crates": handle_update_deps_crates,
        # ── Ruby dep checking ────────────────────────────────────
        "check_dep_compat_rubygems": handle_check_dep_compat_rubygems,
        "update_deps_rubygems": handle_update_deps_rubygems,
        # ── PHP dep checking ─────────────────────────────────────
        "check_dep_compat_packagist": handle_check_dep_compat_packagist,
        "update_deps_packagist": handle_update_deps_packagist,
        # ── Elixir dep checking ──────────────────────────────────
        "check_dep_compat_hex": handle_check_dep_compat_hex,
        "update_deps_hex": handle_update_deps_hex,
        # ── Code scanning & modification (Python-specific) ───────
        "scan_breaking_changes": handle_scan_breaking_changes,
        "scan_incompatible_features": handle_scan_incompatible_features,
        "fix_compat_auto": handle_fix_compat_auto,
        "remove_future_annotations": handle_remove_future_annotations,
        "add_future_annotations": handle_add_future_annotations,
        "modernize_type_hints": handle_modernize_type_hints,
        "guide_incompatible_syntax": handle_guide_incompatible_syntax,
        # ── CI (language-agnostic) ───────────────────────────────
        "update_ci_matrix": handle_update_ci_matrix,
        # ── Subprocess operations (package managers) ─────────────
        "run_go_mod_tidy": handle_run_go_mod_tidy,
        "run_bundle_update": handle_run_bundle_update,
        "run_composer_update": handle_run_composer_update,
        "run_dotnet_restore": handle_run_dotnet_restore,
        "run_mix_deps_get": handle_run_mix_deps_get,
        "run_cargo_check": handle_run_cargo_check,
        "run_npm_install": handle_run_npm_install,
        "run_pip_install": handle_run_pip_install,
        # ── Config generation ────────────────────────────────────
        "generate_module_toml": handle_generate_module_toml,
        # ── Test suite runners ───────────────────────────────────
        "run_pytest": handle_run_pytest,
        "run_npm_test": handle_run_npm_test,
        "run_go_test": handle_run_go_test,
        "run_cargo_test": handle_run_cargo_test,
        "run_bundle_exec_rspec": handle_run_bundle_exec_rspec,
        "run_mvn_test": handle_run_mvn_test,
        "run_dotnet_test": handle_run_dotnet_test,
        "run_composer_test": handle_run_composer_test,
        "run_mix_test": handle_run_mix_test,
        # ── Verification (language-agnostic) ─────────────────────
        "rescan_module": handle_rescan_module,
        # ── Test scaffolding & isolation ──────────────────────────
        "scaffold_module_tests": handle_scaffold_module_tests,
        "scaffold_parent_tests": handle_scaffold_parent_tests,
        "generate_smart_tests": handle_generate_smart_tests,
        "setup_test_env": handle_setup_test_env,
        "run_isolated_tests": handle_run_isolated_tests,
    }
