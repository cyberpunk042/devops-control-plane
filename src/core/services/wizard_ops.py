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
        "dns_dir":        (root / "dns").is_dir(),
        "cdn_dir":        (root / "cdn").is_dir(),
        "cname_file":     (root / "CNAME").is_file(),
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
            "detected": files["dns_dir"] or files["cdn_dir"] or files["cname_file"],
            "status": ("ready" if files["dns_dir"] or files["cdn_dir"]
                       else "partial" if files["cname_file"]
                       else "missing"),
            "suggest": ("auto" if files["dns_dir"] or files["cdn_dir"]
                        else "manual" if files["cname_file"]
                        else "hidden"),
            "label": "🌐 DNS & CDN",
            "has_dns_dir": files["dns_dir"],
            "has_cdn_dir": files["cdn_dir"],
            "has_cname": files["cname_file"],
            "setup_actions": (
                [] if files["dns_dir"] and files["cdn_dir"]
                else ["setup_dns"]
            ),
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
        "stack_defaults": _wizard_stack_defaults(root, detected_stacks),
        "_python_version": py_ver,
        "_project_name": root.name,

        # ── Embedded data: one-stop-shop, no secondary API calls ──
        "status_probes": run_all_probes(root),
        "config_data": _wizard_config_data(root),
        "docker_status": _wizard_docker_status(root),
        "k8s_status": _wizard_k8s_status(root),
        "terraform_status": _wizard_terraform_status(root),
        "dns_status": _wizard_dns_status(root),
        "gh_cli_status": _wizard_gh_cli_status(root),
        "gh_user": _wizard_gh_user(root),
        "gh_repo_info": _wizard_gh_repo_info(root),
        "gh_environments": _wizard_gh_environments(root),
        "ci_status": _wizard_ci_status(root),
        "gitignore_analysis": _wizard_gitignore_analysis(root),
        "git_remotes": _wizard_git_remotes(root),
        "codeowners_content": _wizard_codeowners_content(root),
        "env_status": _wizard_env_status(root),
        "pages_status": _wizard_pages_status(root),
    }


# ── Stack defaults — derive wizard form defaults from detected stacks ──


# Language family → Docker base image template.
# {version} is replaced at runtime with detected or default version.
_DOCKER_IMAGES: dict[str, str] = {
    "python":  "python:{version}-slim",
    "go":      "golang:{version}-alpine",
    "node":    "node:{version}-alpine",
    "rust":    "rust:{version}-slim",
    "java":    "eclipse-temurin:{version}-jdk-alpine",
    "dotnet":  "mcr.microsoft.com/dotnet/sdk:{version}",
    "ruby":    "ruby:{version}-slim",
    "elixir":  "elixir:{version}-slim",
    "php":     "php:{version}-cli",
    "c":       "gcc:latest",
    "cpp":     "gcc:latest",
    "swift":   "swift:{version}",
    "zig":     "alpine:latest",
}

# Language family → CI workflow version key (for actions/setup-*).
_CI_VERSION_KEYS: dict[str, str] = {
    "python": "python-version",
    "go":     "go-version",
    "node":   "node-version",
    "rust":   "toolchain",
    "java":   "java-version",
    "dotnet":  "dotnet-version",
    "ruby":   "ruby-version",
    "elixir": "elixir-version",
}

# Default ports by framework (best-effort hints, user can override).
_FRAMEWORK_PORTS: dict[str, str] = {
    "python-flask":   "5000",
    "python-fastapi": "8000",
    "python-django":  "8000",
    "node-express":   "3000",
    "node-nextjs":    "3000",
    "node-react":     "3000",
    "go-gin":         "8080",
    "go-fiber":       "3000",
    "ruby-rails":     "3000",
    "ruby-sinatra":   "4567",
    "elixir-phoenix": "4000",
    "rust-actix":     "8080",
    "rust-axum":      "3000",
    "dotnet-aspnet":  "5000",
    "dotnet-blazor":  "5000",
}

