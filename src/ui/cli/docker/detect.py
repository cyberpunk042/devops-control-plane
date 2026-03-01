"""Docker detect — status command."""

from __future__ import annotations

import json
import sys

import click

from . import docker, _resolve_project_root


@docker.command()
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def status(ctx: click.Context, as_json: bool) -> None:
    """Show Docker integration status: version, daemon, project files."""
    from src.core.services.docker_ops import docker_status

    project_root = _resolve_project_root(ctx)
    result = docker_status(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("available"):
        click.secho(f"❌ {result.get('error', 'Docker not available')}", fg="red")
        sys.exit(1)

    click.secho("🐳 Docker", fg="cyan", bold=True)
    click.echo(f"   Version:  {result.get('version', '?')}")
    daemon = "✅ running" if result.get("daemon_running") else "❌ stopped"
    click.echo(f"   Daemon:   {daemon}")
    compose = "✅ available" if result.get("compose_available") else "❌ not found"
    click.echo(f"   Compose:  {compose}")

    if result.get("compose_version"):
        click.echo(f"   Compose v: {result['compose_version']}")

    click.echo()

    # Project files
    dockerfiles = result.get("dockerfiles", [])
    if dockerfiles:
        click.secho(f"   📄 Dockerfiles ({len(dockerfiles)}):", fg="green")
        for f in dockerfiles:
            click.echo(f"      {f}")
    else:
        click.secho("   📄 No Dockerfiles found", fg="yellow")

    if result.get("has_compose"):
        click.secho(f"   📋 Compose: {result['compose_file']}", fg="green")
        services = result.get("compose_services", [])
        if services:
            click.echo(f"      Services: {', '.join(services)}")
    else:
        click.secho("   📋 No compose file found", fg="yellow")

    click.echo()
