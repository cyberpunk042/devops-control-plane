"""Infra iac subgroup — IaC detection and resource inventory."""

from __future__ import annotations

import json

import click

from . import infra, _resolve_project_root


@infra.group("iac")
def iac() -> None:
    """Infrastructure as Code detection and analysis."""


@iac.command("status")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def iac_status(ctx: click.Context, as_json: bool) -> None:
    """Detect IaC tools and configurations."""
    from src.core.services.env_ops import iac_status as _status

    project_root = _resolve_project_root(ctx)
    result = _status(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("has_iac"):
        click.secho("⚠️  No IaC configurations detected", fg="yellow")
        return

    click.secho("🏗️  IaC Providers:", fg="cyan", bold=True)
    for p in result.get("providers", []):
        cli_icon = "✅" if p["cli_available"] else "❌"
        click.echo(f"   {cli_icon} {p['name']} ({p['cli'] or 'n/a'})")
        if p.get("dirs_found"):
            click.echo(f"      Dirs: {', '.join(p['dirs_found'])}")
        if p.get("files_found"):
            click.echo(f"      Files: {len(p['files_found'])} found")
    click.echo()


@iac.command("resources")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def iac_resources(ctx: click.Context, as_json: bool) -> None:
    """Inventory IaC resources from detected configurations."""
    from src.core.services.env_ops import iac_resources as _resources

    project_root = _resolve_project_root(ctx)
    result = _resources(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    resources = result.get("resources", [])
    if not resources:
        click.secho("No IaC resources found", fg="yellow")
        return

    click.secho(f"📋 IaC Resources ({result.get('count', 0)}):", fg="cyan", bold=True)
    for r in resources:
        click.echo(f"   [{r['provider']}] {r['type']}/{r['name']}")
        click.echo(f"            File: {r['file']}")
    click.echo()
