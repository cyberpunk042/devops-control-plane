"""Scripts history — show recent script runs from the ledger."""

from __future__ import annotations

import json

import click

from . import scripts, _resolve_project_root


@scripts.command("history")
@click.option("--script-id", "-s", default=None, help="Filter runs by script ID.")
@click.option("--last", "-n", "count", default=10, type=int, help="Number of runs to show (default: 10).")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def script_history(
    ctx: click.Context,
    script_id: str | None,
    count: int,
    as_json: bool,
) -> None:
    """Show recent script execution history.

    Examples:

        controlplane scripts history

        controlplane scripts history --script-id generators/class_diagrams --last 5
    """
    from src.core.services.run_tracker import load_runs

    project_root = _resolve_project_root(ctx)
    all_runs = load_runs(project_root, n=200)

    # Filter to script runs only
    script_runs = [r for r in all_runs if r.get("type") == "script"]

    # Filter by script ID if specified
    if script_id:
        script_runs = [
            r for r in script_runs
            if r.get("metadata", {}).get("script_id") == script_id
        ]

    # Limit count
    script_runs = script_runs[:count]

    if as_json:
        click.echo(json.dumps(script_runs, indent=2, default=str))
        return

    if not script_runs:
        click.secho("📭 No script runs found.", fg="yellow")
        if script_id:
            click.echo(f"   (filtered by: {script_id})")
        return

    click.secho(f"\n📋 Script History ({len(script_runs)} runs):\n", fg="cyan", bold=True)

    for run in script_runs:
        status = run.get("status", "unknown")
        status_icon = {"ok": "✅", "failed": "❌", "running": "🔄"}.get(status, "❓")

        sid = run.get("metadata", {}).get("script_id", run.get("subtype", "?"))
        run_id = run.get("run_id", "?")[:12]
        summary = run.get("summary", "")
        started = run.get("started_at", "?")
        duration = run.get("duration_ms", 0)
        exit_code = run.get("metadata", {}).get("exit_code", "?")

        click.echo(f"   {status_icon} {sid:<35} {run_id}  {started}")
        if ctx.obj.get("verbose"):
            click.echo(f"      Summary: {summary}")
            click.echo(f"      Duration: {duration}ms  Exit: {exit_code}")
            output_path = run.get("metadata", {}).get("output_path", "")
            if output_path:
                click.echo(f"      Output: {output_path}")

    click.echo()
