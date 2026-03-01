"""Docker observe — containers, images, compose ps, logs, stats."""

from __future__ import annotations

import json
import sys

import click

from . import docker, _resolve_project_root


@docker.command("containers")
@click.option("--running", is_flag=True, help="Only show running containers.")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def containers(ctx: click.Context, running: bool, as_json: bool) -> None:
    """List Docker containers."""
    from src.core.services.docker_ops import docker_containers

    project_root = _resolve_project_root(ctx)
    result = docker_containers(project_root, all_=not running)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("available"):
        click.secho(f"❌ {result.get('error', 'Docker not available')}", fg="red")
        sys.exit(1)

    items = result.get("containers", [])
    if not items:
        click.secho("No containers found.", fg="yellow")
        return

    click.secho(f"📦 Containers ({len(items)}):", fg="cyan", bold=True)
    for c in items:
        state = c.get("state", "")
        icon = "🟢" if state == "running" else "🔴" if state == "exited" else "⚪"
        click.echo(f"   {icon} {c['name']:<30} {c['image']}")
        click.echo(f"      Status: {c['status']}  Ports: {c.get('ports', '-')}")
    click.echo()


@docker.command("images")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def images(ctx: click.Context, as_json: bool) -> None:
    """List local Docker images."""
    from src.core.services.docker_ops import docker_images

    project_root = _resolve_project_root(ctx)
    result = docker_images(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("available"):
        click.secho(f"❌ {result.get('error', 'Docker not available')}", fg="red")
        sys.exit(1)

    items = result.get("images", [])
    if not items:
        click.secho("No images found.", fg="yellow")
        return

    click.secho(f"🖼️  Images ({len(items)}):", fg="cyan", bold=True)
    for img in items:
        repo = img.get("repository", "<none>")
        tag = img.get("tag", "latest")
        size = img.get("size", "?")
        click.echo(f"   {repo}:{tag}  ({size})")
    click.echo()


@docker.command("ps")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def compose_ps(ctx: click.Context, as_json: bool) -> None:
    """Show compose service status."""
    from src.core.services.docker_ops import docker_compose_status

    project_root = _resolve_project_root(ctx)
    result = docker_compose_status(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("available"):
        click.secho(f"❌ {result.get('error', 'Not available')}", fg="red")
        sys.exit(1)

    services = result.get("services", [])
    if not services:
        click.secho("No compose services running.", fg="yellow")
        return

    click.secho(f"🐳 Compose services ({len(services)}):", fg="cyan", bold=True)
    for svc in services:
        state = svc.get("state", "")
        icon = "🟢" if state == "running" else "🔴" if state == "exited" else "⚪"
        click.echo(f"   {icon} {svc['name']:<25} {svc.get('status', '')}")
    click.echo()


@docker.command("logs")
@click.argument("service")
@click.option("-n", "tail", default=100, type=int, help="Number of lines.")
@click.pass_context
def logs(ctx: click.Context, service: str, tail: int) -> None:
    """Show logs for a compose service."""
    from src.core.services.docker_ops import docker_logs

    project_root = _resolve_project_root(ctx)
    result = docker_logs(project_root, service, tail=tail)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"📜 Logs: {result.get('service', service)}", fg="cyan", bold=True)
    click.echo(result.get("logs", ""))


@docker.command("stats")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def stats(ctx: click.Context, as_json: bool) -> None:
    """Show container resource usage."""
    from src.core.services.docker_ops import docker_stats

    project_root = _resolve_project_root(ctx)
    result = docker_stats(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("available"):
        click.secho(f"❌ {result.get('error', 'Docker not available')}", fg="red")
        sys.exit(1)

    items = result.get("stats", [])
    if not items:
        click.secho("No running containers.", fg="yellow")
        return

    click.secho(f"📊 Resource usage ({len(items)}):", fg="cyan", bold=True)
    for s in items:
        click.echo(f"   {s['name']:<25} CPU: {s['cpu']}  Mem: {s['memory']}")
    click.echo()
