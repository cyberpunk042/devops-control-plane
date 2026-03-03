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

    # ── Check auth ──
    # Always try gh auth status first. Only fall back to GH_TOKEN
    # when the gh migration error is detected (headless systems).
    authenticated = False
    auth_detail = ""

    r_auth = run_gh("auth", "status", cwd=project_root, timeout=10)
    if r_auth.returncode == 0:
        authenticated = True
        auth_detail = r_auth.stdout.strip() or r_auth.stderr.strip()
    else:
        stderr = r_auth.stderr.strip()
        # Migration error — fall back to GH_TOKEN if available
        if "migration" in stderr.lower():
            from src.core.services.git.ops import get_stored_gh_token, set_gh_migration_broken
            set_gh_migration_broken(True)
            token = get_stored_gh_token()
            if token:
                authenticated = True
                auth_detail = "Authenticated via GH_TOKEN (migration bypass)"
            else:
                auth_detail = stderr
        else:
            auth_detail = stderr

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


# ═══════════════════════════════════════════════════════════════════
#  GitHub Status — check githubstatus.com for outages
# ═══════════════════════════════════════════════════════════════════

import time
import urllib.request

_gh_status_cache: dict = {}
_gh_status_cache_ts: float = 0
_GH_STATUS_CACHE_TTL = 60  # seconds


def check_github_status() -> dict:
    """Check GitHub's operational status via the public API.

    Returns::

        {
            "status": "operational" | "degraded_performance" | "partial_outage" | "major_outage",
            "description": "All Systems Operational",
            "components": {
                "Git Operations": "major_outage",
                "API Requests": "operational",
                ...
            },
            "git_operations": "operational" | "degraded_performance" | ...,
            "degraded": True/False,
        }

    Caches results for 60 seconds to avoid hammering the API.
    """
    global _gh_status_cache, _gh_status_cache_ts

    now = time.time()
    if _gh_status_cache and (now - _gh_status_cache_ts) < _GH_STATUS_CACHE_TTL:
        return _gh_status_cache

    try:
        # Component-level status
        req = urllib.request.Request(
            "https://www.githubstatus.com/api/v2/components.json",
            headers={"Accept": "application/json", "User-Agent": "devops-control-plane"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        components = {}
        git_ops_status = "operational"
        for comp in data.get("components", []):
            name = comp.get("name", "")
            status = comp.get("status", "operational")
            components[name] = status
            if name == "Git Operations":
                git_ops_status = status

        # Overall status
        req2 = urllib.request.Request(
            "https://www.githubstatus.com/api/v2/status.json",
            headers={"Accept": "application/json", "User-Agent": "devops-control-plane"},
        )
        with urllib.request.urlopen(req2, timeout=5) as resp2:
            status_data = json.loads(resp2.read().decode())

        overall = status_data.get("status", {})
        indicator = overall.get("indicator", "none")
        description = overall.get("description", "")

        result = {
            "status": indicator,
            "description": description,
            "components": components,
            "git_operations": git_ops_status,
            "degraded": indicator != "none" or git_ops_status != "operational",
        }

        _gh_status_cache = result
        _gh_status_cache_ts = now
        return result

    except Exception as exc:
        logger.debug("Failed to check GitHub status: %s", exc)
        return {
            "status": "unknown",
            "description": "Could not check GitHub status",
            "components": {},
            "git_operations": "unknown",
            "degraded": False,
        }


# Error patterns that suggest a GitHub outage (not a local auth issue)
_OUTAGE_PATTERNS = [
    "internal error performing authentication",
    "no healthy upstream",
    "upstream connect error",
    "the requested url returned error: 500",
    "internal server error",
    "connection refused",
    "service unavailable",
]


def check_and_notify_github_outage(git_stderr: str) -> bool:
    """If git_stderr matches known outage patterns, check GitHub status
    and publish an SSE event if GitHub is degraded.

    Returns True if a GitHub outage was detected and the user was notified.
    """
    stderr_lower = git_stderr.lower()

    # Only check if the error matches known outage patterns
    if not any(pat in stderr_lower for pat in _OUTAGE_PATTERNS):
        return False

    status = check_github_status()
    if not status.get("degraded"):
        return False

    # Publish SSE event so the frontend can notify the user
    try:
        from src.core.services.event_bus import bus
        bus.publish("github:status", key="outage", data={
            "status": status["status"],
            "description": status["description"],
            "git_operations": status["git_operations"],
            "message": (
                f"GitHub is experiencing issues: {status['description']}. "
                f"Git Operations: {status['git_operations'].replace('_', ' ')}. "
                "Remote sync may fail until GitHub resolves this."
            ),
        })
    except Exception:
        pass

    logger.warning(
        "GitHub outage detected — %s (Git Operations: %s)",
        status["description"], status["git_operations"],
    )
    return True
