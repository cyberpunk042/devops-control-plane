"""
CLI commands for the Content Vault.

Thin wrappers over ``src.core.services.content_crypto``,
``content_optimize``, and ``content_release``.
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
def content() -> None:
    """Content Vault — encrypt, decrypt, optimize, and manage content files."""


# ── Encryption ──────────────────────────────────────────────────

@content.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--passphrase", "-p", prompt=True, hide_input=True, help="Encryption passphrase.")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output path (default: <file>.enc).")
@click.pass_context
def encrypt(ctx: click.Context, file: str, passphrase: str, output: str | None) -> None:
    """Encrypt a file into COVAULT binary envelope (.enc)."""
    from src.core.services.content_crypto import encrypt_file

    source = Path(file).resolve()
    out = Path(output).resolve() if output else None

    try:
        result = encrypt_file(source, passphrase, output_path=out)
        click.secho(f"✅ Encrypted: {source.name}", fg="green", bold=True)
        click.echo(f"   Output: {result}")
        click.echo(f"   Size: {result.stat().st_size:,} bytes")
    except FileNotFoundError as e:
        click.secho(f"❌ {e}", fg="red")
        sys.exit(1)
    except ValueError as e:
        click.secho(f"❌ {e}", fg="red")
        sys.exit(1)
    except Exception as e:
        click.secho(f"❌ Encryption failed: {e}", fg="red")
        sys.exit(1)


@content.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--passphrase", "-p", prompt=True, hide_input=True, help="Decryption passphrase.")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output path (default: original filename).")
@click.pass_context
def decrypt(ctx: click.Context, file: str, passphrase: str, output: str | None) -> None:
    """Decrypt a COVAULT .enc file back to its original."""
    from src.core.services.content_crypto import decrypt_file

    vault_path = Path(file).resolve()
    out = Path(output).resolve() if output else None

    try:
        result = decrypt_file(vault_path, passphrase, output_path=out)
        click.secho(f"✅ Decrypted: {vault_path.name}", fg="green", bold=True)
        click.echo(f"   Output: {result}")
        click.echo(f"   Size: {result.stat().st_size:,} bytes")
    except FileNotFoundError as e:
        click.secho(f"❌ {e}", fg="red")
        sys.exit(1)
    except ValueError as e:
        click.secho(f"❌ {e}", fg="red")
        sys.exit(1)
    except Exception as e:
        click.secho(f"❌ Decryption failed: {e}", fg="red")
        sys.exit(1)


@content.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
def inspect(file: str, as_json: bool) -> None:
    """Read metadata from an encrypted .enc file (no decryption)."""
    from src.core.services.content_crypto import read_metadata

    vault_path = Path(file).resolve()

    try:
        meta = read_metadata(vault_path)
        if as_json:
            click.echo(json.dumps(meta, indent=2))
        else:
            click.secho(f"📦 {vault_path.name}", fg="cyan", bold=True)
            click.echo(f"   Original: {meta.get('filename', '?')}")
            click.echo(f"   MIME: {meta.get('mime_type', '?')}")
            click.echo(f"   Encrypted size: {meta.get('encrypted_size', 0):,} bytes")
            click.echo(f"   SHA-256: {meta.get('original_hash', '?')[:16]}...")
    except Exception as e:
        click.secho(f"❌ {e}", fg="red")
        sys.exit(1)


# ── Classification ──────────────────────────────────────────────

@content.command()
@click.argument("file", type=click.Path(exists=True))
def classify(file: str) -> None:
    """Classify a file into a content category."""
    from src.core.services.content_crypto import classify_file

    path = Path(file).resolve()
    category = classify_file(path)
    click.echo(f"{path.name}: {category}")


@content.command("folders")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def detect_folders(ctx: click.Context, as_json: bool) -> None:
    """Detect content folders in the project."""
    from src.core.services.content_crypto import detect_content_folders, format_size

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


# ── Optimization ────────────────────────────────────────────────

@content.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
def optimize(file: str, as_json: bool) -> None:
    """Optimize a media file (image → WebP, video → H.264, text → gzip)."""
    from src.core.services.content_crypto import format_size
    from src.core.services.content_optimize import classify_storage, optimize_media

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


# ── Release management ──────────────────────────────────────────

@content.group()
def release() -> None:
    """Manage GitHub Release assets for large content files."""


@release.command("list")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def release_list(ctx: click.Context, as_json: bool) -> None:
    """List assets on the content-vault GitHub Release."""
    from src.core.services.content_crypto import format_size
    from src.core.services.content_release import list_release_assets

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
    from src.core.services.content_release import restore_large_files

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
    from src.core.services.content_release import release_inventory

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
