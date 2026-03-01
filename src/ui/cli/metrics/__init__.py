"""
CLI commands for Metrics & Project Health.

Thin wrappers over ``src.core.services.metrics_ops``.
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


@click.group()
def metrics() -> None:
    """Metrics — project health score, probes, and recommendations."""


@metrics.command("health")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def health(ctx: click.Context, as_json: bool) -> None:
    """Run all health probes and show project score."""
    from src.core.services.metrics.ops import project_health

    project_root = _resolve_project_root(ctx)

    click.secho("🔍 Running health probes...", fg="cyan")

    result = project_health(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    # Score header
    score = result.get("score", 0)
    grade = result.get("grade", "?")

    grade_colors = {"A": "green", "B": "green", "C": "yellow", "D": "red", "F": "red"}
    grade_color = grade_colors.get(grade, "white")

    click.echo()
    click.secho("═" * 60, fg="cyan")
    click.secho(f"  PROJECT HEALTH: {score}/{result.get('max_score', 100)} — Grade {grade}", fg=grade_color, bold=True)
    click.secho("═" * 60, fg="cyan")
    click.echo()

    # Score bar
    bar_len = 40
    filled = int(score / 100 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)
    click.echo(f"  [{bar}] {score}%")
    click.echo()

    # Per-probe results
    probe_icons = {
        "git": "🔀",
        "docker": "🐳",
        "ci": "⚙️",
        "packages": "📦",
        "env": "🔐",
        "quality": "🔍",
        "structure": "📁",
    }

    probe_names = {
        "git": "Git",
        "docker": "Docker",
        "ci": "CI/CD",
        "packages": "Packages",
        "env": "Environment",
        "quality": "Quality",
        "structure": "Structure",
    }

    for probe_id, probe_data in result.get("probes", {}).items():
        probe_score = probe_data.get("score", 0)
        icon = probe_icons.get(probe_id, "⚙️")
        name = probe_names.get(probe_id, probe_id)

        # Color by score
        if probe_score >= 0.8:
            color = "green"
            status = "✅"
        elif probe_score >= 0.5:
            color = "yellow"
            status = "⚠️"
        else:
            color = "red"
            status = "❌"

        pct = int(probe_score * 100)
        click.secho(f"  {icon} {name:<15} {status} {pct:>3}%", fg=color)

        for finding in probe_data.get("findings", [])[:3]:
            click.echo(f"     {finding}")

    # Recommendations
    recs = result.get("recommendations", [])
    if recs:
        click.echo()
        click.secho("  💡 Recommendations:", fg="yellow", bold=True)
        for i, rec in enumerate(recs[:7], 1):
            click.echo(f"     {i}. {rec}")

    click.echo()


@metrics.command("summary")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def summary(ctx: click.Context, as_json: bool) -> None:
    """Quick project summary (fast, no probes)."""
    from src.core.services.metrics.ops import project_summary

    project_root = _resolve_project_root(ctx)
    result = project_summary(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    click.secho(f"📋 {result['name']}", fg="cyan", bold=True)
    click.echo(f"   Root: {result['root']}")
    click.echo(f"   Modules: {result['modules']}")
    click.echo(f"   Stacks: {', '.join(result.get('stacks', []))}")

    click.echo()
    click.secho("   Integrations:", fg="cyan")
    for name, available in result.get("integrations", {}).items():
        icon = "✅" if available else "❌"
        click.echo(f"      {icon} {name}")
    click.echo()


@metrics.command("report")
@click.pass_context
def report(ctx: click.Context) -> None:
    """Generate a full health report (Markdown)."""
    from src.core.services.metrics.ops import project_health, project_summary

    project_root = _resolve_project_root(ctx)

    click.secho("📊 Generating health report...", fg="cyan")

    summary = project_summary(project_root)
    health = project_health(project_root)

    lines = [
        f"# Project Health Report: {summary['name']}",
        "",
        f"**Score:** {health['score']}/{health['max_score']} — Grade **{health['grade']}**",
        f"**Generated:** {health['timestamp']}",
        f"**Modules:** {summary['modules']}",
        f"**Stacks:** {', '.join(summary.get('stacks', []))}",
        "",
        "## Probe Results",
        "",
        "| Probe | Score | Status |",
        "|-------|-------|--------|",
    ]

    for probe_id, probe_data in health.get("probes", {}).items():
        pct = int(probe_data.get("score", 0) * 100)
        status = "✅" if pct >= 80 else "⚠️" if pct >= 50 else "❌"
        lines.append(f"| {probe_id} | {pct}% | {status} |")

    lines.extend(["", "## Findings", ""])

    for probe_id, probe_data in health.get("probes", {}).items():
        findings = probe_data.get("findings", [])
        if findings:
            lines.append(f"### {probe_id}")
            for f in findings:
                lines.append(f"- {f}")
            lines.append("")

    recs = health.get("recommendations", [])
    if recs:
        lines.extend(["## Recommendations", ""])
        for i, rec in enumerate(recs, 1):
            lines.append(f"{i}. {rec}")

    report_md = "\n".join(lines) + "\n"
    click.echo(report_md)
