"""Vault .env management — keys, templates, create, add/update/delete key, activate."""

from __future__ import annotations

import json
import sys

import click

from . import vault, _resolve_project_root, _env_path


@vault.command("keys")
@click.option("--env", "env_name", default="", help="Environment name (e.g. production).")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def list_keys(ctx: click.Context, env_name: str, as_json: bool) -> None:
    """List .env keys with masked values."""
    from src.core.services import vault_env_ops

    project_root = _resolve_project_root(ctx)
    env_path = _env_path(project_root, env_name)

    result = vault_env_ops.list_keys_enriched(env_path)

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
