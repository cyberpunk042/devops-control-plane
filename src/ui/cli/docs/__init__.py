"""
CLI commands for Documentation integration.

Thin wrappers over ``src.core.services.docs_ops``.
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


@click.group("docs")
def docs() -> None:
    """Docs — documentation status, coverage, links, and generation."""


# ── Detect ──────────────────────────────────────────────────────


@docs.command("status")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def status(ctx: click.Context, as_json: bool) -> None:
    """Show documentation status (README, API specs, key files)."""
    from src.core.services.docs_svc.ops import docs_status

    project_root = _resolve_project_root(ctx)
    result = docs_status(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    click.secho("📚 Documentation Status:", fg="cyan", bold=True)
    click.echo()

    # README
    readme = result.get("readme", {})
    if readme.get("exists"):
        click.secho(f"   📖 README: {readme['path']} ({readme['lines']} lines)", fg="green")
        headings = readme.get("headings", [])
        for h in headings[:5]:
            indent = "  " * h["level"]
            click.echo(f"      {indent}{'#' * h['level']} {h['text']}")
    else:
        click.secho("   ❌ No README found!", fg="red")

    click.echo()

    # Documentation directories
    doc_dirs = result.get("doc_dirs", [])
    if doc_dirs:
        click.secho("   📁 Documentation directories:", fg="cyan")
        for d in doc_dirs:
            click.echo(f"      {d['name']}/: {d['doc_count']} doc file(s), {d['file_count']} total")
    else:
        click.echo("   📁 No documentation directories (docs/, doc/)")

    click.echo()

    # API specs
    specs = result.get("api_specs", [])
    if specs:
        click.secho("   📡 API Specifications:", fg="cyan")
        for s in specs:
            click.echo(f"      {s['file']} ({s['type']})")
    else:
        click.echo("   📡 No API specifications detected")

    click.echo()

    # Key files
    for name, icon, label in [
        ("changelog", "📝", "Changelog"),
        ("license", "⚖️", "License"),
        ("contributing", "🤝", "Contributing guide"),
        ("code_of_conduct", "📜", "Code of Conduct"),
        ("security_policy", "🔐", "Security policy"),
    ]:
        info = result.get(name, {})
        if info.get("exists"):
            click.secho(f"   {icon} {label}: {info['path']}", fg="green")
        else:
            click.echo(f"   {icon} {label}: not found")

    click.echo()


# ── Observe ─────────────────────────────────────────────────────


@docs.command("coverage")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def coverage(ctx: click.Context, as_json: bool) -> None:
    """Check documentation coverage per module."""
    from src.core.services.docs_svc.ops import docs_coverage

    project_root = _resolve_project_root(ctx)
    result = docs_coverage(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    cov = result.get("coverage", 0)
    documented = result.get("documented", 0)
    total = result.get("total", 0)

    color = "green" if cov >= 0.8 else "yellow" if cov >= 0.5 else "red"
    click.secho(
        f"📊 Documentation Coverage: {int(cov * 100)}% ({documented}/{total} modules)",
        fg=color,
        bold=True,
    )
    click.echo()

    for m in result.get("modules", []):
        icon = "✅" if m["has_readme"] else "❌"
        stack = f" ({m['stack']})" if m.get("stack") else ""
        docs = f" [{m['doc_files']} doc files]" if m["doc_files"] > 0 else ""
        click.echo(f"   {icon} {m['name']}{stack}{docs}")
        click.echo(f"      Path: {m['path']}")

    click.echo()


@docs.command("links")
@click.option("--file", "file_path", default=None, help="Check a specific file.")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def links(ctx: click.Context, file_path: str | None, as_json: bool) -> None:
    """Check for broken internal links in markdown files."""
    from src.core.services.docs_svc.ops import check_links

    project_root = _resolve_project_root(ctx)

    click.secho("🔗 Checking links...", fg="cyan")

    result = check_links(project_root, file_path=file_path)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if result.get("ok"):
        click.secho(
            f"✅ All links valid ({result['total_links']} links in {result['files_checked']} files)",
            fg="green",
            bold=True,
        )
    else:
        broken = result.get("broken", [])
        click.secho(
            f"❌ {result['broken_count']} broken link(s) found!",
            fg="red",
            bold=True,
        )
        click.echo()

        for b in broken[:20]:
            click.secho(f"   ❌ {b['file']}:{b['line']}", fg="red")
            click.echo(f"      [{b['text']}]({b['link']})")
            click.echo(f"      Reason: {b['reason']}")

        if len(broken) > 20:
            click.echo(f"\n   ... and {len(broken) - 20} more")

    click.echo()


# ── Facilitate ──────────────────────────────────────────────────


@docs.group("generate")
def generate() -> None:
    """Generate documentation files."""


@generate.command("changelog")
@click.option("--commits", default=50, help="Max commits to include.")
@click.option("--since", default=None, help="Only commits since date (YYYY-MM-DD).")
@click.option("--write", is_flag=True, help="Write to disk (default: preview only).")
@click.pass_context
def gen_changelog(ctx: click.Context, commits: int, since: str | None, write: bool) -> None:
    """Generate CHANGELOG.md from git history."""
    from src.core.services.docs_svc.ops import generate_changelog
    from src.core.services.docker_ops import write_generated_file

    project_root = _resolve_project_root(ctx)
    result = generate_changelog(project_root, max_commits=commits, since=since)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    file_data = result["file"]
    click.echo(f"   Commits: {result['commits']}")

    if write:
        wr = write_generated_file(project_root, file_data)
        if "error" in wr:
            click.secho(f"❌ {wr['error']}", fg="red")
            sys.exit(1)
        click.secho(f"✅ Written: {wr['path']}", fg="green", bold=True)
    else:
        click.secho(f"📄 Preview: {file_data['path']}", fg="cyan", bold=True)
        if file_data.get("reason"):
            click.echo(f"   Reason: {file_data['reason']}")
        click.echo("─" * 60)
        # Show first 40 lines
        lines = file_data["content"].splitlines()
        for line in lines[:40]:
            click.echo(line)
        if len(lines) > 40:
            click.echo(f"... ({len(lines) - 40} more lines)")
        click.echo("─" * 60)
        click.secho("   (use --write to save to disk)", fg="yellow")


@generate.command("readme")
@click.option("--write", is_flag=True, help="Write to disk (default: preview only).")
@click.pass_context
def gen_readme(ctx: click.Context, write: bool) -> None:
    """Generate README.md template from project metadata."""
    from src.core.services.docs_svc.ops import generate_readme
    from src.core.services.docker_ops import write_generated_file

    project_root = _resolve_project_root(ctx)
    result = generate_readme(project_root)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    file_data = result["file"]
    if write:
        wr = write_generated_file(project_root, file_data)
        if "error" in wr:
            click.secho(f"❌ {wr['error']}", fg="red")
            sys.exit(1)
        click.secho(f"✅ Written: {wr['path']}", fg="green", bold=True)
    else:
        click.secho(f"📄 Preview: {file_data['path']}", fg="cyan", bold=True)
        if file_data.get("reason"):
            click.echo(f"   Reason: {file_data['reason']}")
        click.echo("─" * 60)
        click.echo(file_data["content"])
        click.echo("─" * 60)
        click.secho("   (use --write to save to disk)", fg="yellow")
