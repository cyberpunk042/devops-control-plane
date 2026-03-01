"""Audit install — install a tool via plan-based execution."""

from __future__ import annotations

import json
import sys

import click

from . import audit, _resolve_project_root


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
