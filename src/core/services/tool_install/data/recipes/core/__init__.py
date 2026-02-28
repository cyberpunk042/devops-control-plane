"""
L0 Data — Core system & shell recipes.
"""

from __future__ import annotations

from src.core.services.tool_install.data.recipes.core.shell import _SHELL_RECIPES
from src.core.services.tool_install.data.recipes.core.system import _SYSTEM_RECIPES

_CORE_RECIPES: dict[str, dict] = {
    **_SYSTEM_RECIPES,
    **_SHELL_RECIPES,
}
