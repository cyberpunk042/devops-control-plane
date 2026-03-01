"""K8s generate — manifest generation commands."""

from __future__ import annotations

import sys

import click

from . import k8s, _resolve_project_root


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
