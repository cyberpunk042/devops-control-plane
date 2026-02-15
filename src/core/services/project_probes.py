"""
Project integration probes — detect tool availability and setup status.

Channel-independent: no Flask, no HTTP, no CLI dependency.
Returns simple dicts describing each integration's readiness.

Used by:
    - routes_project.py   (project status API)
    - wizard_ops.py       (wizard detect endpoint)
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Utilities ───────────────────────────────────────────────────────


def has_cmd(cmd: str) -> bool:
    """Check if a command is available on PATH."""
    try:
        result = subprocess.run(
            ["which", cmd],
            capture_output=True, timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False


def count_glob(root: Path, pattern: str) -> int:
    """Count files matching a glob pattern."""
    try:
        return len(list(root.glob(pattern)))
    except Exception:
        return 0


# ── Probes ──────────────────────────────────────────────────────────


def probe_project(root: Path) -> dict:
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


def probe_git(root: Path) -> dict:
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

        # Commit count
        rc = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=str(root), capture_output=True, timeout=5,
        )
        if rc.returncode == 0:
            commit_count = int(rc.stdout.decode().strip())
    except Exception:
        pass

    # Hook detection
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


def probe_github(root: Path) -> dict:
    """Check GitHub CLI and repo status."""
    has_cli = has_cmd("gh")
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
    workflow_count = (
        len(list(wf_dir.glob("*.yml"))) + len(list(wf_dir.glob("*.yaml")))
        if wf_dir.is_dir() else 0
    )

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


def probe_docker(root: Path) -> dict:
    """Check Docker setup."""
    _has_cli = has_cmd("docker")
    has_dockerfile = (root / "Dockerfile").is_file()
    has_compose = any([
        (root / "docker-compose.yml").is_file(),
        (root / "docker-compose.yaml").is_file(),
        (root / "compose.yml").is_file(),
        (root / "compose.yaml").is_file(),
    ])
    has_dockerignore = (root / ".dockerignore").is_file()

    if _has_cli and has_dockerfile:
        status = "ready"
    elif _has_cli and (has_compose or has_dockerfile):
        status = "partial"
    elif _has_cli:
        status = "partial"
    else:
        status = "missing"

    return {
        "status": status,
        "has_cli": _has_cli,
        "has_dockerfile": has_dockerfile,
        "has_compose": has_compose,
        "has_dockerignore": has_dockerignore,
    }


def probe_cicd(root: Path) -> dict:
    """Check CI/CD workflow configuration."""
    gh_workflows = (
        count_glob(root, ".github/workflows/*.yml")
        + count_glob(root, ".github/workflows/*.yaml")
    )
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


def probe_k8s(root: Path) -> dict:
    """Check Kubernetes setup."""
    _has_kubectl = has_cmd("kubectl")
    _has_helm = has_cmd("helm")

    k8s_dirs = ["k8s", "kubernetes", "deploy", "manifests"]
    manifest_count = 0
    for d in k8s_dirs:
        manifest_count += (
            count_glob(root / d, "*.yml")
            + count_glob(root / d, "*.yaml")
        )

    has_chart = (root / "Chart.yaml").is_file() or any(
        (root / d / "Chart.yaml").is_file() for d in k8s_dirs
    )
    has_kustomize = any(
        (root / d / "kustomization.yaml").is_file() for d in [".", *k8s_dirs]
    )
    has_skaffold = (root / "skaffold.yaml").is_file()

    cluster_connected = False
    if _has_kubectl:
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
    elif manifest_count > 0 or _has_kubectl:
        status = "partial"
    else:
        status = "missing"

    return {
        "status": status,
        "has_kubectl": _has_kubectl,
        "has_helm": _has_helm,
        "manifest_count": manifest_count,
        "has_chart": has_chart,
        "has_kustomize": has_kustomize,
        "has_skaffold": has_skaffold,
        "cluster_connected": cluster_connected,
    }


def probe_terraform(root: Path) -> dict:
    """Check Terraform setup."""
    _has_cli = has_cmd("terraform")
    tf_files = count_glob(root, "*.tf") + count_glob(root, "**/*.tf")
    has_state = (root / "terraform.tfstate").is_file() or (root / ".terraform").is_dir()
    initialized = (root / ".terraform").is_dir()

    if tf_files > 0 and initialized:
        status = "ready"
    elif tf_files > 0 or _has_cli:
        status = "partial"
    else:
        status = "missing"

    return {
        "status": status,
        "has_cli": _has_cli,
        "tf_file_count": tf_files,
        "initialized": initialized,
        "has_state": has_state,
    }


def probe_pages(root: Path) -> dict:
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


def probe_dns(root: Path) -> dict:
    """Check DNS/domain configuration."""
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


# ── All probes at once ──────────────────────────────────────────────


def run_all_probes(root: Path) -> dict:
    """Run every integration probe and return the full map."""
    return {
        "project": probe_project(root),
        "git": probe_git(root),
        "github": probe_github(root),
        "docker": probe_docker(root),
        "cicd": probe_cicd(root),
        "k8s": probe_k8s(root),
        "terraform": probe_terraform(root),
        "pages": probe_pages(root),
        "dns": probe_dns(root),
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


def suggest_next(statuses: dict) -> str | None:
    """Suggest the next integration to configure."""
    for key in INTEGRATION_ORDER:
        info = statuses.get(key, {})
        if info.get("status") in ("missing", "partial"):
            deps = DEPENDENCY_MAP.get(key, [])
            deps_met = all(
                statuses.get(d, {}).get("status") == "ready"
                for d in deps
            )
            if deps_met:
                return key
    return None


def compute_progress(statuses: dict) -> dict:
    """Compute overall setup progress."""
    total = len(INTEGRATION_ORDER)
    ready = sum(
        1 for k in INTEGRATION_ORDER
        if statuses.get(k, {}).get("status") == "ready"
    )
    return {
        "complete": ready,
        "total": total,
        "percent": round(ready / total * 100) if total > 0 else 0,
    }
