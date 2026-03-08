"""Scripts list — discover and display available scripts."""

from __future__ import annotations

import json

import click

from . import scripts, _resolve_project_root


@scripts.command("list")
@click.option("--category", "-c", default=None, help="Filter by category (e.g., generator, audit, ops).")
@click.option("--source", "-s", default=None, help="Filter by source (template, root, override).")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def list_scripts(ctx: click.Context, category: str | None, source: str | None, as_json: bool) -> None:
    """List all discovered scripts with metadata."""
    from src.core.services.scripts.registry import discover_scripts

    project_root = _resolve_project_root(ctx)
    all_scripts = discover_scripts(project_root)

    # Apply filters
    if category:
        all_scripts = [s for s in all_scripts if s.category == category]
    if source:
        all_scripts = [s for s in all_scripts if s.source == source]

    if as_json:
        data = [
            {
                "id": s.id,
                "name": s.name,
                "category": s.category,
                "language": s.language,
                "source": s.source,
                "mode": s.mode,
                "tags": s.tags,
                "parameters": len(s.parameters),
            }
            for s in all_scripts
        ]
        click.echo(json.dumps(data, indent=2))
        return

    if not all_scripts:
        click.secho("📭 No scripts found.", fg="yellow")
        click.echo("   Run the setup wizard or add scripts to your scripts/ directory.")
        return

    click.secho(f"\n🧩 Scripts ({len(all_scripts)}):\n", fg="cyan", bold=True)

    # Group by category
    categories: dict[str, list] = {}
    for s in all_scripts:
        categories.setdefault(s.category or "uncategorized", []).append(s)

    for cat_name in sorted(categories):
        click.secho(f"  {cat_name}:", fg="white", bold=True)
        for s in sorted(categories[cat_name], key=lambda x: x.name):
            source_badge = {"template": "📦", "root": "👤", "override": "🔄"}.get(
                s.source, "❓"
            )
            param_count = len(s.parameters)
            params_label = f" ({param_count} params)" if param_count else ""
            click.echo(f"    {source_badge} {s.id:<35} {s.name}{params_label}")
        click.echo()
