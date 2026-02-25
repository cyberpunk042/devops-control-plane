"""
L0 Data — Recipe schema definition and validator.

Defines the canonical recipe shape. Every recipe in TOOL_RECIPES must
conform to this schema. The validator runs at import time to catch
typos, missing fields, and type mismatches before any resolver logic.

Recipe types:
  - tool:      installable software (has install methods)
  - data_pack: downloadable data (has steps[], no method selection)
  - config:    config file generation (has config_templates[])
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Canonical recipe fields ─────────────────────────────────────

# Valid recipe types
RECIPE_TYPES = {"tool", "data_pack", "config"}

# Valid install method keys (PM names + _default)
VALID_METHOD_KEYS = {
    "_default", "apt", "dnf", "yum", "apk", "pacman",
    "zypper", "brew", "snap", "pip", "npm", "cargo", "source",
}

# Valid distro family keys (for packages map)
VALID_FAMILIES = {
    "debian", "rhel", "alpine", "arch", "suse", "macos",
}

# ── Field definitions ───────────────────────────────────────────

# Fields valid for ALL recipe types
_COMMON_FIELDS = {
    "type",            # str: "tool" | "data_pack" | "config"
    "label",           # str: human-readable name (REQUIRED)
    "description",     # str: optional longer description
    "category",        # str: UI grouping (e.g. "security", "k8s")
    "risk",            # str: "low" | "medium" | "high" | "critical"
    "cli",             # str: binary name to check on PATH (default: recipe key)
    "verify",          # list[str]: command to verify installation
    "update",          # dict: method-keyed update commands
    "rollback",        # dict: method-keyed rollback commands
    "remove",          # dict: method-keyed removal commands
    "restart_required", # str: "shell" | "reboot" | "service"
    "version_constraint", # dict: version constraint spec
    "minimum_version",    # str: minimum acceptable version
}

# Fields valid for tool recipes
_TOOL_FIELDS = _COMMON_FIELDS | {
    "install",           # dict: method-keyed install commands (REQUIRED for tool)
    "needs_sudo",        # dict: method-keyed sudo requirements
    "requires",          # dict: binary + package dependencies
    "prefer",            # list[str]: preferred method order
    "post_env",          # str: env setup for subsequent steps
    "post_install",      # list[dict]: post-install steps
    "repo_setup",        # dict: PM-keyed repo setup steps
    "choices",           # list[dict]: interactive choice definitions
    "inputs",            # list[dict]: user input definitions
    "install_variants",  # dict: variant-keyed install commands
    "arch_map",          # dict: architecture name mappings
    "cli_verify_args",   # list[str]: alternative verify args
}

# Fields valid for data_pack recipes
_DATA_PACK_FIELDS = _COMMON_FIELDS | {
    "steps",             # list[dict]: pre-built execution steps (REQUIRED for data_pack)
    "requires",          # dict: binary dependencies
    "inputs",            # list[dict]: user inputs (e.g. model URL, DB version)
    "install",           # dict: some data packs have installable components
    "needs_sudo",        # dict: sudo for install components
}

# Fields valid for config recipes
_CONFIG_FIELDS = _COMMON_FIELDS | {
    "config_templates",  # list[dict]: config file templates (REQUIRED for config)
    "requires",          # dict: dependencies
    "post_install",      # list[dict]: post-config steps
    "install",           # dict: config recipes may also install services
    "needs_sudo",        # dict: sudo requirements
    "inputs",            # list[dict]: user-configurable template variables
}

# Map type → valid fields
_FIELDS_BY_TYPE = {
    "tool": _TOOL_FIELDS,
    "data_pack": _DATA_PACK_FIELDS,
    "config": _CONFIG_FIELDS,
}

# Map type → required fields
_REQUIRED_BY_TYPE = {
    "tool": {"label", "install"},
    "data_pack": {"label", "steps"},
    "config": {"label", "config_templates"},
}


# ── Validator ───────────────────────────────────────────────────

def validate_recipe(tool_id: str, recipe: dict) -> list[str]:
    """Validate a single recipe against the schema.

    Returns a list of error strings. Empty list = valid.
    """
    errors: list[str] = []

    # Type detection
    rtype = recipe.get("type")
    if not rtype:
        # Infer type from keys
        if recipe.get("install"):
            rtype = "tool"
        elif recipe.get("steps"):
            rtype = "data_pack"
        elif recipe.get("config_templates"):
            rtype = "config"
        else:
            errors.append(f"Cannot infer type: no 'install', 'steps', or 'config_templates' key")
            return errors

    if rtype not in RECIPE_TYPES:
        errors.append(f"Invalid type '{rtype}' — must be one of {RECIPE_TYPES}")
        return errors

    # Required fields
    required = _REQUIRED_BY_TYPE[rtype]
    for field in required:
        if field not in recipe:
            errors.append(f"Missing required field '{field}' for type '{rtype}'")

    # Unknown fields
    valid_fields = _FIELDS_BY_TYPE[rtype]
    for key in recipe:
        if key not in valid_fields:
            errors.append(f"Unknown field '{key}' for type '{rtype}'")

    # ── Tool-specific validations ──

    if rtype == "tool":
        install = recipe.get("install", {})
        needs_sudo = recipe.get("needs_sudo", {})

        # Method keys must be valid
        for method in install:
            if method not in VALID_METHOD_KEYS:
                errors.append(f"Unknown install method '{method}'")

        # Every method should have a needs_sudo entry
        for method in install:
            if method not in needs_sudo and "_default" not in needs_sudo:
                errors.append(
                    f"Install method '{method}' has no needs_sudo entry "
                    f"(and no '_default' fallback)"
                )

        # Install commands must be lists
        for method, cmd in install.items():
            if not isinstance(cmd, list):
                errors.append(f"install['{method}'] must be a list, got {type(cmd).__name__}")

        # Verify should be a list
        verify = recipe.get("verify")
        if verify is not None and not isinstance(verify, list):
            errors.append(f"'verify' must be a list, got {type(verify).__name__}")

        # Requires validation
        requires = recipe.get("requires", {})
        if requires:
            # binaries must be a list
            binaries = requires.get("binaries", [])
            if not isinstance(binaries, list):
                errors.append(f"requires.binaries must be a list")

            # packages must be family-keyed
            packages = requires.get("packages", {})
            if packages:
                for family in packages:
                    if family not in VALID_FAMILIES:
                        errors.append(f"Unknown family '{family}' in requires.packages")
                    if not isinstance(packages[family], list):
                        errors.append(f"requires.packages['{family}'] must be a list")

        # prefer must reference actual install methods
        prefer = recipe.get("prefer", [])
        for p in prefer:
            if p not in install:
                errors.append(f"prefer references '{p}' but no install['{p}'] exists")

    return errors


def validate_all_recipes(recipes: dict[str, dict]) -> dict[str, list[str]]:
    """Validate all recipes in the registry.

    Returns:
        Dict mapping tool_id → list of errors. Only tools with errors are included.
    """
    all_errors: dict[str, list[str]] = {}
    for tool_id, recipe in recipes.items():
        errs = validate_recipe(tool_id, recipe)
        if errs:
            all_errors[tool_id] = errs
    return all_errors