# Default language versions (fallback when requires.min_version is empty).
_DEFAULT_VERSIONS: dict[str, str] = {
    "python": f"{sys.version_info.major}.{sys.version_info.minor}",
    "go":     "1.22",
    "node":   "20",
    "rust":   "stable",
    "java":   "21",
    "dotnet":  "8.0",
    "ruby":   "3.3",
    "elixir": "1.16",
    "php":    "8.3",
    "swift":  "5.10",
}


def _wizard_stack_defaults(
    root: Path,
    detected_stacks: list[str],
) -> dict:
    """Derive wizard-relevant defaults from detected stacks.

    Returns a dict the frontend can use to populate sub-wizard forms
    with stack-appropriate defaults instead of hardcoded Python values.

    Falls back gracefully: if no stacks are detected or resolution
    fails, returns a generic Python-based default set.
    """
    # ── Resolve stacks ──────────────────────────────────────────
    stacks_dir = root / "stacks"
    resolved: dict = {}
    try:
        from src.core.config.stack_loader import discover_stacks
        resolved = discover_stacks(stacks_dir)
    except Exception:
        pass

    # Pick primary stack: most specific (flavored > base).
    # detected_stacks is sorted alphabetically; prefer longest name
    # (likely the most specific flavored stack).
    primary = None
    for name in sorted(detected_stacks, key=len, reverse=True):
        if name in resolved:
            primary = resolved[name]
            break

    if not primary:
        # Fallback: generic defaults
        return _generic_stack_defaults()

    # ── Extract language family ─────────────────────────────────
    family = primary.parent or primary.name  # base stack name

    # ── Version ─────────────────────────────────────────────────
    version = _DEFAULT_VERSIONS.get(family, "latest")
    for req in primary.requires:
        if req.min_version:
            version = req.min_version
            break
    # For Python, use the running interpreter version (more accurate)
    if family == "python":
        version = f"{sys.version_info.major}.{sys.version_info.minor}"

    # ── Capabilities → commands ─────────────────────────────────
    caps: dict[str, str] = {}
    for cap in primary.capabilities:
        caps[cap.name] = cap.command

    # ── Docker defaults ─────────────────────────────────────────
    image_tpl = _DOCKER_IMAGES.get(family, "alpine:latest")
    base_image = image_tpl.replace("{version}", version)

    # Entry command: prefer serve, then run, then build
    entry_cmd = caps.get("serve") or caps.get("run") or caps.get("build") or ""
    # For Docker, bind to 0.0.0.0 if the serve command has --debug or localhost
    if entry_cmd and family == "python" and "--debug" in entry_cmd:
        entry_cmd = entry_cmd.replace("--debug", "--host=0.0.0.0")

    port = _FRAMEWORK_PORTS.get(primary.name, "8080")

    # ── CI defaults ─────────────────────────────────────────────
    ci_version_key = _CI_VERSION_KEYS.get(family, "")

    return {
        "primary_stack": primary.name,
        "language_family": family,
        "icon": primary.icon or "",
        "domain": primary.domain,
        "docker": {
            "base_image": base_image,
            "install_cmd": caps.get("install", ""),
            "entry_cmd": entry_cmd,
            "workdir": "/app",
            "port": port,
        },
        "ci": {
            "install_cmd": caps.get("install", ""),
            "test_cmd": caps.get("test", ""),
            "lint_cmd": caps.get("lint", ""),
            "format_cmd": caps.get("format", ""),
            "language_version": version,
            "language_key": ci_version_key,
            "language_label": family.capitalize() + " Version",
        },
        "capabilities": caps,
    }


