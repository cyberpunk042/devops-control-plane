"""K8s observe — cluster and get resources commands."""

from __future__ import annotations

import json
import sys

import click

from . import k8s, _resolve_project_root


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
