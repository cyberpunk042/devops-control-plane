"""
CLI commands for Secrets & GitHub integration.

Thin wrappers over ``src.core.services.secrets_ops``.

Sub-modules:
    status.py — gh status, auto-detect, key generation
    crud.py   — set, remove, list secrets
    envs.py   — GitHub deployment environments
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
def secrets() -> None:
    """Secrets management — GitHub CLI, environment variables, key generation."""


from . import status, crud, envs  # noqa: E402, F401
