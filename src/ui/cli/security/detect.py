"""Security detect — scan and sensitive files commands."""

from __future__ import annotations

import json
import sys

import click

from . import security, _resolve_project_root


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
