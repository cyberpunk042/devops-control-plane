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
import re
from typing import Any

from src.core.services.tool_install.data.remediation_handlers import (
    VALID_STRATEGIES,
    VALID_CATEGORIES,
)

logger = logging.getLogger(__name__)

# ── Canonical recipe fields ─────────────────────────────────────

# Valid recipe types
RECIPE_TYPES = {"tool", "data_pack", "config"}

# Valid install method keys (PM names + _default)
VALID_METHOD_KEYS = {
    "_default", "apt", "dnf", "yum", "apk", "pacman",
    "zypper", "brew", "snap", "pip", "pipx", "npm", "cargo", "source",
}

# Valid distro family keys (for packages map)
VALID_FAMILIES = {
    "debian", "rhel", "alpine", "arch", "suse", "macos",
}

# ── Source method sub-schema ────────────────────────────────────

VALID_BUILD_SYSTEMS = {
    "autotools", "cmake", "cargo", "meson", "go", "make",
}

_SOURCE_SPEC_FIELDS = {
    "build_system",         # str: REQUIRED — one of VALID_BUILD_SYSTEMS
    "git_repo",             # str: source acquisition — mutex with tarball_url
    "tarball_url",          # str: source acquisition — mutex with git_repo
    "default_version",      # str: REQUIRED when tarball_url contains {version}
    "branch",               # str: git branch/tag — only with git_repo
    "depth",                # int: git clone depth — only with git_repo
    "requires_toolchain",   # list[str]: REQUIRED — binaries needed for build
    "configure_args",       # list[str]: args for ./configure (autotools)
    "cmake_args",           # list[str]: args for cmake
    "cargo_args",           # list[str]: args for cargo build
    "install_prefix",       # str: --prefix value, default /usr/local
    "build_size",           # str: "small" | "medium" | "large"
    "configure_timeout",    # int: configure step timeout in seconds
    "install_needs_sudo",   # bool: whether make install needs sudo
}

# ── Handler option schema ───────────────────────────────────────

# Fields valid on ALL options regardless of strategy
_OPTION_COMMON_REQUIRED = {"id", "label", "strategy", "icon"}

_OPTION_COMMON_OPTIONAL = {
    "description",      # str: what this option does
    "recommended",      # bool: is this the recommended choice?
    "risk",             # str: "low" | "medium" | "high"
    "requires_binary",  # str: binary that must be on PATH for ready state
    "requires",         # dict[str→bool]: system capability conditions that must all pass
    "group",            # str: "primary" | "extended" — UI grouping
    "arch_exclude",     # list[str]: architectures where this is impossible
    "pre_packages",     # dict[family→list[str]]: OS packages to install before strategy
}

