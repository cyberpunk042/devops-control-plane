"""Pages info — builders command."""

from __future__ import annotations

import json

import click

from . import pages


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
