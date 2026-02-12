"""
CLI commands for Secrets & GitHub integration.

Thin wrappers over ``src.core.services.secrets_ops``.
"""

from __future__ import annotations

import json
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
def secrets() -> None:
    """Secrets management — GitHub CLI, environment variables, key generation."""


# ── gh CLI status ───────────────────────────────────────────────


@secrets.command()
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def status(ctx: click.Context, as_json: bool) -> None:
    """Check gh CLI installation and authentication status."""
    from src.core.services.secrets_ops import gh_status

    result = gh_status()

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    installed = result.get("installed", False)
    authenticated = result.get("authenticated", False)

    if not installed:
        click.secho("✗ gh CLI not installed", fg="red")
        click.echo("  Install: https://cli.github.com/")
        sys.exit(1)

    version = result.get("version", "?")
    click.echo(f"  gh CLI: {version}")

    if authenticated:
        click.secho("  ✓ Authenticated", fg="green")
    else:
        click.secho("  ✗ Not authenticated", fg="red")
        click.echo("  Run: gh auth login")
        sys.exit(1)


@secrets.command("auto-detect")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def auto_detect(ctx: click.Context, as_json: bool) -> None:
    """Auto-detect GitHub token and repository from environment."""
    from src.core.services.secrets_ops import gh_auto_detect

    project_root = _resolve_project_root(ctx)
    result = gh_auto_detect(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if "error" in result:
        click.secho(f"✗ {result['error']}", fg="red")
        sys.exit(1)

    if result.get("token"):
        click.secho("  ✓ GitHub token detected", fg="green")
    if result.get("repo"):
        click.echo(f"  Repository: {result['repo']}")
    if result.get("saved"):
        for key in result["saved"]:
            click.echo(f"  → Saved {key} to .env")


# ── Key generation ──────────────────────────────────────────────


@secrets.command()
@click.option("--type", "gen_type", default="password",
              type=click.Choice(["password", "token",
                                 "ssh-ed25519", "ssh-rsa", "cert-selfsigned"]),
              help="Type of key to generate.")
@click.option("--length", "-l", default=32, help="Length (passwords/tokens).")
@click.option("--cn", default="localhost", help="Common Name (certificates).")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
def generate(gen_type: str, length: int, cn: str, as_json: bool) -> None:
    """Generate a secret value (password, token, SSH key, certificate)."""
    from src.core.services.secrets_ops import generate_key

    result = generate_key(gen_type=gen_type, length=length, cn=cn)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        if "error" in result:
            sys.exit(1)
        return

    if "error" in result:
        click.secho(f"✗ {result['error']}", fg="red")
        sys.exit(1)

    value = result.get("value", "")
    click.secho(f"  Generated ({gen_type}):", fg="cyan", bold=True)

    if gen_type in ("ssh-ed25519", "ssh-rsa"):
        click.echo(f"\n  Private key (base64):\n{value[:80]}...")
        pub = result.get("public_value", "")
        if pub:
            click.echo(f"\n  Public key:\n{pub[:80]}...")
    elif gen_type == "cert-selfsigned":
        click.echo(f"\n  Certificate (base64):\n{value[:80]}...")
        pkey = result.get("private_key", "")
        if pkey:
            click.echo(f"\n  Private key (base64):\n{pkey[:80]}...")
    else:
        click.echo(f"  {value}")


# ── Secret CRUD ─────────────────────────────────────────────────


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


# ── GitHub Environments ─────────────────────────────────────────


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
