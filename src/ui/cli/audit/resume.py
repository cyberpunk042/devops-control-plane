"""Audit resume — resume a paused or failed installation plan."""

from __future__ import annotations

import json
import sys

import click

from . import audit


@audit.command()
@click.argument("plan_id")
@click.option(
    "--sudo-password", envvar="SUDO_PASSWORD", default="",
    help="Password for sudo steps.",
)
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def resume(
    ctx: click.Context,
    plan_id: str,
    sudo_password: str,
    as_json: bool,
) -> None:
    """Resume a paused or failed installation plan.

    Example::

        controlplane audit resume abc123-def456
    """
    from src.core.services.tool_install import (
        execute_plan_step,
        resume_plan,
        save_plan_state,
    )

    plan = resume_plan(plan_id)

    if plan.get("error"):
        if as_json:
            click.echo(json.dumps(plan, indent=2))
        else:
            click.secho(f"❌ {plan['error']}", fg="red")
        sys.exit(1)

    tool = plan.get("tool", "?")
    steps = plan.get("steps", [])
    completed_count = plan.get("completed_count", 0)
    original_total = plan.get("original_total", len(steps))

    if as_json:
        click.echo(json.dumps(plan, indent=2, default=str))
        return

    click.secho(
        f"\n⚡ Resuming {tool} ({completed_count}/{original_total} done)...\n",
        fg="cyan", bold=True,
    )

    completed: list[int] = list(range(completed_count))
    failed = False

    for i, step in enumerate(steps):
        step_label = step.get("label", f"Step {completed_count + i + 1}")
        click.echo(
            f"   [{completed_count + i + 1}/{original_total}] "
            f"{step_label}... ",
            nl=False,
        )

        try:
            result = execute_plan_step(step, sudo_password=sudo_password)
        except Exception as exc:
            click.secho("CRASHED", fg="red", bold=True)
            click.echo(f"         {exc}")
            failed = True
            break

        if result.get("skipped"):
            click.secho("SKIP", fg="yellow")
            completed.append(completed_count + i)
            continue

        if result.get("ok"):
            elapsed = result.get("elapsed_ms", "")
            timing = f" ({elapsed}ms)" if elapsed else ""
            click.secho(f"OK{timing}", fg="green")
            completed.append(completed_count + i)
            save_plan_state({
                "plan_id": plan_id, "tool": tool, "status": "running",
                "current_step": completed_count + i,
                "completed_steps": completed,
                "steps": steps,
            })
        else:
            click.secho("FAILED", fg="red", bold=True)
            click.echo(f"         {result.get('error', 'Unknown error')}")
            save_plan_state({
                "plan_id": plan_id, "tool": tool, "status": "failed",
                "current_step": completed_count + i,
                "completed_steps": completed,
                "steps": steps,
            })
            failed = True
            break

    click.echo()
    if failed:
        click.secho("❌ Resume failed", fg="red", bold=True)
        click.echo(f"   Plan ID: {plan_id}")
        sys.exit(1)
    else:
        save_plan_state({
            "plan_id": plan_id, "tool": tool, "status": "done",
            "completed_steps": completed,
            "steps": steps,
        })
        click.secho(f"✅ {tool} installation resumed and completed", fg="green", bold=True)
