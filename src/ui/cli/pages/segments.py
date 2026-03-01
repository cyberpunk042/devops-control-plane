"""Pages segments — list, add, remove commands."""

from __future__ import annotations

import json
import sys

import click

from . import pages, _resolve_project_root


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
