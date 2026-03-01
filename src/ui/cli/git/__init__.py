"""
CLI commands for Git & GitHub.

Thin wrappers over ``src.core.services.git_ops``
and the ``gh`` CLI.

Sub-modules:
    core.py   — status, log, commit, pull, push
    github.py — gh pulls, runs, dispatch, workflows
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
def git() -> None:
    """Git & GitHub — status, commit, push, pull requests, actions."""


from . import core, github  # noqa: E402, F401
