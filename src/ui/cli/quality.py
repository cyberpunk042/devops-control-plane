"""
CLI commands for Code Quality integration.

Thin wrappers over ``src.core.services.quality_ops``.
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


@click.group()
def quality() -> None:
    """Quality — lint, typecheck, test, format, and config generation."""


# ── Detect ──────────────────────────────────────────────────────


@quality.command()
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def status(ctx: click.Context, as_json: bool) -> None:
    """Show detected quality tools and their availability."""
    from src.core.services.quality_ops import quality_status

    project_root = _resolve_project_root(ctx)
    stack_names = _detect_stack_names(project_root)
    result = quality_status(project_root, stack_names=stack_names)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("has_quality"):
        click.secho("⚠️  No quality tools detected", fg="yellow")
        return

    click.secho("🔍 Quality Tools:", fg="cyan", bold=True)

    # Group by category
    by_cat: dict[str, list[dict]] = {}
    for t in result.get("tools", []):
        cat = t["category"]
        by_cat.setdefault(cat, []).append(t)

    cat_icons = {"lint": "🔎", "typecheck": "📐", "test": "🧪", "format": "✨"}
    for cat in ("lint", "typecheck", "test", "format"):
        tools = by_cat.get(cat, [])
        if not tools:
            continue
        icon = cat_icons.get(cat, "⚙️")
        click.echo(f"\n   {icon} {cat.title()}:")
        for t in tools:
            cli_icon = "✅" if t["cli_available"] else "❌"
            cfg_note = f" ({t['config_file']})" if t["config_found"] else ""
            click.echo(f"      {cli_icon} {t['name']}{cfg_note}")

    click.echo()


# ── Run ─────────────────────────────────────────────────────────


@quality.command("check")
@click.option("--tool", "-t", default=None, help="Specific tool (e.g. ruff, mypy, pytest).")
@click.option("--category", "-c", default=None, type=click.Choice(["lint", "typecheck", "test", "format"]))
@click.option("--fix", is_flag=True, help="Auto-fix where supported.")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def check(ctx: click.Context, tool: str | None, category: str | None, fix: bool, as_json: bool) -> None:
    """Run quality checks (all, by category, or specific tool)."""
    from src.core.services.quality_ops import quality_run

    project_root = _resolve_project_root(ctx)
    result = quality_run(project_root, tool=tool, category=category, fix=fix)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        if result.get("available"):
            click.echo(f"   Available: {', '.join(result['available'])}")
        sys.exit(1)

    results = result.get("results", [])
    if not results:
        click.secho("No quality tools available to run", fg="yellow")
        return

    for r in results:
        icon = "✅" if r["passed"] else "❌"
        click.secho(f"{icon} {r['name']} ({r['category']})", fg="green" if r["passed"] else "red")

        if not r["passed"]:
            # Show output on failure
            output = r.get("stdout", "") or r.get("stderr", "")
            if output:
                for line in output.splitlines()[:15]:
                    click.echo(f"   {line}")
                lines = output.splitlines()
                if len(lines) > 15:
                    click.echo(f"   ... ({len(lines) - 15} more lines)")

            if r.get("fixable"):
                click.secho(f"   💡 Auto-fixable: run with --fix", fg="yellow")

    click.echo()
    passed = result.get("passed", 0)
    total = result.get("total", 0)
    color = "green" if result.get("all_passed") else "red"
    click.secho(f"{'✅' if result.get('all_passed') else '❌'} {passed}/{total} passed", fg=color, bold=True)


@quality.command("lint")
@click.option("--fix", is_flag=True, help="Auto-fix lint issues.")
@click.pass_context
def lint(ctx: click.Context, fix: bool) -> None:
    """Run linters only."""
    ctx.invoke(check, category="lint", fix=fix, tool=None, as_json=False)


@quality.command("typecheck")
@click.pass_context
def typecheck(ctx: click.Context) -> None:
    """Run type-checkers only."""
    ctx.invoke(check, category="typecheck", fix=False, tool=None, as_json=False)


@quality.command("test")
@click.pass_context
def test(ctx: click.Context) -> None:
    """Run tests only."""
    ctx.invoke(check, category="test", fix=False, tool=None, as_json=False)


@quality.command("format")
@click.option("--fix", is_flag=True, help="Apply formatting.")
@click.pass_context
def fmt(ctx: click.Context, fix: bool) -> None:
    """Check formatting (or apply with --fix)."""
    ctx.invoke(check, category="format", fix=fix, tool=None, as_json=False)


# ── Facilitate ──────────────────────────────────────────────────


@quality.group("generate")
def generate() -> None:
    """Generate quality tool configuration files."""


@generate.command("config")
@click.argument("stack_name")
@click.option("--write", is_flag=True, help="Write to disk (default: preview only).")
@click.pass_context
def gen_config(ctx: click.Context, stack_name: str, write: bool) -> None:
    """Generate quality configs for a stack (e.g. python, node)."""
    from src.core.services.quality_ops import generate_quality_config
    from src.core.services.docker_ops import write_generated_file

    project_root = _resolve_project_root(ctx)
    result = generate_quality_config(project_root, stack_name)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    for file_data in result.get("files", []):
        if write:
            wr = write_generated_file(project_root, file_data)
            if "error" in wr:
                click.secho(f"❌ {wr['error']}", fg="red")
            else:
                click.secho(f"✅ Written: {wr['path']}", fg="green", bold=True)
        else:
            click.secho(f"\n📄 Preview: {file_data['path']}", fg="cyan", bold=True)
            if file_data.get("reason"):
                click.echo(f"   Reason: {file_data['reason']}")
            click.echo("─" * 60)
            click.echo(file_data["content"])
            click.echo("─" * 60)

    if not write:
        click.secho("\n   (use --write to save to disk)", fg="yellow")
