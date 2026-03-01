"""Git github — gh pulls, runs, dispatch, workflows commands."""

from __future__ import annotations

import json
import sys

import click

from . import git, _resolve_project_root


@git.group()
def gh() -> None:
    """GitHub CLI operations — PRs, Actions, workflows."""


@gh.command()
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def pulls(ctx: click.Context, as_json: bool) -> None:
    """List open pull requests."""
    from src.core.services.git_ops import gh_pulls

    project_root = _resolve_project_root(ctx)
    result = gh_pulls(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("available"):
        click.secho(f"❌ {result.get('error', 'Not available')}", fg="red")
        sys.exit(1)

    prs = result.get("pulls", [])
    if not prs:
        click.secho("No open pull requests.", fg="green")
        return

    click.secho(f"📋 Open PRs ({len(prs)}):", fg="cyan", bold=True)
    for pr in prs:
        click.echo(f"   #{pr.get('number', '?')} {pr.get('title', '?')}")
        click.echo(f"      {pr.get('headRefName', '?')} — {pr.get('author', {}).get('login', '?')}")
    click.echo()


@gh.command()
@click.option("-n", "count", default=10, type=int, help="Number of runs.")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def runs(ctx: click.Context, count: int, as_json: bool) -> None:
    """List recent workflow runs."""
    from src.core.services.git_ops import gh_actions_runs

    project_root = _resolve_project_root(ctx)
    result = gh_actions_runs(project_root, n=count)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("available"):
        click.secho(f"❌ {result.get('error', 'Not available')}", fg="red")
        sys.exit(1)

    run_list = result.get("runs", [])
    if not run_list:
        click.secho("No workflow runs found.", fg="yellow")
        return

    click.secho(f"⚡ Workflow runs ({len(run_list)}):", fg="cyan", bold=True)
    for r in run_list:
        status_icons = {"completed": "✅", "in_progress": "⏳", "queued": "⬜", "failure": "❌"}
        conclusion = r.get("conclusion", "")
        status_key = conclusion if conclusion else r.get("status", "")
        icon = status_icons.get(status_key, "❓")
        click.echo(f"   {icon} {r.get('name', '?')} [{r.get('headBranch', '?')}]")
    click.echo()


@gh.command()
@click.argument("workflow")
@click.option("--ref", default=None, help="Branch to dispatch on (default: current).")
@click.pass_context
def dispatch(ctx: click.Context, workflow: str, ref: str | None) -> None:
    """Trigger a workflow via repository dispatch."""
    from src.core.services.git_ops import gh_actions_dispatch

    project_root = _resolve_project_root(ctx)
    result = gh_actions_dispatch(project_root, workflow, ref=ref)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"✅ Dispatched: {result.get('workflow', '?')}", fg="green", bold=True)
    click.echo(f"   Ref: {result.get('ref', '?')}")


@gh.command()
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def workflows(ctx: click.Context, as_json: bool) -> None:
    """List available GitHub Actions workflows."""
    from src.core.services.git_ops import gh_actions_workflows

    project_root = _resolve_project_root(ctx)
    result = gh_actions_workflows(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("available"):
        click.secho(f"❌ {result.get('error', 'Not available')}", fg="red")
        sys.exit(1)

    wfs = result.get("workflows", [])
    if not wfs:
        click.secho("No workflows found.", fg="yellow")
        return

    click.secho(f"⚙️  Workflows ({len(wfs)}):", fg="cyan", bold=True)
    for w in wfs:
        state = w.get("state", "?")
        icon = "✅" if state == "active" else "⏸️"
        click.echo(f"   {icon} {w.get('name', '?')} [{state}]")
    click.echo()
