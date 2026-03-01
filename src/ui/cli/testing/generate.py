"""Testing generate — test template and coverage config generation."""

from __future__ import annotations

import sys

import click

from . import testing, _resolve_project_root


@testing.group("generate")
def generate() -> None:
    """Generate test files and configs."""


@generate.command("template")
@click.argument("module_name")
@click.option("--stack", default="python", help="Stack for template (python/node/go).")
@click.option("--write", is_flag=True, help="Write to disk.")
@click.pass_context
def gen_template(ctx: click.Context, module_name: str, stack: str, write: bool) -> None:
    """Generate a test template for a module."""
    from src.core.services.testing_ops import generate_test_template
    from src.core.services.docker_ops import write_generated_file

    project_root = _resolve_project_root(ctx)
    result = generate_test_template(project_root, module_name, stack)

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


@generate.command("coverage-config")
@click.option("--stack", default="python", help="Stack (python/node).")
@click.option("--write", is_flag=True, help="Write to disk.")
@click.pass_context
def gen_coverage(ctx: click.Context, stack: str, write: bool) -> None:
    """Generate coverage configuration."""
    from src.core.services.testing_ops import generate_coverage_config
    from src.core.services.docker_ops import write_generated_file

    project_root = _resolve_project_root(ctx)
    result = generate_coverage_config(project_root, stack)

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
