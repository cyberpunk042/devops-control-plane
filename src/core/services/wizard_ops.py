"""
Wizard operations — environment detection and wizard data helpers.

Channel-independent: no Flask, no HTTP dependency.

Detects available integrations, tools, project characteristics,
and bundles them into a snapshot for the setup wizard.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("wizard")


# ── Main detection ──────────────────────────────────────────────────


def wizard_detect(root: Path) -> dict:
    """Detect available integrations, tools, and project characteristics.

    Returns a dict used by the setup wizard to suggest which
    integrations to enable and which tools to install.
    """
    from src.core.services import devops_cache
    from src.core.services.project_probes import run_all_probes

    # ── Tool availability ───────────────────────────────────────
    tool_checks = {
        "git":             shutil.which("git"),
        "gh":              shutil.which("gh"),
        "docker":          shutil.which("docker"),
        "docker-compose":  shutil.which("docker-compose"),
        "kubectl":         shutil.which("kubectl"),
        "terraform":       shutil.which("terraform"),
        "helm":            shutil.which("helm"),
        "node":            shutil.which("node"),
        "npm":             shutil.which("npm"),
        "ruff":            shutil.which("ruff"),
        "mypy":            shutil.which("mypy"),
        "pytest":          shutil.which("pytest"),
        "pip-audit":       shutil.which("pip-audit"),
        "bandit":          shutil.which("bandit"),
        "safety":          shutil.which("safety"),
    }
    tools = {k: v is not None for k, v in tool_checks.items()}

    # ── Project file detection ──────────────────────────────────
    files = {
        "git_repo":       (root / ".git").is_dir(),
        "dockerfile":     (root / "Dockerfile").is_file(),
        "docker_compose": (root / "docker-compose.yml").is_file()
                          or (root / "docker-compose.yaml").is_file(),
        "k8s_manifests":  (root / "k8s").is_dir()
                          or (root / "kubernetes").is_dir(),
        "terraform_dir":  (root / "terraform").is_dir()
                          or (root / "main.tf").is_file(),
        "github_actions": (root / ".github" / "workflows").is_dir(),
        "pyproject":      (root / "pyproject.toml").is_file(),
        "package_json":   (root / "package.json").is_file(),
        "pages_config":   (root / "project.yml").is_file(),
    }

    # ── Connectivity probes ─────────────────────────────────────
    _docker_ok = False
    if tools["docker"]:
        try:
            r = subprocess.run(
                ["docker", "info"], capture_output=True, timeout=5,
            )
            _docker_ok = r.returncode == 0
        except Exception:
            pass

    _kubectl_ok = False
    if tools["kubectl"]:
        try:
            r = subprocess.run(
                ["kubectl", "cluster-info", "--request-timeout=3s"],
                capture_output=True, timeout=5,
            )
            _kubectl_ok = r.returncode == 0
        except Exception:
            pass

    _terraform_ok = False
    if tools["terraform"] and files["terraform_dir"]:
        try:
            r = subprocess.run(
                ["terraform", "version"], capture_output=True, timeout=5,
            )
            _terraform_ok = r.returncode == 0
        except Exception:
            pass

    # ── Per-integration suggestions ─────────────────────────────
    integrations = {
        "int:git": {
            "detected": files["git_repo"] and tools["git"],
            "status": "ready" if files["git_repo"] and tools["git"]
                      else "installed" if tools["git"] else "not_installed",
            "tools_needed": [] if tools["git"] else ["git"],
            "suggest": "auto" if files["git_repo"] and tools["git"] else "hidden",
            "label": "🔀 Git",
            "setup_actions": [] if files["git_repo"]
                             else ["init_repo"],
        },
        "int:github": {
            "detected": files["git_repo"] and tools.get("gh", False),
            "status": "ready" if tools["gh"] and files["git_repo"]
                      else "installed" if tools["gh"] else "not_installed",
            "tools_needed": [] if tools["gh"] else ["gh"],
            "suggest": "auto" if tools["gh"] else "manual",
            "label": "🐙 GitHub",
            "setup_actions": [] if tools["gh"] else ["install_gh"],
        },
        "int:ci": {
            "detected": files["github_actions"],
            "status": "ready" if files["github_actions"]
                      else "available",
            "tools_needed": [] if tools["gh"] else ["gh"],
            "suggest": "auto" if files["github_actions"] and tools["gh"] else "hidden",
            "label": "🔄 CI/CD",
            "setup_actions": [] if files["github_actions"]
                             else ["generate_workflow"],
        },
        "int:docker": {
            "detected": (files["dockerfile"] or files["docker_compose"])
                        and _docker_ok,
            "status": "ready" if _docker_ok and files["dockerfile"]
                      else "installed" if tools["docker"]
                      else "not_installed",
            "tools_needed": [t for t in ["docker", "docker-compose"]
                            if not tools[t]],
            "suggest": ("auto" if files["dockerfile"] and _docker_ok
                        else "manual" if tools["docker"]
                        else "hidden"),
            "label": "🐳 Docker",
            "daemon_ok": _docker_ok,
            "has_dockerfile": files["dockerfile"],
            "has_compose": files["docker_compose"],
            "setup_actions": (
                ([] if files["dockerfile"] else ["generate_dockerfile"])
                + ([] if files["docker_compose"]
                   else ["generate_compose"])
            ),
        },
        "int:pages": {
            "detected": files["pages_config"],
            "status": "ready" if files["pages_config"] else "available",
            "tools_needed": [],
            "suggest": "auto" if files["pages_config"] else "hidden",
            "label": "📄 Pages",
            "setup_actions": [],
        },
        "int:k8s": {
            "detected": files["k8s_manifests"] and _kubectl_ok,
            "status": ("ready" if files["k8s_manifests"] and _kubectl_ok
                       else "installed" if tools["kubectl"]
                       else "not_installed"),
            "suggest": ("auto" if files["k8s_manifests"] and _kubectl_ok
                        else "hidden"),
            "tools_needed": [t for t in ["kubectl", "helm"]
                            if not tools[t]],
            "label": "☸️ Kubernetes",
            "setup_actions": [],
        },
        "int:terraform": {
            "detected": files["terraform_dir"] and _terraform_ok,
            "status": ("ready" if files["terraform_dir"] and _terraform_ok
                       else "installed" if tools["terraform"]
                       else "not_installed"),
            "suggest": ("auto" if files["terraform_dir"] and _terraform_ok
                        else "hidden"),
            "tools_needed": ([] if tools["terraform"]
                            else ["terraform"]),
            "label": "🏗️ Terraform",
            "setup_actions": [],
        },
    }

    devops_cards = {
        "security": {"detected": True, "suggest": "auto",
                     "label": "🔐 Security"},
        "testing":  {"detected": True, "suggest": "auto",
                     "label": "🧪 Testing"},
        "quality":  {"detected": True, "suggest": "auto",
                     "label": "🔧 Quality"},
        "packages": {"detected": True, "suggest": "auto",
                     "label": "📦 Packages"},
        "env":      {"detected": True, "suggest": "auto",
                     "label": "⚙️ Environment"},
        "docs":     {"detected": True, "suggest": "auto",
                     "label": "📚 Docs"},
        "k8s": {
            "detected": files["k8s_manifests"] and _kubectl_ok,
            "status": ("ready" if files["k8s_manifests"] and _kubectl_ok
                       else "installed" if tools["kubectl"]
                       else "not_installed"),
            "suggest": ("auto" if files["k8s_manifests"] and _kubectl_ok
                        else "hidden"),
            "tools_needed": [t for t in ["kubectl", "helm"]
                            if not tools[t]],
            "label": "☸️ Kubernetes",
            "cluster_ok": _kubectl_ok,
            "setup_actions": (
                ([] if files["k8s_manifests"]
                 else ["generate_k8s_manifests"])
                + ([] if _kubectl_ok
                   else ["connect_cluster"])
            ),
        },
        "terraform": {
            "detected": files["terraform_dir"] and _terraform_ok,
            "status": ("ready" if files["terraform_dir"] and _terraform_ok
                       else "installed" if tools["terraform"]
                       else "not_installed"),
            "suggest": ("auto" if files["terraform_dir"] and _terraform_ok
                        else "hidden"),
            "tools_needed": ([] if tools["terraform"]
                            else ["terraform"]),
            "label": "🏗️ Terraform",
            "setup_actions": (
                [] if files["terraform_dir"]
                else ["generate_terraform"]
            ),
        },
        "dns": {
            "detected": False,
            "status": "not_available",
            "suggest": "hidden",
            "label": "🌐 DNS & CDN",
            "setup_actions": [],
        },
    }

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"

    # Detect project stacks for wizard hints
    detected_stacks: list[str] = []
    try:
        from src.core.config.loader import load_project
        from src.core.config.stack_loader import discover_stacks
        from src.core.services.detection import detect_modules

        project = load_project(root / "project.yml")
        stacks = discover_stacks(root / "stacks")
        detection = detect_modules(project, root, stacks)
        detected_stacks = sorted(
            {m.effective_stack for m in detection.modules if m.effective_stack}
        )
    except Exception:
        pass

    return {
        "tools": tools,
        "files": files,
        "integrations": integrations,
        "devops_cards": devops_cards,
        "current_prefs": devops_cache.load_prefs(root),
        "detected_stacks": detected_stacks,
        "_python_version": py_ver,
        "_project_name": root.name,

        # ── Embedded data: one-stop-shop, no secondary API calls ──
        "status_probes": run_all_probes(root),
        "config_data": _wizard_config_data(root),
        "docker_status": _wizard_docker_status(root),
        "gh_cli_status": _wizard_gh_cli_status(root),
        "gh_user": _wizard_gh_user(root),
        "gh_repo_info": _wizard_gh_repo_info(root),
        "gh_environments": _wizard_gh_environments(root),
        "ci_status": _wizard_ci_status(root),
        "gitignore_analysis": _wizard_gitignore_analysis(root),
        "git_remotes": _wizard_git_remotes(root),
        "codeowners_content": _wizard_codeowners_content(root),
    }


# ── Data helpers ────────────────────────────────────────────────────


def _wizard_config_data(root: Path) -> dict:
    """Load project config (modules, environments) for wizard use."""
    try:
        from src.core.config.loader import load_project
        proj = load_project(root / "project.yml")
        modules = [{"name": m.name, "path": m.path, "stack": m.stack,
                     "domain": m.domain, "description": m.description}
                    for m in (proj.modules or [])]
        envs = [{"name": e.name, "default": e.default}
                for e in (proj.environments or [])]
        return {"modules": modules, "environments": envs}
    except Exception:
        return {"modules": [], "environments": []}


def _wizard_docker_status(root: Path) -> dict:
    """Full docker status (version, daemon, compose) for wizard use."""
    try:
        from src.core.services.docker_ops import docker_status
        return docker_status(root)
    except Exception:
        return {"available": False}


def _wizard_gh_cli_status(root: Path) -> dict:
    """GH CLI status (version, auth, repo) for wizard use."""
    try:
        from src.core.services.git_ops import gh_status
        return gh_status(root)
    except Exception:
        return {"available": False}


def _wizard_gh_environments(root: Path) -> dict:
    """GitHub environments list for wizard use."""
    try:
        r = subprocess.run(
            ["gh", "api", "repos/{owner}/{repo}/environments",
             "--jq", ".environments[].name"],
            cwd=str(root), capture_output=True, timeout=10,
        )
        if r.returncode == 0:
            envs = [
                n.strip()
                for n in r.stdout.decode().strip().split("\n")
                if n.strip()
            ]
            return {"available": True, "environments": envs}
        return {"available": False, "environments": []}
    except Exception:
        return {"available": False, "environments": []}


def _wizard_ci_status(root: Path) -> dict:
    """CI status for wizard use."""
    try:
        from src.core.services.ci_ops import ci_status
        return ci_status(root)
    except Exception:
        return {}


def _wizard_gitignore_analysis(root: Path) -> dict:
    """Gitignore analysis for wizard use."""
    try:
        from src.core.services.security_ops import gitignore_analysis
        return gitignore_analysis(root)
    except Exception:
        return {"exists": False, "coverage": 0, "missing_patterns": []}


def _wizard_gh_user(root: Path) -> dict:
    """Get authenticated GitHub user for wizard use."""
    try:
        from src.core.services.git_ops import gh_user
        return gh_user(root)
    except Exception:
        return {"available": False}


def _wizard_gh_repo_info(root: Path) -> dict:
    """Get repo info (visibility, description) for wizard use."""
    try:
        from src.core.services.git_ops import gh_repo_info
        return gh_repo_info(root)
    except Exception:
        return {"available": False}


def _wizard_git_remotes(root: Path) -> dict:
    """Get all git remotes for wizard use."""
    try:
        from src.core.services.git_ops import git_remotes
        return git_remotes(root)
    except Exception:
        return {"available": True, "remotes": []}


def _wizard_codeowners_content(root: Path) -> str:
    """Read existing CODEOWNERS file content, or empty string if absent."""
    try:
        co_path = root / ".github" / "CODEOWNERS"
        if co_path.is_file():
            return co_path.read_text(encoding="utf-8")
    except Exception:
        pass
    return ""


# ═══════════════════════════════════════════════════════════════════
# Re-exports — backward compatibility
# ═══════════════════════════════════════════════════════════════════

from src.core.services.wizard_setup import (  # noqa: F401, E402
    setup_git,
    setup_github,
    setup_docker,
    setup_k8s,
    setup_ci,
    setup_terraform,
    wizard_setup,
    delete_generated_configs,
)

