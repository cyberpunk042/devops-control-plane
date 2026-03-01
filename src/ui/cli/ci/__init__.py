"""
CLI commands for CI/CD integration.

Thin wrappers over ``src.core.services.ci_ops``.
Complements the GitHub Actions runtime commands in ``git.py``
(gh runs, gh dispatch) with static CI analysis and generation.
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
def ci() -> None:
    """CI/CD — detect providers, audit workflows, generate configs."""


# ── Detect ──────────────────────────────────────────────────────


@ci.command()
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def status(ctx: click.Context, as_json: bool) -> None:
    """Show CI/CD integration status: detected providers, workflow count."""
    from src.core.services.ci_ops import ci_status

    project_root = _resolve_project_root(ctx)
    result = ci_status(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("has_ci"):
        click.secho("⚠️  No CI/CD configuration detected", fg="yellow")
        click.echo("   Run 'controlplane ci generate ci' to create one")
        return

    click.secho("⚙️  CI/CD Providers:", fg="cyan", bold=True)
    for p in result.get("providers", []):
        click.echo(f"   ✅ {p['name']} ({p['workflows']} workflow(s))")
    click.echo(f"\n   Total workflows: {result['total_workflows']}")
    click.echo()


# ── Observe ─────────────────────────────────────────────────────


@ci.command("workflows")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def workflows(ctx: click.Context, as_json: bool) -> None:
    """Parse and list all CI workflow files with analysis."""
    from src.core.services.ci_ops import ci_workflows

    project_root = _resolve_project_root(ctx)
    result = ci_workflows(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    wfs = result.get("workflows", [])
    if not wfs:
        click.secho("No CI workflows found.", fg="yellow")
        return

    for wf in wfs:
        provider_icon = {
            "github_actions": "🐙",
            "gitlab_ci": "🦊",
            "jenkins": "🏗️",
        }.get(wf["provider"], "⚙️")

        click.secho(f"\n{provider_icon} {wf['name']}", fg="cyan", bold=True)
        click.echo(f"   File: {wf['file']}")
        click.echo(f"   Triggers: {', '.join(wf['triggers']) or 'none'}")

        for job in wf.get("jobs", []):
            click.echo(f"   📋 {job['name']} ({job['steps_count']} steps, {job.get('runs_on', '?')})")

        issues = wf.get("issues", [])
        if issues:
            click.secho(f"   ⚠️  Issues ({len(issues)}):", fg="yellow")
            for issue in issues:
                click.echo(f"      • {issue}")

    click.echo()


@ci.command("coverage")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def coverage(ctx: click.Context, as_json: bool) -> None:
    """Analyze which modules have CI coverage."""
    from src.core.services.ci_ops import ci_coverage

    project_root = _resolve_project_root(ctx)

    # Load modules
    from src.core.config.loader import load_project
    from src.core.config.stack_loader import discover_stacks
    from src.core.services.detection import detect_modules

    project = load_project(project_root / "project.yml")
    stacks = discover_stacks(project_root / "stacks")
    detection = detect_modules(project, project_root, stacks)
    modules = [m.model_dump() for m in detection.modules]

    result = ci_coverage(project_root, modules)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    pct = result.get("coverage_pct", 0)
    pct_color = "green" if pct >= 80 else "yellow" if pct >= 50 else "red"

    click.secho(f"📊 CI Coverage: {pct}%", fg=pct_color, bold=True)
    click.echo()

    for name, detail in result.get("details", {}).items():
        icon = "✅" if detail["covered"] else "❌"
        click.echo(f"   {icon} {name:<25} {detail['reason']}")

    click.echo()


# ── Facilitate (generate) ───────────────────────────────────────


@ci.group("generate")
def generate() -> None:
    """Generate CI/CD workflow files from project context."""


@generate.command("ci")
@click.option("--write", is_flag=True, help="Write to disk (default: preview only).")
@click.pass_context
def gen_ci(ctx: click.Context, write: bool) -> None:
    """Generate a GitHub Actions CI workflow from detected stacks."""
    from src.core.services.ci_ops import generate_ci_workflow
    from src.core.services.docker_ops import write_generated_file

    project_root = _resolve_project_root(ctx)
    stack_names = _detect_stack_names(project_root)

    from src.core.config.loader import load_project

    project = load_project(project_root / "project.yml")
    result = generate_ci_workflow(project_root, stack_names, project_name=project.name)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    _handle_generated(project_root, result["file"], write)


@generate.command("lint")
@click.option("--write", is_flag=True, help="Write to disk (default: preview only).")
@click.pass_context
def gen_lint(ctx: click.Context, write: bool) -> None:
    """Generate a GitHub Actions lint workflow."""
    from src.core.services.ci_ops import generate_lint_workflow
    from src.core.services.docker_ops import write_generated_file

    project_root = _resolve_project_root(ctx)
    stack_names = _detect_stack_names(project_root)

    result = generate_lint_workflow(project_root, stack_names)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    _handle_generated(project_root, result["file"], write)


# ── Helpers ─────────────────────────────────────────────────────


def _detect_stack_names(project_root: Path) -> list[str]:
    """Load project and detect unique stack names."""
    from src.core.config.loader import load_project
    from src.core.config.stack_loader import discover_stacks
    from src.core.services.detection import detect_modules

    project = load_project(project_root / "project.yml")
    stacks = discover_stacks(project_root / "stacks")
    detection = detect_modules(project, project_root, stacks)

    seen: set[str] = set()
    names: list[str] = []
    for m in detection.modules:
        stack = m.effective_stack
        if stack and stack not in seen:
            names.append(stack)
            seen.add(stack)
    return names


def _handle_generated(project_root: Path, file_data: dict, write: bool) -> None:
    """Preview or write a generated file."""
    from src.core.services.docker_ops import write_generated_file

    if write:
        wr = write_generated_file(project_root, file_data)
        if "error" in wr:
            click.secho(f"❌ {wr['error']}", fg="red")
            sys.exit(1)
        click.secho(f"✅ Written: {wr['path']}", fg="green", bold=True)
    else:
        click.secho(f"📄 Preview: {file_data['path']}", fg="cyan", bold=True)
        if file_data.get("reason"):
            click.echo(f"   Reason: {file_data['reason']}")
        click.echo("─" * 60)
        click.echo(file_data["content"])
        click.echo("─" * 60)
        click.secho("   (use --write to save to disk)", fg="yellow")
