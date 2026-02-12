"""
CLI commands for the Secrets Vault.

Thin wrappers over ``src.core.services.vault``, ``vault_io``,
and ``vault_env_ops``.
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


# ── .env management (vault_env_ops) ─────────────────────────────


def _env_path(project_root: Path, env_name: str = "") -> Path:
    """Resolve .env file path from optional env name."""
    if env_name:
        return project_root / f".env.{env_name}"
    return project_root / ".env"


@vault.command("keys")
@click.option("--env", "env_name", default="", help="Environment name (e.g. production).")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def list_keys(ctx: click.Context, env_name: str, as_json: bool) -> None:
    """List .env keys with masked values."""
    from src.core.services import vault_env_ops
    from src.core.services.vault import _vault_path_for

    project_root = _resolve_project_root(ctx)
    env_path = _env_path(project_root, env_name)
    vault_path = _vault_path_for(env_path)

    result = vault_env_ops.list_keys_enriched(env_path, vault_path)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    state = result.get("state", "empty")
    if state == "locked":
        click.secho("🔒 Vault is locked — unlock first.", fg="yellow")
        return
    if state == "empty":
        click.secho("📭 No .env file found.", fg="yellow")
        return

    keys = result.get("keys", [])
    click.secho(f"🔑 Keys ({len(keys)}):", fg="cyan", bold=True)
    for k in keys:
        kind_icon = "🔒" if k.get("kind") == "secret" else "📋"
        local = " 📌" if k.get("local_only") else ""
        click.echo(f"   {kind_icon} {k['key']:30s} = {k.get('masked', '?')}{local}")

    sections = result.get("sections", [])
    if sections:
        click.echo()
        click.secho("📂 Sections:", fg="cyan")
        for s in sections:
            click.echo(f"   • {s['name']} ({len(s.get('keys', []))} keys)")
    click.echo()


@vault.command("templates")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
def list_templates(as_json: bool) -> None:
    """Show available .env template sections."""
    from src.core.services.vault_env_ops import get_templates

    sections = get_templates()

    if as_json:
        click.echo(json.dumps({"sections": sections}, indent=2))
        return

    click.secho("📋 Available templates:", fg="cyan", bold=True)
    for s in sections:
        keys_list = ", ".join(k["key"] for k in s.get("keys", [])[:3])
        more = f" +{len(s['keys']) - 3} more" if len(s.get("keys", [])) > 3 else ""
        click.echo(f"   • {s['id']:20s}  {s['name']}")
        click.echo(f"     {keys_list}{more}")
    click.echo()


@vault.command("create")
@click.option("--env", "env_name", default="", help="Environment name.")
@click.option("--template", "-t", "templates", multiple=True,
              help="Template section IDs to include (repeatable).")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def create_env(ctx: click.Context, env_name: str,
               templates: tuple[str, ...], as_json: bool) -> None:
    """Create a new .env file from template sections.

    Examples:

        controlplane vault create --template content_vault --template api_keys

        controlplane vault create --env production --template database
    """
    from src.core.services.vault_env_ops import create_env as _create_env

    project_root = _resolve_project_root(ctx)
    env_path = _env_path(project_root, env_name)

    result = _create_env(env_path, template_sections=list(templates))

    if as_json:
        click.echo(json.dumps(result, indent=2))
        if "error" in result:
            sys.exit(1)
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"✅ Created: {env_path.name}", fg="green", bold=True)
    click.echo(f"   Keys: {result.get('total_keys', '?')}")


@vault.command("add-key")
@click.argument("key")
@click.argument("value", default="")
@click.option("--env", "env_name", default="", help="Environment name.")
@click.option("--section", "-s", default="", help="Section to add the key under.")
@click.pass_context
def add_key(ctx: click.Context, key: str, value: str,
            env_name: str, section: str) -> None:
    """Add a key-value pair to the .env file.

    Examples:

        controlplane vault add-key DATABASE_URL postgres://localhost/mydb

        controlplane vault add-key API_KEY sk-1234 --section "API Keys"
    """
    from src.core.services.vault_env_ops import add_keys as _add_keys

    project_root = _resolve_project_root(ctx)
    env_path = _env_path(project_root, env_name)

    result = _add_keys(env_path, [{"key": key, "value": value}], section=section)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"✅ Added: {key}", fg="green")


@vault.command("update-key")
@click.argument("key")
@click.argument("value")
@click.option("--env", "env_name", default="", help="Environment name.")
@click.pass_context
def update_key_cmd(ctx: click.Context, key: str, value: str, env_name: str) -> None:
    """Update a key's value in the .env file."""
    from src.core.services.vault_env_ops import update_key as _update_key

    project_root = _resolve_project_root(ctx)
    env_path = _env_path(project_root, env_name)

    result = _update_key(env_path, key, value)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"✅ Updated: {key}", fg="green")


@vault.command("delete-key")
@click.argument("key")
@click.option("--env", "env_name", default="", help="Environment name.")
@click.pass_context
def delete_key_cmd(ctx: click.Context, key: str, env_name: str) -> None:
    """Remove a key from the .env file."""
    from src.core.services.vault_env_ops import delete_key as _delete_key

    project_root = _resolve_project_root(ctx)
    env_path = _env_path(project_root, env_name)

    result = _delete_key(env_path, key)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"✅ Deleted: {key}", fg="green")


@vault.command("activate")
@click.argument("name")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def activate_env(ctx: click.Context, name: str, as_json: bool) -> None:
    """Switch the active environment (swap .env files).

    Saves the current .env to .env.<old>, copies .env.<name> to .env,
    and updates the .env.active marker.

    Examples:

        controlplane vault activate production

        controlplane vault activate staging
    """
    from src.core.services import vault_env_ops
    from src.ui.web import vault as vault_module

    project_root = _resolve_project_root(ctx)
    result = vault_env_ops.activate_env(
        project_root, name, vault_module=vault_module,
    )

    if as_json:
        click.echo(json.dumps(result, indent=2))
        if "error" in result:
            sys.exit(1)
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"✅ Active environment: {name}", fg="green", bold=True)
    if result.get("state"):
        click.echo(f"   State: {result['state']}")
