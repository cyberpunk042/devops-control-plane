"""
CLI commands for the Secrets Vault.

Thin wrappers over ``src.core.services.vault`` and ``vault_io``.
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
def vault() -> None:
    """Secrets Vault — encrypt, decrypt, and manage secrets."""


@vault.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--passphrase", "-p", prompt=True, hide_input=True, help="Encryption passphrase.")
@click.pass_context
def lock(ctx: click.Context, file: str, passphrase: str) -> None:
    """Encrypt a secret file (lock it into the vault)."""
    from src.core.services.vault import lock_vault

    secret_path = Path(file).resolve()

    try:
        result = lock_vault(secret_path, passphrase)
        click.secho(f"✅ Locked: {secret_path.name}", fg="green", bold=True)
        click.echo(f"   Vault file: {result}")
    except FileNotFoundError as e:
        click.secho(f"❌ {e}", fg="red")
        sys.exit(1)
    except Exception as e:
        click.secho(f"❌ Lock failed: {e}", fg="red")
        sys.exit(1)


@vault.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--passphrase", "-p", prompt=True, hide_input=True, help="Decryption passphrase.")
@click.pass_context
def unlock(ctx: click.Context, file: str, passphrase: str) -> None:
    """Decrypt a vault file (unlock it back to plaintext)."""
    from src.core.services.vault import unlock_vault

    vault_path = Path(file).resolve()

    try:
        result = unlock_vault(vault_path, passphrase)
        click.secho(f"✅ Unlocked: {vault_path.name}", fg="green", bold=True)
        click.echo(f"   Plaintext: {result}")
    except FileNotFoundError as e:
        click.secho(f"❌ {e}", fg="red")
        sys.exit(1)
    except ValueError as e:
        click.secho(f"❌ {e}", fg="red")
        sys.exit(1)
    except Exception as e:
        click.secho(f"❌ Unlock failed: {e}", fg="red")
        sys.exit(1)


@vault.command()
@click.argument("file", type=click.Path(exists=True))
@click.pass_context
def status(ctx: click.Context, file: str) -> None:
    """Check vault status for a secret file."""
    from src.core.services.vault import vault_status

    secret_path = Path(file).resolve()
    result = vault_status(secret_path)

    state = result.get("state", "unknown")
    icons = {"locked": "🔒", "unlocked": "🔓", "missing": "❓"}
    icon = icons.get(state, "❓")

    click.secho(f"{icon} {secret_path.name}: {state}", bold=True)
    if result.get("vault_file"):
        click.echo(f"   Vault file: {result['vault_file']}")


@vault.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--passphrase", "-p", prompt=True, hide_input=True, help="Export passphrase.")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def export(ctx: click.Context, file: str, passphrase: str, as_json: bool) -> None:
    """Export a vault file as a portable JSON envelope."""
    from src.core.services.vault_io import export_vault_file

    secret_path = Path(file).resolve()

    try:
        result = export_vault_file(secret_path, passphrase)
        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            click.secho(f"✅ Exported: {secret_path.name}", fg="green", bold=True)
            click.echo(f"   Format: {result.get('format', 'unknown')}")
            click.echo(f"   Entries: {len(result.get('entries', []))}")
    except Exception as e:
        click.secho(f"❌ Export failed: {e}", fg="red")
        sys.exit(1)


@vault.command("detect")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def detect_secrets(ctx: click.Context, as_json: bool) -> None:
    """Scan project for secret files (.env, credentials, keys)."""
    from src.core.services.vault import set_project_root
    from src.core.services.vault_io import detect_secret_files

    project_root = _resolve_project_root(ctx)
    set_project_root(project_root)

    result = detect_secret_files(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    files = result if isinstance(result, list) else result.get("files", [])
    if not files:
        click.secho("✅ No secret files detected.", fg="green")
        return

    click.secho(f"🔍 Found {len(files)} secret file(s):", fg="cyan", bold=True)
    for f in files:
        name = f.get("name", f) if isinstance(f, dict) else str(f)
        state = f.get("state", "") if isinstance(f, dict) else ""
        state_str = f" [{state}]" if state else ""
        click.echo(f"   • {name}{state_str}")
    click.echo()
