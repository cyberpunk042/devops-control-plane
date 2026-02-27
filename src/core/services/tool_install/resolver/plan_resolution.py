"""
L2 Resolver — Plan resolution.

Top-level plan resolvers that combine method selection,
dependency collection, choice resolution, and risk assessment
to produce executable plans.
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import Any

from src.core.services.tool_install.data.recipes import TOOL_RECIPES
from src.core.services.tool_install.detection.condition import _evaluate_condition
from src.core.services.tool_install.detection.tool_version import (
    _is_linux_binary,
    get_tool_version,
)
from src.core.services.tool_install.domain.risk import _infer_risk, _plan_risk, _check_risk_escalation
from src.core.services.tool_install.domain.version_constraint import check_version_constraint
from src.core.services.tool_install.resolver.dependency_collection import _collect_deps
from src.core.services.tool_install.resolver.method_selection import (
    _build_pkg_install_cmd,
    _pick_install_method,
    _wrap_with_env,
)

logger = logging.getLogger(__name__)


def resolve_install_plan(
    tool: str,
    system_profile: dict,
) -> dict:
    """Produce an ordered install plan for a tool.

    Walks the dependency tree depth-first, batches system packages,
    orders tool installs, applies post-env propagation, filters
    post_install conditions, and adds a verify step.

    Args:
        tool: Tool ID (e.g. ``"cargo-outdated"``).
        system_profile: Phase 1 ``_detect_os()`` output.

    Returns:
        Plan dict with ``steps`` list on success, or ``error`` key
        on failure::

            {
                "tool": "cargo-outdated",
                "label": "cargo-outdated",
                "needs_sudo": True,
                "already_installed": False,
                "steps": [ ... ],
            }
    """
    recipe = TOOL_RECIPES.get(tool)
    if not recipe:
        return {"tool": tool, "error": f"No recipe for '{tool}'."}

    # ── Type-based dispatch ────────────────────────────────────
    recipe_type = recipe.get("type", "tool")

    if recipe_type == "data_pack":
        return _resolve_data_pack_plan(tool, recipe, system_profile)

    if recipe_type == "config":
        return _resolve_config_plan(tool, recipe, system_profile)

    cli = recipe.get("cli", tool)
    cli_path = shutil.which(cli)
    if cli_path and _is_linux_binary(cli_path):
        # ── Check version constraint before declaring "already installed" ──
        min_ver = recipe.get("minimum_version")
        vc = recipe.get("version_constraint")
        installed_version = get_tool_version(tool)

        needs_upgrade = False
        version_message = ""

        if installed_version and min_ver:
            vc_result = check_version_constraint(
                installed_version,
                {"type": "gte", "reference": min_ver},
            )
            if not vc_result.get("valid"):
                needs_upgrade = True
                version_message = vc_result.get("message", "")
                logger.info(
                    "%s installed (%s) but below minimum %s — planning upgrade",
                    tool, installed_version, min_ver,
                )

        if installed_version and vc and not needs_upgrade:
            vc_result = check_version_constraint(installed_version, vc)
            if not vc_result.get("valid"):
                needs_upgrade = True
                version_message = vc_result.get("message", "")
                logger.info(
                    "%s installed (%s) but fails constraint — planning upgrade",
                    tool, installed_version,
                )

        if not needs_upgrade:
            return {
                "tool": tool,
                "label": recipe["label"],
                "already_installed": True,
                "version_installed": installed_version,
                "steps": [],
            }

        # Fall through to plan generation for upgrade
        logger.info("%s needs upgrade: %s", tool, version_message)

    pm = system_profile.get("package_manager", {}).get("primary", "apt")
    snap_ok = system_profile.get("package_manager", {}).get("snap_available", False)

    # Check if a method exists for the target tool itself
    method_for_target = _pick_install_method(recipe, pm, snap_ok)
    if method_for_target is None:
        available = [m for m in recipe.get("install", {}) if not m.startswith("_")]
        return {
            "tool": tool,
            "label": recipe["label"],
            "error": f"No install method available for {recipe['label']} on this system.",
            "available_methods": available,
            "suggestion": (
                f"Install {' or '.join(available)} to enable "
                f"{recipe['label']} installation."
                if available else "No known install method for this platform."
            ),
        }

    # ── Collect deps ──
    batch_packages: list[str] = []
    tool_steps: list[dict] = []
    batched_tools: list[str] = []
    post_env_map: dict[str, str] = {}
    visited: set[str] = set()

    _collect_deps(
        tool, system_profile, visited,
        batch_packages, tool_steps, batched_tools, post_env_map,
    )

    # ── Build plan steps ──
    steps: list[dict] = []

    # 1. Repo setup (if any tool step has repo_setup for this pm)
    for ts in tool_steps:
        for rs in ts["recipe"].get("repo_setup", {}).get(pm, []):
            steps.append({
                "type": "repo_setup",
                "label": rs["label"],
                "tool_id": ts["tool_id"],
                "command": rs["command"],
                "needs_sudo": rs.get("needs_sudo", True),
            })

    # 2. System packages batch (single step)
    if batch_packages:
        cmd = _build_pkg_install_cmd(batch_packages, pm)
        steps.append({
            "type": "packages",
            "label": "Install system packages",
            "command": cmd,
            "needs_sudo": pm != "brew",
            "packages": list(batch_packages),
        })

    # 3. Tool install steps (dependency order)
    accumulated_env = ""
    for ts in tool_steps:
        tool_id = ts["tool_id"]
        recipe_t = ts["recipe"]
        method = ts["method"]

        # ── Build-from-source method ──
        if method == "source":
            from src.core.services.tool_install.execution.build_helpers import (
                _autotools_plan,
                _cargo_git_plan,
                _cmake_plan,
                _substitute_install_vars,
                _validate_toolchain,
            )

            source_spec = recipe_t["install"]["source"]
            build_system = source_spec.get("build_system", "autotools")

            # Toolchain validation step
            required_tools = source_spec.get("requires_toolchain", [])
            if not required_tools:
                # Infer from build system
                if build_system == "cmake":
                    required_tools = ["cmake", "make"]
                elif build_system == "autotools":
                    required_tools = ["make", "gcc"]
                elif build_system == "cargo-git":
                    required_tools = ["cargo"]

            tc_check = _validate_toolchain(required_tools)
            if not tc_check["ok"]:
                steps.append({
                    "type": "notification",
                    "label": f"Missing build tools for {recipe_t['label']}",
                    "message": tc_check.get("suggestion", "Install missing build tools"),
                    "missing_tools": tc_check["missing"],
                    "severity": "error",
                })

            # Source acquisition step — git clone or tarball download
            build_dir = source_spec.get(
                "build_dir",
                f"/tmp/devops-cp-build-{tool_id}",
            )

            if "git_repo" in source_spec:
                steps.append({
                    "type": "source",
                    "label": f"Clone {recipe_t['label']} source",
                    "tool_id": tool_id,
                    "source": {
                        "type": "git",
                        "repo": source_spec["git_repo"],
                        "branch": source_spec.get("branch"),
                        "depth": source_spec.get("depth", 1),
                    },
                    "dest": build_dir,
                    "needs_sudo": False,
                })
            elif "tarball_url" in source_spec:
                tarball_url = source_spec["tarball_url"]
                # Variable substitution for {version}, {arch}, etc.
                default_version = source_spec.get("default_version", "")
                tarball_url_resolved = _substitute_install_vars(
                    [tarball_url], system_profile,
                    version=default_version,
                )[0]
                steps.append({
                    "type": "source",
                    "label": f"Download {recipe_t['label']} source tarball",
                    "tool_id": tool_id,
                    "source": {
                        "type": "tarball",
                        "url": tarball_url_resolved,
                    },
                    "dest": build_dir,
                    "needs_sudo": False,
                })
            else:
                # No source acquisition method specified
                logger.warning(
                    "Source method for %s has no git_repo or tarball_url",
                    tool_id,
                )
                continue

            # Build steps — dispatch to the right plan generator
            if build_system == "autotools":
                build_steps = _autotools_plan(source_spec, system_profile, build_dir)
            elif build_system == "cmake":
                build_steps = _cmake_plan(source_spec, system_profile, build_dir)
            elif build_system == "cargo-git":
                build_steps = _cargo_git_plan(source_spec, system_profile)
            else:
                # Generic: use the raw command from the recipe
                raw_cmd = source_spec.get("command", ["make"])
                build_steps = [{
                    "type": "build",
                    "label": f"Build {recipe_t['label']}",
                    "command": _substitute_install_vars(raw_cmd, system_profile),
                    "cwd": build_dir,
                    "needs_sudo": False,
                }]

            for bs in build_steps:
                bs["tool_id"] = tool_id
                steps.append(bs)

            # Cleanup step
            steps.append({
                "type": "cleanup",
                "label": "Cleanup build directory",
                "command": ["rm", "-rf", build_dir],
                "needs_sudo": False,
            })
            continue

        cmd = recipe_t["install"][method]
        sudo = recipe_t.get("needs_sudo", {}).get(method, False)

        # ── Resolve OS variant for dict _default ─────────────
        # _default may be a dict keyed by OS (e.g. {"linux": [...],
        # "darwin": [...]}). Extract the command for this OS.
        if method == "_default" and isinstance(cmd, dict):
            import platform as _plat
            current_os = _plat.system().lower()
            cmd = cmd[current_os]  # guaranteed to exist — method_selection checked
        cmd = list(cmd)

        # ── Arch/OS variable substitution for _default commands ──
        if method == "_default":
            from src.core.services.tool_install.execution.build_helpers import (
                _substitute_install_vars,
            )
            # Inject recipe-level arch_map so per-tool overrides work.
            # Docker Compose releases use x86_64/aarch64, not amd64/arm64.
            recipe_arch_map = recipe_t.get("arch_map")
            if recipe_arch_map:
                system_profile["_arch_map"] = recipe_arch_map
            cmd = _substitute_install_vars(cmd, system_profile)
            # Clean up to avoid leaking into other tools
            system_profile.pop("_arch_map", None)

        # ── M6: Dynamic npm sudo detection ──────────────────
        if method == "npm" and not sudo:
            import subprocess as _sp
            try:
                prefix = _sp.run(
                    ["npm", "config", "get", "prefix"],
                    capture_output=True, text=True, timeout=5,
                ).stdout.strip()
                if prefix and not os.access(prefix, os.W_OK):
                    sudo = True
                    logger.debug("npm prefix %s not writable — needs sudo", prefix)
            except Exception:
                pass  # npm not found or timeout — leave as-is

        if accumulated_env:
            cmd = _wrap_with_env(cmd, accumulated_env)

        steps.append({
            "type": "tool",
            "label": f"Install {recipe_t['label']}",
            "tool_id": tool_id,
            "command": cmd,
            "needs_sudo": sudo,
        })

        pe = recipe_t.get("post_env", "")
        if pe:
            accumulated_env = (
                pe if not accumulated_env
                else f"{accumulated_env} && {pe}"
            )

    # 4. Post-install steps (for both tool_steps and batched_tools)
    all_tool_ids = [ts["tool_id"] for ts in tool_steps] + batched_tools
    for tid in all_tool_ids:
        rec = TOOL_RECIPES.get(tid, {})
        for pis in rec.get("post_install", []):
            if not _evaluate_condition(pis.get("condition"), system_profile):
                continue
            steps.append({
                "type": "post_install",
                "label": pis["label"],
                "tool_id": tid,
                "command": pis["command"],
                "needs_sudo": pis.get("needs_sudo", False),
            })

    # 5. Verify step
    verify_cmd = recipe.get("verify")
    if verify_cmd:
        cmd = list(verify_cmd)
        if accumulated_env:
            cmd = _wrap_with_env(cmd, accumulated_env)
        steps.append({
            "type": "verify",
            "label": f"Verify {recipe['label']}",
            "command": cmd,
            "needs_sudo": False,
        })

    # ── Risk tagging ──
    for step in steps:
        step["risk"] = _infer_risk(step)

    # ── Plan-level flags ──
    any_sudo = any(s["needs_sudo"] for s in steps)
    has_sudo = system_profile.get("capabilities", {}).get("has_sudo", True)

    plan: dict[str, Any] = {
        "tool": tool,
        "label": recipe["label"],
        "already_installed": False,
        "needs_sudo": any_sudo,
        "risk_summary": _plan_risk(steps),
        "steps": steps,
    }

    # Check for risk escalation from user choices
    escalation = _check_risk_escalation(recipe, plan["risk_summary"])
    if escalation:
        plan["risk_escalation"] = escalation

    # Confirmation gate — three levels per domain-risk-levels spec
    if plan["risk_summary"]["has_high"]:
        high_steps = []
        for i, s in enumerate(steps):
            if s.get("risk") == "high":
                high_steps.append({
                    "label": s.get("label", f"Step {i+1}"),
                    "risk_description": s.get(
                        "risk_description",
                        "This step modifies system components.",
                    ),
                    "rollback": s.get("rollback", ""),
                    "backup_before": s.get("backup_before", []),
                })
        plan["confirmation_gate"] = {
            "type": "double",
            "required": True,
            "reason": "This plan contains high-risk steps that modify system components.",
            "confirm_text": "I understand",
            "high_risk_steps": high_steps,
        }
    elif plan["risk_summary"]["has_medium"]:
        medium_count = sum(
            1 for s in steps if s.get("risk") == "medium"
        )
        plan["confirmation_gate"] = {
            "type": "single",
            "required": True,
            "reason": (
                f"This plan requires administrator access (sudo) "
                f"for {medium_count} step{'s' if medium_count > 1 else ''}."
            ),
        }
    else:
        plan["confirmation_gate"] = {
            "type": "none",
            "required": False,
        }

    if any_sudo and not has_sudo:
        plan["warning"] = (
            "This plan requires sudo but sudo is not available on this system."
        )

    # ── M7: Version constraint validation ──────────────────
    vc = recipe.get("version_constraint")
    if vc:
        # Determine reference version:
        # 1. Explicit in constraint, 2. From system_profile, 3. reference_hint
        ref_version = vc.get("reference")
        if not ref_version:
            hint = vc.get("reference_hint", "")
            if hint and hint in system_profile.get("versions", {}):
                ref_version = system_profile["versions"][hint]

        if ref_version:
            vc_with_ref = {**vc, "reference": ref_version}
            plan["version_constraint"] = vc_with_ref
            plan["version_constraint"]["description"] = vc.get(
                "description", ""
            )
        else:
            # Can't validate without a reference, but include the constraint
            # so the UI can prompt the user
            plan["version_constraint"] = vc

    return plan


def resolve_install_plan_with_choices(
    tool: str,
    system_profile: dict,
    answers: dict,
) -> dict:
    """Pass 2 — Resolve an install plan using the user's choice answers.

    Takes the user's answers from the choice modal, applies them to
    the recipe (selecting branches, substituting inputs), then resolves
    the plan using the standard single-pass resolver.

    Args:
        tool: Tool ID.
        system_profile: Phase 1 ``_detect_os()`` output.
        answers: ``{"choice_id": "selected_value", "input_id": "val"}``.

    Returns:
        Install plan (same format as ``resolve_install_plan()``).
    """
    recipe = TOOL_RECIPES.get(tool)
    if not recipe:
        return {"tool": tool, "error": f"No recipe for '{tool}'."}

    # Check if already installed
    cli = recipe.get("cli", tool)
    cli_path = shutil.which(cli)
    if cli_path and _is_linux_binary(cli_path):
        return {
            "tool": tool,
            "label": recipe["label"],
            "already_installed": True,
            "steps": [],
        }

    # Apply choices → flatten recipe branches
    resolved_recipe = _apply_choices(recipe, answers)

    # Apply inputs → template substitution
    resolved_recipe = _apply_inputs(resolved_recipe, answers)

    # If choices produced _resolved_steps (multi-step variant like
    # build-from-source), construct the plan directly
    if "_resolved_steps" in resolved_recipe:
        steps = []
        for raw_step in resolved_recipe["_resolved_steps"]:
            step = dict(raw_step)
            step.setdefault("type", "tool")
            step.setdefault("needs_sudo", False)
            steps.append(step)

        # Add verify step if present
        verify_cmd = resolved_recipe.get("verify")
        if verify_cmd:
            if isinstance(verify_cmd, list):
                steps.append({
                    "type": "verify",
                    "label": f"Verify {recipe['label']}",
                    "command": verify_cmd,
                    "needs_sudo": False,
                })

        any_sudo = any(s.get("needs_sudo", False) for s in steps)
        has_sudo = system_profile.get(
            "capabilities", {}
        ).get("has_sudo", True)

        plan: dict[str, Any] = {
            "tool": tool,
            "label": recipe["label"],
            "already_installed": False,
            "needs_sudo": any_sudo,
            "steps": steps,
        }
        if any_sudo and not has_sudo:
            plan["warning"] = (
                "This plan requires sudo but sudo is not available."
            )
        return plan

    # Otherwise, the choices flattened the recipe to a simple form.
    # Temporarily patch TOOL_RECIPES for the single-pass resolver,
    # then restore.
    original = TOOL_RECIPES.get(tool)
    try:
        TOOL_RECIPES[tool] = resolved_recipe
        return resolve_install_plan(tool, system_profile)
    finally:
        if original is not None:
            TOOL_RECIPES[tool] = original
        else:
            TOOL_RECIPES.pop(tool, None)


# ── Data‑pack resolution ──────────────────────────────────────

def _resolve_data_pack_plan(
    tool: str,
    recipe: dict,
    system_profile: dict,
) -> dict:
    """Wrap a data‑pack recipe's pre‑built steps into a plan.

    Data packs have a ``steps`` list with pre‑defined download/setup
    steps.  No method selection needed — the steps are ready to execute.
    """
    raw_steps = recipe.get("steps", [])
    steps: list[dict] = []

    for i, s in enumerate(raw_steps):
        step = {
            "type": s.get("type", "download"),
            "label": s.get("label", f"{recipe['label']} step {i + 1}"),
            "command": s.get("command", []),
            "needs_sudo": s.get("needs_sudo", False),
        }
        # Forward all data-pack specific fields (url, dest, checksum, etc.)
        for key in ("url", "dest", "checksum", "size_hint", "resume",
                     "disk_check", "freshness_days"):
            if key in s:
                step[key] = s[key]
        steps.append(step)

    # Append verify if present
    verify = recipe.get("verify")
    if verify:
        steps.append({
            "type": "verify",
            "label": f"Verify {recipe['label']}",
            "command": verify,
            "needs_sudo": False,
        })

    return {
        "tool": tool,
        "label": recipe["label"],
        "type": "data_pack",
        "already_installed": False,
        "needs_sudo": any(s.get("needs_sudo") for s in steps),
        "steps": steps,
    }


# ── Config resolution ─────────────────────────────────────────

def _resolve_config_plan(
    tool: str,
    recipe: dict,
    system_profile: dict,
) -> dict:
    """Wrap a config recipe's templates into config steps.

    Config recipes define config file templates with target paths,
    default content, and backup policies.
    """
    templates = recipe.get("config_templates", [])
    steps: list[dict] = []

    for tmpl in templates:
        steps.append({
            "type": "config",
            "label": tmpl.get("label", f"Configure {tmpl.get('file', '?')}"),
            "target_file": tmpl.get("file", ""),
            "template": tmpl.get("template", ""),
            "defaults": tmpl.get("defaults", {}),
            "backup": tmpl.get("backup", True),
            "needs_sudo": tmpl.get("needs_sudo", True),
        })

    # Post-install steps (e.g., restart docker after config change)
    for pis in recipe.get("post_install", []):
        steps.append({
            "type": "post_install",
            "label": pis.get("label", "Post-install"),
            "command": pis.get("command", []),
            "needs_sudo": pis.get("needs_sudo", False),
        })

    # Verify step
    verify = recipe.get("verify")
    if verify:
        steps.append({
            "type": "verify",
            "label": f"Verify {recipe['label']}",
            "command": verify,
            "needs_sudo": False,
        })

    return {
        "tool": tool,
        "label": recipe["label"],
        "type": "config",
        "already_installed": False,
        "needs_sudo": any(s.get("needs_sudo") for s in steps),
        "steps": steps,
    }

