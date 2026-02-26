"""
L1 Domain — Remediation planning (pure).

Builds the complete remediation response for the UI. Takes a failure
context (tool, method, stderr, exit_code, system_profile) and returns
the §6 response shape from remediation-model.md.

Flow:
  1. Calls handler_matching to collect all matching options
  2. Computes availability (ready/locked/impossible) for each option
  3. Sorts options by priority
  4. Assembles the response with failure info, chain context, fallbacks

No I/O, no subprocess. Only references to recipe data and shutil.which
for binary checks.
"""

from __future__ import annotations

import shutil
from typing import Any

from src.core.services.tool_install.data.recipes import TOOL_RECIPES
from src.core.services.tool_install.data.remediation_handlers import (
    LIB_TO_PACKAGE_MAP,
    VALID_STRATEGIES,
)
from src.core.services.tool_install.domain.handler_matching import (
    _collect_all_options,
    _sort_options,
)


# ── Always-available fallback actions ───────────────────────────

_FALLBACK_ACTIONS = [
    {"id": "retry", "label": "Retry", "icon": "🔄"},
    {"id": "skip", "label": "Skip this tool", "icon": "⏭️"},
    {"id": "cancel", "label": "Cancel", "icon": "✕"},
]


# ── Availability computation ───────────────────────────────────

# System-native PMs — tied to the distro, can't be installed elsewhere.
# If the system doesn't ship with them, they're truly impossible.
_NATIVE_PMS = frozenset({"apt", "dnf", "yum", "apk", "pacman", "zypper"})

# Installable PMs — available on most systems as an add-on.
# If not present, they're locked (installable prerequisite), not impossible.
_INSTALLABLE_PMS = frozenset({"brew", "snap"})

# All PM methods (union of native + installable)
_PM_METHODS = _NATIVE_PMS | _INSTALLABLE_PMS


def _compute_availability(
    option: dict,
    recipe: dict,
    system_profile: dict | None,
) -> tuple[str, str | None, list[str] | None, str | None]:
    """Compute availability state for a single remediation option.

    Checks whether the option can be executed immediately (ready),
    needs prerequisites installed first (locked), or can never work
    on this system (impossible).

    Version-aware gates (uses rich system profile):
      - Native PM options (apt, dnf, apk…) → impossible if PM not on system
      - Installable PMs (brew, snap) → locked if not present
      - snap locked on systemd absence (impossible — can't run snapd)
      - install_packages gated on read-only rootfs
      - architecture exclusions checked

    Args:
        option: Option dict from a handler.
        recipe: The tool's recipe dict.
        system_profile: Phase 1 ``_detect_os()`` output. May be None.

    Returns:
        Tuple of (state, lock_reason, unlock_deps, impossible_reason):
          - ``("ready", None, None, None)``
          - ``("locked", "reason", ["dep_id", ...], None)``
          - ``("impossible", None, None, "reason")``
    """
    strategy = option.get("strategy", "")
    family = _get_family(system_profile)

    # ── Architecture exclusion ─────────────────────────────────
    arch_exclude = option.get("arch_exclude", [])
    if arch_exclude and system_profile:
        arch = system_profile.get("arch", "")
        if arch in arch_exclude:
            return "impossible", None, None, "ARM architecture is not supported"

    if strategy == "install_dep":
        dep = option.get("dep", "")
        return _check_dep_availability(dep, system_profile)

    if strategy == "install_dep_then_switch":
        dep = option.get("dep", "")
        switch_to = option.get("switch_to", "")
        # Check if the dep is available; also check the target method exists
        dep_state, dep_reason, dep_deps, _ = _check_dep_availability(dep, system_profile)
        if dep_state == "impossible":
            return dep_state, None, None, dep_reason
        # Check that the switch target method exists in the recipe
        if switch_to and switch_to not in recipe.get("install", {}):
            # The dep might provide its own command (e.g. pipx install)
            # so we don't require the method to exist in the recipe
            pass
        return dep_state, dep_reason, dep_deps, None

    if strategy == "switch_method":
        target_method = option.get("method", "")
        if not target_method:
            return "impossible", None, None, "No target method specified"

        # ── Version-aware PM gate ──────────────────────────────
        if target_method in _PM_METHODS and system_profile:
            available_pms = _get_available_pms(system_profile)

            # snap: needs systemd (hard gate) + snapd (installable prereq)
            if target_method == "snap":
                has_systemd = system_profile.get(
                    "capabilities", {},
                ).get("has_systemd", True)
                if not has_systemd:
                    return "impossible", None, None, (
                        "snap requires systemd (not available)"
                    )
                if "snap" not in available_pms:
                    return "locked", "snapd not installed", ["snapd"], None

            # brew: installable anywhere (Linuxbrew) — locked if missing
            elif target_method == "brew":
                if available_pms and "brew" not in available_pms:
                    return "locked", "brew not installed", ["brew"], None

            # Native PMs: tied to the distro — impossible if missing
            elif target_method in _NATIVE_PMS:
                if available_pms and target_method not in available_pms:
                    return "impossible", None, None, (
                        f"Package manager '{target_method}' is not "
                        f"available on this system"
                    )

        install_methods = recipe.get("install", {})
        if target_method not in install_methods:
            return "impossible", None, None, (
                f"No '{target_method}' install method in recipe"
            )
        return "ready", None, None, None

    if strategy == "retry_with_modifier":
        return "ready", None, None, None

    if strategy == "install_packages":
        # ── Read-only rootfs gate ──────────────────────────────
        if system_profile:
            read_only = system_profile.get(
                "container", {},
            ).get("read_only_rootfs", False)
            if read_only:
                return "impossible", None, None, (
                    "Cannot install packages: read-only root filesystem"
                )

        dynamic = option.get("dynamic_packages", False)
        if dynamic:
            # Dynamic packages are resolved at execution time
            return "ready", None, None, None
        packages = option.get("packages", {})
        if not packages:
            return "impossible", None, None, "No packages defined"
        if family and family not in packages:
            return "impossible", None, None, (
                f"No packages defined for distro family '{family}'"
            )
        return "ready", None, None, None

    if strategy == "add_repo":
        return "ready", None, None, None

    if strategy == "upgrade_dep":
        dep = option.get("dep", "")
        return _check_dep_availability(dep, system_profile)

    if strategy == "env_fix":
        return "ready", None, None, None

    if strategy == "manual":
        return "ready", None, None, None

    if strategy == "cleanup_retry":
        return "ready", None, None, None

    # Unknown strategy
    return "ready", None, None, None


