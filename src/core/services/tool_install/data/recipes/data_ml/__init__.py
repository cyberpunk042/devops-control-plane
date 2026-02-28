"""
L0 Data — Data, ML, database & GPU recipes.
"""

from __future__ import annotations

from src.core.services.tool_install.data.recipes.data_ml.data_packs import (
    _DATA_PACKS_RECIPES,
)
from src.core.services.tool_install.data.recipes.data_ml.databases import (
    _DATABASES_RECIPES,
)
from src.core.services.tool_install.data.recipes.data_ml.gpu import _GPU_RECIPES
from src.core.services.tool_install.data.recipes.data_ml.ml import _ML_RECIPES

_DATA_ML_RECIPES: dict[str, dict] = {
    **_ML_RECIPES,
    **_DATA_PACKS_RECIPES,
    **_DATABASES_RECIPES,
    **_GPU_RECIPES,
}
