"""Audit plans — list pending/paused installation plans."""

from __future__ import annotations

import json

import click

from . import audit


@audit.command("plans")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def list_plans(ctx: click.Context, as_json: bool) -> None:
    """Show pending, paused, or failed installation plans."""
    from src.core.services.tool_install import list_pending_plans

    pending = list_pending_plans()

    if as_json:
        click.echo(json.dumps(pending, indent=2, default=str))
        return

    if not pending:
        click.secho("✅ No pending plans", fg="green")
        return

    click.secho(f"\n📋 Pending plans ({len(pending)}):\n", fg="cyan", bold=True)
    for p in pending:
        status_icon = {"paused": "⏸️", "running": "🔄", "failed": "❌"}.get(
            p.get("status", ""), "❓"
        )
        tool = p.get("tool", "?")
        plan_id = p.get("plan_id", "?")
        completed = len(p.get("completed_steps", []))
        total = len(p.get("steps", []))
        click.echo(f"   {status_icon} {tool:<20} [{completed}/{total}] {plan_id}")
    click.echo()
