"""
GitHub API queries — status, PRs, Actions, user, repo info.

Channel-independent: no Flask or HTTP dependency.
Requires ``gh`` CLI for GitHub API operations.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from src.core.services.git.ops import repo_slug, run_gh, run_git

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  GitHub CLI queries
# ═══════════════════════════════════════════════════════════════════


def gh_status(project_root: Path) -> dict:
    """Extended GitHub status — version, repo, auth details."""
    from src.core.services.git.gh_auth import detect_platform_capabilities
    from src.core.services.tool_requirements import check_required_tools

    caps = detect_platform_capabilities()

    if not shutil.which("gh"):
        return {
            "available": False,
            "error": "gh CLI not installed",
            "missing_tools": check_required_tools(["gh"]),
            "platform": caps,
        }

    # Get version (local command, no network needed)
    r = run_gh("--version", cwd=project_root, timeout=5)
    version = (
        r.stdout.strip().splitlines()[0]
        if r.returncode == 0 and r.stdout.strip()
        else "unknown"
    )

    # ── Check auth: local state file first (instant, no network) ──
    # Written by the HTTP device flow on success.
    authenticated = False
    auth_detail = ""
    state_file = Path.home() / ".config" / "devops-cp" / "gh_authenticated"
    try:
        if state_file.exists():
            token = state_file.read_text().strip()
            if token:
                authenticated = True
                auth_detail = "Authenticated via device flow"
    except Exception:
        pass

    # ── Fallback: check gh auth status (only if no local state) ──
    if not authenticated:
        if caps.get("can_pty_device_flow"):
            r_auth = run_gh("auth", "status", cwd=project_root, timeout=10)
            authenticated = r_auth.returncode == 0
            auth_detail = r_auth.stdout.strip() or r_auth.stderr.strip()
        else:
            # On restricted platforms, check gh config file
            auth_detail = "Not authenticated"
            try:
                import os
                gh_config = Path(os.environ.get(
                    "GH_CONFIG_DIR",
                    Path.home() / ".config" / "gh",
                )) / "hosts.yml"
                if gh_config.exists():
                    content = gh_config.read_text()
                    if "oauth_token:" in content and "oauth_token: \n" not in content:
                        authenticated = True
                        auth_detail = "Token found in gh config"
            except Exception:
                pass

    slug = repo_slug(project_root)

    return {
        "available": True,
        "version": version,
        "authenticated": authenticated,
        "auth_detail": auth_detail,
        "repo": slug,
        "missing_tools": check_required_tools(["gh"]),
        "platform": caps,
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
#  GitHub: User & Repository info
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
