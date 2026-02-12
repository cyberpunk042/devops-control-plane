"""
CLI commands for Git & GitHub integration.

Thin wrappers over ``src.core.services.git_ops``.
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


@click.group()
def git() -> None:
    """Git & GitHub — status, commit, push, pull requests, actions."""


# ── Git ─────────────────────────────────────────────────────────

@git.command()
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def status(ctx: click.Context, as_json: bool) -> None:
    """Show git status: branch, dirty state, ahead/behind."""
    from src.core.services.git_ops import git_status

    project_root = _resolve_project_root(ctx)
    result = git_status(project_root)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if not result.get("available"):
        click.secho(f"❌ {result.get('error', 'Not a git repository')}", fg="red")
        sys.exit(1)

    branch = result.get("branch", "?")
    commit = result.get("commit", "?")
    dirty = "dirty" if result.get("dirty") else "clean"
    dirty_color = "yellow" if result.get("dirty") else "green"

    click.secho(f"🌿 {branch}", fg="cyan", bold=True, nl=False)
    click.echo(f" @ {commit}")
    click.secho(f"   State: {dirty}", fg=dirty_color)

    ahead = result.get("ahead", 0)
    behind = result.get("behind", 0)
    if ahead or behind:
        click.echo(f"   ↑ ahead {ahead}  ↓ behind {behind}")

    if result.get("staged_count"):
        click.echo(f"   Staged: {result['staged_count']}")
    if result.get("modified_count"):
        click.echo(f"   Modified: {result['modified_count']}")
    if result.get("untracked_count"):
        click.echo(f"   Untracked: {result['untracked_count']}")

    lc = result.get("last_commit")
    if lc:
        click.echo(f"   Last: {lc['message'][:60]} ({lc['author']}, {lc['date'][:10]})")
    click.echo()


@git.command()
@click.option("-n", "count", default=10, type=int, help="Number of commits.")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def log(ctx: click.Context, count: int, as_json: bool) -> None:
    """Show recent commit history."""
    from src.core.services.git_ops import git_log

    project_root = _resolve_project_root(ctx)
    result = git_log(project_root, n=count)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    commits = result.get("commits", [])
    if not commits:
        click.secho("No commits found.", fg="yellow")
        return

    for c in commits:
        click.secho(f"  {c['short_hash']}", fg="yellow", nl=False)
        click.echo(f"  {c['message'][:70]}")
        click.echo(f"         {c['author']} — {c['date'][:10]}")
    click.echo()


@git.command()
@click.argument("message")
@click.option("--files", "-f", multiple=True, help="Specific files to stage.")
@click.pass_context
def commit(ctx: click.Context, message: str, files: tuple[str, ...]) -> None:
    """Stage and commit changes."""
    from src.core.services.git_ops import git_commit

    project_root = _resolve_project_root(ctx)
    file_list = list(files) if files else None
    result = git_commit(project_root, message, files=file_list)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho(f"✅ Committed: {result.get('hash', '?')}", fg="green", bold=True)
    click.echo(f"   Message: {result.get('message', '')}")


@git.command()
@click.option("--rebase", is_flag=True, help="Pull with rebase.")
@click.pass_context
def pull(ctx: click.Context, rebase: bool) -> None:
    """Pull from remote."""
    from src.core.services.git_ops import git_pull

    project_root = _resolve_project_root(ctx)
    result = git_pull(project_root, rebase=rebase)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho("✅ Pulled", fg="green")
    if result.get("output"):
        click.echo(f"   {result['output'][:200]}")


@git.command()
@click.option("--force", is_flag=True, help="Force push (with lease).")
@click.pass_context
def push(ctx: click.Context, force: bool) -> None:
    """Push to remote."""
    from src.core.services.git_ops import git_push

    project_root = _resolve_project_root(ctx)
    result = git_push(project_root, force=force)

    if "error" in result:
        click.secho(f"❌ {result['error']}", fg="red")
        sys.exit(1)

    click.secho("✅ Pushed", fg="green")
    if result.get("output"):
        click.echo(f"   {result['output'][:200]}")


# ── GitHub ──────────────────────────────────────────────────────

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
