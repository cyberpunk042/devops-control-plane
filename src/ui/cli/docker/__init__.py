"""
CLI commands for Docker & Compose integration.

Thin wrappers over ``src.core.services.docker_ops``.

Sub-modules:
    detect.py   — status
    observe.py  — containers, images, ps, logs, stats
    actions.py  — build, up, down, restart, prune
    generate.py — dockerfile, dockerignore, compose
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
def docker() -> None:
    """Docker & Compose — status, containers, images, build, up, down."""


from . import detect, observe, actions, generate  # noqa: E402, F401
