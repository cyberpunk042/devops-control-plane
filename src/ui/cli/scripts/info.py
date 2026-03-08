"""Scripts info — show detailed metadata for a script."""

from __future__ import annotations

import json
import sys

import click

from . import scripts, _resolve_project_root


@scripts.command("info")
@click.argument("script_id")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def script_info(ctx: click.Context, script_id: str, as_json: bool) -> None:
    """Show full metadata and parameters for a script.

    Examples:

        controlplane scripts info generators/class_diagrams

        controlplane scripts info generators/class_diagrams --json
    """
    from src.core.services.scripts.registry import get_script

    project_root = _resolve_project_root(ctx)
    meta = get_script(project_root, script_id)

    if meta is None:
        click.secho(f"❌ Script '{script_id}' not found.", fg="red")
        click.echo("   Use 'controlplane scripts list' to see available scripts.")
        sys.exit(1)

    if as_json:
        data = {
            "id": meta.id,
            "name": meta.name,
            "description": meta.description,
            "category": meta.category,
            "language": meta.language,
            "mode": meta.mode,
            "source": meta.source,
            "tags": meta.tags,
            "timeout": meta.timeout,
            "default_output": meta.default_output,
            "output_formats": meta.output_formats,
            "path": meta.path,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default,
                    "choices": p.choices,
                }
                for p in meta.parameters
            ],
        }
        click.echo(json.dumps(data, indent=2))
        return

    # Pretty output
    click.secho(f"\n🧩 {meta.name}\n", fg="cyan", bold=True)
    if meta.description:
        click.echo(f"   {meta.description}")
        click.echo()

    click.echo(f"   ID:        {meta.id}")
    click.echo(f"   Category:  {meta.category}")
    click.echo(f"   Language:  {meta.language}")
    click.echo(f"   Mode:      {meta.mode}")
    click.echo(f"   Source:    {meta.source}")
    click.echo(f"   Timeout:   {meta.timeout}s")
    if meta.tags:
        click.echo(f"   Tags:      {', '.join(meta.tags)}")
    if meta.default_output:
        click.echo(f"   Output:    {meta.default_output}")
    if meta.output_formats:
        click.echo(f"   Formats:   {', '.join(meta.output_formats)}")

    if meta.parameters:
        click.echo()
        click.secho("   Parameters:", fg="white", bold=True)
        for p in meta.parameters:
            required_mark = " *" if p.required else ""
            default_mark = f" = {p.default}" if p.default else ""
            choices_mark = f" [{', '.join(p.choices)}]" if p.choices else ""
            click.echo(f"     --{p.name}{required_mark} ({p.type}{default_mark}{choices_mark})")
            if p.description:
                click.echo(f"       {p.description}")

    click.echo()
