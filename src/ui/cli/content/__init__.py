"""
CLI commands for Content Vault integration.

Thin wrappers over ``src.core.services.content_crypto``
and ``src.core.services.content_ops``.

Sub-modules:
    crypto.py   — encrypt, decrypt, inspect, classify
    optimize.py — folders, optimize
    release.py  — release list, restore, inventory
"""

from __future__ import annotations

from pathlib import Path

import click


def _resolve_project_root(ctx: click.Context) -> Path:
    """Resolve project root from context or CWD."""
    config_path: Path | None = ctx.obj.get("config_path")
    if config_path is None:
        from src.core.config.loader import find_project_file

        config_path = find_project_file()
    return config_path.parent.resolve() if config_path else Path.cwd()


@click.group()
def content() -> None:
    """Content Vault — encrypt, decrypt, optimize, and manage content files."""


from . import crypto, optimize, release  # noqa: E402, F401
