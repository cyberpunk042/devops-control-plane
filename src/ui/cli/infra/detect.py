"""Infra detect — combined environment + IaC status command."""

from __future__ import annotations

import json

import click

from . import infra, _resolve_project_root


@infra.command("status")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def infra_status(ctx: click.Context, as_json: bool) -> None:
    """Combined environment and IaC status."""
    from src.core.services.env_ops import infra_status as _status

    project_root = _resolve_project_root(ctx)
    result = _status(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    # Env section
    env_data = result.get("env", {})
    env_files = env_data.get("files", [])
    if env_files:
        click.secho("🔐 Environment:", fg="cyan", bold=True)
        for f in env_files:
            click.echo(f"   📄 {f['name']} ({f['var_count']} vars)")
    else:
        click.secho("🔐 Environment: no .env files", fg="yellow")

    click.echo()

    # IaC section
    iac_data = result.get("iac", {})
    providers = iac_data.get("providers", [])
    if providers:
        click.secho("🏗️  Infrastructure as Code:", fg="cyan", bold=True)
        for p in providers:
            cli_icon = "✅" if p["cli_available"] else "❌"
            click.echo(f"   {cli_icon} {p['name']}")
    else:
        click.secho("🏗️  Infrastructure as Code: none detected", fg="yellow")

    click.echo()
