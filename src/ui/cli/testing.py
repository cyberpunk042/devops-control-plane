"""
CLI commands for Testing integration.

Thin wrappers over ``src.core.services.testing_ops``.
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


@click.group("testing")
def testing() -> None:
    """Testing — frameworks, coverage, inventory, and test generation."""


# ── Detect ──────────────────────────────────────────────────────


@testing.command("status")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def status(ctx: click.Context, as_json: bool) -> None:
    """Show detected test frameworks, tools, and stats."""
    from src.core.services.testing_ops import testing_status

    project_root = _resolve_project_root(ctx)
    result = testing_status(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("has_tests"):
        click.secho("❌ No tests detected!", fg="red", bold=True)
        click.echo("   Generate test templates: controlplane testing generate template <module>")
        return

    click.secho("🧪 Testing Status:", fg="cyan", bold=True)
    click.echo()

    # Frameworks
    click.secho("   Frameworks:", fg="cyan")
    for fw in result.get("frameworks", []):
        detected_str = ", ".join(fw.get("detected_by", []))
        click.secho(f"      ✅ {fw['name']} ({fw['stack']})", fg="green")
        click.echo(f"         Detected by: {detected_str}")
        if fw.get("test_dir"):
            click.echo(f"         Test dir: {fw['test_dir']}/")

    # Coverage tools
    cov = result.get("coverage_tools", [])
    if cov:
        click.echo()
        click.secho("   Coverage tools:", fg="cyan")
        for c in cov:
            click.secho(f"      ✅ {c['name']} (config: {c['config']})", fg="green")

    # Stats
    stats = result.get("stats", {})
    click.echo()
    click.secho("   Statistics:", fg="cyan")
    click.echo(f"      Test files:     {stats.get('test_files', 0)}")
    click.echo(f"      Test functions: {stats.get('test_functions', 0)}")
    click.echo(f"      Test classes:   {stats.get('test_classes', 0)}")
    click.echo(f"      Source files:   {stats.get('source_files', 0)}")

    ratio = stats.get("test_ratio", 0)
    ratio_color = "green" if ratio >= 0.3 else "yellow" if ratio >= 0.1 else "red"
    click.secho(f"      Test/source:    {ratio:.0%}", fg=ratio_color)
    click.echo()


# ── Observe ─────────────────────────────────────────────────────


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


# ── Facilitate ──────────────────────────────────────────────────


@testing.group("generate")
def generate() -> None:
    """Generate test files and configs."""


@generate.command("template")
@click.argument("module_name")
@click.option("--stack", default="python", help="Stack for template (python/node/go).")
@click.option("--write", is_flag=True, help="Write to disk.")
@click.pass_context
def gen_template(ctx: click.Context, module_name: str, stack: str, write: bool) -> None:
    """Generate a test template for a module."""
    from src.core.services.testing_ops import generate_test_template
    from src.core.services.docker_ops import write_generated_file

    project_root = _resolve_project_root(ctx)
    result = generate_test_template(project_root, module_name, stack)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    file_data = result["file"]
    if write:
        wr = write_generated_file(project_root, file_data)
        if "error" in wr:
            click.secho(f"❌ {wr['error']}", fg="red")
            sys.exit(1)
        click.secho(f"✅ Written: {wr['path']}", fg="green", bold=True)
    else:
        click.secho(f"📄 Preview: {file_data['path']}", fg="cyan", bold=True)
        click.echo("─" * 60)
        click.echo(file_data["content"])
        click.echo("─" * 60)
        click.secho("   (use --write to save to disk)", fg="yellow")


@generate.command("coverage-config")
@click.option("--stack", default="python", help="Stack (python/node).")
@click.option("--write", is_flag=True, help="Write to disk.")
@click.pass_context
def gen_coverage(ctx: click.Context, stack: str, write: bool) -> None:
    """Generate coverage configuration."""
    from src.core.services.testing_ops import generate_coverage_config
    from src.core.services.docker_ops import write_generated_file

    project_root = _resolve_project_root(ctx)
    result = generate_coverage_config(project_root, stack)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    file_data = result["file"]
    if write:
        wr = write_generated_file(project_root, file_data)
        if "error" in wr:
            click.secho(f"❌ {wr['error']}", fg="red")
            sys.exit(1)
        click.secho(f"✅ Written: {wr['path']}", fg="green", bold=True)
    else:
        click.secho(f"📄 Preview: {file_data['path']}", fg="cyan", bold=True)
        click.echo("─" * 60)
        click.echo(file_data["content"])
        click.echo("─" * 60)
        click.secho("   (use --write to save to disk)", fg="yellow")
