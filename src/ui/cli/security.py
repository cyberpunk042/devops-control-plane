"""
CLI commands for Security integration.

Thin wrappers over ``src.core.services.security_ops``.
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


def _detect_stack_names(project_root: Path) -> list[str]:
    """Load project and return unique stack names."""
    try:
        from src.core.config.loader import load_project
        from src.core.config.stack_loader import discover_stacks
        from src.core.services.detection import detect_modules

        project = load_project(project_root / "project.yml")
        stacks = discover_stacks(project_root / "stacks")
        detection = detect_modules(project, project_root, stacks)
        return list({m.effective_stack for m in detection.modules if m.effective_stack})
    except Exception:
        return []


@click.group()
def security() -> None:
    """Security — secret scanning, .gitignore management, posture analysis."""


# ── Detect ──────────────────────────────────────────────────────


@security.command("scan")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def scan(ctx: click.Context, as_json: bool) -> None:
    """Scan source code for hardcoded secrets."""
    from src.core.services.security_ops import scan_secrets

    project_root = _resolve_project_root(ctx)
    click.secho("🔍 Scanning for hardcoded secrets...", fg="cyan")

    result = scan_secrets(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    findings = result.get("findings", [])
    summary = result.get("summary", {})

    if summary.get("total", 0) == 0:
        click.secho(
            f"✅ No secrets found ({result['files_scanned']} files scanned)",
            fg="green",
            bold=True,
        )
        return

    # Group by severity
    severity_colors = {"critical": "red", "high": "red", "medium": "yellow"}
    severity_icons = {"critical": "🚨", "high": "⚠️", "medium": "ℹ️"}

    click.secho(
        f"{'🚨' if summary.get('critical') else '⚠️'} "
        f"{summary['total']} potential secret(s) found!",
        fg="red",
        bold=True,
    )
    click.echo()

    # Show summary counts
    for sev in ("critical", "high", "medium"):
        count = summary.get(sev, 0)
        if count > 0:
            click.secho(f"   {severity_icons[sev]} {sev.title()}: {count}", fg=severity_colors[sev])

    click.echo()

    # Show individual findings (capped)
    for f in findings[:20]:
        icon = severity_icons.get(f["severity"], "ℹ️")
        color = severity_colors.get(f["severity"], "white")
        click.secho(
            f"   {icon} [{f['severity'].upper()}] {f['pattern']}",
            fg=color,
        )
        click.echo(f"      {f['file']}:{f['line']} — {f['match_preview']}")

    if len(findings) > 20:
        click.echo(f"\n   ... and {len(findings) - 20} more (use --json for full list)")

    click.echo(f"\n   Files scanned: {result['files_scanned']}")


@security.command("files")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def sensitive_files(ctx: click.Context, as_json: bool) -> None:
    """Detect sensitive files (keys, certs, credentials)."""
    from src.core.services.security_ops import detect_sensitive_files

    project_root = _resolve_project_root(ctx)
    result = detect_sensitive_files(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if result["count"] == 0:
        click.secho("✅ No sensitive files detected", fg="green", bold=True)
        return

    click.secho(f"📄 Sensitive files ({result['count']}):", fg="cyan", bold=True)
    for f in result["files"]:
        icon = "✅" if f["gitignored"] else "❌"
        status = "gitignored" if f["gitignored"] else "NOT gitignored"
        click.echo(f"   {icon} {f['path']}")
        click.echo(f"      {f['description']} — {status}")

    unprotected = result.get("unprotected", 0)
    if unprotected > 0:
        click.secho(
            f"\n   🚨 {unprotected} file(s) NOT protected by .gitignore!",
            fg="red",
            bold=True,
        )
    click.echo()


# ── Observe ─────────────────────────────────────────────────────


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


# ── Facilitate ──────────────────────────────────────────────────


@security.group("generate")
def generate() -> None:
    """Generate security configuration files."""


@generate.command("gitignore")
@click.option("--write", is_flag=True, help="Write to disk (default: preview only).")
@click.pass_context
def gen_gitignore(ctx: click.Context, write: bool) -> None:
    """Generate .gitignore from detected stacks."""
    from src.core.services.security_ops import generate_gitignore
    from src.core.services.docker_ops import write_generated_file

    project_root = _resolve_project_root(ctx)
    stack_names = _detect_stack_names(project_root)

    if not stack_names:
        click.secho("⚠️  No stacks detected, generating minimal .gitignore", fg="yellow")
        stack_names = ["python"]  # fallback

    result = generate_gitignore(project_root, stack_names)

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
