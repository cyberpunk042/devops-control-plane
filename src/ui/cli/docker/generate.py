"""Docker generate — dockerfile, dockerignore, compose."""

from __future__ import annotations

import sys

import click

from . import docker, _resolve_project_root


@docker.group("generate")
def generate() -> None:
    """Generate Docker config files from project context."""


@generate.command("dockerfile")
@click.argument("stack_name")
@click.option("--write", is_flag=True, help="Write to disk (default: preview only).")
@click.option("--base-image", default=None, help="Custom base image for the builder stage.")
@click.pass_context
def gen_dockerfile(ctx: click.Context, stack_name: str, write: bool, base_image: str | None) -> None:
    """Generate a Dockerfile for a stack (e.g. python, node, go)."""
    from src.core.services.docker_ops import generate_dockerfile, write_generated_file

    project_root = _resolve_project_root(ctx)
    result = generate_dockerfile(project_root, stack_name, base_image=base_image)

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
