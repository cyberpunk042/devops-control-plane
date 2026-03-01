"""Terraform detect — status command."""

from __future__ import annotations

import json

import click

from . import terraform, _resolve_project_root


@terraform.command("status")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def status(ctx: click.Context, as_json: bool) -> None:
    """Show Terraform configuration status."""
    from src.core.services.terraform.ops import terraform_status

    project_root = _resolve_project_root(ctx)
    result = terraform_status(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    cli = result.get("cli", {})
    click.secho("🏗️  Terraform Status:", fg="cyan", bold=True)
    click.echo()

    # CLI
    if cli.get("available"):
        click.secho(f"   🔧 CLI: {cli.get('version', '?')}", fg="green")
    else:
        click.secho("   🔧 CLI: not available", fg="yellow")

    if not result.get("has_terraform"):
        click.echo("\n   📁 No Terraform configuration found")
        click.secho(
            "\n   💡 Generate: controlplane terraform generate --provider aws",
            fg="yellow",
        )
        return

    # Root
    click.echo(f"   📁 Root: {result.get('root', '?')}/")
    click.echo(f"   📋 Initialized: {'✅' if result.get('initialized') else '❌'}")

    # Files
    files = result.get("files", [])
    if files:
        click.echo(f"\n   📄 Files ({len(files)}):")
        for f in files:
            click.echo(f"      {f['path']:<40} [{f['type']}]")

    # Providers
    providers = result.get("providers", [])
    if providers:
        click.echo(f"\n   🔌 Providers: {', '.join(providers)}")

    # Modules
    modules = result.get("modules", [])
    if modules:
        click.echo(f"\n   📦 Modules ({len(modules)}):")
        for m in modules:
            click.echo(f"      {m['name']:<30} → {m['source']}")

    # Resources
    resources = result.get("resources", [])
    if resources:
        click.echo(f"\n   🏗️  Resources ({len(resources)}):")
        for r in resources[:15]:
            click.echo(f"      {r['type']}.{r['name']:<35} [{r['file']}]")
        if len(resources) > 15:
            click.echo(f"      ... and {len(resources) - 15} more")

    # Backend
    backend = result.get("backend")
    if backend:
        click.echo(f"\n   💾 Backend: {backend['type']} ({backend['file']})")

    click.echo()