def _check_dep_availability(
    dep: str,
    system_profile: dict | None = None,
) -> tuple[str, str | None, list[str] | None, str | None]:
    """Check if a dependency (recipe ID or system package) is available.

    Resolution order:
      1. TOOL_RECIPES — full recipe, check CLI binary
      2. Dynamic resolver — known packages, lib mappings, identity
      3. shutil.which fallback — binary already on PATH

    Args:
        dep: Dependency name (tool ID, binary name, or lib short name).
        system_profile: Phase 1 ``_detect_os()`` output. Used by the
            dynamic resolver for PM-aware package resolution.

    Returns:
        Availability tuple (state, lock_reason, unlock_deps, impossible_reason).
    """
    if not dep:
        return "impossible", None, None, "No dependency specified"

    dep_recipe = TOOL_RECIPES.get(dep)

    if dep_recipe:
        # Has a recipe — use its CLI to check
        cli = dep_recipe.get("cli", dep)
        if shutil.which(cli):
            return "ready", None, None, None
        return "locked", f"{dep} not installed", [dep], None

    # Already installed on PATH?
    if shutil.which(dep):
        return "ready", None, None, None

    # ── Dynamic resolver: better info for no-recipe deps ───────
    if system_profile:
        from src.core.services.tool_install.resolver.dynamic_dep_resolver import (
            resolve_dep_install,
        )
        resolution = resolve_dep_install(dep, system_profile)
        if resolution:
            confidence = resolution.get("confidence", "medium")
            source = resolution["source"]
            if confidence == "high":
                return "locked", f"{dep} not installed ({source})", [dep], None
            else:
                return (
                    "locked",
                    f"{dep} not installed (assumed package name)",
                    [dep],
                    None,
                )

    # Fallback: assume installable via system PM
    return "locked", f"{dep} not installed (system package)", [dep], None


def _get_family(system_profile: dict | None) -> str:
    """Extract distro family from system_profile."""
    if not system_profile:
        return ""
    return system_profile.get("distro", {}).get("family", "")


def _get_available_pms(system_profile: dict | None) -> list[str]:
    """Extract available package managers from system_profile.

    Returns the ``available`` list from the ``package_manager`` section,
    plus ``"snap"`` if ``snap_available`` is True.

    Returns an empty list if no profile or no ``available`` key
    (signals the caller to skip PM availability checks).
    """
    if not system_profile:
        return []
    pm_info = system_profile.get("package_manager", {})
    available = list(pm_info.get("available", []))
    if pm_info.get("snap_available", False) and "snap" not in available:
        available.append("snap")
    return available


# ── Step count estimation ───────────────────────────────────────

def _compute_step_count(option: dict, system_profile: dict | None) -> int:
    """Estimate how many execution steps an option will take.

    This is a rough estimate for the UI — not exact.
    """
    strategy = option.get("strategy", "")

    if strategy in ("retry_with_modifier", "manual"):
        return 1

    if strategy == "install_dep":
        # The dep itself is a full install plan (1-5 steps typically)
        return 2

    if strategy == "install_dep_then_switch":
        # Install dep + switch method install
        return 3

    if strategy == "switch_method":
        return 1

    if strategy == "install_packages":
        return 1

    if strategy == "add_repo":
        return 2  # add repo + retry

    if strategy == "upgrade_dep":
        return 2

    if strategy == "env_fix":
        cmds = option.get("fix_commands", [])
        return max(1, len(cmds))

    if strategy == "cleanup_retry":
        cmds = option.get("cleanup_commands", [])
        return max(1, len(cmds)) + 1  # cleanup + retry

    return 1


# ── Main response builder ──────────────────────────────────────

