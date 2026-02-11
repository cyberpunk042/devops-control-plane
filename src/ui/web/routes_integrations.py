"""
Integration routes — Git, GitHub, and CI/CD endpoints.

Blueprint: integrations_bp
Prefix: /api

Endpoints:
    GET  /git/status          — branch, dirty state, ahead/behind
    GET  /git/log             — recent commit history
    POST /git/commit          — stage + commit
    POST /git/pull            — pull from remote
    POST /git/push            — push to remote
    GET  /gh/pulls            — open pull requests
    GET  /gh/actions/runs     — recent workflow runs
    POST /gh/actions/dispatch — trigger a workflow
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

logger = logging.getLogger(__name__)

integrations_bp = Blueprint("integrations", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


def _run_git(
    *args: str,
    cwd: Path | None = None,
    timeout: int = 15,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the result."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd or _project_root()),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
    )


def _run_gh(
    *args: str,
    cwd: Path | None = None,
    timeout: int = 30,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a gh CLI command and return the result."""
    return subprocess.run(
        ["gh", *args],
        cwd=str(cwd or _project_root()),
        capture_output=True,
        text=True,
        timeout=timeout,
        input=stdin,
    )


def _repo_slug() -> str | None:
    """Get the GitHub owner/repo slug from git remote."""
    r = _run_git("remote", "get-url", "origin")
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


# ── Git Status ──────────────────────────────────────────────────────


@integrations_bp.route("/git/status")
def git_status():  # type: ignore[no-untyped-def]
    """Git repository status: branch, dirty files, ahead/behind tracking."""
    root = _project_root()

    # Current branch
    r_branch = _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
    branch = r_branch.stdout.strip() if r_branch.returncode == 0 else None

    if branch is None:
        return jsonify({"error": "Not a git repository", "available": False}), 200

    # Commit hash
    r_hash = _run_git("rev-parse", "--short", "HEAD", cwd=root)
    commit_hash = r_hash.stdout.strip() if r_hash.returncode == 0 else None

    # Dirty state — porcelain v1 for reliable parsing
    r_status = _run_git("status", "--porcelain", cwd=root)
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
    r_ab = _run_git(
        "rev-list", "--left-right", "--count", f"HEAD...@{{u}}", cwd=root,
    )
    if r_ab.returncode == 0:
        parts = r_ab.stdout.strip().split()
        if len(parts) == 2:
            ahead = int(parts[0])
            behind = int(parts[1])

    # Last commit info
    r_last = _run_git(
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
    r_remote = _run_git("remote", "get-url", "origin", cwd=root)
    remote_url = r_remote.stdout.strip() if r_remote.returncode == 0 else None

    return jsonify({
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
    })


# ── Git Log ─────────────────────────────────────────────────────────


@integrations_bp.route("/git/log")
def git_log():  # type: ignore[no-untyped-def]
    """Recent commit history."""
    n = request.args.get("n", 10, type=int)
    n = min(n, 50)  # cap

    r = _run_git(
        "log", f"-{n}", "--format=%H%n%h%n%s%n%an%n%aI%n---",
        cwd=_project_root(),
    )
    if r.returncode != 0:
        return jsonify({"error": "Failed to read git log", "commits": []}), 200

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

    return jsonify({"commits": commits})


# ── Git Commit ──────────────────────────────────────────────────────


@integrations_bp.route("/git/commit", methods=["POST"])
def git_commit():  # type: ignore[no-untyped-def]
    """Stage and commit changes.

    JSON body:
        message: commit message (required)
        files: optional list of files to stage (default: all)
    """
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "Commit message is required"}), 400

    root = _project_root()
    files = data.get("files")

    # Stage
    if files:
        for f in files:
            _run_git("add", f, cwd=root)
    else:
        _run_git("add", "-A", cwd=root)

    # Check if there's anything to commit
    r_diff = _run_git("diff", "--cached", "--quiet", cwd=root)
    if r_diff.returncode == 0:
        return jsonify({"error": "Nothing to commit (no staged changes)"}), 400

    # Commit
    r = _run_git("commit", "-m", message, cwd=root, timeout=30)
    if r.returncode != 0:
        return jsonify({"error": f"Commit failed: {r.stderr.strip()}"}), 400

    # Get the new commit hash
    r_hash = _run_git("rev-parse", "--short", "HEAD", cwd=root)
    new_hash = r_hash.stdout.strip() if r_hash.returncode == 0 else "?"

    return jsonify({
        "ok": True,
        "hash": new_hash,
        "message": message,
    })


# ── Git Pull ────────────────────────────────────────────────────────


@integrations_bp.route("/git/pull", methods=["POST"])
def git_pull():  # type: ignore[no-untyped-def]
    """Pull from remote."""
    root = _project_root()
    data = request.get_json(silent=True) or {}
    rebase = data.get("rebase", False)

    args = ["pull"]
    if rebase:
        args.append("--rebase")

    r = _run_git(*args, cwd=root, timeout=60)
    if r.returncode != 0:
        return jsonify({"error": f"Pull failed: {r.stderr.strip()}"}), 400

    return jsonify({
        "ok": True,
        "output": r.stdout.strip(),
    })


# ── Git Push ────────────────────────────────────────────────────────


