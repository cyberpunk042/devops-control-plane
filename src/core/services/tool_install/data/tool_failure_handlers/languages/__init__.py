"""
Tool-specific failure handlers — Language ecosystem tools.

Merges handlers from: rust, go, python, node, php
"""

from __future__ import annotations

from .rust import _CARGO_HANDLERS, _RUSTUP_HANDLERS
from .go import _GO_HANDLERS
from .python import _PYTHON_HANDLERS, _POETRY_HANDLERS, _UV_HANDLERS
from .node import _NODE_HANDLERS, _NVM_HANDLERS, _YARN_HANDLERS, _PNPM_HANDLERS
from .php import _COMPOSER_HANDLERS

LANGUAGE_TOOL_HANDLERS: dict[str, list[dict]] = {
    "cargo": _CARGO_HANDLERS,
    "rustup": _RUSTUP_HANDLERS,
    "go": _GO_HANDLERS,
    "python": _PYTHON_HANDLERS,
    "poetry": _POETRY_HANDLERS,
    "uv": _UV_HANDLERS,
    "node": _NODE_HANDLERS,
    "nvm": _NVM_HANDLERS,
    "yarn": _YARN_HANDLERS,
    "pnpm": _PNPM_HANDLERS,
    "composer": _COMPOSER_HANDLERS,
}
