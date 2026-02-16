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
#  Wizard setup actions — generate configs, apply settings
# ═══════════════════════════════════════════════════════════════════


def setup_git(root: Path, data: dict) -> dict:
    """Configure git: init, branch, .gitignore, remote, hooks, commit."""
    from src.core.services import devops_cache

    results: list[str] = []
    files_created: list[str] = []

    # 1. git init (if needed)
    if not (root / ".git").is_dir():
        subprocess.run(
            ["git", "init"], cwd=str(root),
            check=True, capture_output=True, timeout=10,
        )
        files_created.append(".git/")
        results.append("Repository initialized")

    # 2. Default branch rename (if requested and different)
    default_branch = data.get("default_branch", "").strip()
    if default_branch:
        r_cur = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(root), capture_output=True, timeout=5,
        )
        current = r_cur.stdout.decode().strip() if r_cur.returncode == 0 else ""
        if current and current != default_branch:
            subprocess.run(
                ["git", "branch", "-m", current, default_branch],
                cwd=str(root), capture_output=True, timeout=5,
            )
            results.append(f"Branch renamed: {current} → {default_branch}")

    # 3. Write .gitignore (if content provided)
    gitignore_content = data.get("gitignore_content", "").strip()
    if gitignore_content:
        gi_path = root / ".gitignore"
        gi_path.write_text(gitignore_content + "\n", encoding="utf-8")
        files_created.append(".gitignore")
        pattern_count = sum(
            1 for line in gitignore_content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
        results.append(f".gitignore created ({pattern_count} patterns)")

    # 4. Remote setup
    remote = data.get("remote", "").strip()
    if remote:
        subprocess.run(
            ["git", "remote", "remove", "origin"],
            cwd=str(root), capture_output=True, timeout=5,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", remote],
            cwd=str(root), check=True,
            capture_output=True, timeout=5,
        )
        results.append(f"Remote set: origin → {remote}")

    # 5. Pre-commit hook (if requested)
    if data.get("setup_hooks"):
        hooks_dir = root / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        hook_path = hooks_dir / "pre-commit"
        hook_cmds = data.get("hook_commands", [])
        if hook_cmds:
            hook_content = "#!/bin/sh\n# Auto-generated pre-commit hook\nset -e\n\n"
            for cmd in hook_cmds:
                hook_content += f'echo "→ Running {cmd}..."\n{cmd}\n\n'
            hook_path.write_text(hook_content, encoding="utf-8")
            hook_path.chmod(0o755)
            results.append(f"Pre-commit hook installed ({len(hook_cmds)} checks)")

    # 6. Initial commit (if requested)
    if data.get("create_initial_commit"):
        commit_msg = data.get("commit_message", "Initial commit").strip()
        subprocess.run(
            ["git", "add", "."],
            cwd=str(root), capture_output=True, timeout=10,
        )
        r_commit = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=str(root), capture_output=True, timeout=10,
        )
        if r_commit.returncode == 0:
            r_hash = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(root), capture_output=True, timeout=5,
            )
            short_hash = r_hash.stdout.decode().strip() if r_hash.returncode == 0 else "?"
            results.append(f"Initial commit: {short_hash}")
        else:
            results.append("Initial commit skipped (nothing to commit)")

    devops_cache.record_event(
        root,
        label="💻 Git Setup",
        summary=f"Git configured: {', '.join(results) or 'no changes'}",
        detail={"results": results, "files_created": files_created},
        card="wizard",
        action="configured",
        target="git",
    )

    return {
        "ok": True,
        "message": "Git repository configured",
        "files_created": files_created,
        "results": results,
    }


