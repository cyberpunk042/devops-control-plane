"""
CLI commands for Kubernetes integration.

Thin wrappers over ``src.core.services.k8s_ops``.
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


@click.group("k8s")
def k8s() -> None:
    """Kubernetes — manifests, validation, cluster status, generation."""


# ── Detect ──────────────────────────────────────────────────────


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


# ── Observe ─────────────────────────────────────────────────────


@k8s.command("cluster")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def cluster(ctx: click.Context, as_json: bool) -> None:
    """Show cluster connection status, nodes, and namespaces."""
    from src.core.services.k8s_ops import cluster_status

    result = cluster_status()

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("connected"):
        click.secho("❌ Not connected to any cluster", fg="red")
        if result.get("error"):
            click.echo(f"   {result['error']}")
        return

    click.secho(f"☸️  Cluster: {result.get('context', '?')}", fg="green", bold=True)
    click.echo()

    # Nodes
    nodes = result.get("nodes", [])
    if nodes:
        click.secho(f"   Nodes ({len(nodes)}):", fg="cyan")
        for node in nodes:
            icon = "✅" if node.get("ready") else "❌"
            click.echo(
                f"      {icon} {node['name']} "
                f"({node.get('roles', 'worker')}) "
                f"{node.get('version', '')}"
            )

    # Namespaces
    ns = result.get("namespaces", [])
    if ns:
        click.echo()
        click.echo(f"   Namespaces: {', '.join(ns[:15])}")
        if len(ns) > 15:
            click.echo(f"   ... and {len(ns) - 15} more")

    click.echo()


@k8s.command("get")
@click.argument("kind", default="pods")
@click.option("-n", "namespace", default="default", help="Namespace.")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def get_resources(
    ctx: click.Context, kind: str, namespace: str, as_json: bool
) -> None:
    """Get resources from the cluster (pods, deployments, services, ...)."""
    from src.core.services.k8s_ops import get_resources as _get_resources

    result = _get_resources(namespace=namespace, kind=kind)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("ok"):
        click.secho(f"❌ {result.get('error', 'Unknown error')}", fg="red")
        sys.exit(1)

    resources = result.get("resources", [])
    click.secho(
        f"☸️  {kind} in {namespace} ({result['count']}):",
        fg="cyan",
        bold=True,
    )

    for r in resources:
        phase = r.get("phase", "")
        icon = "✅" if phase in ("Running", "Succeeded", "Active", "Bound") else "⚠️"
        click.echo(f"   {icon} {r['name']} — {phase}")

    click.echo()


# ── Facilitate ──────────────────────────────────────────────────


@k8s.group("generate")
def generate() -> None:
    """Generate Kubernetes manifests."""


@generate.command("manifests")
@click.argument("app_name")
@click.option("--image", default="", help="Container image.")
@click.option("--port", default=8080, type=int, help="Container port.")
@click.option("--replicas", default=2, type=int, help="Number of replicas.")
@click.option("--service-type", default="ClusterIP", help="Service type.")
@click.option("--host", default="", help="Ingress hostname (generates Ingress if set).")
@click.option("--namespace", default="", help="Namespace (generates Namespace if set).")
@click.option("--write", is_flag=True, help="Write to disk.")
@click.pass_context
def gen_manifests(
    ctx: click.Context,
    app_name: str,
    image: str,
    port: int,
    replicas: int,
    service_type: str,
    host: str,
    namespace: str,
    write: bool,
) -> None:
    """Generate Deployment, Service, and optional Ingress manifests."""
    from src.core.services.k8s_ops import generate_manifests
    from src.core.services.docker_ops import write_generated_file

    project_root = _resolve_project_root(ctx)

    result = generate_manifests(
        project_root,
        app_name,
        image=image,
        port=port,
        replicas=replicas,
        service_type=service_type,
        host=host,
        namespace=namespace,
    )

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    for file_data in result["files"]:
        if write:
            wr = write_generated_file(project_root, file_data)
            if "error" in wr:
                click.secho(f"❌ {wr['error']}", fg="red")
            else:
                click.secho(f"✅ Written: {wr['path']}", fg="green")
        else:
            click.secho(f"\n📄 {file_data['path']}", fg="cyan", bold=True)
            click.echo(f"   {file_data.get('reason', '')}")
            click.echo("─" * 60)
            click.echo(file_data["content"])

    if not write:
        click.echo("─" * 60)
        click.secho("   (use --write to save files to disk)", fg="yellow")
