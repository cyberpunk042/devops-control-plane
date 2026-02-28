"""
GitHub repository & remote management — create, visibility, remotes.

Channel-independent: no Flask or HTTP dependency.
Requires ``gh`` CLI for GitHub repo operations.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.services.git.ops import repo_slug, run_gh, run_git

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  GitHub: Repository management
# ═══════════════════════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════════════════════
#  Git: Remote management
# ═══════════════════════════════════════════════════════════════════


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
