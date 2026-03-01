"""Content release — GitHub Release asset management commands."""

from __future__ import annotations

import json
import sys

import click

from . import content, _resolve_project_root


@content.group()
def release() -> None:
    """Manage GitHub Release assets for large content files."""


@release.command("list")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def release_list(ctx: click.Context, as_json: bool) -> None:
    """List assets on the content-vault GitHub Release."""
    from src.core.services.content.crypto import format_size
    from src.core.services.content.release import list_release_assets

    project_root = _resolve_project_root(ctx)
    result = list_release_assets(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("available"):
        click.secho(f"❌ {result.get('error', 'Release not available')}", fg="red")
        sys.exit(1)

    assets = result.get("assets", [])
    if not assets:
        click.secho("No assets on content-vault release.", fg="yellow")
        return

    click.secho(f"☁️  Release assets ({len(assets)}):", fg="cyan", bold=True)
    for a in assets:
        size = format_size(a.get("size", 0))
        click.echo(f"   • {a['name']} ({size})")
    click.echo()


@release.command()
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def restore(ctx: click.Context, as_json: bool) -> None:
    """Download missing large files from the content-vault release."""
    from src.core.services.content.release import restore_large_files

    project_root = _resolve_project_root(ctx)
    result = restore_large_files(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("gh_available"):
        click.secho("❌ gh CLI not available — cannot restore", fg="red")
        sys.exit(1)

    restored = result.get("restored", [])
    failed = result.get("failed", [])
    present = result.get("already_present", [])

    if restored:
        click.secho(f"✅ Restored {len(restored)} file(s):", fg="green", bold=True)
        for name in restored:
            click.echo(f"   ⬇ {name}")

    if present:
        click.echo(f"   Already present: {len(present)}")

    if failed:
        click.secho(f"❌ Failed: {len(failed)}", fg="red")
        for f in failed:
            click.echo(f"   • {f['name']}: {f['error']}")

    if not restored and not failed:
        click.secho("✅ All large files are present.", fg="green")

    click.echo()


@release.command()
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def inventory(ctx: click.Context, as_json: bool) -> None:
    """Cross-reference local sidecars with remote release assets."""
    from src.core.services.content.release import release_inventory

    project_root = _resolve_project_root(ctx)
    result = release_inventory(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    synced = result.get("synced", [])
    orphaned = result.get("orphaned", [])
    extra = result.get("extra_remote", [])

    click.secho("📊 Release Inventory:", fg="cyan", bold=True)
    click.echo(f"   Synced: {len(synced)}")
    if orphaned:
        click.secho(f"   Orphaned (sidecar but no remote): {len(orphaned)}", fg="yellow")
        for o in orphaned:
            click.echo(f"     • {o['name']} → {o.get('asset_name', '?')}")
    if extra:
        click.secho(f"   Extra remote (no local sidecar): {len(extra)}", fg="yellow")
        for name in extra:
            click.echo(f"     • {name}")
    click.echo()
