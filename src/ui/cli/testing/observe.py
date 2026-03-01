"""Testing observe — inventory, run, coverage commands."""

from __future__ import annotations

import json
import sys

import click

from . import testing, _resolve_project_root


@testing.command("inventory")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def inventory(ctx: click.Context, as_json: bool) -> None:
    """List all test files with function counts."""
    from src.core.services.testing_ops import test_inventory

    project_root = _resolve_project_root(ctx)
    result = test_inventory(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    files = result.get("files", [])
    if not files:
        click.secho("❌ No test files found", fg="red")
        return

    click.secho(
        f"📋 Test Inventory ({result['total_files']} files, "
        f"{result['total_functions']} functions):",
        fg="cyan",
        bold=True,
    )
    click.echo()

    for f in files:
        funcs = f["functions"]
        icon = "🧪" if funcs > 0 else "📄"
        click.echo(
            f"   {icon} {f['path']:<45} "
            f"{funcs:>3} tests  {f['lines']:>4} lines  [{f['framework']}]"
        )

    click.echo()


@testing.command("run")
@click.option("--file", "file_path", default=None, help="Run specific test file.")
@click.option("-k", "keyword", default=None, help="Run tests matching keyword.")
@click.option("-v", "verbose", is_flag=True, help="Verbose output.")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def run_tests(
    ctx: click.Context,
    file_path: str | None,
    keyword: str | None,
    verbose: bool,
    as_json: bool,
) -> None:
    """Run tests with structured result output."""
    from src.core.services.testing_ops import run_tests as _run_tests

    project_root = _resolve_project_root(ctx)

    if not as_json:
        click.secho("🧪 Running tests...", fg="cyan")

    result = _run_tests(
        project_root,
        verbose=verbose,
        file_path=file_path,
        keyword=keyword,
    )

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    # Summary
    ok = result.get("ok", False)
    passed = result.get("passed", 0)
    failed = result.get("failed", 0)
    errors = result.get("errors", 0)
    skipped = result.get("skipped", 0)
    duration = result.get("duration_seconds", 0)

    if ok:
        click.secho(
            f"✅ {passed} passed in {duration:.1f}s",
            fg="green",
            bold=True,
        )
    else:
        click.secho(
            f"❌ {failed} failed, {errors} error(s), {passed} passed in {duration:.1f}s",
            fg="red",
            bold=True,
        )
        if skipped > 0:
            click.echo(f"   Skipped: {skipped}")

        failures = result.get("failures", [])
        if failures:
            click.echo()
            click.secho("   Failures:", fg="red")
            for f in failures[:10]:
                click.echo(f"      ❌ {f['name']}")

        sys.exit(1)


@testing.command("coverage")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def coverage(ctx: click.Context, as_json: bool) -> None:
    """Run tests with coverage and show report."""
    from src.core.services.testing_ops import test_coverage

    project_root = _resolve_project_root(ctx)

    if not as_json:
        click.secho("📊 Running coverage...", fg="cyan")

    result = test_coverage(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("ok"):
        click.secho("❌ Coverage analysis failed", fg="red")
        click.echo(f"   {result.get('output', '')}")
        return

    pct = result.get("coverage_percent")
    if pct is not None:
        color = "green" if pct >= 80 else "yellow" if pct >= 60 else "red"
        click.secho(
            f"📊 Coverage: {pct:.0f}% (tool: {result.get('tool', '?')})",
            fg=color,
            bold=True,
        )

        # Show per-file coverage (lowest coverage first)
        files = sorted(result.get("files", []), key=lambda x: x.get("cover", 100))
        if files:
            click.echo()
            click.secho("   Lowest coverage:", fg="yellow")
            for f in files[:10]:
                cover = f.get("cover", 0)
                fc = "green" if cover >= 80 else "yellow" if cover >= 60 else "red"
                click.secho(
                    f"      {f['name']:<45} {cover:>3}% ({f['miss']} uncovered)",
                    fg=fc,
                )
    else:
        click.echo(result.get("output", "No data"))

    click.echo()