def setup_github(root: Path, data: dict) -> dict:
    """Configure GitHub: environments, secrets, CODEOWNERS."""
    from src.core.services import devops_cache, secrets_ops

    results: dict = {
        "environments_created": [],
        "environments_failed": [],
        "secrets_pushed": 0,
        "codeowners_written": False,
    }

    # 1. Create deployment environments
    env_names = data.get("create_environments", [])
    for env_name in env_names:
        try:
            r = secrets_ops.create_environment(root, env_name)
            if r.get("success"):
                results["environments_created"].append(env_name)
            else:
                results["environments_failed"].append(
                    {"name": env_name, "error": r.get("error", "unknown")}
                )
        except Exception as exc:
            results["environments_failed"].append(
                {"name": env_name, "error": str(exc)}
            )

    # 2. Push secrets to GitHub (bulk)
    if data.get("push_secrets"):
        try:
            push_result = secrets_ops.push_secrets(
                root,
                push_to_github=True,
                save_to_env=False,
            )
            results["secrets_pushed"] = len(push_result.get("pushed", []))
        except Exception as exc:
            results["secrets_push_error"] = str(exc)

    # 3. Write CODEOWNERS (optional)
    codeowners_content = data.get("codeowners_content", "").strip()
    if codeowners_content:
        try:
            co_path = root / ".github" / "CODEOWNERS"
            co_path.parent.mkdir(parents=True, exist_ok=True)
            co_path.write_text(codeowners_content + "\n", encoding="utf-8")
            results["codeowners_written"] = True
        except Exception as exc:
            results["codeowners_error"] = str(exc)

    devops_cache.record_event(
        root,
        label="🐙 GitHub Setup",
        summary=(
            f"GitHub configured: "
            f"{len(results.get('environments_created', []))} env(s), "
            f"{results.get('secrets_pushed', 0)} secret(s)"
        ),
        detail=results,
        card="wizard",
        action="configured",
        target="github",
    )

    return {
        "ok": True,
        "message": "GitHub configuration applied",
        "results": results,
    }


def setup_docker(root: Path, data: dict) -> dict:
    """Generate Dockerfile and optional docker-compose.yml."""
    from src.core.services import devops_cache

    base_image = data.get("base_image", "python:3.12-slim")
    workdir = data.get("workdir", "/app")
    install_cmd = data.get("install_cmd", "pip install -e .")
    port = data.get("port", "8080")
    cmd = data.get("cmd", "python -m src")
    overwrite = data.get("overwrite", False)
    compose = data.get("compose", False)

    files_created: list[str] = []

    cmd_parts = cmd.split()
    cmd_json = ", ".join(f'"{p}"' for p in cmd_parts)

    dest = root / "Dockerfile"
    if dest.exists() and not overwrite:
        return {
            "ok": False,
            "error": "Dockerfile already exists. Check 'Overwrite' to replace.",
        }
    dest.write_text(
        f"FROM {base_image}\n\n"
        f"WORKDIR {workdir}\n"
        f"COPY . .\n"
        f"RUN pip install --no-cache-dir --upgrade pip && \\\n"
        f"    {install_cmd}\n\n"
        f"EXPOSE {port}\n"
        f"CMD [{cmd_json}]\n"
    )
    files_created.append("Dockerfile")

    if compose:
        compose_dest = root / "docker-compose.yml"
        if not compose_dest.exists() or overwrite:
            name = root.name.replace(" ", "-").lower()
            compose_dest.write_text(
                f'version: "3.9"\n'
                f"services:\n"
                f"  app:\n"
                f"    build: .\n"
                f"    container_name: {name}\n"
                f"    ports:\n"
                f'      - "{port}:{port}"\n'
                f"    volumes:\n"
                f"      - .:{workdir}\n"
                f"    restart: unless-stopped\n"
            )
            files_created.append("docker-compose.yml")

    devops_cache.record_event(
        root,
        label="🐳 Docker Setup",
        summary=f"Docker configured ({', '.join(files_created)})",
        detail={"files_created": files_created},
        card="wizard",
        action="configured",
        target="docker",
    )

    return {
        "ok": True,
        "message": "Docker configuration generated",
        "files_created": files_created,
    }


