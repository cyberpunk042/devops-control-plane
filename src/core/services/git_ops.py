"""
Git & GitHub operations — channel-independent service.

Provides Git status, log, commit, pull, push, and GitHub CLI
(pull requests, actions runs, workflow dispatch) without any
Flask or HTTP dependency.

Extracted from ``src/ui/web/routes_integrations.py`` (P7).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("git")


# ═══════════════════════════════════════════════════════════════════
#  Low-level runners
# ═══════════════════════════════════════════════════════════════════


def run_git(
    *args: str,
    cwd: Path,
    timeout: int = 15,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the result."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
    )


def run_gh(
    *args: str,
    cwd: Path,
    timeout: int = 30,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a gh CLI command and return the result."""
    return subprocess.run(
        ["gh", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        input=stdin,
    )


def repo_slug(project_root: Path) -> str | None:
    """Get the GitHub owner/repo slug from git remote."""
    r = run_git("remote", "get-url", "origin", cwd=project_root)
    if r.returncode != 0:
        return None
    url = r.stdout.strip()
    # Handle SSH: git@github.com:owner/repo.git
    if url.startswith("git@"):
        url = url.split(":", 1)[1]
    # Handle HTTPS: https://github.com/owner/repo.git
    elif "github.com/" in url:
        url = url.split("github.com/", 1)[1]
    else:
        return None
    return url.removesuffix(".git")


# ═══════════════════════════════════════════════════════════════════
#  Git operations
# ═══════════════════════════════════════════════════════════════════


def git_status(project_root: Path) -> dict:
    """Git repository status: branch, dirty files, ahead/behind tracking."""
    root = project_root

    # Current branch
    r_branch = run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
    branch = r_branch.stdout.strip() if r_branch.returncode == 0 else None

    if branch is None:
        return {"error": "Not a git repository", "available": False}

    # Commit hash
    r_hash = run_git("rev-parse", "--short", "HEAD", cwd=root)
    commit_hash = r_hash.stdout.strip() if r_hash.returncode == 0 else None

    # Dirty state — porcelain v1 for reliable parsing
    r_status = run_git("status", "--porcelain", cwd=root)
    status_lines = [
        ln for ln in r_status.stdout.strip().splitlines() if ln.strip()
    ] if r_status.returncode == 0 else []

    staged = []
    modified = []
    untracked = []
    for line in status_lines:
        if len(line) < 3:
            continue
        idx = line[0]  # index status
        wt = line[1]   # worktree status
        fname = line[3:]
        if idx in ("A", "M", "D", "R", "C"):
            staged.append(fname)
        if wt == "M":
            modified.append(fname)
        elif wt == "?":
            untracked.append(fname)

    dirty = len(status_lines) > 0

    # Ahead/behind remote tracking branch
    ahead = 0
    behind = 0
    r_ab = run_git(
        "rev-list", "--left-right", "--count", "HEAD...@{u}", cwd=root,
    )
    if r_ab.returncode == 0:
        parts = r_ab.stdout.strip().split()
        if len(parts) == 2:
            ahead = int(parts[0])
            behind = int(parts[1])

    # Last commit info
    r_last = run_git(
        "log", "-1", "--format=%H%n%h%n%s%n%an%n%aI", cwd=root,
    )
    last_commit = None
    if r_last.returncode == 0:
        lines = r_last.stdout.strip().splitlines()
        if len(lines) >= 5:
            last_commit = {
                "hash": lines[0],
                "short_hash": lines[1],
                "message": lines[2],
                "author": lines[3],
                "date": lines[4],
            }

    # Remote URL
    r_remote = run_git("remote", "get-url", "origin", cwd=root)
    remote_url = r_remote.stdout.strip() if r_remote.returncode == 0 else None

    return {
        "available": True,
        "branch": branch,
        "commit": commit_hash,
        "dirty": dirty,
        "staged_count": len(staged),
        "modified_count": len(modified),
        "untracked_count": len(untracked),
        "total_changes": len(status_lines),
        "staged": staged[:20],         # cap for UI
        "modified": modified[:20],
        "untracked": untracked[:20],
        "ahead": ahead,
        "behind": behind,
        "last_commit": last_commit,
        "remote_url": remote_url,
    }


def git_log(project_root: Path, *, n: int = 10) -> dict:
    """Recent commit history."""
    n = min(n, 50)  # cap

    r = run_git(
        "log", f"-{n}", "--format=%H%n%h%n%s%n%an%n%aI%n---",
        cwd=project_root,
    )
    if r.returncode != 0:
        return {"error": "Failed to read git log", "commits": []}

    commits = []
    entries = r.stdout.strip().split("\n---\n")
    for entry in entries:
        lines = entry.strip().splitlines()
        if len(lines) >= 5:
            commits.append({
                "hash": lines[0],
                "short_hash": lines[1],
                "message": lines[2],
                "author": lines[3],
                "date": lines[4],
            })

    return {"commits": commits}


def git_commit(
    project_root: Path,
    message: str,
    *,
    files: list[str] | None = None,
) -> dict:
    """Stage and commit changes.

    Args:
        project_root: Repository root.
        message: Commit message.
        files: Optional list of files to stage (default: all).

    Returns:
        {"ok": True, "hash": ..., "message": ...} on success,
        {"error": ...} on failure.
    """
    if not message.strip():
        return {"error": "Commit message is required"}

    root = project_root

    # Stage
    if files:
        for f in files:
            run_git("add", f, cwd=root)
    else:
        run_git("add", "-A", cwd=root)

    # Check if there's anything to commit
    r_diff = run_git("diff", "--cached", "--quiet", cwd=root)
    if r_diff.returncode == 0:
        return {"error": "Nothing to commit (no staged changes)"}

    # Commit
    r = run_git("commit", "-m", message, cwd=root, timeout=30)
    if r.returncode != 0:
        return {"error": f"Commit failed: {r.stderr.strip()}"}

    # Get the new commit hash
    r_hash = run_git("rev-parse", "--short", "HEAD", cwd=root)
    new_hash = r_hash.stdout.strip() if r_hash.returncode == 0 else "?"

    return {"ok": True, "hash": new_hash, "message": message}


def git_pull(project_root: Path, *, rebase: bool = False) -> dict:
    """Pull from remote."""
    args = ["pull"]
    if rebase:
        args.append("--rebase")

    r = run_git(*args, cwd=project_root, timeout=60)
    if r.returncode != 0:
        return {"error": f"Pull failed: {r.stderr.strip()}"}

    return {"ok": True, "output": r.stdout.strip()}


def git_push(project_root: Path, *, force: bool = False) -> dict:
    """Push to remote."""
    root = project_root
    args = ["push"]
    if force:
        args.append("--force-with-lease")

    r = run_git(*args, cwd=root, timeout=60)
    if r.returncode != 0:
        stderr = r.stderr.strip()
        # Common case: no upstream configured
        if "no upstream branch" in stderr.lower() or "has no upstream" in stderr.lower():
            # Get current branch and set upstream
            r_branch = run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
            branch = r_branch.stdout.strip()
            r2 = run_git("push", "--set-upstream", "origin", branch, cwd=root, timeout=60)
            if r2.returncode != 0:
                return {"error": f"Push failed: {r2.stderr.strip()}"}
            return {"ok": True, "output": r2.stdout.strip() or r2.stderr.strip()}
        return {"error": f"Push failed: {stderr}"}

    return {"ok": True, "output": r.stdout.strip() or r.stderr.strip()}


# ═══════════════════════════════════════════════════════════════════
# Re-exports — backward compatibility
# ═══════════════════════════════════════════════════════════════════

from src.core.services.git_gh_ops import (  # noqa: F401, E402
    gh_status,
    gh_pulls,
    gh_actions_runs,
    gh_actions_dispatch,
    gh_actions_workflows,
    gh_user,
    gh_repo_info,
    gh_auth_logout,
    gh_repo_create,
    gh_repo_set_visibility,
    git_remote_remove,
    git_remotes,
    git_remote_add,
    git_remote_rename,
    git_remote_set_url,
    gh_repo_set_default_branch,
)

