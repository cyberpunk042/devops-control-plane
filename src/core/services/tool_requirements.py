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
    import shutil
    from src.core.services.audit.l0_detection import TOOL_REGISTRY
    from src.core.services.tool_install import TOOL_RECIPES

    # Build lookup from the registry (no detection, just metadata)
    registry_by_id = {t["id"]: t for t in TOOL_REGISTRY}

    missing = []
    for tid in tool_ids:
        spec = registry_by_id.get(tid)
        cli_name = spec["cli"] if spec else tid

        # Only check this specific tool — not all 35
        if shutil.which(cli_name) is not None:
            continue  # available, skip

        recipe = TOOL_RECIPES.get(tid)
        missing.append({
            "id": tid,
            "label": spec["label"] if spec else tid,
            "install_type": spec.get("install_type", "none") if spec else "none",
            "has_recipe": recipe is not None,
            "needs_sudo": (
                any(recipe["needs_sudo"].values()) if recipe else False
            ),
        })

    return missing
