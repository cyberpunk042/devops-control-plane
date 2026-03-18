"""
CLI commands for System Posture.

Thin wrappers over ``src.core.services.system_posture``.

Usage:
    controlplane posture              # Pretty table view
    controlplane posture --json       # Full JSON output
    controlplane posture --pillar toolchain   # Single pillar
    controlplane posture --force      # Bypass cache
"""

from __future__ import annotations

import json
from pathlib import Path

import click


def _resolve_project_root(ctx: click.Context) -> Path:
    """Resolve project root from context or CWD."""
    config_path: Path | None = ctx.obj.get("config_path")
    if config_path is None:
        from src.core.config.loader import find_project_file

        config_path = find_project_file()
    return config_path.parent.resolve() if config_path else Path.cwd()


# ── Rank rendering helpers ─────────────────────────────────────

_RANK_COLORS = {
    "current":    "green",
    "aging":      "blue",
    "outdated":   "yellow",
    "deprecated": "yellow",
    "dangerous":  "red",
    "unknown":    "white",
    "na":         "white",
}

_RANK_ICONS = {
    "current":    "🟢",
    "aging":      "🔵",
    "outdated":   "🟡",
    "deprecated": "🟠",
    "dangerous":  "🔴",
    "unknown":    "⚪",
    "na":         "—",
}

_PILLAR_ICONS = {
    "platform":  "💻",
    "toolchain": "🔧",
    "project":   "📦",
    "runtime":   "⚡",
}

_PILLAR_LABELS = {
    "platform":  "Platform",
    "toolchain": "Toolchain",
    "project":   "Project Health",
    "runtime":   "Runtime",
}


@click.group(invoke_without_command=True)
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.option("--force", is_flag=True, help="Bypass cache and rescan everything.")
@click.option("--pillar", default=None, help="Show only one pillar (platform|toolchain|project|runtime).")
@click.pass_context
def posture(ctx: click.Context, as_json: bool, force: bool, pillar: str | None) -> None:
    """System posture — deprecation awareness across all layers."""
    if ctx.invoked_subcommand is not None:
        return  # subcommand handles it

    from src.core.services.system_posture import scan_posture

    project_root = _resolve_project_root(ctx)

    if not as_json:
        click.secho("🛡️  Scanning system posture...", fg="cyan")

    result = scan_posture(force=force, project_root=project_root)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2, default=str))
        return

    _render_posture(result, pillar_filter=pillar, verbose=ctx.obj.get("verbose", False))


@posture.command("cache")
@click.pass_context
def posture_cache(ctx: click.Context) -> None:
    """Show posture cache diagnostics."""
    from src.core.services.system_posture import cache_stats

    stats = cache_stats()

    if not stats:
        click.secho("  No cached data.", fg="yellow")
        return

    click.echo()
    click.secho("  Cache Key      Age       TTL       Fresh    Compute", fg="cyan", bold=True)
    click.secho("  " + "─" * 56, fg="cyan")

    for key, info in stats.items():
        age = info.get("age_s", 0)
        ttl = info.get("ttl_s", "?")
        fresh = "✅" if info.get("fresh") else "❌"
        elapsed = info.get("elapsed_s", "?")

        ttl_str = "∞" if ttl == float("inf") else f"{ttl}s"
        click.echo(f"  {key:<14}  {age:>5.1f}s    {ttl_str:>6}    {fresh}       {elapsed}s")

    click.echo()


@posture.command("invalidate")
@click.argument("key", required=False, default=None)
@click.pass_context
def posture_invalidate(ctx: click.Context, key: str | None) -> None:
    """Invalidate posture cache (all or specific key)."""
    from src.core.services.mediator import get_mediator

    m = get_mediator()
    path = f"posture.{key}" if key else "posture.full"
    inv = m.put(path, cascade=True)
    busted = inv.get("invalidated", [])
    if busted:
        click.secho(f"  Invalidated: {', '.join(busted)}", fg="green")
    else:
        click.secho("  Nothing to invalidate.", fg="yellow")


# ── Pretty rendering ───────────────────────────────────────────

def _render_posture(posture, *, pillar_filter: str | None = None, verbose: bool = False) -> None:
    """Render the full posture scan to the terminal."""
    overall = posture.overall_rank.value
    overall_icon = _RANK_ICONS.get(overall, "⚪")
    overall_color = _RANK_COLORS.get(overall, "white")

    click.echo()
    click.secho("═" * 64, fg="cyan")
    click.secho(
        f"  {overall_icon} SYSTEM POSTURE: {posture.overall_status.upper()}",
        fg=overall_color, bold=True,
    )
    click.secho("═" * 64, fg="cyan")
    click.echo(f"  {posture.summary}")
    click.echo(f"  Scanned in {posture.scan_duration_ms}ms")
    click.echo()

    pillar_order = ["platform", "toolchain", "project", "runtime"]

    for key in pillar_order:
        if pillar_filter and key != pillar_filter:
            continue

        pillar = posture.pillars.get(key)
        if not pillar:
            continue

        _render_pillar(key, pillar, verbose=verbose)

    click.echo()


def _render_pillar(key: str, pillar, *, verbose: bool = False) -> None:
    """Render a single pillar section."""
    rank = pillar.rank.value
    icon = _PILLAR_ICONS.get(key, "⚙️")
    label = _PILLAR_LABELS.get(key, key)
    rank_icon = _RANK_ICONS.get(rank, "⚪")
    color = _RANK_COLORS.get(rank, "white")

    click.secho(f"  {icon} {label}", fg=color, bold=True, nl=False)
    click.echo(f"  {rank_icon} ({len(pillar.items)} items)")

    for item in pillar.items:
        i_rank = item.rank.value
        i_icon = _RANK_ICONS.get(i_rank, "⚪")
        i_color = _RANK_COLORS.get(i_rank, "white")

        name = item.name
        value = item.value or ""

        # Compact one-liner: emoji  name  value  detail
        click.echo(f"     {i_icon} ", nl=False)
        click.secho(f"{name:<24}", fg=i_color, nl=False)
        click.echo(f" {value:<12}", nl=False)
        if item.detail:
            click.secho(f" {item.detail}", fg="white", dim=True)
        else:
            click.echo()

        # In verbose mode, show extra fields (eol_date, current_version, notes)
        if verbose:
            if item.eol_date:
                click.echo(f"        EOL: {item.eol_date}")
            if item.current_version:
                click.echo(f"        Current: {item.current_version}")
            if item.notes:
                click.echo(f"        Note: {item.notes}")

    # Warnings
    if pillar.warnings:
        for w in pillar.warnings:
            click.secho(f"     ⚠️  {w}", fg="yellow")

    # Recommendations (verbose only)
    if verbose and pillar.recommendations:
        click.secho("     💡 Recommendations:", fg="yellow")
        for r in pillar.recommendations[:5]:
            click.echo(f"        → {r}")

    click.echo()
