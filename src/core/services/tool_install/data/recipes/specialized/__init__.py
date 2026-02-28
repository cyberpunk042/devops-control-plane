"""
L0 Data — Specialized tool recipes (devtools, media, docs, config, build tools).
"""

from __future__ import annotations

from src.core.services.tool_install.data.recipes.specialized.build_tools import (
    _BUILD_TOOLS_RECIPES,
)
from src.core.services.tool_install.data.recipes.specialized.config import (
    _CONFIG_RECIPES,
)
from src.core.services.tool_install.data.recipes.specialized.devtools import (
    _DEVTOOLS_RECIPES,
)
from src.core.services.tool_install.data.recipes.specialized.media_docs import (
    _MEDIA_DOCS_RECIPES,
)

_SPECIALIZED_RECIPES: dict[str, dict] = {
    **_DEVTOOLS_RECIPES,
    **_MEDIA_DOCS_RECIPES,
    **_CONFIG_RECIPES,
    **_BUILD_TOOLS_RECIPES,
}
