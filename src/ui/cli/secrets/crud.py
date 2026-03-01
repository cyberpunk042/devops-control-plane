"""Secrets CRUD — set, remove, list secrets on GitHub and .env."""

from __future__ import annotations

import json
import sys

import click

from . import secrets, _resolve_project_root


@secrets.command("set")
@click.argument("name")
@click.argument("value")
@click.option("--target", "-t", default="both",
              type=click.Choice(["local", "github", "both"]),
              help="Where to set the secret.")
@click.option("--env-name", "-e", default="", help="GitHub environment name.")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def set_secret_cmd(ctx: click.Context, name: str, value: str,
                   target: str, env_name: str, as_json: bool) -> None:
    """Set a secret in .env and/or GitHub.

    Examples:

        controlplane secrets set DATABASE_URL postgres://localhost/mydb

        controlplane secrets set API_KEY sk-1234 --target github --env-name production
    """
    from src.core.services.secrets_ops import set_secret

    project_root = _resolve_project_root(ctx)
    result = set_secret(
        project_root, name, value,
        target=target, env_name=env_name,
    )

    if as_json:
        click.echo(json.dumps(result, indent=2))
        if "error" in result:
            sys.exit(1)
        return

    if "error" in result:
        click.secho(f"✗ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"✓ {name} set", fg="green")
    if result.get("env_saved"):
        click.echo(f"  → Saved to .env")
    if result.get("github_set"):
        click.echo(f"  → Set on GitHub{f' ({env_name})' if env_name else ''}")


@secrets.command("remove")
@click.argument("name")
@click.option("--target", "-t", default="both",
              type=click.Choice(["local", "github", "both"]),
              help="Where to remove the secret.")
@click.option("--kind", "-k", default="secret",
              type=click.Choice(["secret", "variable"]),
              help="Secret or variable (for GitHub).")
@click.option("--env-name", "-e", default="", help="GitHub environment name.")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def remove_secret_cmd(ctx: click.Context, name: str,
                      target: str, kind: str, env_name: str, as_json: bool) -> None:
    """Remove a secret from .env and/or GitHub."""
    from src.core.services.secrets_ops import remove_secret

    project_root = _resolve_project_root(ctx)
    result = remove_secret(
        project_root, name,
        target=target, kind=kind, env_name=env_name,
    )

    if as_json:
        click.echo(json.dumps(result, indent=2))
        if "error" in result:
            sys.exit(1)
        return

    if "error" in result:
        click.secho(f"✗ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"✓ {name} removed", fg="green")


@secrets.command("list")
@click.option("--env-name", "-e", default="", help="GitHub environment name.")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def list_secrets_cmd(ctx: click.Context, env_name: str, as_json: bool) -> None:
    """List secrets and variables set on GitHub."""
    from src.core.services.secrets_ops import list_gh_secrets

    project_root = _resolve_project_root(ctx)
    result = list_gh_secrets(project_root, env_name=env_name)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        if "error" in result:
            sys.exit(1)
        return

    if "error" in result:
        click.secho(f"✗ {result['error']}", fg="red")
        sys.exit(1)

    gh_secrets = result.get("secrets", [])
    gh_vars = result.get("variables", [])
    scope = f" ({env_name})" if env_name else ""

    if gh_secrets:
        click.secho(f"  🔒 Secrets{scope} ({len(gh_secrets)}):", fg="cyan", bold=True)
        for s in gh_secrets:
            name = s if isinstance(s, str) else s.get("name", "?")
            click.echo(f"     • {name}")
    else:
        click.echo(f"  No secrets{scope}")

    if gh_vars:
        click.secho(f"  📋 Variables{scope} ({len(gh_vars)}):", fg="cyan", bold=True)
        for v in gh_vars:
            if isinstance(v, str):
                click.echo(f"     • {v}")
            else:
                click.echo(f"     • {v.get('name', '?')} = {v.get('value', '?')}")
    else:
        click.echo(f"  No variables{scope}")

    click.echo()
