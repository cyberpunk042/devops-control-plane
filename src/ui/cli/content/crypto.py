"""Content crypto — encrypt, decrypt, inspect, classify commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from . import content


@content.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--passphrase", "-p", prompt=True, hide_input=True, help="Encryption passphrase.")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output path (default: <file>.enc).")
@click.pass_context
def encrypt(ctx: click.Context, file: str, passphrase: str, output: str | None) -> None:
    """Encrypt a file into COVAULT binary envelope (.enc)."""
    from src.core.services.content.crypto import encrypt_file

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
    from src.core.services.content.crypto import decrypt_file

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
    from src.core.services.content.crypto import read_metadata

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


@content.command()
@click.argument("file", type=click.Path(exists=True))
def classify(file: str) -> None:
    """Classify a file into a content category."""
    from src.core.services.content.crypto import classify_file

    path = Path(file).resolve()
    category = classify_file(path)
    click.echo(f"{path.name}: {category}")
