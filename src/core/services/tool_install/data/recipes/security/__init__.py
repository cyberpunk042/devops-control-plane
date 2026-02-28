"""
L0 Data — Security & crypto recipes.
"""

from __future__ import annotations

from src.core.services.tool_install.data.recipes.security.crypto import (
    _CRYPTO_RECIPES,
)
from src.core.services.tool_install.data.recipes.security.scanners import (
    _SCANNERS_RECIPES,
)

_SECURITY_RECIPES: dict[str, dict] = {
    **_SCANNERS_RECIPES,
    **_CRYPTO_RECIPES,
}
