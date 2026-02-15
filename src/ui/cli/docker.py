"""
CLI commands for Docker & Compose integration.

Thin wrappers over ``src.core.services.docker_ops``.
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
def docker() -> None:
    """Docker & Compose — status, containers, images, build, up, down."""


# ── Detect ──────────────────────────────────────────────────────


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


# ── Observe ─────────────────────────────────────────────────────


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


# ── Act ─────────────────────────────────────────────────────────


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


# ── Facilitate (generate) ───────────────────────────────────────


@docker.group("generate")
def generate() -> None:
    """Generate Docker config files from project context."""


@generate.command("dockerfile")
@click.argument("stack_name")
@click.option("--write", is_flag=True, help="Write to disk (default: preview only).")
@click.pass_context
def gen_dockerfile(ctx: click.Context, stack_name: str, write: bool) -> None:
    """Generate a Dockerfile for a stack (e.g. python, node, go)."""
    from src.core.services.docker_ops import generate_dockerfile, write_generated_file

    project_root = _resolve_project_root(ctx)
    result = generate_dockerfile(project_root, stack_name)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        if result.get("supported"):
            click.echo(f"   Supported: {', '.join(result['supported'])}")
        sys.exit(1)

    file_data = result["file"]

    if write:
        wr = write_generated_file(project_root, file_data)
        if "error" in wr:
            click.secho(f"❌ {wr['error']}", fg="red")
            sys.exit(1)
        click.secho(f"✅ Written: {wr['path']}", fg="green", bold=True)
    else:
        click.secho(f"📄 Preview: {file_data['path']}", fg="cyan", bold=True)
        click.echo(f"   Reason: {file_data['reason']}")
        click.echo("─" * 60)
        click.echo(file_data["content"])
        click.echo("─" * 60)
        click.secho("   (use --write to save to disk)", fg="yellow")


@generate.command("dockerignore")
@click.argument("stack_names", nargs=-1, required=True)
@click.option("--write", is_flag=True, help="Write to disk (default: preview only).")
@click.pass_context
def gen_dockerignore(ctx: click.Context, stack_names: tuple[str, ...], write: bool) -> None:
    """Generate a .dockerignore for given stacks."""
    from src.core.services.docker_ops import generate_dockerignore, write_generated_file

    project_root = _resolve_project_root(ctx)
    result = generate_dockerignore(project_root, list(stack_names))

    file_data = result["file"]

    if write:
        wr = write_generated_file(project_root, file_data)
        if "error" in wr:
            click.secho(f"❌ {wr['error']}", fg="red")
            sys.exit(1)
        click.secho(f"✅ Written: {wr['path']}", fg="green", bold=True)
    else:
        click.secho(f"📄 Preview: {file_data['path']}", fg="cyan", bold=True)
        click.echo("─" * 60)
        click.echo(file_data["content"])
        click.echo("─" * 60)
        click.secho("   (use --write to save to disk)", fg="yellow")


@generate.command("compose")
@click.option("--write", is_flag=True, help="Write to disk (default: preview only).")
@click.pass_context
def gen_compose(ctx: click.Context, write: bool) -> None:
    """Generate a docker-compose.yml from detected modules."""
    from src.core.services.docker_ops import generate_compose, write_generated_file

    project_root = _resolve_project_root(ctx)

    result = generate_compose(project_root)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    file_data = result["file"]

    if write:
        wr = write_generated_file(project_root, file_data)
        if "error" in wr:
            click.secho(f"❌ {wr['error']}", fg="red")
            sys.exit(1)
        click.secho(f"✅ Written: {wr['path']}", fg="green", bold=True)
    else:
        click.secho(f"📄 Preview: {file_data['path']}", fg="cyan", bold=True)
        click.echo("─" * 60)
        click.echo(file_data["content"])
        click.echo("─" * 60)
        click.secho("   (use --write to save to disk)", fg="yellow")

