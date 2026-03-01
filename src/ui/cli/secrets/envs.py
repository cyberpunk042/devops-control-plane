"""Secrets environments — GitHub deployment environments subgroup."""

from __future__ import annotations

import json
import sys

import click

from . import secrets, _resolve_project_root


@secrets.group("envs")
def envs() -> None:
    """GitHub deployment environments — list, create, cleanup."""


@envs.command("list")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def envs_list(ctx: click.Context, as_json: bool) -> None:
    """List GitHub deployment environments."""
    from src.core.services.secrets_ops import list_environments

    project_root = _resolve_project_root(ctx)
    result = list_environments(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        if "error" in result:
            sys.exit(1)
        return

    if "error" in result:
        click.secho(f"✗ {result['error']}", fg="red")
        sys.exit(1)

    environments = result.get("environments", [])
    if not environments:
        click.echo("  No deployment environments found.")
        return

    click.secho(f"  🌍 Environments ({len(environments)}):", fg="cyan", bold=True)
    for env in environments:
        name = env if isinstance(env, str) else env.get("name", "?")
        click.echo(f"     • {name}")
    click.echo()


@envs.command("create")
@click.argument("name")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def envs_create(ctx: click.Context, name: str, as_json: bool) -> None:
    """Create a GitHub deployment environment."""
    from src.core.services.secrets_ops import create_environment

    project_root = _resolve_project_root(ctx)
    result = create_environment(project_root, name)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        if "error" in result:
            sys.exit(1)
        return

    if "error" in result:
        click.secho(f"✗ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"✓ Environment '{name}' created", fg="green")


@envs.command("cleanup")
@click.argument("name")
@click.option("--delete-files/--keep-files", default=True,
              help="Delete local .env.<name> files.")
@click.option("--delete-github/--keep-github", default=False,
              help="Also delete the GitHub environment.")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def envs_cleanup(ctx: click.Context, name: str,
                 delete_files: bool, delete_github: bool, as_json: bool) -> None:
    """Clean up an environment — delete local files and optionally GitHub env."""
    from src.core.services.secrets_ops import cleanup_environment

    project_root = _resolve_project_root(ctx)
    result = cleanup_environment(
        project_root, name,
        delete_files=delete_files,
        delete_github=delete_github,
    )

    if as_json:
        click.echo(json.dumps(result, indent=2))
        if "error" in result:
            sys.exit(1)
        return

    if "error" in result:
        click.secho(f"✗ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"✓ Environment '{name}' cleaned up", fg="green")
    for msg in result.get("actions", []):
        click.echo(f"  → {msg}")