def _generic_stack_defaults() -> dict:
    """Fallback defaults when no stacks are detected."""
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    return {
        "primary_stack": "",
        "language_family": "python",
        "icon": "🐍",
        "domain": "service",
        "docker": {
            "base_image": f"python:{py_ver}-slim",
            "install_cmd": "pip install -e .",
            "entry_cmd": "python -m src",
            "workdir": "/app",
            "port": "8080",
        },
        "ci": {
            "install_cmd": 'pip install -e ".[dev]" || pip install -e .',
            "test_cmd": "pytest",
            "lint_cmd": "ruff check .",
            "format_cmd": "ruff format .",
            "language_version": py_ver,
            "language_key": "python-version",
            "language_label": "Python Version",
        },
        "capabilities": {
            "install": "pip install -e .",
            "lint": "ruff check .",
            "format": "ruff format .",
            "test": "pytest",
        },
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


def _wizard_k8s_status(root: Path) -> dict:
    """Full K8s detection (manifests, helm, kustomize, tools) for wizard use."""
    try:
        from src.core.services.k8s_detect import k8s_status
        return k8s_status(root)
    except Exception:
        return {"has_k8s": False, "kubectl": {"available": False, "version": None}}


def _wizard_terraform_status(root: Path) -> dict:
    """Full Terraform detection (CLI, files, providers, modules, backend) for wizard use."""
    try:
        from src.core.services.terraform_ops import terraform_status
        return terraform_status(root)
    except Exception:
        return {"has_terraform": False, "cli": {"available": False, "version": None}}


def _wizard_dns_status(root: Path) -> dict:
    """Full DNS/CDN detection (providers, domains, certs, files) for wizard use."""
    try:
        from src.core.services.dns_cdn_ops import dns_cdn_status
        return dns_cdn_status(root)
    except Exception:
        return {"has_dns": False, "has_cdn": False, "cdn_providers": [], "domains": []}


def _wizard_env_status(root: Path) -> dict:
    """Env var status (files, vars, validation) for wizard use."""
    try:
        from src.core.services.env_ops import env_status
        return env_status(root)
    except Exception:
        return {"files": [], "has_env": False, "has_example": False, "total_vars": 0}


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


def _wizard_pages_status(root: Path) -> dict:
    """Pages status for wizard use — segments, meta, content folders."""
    result: dict = {
        "segments": [],
        "meta": {},
        "content_folders": [],
        "can_auto_init": False,
        "builders_available": [],
    }
    try:
        from src.core.services.pages_engine import get_pages_meta, get_segments
        from src.core.services.pages_discovery import (
            detect_best_builder,
            list_builders_detail,
        )

        # Existing segments
        segments = get_segments(root)
        result["segments"] = [
            {
                "name": s.name,
                "builder": s.builder,
                "source": s.source,
                "path": s.path,
                "auto": s.auto,
            }
            for s in segments
        ]

        # Pages metadata
        result["meta"] = get_pages_meta(root)

        # Available builders (slim summary)
        builders = list_builders_detail()
        result["builders_available"] = [
            {"name": b["name"], "label": b["label"], "available": b["available"]}
            for b in builders
        ]

        # Content folders — scan directly to avoid circular import
        # with content_listing ↔ content_crypto
        _DEFAULT_DIRS = ["docs", "content", "media", "assets", "archive"]
        dir_names = _DEFAULT_DIRS
        try:
            import yaml as _yaml
            pf = root / "project.yml"
            if pf.is_file():
                data = _yaml.safe_load(pf.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    cf = data.get("content_folders")
                    if isinstance(cf, list) and cf:
                        dir_names = cf
        except Exception:
            pass

        existing_names = {s.name for s in segments}
        for dir_name in dir_names:
            folder_path = root / dir_name
            if not folder_path.is_dir():
                continue
            # Count files (non-recursive, keep it light)
            file_count = sum(1 for f in folder_path.iterdir() if f.is_file())
            builder_name, reason, suggestion = detect_best_builder(folder_path)
            result["content_folders"].append({
                "name": dir_name,
                "file_count": file_count,
                "best_builder": builder_name,
                "reason": reason,
                "suggestion": suggestion,
                "has_segment": dir_name in existing_names,
            })

        # Can auto-init if there are content folders without segments
        uninit = [
            cf for cf in result["content_folders"]
            if not cf["has_segment"]
        ]
        result["can_auto_init"] = len(uninit) > 0

    except Exception:
        logger.exception("_wizard_pages_status failed")
    return result


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
    setup_dns,
    setup_pages,
    wizard_setup,
    delete_generated_configs,
)