@integrations_bp.route("/git/push", methods=["POST"])
def git_push():  # type: ignore[no-untyped-def]
    """Push to remote."""
    root = _project_root()
    data = request.get_json(silent=True) or {}
    force = data.get("force", False)

    args = ["push"]
    if force:
        args.append("--force-with-lease")

    r = _run_git(*args, cwd=root, timeout=60)
    if r.returncode != 0:
        stderr = r.stderr.strip()
        # Common case: no upstream configured
        if "no upstream branch" in stderr.lower() or "has no upstream" in stderr.lower():
            # Get current branch and set upstream
            r_branch = _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
            branch = r_branch.stdout.strip()
            r2 = _run_git("push", "--set-upstream", "origin", branch, cwd=root, timeout=60)
            if r2.returncode != 0:
                return jsonify({"error": f"Push failed: {r2.stderr.strip()}"}), 400
            return jsonify({"ok": True, "output": r2.stdout.strip() or r2.stderr.strip()})
        return jsonify({"error": f"Push failed: {stderr}"}), 400

    return jsonify({
        "ok": True,
        "output": r.stdout.strip() or r.stderr.strip(),
    })


# ── GitHub: Pull Requests ───────────────────────────────────────────


@integrations_bp.route("/integrations/gh/status")
def gh_status_extended():  # type: ignore[no-untyped-def]
    """Extended GitHub status — version, repo, auth details.

    Note: Basic gh status (installed/authenticated) is already served by
    routes_secrets.py at /api/gh/status. This endpoint adds richer data
    for the integrations card.
    """
    import shutil

    if not shutil.which("gh"):
        return jsonify({
            "available": False,
            "error": "gh CLI not installed",
        })

    # Get version
    r = _run_gh("--version")
    version = r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else "unknown"

    # Check auth
    r_auth = _run_gh("auth", "status")
    authenticated = r_auth.returncode == 0

    repo = _repo_slug()

    return jsonify({
        "available": True,
        "version": version,
        "authenticated": authenticated,
        "auth_detail": r_auth.stdout.strip() or r_auth.stderr.strip(),
        "repo": repo,
    })


@integrations_bp.route("/gh/pulls")
def gh_pulls():  # type: ignore[no-untyped-def]
    """List open pull requests."""
    repo = _repo_slug()
    if not repo:
        return jsonify({"available": False, "error": "No GitHub remote configured"})

    r = _run_gh(
        "pr", "list", "--json", "number,title,author,createdAt,url,headRefName,state",
        "--limit", "10",
        "-R", repo,
    )
    if r.returncode != 0:
        return jsonify({"available": False, "error": r.stderr.strip()})

    try:
        pulls = json.loads(r.stdout)
    except (json.JSONDecodeError, ValueError):
        pulls = []

    return jsonify({
        "available": True,
        "pulls": pulls,
    })


# ── GitHub: Actions ─────────────────────────────────────────────────


@integrations_bp.route("/gh/actions/runs")
def gh_actions_runs():  # type: ignore[no-untyped-def]
    """Recent workflow run history."""
    repo = _repo_slug()
    if not repo:
        return jsonify({"available": False, "error": "No GitHub remote configured"})

    n = request.args.get("n", 10, type=int)
    n = min(n, 30)

    r = _run_gh(
        "run", "list",
        "--json", "databaseId,name,status,conclusion,createdAt,updatedAt,url,headBranch,event",
        "--limit", str(n),
        "-R", repo,
    )
    if r.returncode != 0:
        return jsonify({"available": False, "error": r.stderr.strip()})

    try:
        runs = json.loads(r.stdout)
    except (json.JSONDecodeError, ValueError):
        runs = []

    return jsonify({
        "available": True,
        "runs": runs,
    })


@integrations_bp.route("/gh/actions/dispatch", methods=["POST"])
def gh_actions_dispatch():  # type: ignore[no-untyped-def]
    """Trigger a workflow via repository dispatch.

    JSON body:
        workflow: workflow filename (e.g., "ci.yml")
        ref: branch (default: current branch)
    """
    repo = _repo_slug()
    if not repo:
        return jsonify({"error": "No GitHub remote configured"}), 400

    data = request.get_json(silent=True) or {}
    workflow = data.get("workflow", "")
    if not workflow:
        return jsonify({"error": "Missing 'workflow' field"}), 400

    ref = data.get("ref")
    if not ref:
        r_branch = _run_git("rev-parse", "--abbrev-ref", "HEAD")
        ref = r_branch.stdout.strip() if r_branch.returncode == 0 else "main"

    r = _run_gh(
        "workflow", "run", workflow,
        "--ref", ref,
        "-R", repo,
    )
    if r.returncode != 0:
        return jsonify({"error": f"Dispatch failed: {r.stderr.strip()}"}), 400

    return jsonify({
        "ok": True,
        "workflow": workflow,
        "ref": ref,
    })


# ── GitHub: Workflows list ──────────────────────────────────────────


@integrations_bp.route("/gh/actions/workflows")
def gh_actions_workflows():  # type: ignore[no-untyped-def]
    """List available workflows."""
    repo = _repo_slug()
    if not repo:
        return jsonify({"available": False, "error": "No GitHub remote configured"})

    r = _run_gh(
        "workflow", "list",
        "--json", "id,name,state",
        "-R", repo,
    )
    if r.returncode != 0:
        return jsonify({"available": False, "error": r.stderr.strip()})

    try:
        workflows = json.loads(r.stdout)
    except (json.JSONDecodeError, ValueError):
        workflows = []

    return jsonify({
        "available": True,
        "workflows": workflows,
    })
