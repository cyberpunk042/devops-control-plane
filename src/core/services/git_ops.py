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
#  GitHub CLI operations
# ═══════════════════════════════════════════════════════════════════


def gh_status(project_root: Path) -> dict:
    """Extended GitHub status — version, repo, auth details."""
    if not shutil.which("gh"):
        return {"available": False, "error": "gh CLI not installed"}

    # Get version
    r = run_gh("--version", cwd=project_root)
    version = (
        r.stdout.strip().splitlines()[0]
        if r.returncode == 0 and r.stdout.strip()
        else "unknown"
    )

    # Check auth
    r_auth = run_gh("auth", "status", cwd=project_root)
    authenticated = r_auth.returncode == 0

    slug = repo_slug(project_root)

    return {
        "available": True,
        "version": version,
        "authenticated": authenticated,
        "auth_detail": r_auth.stdout.strip() or r_auth.stderr.strip(),
        "repo": slug,
    }


def gh_pulls(project_root: Path) -> dict:
    """List open pull requests."""
    slug = repo_slug(project_root)
    if not slug:
        return {"available": False, "error": "No GitHub remote configured"}

    r = run_gh(
        "pr", "list", "--json", "number,title,author,createdAt,url,headRefName,state",
        "--limit", "10",
        "-R", slug,
        cwd=project_root,
    )
    if r.returncode != 0:
        return {"available": False, "error": r.stderr.strip()}

    try:
        pulls = json.loads(r.stdout)
    except (json.JSONDecodeError, ValueError):
        pulls = []

    return {"available": True, "pulls": pulls}


def gh_actions_runs(project_root: Path, *, n: int = 10) -> dict:
    """Recent workflow run history."""
    slug = repo_slug(project_root)
    if not slug:
        return {"available": False, "error": "No GitHub remote configured"}

    n = min(n, 30)

    r = run_gh(
        "run", "list",
        "--json", "databaseId,name,status,conclusion,createdAt,updatedAt,url,headBranch,event",
        "--limit", str(n),
        "-R", slug,
        cwd=project_root,
    )
    if r.returncode != 0:
        return {"available": False, "error": r.stderr.strip()}

    try:
        runs = json.loads(r.stdout)
    except (json.JSONDecodeError, ValueError):
        runs = []

    return {"available": True, "runs": runs}


def gh_actions_dispatch(
    project_root: Path,
    workflow: str,
    *,
    ref: str | None = None,
) -> dict:
    """Trigger a workflow via repository dispatch."""
    slug = repo_slug(project_root)
    if not slug:
        return {"error": "No GitHub remote configured"}

    if not workflow:
        return {"error": "Missing 'workflow' field"}

    if not ref:
        r_branch = run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=project_root)
        ref = r_branch.stdout.strip() if r_branch.returncode == 0 else "main"

    r = run_gh(
        "workflow", "run", workflow,
        "--ref", ref,
        "-R", slug,
        cwd=project_root,
    )
    if r.returncode != 0:
        return {"error": f"Dispatch failed: {r.stderr.strip()}"}

    return {"ok": True, "workflow": workflow, "ref": ref}


def gh_actions_workflows(project_root: Path) -> dict:
    """List available workflows."""
    slug = repo_slug(project_root)
    if not slug:
        return {"available": False, "error": "No GitHub remote configured"}

    r = run_gh(
        "workflow", "list",
        "--json", "id,name,state",
        "-R", slug,
        cwd=project_root,
    )
    if r.returncode != 0:
        return {"available": False, "error": r.stderr.strip()}

    try:
        workflows = json.loads(r.stdout)
    except (json.JSONDecodeError, ValueError):
        workflows = []

    return {"available": True, "workflows": workflows}


# ═══════════════════════════════════════════════════════════════════
#  GitHub: Account & Repository management
# ═══════════════════════════════════════════════════════════════════


def gh_user(project_root: Path) -> dict:
    """Get the currently authenticated GitHub user."""
    if not shutil.which("gh"):
        return {"available": False, "error": "gh CLI not installed"}

    r = run_gh("api", "user", "--jq", ".login", cwd=project_root, timeout=10)
    if r.returncode != 0:
        return {"available": False, "error": r.stderr.strip() or "Not authenticated"}

    login = r.stdout.strip()
    if not login:
        return {"available": False, "error": "Not authenticated"}

    # Get more user details
    r2 = run_gh(
        "api", "user", "--jq", "[.login, .name, .avatar_url, .html_url] | @tsv",
        cwd=project_root, timeout=10,
    )
    if r2.returncode == 0 and r2.stdout.strip():
        parts = r2.stdout.strip().split("\t")
        return {
            "available": True,
            "login": parts[0] if len(parts) > 0 else login,
            "name": parts[1] if len(parts) > 1 else "",
            "avatar_url": parts[2] if len(parts) > 2 else "",
            "html_url": parts[3] if len(parts) > 3 else "",
        }

    return {"available": True, "login": login}