# Per-strategy: (required_fields, optional_fields)
_STRATEGY_FIELDS: dict[str, tuple[set[str], set[str]]] = {
    "install_dep": (
        {"dep"},
        {"env_override"},
    ),
    "install_dep_then_switch": (
        {"dep", "switch_to"},
        set(),
    ),
    "install_packages": (
        set(),  # Must have packages OR dynamic_packages — checked separately
        {"packages", "dynamic_packages", "env_override"},
    ),
    "switch_method": (
        {"method"},
        set(),
    ),
    "retry_with_modifier": (
        {"modifier"},
        {"requires_binary"},  # Already in common optional, listed for clarity
    ),
    "add_repo": (
        {"repo_commands"},
        set(),
    ),
    "upgrade_dep": (
        {"dep"},
        set(),
    ),
    "env_fix": (
        {"fix_commands"},
        set(),
    ),
    "manual": (
        {"instructions"},
        set(),
    ),
    "cleanup_retry": (
        {"cleanup_commands"},
        set(),
    ),
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
    "on_failure",        # list[dict]: reactive remediation handlers (optional)
    "install_via",       # dict: method key → pattern family (e.g. {"_default": "composer_global"})
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


# ── Source spec validator ───────────────────────────────────────

def _validate_source_spec(
    source_spec: dict,
    prefix: str,
) -> list[str]:
    """Validate a source method spec dict.

    Checks:
      - build_system is present and valid
      - Exactly one of git_repo / tarball_url is present
      - requires_toolchain is present and is a list
      - default_version present when tarball_url contains {version}
      - branch/depth only allowed with git_repo
      - configure_args / cmake_args / cargo_args are lists when present
      - No unknown fields

    Args:
        source_spec: The source method dict from install.source.
        prefix: Error message prefix (e.g. "install['source']").

    Returns:
        List of error strings.
    """
    errors: list[str] = []

    # Unknown fields
    for key in source_spec:
        if key not in _SOURCE_SPEC_FIELDS:
            errors.append(f"{prefix}: unknown field '{key}'")

    # build_system — required
    bs = source_spec.get("build_system")
    if not bs:
        errors.append(f"{prefix}: missing required field 'build_system'")
    elif bs not in VALID_BUILD_SYSTEMS:
        errors.append(
            f"{prefix}: invalid build_system '{bs}' — "
            f"must be one of {sorted(VALID_BUILD_SYSTEMS)}"
        )

    # Source acquisition — exactly one of git_repo or tarball_url
    has_git = "git_repo" in source_spec
    has_tarball = "tarball_url" in source_spec
    if not has_git and not has_tarball:
        errors.append(
            f"{prefix}: must have 'git_repo' or 'tarball_url'"
        )
    if has_git and has_tarball:
        errors.append(
            f"{prefix}: cannot have both 'git_repo' and 'tarball_url'"
        )

    # requires_toolchain — required, must be list
    tc = source_spec.get("requires_toolchain")
    if tc is None:
        errors.append(f"{prefix}: missing required field 'requires_toolchain'")
    elif not isinstance(tc, list):
        errors.append(f"{prefix}: 'requires_toolchain' must be a list")

    # default_version — required when tarball_url contains {version}
    if has_tarball:
        url = source_spec.get("tarball_url", "")
        if "{version}" in url:
            if "default_version" not in source_spec:
                errors.append(
                    f"{prefix}: tarball_url contains '{{version}}' but "
                    f"no 'default_version' is specified"
                )

    # branch/depth — only valid with git_repo
    if has_tarball:
        if "branch" in source_spec:
            errors.append(
                f"{prefix}: 'branch' is only valid with 'git_repo', "
                f"not 'tarball_url'"
            )
        if "depth" in source_spec:
            errors.append(
                f"{prefix}: 'depth' is only valid with 'git_repo', "
                f"not 'tarball_url'"
            )

    # List fields — must be lists when present
    for field in ("configure_args", "cmake_args", "cargo_args"):
        val = source_spec.get(field)
        if val is not None and not isinstance(val, list):
            errors.append(f"{prefix}: '{field}' must be a list")

    # build_size — must be valid
    bs_size = source_spec.get("build_size")
    if bs_size is not None and bs_size not in ("small", "medium", "large"):
        errors.append(
            f"{prefix}: invalid build_size '{bs_size}' — "
            f"must be 'small', 'medium', or 'large'"
        )

    # depth — must be int
    depth = source_spec.get("depth")
    if depth is not None and not isinstance(depth, int):
        errors.append(f"{prefix}: 'depth' must be an int")

    # configure_timeout — must be int
    ct = source_spec.get("configure_timeout")
    if ct is not None and not isinstance(ct, int):
        errors.append(f"{prefix}: 'configure_timeout' must be an int")

    return errors


# ── Option validator ────────────────────────────────────────────

def _validate_option(
    opt: dict,
    prefix: str,
    seen_ids: set[str],
) -> list[str]:
    """Validate a single remediation option dict.

    Checks:
      - Common required fields present
      - Strategy is valid
      - Per-strategy required fields present
      - No unknown fields (common + strategy-specific)
      - Type checks on strategy-specific fields
      - Duplicate option ID detection

    Args:
        opt: The option dict.
        prefix: Error message prefix (e.g. "on_failure[0].options[1]").
        seen_ids: Set of already-seen option IDs (mutated in place).

    Returns:
        List of error strings.
    """
    errors: list[str] = []

    if not isinstance(opt, dict):
        errors.append(f"{prefix} must be a dict")
        return errors

    # Common required fields
    for f in _OPTION_COMMON_REQUIRED:
        if f not in opt:
            errors.append(f"{prefix}: missing '{f}'")

    # Strategy validation
    strat = opt.get("strategy", "")
    if strat and strat not in VALID_STRATEGIES:
        errors.append(f"{prefix}: unknown strategy '{strat}'")
        # Can't validate strategy-specific fields if strategy is unknown
        return errors

    # Duplicate ID
    oid = opt.get("id", "")
    if oid in seen_ids:
        errors.append(f"{prefix}: duplicate option id '{oid}'")
    seen_ids.add(oid)

    if not strat:
        return errors  # Can't validate further without strategy

    # Per-strategy required + optional fields
    strat_req, strat_opt = _STRATEGY_FIELDS.get(strat, (set(), set()))

    # Check required strategy-specific fields
    for f in strat_req:
        if f not in opt:
            errors.append(
                f"{prefix}: strategy '{strat}' requires field '{f}'"
            )

    # install_packages special case: must have packages OR dynamic_packages
    if strat == "install_packages":
        if "packages" not in opt and not opt.get("dynamic_packages"):
            errors.append(
                f"{prefix}: strategy 'install_packages' requires "
                f"'packages' or 'dynamic_packages: True'"
            )

    # Unknown field check — allow common + strategy-specific
    all_valid = (
        _OPTION_COMMON_REQUIRED
        | _OPTION_COMMON_OPTIONAL
        | strat_req
        | strat_opt
    )
    for f in opt:
        if f not in all_valid:
            errors.append(
                f"{prefix}: unknown field '{f}' "
                f"for strategy '{strat}'"
            )

    # ── Type checks on strategy-specific fields ──

    # dep must be a non-empty string
    if "dep" in opt:
        dep = opt["dep"]
        if not isinstance(dep, str) or not dep:
            errors.append(f"{prefix}: 'dep' must be a non-empty string")

    # method must be a non-empty string
    if "method" in opt:
        m = opt["method"]
        if not isinstance(m, str) or not m:
            errors.append(f"{prefix}: 'method' must be a non-empty string")

    # modifier must be a dict
    if "modifier" in opt:
        if not isinstance(opt["modifier"], dict):
            errors.append(f"{prefix}: 'modifier' must be a dict")

    # packages must be family-keyed dict of lists
    if "packages" in opt:
        pkgs = opt["packages"]
        if not isinstance(pkgs, dict):
            errors.append(f"{prefix}: 'packages' must be a dict")
        else:
            for fam in pkgs:
                if fam not in VALID_FAMILIES:
                    errors.append(
                        f"{prefix}: unknown family '{fam}' in 'packages'"
                    )
                if not isinstance(pkgs[fam], list):
                    errors.append(
                        f"{prefix}: packages['{fam}'] must be a list"
                    )

    # pre_packages must be family-keyed dict of lists (same as packages)
    if "pre_packages" in opt:
        pre = opt["pre_packages"]
        if not isinstance(pre, dict):
            errors.append(f"{prefix}: 'pre_packages' must be a dict")
        else:
            for fam in pre:
                if fam not in VALID_FAMILIES:
                    errors.append(
                        f"{prefix}: unknown family '{fam}' in 'pre_packages'"
                    )
                if not isinstance(pre[fam], list):
                    errors.append(
                        f"{prefix}: pre_packages['{fam}'] must be a list"
                    )

    # fix_commands / repo_commands / cleanup_commands must be list of lists
    for cmd_field in ("fix_commands", "repo_commands", "cleanup_commands"):
        if cmd_field in opt:
            cmds = opt[cmd_field]
            if not isinstance(cmds, list):
                errors.append(f"{prefix}: '{cmd_field}' must be a list")
            else:
                for ci, c in enumerate(cmds):
                    if not isinstance(c, list):
                        errors.append(
                            f"{prefix}: {cmd_field}[{ci}] must be a list"
                        )

    # instructions must be a string
    if "instructions" in opt:
        if not isinstance(opt["instructions"], str):
            errors.append(f"{prefix}: 'instructions' must be a string")

    # env_override must be a dict
    if "env_override" in opt:
        if not isinstance(opt["env_override"], dict):
            errors.append(f"{prefix}: 'env_override' must be a dict")

    # arch_exclude must be a list
    if "arch_exclude" in opt:
        if not isinstance(opt["arch_exclude"], list):
            errors.append(f"{prefix}: 'arch_exclude' must be a list")

    # requires_binary must be a string
    if "requires_binary" in opt:
        rb = opt["requires_binary"]
        if not isinstance(rb, str) or not rb:
            errors.append(
                f"{prefix}: 'requires_binary' must be a non-empty string"
            )

    # requires must be dict of known conditions → bool
    _VALID_REQUIRES_CONDITIONS = {
        "has_systemd",      # capabilities.has_systemd == True
        "has_openrc",       # init system is OpenRC (Alpine, Gentoo)
        "is_linux",         # system == "Linux"
        "not_container",    # not container.in_container
        "writable_rootfs",  # not container.read_only_rootfs
        "not_root",         # not capabilities.is_root
        "has_sudo",         # capabilities.has_sudo == True
    }
    if "requires" in opt:
        req = opt["requires"]
        if not isinstance(req, dict):
            errors.append(f"{prefix}: 'requires' must be a dict")
        else:
            for cond, val in req.items():
                if cond not in _VALID_REQUIRES_CONDITIONS:
                    errors.append(
                        f"{prefix}: unknown requires condition "
                        f"'{cond}' — valid: "
                        f"{sorted(_VALID_REQUIRES_CONDITIONS)}"
                    )
                if not isinstance(val, bool):
                    errors.append(
                        f"{prefix}: requires['{cond}'] must be bool"
                    )

    # risk must be valid
    if "risk" in opt:
        r = opt["risk"]
        if r not in ("low", "medium", "high", "critical"):
            errors.append(
                f"{prefix}: invalid risk '{r}' — "
                f"must be 'low', 'medium', 'high', or 'critical'"
            )

    # group must be valid
    if "group" in opt:
        g = opt["group"]
        if g not in ("primary", "extended"):
            errors.append(
                f"{prefix}: invalid group '{g}' — "
                f"must be 'primary' or 'extended'"
            )

    return errors


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

        # Install commands: lists for normal methods, dict for source
        for method, cmd in install.items():
            if method == "source":
                # Source method can be a dict (structured) or a list (legacy)
                if isinstance(cmd, dict):
                    errors.extend(
                        _validate_source_spec(cmd, f"install['source']")
                    )
                elif not isinstance(cmd, list):
                    errors.append(
                        f"install['source'] must be a list or dict, "
                        f"got {type(cmd).__name__}"
                    )
            else:
                if not isinstance(cmd, list):
                    errors.append(
                        f"install['{method}'] must be a list, "
                        f"got {type(cmd).__name__}"
                    )

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

        # ── on_failure validation ──
        on_failure = recipe.get("on_failure")
        if on_failure is not None:
            if not isinstance(on_failure, list):
                errors.append("on_failure must be a list")
            else:
                errors.extend(_validate_handler_list(on_failure, "on_failure"))

    return errors


def _validate_handler_list(
    handlers: list,
    prefix: str,
) -> list[str]:
    """Validate a list of handler dicts.

    Shared between on_failure (recipe layer) and standalone handler
    registry validation.

    Args:
        handlers: List of handler dicts.
        prefix: Error prefix (e.g. "on_failure" or "METHOD_FAMILY_HANDLERS['pip']").

    Returns:
        List of error strings.
    """
    errors: list[str] = []
    _handler_req = {"pattern", "failure_id", "category", "label", "options"}
    _handler_opt = {"description", "exit_code", "detect_fn", "example_stderr", "example_exit_code"}

    for hi, handler in enumerate(handlers):
        hp = f"{prefix}[{hi}]"
        if not isinstance(handler, dict):
            errors.append(f"{hp} must be a dict")
            continue

        for f in _handler_req:
            if f not in handler:
                errors.append(f"{hp}: missing required field '{f}'")

        for f in handler:
            if f not in _handler_req | _handler_opt:
                errors.append(f"{hp}: unknown field '{f}'")

        # Validate pattern is a compilable regex
        pat = handler.get("pattern", "")
        if pat:
            try:
                re.compile(pat)
            except re.error as exc:
                errors.append(f"{hp}: invalid regex '{pat}': {exc}")

        # Validate category
        cat = handler.get("category", "")
        if cat and cat not in VALID_CATEGORIES:
            errors.append(f"{hp}: unknown category '{cat}'")

        # Validate options
        opts = handler.get("options")
        if opts is not None:
            if not isinstance(opts, list):
                errors.append(f"{hp}.options must be a list")
            else:
                seen_ids: set[str] = set()
                for oi, opt in enumerate(opts):
                    oprefix = f"{hp}.options[{oi}]"
                    errors.extend(
                        _validate_option(opt, oprefix, seen_ids)
                    )

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
