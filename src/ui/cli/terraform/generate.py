"""Terraform generate — scaffolding generation command."""

from __future__ import annotations

import sys

import click

from . import terraform, _resolve_project_root


@terraform.command("generate")
@click.option("--provider", default="aws", help="Cloud provider (aws/google/azurerm/digitalocean).")
@click.option("--backend", default="local", help="Backend type (s3/gcs/azurerm/local).")
@click.option("--project-name", default="", help="Project name.")
@click.option("--write", is_flag=True, help="Write to disk.")
@click.pass_context
def generate(
    ctx: click.Context,
    provider: str,
    backend: str,
    project_name: str,
    write: bool,
) -> None:
    """Generate Terraform scaffolding (main, variables, outputs)."""
    from src.core.services.terraform.ops import generate_terraform
    from src.core.services.docker_ops import write_generated_file

    project_root = _resolve_project_root(ctx)

    result = generate_terraform(
        project_root,
        provider,
        backend=backend,
        project_name=project_name,
    )

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    for file_data in result["files"]:
        if write:
            wr = write_generated_file(project_root, file_data)
            if "error" in wr:
                click.secho(f"❌ {wr['error']}", fg="red")
            else:
                click.secho(f"✅ Written: {wr['path']}", fg="green")
        else:
            click.secho(f"\n📄 {file_data['path']}", fg="cyan", bold=True)
            click.echo(f"   {file_data.get('reason', '')}")
            click.echo("─" * 60)
            click.echo(file_data["content"])

    if not write:
        click.echo("─" * 60)
        click.secho("   (use --write to save files to disk)", fg="yellow")
