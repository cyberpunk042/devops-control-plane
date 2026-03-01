"""Security generate — gitignore generation command."""

from __future__ import annotations

import sys

import click

from . import security, _resolve_project_root, _detect_stack_names


@security.group("generate")
def generate() -> None:
    """Generate security configuration files."""


@generate.command("gitignore")
@click.option("--write", is_flag=True, help="Write to disk (default: preview only).")
@click.pass_context
def gen_gitignore(ctx: click.Context, write: bool) -> None:
    """Generate .gitignore from detected stacks."""
    from src.core.services.security_ops import generate_gitignore
    from src.core.services.docker_ops import write_generated_file

    project_root = _resolve_project_root(ctx)
    stack_names = _detect_stack_names(project_root)

    if not stack_names:
        click.secho("⚠️  No stacks detected, generating minimal .gitignore", fg="yellow")
        stack_names = ["python"]  # fallback

    result = generate_gitignore(project_root, stack_names)

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
        if file_data.get("reason"):
            click.echo(f"   Reason: {file_data['reason']}")
        click.echo("─" * 60)
        click.echo(file_data["content"])
        click.echo("─" * 60)
        click.secho("   (use --write to save to disk)", fg="yellow")
