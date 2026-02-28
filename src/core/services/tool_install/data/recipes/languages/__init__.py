"""
L0 Data — Programming language ecosystem recipes.
"""

from __future__ import annotations

from src.core.services.tool_install.data.recipes.languages.dotnet import (
    _DOTNET_RECIPES,
)
from src.core.services.tool_install.data.recipes.languages.elixir import (
    _ELIXIR_RECIPES,
)
from src.core.services.tool_install.data.recipes.languages.go import _GO_RECIPES
from src.core.services.tool_install.data.recipes.languages.haskell import (
    _HASKELL_RECIPES,
)
from src.core.services.tool_install.data.recipes.languages.jvm import _JVM_RECIPES
from src.core.services.tool_install.data.recipes.languages.lua import _LUA_RECIPES
from src.core.services.tool_install.data.recipes.languages.node import _NODE_RECIPES
from src.core.services.tool_install.data.recipes.languages.ocaml import (
    _OCAML_RECIPES,
)
from src.core.services.tool_install.data.recipes.languages.php import _PHP_RECIPES
from src.core.services.tool_install.data.recipes.languages.python import (
    _PYTHON_RECIPES,
)
from src.core.services.tool_install.data.recipes.languages.rlang import (
    _RLANG_RECIPES,
)
from src.core.services.tool_install.data.recipes.languages.ruby import _RUBY_RECIPES
from src.core.services.tool_install.data.recipes.languages.rust import _RUST_RECIPES
from src.core.services.tool_install.data.recipes.languages.wasm import _WASM_RECIPES
from src.core.services.tool_install.data.recipes.languages.zig import _ZIG_RECIPES

_LANGUAGE_RECIPES: dict[str, dict] = {
    **_PYTHON_RECIPES,
    **_NODE_RECIPES,
    **_RUST_RECIPES,
    **_GO_RECIPES,
    **_JVM_RECIPES,
    **_RUBY_RECIPES,
    **_PHP_RECIPES,
    **_DOTNET_RECIPES,
    **_ELIXIR_RECIPES,
    **_LUA_RECIPES,
    **_ZIG_RECIPES,
    **_WASM_RECIPES,
    **_HASKELL_RECIPES,
    **_OCAML_RECIPES,
    **_RLANG_RECIPES,
}
