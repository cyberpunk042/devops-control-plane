"""
CLI commands for audit tooling — plan-based tool installation.

Thin wrappers over ``src.core.services.tool_install``.

Usage::

    controlplane audit install docker
    controlplane audit install pytorch --json
    controlplane audit install --list
    controlplane audit plans
    controlplane audit resume <plan-id>
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


@click.group()
def audit() -> None:
    """Audit — tool installation, plans, and system detection."""


# ── Install a tool via plan ────────────────────────────────────


@audit.command()
@click.argument("tool", required=False)
@click.option("--list", "list_tools", is_flag=True, help="List available tools.")
@click.option(
    "--sudo-password", envvar="SUDO_PASSWORD", default="",
    help="Password for sudo steps (can also set SUDO_PASSWORD env var).",
)
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.option("--dry-run", is_flag=True, help="Show the plan without executing.")
@click.pass_context
def install(
    ctx: click.Context,
    tool: str | None,
    list_tools: bool,
    sudo_password: str,
    as_json: bool,
    dry_run: bool,
) -> None:
    """Install a tool via plan-based execution.

    Examples::

        controlplane audit install docker
        controlplane audit install pytorch
        controlplane audit install --list
        controlplane audit install docker --dry-run
    """
    from src.core.services.audit.l0_detection import _detect_os
    from src.core.services.tool_install import (
        TOOL_RECIPES,
        execute_plan_step,
        resolve_install_plan,
        save_plan_state,
    )

    # ── List mode ──────────────────────────────────────────
    if list_tools or not tool:
        if as_json:
            tools_list = [
                {"id": k, "label": v.get("label", k), "category": v.get("category", "")}
                for k, v in TOOL_RECIPES.items()
            ]
            click.echo(json.dumps(tools_list, indent=2))
            return

        click.secho("\n🔧 Available tools:\n", fg="cyan", bold=True)
        # Group by category
        categories: dict[str, list[str]] = {}
        for k, v in TOOL_RECIPES.items():
            cat = v.get("category", "other")
            categories.setdefault(cat, []).append(
                f"{k:<25} {v.get('label', k)}"
            )
        for cat in sorted(categories):
            click.secho(f"   [{cat}]", fg="white", bold=True)
            for line in sorted(categories[cat]):
                click.echo(f"     {line}")
            click.echo()
        return

    # ── Single tool install ────────────────────────────────
    tool = tool.strip().lower()

    if tool not in TOOL_RECIPES:
        click.secho(f"❌ Unknown tool: {tool}", fg="red")
        click.echo("   Use 'controlplane audit install --list' to see available tools.")
        sys.exit(1)

    system_profile = _detect_os()
    plan = resolve_install_plan(tool, system_profile)

    if plan.get("error"):
        click.secho(f"❌ {plan['error']}", fg="red")
        sys.exit(1)

    if plan.get("already_installed"):
        click.secho(f"✅ {tool} is already installed", fg="green")
        return

    steps = plan.get("steps", [])

    # ── Dry run ────────────────────────────────────────────
    if dry_run:
        if as_json:
            click.echo(json.dumps(plan, indent=2, default=str))
            return

        click.secho(f"\n📋 Install plan for {tool}:", fg="cyan", bold=True)
        click.echo(f"   Steps: {len(steps)}")
        click.echo()
        for i, step in enumerate(steps):
            needs_sudo = step.get("sudo", False)
            sudo_marker = " 🔒" if needs_sudo else ""
            click.echo(
                f"   {i + 1}. [{step.get('type', '?')}] "
                f"{step.get('label', step.get('id', '?'))}{sudo_marker}"
            )
            if step.get("command"):
                cmd = step["command"]
                if isinstance(cmd, list):
                    cmd = " ".join(cmd)
                click.echo(f"      $ {cmd}")
        click.echo()
        return

    # ── Execute ────────────────────────────────────────────
    import uuid as _uuid_mod
    plan_id = str(_uuid_mod.uuid4())

    click.secho(f"\n⚡ Installing {tool}...\n", fg="cyan", bold=True)
    completed: list[int] = []
    failed = False

    for i, step in enumerate(steps):
        step_label = step.get("label", f"Step {i + 1}")
        click.echo(f"   [{i + 1}/{len(steps)}] {step_label}... ", nl=False)

        try:
            result = execute_plan_step(step, sudo_password=sudo_password)
        except Exception as exc:
            click.secho("CRASHED", fg="red", bold=True)
            click.echo(f"         {exc}")
            save_plan_state({
                "plan_id": plan_id, "tool": tool, "status": "failed",
                "current_step": i, "completed_steps": completed,
                "steps": [dict(s) for s in steps],
            })
            failed = True
            break

        if result.get("skipped"):
            click.secho("SKIP", fg="yellow")
            completed.append(i)
            continue

        if result.get("ok"):
            elapsed = result.get("elapsed_ms", "")
            timing = f" ({elapsed}ms)" if elapsed else ""
            click.secho(f"OK{timing}", fg="green")
            completed.append(i)
            save_plan_state({
                "plan_id": plan_id, "tool": tool, "status": "running",
                "current_step": i, "completed_steps": completed,
                "steps": [dict(s) for s in steps],
            })
        else:
            click.secho("FAILED", fg="red", bold=True)
            error = result.get("error", "Unknown error")
            click.echo(f"         {error}")
            if result.get("needs_sudo"):
                click.echo("         💡 Try: --sudo-password <password>")
            save_plan_state({
                "plan_id": plan_id, "tool": tool, "status": "failed",
                "current_step": i, "completed_steps": completed,
                "steps": [dict(s) for s in steps],
            })
            failed = True
            break

    click.echo()
    if failed:
        click.secho(f"❌ Installation failed at step {i + 1}", fg="red", bold=True)
        click.echo(f"   Plan ID: {plan_id}")
        click.echo(f"   Resume:  controlplane audit resume {plan_id}")
        sys.exit(1)
    else:
        save_plan_state({
            "plan_id": plan_id, "tool": tool, "status": "done",
            "completed_steps": completed,
            "steps": [dict(s) for s in steps],
        })
        click.secho(f"✅ {tool} installed successfully", fg="green", bold=True)


# ── List pending/paused plans ──────────────────────────────────


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


# ── Resume a plan ──────────────────────────────────────────────


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
