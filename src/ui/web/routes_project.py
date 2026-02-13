"""
Project Status API — unified integration status for the connected journey.

GET  /api/project/status  → complete integration state
GET  /api/project/next    → suggested next integration to configure

This is the backbone for:
- Dashboard progress tracker
- Card empty-state CTAs
- Dependency hints between cards
- Wizard step pre-population
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from flask import Blueprint, current_app, jsonify

logger = logging.getLogger(__name__)

project_bp = Blueprint("project", __name__)


def _root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


def _has_cmd(cmd: str) -> bool:
    """Check if a command is available on PATH."""
    try:
        result = subprocess.run(
            ["which", cmd],
            capture_output=True, timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False


def _count_glob(root: Path, pattern: str) -> int:
    """Count files matching a glob pattern."""
    try:
        return len(list(root.glob(pattern)))
    except Exception:
        return 0


# ── Status probes ──────────────────────────────────────────────────


def _probe_project(root: Path) -> dict:
    """Check if project.yml exists and is configured."""
    from src.core.config.loader import find_project_file
    config_path = find_project_file(root)
    if config_path and config_path.is_file():
        import yaml
        try:
            data = yaml.safe_load(config_path.read_text())
            return {
                "status": "ready",
                "name": data.get("name", ""),
                "modules": len(data.get("modules", [])),
                "environments": len(data.get("environments", [])),
            }
        except Exception:
            return {"status": "error", "name": ""}
    return {"status": "missing", "name": ""}


def _probe_git(root: Path) -> dict:
    """Check Git repository status."""
    git_dir = root / ".git"
    if not git_dir.is_dir():
        return {"status": "missing", "initialized": False, "has_remote": False}

    has_remote = False
    branch = ""
    remote_url = ""
    git_version = ""
    commit_count = 0
    try:
        # Git version
        rv = subprocess.run(
            ["git", "--version"],
            capture_output=True, timeout=3,
        )
        if rv.returncode == 0:
            # "git version 2.43.0" → "2.43.0"
            ver_line = rv.stdout.decode().strip()
            git_version = ver_line.replace("git version ", "").strip()

        # Remote URL
        r = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(root), capture_output=True, timeout=5,
        )
        has_remote = r.returncode == 0
        remote_url = r.stdout.decode().strip() if has_remote else ""

        # Current branch
        r2 = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(root), capture_output=True, timeout=5,
        )
        branch = r2.stdout.decode().strip() if r2.returncode == 0 else ""

        # Commit count (0 = fresh repo with no commits)
        rc = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=str(root), capture_output=True, timeout=5,
        )
        if rc.returncode == 0:
            commit_count = int(rc.stdout.decode().strip())
    except Exception:
        pass

    # Hook detection — count non-sample hooks in .git/hooks/
    hooks_dir = git_dir / "hooks"
    hooks: list[str] = []
    if hooks_dir.is_dir():
        for h in hooks_dir.iterdir():
            if h.is_file() and not h.name.endswith(".sample") and h.name != "README":
                hooks.append(h.name)

    gitignore = (root / ".gitignore").is_file()

    status = "ready" if has_remote else "partial"
    return {
        "status": status,
        "initialized": True,
        "has_remote": has_remote,
        "remote": remote_url if has_remote else None,
        "branch": branch,
        "has_gitignore": gitignore,
        "git_version": git_version,
        "commit_count": commit_count,
        "hooks": hooks,
        "hook_count": len(hooks),
    }


def _probe_github(root: Path) -> dict:
    """Check GitHub CLI and repo status."""
    has_cli = _has_cmd("gh")
    if not has_cli:
        return {"status": "missing", "has_cli": False, "authenticated": False}

    authenticated = False
    repo = ""
    try:
        r = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, timeout=5,
        )
        authenticated = r.returncode == 0

        r2 = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
            cwd=str(root), capture_output=True, timeout=5,
        )
        repo = r2.stdout.decode().strip() if r2.returncode == 0 else ""
    except Exception:
        pass

    has_github_dir = (root / ".github").is_dir()
    has_codeowners = (root / ".github" / "CODEOWNERS").exists()
    wf_dir = root / ".github" / "workflows"
    workflow_count = len(list(wf_dir.glob("*.yml"))) + len(list(wf_dir.glob("*.yaml"))) if wf_dir.is_dir() else 0

    if authenticated and repo:
        status = "ready"
    elif has_cli:
        status = "partial"
    else:
        status = "missing"

    return {
        "status": status,
        "has_cli": has_cli,
        "authenticated": authenticated,
        "repo": repo or None,
        "has_github_dir": has_github_dir,
        "has_codeowners": has_codeowners,
        "workflow_count": workflow_count,
    }


def _probe_docker(root: Path) -> dict:
    """Check Docker setup."""
    has_cli = _has_cmd("docker")
    has_dockerfile = (root / "Dockerfile").is_file()
    has_compose = any([
        (root / "docker-compose.yml").is_file(),
        (root / "docker-compose.yaml").is_file(),
        (root / "compose.yml").is_file(),
        (root / "compose.yaml").is_file(),
    ])
    has_dockerignore = (root / ".dockerignore").is_file()

    if has_cli and has_dockerfile:
        status = "ready"
    elif has_cli and (has_compose or has_dockerfile):
        status = "partial"
    elif has_cli:
        status = "partial"
    else:
        status = "missing"

    return {
        "status": status,
        "has_cli": has_cli,
        "has_dockerfile": has_dockerfile,
        "has_compose": has_compose,
        "has_dockerignore": has_dockerignore,
    }


def _probe_cicd(root: Path) -> dict:
    """Check CI/CD workflow configuration."""
    gh_workflows = _count_glob(root, ".github/workflows/*.yml") + _count_glob(root, ".github/workflows/*.yaml")
    gitlab_ci = (root / ".gitlab-ci.yml").is_file()

    provider = None
    if gh_workflows > 0:
        provider = "github-actions"
    elif gitlab_ci:
        provider = "gitlab-ci"

    if provider:
        status = "ready"
    else:
        status = "missing"

    return {
        "status": status,
        "provider": provider,
        "workflow_count": gh_workflows + (1 if gitlab_ci else 0),
    }


def _probe_k8s(root: Path) -> dict:
    """Check Kubernetes setup."""
    has_kubectl = _has_cmd("kubectl")
    has_helm = _has_cmd("helm")

    # Look for manifest directories
    k8s_dirs = ["k8s", "kubernetes", "deploy", "manifests"]
    manifest_count = 0
    for d in k8s_dirs:
        manifest_count += _count_glob(root / d, "*.yml") + _count_glob(root / d, "*.yaml")

    # Also check root for common k8s files
    has_chart = (root / "Chart.yaml").is_file() or any(
        (root / d / "Chart.yaml").is_file() for d in k8s_dirs
    )
    has_kustomize = any(
        (root / d / "kustomization.yaml").is_file() for d in [".", *k8s_dirs]
    )
    has_skaffold = (root / "skaffold.yaml").is_file()

    cluster_connected = False
    if has_kubectl:
        try:
            r = subprocess.run(
                ["kubectl", "cluster-info", "--request-timeout=3s"],
                capture_output=True, timeout=5,
            )
            cluster_connected = r.returncode == 0
        except Exception:
            pass

    if manifest_count > 0 and cluster_connected:
        status = "ready"
    elif manifest_count > 0 or has_kubectl:
        status = "partial"
    else:
        status = "missing"

    return {
        "status": status,
        "has_kubectl": has_kubectl,
        "has_helm": has_helm,
        "manifest_count": manifest_count,
        "has_chart": has_chart,
        "has_kustomize": has_kustomize,
        "has_skaffold": has_skaffold,
        "cluster_connected": cluster_connected,
    }


def _probe_terraform(root: Path) -> dict:
    """Check Terraform setup."""
    has_cli = _has_cmd("terraform")
    tf_files = _count_glob(root, "*.tf") + _count_glob(root, "**/*.tf")
    has_state = (root / "terraform.tfstate").is_file() or (root / ".terraform").is_dir()
    initialized = (root / ".terraform").is_dir()

    if tf_files > 0 and initialized:
        status = "ready"
    elif tf_files > 0 or has_cli:
        status = "partial"
    else:
        status = "missing"

    return {
        "status": status,
        "has_cli": has_cli,
        "tf_file_count": tf_files,
        "initialized": initialized,
        "has_state": has_state,
    }


def _probe_pages(root: Path) -> dict:
    """Check Pages (documentation site) setup."""
    import yaml
    from src.core.config.loader import find_project_file

    segments = 0
    config_path = find_project_file(root)
    if config_path and config_path.is_file():
        try:
            data = yaml.safe_load(config_path.read_text())
            pages_conf = data.get("pages", {})
            if isinstance(pages_conf, dict):
                segments = len(pages_conf.get("segments", []))
        except Exception:
            pass

    pages_dir = (root / ".pages").is_dir()

    if segments > 0:
        status = "ready"
    elif pages_dir:
        status = "partial"
    else:
        status = "missing"

    return {
        "status": status,
        "segment_count": segments,
        "has_pages_dir": pages_dir,
    }


def _probe_dns(root: Path) -> dict:
    """Check DNS/domain configuration."""
    # Look for CNAME file (GitHub Pages), domain in config, etc.
    has_cname = (root / "CNAME").is_file()

    import yaml
    from src.core.config.loader import find_project_file
    domain = None
    config_path = find_project_file(root)
    if config_path and config_path.is_file():
        try:
            data = yaml.safe_load(config_path.read_text())
            domain = data.get("domain") or data.get("pages", {}).get("domain")
        except Exception:
            pass

    if domain or has_cname:
        status = "ready"
    else:
        status = "missing"

    return {
        "status": status,
        "has_cname": has_cname,
        "domain": domain,
    }


# ── Dependency graph (defines the "next" recommendation) ───────────

INTEGRATION_ORDER = [
    "git",
    "docker",
    "github",
    "cicd",
    "k8s",
    "terraform",
    "pages",
    "dns",
]

DEPENDENCY_MAP = {
    "git": [],
    "docker": ["git"],
    "github": ["git"],
    "cicd": ["git", "docker"],
    "k8s": ["docker"],
    "terraform": [],
    "pages": ["git"],
    "dns": ["pages"],
}


def _suggest_next(statuses: dict) -> str | None:
    """Suggest the next integration to configure."""
    for key in INTEGRATION_ORDER:
        info = statuses.get(key, {})
        if info.get("status") in ("missing", "partial"):
            # Check if dependencies are met
            deps = DEPENDENCY_MAP.get(key, [])
            deps_met = all(
                statuses.get(d, {}).get("status") == "ready"
                for d in deps
            )
            if deps_met:
                return key
    return None


def _compute_progress(statuses: dict) -> dict:
    """Compute overall setup progress."""
    total = len(INTEGRATION_ORDER)
    ready = sum(1 for k in INTEGRATION_ORDER if statuses.get(k, {}).get("status") == "ready")
    return {
        "complete": ready,
        "total": total,
        "percent": round(ready / total * 100) if total > 0 else 0,
    }


# ── Routes ─────────────────────────────────────────────────────────


@project_bp.route("/project/status")
def project_status():  # type: ignore[no-untyped-def]
    """Complete integration status for all cards."""
    root = _root()

    statuses = {
        "project": _probe_project(root),
        "git": _probe_git(root),
        "github": _probe_github(root),
        "docker": _probe_docker(root),
        "cicd": _probe_cicd(root),
        "k8s": _probe_k8s(root),
        "terraform": _probe_terraform(root),
        "pages": _probe_pages(root),
        "dns": _probe_dns(root),
    }

    return jsonify({
        "integrations": statuses,
        "suggested_next": _suggest_next(statuses),
        "progress": _compute_progress(statuses),
    })


@project_bp.route("/project/next")
def project_next():  # type: ignore[no-untyped-def]
    """Suggest just the next integration to configure."""
    root = _root()
    statuses = {
        "git": _probe_git(root),
        "docker": _probe_docker(root),
        "github": _probe_github(root),
        "cicd": _probe_cicd(root),
        "k8s": _probe_k8s(root),
        "terraform": _probe_terraform(root),
        "pages": _probe_pages(root),
        "dns": _probe_dns(root),
    }

    next_key = _suggest_next(statuses)
    return jsonify({
        "suggested_next": next_key,
        "status": statuses.get(next_key) if next_key else None,
        "progress": _compute_progress(statuses),
    })
