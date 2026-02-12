"""
CLI commands for Package Management integration.

Thin wrappers over ``src.core.services.package_ops``.
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
def packages() -> None:
    """Packages — status, outdated, audit, install, update."""


# ── Detect ──────────────────────────────────────────────────────


@packages.command()
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def status(ctx: click.Context, as_json: bool) -> None:
    """Show detected package managers and dependency files."""
    from src.core.services.package_ops import package_status

    project_root = _resolve_project_root(ctx)
    result = package_status(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("has_packages"):
        click.secho("⚠️  No package managers detected", fg="yellow")
        return

    click.secho("📦 Package Managers:", fg="cyan", bold=True)
    for pm in result.get("managers", []):
        cli_icon = "✅" if pm["cli_available"] else "❌"
        lock_icon = "🔒" if pm["has_lock"] else "⚠️"
        click.echo(f"   {cli_icon} {pm['name']} ({pm['cli']})")
        click.echo(f"      Files: {', '.join(pm['dependency_files'])}")
        if pm["lock_files"]:
            click.echo(f"      {lock_icon} Lock: {', '.join(pm['lock_files'])}")
        else:
            click.echo(f"      {lock_icon} No lock file")
    click.echo()


# ── Observe ─────────────────────────────────────────────────────


@packages.command()
@click.option("--manager", "-m", default=None, help="Package manager (default: auto-detect).")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def outdated(ctx: click.Context, manager: str | None, as_json: bool) -> None:
    """Check for outdated packages."""
    from src.core.services.package_ops import package_outdated

    project_root = _resolve_project_root(ctx)
    result = package_outdated(project_root, manager=manager)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    pkgs = result.get("outdated", [])
    if not pkgs:
        click.secho("✅ All packages up to date", fg="green")
        if result.get("note"):
            click.echo(f"   ℹ️  {result['note']}")
        return

    click.secho(f"📦 Outdated ({result.get('count', len(pkgs))}, {result['manager']}):", fg="yellow", bold=True)
    for p in pkgs:
        click.echo(f"   {p['name']:<30} {p.get('current', '?'):<12} → {p.get('latest', '?')}")
    click.echo()


@packages.command()
@click.option("--manager", "-m", default=None, help="Package manager (default: auto-detect).")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def audit(ctx: click.Context, manager: str | None, as_json: bool) -> None:
    """Run security audit on dependencies."""
    from src.core.services.package_ops import package_audit

    project_root = _resolve_project_root(ctx)
    result = package_audit(project_root, manager=manager)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    if not result.get("available"):
        click.secho(f"⚠️  {result.get('output', 'Audit tool not available')}", fg="yellow")
        return

    vuln_count = result.get("vulnerabilities", 0)
    if vuln_count == 0:
        click.secho(f"✅ No vulnerabilities found ({result['manager']})", fg="green")
    else:
        click.secho(
            f"🚨 {vuln_count} vulnerability(ies) found ({result['manager']})",
            fg="red",
            bold=True,
        )
        if result.get("output"):
            click.echo(result["output"][:1000])
    click.echo()


@packages.command("list")
@click.option("--manager", "-m", default=None, help="Package manager (default: auto-detect).")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def list_packages(ctx: click.Context, manager: str | None, as_json: bool) -> None:
    """List installed packages."""
    from src.core.services.package_ops import package_list

    project_root = _resolve_project_root(ctx)
    result = package_list(project_root, manager=manager)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    pkgs = result.get("packages", [])
    click.secho(f"📦 Installed ({result.get('count', len(pkgs))}, {result['manager']}):", fg="cyan", bold=True)
    for p in pkgs[:50]:  # Cap display
        click.echo(f"   {p['name']:<35} {p.get('version', '?')}")
    if len(pkgs) > 50:
        click.echo(f"   ... and {len(pkgs) - 50} more")
    click.echo()


# ── Act ─────────────────────────────────────────────────────────


@packages.command()
@click.option("--manager", "-m", default=None, help="Package manager (default: auto-detect).")
@click.pass_context
def install(ctx: click.Context, manager: str | None) -> None:
    """Install dependencies."""
    from src.core.services.package_ops import package_install

    project_root = _resolve_project_root(ctx)
    click.secho("📦 Installing dependencies...", fg="cyan")

    result = package_install(project_root, manager=manager)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"✅ Installed ({result['manager']})", fg="green", bold=True)


@packages.command()
@click.argument("package", required=False)
@click.option("--manager", "-m", default=None, help="Package manager (default: auto-detect).")
@click.pass_context
def update(ctx: click.Context, package: str | None, manager: str | None) -> None:
    """Update packages (specific or all)."""
    from src.core.services.package_ops import package_update

    project_root = _resolve_project_root(ctx)
    target = package or "all packages"
    click.secho(f"📦 Updating {target}...", fg="cyan")

    result = package_update(project_root, package=package, manager=manager)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"✅ Updated: {result.get('package', 'all')} ({result['manager']})", fg="green", bold=True)