def gh_repo_info(project_root: Path) -> dict:
    """Get detailed repository info: visibility, description, topics, default branch."""
    slug = repo_slug(project_root)
    if not slug:
        return {"available": False, "error": "No GitHub remote configured"}

    r = run_gh(
        "repo", "view", slug, "--json",
        "name,owner,visibility,description,defaultBranchRef,isPrivate,isFork,url,sshUrl,homepageUrl",
        cwd=project_root, timeout=15,
    )
    if r.returncode != 0:
        return {"available": False, "error": r.stderr.strip(), "slug": slug}

    try:
        data = json.loads(r.stdout)
    except (json.JSONDecodeError, ValueError):
        return {"available": False, "error": "Failed to parse repo info", "slug": slug}

    return {
        "available": True,
        "slug": slug,
        "name": data.get("name", ""),
        "owner": (data.get("owner", {}) or {}).get("login", ""),
        "visibility": (data.get("visibility") or "").upper(),  # PUBLIC / PRIVATE
        "is_private": data.get("isPrivate", False),
        "is_fork": data.get("isFork", False),
        "description": data.get("description", "") or "",
        "default_branch": (data.get("defaultBranchRef") or {}).get("name", "main"),
        "url": data.get("url", ""),
        "ssh_url": data.get("sshUrl", ""),
        "homepage_url": data.get("homepageUrl", "") or "",
    }


def gh_auth_logout(project_root: Path) -> dict:
    """Logout from GitHub CLI."""
    if not shutil.which("gh"):
        return {"error": "gh CLI not installed"}

    # Determine current hostname
    r_host = run_gh("auth", "status", cwd=project_root)
    # Default to github.com
    hostname = "github.com"

    r = run_gh(
        "auth", "logout", "--hostname", hostname,
        cwd=project_root, timeout=10,
        stdin="Y\n",  # confirm logout
    )
    if r.returncode != 0:
        err = r.stderr.strip()
        # "not logged in" is success for us
        if "not logged in" in err.lower():
            return {"ok": True, "message": "Already logged out"}
        return {"error": f"Logout failed: {err}"}

    return {"ok": True, "message": f"Logged out from {hostname}"}


def gh_repo_create(
    project_root: Path,
    name: str,
    *,
    private: bool = True,
    description: str = "",
    add_remote: bool = True,
) -> dict:
    """Create a new GitHub repository and optionally add it as origin.

    Args:
        project_root: Local project directory.
        name: Repository name (e.g. 'my-project' or 'org/my-project').
        private: Whether the repo should be private (default True).
        description: Optional repository description.
        add_remote: Whether to set the new repo as git remote origin.
    """
    if not name.strip():
        return {"error": "Repository name is required"}

    args = ["repo", "create", name.strip()]
    args.append("--private" if private else "--public")

    if description.strip():
        args.extend(["--description", description.strip()])

    # Don't clone — we already have a local repo
    args.append("--source=.")
    if add_remote:
        args.append("--remote=origin")
        args.append("--push")

    r = run_gh(*args, cwd=project_root, timeout=60)
    if r.returncode != 0:
        err = r.stderr.strip()
        return {"error": f"Failed to create repository: {err}"}

    # Parse the created repo URL from output
    output = r.stdout.strip() or r.stderr.strip()
    repo_url = ""
    for line in output.splitlines():
        if "github.com/" in line:
            repo_url = line.strip()
            break

    return {
        "ok": True,
        "message": f"Repository created: {name}",
        "name": name,
        "private": private,
        "url": repo_url,
    }


