"""Scripts run — execute a script with parameters."""

from __future__ import annotations

import sys

import click

from . import scripts, _resolve_project_root


@scripts.command("run")
@click.argument("script_id")
@click.option("--param", "-p", "params", multiple=True, help="Parameters as KEY=VALUE pairs.")
@click.option("--output", "-o", default=None, help="Output directory override.")
@click.option("--dry-run", is_flag=True, help="Show what would be executed without running.")
@click.pass_context
def run_script(
    ctx: click.Context,
    script_id: str,
    params: tuple[str, ...],
    output: str | None,
    dry_run: bool,
) -> None:
    """Run a script by ID with optional parameters.

    Examples:

        controlplane scripts run generators/class_diagrams

        controlplane scripts run generators/class_diagrams -p scope=core.services.vault

        controlplane scripts run generators/class_diagrams --dry-run
    """
    from src.core.services.scripts.registry import get_script

    project_root = _resolve_project_root(ctx)

    # Parse KEY=VALUE params
    param_dict: dict[str, str] = {}
    for p in params:
        if "=" not in p:
            click.secho(f"❌ Invalid param format: {p!r} (expected KEY=VALUE)", fg="red")
            sys.exit(1)
        key, _, value = p.partition("=")
        param_dict[key.strip()] = value.strip()

    # Resolve script first for dry-run display
    meta = get_script(project_root, script_id)
    if meta is None:
        click.secho(f"❌ Script '{script_id}' not found.", fg="red")
        click.echo("   Use 'controlplane scripts list' to see available scripts.")
        sys.exit(1)

    if dry_run:
        click.secho(f"\n🧪 Dry run — {meta.name}\n", fg="cyan", bold=True)
        click.echo(f"   Script:    {script_id}")
        click.echo(f"   Language:  {meta.language}")
        click.echo(f"   Mode:      {meta.mode}")
        click.echo(f"   Timeout:   {meta.timeout}s")
        if param_dict:
            click.echo(f"   Params:    {param_dict}")
        if output:
            click.echo(f"   Output:    {output}")
        click.echo("\n   Would execute — no changes made.")
        return

    # Execute
    click.secho(f"\n▶ Running: {meta.name}...\n", fg="cyan", bold=True)

    from src.core.services.scripts.executor import execute_script

    result = execute_script(
        project_root,
        script_id,
        params=param_dict,
        output_target=output,
    )

    # Stream lines to terminal
    for line in result.get("lines", []):
        click.echo(f"   {line}")

    # Result summary
    click.echo()
    if result["ok"]:
        duration = result.get("duration_ms", 0)
        click.secho(
            f"✅ Completed in {duration}ms — exit code {result['exit_code']}",
            fg="green", bold=True,
        )
        if result.get("output_path"):
            click.echo(f"   Output: {result['output_path']}")
        click.echo(f"   Run ID: {result['run_id']}")
    else:
        click.secho(f"❌ Failed — {result.get('error', 'unknown error')}", fg="red")
        if result.get("exit_code", -1) >= 0:
            click.echo(f"   Exit code: {result['exit_code']}")
        sys.exit(1)

    click.echo()
