"""
CLI commands for Terraform (Cloud/IaC) integration.

Thin wrappers over ``src.core.services.terraform_ops``.
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


@click.group("terraform")
def terraform() -> None:
    """Terraform — IaC status, validate, plan, state, and generation."""


# ── Detect ──────────────────────────────────────────────────────


@terraform.command("status")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def status(ctx: click.Context, as_json: bool) -> None:
    """Show Terraform configuration status."""
    from src.core.services.terraform_ops import terraform_status

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


# ── Observe ─────────────────────────────────────────────────────


@terraform.command("validate")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def validate(ctx: click.Context, as_json: bool) -> None:
    """Validate Terraform configuration (syntax check)."""
    from src.core.services.terraform_ops import terraform_validate

    project_root = _resolve_project_root(ctx)

    if not as_json:
        click.secho("🔍 Validating Terraform...", fg="cyan")

    result = terraform_validate(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    if result.get("valid"):
        click.secho("✅ Configuration is valid", fg="green", bold=True)
    else:
        click.secho("❌ Configuration has errors", fg="red", bold=True)

    for err in result.get("errors", []):
        sev = err.get("severity", "error")
        icon = "❌" if sev == "error" else "⚠️"
        color = "red" if sev == "error" else "yellow"
        click.secho(f"   {icon} [{sev}] {err['message']}", fg=color)
        if err.get("detail"):
            click.echo(f"      {err['detail']}")

    click.echo()


@terraform.command("plan")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def plan(ctx: click.Context, as_json: bool) -> None:
    """Run terraform plan (dry-run)."""
    from src.core.services.terraform_ops import terraform_plan

    project_root = _resolve_project_root(ctx)

    if not as_json:
        click.secho("📋 Running terraform plan...", fg="cyan")

    result = terraform_plan(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    changes = result.get("changes", {})
    add = changes.get("add", 0)
    change = changes.get("change", 0)
    destroy = changes.get("destroy", 0)

    total = add + change + destroy
    if total == 0:
        click.secho("✅ No changes. Infrastructure is up-to-date.", fg="green", bold=True)
    else:
        click.secho(f"📋 Plan: {add} to add, {change} to change, {destroy} to destroy", bold=True)
        if add > 0:
            click.secho(f"      ➕ {add} to add", fg="green")
        if change > 0:
            click.secho(f"      🔄 {change} to change", fg="yellow")
        if destroy > 0:
            click.secho(f"      🗑️  {destroy} to destroy", fg="red")

    click.echo()


@terraform.command("state")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def state(ctx: click.Context, as_json: bool) -> None:
    """List resources in terraform state."""
    from src.core.services.terraform_ops import terraform_state

    project_root = _resolve_project_root(ctx)
    result = terraform_state(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    resources = result.get("resources", [])
    if not resources:
        note = result.get("note", "No resources in state")
        click.secho(f"📋 {note}", fg="yellow")
        return

    click.secho(f"📋 State ({result['count']} resources):", fg="cyan", bold=True)
    for r in resources:
        prefix = f"[{r['module']}] " if r.get("module") else ""
        click.echo(f"   {prefix}{r['type']}.{r['name']}")

    click.echo()


@terraform.command("workspaces")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def workspaces(ctx: click.Context, as_json: bool) -> None:
    """List terraform workspaces."""
    from src.core.services.terraform_ops import terraform_workspaces

    project_root = _resolve_project_root(ctx)
    result = terraform_workspaces(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    current = result.get("current", "default")
    click.secho(f"🏗️  Workspaces (current: {current}):", fg="cyan", bold=True)
    for ws in result.get("workspaces", []):
        icon = "▶" if ws == current else " "
        click.echo(f"   {icon} {ws}")

    click.echo()


# ── Facilitate ──────────────────────────────────────────────────


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
    from src.core.services.terraform_ops import generate_terraform
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