def gh_repo_set_visibility(
    project_root: Path,
    visibility: str,
) -> dict:
    """Change repository visibility (public/private).

    Args:
        project_root: Local project directory.
        visibility: 'public' or 'private'.
    """
    slug = repo_slug(project_root)
    if not slug:
        return {"error": "No GitHub remote configured"}

    visibility = visibility.strip().lower()
    if visibility not in ("public", "private"):
        return {"error": f"Invalid visibility: {visibility}. Must be 'public' or 'private'."}

    r = run_gh(
        "repo", "edit", slug, f"--visibility={visibility}",
        cwd=project_root, timeout=15,
    )
    if r.returncode != 0:
        err = r.stderr.strip()
        return {"error": f"Failed to change visibility: {err}"}

    return {
        "ok": True,
        "slug": slug,
        "visibility": visibility.upper(),
        "message": f"Repository {slug} is now {visibility}",
    }


def git_remote_remove(project_root: Path, name: str = "origin") -> dict:
    """Remove a git remote by name."""
    name = name.strip() or "origin"
    r = run_git("remote", "remove", name, cwd=project_root)
    if r.returncode != 0:
        err = r.stderr.strip()
        if "No such remote" in err:
            return {"ok": True, "message": f"No remote '{name}' to remove"}
        return {"error": f"Failed to remove remote: {err}"}

    return {"ok": True, "message": f"Remote '{name}' removed"}


def git_remotes(project_root: Path) -> dict:
    """List ALL git remotes with their fetch and push URLs."""
    r = run_git("remote", "-v", cwd=project_root)
    if r.returncode != 0:
        return {"available": True, "remotes": []}

    # Parse: "origin\thttps://...git (fetch)"
    seen: dict[str, dict] = {}
    for line in r.stdout.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        rname = parts[0]
        url = parts[1]
        kind = parts[2].strip("()")
        if rname not in seen:
            seen[rname] = {"name": rname, "fetch": "", "push": ""}
        seen[rname][kind] = url

    return {"available": True, "remotes": list(seen.values())}


def git_remote_add(project_root: Path, name: str, url: str) -> dict:
    """Add a new git remote.  Idempotent: updates URL if remote already exists."""
    name = name.strip()
    url = url.strip()
    if not name:
        return {"error": "Remote name is required"}
    if not url:
        return {"error": "Remote URL is required"}

    r = run_git("remote", "add", name, url, cwd=project_root)
    if r.returncode != 0:
        err = r.stderr.strip()
        if "already exists" in err.lower():
            # Idempotent: update URL instead of failing
            r2 = run_git("remote", "set-url", name, url, cwd=project_root)
            if r2.returncode != 0:
                return {"error": f"Failed to update remote: {r2.stderr.strip()}"}
            return {"ok": True, "message": f"Remote '{name}' updated → {url}"}
        return {"error": f"Failed to add remote: {err}"}

    return {"ok": True, "message": f"Remote '{name}' added → {url}"}


def git_remote_rename(project_root: Path, old_name: str, new_name: str) -> dict:
    """Rename a git remote."""
    old_name = old_name.strip()
    new_name = new_name.strip()
    if not old_name or not new_name:
        return {"error": "Both old and new names are required"}

    r = run_git("remote", "rename", old_name, new_name, cwd=project_root)
    if r.returncode != 0:
        return {"error": f"Failed to rename remote: {r.stderr.strip()}"}

    return {"ok": True, "message": f"Remote renamed: {old_name} → {new_name}"}


def git_remote_set_url(project_root: Path, name: str, url: str) -> dict:
    """Change the URL of an existing git remote."""
    name = name.strip()
    url = url.strip()
    if not name or not url:
        return {"error": "Remote name and URL are required"}

    r = run_git("remote", "set-url", name, url, cwd=project_root)
    if r.returncode != 0:
        return {"error": f"Failed to set URL: {r.stderr.strip()}"}

    return {"ok": True, "message": f"Remote '{name}' URL → {url}"}


def gh_repo_set_default_branch(
    project_root: Path,
    branch: str,
) -> dict:
    """Change the default branch on GitHub.

    Args:
        project_root: Local project directory.
        branch: Branch name to set as default.
    """
    slug = repo_slug(project_root)
    if not slug:
        return {"error": "No GitHub remote configured"}

    branch = branch.strip()
    if not branch:
        return {"error": "Branch name is required"}

    r = run_gh(
        "repo", "edit", slug, f"--default-branch={branch}",
        cwd=project_root, timeout=15,
    )
    if r.returncode != 0:
        err = r.stderr.strip()
        return {"error": f"Failed to change default branch: {err}"}

    return {
        "ok": True,
        "slug": slug,
        "default_branch": branch,
        "message": f"Default branch set to '{branch}' on {slug}",
    }

