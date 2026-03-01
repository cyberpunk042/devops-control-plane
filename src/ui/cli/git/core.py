"""Git core — status, log, commit, pull, push commands."""

from __future__ import annotations

import json
import sys

import click

from . import git, _resolve_project_root


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
