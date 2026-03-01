"""Terraform observe — validate, plan, state, workspaces commands."""

from __future__ import annotations

import json
import sys

import click

from . import terraform, _resolve_project_root


@terraform.command("validate")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def validate(ctx: click.Context, as_json: bool) -> None:
    """Validate Terraform configuration (syntax check)."""
    from src.core.services.terraform.ops import terraform_validate

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
    from src.core.services.terraform.ops import terraform_plan

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
    from src.core.services.terraform.ops import terraform_state

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
    from src.core.services.terraform.ops import terraform_workspaces

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
