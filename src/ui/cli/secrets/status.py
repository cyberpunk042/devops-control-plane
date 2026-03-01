"""Secrets status — gh CLI check, auto-detect, key generation."""

from __future__ import annotations

import json
import sys

import click

from . import secrets, _resolve_project_root


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
