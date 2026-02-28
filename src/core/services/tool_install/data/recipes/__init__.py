"""
L0 Data — Composite tool recipe registry.

Merges all domain recipe sub-packages into the canonical ``TOOL_RECIPES``
dict. Every consumer imports this single symbol — the internal split
is invisible to them.

Structure::

    recipes/
    ├── __init__.py          ← YOU ARE HERE (merge point)
    ├── core/                system, shell, terminal, compression
    ├── languages/           python, node, rust, go, jvm, web, other
    ├── devops/              k8s, cloud, iac, containers, cicd, monitoring
    ├── security/            security, crypto
    ├── network/             network, dns, proxy
    ├── data_ml/             ml, gpu, database, data_pack
    └── specialized/         devtools, editors, media, docs, config, build
"""

from __future__ import annotations

from src.core.services.tool_install.data.recipes.core import _CORE_RECIPES
from src.core.services.tool_install.data.recipes.data_ml import _DATA_ML_RECIPES
from src.core.services.tool_install.data.recipes.devops import _DEVOPS_RECIPES
from src.core.services.tool_install.data.recipes.languages import _LANGUAGE_RECIPES
from src.core.services.tool_install.data.recipes.network import _NETWORK_RECIPES
from src.core.services.tool_install.data.recipes.security import _SECURITY_RECIPES
from src.core.services.tool_install.data.recipes.specialized import (
    _SPECIALIZED_RECIPES,
)

TOOL_RECIPES: dict[str, dict] = {
    **_CORE_RECIPES,
    **_LANGUAGE_RECIPES,
    **_DEVOPS_RECIPES,
    **_SECURITY_RECIPES,
    **_NETWORK_RECIPES,
    **_DATA_ML_RECIPES,
    **_SPECIALIZED_RECIPES,
}
