"""
L2 Resolver — Update plan resolution.

Produces executable update plans for tools that are already installed
but outdated.  Plans share the same shape as install plans so the
frontend ``showStepModal()`` and the SSE execution endpoint work
without modification.
"""

from __future__ import annotations

import logging
import shutil
from typing import Any

from src.core.services.tool_install.data.recipes import TOOL_RECIPES
from src.core.services.tool_install.detection.tool_version import get_tool_version
from src.core.services.tool_install.domain.risk import (
    _check_risk_escalation,
    _infer_risk,
    _plan_risk,
)
from src.core.services.tool_install.resolver.method_selection import (
    _pick_method_command,
    get_update_map,
)

logger = logging.getLogger(__name__)


def resolve_update_plan(
    tool: str,
    system_profile: dict,
    *,
    prefer_method: str | None = None,
) -> dict:
    """Produce an ordered update plan for an installed tool.

    Unlike ``resolve_install_plan()``, this does NOT short-circuit on
    "already installed" — the whole point is to update a tool that IS
    installed but outdated.

    Uses ``get_update_map(recipe)`` to resolve the update command,
    wraps it in the standard plan format so ``showStepModal()`` and
    the SSE execute endpoint work identically.

    Args:
        tool: Tool ID (e.g. ``"docker"``, ``"kubectl"``).
        system_profile: Phase 1 ``_detect_os()`` output.
        prefer_method: If set, force this specific method from the
            update map (e.g. ``"_default"`` for direct download).

    Returns:
        Plan dict with ``steps`` list on success, or ``error`` key
        on failure::

            {
                "tool": "docker",
                "label": "Docker",
                "action": "update",
                "from_version": "24.0.7",
                "needs_sudo": True,
                "steps": [ ... ],
                "risk_summary": { ... },
                "confirmation_gate": { ... },
            }
    """
    recipe = TOOL_RECIPES.get(tool)
    if not recipe:
        return {"tool": tool, "error": f"No recipe for '{tool}'."}

    cli = recipe.get("cli", tool)
    if not shutil.which(cli):
        return {
            "tool": tool,
            "error": f"{tool} is not installed. Cannot update a tool that isn't installed.",
        }

    # ── Get current version ────────────────────────────────────
    version_before = get_tool_version(tool)

    # ── Resolve update command ─────────────────────────────────
    update_map = get_update_map(recipe)
    if not update_map:
        return {
            "tool": tool,
            "label": recipe.get("label", tool),
            "error": f"No update command defined for {tool}.",
            "manual_hint": _manual_update_hint(tool, recipe),
        }

    # If a preferred method was requested, try to use it directly
    if prefer_method and prefer_method in update_map:
        cmd = update_map[prefer_method]
        if isinstance(cmd, list):
            resolved = (cmd, prefer_method)
        else:
            resolved = None
    else:
        resolved = _pick_method_command(update_map, system_profile)

    if not resolved:
        available = [m for m in update_map if not m.startswith("_")]
        return {
            "tool": tool,
            "label": recipe.get("label", tool),
            "error": f"No update method available for {tool} on this system.",
            "available_methods": available,
        }

    cmd, method = resolved
    needs_sudo = recipe.get("needs_sudo", {}).get(method, False)

    # Resolve {os}, {arch} placeholders in command
    from src.core.services.tool_install.execution.build_helpers import (
        _substitute_install_vars,
    )
    cmd = _substitute_install_vars(list(cmd), system_profile)

    # ── Build steps ────────────────────────────────────────────
    steps: list[dict] = []

    # 1. Update step
    steps.append({
        "type": "tool",
        "label": f"Update {recipe.get('label', tool)}",
        "tool_id": tool,
        "command": cmd,
        "needs_sudo": needs_sudo,
        "method": method,
    })

    # 2. Verify step (if recipe has one)
    verify_cmd = recipe.get("verify")
    if verify_cmd:
        steps.append({
            "type": "verify",
            "label": f"Verify {recipe.get('label', tool)}",
            "command": list(verify_cmd),
            "needs_sudo": False,
        })

    # ── Risk tagging ───────────────────────────────────────────
    for step in steps:
        step["risk"] = _infer_risk(step)

    risk_summary = _plan_risk(steps)

    # ── Confirmation gate ──────────────────────────────────────
    any_sudo = any(s["needs_sudo"] for s in steps)

    if risk_summary["has_high"]:
        high_steps = [
            {
                "label": s.get("label", f"Step {i + 1}"),
                "risk_description": s.get(
                    "risk_description",
                    "This step modifies system components.",
                ),
            }
            for i, s in enumerate(steps)
            if s.get("risk") == "high"
        ]
        confirmation_gate = {
            "type": "double",
            "required": True,
            "reason": "This update contains high-risk steps that modify system components.",
            "confirm_text": "I understand",
            "high_risk_steps": high_steps,
        }
    elif risk_summary["has_medium"]:
        medium_count = sum(1 for s in steps if s.get("risk") == "medium")
        confirmation_gate = {
            "type": "single",
            "required": True,
            "reason": (
                f"This update requires administrator access (sudo) "
                f"for {medium_count} step{'s' if medium_count > 1 else ''}."
            ),
        }
    else:
        confirmation_gate = {
            "type": "none",
            "required": False,
        }

    # ── Assemble plan ──────────────────────────────────────────
    plan: dict[str, Any] = {
        "tool": tool,
        "label": recipe.get("label", tool),
        "action": "update",
        "from_version": version_before,
        "already_installed": False,
        "needs_sudo": any_sudo,
        "method": method,
        "risk_summary": risk_summary,
        "confirmation_gate": confirmation_gate,
        "steps": steps,
    }

    # Check for risk escalation
    escalation = _check_risk_escalation(recipe, risk_summary)
    if escalation:
        plan["risk_escalation"] = escalation

    has_sudo = system_profile.get("capabilities", {}).get("has_sudo", True)
    if any_sudo and not has_sudo:
        plan["warning"] = (
            "This update requires sudo but sudo is not available on this system."
        )

    return plan


