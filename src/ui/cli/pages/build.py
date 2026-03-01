"""Pages build — build, merge, deploy, ci, status commands."""

from __future__ import annotations

import json
import sys

import click

from . import pages, _resolve_project_root


@pages.command()
@click.argument("name")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def build(ctx: click.Context, name: str, as_json: bool) -> None:
    """Build a page segment."""
    from src.core.services.pages_engine import build_segment

    project_root = _resolve_project_root(ctx)

    click.echo(f"🔨 Building segment: {name}...")
    try:
        result = build_segment(project_root, name)

        if as_json:
            click.echo(json.dumps(result, indent=2, default=str))
            return

        if result.get("success"):
            click.secho(f"✅ Build succeeded: {name}", fg="green", bold=True)
            if result.get("output_dir"):
                click.echo(f"   Output: {result['output_dir']}")
            if result.get("duration"):
                click.echo(f"   Duration: {result['duration']:.1f}s")
        else:
            click.secho(f"❌ Build failed: {name}", fg="red", bold=True)
            if result.get("error"):
                click.echo(f"   Error: {result['error']}")
            sys.exit(1)
    except Exception as e:
        click.secho(f"❌ Build failed: {e}", fg="red")
        sys.exit(1)


@pages.command()
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def merge(ctx: click.Context, as_json: bool) -> None:
    """Merge all built segments into the final site output."""
    from src.core.services.pages_engine import merge_segments

    project_root = _resolve_project_root(ctx)

    try:
        result = merge_segments(project_root)
        if as_json:
            click.echo(json.dumps(result, indent=2, default=str))
        else:
            click.secho("✅ Segments merged", fg="green", bold=True)
            if result.get("output_dir"):
                click.echo(f"   Output: {result['output_dir']}")
    except Exception as e:
        click.secho(f"❌ Merge failed: {e}", fg="red")
        sys.exit(1)


@pages.command()
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def deploy(ctx: click.Context, as_json: bool) -> None:
    """Deploy merged site to GitHub Pages (gh-pages branch)."""
    from src.core.services.pages_engine import deploy_to_ghpages

    project_root = _resolve_project_root(ctx)

    click.echo("🚀 Deploying to GitHub Pages...")
    try:
        result = deploy_to_ghpages(project_root)
        if as_json:
            click.echo(json.dumps(result, indent=2, default=str))
        else:
            if result.get("success"):
                click.secho("✅ Deployed to gh-pages", fg="green", bold=True)
                if result.get("url"):
                    click.echo(f"   URL: {result['url']}")
            else:
                click.secho(f"❌ Deployment failed", fg="red", bold=True)
                if result.get("error"):
                    click.echo(f"   Error: {result['error']}")
                sys.exit(1)
    except Exception as e:
        click.secho(f"❌ Deployment failed: {e}", fg="red")
        sys.exit(1)


@pages.command("ci")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def generate_ci(ctx: click.Context, as_json: bool) -> None:
    """Generate a GitHub Actions CI workflow for Pages."""
    from src.core.services.pages_engine import generate_ci_workflow

    project_root = _resolve_project_root(ctx)

    try:
        result = generate_ci_workflow(project_root)
        if as_json:
            click.echo(json.dumps(result, indent=2, default=str))
        else:
            if result.get("path"):
                click.secho("✅ CI workflow generated", fg="green", bold=True)
                click.echo(f"   Path: {result['path']}")
            else:
                click.secho("ℹ️  No workflow changes needed", fg="yellow")
    except Exception as e:
        click.secho(f"❌ {e}", fg="red")
        sys.exit(1)


@pages.command("status")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def build_status(ctx: click.Context, as_json: bool) -> None:
    """Show build status for all segments."""
    from src.core.services.pages_engine import get_build_status

    project_root = _resolve_project_root(ctx)
    result = get_build_status(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    if not result:
        click.secho("No build history.", fg="yellow")
        return

    click.secho("📊 Build Status:", fg="cyan", bold=True)
    for name, status in result.items():
        state = status.get("state", "unknown")
        icons = {"built": "✅", "failed": "❌", "building": "⏳", "pending": "⬜"}
        icon = icons.get(state, "❓")
        click.echo(f"   {icon} {name}: {state}")
    click.echo()
