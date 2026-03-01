"""Security observe — gitignore analysis and posture commands."""

from __future__ import annotations

import json

import click

from . import security, _resolve_project_root, _detect_stack_names


@security.command("gitignore")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def gitignore(ctx: click.Context, as_json: bool) -> None:
    """Analyze .gitignore completeness for detected stacks."""
    from src.core.services.security_ops import gitignore_analysis

    project_root = _resolve_project_root(ctx)
    stack_names = _detect_stack_names(project_root)
    result = gitignore_analysis(project_root, stack_names=stack_names)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("exists"):
        click.secho("❌ No .gitignore file found!", fg="red", bold=True)
        click.echo("   Generate one: controlplane security generate gitignore")
        return

    coverage = result.get("coverage", 0)
    missing = result.get("missing_patterns", [])

    if coverage >= 0.95:
        click.secho(f"✅ .gitignore: {int(coverage * 100)}% coverage", fg="green", bold=True)
    elif coverage >= 0.7:
        click.secho(f"⚠️  .gitignore: {int(coverage * 100)}% coverage", fg="yellow", bold=True)
    else:
        click.secho(f"❌ .gitignore: {int(coverage * 100)}% coverage", fg="red", bold=True)

    click.echo(f"   Patterns: {result.get('current_patterns', 0)}")

    if missing:
        click.secho(f"\n   Missing ({len(missing)}):", fg="yellow")
        for m in missing[:15]:
            click.echo(f"      {m['pattern']:<25} ({m['category']})")
        if len(missing) > 15:
            click.echo(f"      ... and {len(missing) - 15} more")
    click.echo()


@security.command("posture")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def posture(ctx: click.Context, as_json: bool) -> None:
    """Unified security posture score."""
    from src.core.services.security_ops import security_posture

    project_root = _resolve_project_root(ctx)
    click.secho("🔐 Computing security posture...", fg="cyan")

    result = security_posture(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    score = result.get("score", 0)
    grade = result.get("grade", "?")

    grade_colors = {"A": "green", "B": "green", "C": "yellow", "D": "red", "F": "red"}
    color = grade_colors.get(grade, "white")

    click.echo()
    click.secho("═" * 60, fg="cyan")
    click.secho(f"  SECURITY POSTURE: {score}/100 — Grade {grade}", fg=color, bold=True)
    click.secho("═" * 60, fg="cyan")
    click.echo()

    # Score bar
    bar_len = 40
    filled = int(score / 100 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)
    click.echo(f"  [{bar}] {score}%")
    click.echo()

    # Per-check results
    for check in result.get("checks", []):
        icon = "✅" if check["passed"] else "❌"
        chk_score = int(check["score"] * 100)
        chk_color = "green" if check["passed"] else "red"
        click.secho(
            f"  {icon} {check['name']:<25} {chk_score:>3}%  (weight: {check['weight']})",
            fg=chk_color,
        )
        click.echo(f"     {check['details']}")

    # Recommendations
    recs = result.get("recommendations", [])
    if recs:
        click.echo()
        click.secho("  💡 Recommendations:", fg="yellow", bold=True)
        for i, rec in enumerate(recs[:7], 1):
            click.echo(f"     {i}. {rec}")

    click.echo()