def setup_k8s(root: Path, data: dict) -> dict:
    """Generate Kubernetes manifests from wizard state."""
    from src.core.services import devops_cache
    from src.core.services.k8s_ops import (
        wizard_state_to_resources,
        generate_k8s_wizard,
        _generate_skaffold,
    )

    files_created: list[str] = []

    # Translate wizard state → flat resource list
    resources = wizard_state_to_resources(data)

    # Generate manifests (returns {ok, files} or {error})
    result = generate_k8s_wizard(root, resources)
    if result.get("error"):
        return {"ok": False, "error": result["error"]}

    # Collect all files to write (manifests + optional skaffold)
    all_files = list(result.get("files", []))

    # Generate skaffold.yaml if checkbox was checked
    skaffold_file = _generate_skaffold(data, all_files)
    if skaffold_file:
        all_files.append(skaffold_file)

    # Write generated files to disk
    skipped: list[str] = []
    for f in all_files:
        fpath = root / f["path"]
        if fpath.exists() and not f.get("overwrite", True):
            skipped.append(f["path"])
            continue
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(f["content"])
        files_created.append(f["path"])

    resp: dict = {
        "ok": True,
        "message": f"Kubernetes manifests generated ({len(files_created)} files)",
        "files_created": files_created,
    }
    if skipped:
        resp["files_skipped"] = skipped
        resp["message"] += f", {len(skipped)} skipped (already exist)"

    devops_cache.record_event(
        root,
        label="☸️ K8s Setup",
        summary=(
            f"K8s manifests generated ({len(files_created)} files"
            + (f", {len(skipped)} skipped" if skipped else "")
            + ")"
        ),
        detail={"files_created": files_created, "files_skipped": skipped},
        card="wizard",
        action="configured",
        target="kubernetes",
    )

    return resp


def setup_ci(root: Path, data: dict) -> dict:
    """Generate CI workflow YAML."""
    from src.core.services import devops_cache

    branches_str = data.get("branches", "main, master")
    branches = [b.strip() for b in branches_str.split(",") if b.strip()]
    py_ver = data.get("python_version", "3.12")
    install_cmd = data.get("install_cmd", 'pip install -e ".[dev]"')
    test_cmd = data.get("test_cmd", "python -m pytest tests/ -v --tb=short")
    lint = data.get("lint", False)
    lint_cmd = data.get("lint_cmd", "ruff check src/")
    overwrite = data.get("overwrite", False)

    files_created: list[str] = []

    wf_dir = root / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    dest = wf_dir / "ci.yml"

    if dest.exists() and not overwrite:
        return {
            "ok": False,
            "error": "CI workflow already exists. Check 'Overwrite' to replace.",
        }

    branch_list = ", ".join(branches)
    steps = (
        f"      - uses: actions/checkout@v4\n"
        f"      - uses: actions/setup-python@v5\n"
        f"        with:\n"
        f'          python-version: "{py_ver}"\n'
        f"      - run: {install_cmd}\n"
        f"      - run: {test_cmd}\n"
    )
    if lint:
        steps += f"      - run: {lint_cmd}\n"

    dest.write_text(
        f"name: CI\n"
        f"on:\n"
        f"  push:\n"
        f"    branches: [{branch_list}]\n"
        f"  pull_request:\n"
        f"    branches: [{branch_list}]\n\n"
        f"jobs:\n"
        f"  test:\n"
        f"    runs-on: ubuntu-latest\n"
        f"    steps:\n"
        f"{steps}"
    )
    files_created.append(".github/workflows/ci.yml")

    devops_cache.record_event(
        root,
        label="⚙️ CI Setup",
        summary=f"CI workflow generated ({', '.join(files_created)})",
        detail={"files_created": files_created, "branches": branches},
        card="wizard",
        action="configured",
        target="ci",
    )

    return {
        "ok": True,
        "message": "CI workflow generated",
        "files_created": files_created,
    }


