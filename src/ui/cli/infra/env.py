"""Infra env subgroup — .env file management commands."""

from __future__ import annotations

import json
import sys

import click

from . import infra, _resolve_project_root, _handle_generated


@infra.group("env")
def env() -> None:
    """Environment variable management (.env files)."""


@env.command("status")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def env_status(ctx: click.Context, as_json: bool) -> None:
    """Show detected .env files and their state."""
    from src.core.services.env_ops import env_status as _status

    project_root = _resolve_project_root(ctx)
    result = _status(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    files = result.get("files", [])
    if not files:
        click.secho("⚠️  No .env files detected", fg="yellow")
        return

    click.secho("🔐 Environment Files:", fg="cyan", bold=True)
    for f in files:
        click.echo(f"   📄 {f['name']} ({f['var_count']} variables)")

    status_parts = []
    if result.get("has_env"):
        status_parts.append("✅ .env present")
    else:
        status_parts.append("❌ .env missing")
    if result.get("has_example"):
        status_parts.append("✅ .env.example present")
    else:
        status_parts.append("⚠️  .env.example missing")

    click.echo(f"\n   {' │ '.join(status_parts)}")
    click.echo()


@env.command("vars")
@click.option("--file", "-f", default=".env", help="Env file to read (default: .env).")
@click.option("--show-values", is_flag=True, help="Show actual values (default: redacted).")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def env_vars(ctx: click.Context, file: str, show_values: bool, as_json: bool) -> None:
    """List variables in a .env file."""
    from src.core.services.env_ops import env_vars as _vars

    project_root = _resolve_project_root(ctx)
    result = _vars(project_root, file=file, redact=not show_values)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"📄 {file} ({result.get('count', 0)} variables):", fg="cyan", bold=True)
    for key, value in result.get("variables", {}).items():
        click.echo(f"   {key:<35} {value}")
    click.echo()


@env.command("diff")
@click.option("--source", "-s", default=".env.example", help="Source file (default: .env.example).")
@click.option("--target", "-t", default=".env", help="Target file (default: .env).")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def env_diff(ctx: click.Context, source: str, target: str, as_json: bool) -> None:
    """Compare two .env files — find missing and extra variables."""
    from src.core.services.env_ops import env_diff as _diff

    project_root = _resolve_project_root(ctx)
    result = _diff(project_root, source=source, target=target)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    if result.get("in_sync"):
        click.secho(f"✅ {source} ↔ {target}: In sync", fg="green", bold=True)
    else:
        click.secho(f"📊 {source} ↔ {target}:", fg="cyan", bold=True)

        missing = result.get("missing", [])
        extra = result.get("extra", [])
        common = result.get("common", [])

        if missing:
            click.secho(f"\n   ❌ Missing from {target} ({len(missing)}):", fg="red")
            for key in missing:
                click.echo(f"      {key}")

        if extra:
            click.secho(f"\n   ⚠️  Extra in {target} ({len(extra)}):", fg="yellow")
            for key in extra:
                click.echo(f"      {key}")

        click.echo(f"\n   ✅ Common: {len(common)} variables")
    click.echo()


@env.command("validate")
@click.option("--file", "-f", default=".env", help="Env file to validate (default: .env).")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def env_validate(ctx: click.Context, file: str, as_json: bool) -> None:
    """Validate a .env file for common issues."""
    from src.core.services.env_ops import env_validate as _validate

    project_root = _resolve_project_root(ctx)
    result = _validate(project_root, file=file)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    if result.get("valid"):
        click.secho(f"✅ {file}: Valid (no warnings)", fg="green", bold=True)
    else:
        click.secho(f"⚠️  {file}: {result.get('issue_count', 0)} issue(s)", fg="yellow", bold=True)

    for issue in result.get("issues", []):
        icon = "⚠️" if issue["severity"] == "warning" else "ℹ️"
        click.echo(f"   {icon} Line {issue['line']}: {issue['message']}")
    click.echo()


@env.command("generate-example")
@click.option("--write", is_flag=True, help="Write to disk (default: preview only).")
@click.pass_context
def env_generate_example(ctx: click.Context, write: bool) -> None:
    """Generate .env.example from existing .env."""
    from src.core.services.env_ops import generate_env_example
    from src.core.services.docker_ops import write_generated_file

    project_root = _resolve_project_root(ctx)
    result = generate_env_example(project_root)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    _handle_generated(project_root, result["file"], write)


@env.command("generate-env")
@click.option("--write", is_flag=True, help="Write to disk (default: preview only).")
@click.pass_context
def env_generate_env(ctx: click.Context, write: bool) -> None:
    """Generate .env from .env.example."""
    from src.core.services.env_ops import generate_env_from_example
    from src.core.services.docker_ops import write_generated_file

    project_root = _resolve_project_root(ctx)
    result = generate_env_from_example(project_root)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    _handle_generated(project_root, result["file"], write)
