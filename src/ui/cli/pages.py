"""
CLI commands for GitHub Pages deployment.

Thin wrappers over ``src.core.services.pages_engine``
and ``src.core.services.pages_builders``.
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
def pages() -> None:
    """GitHub Pages — build, deploy, and manage page segments."""


# ── Segments ────────────────────────────────────────────────────

@pages.command("list")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def list_segments(ctx: click.Context, as_json: bool) -> None:
    """List all configured page segments."""
    from src.core.services.pages_engine import get_segments

    project_root = _resolve_project_root(ctx)
    segments = get_segments(project_root)

    if as_json:
        click.echo(json.dumps(segments, indent=2, default=str))
        return

    if not segments:
        click.secho("No page segments configured.", fg="yellow")
        click.echo("   Use 'pages add' to create one.")
        return

    click.secho(f"📄 Page segments ({len(segments)}):", fg="cyan", bold=True)
    for seg in segments:
        name = seg.get("name", "?")
        builder = seg.get("builder", "?")
        source = seg.get("source_dir", "?")
        click.echo(f"   • {name} [{builder}] → {source}")
    click.echo()


@pages.command()
@click.argument("name")
@click.option("--builder", "-b", required=True, help="Builder type (docusaurus, mkdocs, hugo, etc.).")
@click.option("--source", "-s", required=True, type=click.Path(), help="Source directory.")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output directory.")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def add(ctx: click.Context, name: str, builder: str, source: str, output: str | None, as_json: bool) -> None:
    """Add a new page segment."""
    from src.core.services.pages_engine import add_segment

    project_root = _resolve_project_root(ctx)

    try:
        result = add_segment(
            project_root,
            name=name,
            builder=builder,
            source_dir=source,
            output_dir=output,
        )
        if as_json:
            click.echo(json.dumps(result, indent=2, default=str))
        else:
            click.secho(f"✅ Added segment: {name}", fg="green", bold=True)
            click.echo(f"   Builder: {builder}")
            click.echo(f"   Source: {source}")
    except Exception as e:
        click.secho(f"❌ {e}", fg="red")
        sys.exit(1)


@pages.command()
@click.argument("name")
@click.pass_context
def remove(ctx: click.Context, name: str) -> None:
    """Remove a page segment."""
    from src.core.services.pages_engine import remove_segment

    project_root = _resolve_project_root(ctx)

    try:
        result = remove_segment(project_root, name)
        click.secho(f"✅ Removed segment: {name}", fg="green")
    except Exception as e:
        click.secho(f"❌ {e}", fg="red")
        sys.exit(1)


# ── Building ────────────────────────────────────────────────────

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


# ── Deployment ──────────────────────────────────────────────────

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


# ── CI ──────────────────────────────────────────────────────────

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


# ── Info ────────────────────────────────────────────────────────

@pages.command()
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def builders(ctx: click.Context, as_json: bool) -> None:
    """List available page builders."""
    from src.core.services.pages_builders import list_builders

    available = list_builders()

    if as_json:
        click.echo(json.dumps(
            [{"name": b.name, "label": b.label, "available": b.available,
              "description": b.description} for b in available],
            indent=2,
        ))
        return

    click.secho(f"🔧 Available builders ({len(available)}):", fg="cyan", bold=True)
    for b in available:
        avail = "✓" if b.available else "✗"
        click.echo(f"   {avail} {b.name:12s} — {b.label}")
        if b.description:
            click.echo(f"     {b.description}")
    click.echo()


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
