"""Docker actions — build, up, down, restart, prune."""

from __future__ import annotations

import sys

import click

from . import docker, _resolve_project_root


@docker.command("build")
@click.option("--service", "-s", default=None, help="Specific service to build.")
@click.pass_context
def build(ctx: click.Context, service: str | None) -> None:
    """Build images via compose."""
    from src.core.services.docker_ops import docker_build

    project_root = _resolve_project_root(ctx)
    click.secho(f"🔨 Building {service or 'all services'}...", fg="cyan")

    result = docker_build(project_root, service=service)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"✅ Built: {result.get('service', 'all')}", fg="green", bold=True)
    if result.get("output"):
        click.echo(result["output"][-500:])  # last 500 chars


@docker.command("up")
@click.option("--service", "-s", default=None, help="Specific service to start.")
@click.pass_context
def up(ctx: click.Context, service: str | None) -> None:
    """Start compose services (detached)."""
    from src.core.services.docker_ops import docker_up

    project_root = _resolve_project_root(ctx)
    click.secho(f"🚀 Starting {service or 'all services'}...", fg="cyan")

    result = docker_up(project_root, service=service)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"✅ Started: {result.get('service', 'all')}", fg="green", bold=True)


@docker.command("down")
@click.option("--volumes", "-v", is_flag=True, help="Also remove named volumes.")
@click.pass_context
def down(ctx: click.Context, volumes: bool) -> None:
    """Stop and remove compose services."""
    from src.core.services.docker_ops import docker_down

    project_root = _resolve_project_root(ctx)
    click.secho("🛑 Stopping services...", fg="cyan")

    result = docker_down(project_root, volumes=volumes)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho("✅ Stopped", fg="green", bold=True)


@docker.command("restart")
@click.option("--service", "-s", default=None, help="Specific service to restart.")
@click.pass_context
def restart(ctx: click.Context, service: str | None) -> None:
    """Restart compose services."""
    from src.core.services.docker_ops import docker_restart

    project_root = _resolve_project_root(ctx)
    click.secho(f"🔄 Restarting {service or 'all services'}...", fg="cyan")

    result = docker_restart(project_root, service=service)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"✅ Restarted: {result.get('service', 'all')}", fg="green", bold=True)


@docker.command("prune")
@click.pass_context
def prune(ctx: click.Context) -> None:
    """Remove unused containers, images, and build cache."""
    from src.core.services.docker_ops import docker_prune

    project_root = _resolve_project_root(ctx)
    click.secho("🧹 Pruning unused Docker resources...", fg="cyan")

    result = docker_prune(project_root)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho("✅ Pruned", fg="green", bold=True)
    if result.get("output"):
        click.echo(result["output"])
