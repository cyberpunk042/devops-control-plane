"""
Scripts engine — script lifecycle management.

Manages the discovery, registration, and execution of project scripts.
Scripts can be user-owned (root) or shipped templates, merged with
root overriding templates when both exist.

This mirrors the artifacts engine pattern but for operational scripts
rather than distributable artifacts.
"""

from .config import load_scripts_config, save_scripts_config  # noqa: F401
from .executor import execute_script  # noqa: F401
from .models import ScriptConfig, ScriptMeta, ScriptParameter  # noqa: F401
from .output_router import inject_output_env, resolve_output_target  # noqa: F401
from .registry import (  # noqa: F401
    discover_scripts,
    get_all_scripts,
    get_script,
    get_scripts_by_category,
    get_scripts_by_tag,
    get_scripts_summary,
    refresh_registry,
)
