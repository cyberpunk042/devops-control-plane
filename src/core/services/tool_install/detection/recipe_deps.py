"""
L3 Detection — Recipe dependency resolution.

Resolves system-level package dependencies from TOOL_RECIPES
based on the detected OS/distro family.
"""

from __future__ import annotations

from src.core.services.tool_install.data.recipes import TOOL_RECIPES


def _get_system_deps(tool: str) -> list[str]:
    """Get system package deps for a tool, using detected distro family.

    Looks up requires.packages from TOOL_RECIPES keyed by distro family.
    Falls back to debian names if family not found.
    Returns empty list if tool has no package requirements.
    """
    recipe = TOOL_RECIPES.get(tool, {})
    pkg_map = recipe.get("requires", {}).get("packages", {})
    if not pkg_map:
        return []
    from src.core.services.audit.l0_detection import _detect_os
    family = _detect_os().get("distro", {}).get("family", "debian")
    return pkg_map.get(family, pkg_map.get("debian", []))