def resolve_batch_update_plan(
    tools: list[str],
    system_profile: dict,
) -> dict:
    """Produce a combined update plan for multiple tools.

    Resolves individual update plans and merges their steps into a
    single ordered plan.  Tools without update commands or that are
    not installed are collected in a ``skipped`` list.

    Args:
        tools: List of tool IDs to update.
        system_profile: Phase 1 ``_detect_os()`` output.

    Returns:
        Combined plan dict::

            {
                "tools": ["docker", "kubectl"],
                "action": "batch_update",
                "steps": [ ... merged steps ... ],
                "skipped": [{"tool": "helm", "reason": "No update command"}],
                ...
            }
    """
    all_steps: list[dict] = []
    skipped: list[dict] = []
    tool_labels: list[str] = []
    any_sudo = False

    for tool_id in tools:
        plan = resolve_update_plan(tool_id, system_profile)

        if plan.get("error"):
            skipped.append({
                "tool": tool_id,
                "label": plan.get("label", tool_id),
                "reason": plan["error"],
            })
            continue

        steps = plan.get("steps", [])
        if not steps:
            skipped.append({
                "tool": tool_id,
                "label": plan.get("label", tool_id),
                "reason": "No update steps resolved.",
            })
            continue

        all_steps.extend(steps)
        tool_labels.append(plan.get("label", tool_id))
        if plan.get("needs_sudo"):
            any_sudo = True

    if not all_steps:
        return {
            "tools": tools,
            "action": "batch_update",
            "error": "No tools could be updated.",
            "skipped": skipped,
        }

    # ── Risk for the combined plan ─────────────────────────────
    risk_summary = _plan_risk(all_steps)

    # Confirmation gate for batch — always at least "single" since
    # batch updates are inherently more impactful
    if risk_summary["has_high"]:
        confirmation_gate = {
            "type": "double",
            "required": True,
            "reason": (
                f"This batch update contains high-risk steps across "
                f"{len(tool_labels)} tool(s)."
            ),
            "confirm_text": "I understand",
        }
    else:
        confirmation_gate = {
            "type": "single",
            "required": True,
            "reason": (
                f"This will update {len(tool_labels)} tool(s): "
                f"{', '.join(tool_labels)}."
            ),
        }

    return {
        "tools": tools,
        "label": f"Update {len(tool_labels)} tool(s)",
        "action": "batch_update",
        "already_installed": False,
        "needs_sudo": any_sudo,
        "risk_summary": risk_summary,
        "confirmation_gate": confirmation_gate,
        "steps": all_steps,
        "skipped": skipped,
        "tool_labels": tool_labels,
    }


# ── Helpers ────────────────────────────────────────────────────


def _manual_update_hint(tool: str, recipe: dict) -> str:
    """Generate a manual update hint for tools without update commands.

    Inspects the install method to suggest how the user might update
    the tool manually.
    """
    install_map = recipe.get("install", {})

    if "pip" in install_map:
        return f"pip install --upgrade {recipe.get('cli', tool)}"
    if "npm" in install_map:
        return f"npm update -g {recipe.get('cli', tool)}"
    if "cargo" in install_map:
        return f"cargo install {recipe.get('cli', tool)}"
    if "brew" in install_map:
        return f"brew upgrade {recipe.get('cli', tool)}"
    if "apt" in install_map:
        return f"sudo apt update && sudo apt upgrade {recipe.get('cli', tool)}"

    return f"Check the official documentation for {recipe.get('label', tool)} update instructions."