def build_remediation_response(
    tool_id: str,
    step_idx: int,
    step_label: str,
    exit_code: int,
    stderr: str,
    method: str,
    system_profile: dict | None = None,
    chain: dict | None = None,
    recipe_override: dict | None = None,
) -> dict | None:
    """Build the complete remediation response for the UI.

    This is the central function. Calls the cascade, computes
    availability, sorts options, and assembles the §6 response.

    Args:
        tool_id: The tool that failed.
        step_idx: Index of the failed step in the plan.
        step_label: Human-readable step label.
        exit_code: Process exit code.
        stderr: stderr output from the failed command.
        method: Install method used (e.g. ``"pip"``).
        system_profile: Phase 1 ``_detect_os()`` output.
        chain: Existing escalation chain, or None for first failure.
        recipe_override: If provided, use this recipe instead of
            looking up ``TOOL_RECIPES``.  Used by the scenario
            generator to supply synthetic recipes.

    Returns:
        Full remediation response dict (§6 shape), or None if
        no handlers matched the failure.
    """
    recipe = recipe_override if recipe_override is not None else TOOL_RECIPES.get(tool_id, {})

    # Cascade through all layers
    matched_handlers, merged_options = _collect_all_options(
        tool_id, method, stderr, exit_code, recipe,
    )

    if not matched_handlers and not merged_options:
        return None  # No handlers matched — caller uses generic fallback

    # Compute availability for each option
    for opt in merged_options:
        state, lock_reason, unlock_deps, impossible_reason = (
            _compute_availability(opt, recipe, system_profile)
        )
        opt["availability"] = state
        if lock_reason:
            opt["lock_reason"] = lock_reason
        if unlock_deps:
            opt["unlock_deps"] = unlock_deps
            opt["unlock_step_count"] = sum(
                _compute_step_count({"strategy": "install_dep", "dep": d}, system_profile)
                for d in unlock_deps
            )
        if impossible_reason:
            opt["impossible_reason"] = impossible_reason
        opt["step_count"] = _compute_step_count(opt, system_profile)
        opt.setdefault("risk", "low")

    # Sort by priority
    sorted_options = _sort_options(merged_options)

    # Build failure info from the first (highest priority) matched handler
    first_handler = matched_handlers[0] if matched_handlers else {}

    failure_info = {
        "failure_id": first_handler.get("failure_id", "unknown"),
        "category": first_handler.get("category", "unknown"),
        "label": first_handler.get("label", "Unknown failure"),
        "description": first_handler.get("description", ""),
        "matched_layer": first_handler.get("_matched_layer", ""),
        "matched_method": method,
    }

    # Build chain context
    chain_context = _build_chain_context(chain, tool_id)

    return {
        "ok": False,
        "tool_id": tool_id,
        "step_idx": step_idx,
        "step_label": step_label,
        "exit_code": exit_code,
        "stderr": stderr[:2000],  # Cap stderr for the response
        "failure": failure_info,
        "options": sorted_options,
        "chain": chain_context,
        "fallback_actions": list(_FALLBACK_ACTIONS),
    }


def _build_chain_context(
    chain: dict | None,
    tool_id: str,
) -> dict:
    """Build the chain context section of the response.

    If no chain exists (first failure), returns a minimal context.
    If a chain exists, includes breadcrumbs and depth info.
    """
    if not chain:
        return {
            "chain_id": None,
            "original_goal": tool_id,
            "depth": 0,
            "max_depth": 3,
            "breadcrumbs": [],
        }

    return {
        "chain_id": chain.get("chain_id"),
        "original_goal": chain.get("original_goal", {}).get("tool_id", tool_id),
        "depth": len(chain.get("escalation_stack", [])),
        "max_depth": chain.get("max_depth", 3),
        "breadcrumbs": chain.get("breadcrumbs", []),
    }


# ── Legacy compatibility adapter ───────────────────────────────

def to_legacy_remediation(response: dict) -> dict:
    """Convert a §6 response to the legacy remediation shape.

    The legacy shape (used by the current UI) has:
      ``{"reason": "...", "options": [{"label": ..., "command": ..., ...}]}``

    This adapter lets old callers work while we migrate.

    Args:
        response: Full §6 response dict.

    Returns:
        Legacy-shaped remediation dict.
    """
    if not response:
        return {}

    failure = response.get("failure", {})
    options = response.get("options", [])

    legacy_options = []
    for opt in options:
        legacy_opt: dict[str, Any] = {
            "label": opt.get("label", ""),
            "description": opt.get("description", ""),
            "icon": opt.get("icon", "📦"),
        }
        # The legacy modal expects a "command" field for execution
        # For now, we pass the strategy info and let the backend resolve
        strategy = opt.get("strategy", "")
        if strategy == "retry_with_modifier":
            modifier = opt.get("modifier", {})
            if modifier.get("retry_sudo"):
                legacy_opt["needs_sudo"] = True
        legacy_opt["strategy"] = strategy
        legacy_opt["option_id"] = opt.get("id", "")
        legacy_options.append(legacy_opt)

    return {
        "reason": failure.get("label", "Installation failed"),
        "options": legacy_options,
    }
