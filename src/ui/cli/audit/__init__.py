"""
CLI commands for audit tooling — plan-based tool installation.

Thin wrappers over ``src.core.services.tool_install``.

Sub-modules:
    install.py — install a tool via plan
    plans.py   — list pending/paused plans
    resume.py  — resume a paused/failed plan
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
def audit() -> None:
    """Audit — tool installation, plans, and system detection."""


from . import install, plans, resume  # noqa: E402, F401
