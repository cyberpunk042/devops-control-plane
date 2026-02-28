"""
L0 Data — Networking recipes.
"""

from __future__ import annotations

from src.core.services.tool_install.data.recipes.network.dns import _DNS_RECIPES
from src.core.services.tool_install.data.recipes.network.network import (
    _NETWORK_RECIPES as _NET_RECIPES,
)
from src.core.services.tool_install.data.recipes.network.proxy import _PROXY_RECIPES
from src.core.services.tool_install.data.recipes.network.service_discovery import (
    _SERVICE_DISCOVERY_RECIPES,
)

_NETWORK_RECIPES: dict[str, dict] = {
    **_NET_RECIPES,
    **_DNS_RECIPES,
    **_PROXY_RECIPES,
    **_SERVICE_DISCOVERY_RECIPES,
}
