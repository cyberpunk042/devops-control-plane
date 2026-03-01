"""
CLI commands for Environment & IaC integration.

Thin wrappers over ``src.core.services.env_ops``.

Sub-modules:
    env.py    — .env file management subgroup
    iac.py    — IaC detection subgroup
    detect.py — combined infra status
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
def infra() -> None:
    """Infra — environment variables, IaC detection, config generation."""


def _handle_generated(project_root: Path, file_data: dict, write: bool) -> None:
    """Preview or write a generated file."""
    from src.core.services.docker_ops import write_generated_file

    if write:
        wr = write_generated_file(project_root, file_data)
        if "error" in wr:
            click.secho(f"❌ {wr['error']}", fg="red")
            sys.exit(1)
        click.secho(f"✅ Written: {wr['path']}", fg="green", bold=True)
    else:
        click.secho(f"📄 Preview: {file_data['path']}", fg="cyan", bold=True)
        if file_data.get("reason"):
            click.echo(f"   Reason: {file_data['reason']}")
        click.echo("─" * 60)
        click.echo(file_data["content"])
        click.echo("─" * 60)
        click.secho("   (use --write to save to disk)", fg="yellow")


from . import env, iac, detect  # noqa: E402, F401
