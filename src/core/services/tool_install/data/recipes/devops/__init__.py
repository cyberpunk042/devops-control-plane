"""
L0 Data — DevOps & infrastructure recipes.
"""

from __future__ import annotations

from src.core.services.tool_install.data.recipes.devops.cicd import _CICD_RECIPES
from src.core.services.tool_install.data.recipes.devops.cloud import _CLOUD_RECIPES
from src.core.services.tool_install.data.recipes.devops.containers import (
    _CONTAINERS_RECIPES,
)
from src.core.services.tool_install.data.recipes.devops.k8s import _K8S_RECIPES
from src.core.services.tool_install.data.recipes.devops.monitoring import (
    _MONITORING_RECIPES,
)

_DEVOPS_RECIPES: dict[str, dict] = {
    **_K8S_RECIPES,
    **_CLOUD_RECIPES,
    **_CONTAINERS_RECIPES,
    **_CICD_RECIPES,
    **_MONITORING_RECIPES,
}
