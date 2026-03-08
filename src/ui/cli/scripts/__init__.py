"""
CLI commands for the Scripts system — discover, run, and manage scripts.

Thin wrappers over ``src.core.services.scripts`` (M1 backend).

Sub-modules:
    list.py    — list discovered scripts
    run.py     — run a script with parameters
    info.py    — show script metadata + parameters
    history.py — show script run history
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
def scripts() -> None:
    """Scripts — discover, run, and manage automation scripts."""


from . import list, run, info, history  # noqa: E402, F401
