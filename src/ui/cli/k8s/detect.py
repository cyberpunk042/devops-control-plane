"""K8s detect — status and validate commands."""

from __future__ import annotations

import json
import sys

import click

from . import k8s, _resolve_project_root


@k8s.command("status")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def status(ctx: click.Context, as_json: bool) -> None:
    """Show Kubernetes manifest status and kubectl availability."""
    from src.core.services.k8s_ops import k8s_status

    project_root = _resolve_project_root(ctx)
    result = k8s_status(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    click.secho("☸️  Kubernetes Status:", fg="cyan", bold=True)
    click.echo()

    # kubectl
    kubectl = result.get("kubectl", {})
    if kubectl.get("available"):
        click.secho(f"   🔧 kubectl: {kubectl.get('version', '?')}", fg="green")
    else:
        click.secho("   🔧 kubectl: not available", fg="yellow")

    # Manifest directories
    dirs = result.get("manifest_dirs", [])
    if dirs:
        click.echo(f"   📁 Manifest dirs: {', '.join(dirs)}")

    # Resources
    summary = result.get("resource_summary", {})
    total = result.get("total_resources", 0)

    if total > 0:
        click.secho(f"\n   📦 Resources ({total}):", fg="cyan")
        for kind, count in sorted(summary.items()):
            click.echo(f"      {kind}: {count}")

        click.echo()
        for manifest in result.get("manifests", []):
            click.echo(f"   📄 {manifest['path']} ({manifest['count']} resources)")
    else:
        click.echo("\n   📦 No Kubernetes manifests detected")

    # Helm
    helm = result.get("helm_charts", [])
    if helm:
        click.echo()
        click.secho("   ⎈ Helm Charts:", fg="cyan")
        for chart in helm:
            click.echo(f"      {chart['name']} v{chart.get('version', '?')} ({chart['path']}/)")

    # Kustomize
    kustomize = result.get("kustomize", {})
    if kustomize.get("exists"):
        click.secho(f"\n   🔧 Kustomize: {kustomize['path']}", fg="green")

    click.echo()


@k8s.command("validate")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def validate(ctx: click.Context, as_json: bool) -> None:
    """Validate Kubernetes manifests (structure, best practices)."""
    from src.core.services.k8s_ops import validate_manifests

    project_root = _resolve_project_root(ctx)

    click.secho("🔍 Validating manifests...", fg="cyan")

    result = validate_manifests(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if result.get("files_checked", 0) == 0:
        click.secho("❌ No manifests found to validate", fg="yellow")
        return

    ok = result.get("ok", False)
    errors = result.get("errors", 0)
    warnings = result.get("warnings", 0)

    if ok and warnings == 0:
        click.secho(
            f"✅ All manifests valid ({result['files_checked']} files)",
            fg="green",
            bold=True,
        )
    elif ok:
        click.secho(
            f"⚠️  {warnings} warning(s), 0 errors ({result['files_checked']} files)",
            fg="yellow",
            bold=True,
        )
    else:
        click.secho(
            f"❌ {errors} error(s), {warnings} warning(s)",
            fg="red",
            bold=True,
        )

    severity_colors = {"error": "red", "warning": "yellow", "info": "white"}
    severity_icons = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}

    issues = result.get("issues", [])
    if issues:
        click.echo()
        for issue in issues[:25]:
            sev = issue["severity"]
            click.secho(
                f"   {severity_icons.get(sev, '?')} [{sev.upper()}] {issue['file']}",
                fg=severity_colors.get(sev, "white"),
            )
            click.echo(f"      {issue['message']}")

        if len(issues) > 25:
            click.echo(f"\n   ... and {len(issues) - 25} more")

    click.echo()
