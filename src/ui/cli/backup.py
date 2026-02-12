"""
CLI commands for Backup & Restore.

Thin wrappers over ``src.core.services.backup_ops``.
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
def backup() -> None:
    """Backup & Restore — create, list, preview, and restore archives."""


@backup.command()
@click.argument("folder")
@click.argument("paths", nargs=-1, required=True)
@click.option("--label", "-l", default="cli_export", help="Backup label.")
@click.option("--decrypt-enc", is_flag=True, help="Decrypt .enc files into archive.")
@click.option("--encrypt", is_flag=True, help="Encrypt the entire archive.")
@click.option("--name", "custom_name", default="", help="Custom archive name.")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def create(
    ctx: click.Context,
    folder: str,
    paths: tuple[str, ...],
    label: str,
    decrypt_enc: bool,
    encrypt: bool,
    custom_name: str,
    as_json: bool,
) -> None:
    """Create a backup archive from selected paths.

    FOLDER is the target folder (backup stored in FOLDER/.backup/).
    PATHS are relative paths to include.

    Examples:

        controlplane backup create docs docs/guides docs/api

        controlplane backup create content content/ --encrypt
    """
    from src.core.services.backup_ops import create_backup

    project_root = _resolve_project_root(ctx)
    result = create_backup(
        project_root,
        folder,
        list(paths),
        label=label,
        decrypt_enc=decrypt_enc,
        encrypt_archive_flag=encrypt,
        custom_name=custom_name,
    )

    if as_json:
        click.echo(json.dumps(result, indent=2))
        if "error" in result:
            sys.exit(1)
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"✅ Backup created: {result['filename']}", fg="green", bold=True)
    click.echo(f"   Path: {result.get('full_path', '?')}")
    click.echo(f"   Size: {result.get('size_bytes', 0):,} bytes")
    manifest = result.get("manifest", {})
    stats = manifest.get("stats", {})
    click.echo(f"   Files: {stats.get('total_files', '?')}")
    if result.get("encrypted"):
        click.echo(f"   🔒 Encrypted")


@backup.command("list")
@click.argument("folder")
@click.option("--check-release", is_flag=True, help="Cross-ref with GitHub Release.")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def list_backups_cmd(ctx: click.Context, folder: str, check_release: bool, as_json: bool) -> None:
    """List backups in a folder's .backup/ directory."""
    from src.core.services.backup_ops import list_backups

    project_root = _resolve_project_root(ctx)
    result = list_backups(project_root, folder, check_release=check_release)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    backups = result.get("backups", [])
    if not backups:
        click.secho(f"No backups found in {folder}/.backup/", fg="yellow")
        return

    click.secho(f"📦 Backups in {folder} ({len(backups)}):", fg="cyan", bold=True)
    for b in backups:
        enc = " 🔒" if b.get("encrypted") else ""
        git = " 📌" if b.get("git_tracked") else ""
        size_kb = b.get("size_bytes", 0) / 1024
        click.echo(f"   {b['filename']}{enc}{git}  ({size_kb:.0f} KB)")
    click.echo()


@backup.command()
@click.argument("path")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def preview(ctx: click.Context, path: str, as_json: bool) -> None:
    """Preview the file tree inside a backup archive."""
    from src.core.services.backup_ops import preview_backup

    project_root = _resolve_project_root(ctx)
    result = preview_backup(project_root, path)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        if "error" in result:
            sys.exit(1)
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    files = result.get("files", [])
    click.secho(f"📋 Archive: {result.get('backup_path', '?')}", fg="cyan", bold=True)
    if result.get("encrypted"):
        click.echo("   🔒 Encrypted archive")
    click.echo(f"   Files: {result.get('total', 0)}")
    click.echo()

    for f in files:
        size_kb = f.get("size", 0) / 1024
        click.echo(f"   {f['path']:50s} [{f.get('type', '?'):6s}] {size_kb:7.1f} KB")
    click.echo()


@backup.command()
@click.argument("path")
@click.pass_context
def delete(ctx: click.Context, path: str) -> None:
    """Delete a backup archive."""
    from src.core.services.backup_ops import delete_backup

    project_root = _resolve_project_root(ctx)
    result = delete_backup(project_root, path)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"✅ Deleted: {result.get('deleted', '?')}", fg="green")


@backup.command()
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def folders(ctx: click.Context, as_json: bool) -> None:
    """List scannable project folders."""
    from src.core.services.backup_ops import list_folders

    project_root = _resolve_project_root(ctx)
    result = list_folders(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result:
        click.secho("No scannable folders found.", fg="yellow")
        return

    click.secho(f"📁 Folders ({len(result)}):", fg="cyan", bold=True)
    for f in result:
        click.echo(f"   • {f['name']}")
    click.echo()
