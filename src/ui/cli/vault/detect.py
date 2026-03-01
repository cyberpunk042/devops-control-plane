"""Vault detect — scan project for secret files."""

from __future__ import annotations

import json

import click

from . import vault, _resolve_project_root


@vault.command("detect")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def detect_secrets(ctx: click.Context, as_json: bool) -> None:
    """Scan project for secret files (.env, credentials, keys)."""
    from src.core.services.vault_io import detect_secret_files

    project_root = _resolve_project_root(ctx)

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
