"""Testing detect — status command."""

from __future__ import annotations

import json

import click

from . import testing, _resolve_project_root


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
