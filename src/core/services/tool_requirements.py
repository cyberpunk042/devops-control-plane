"""
Tool requirements helper — check which tools a card needs and which are missing.

Used by card status functions to consistently report missing tools
with install recipe information.
"""

from __future__ import annotations

from typing import Any


def check_required_tools(tool_ids: list[str]) -> list[dict[str, Any]]:
    """Check which of the given tool IDs are missing.

    Args:
        tool_ids: List of tool ID strings (e.g. ``["kubectl", "helm"]``).

    Returns:
        List of dicts for each *missing* tool::

            [
                {
                    "id": "kubectl",
                    "label": "kubectl",
                    "install_type": "sudo",
                    "has_recipe": True,
                    "needs_sudo": True,
                },
                ...
            ]

        Empty list if all tools are available.
    """
    from src.core.services.audit.l0_detection import detect_tools
    from src.core.services.tool_install import TOOL_RECIPES

    # Only detect the tools we care about (fast — reuses cached shutil.which)
    all_tools = {t["id"]: t for t in detect_tools()}

    missing = []
    for tid in tool_ids:
        recipe = TOOL_RECIPES.get(tid)
        t = all_tools.get(tid)
        if t is None:
            # Tool not in registry at all
            missing.append({
                "id": tid,
                "label": tid,
                "install_type": "none",
                "has_recipe": recipe is not None,
                "needs_sudo": (
                    any(recipe["needs_sudo"].values()) if recipe else False
                ),
            })
        elif not t["available"]:
            missing.append({
                "id": t["id"],
                "label": t["label"],
                "install_type": t["install_type"],
                "has_recipe": recipe is not None,
                "needs_sudo": (
                    any(recipe["needs_sudo"].values()) if recipe else False
                ),
            })

    return missing
