"""
CLI commands for GitHub Pages deployment.

Thin wrappers over ``src.core.services.pages_engine``
and ``src.core.services.pages_builders``.

Sub-modules:
    segments.py — list, add, remove segments
    build.py    — build, merge, deploy, ci, status
    info.py     — builders
"""

from __future__ import annotations

import sys
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
def pages() -> None:
    """GitHub Pages — build, deploy, and manage page segments."""


from . import segments, build, info  # noqa: E402, F401