def setup_terraform(root: Path, data: dict) -> dict:
    """Generate Terraform main.tf with provider and backend."""
    from src.core.services import devops_cache

    provider = data.get("provider", "aws")
    region = data.get("region", "us-east-1")
    project_name = data.get("project_name", "app")
    backend = data.get("backend", "local")
    overwrite = data.get("overwrite", False)

    files_created: list[str] = []

    tf_dir = root / "terraform"
    tf_dir.mkdir(exist_ok=True)
    tf_main = tf_dir / "main.tf"

    if tf_main.exists() and not overwrite:
        return {
            "ok": False,
            "error": "Terraform config exists. Check 'Overwrite' to replace.",
        }

    provider_blocks = {
        "aws": f'provider "aws" {{\n  region = "{region}"\n}}\n',
        "google": f'provider "google" {{\n  project = "{project_name}"\n  region  = "{region}"\n}}\n',
        "azurerm": f'provider "azurerm" {{\n  features {{}}\n}}\n',
        "digitalocean": f'provider "digitalocean" {{\n  # token = var.do_token\n}}\n',
    }
    prov_block = provider_blocks.get(provider, f'# provider "{provider}" {{}}\n')

    backend_blocks = {
        "local": "",
        "s3": (
            f'  backend "s3" {{\n'
            f'    bucket = "{project_name}-tfstate"\n'
            f'    key    = "state/terraform.tfstate"\n'
            f'    region = "{region}"\n'
            f"  }}\n"
        ),
        "gcs": (
            f'  backend "gcs" {{\n'
            f'    bucket = "{project_name}-tfstate"\n'
            f'    prefix = "terraform/state"\n'
            f"  }}\n"
        ),
        "azurerm": (
            f'  backend "azurerm" {{\n'
            f'    resource_group_name  = "{project_name}-rg"\n'
            f'    storage_account_name = "{project_name}sa"\n'
            f'    container_name       = "tfstate"\n'
            f'    key                  = "terraform.tfstate"\n'
            f"  }}\n"
        ),
    }
    be_block = backend_blocks.get(backend, "")

    tf_main.write_text(
        f'terraform {{\n'
        f'  required_version = ">= 1.0"\n'
        f'{be_block}'
        f'}}\n\n'
        f'{prov_block}\n'
        f'# Add resources below\n'
    )
    files_created.append("terraform/main.tf")

    devops_cache.record_event(
        root,
        label="🏗️ Terraform Setup",
        summary=f"Terraform config generated (provider={provider}, backend={backend})",
        detail={"files_created": files_created, "provider": provider, "backend": backend},
        card="wizard",
        action="configured",
        target="terraform",
    )

    return {
        "ok": True,
        "message": "Terraform configuration generated",
        "files_created": files_created,
    }


# ── Dispatcher ──────────────────────────────────────────────────────

_SETUP_ACTIONS = {
    "setup_git": setup_git,
    "setup_github": setup_github,
    "setup_docker": setup_docker,
    "setup_k8s": setup_k8s,
    "setup_ci": setup_ci,
    "setup_terraform": setup_terraform,
}


def wizard_setup(root: Path, action: str, data: dict) -> dict:
    """Dispatch a wizard setup action.

    Returns:
        {"ok": True, ...} on success
        {"ok": False, "error": "..."} on failure
    """
    fn = _SETUP_ACTIONS.get(action)
    if not fn:
        return {"ok": False, "error": f"Unknown action: {action}"}
    return fn(root, data)


# ── Delete generated configs ───────────────────────────────────────


def delete_generated_configs(root: Path, target: str) -> dict:
    """Delete wizard-generated config files.

    Args:
        target: "docker" | "k8s" | "ci" | "terraform" | "all"
    """
    import shutil as _shutil

    from src.core.services import devops_cache

    deleted: list[str] = []
    errors: list[str] = []

    targets = [target] if target != "all" else [
        "docker", "k8s", "ci", "terraform",
    ]

    for t in targets:
        try:
            if t == "docker":
                for f in ["Dockerfile", ".dockerignore"]:
                    fp = root / f
                    if fp.is_file():
                        fp.unlink()
                        deleted.append(f)
                for f in root.glob("docker-compose*.y*ml"):
                    rel = str(f.relative_to(root))
                    f.unlink()
                    deleted.append(rel)
            elif t == "k8s":
                k8s_dir = root / "k8s"
                if k8s_dir.is_dir():
                    _shutil.rmtree(k8s_dir)
                    deleted.append("k8s/")
            elif t == "ci":
                ci = root / ".github" / "workflows" / "ci.yml"
                if ci.is_file():
                    ci.unlink()
                    deleted.append(".github/workflows/ci.yml")
            elif t == "terraform":
                tf_dir = root / "terraform"
                if tf_dir.is_dir():
                    _shutil.rmtree(tf_dir)
                    deleted.append("terraform/")
            else:
                errors.append(f"Unknown target: {t}")
        except Exception as e:
            errors.append(f"{t}: {e}")

    devops_cache.record_event(
        root,
        label="🗑️ Wizard Config Deleted",
        summary=(
            f"Wizard config deleted: {', '.join(deleted) or 'nothing'}"
            + (f" ({len(errors)} error(s))" if errors else "")
        ),
        detail={"target": target, "deleted": deleted, "errors": errors},
        card="wizard",
        action="deleted",
        target=target,
    )

    return {
        "ok": len(errors) == 0,
        "deleted": deleted,
        "errors": errors,
    }
