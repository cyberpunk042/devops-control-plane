"""Content optimize — folders detection and media optimization commands."""

from __future__ import annotations

import json
from pathlib import Path

import click

from . import content, _resolve_project_root


@content.command("folders")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def detect_folders(ctx: click.Context, as_json: bool) -> None:
    """Detect content folders in the project."""
    from src.core.services.content.crypto import detect_content_folders, format_size

    project_root = _resolve_project_root(ctx)
    folders = detect_content_folders(project_root)

    if as_json:
        click.echo(json.dumps(folders, indent=2))
        return

    if not folders:
        click.secho("No content folders found.", fg="yellow")
        return

    click.secho(f"📁 Content folders ({len(folders)}):", fg="cyan", bold=True)
    for f in folders:
        size = format_size(f.get("total_size", 0))
        enc = f.get("encrypted_count", 0)
        enc_str = f" ({enc} encrypted)" if enc else ""
        click.echo(
            f"   {f['name']}: {f.get('file_count', 0)} files, {size}{enc_str}"
        )
    click.echo()


@content.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
def optimize(file: str, as_json: bool) -> None:
    """Optimize a media file (image → WebP, video → H.264, text → gzip)."""
    from src.core.services.content.crypto import format_size
    from src.core.services.content.optimize import classify_storage, optimize_media

    source = Path(file).resolve()
    data = source.read_bytes()
    original_size = len(data)

    import mimetypes
    mime, _ = mimetypes.guess_type(source.name)
    mime = mime or "application/octet-stream"

    opt_data, opt_mime, opt_ext, was_optimized = optimize_media(data, mime, source.name)

    if as_json:
        click.echo(json.dumps({
            "file": source.name,
            "original_size": original_size,
            "optimized_size": len(opt_data),
            "optimized": was_optimized,
            "mime": opt_mime,
            "extension": opt_ext,
            "tier": classify_storage(len(opt_data)),
        }, indent=2))
        return

    if was_optimized:
        pct = len(opt_data) / original_size * 100
        out_path = source.parent / (source.stem + opt_ext)
        out_path.write_bytes(opt_data)
        tier = classify_storage(len(opt_data))

        click.secho(f"✅ Optimized: {source.name}", fg="green", bold=True)
        click.echo(f"   {format_size(original_size)} → {format_size(len(opt_data))} ({pct:.0f}%)")
        click.echo(f"   Output: {out_path.name}")
        click.echo(f"   MIME: {opt_mime}")
        click.echo(f"   Tier: {tier}")
    else:
        click.secho(f"ℹ️  No optimization needed for {source.name}", fg="yellow")
        click.echo(f"   Size: {format_size(original_size)}")
        click.echo(f"   MIME: {mime}")
