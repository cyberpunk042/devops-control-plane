"""
CLI commands for Testing integration.

Thin wrappers over ``src.core.services.testing_ops``.

Sub-modules:
    detect.py   — testing status
    observe.py  — inventory, run, coverage
    generate.py — test template and coverage config generation
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


@click.group("testing")
def testing() -> None:
    """Testing — frameworks, coverage, inventory, and test generation."""


from . import detect, observe, generate  # noqa: E402, F401
