"""
DevOps dashboard routes — preferences and cache management.

Blueprint: devops_bp
Prefix: /api

Endpoints:
    GET  /devops/prefs           — card load preferences (devops tab)
    PUT  /devops/prefs           — save card load preferences
    GET  /integrations/prefs     — integration card preferences (int:* keys)
    PUT  /integrations/prefs     — save integration card preferences
    GET  /wizard/detect          — detect tools, files, suggest prefs
    POST /devops/cache/bust      — bust server-side cache (all or specific)
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import devops_cache

devops_bp = Blueprint("devops", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


# ── Card preferences ────────────────────────────────────────────


@devops_bp.route("/devops/prefs")
def devops_prefs_get():
    """Get card load preferences."""
    return jsonify(devops_cache.load_prefs(_project_root()))


@devops_bp.route("/devops/prefs", methods=["PUT"])
def devops_prefs_put():
    """Save card load preferences."""
    data = request.get_json(silent=True) or {}
    result = devops_cache.save_prefs(_project_root(), data)
    return jsonify(result)


# ── Integration card preferences ────────────────────────────────


@devops_bp.route("/integrations/prefs")
def integration_prefs_get():
    """Get integration card load preferences (int:* keys only)."""
    all_prefs = devops_cache.load_prefs(_project_root())
    return jsonify({k: v for k, v in all_prefs.items() if k.startswith("int:")})


@devops_bp.route("/integrations/prefs", methods=["PUT"])
def integration_prefs_put():
    """Save integration card load preferences."""
    data = request.get_json(silent=True) or {}
    # Merge with all existing prefs (only update int:* keys)
    all_prefs = devops_cache.load_prefs(_project_root())
    for k, v in data.items():
        if k.startswith("int:") and v in ("auto", "manual", "hidden", "visible"):
            all_prefs[k] = v
    result = devops_cache.save_prefs(_project_root(), all_prefs)
    return jsonify({k: v for k, v in result.items() if k.startswith("int:")})


# ── Wizard: environment detection ───────────────────────────────


@devops_bp.route("/wizard/detect")
def wizard_detect():
    """Detect available integrations, tools, and project characteristics.

    Returns a lightweight snapshot used by the setup wizard to suggest
    which integrations to enable and which tools to install.
    """
    import shutil

    root = _project_root()

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

    # ── Per-integration suggestions ─────────────────────────────
    # For tools that need connectivity, verify they actually work
    _docker_ok = False
    if tools["docker"]:
        import subprocess
        try:
            r = subprocess.run(
                ["docker", "info"], capture_output=True, timeout=5,
            )
            _docker_ok = r.returncode == 0
        except Exception:
            pass

    _kubectl_ok = False
    if tools["kubectl"]:
        import subprocess
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
        import subprocess
        try:
            r = subprocess.run(
                ["terraform", "version"], capture_output=True, timeout=5,
            )
            _terraform_ok = r.returncode == 0
        except Exception:
            pass

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

    import sys
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"

    return jsonify({
        "tools": tools,
        "files": files,
        "integrations": integrations,
        "devops_cards": devops_cards,
        "current_prefs": devops_cache.load_prefs(root),
        "_python_version": py_ver,
        "_project_name": root.name,
    })


# ── Wizard: setup actions ───────────────────────────────────────



@devops_bp.route("/wizard/setup", methods=["POST"])
def wizard_setup():
    """Execute a setup action using user-provided configuration.

    Each action accepts form fields from the sub-wizard UI.
    """
    import subprocess

    data = request.get_json(silent=True) or {}
    action = data.get("action", "")
    root = _project_root()

    if not action:
        return jsonify({"ok": False, "error": "No action specified"}), 400

    files_created: list[str] = []

    try:
        # ── setup_git ───────────────────────────────────────────
        if action == "setup_git":
            if not (root / ".git").is_dir():
                subprocess.run(
                    ["git", "init"], cwd=str(root),
                    check=True, capture_output=True, timeout=10,
                )
                files_created.append(".git/")
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
            return jsonify({
                "ok": True,
                "message": "Git repository configured",
                "files_created": files_created,
            })

        # ── setup_docker ────────────────────────────────────────
        if action == "setup_docker":
            base_image = data.get("base_image", "python:3.12-slim")
            workdir = data.get("workdir", "/app")
            install_cmd = data.get("install_cmd", "pip install -e .")
            port = data.get("port", "8080")
            cmd = data.get("cmd", "python -m src")
            overwrite = data.get("overwrite", False)
            compose = data.get("compose", False)

            cmd_parts = cmd.split()
            cmd_json = ", ".join(f'"{p}"' for p in cmd_parts)

            dest = root / "Dockerfile"
            if dest.exists() and not overwrite:
                return jsonify({
                    "ok": False,
                    "error": "Dockerfile already exists. Check 'Overwrite' to replace.",
                })
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

            return jsonify({
                "ok": True,
                "message": "Docker configuration generated",
                "files_created": files_created,
            })

        # ── setup_k8s ───────────────────────────────────────────
        if action == "setup_k8s":
            app_name = data.get("app_name", "app")
            image = data.get("image", f"{app_name}:latest")
            port = data.get("port", "8080")
            replicas = data.get("replicas", "1")
            namespace = data.get("namespace", "default")
            svc_type = data.get("service_type", "ClusterIP")

            k8s_dir = root / "k8s"
            k8s_dir.mkdir(exist_ok=True)

            deploy = k8s_dir / "deployment.yml"
            deploy.write_text(
                f"apiVersion: apps/v1\n"
                f"kind: Deployment\n"
                f"metadata:\n"
                f"  name: {app_name}\n"
                f"  namespace: {namespace}\n"
                f"spec:\n"
                f"  replicas: {replicas}\n"
                f"  selector:\n"
                f"    matchLabels:\n"
                f"      app: {app_name}\n"
                f"  template:\n"
                f"    metadata:\n"
                f"      labels:\n"
                f"        app: {app_name}\n"
                f"    spec:\n"
                f"      containers:\n"
                f"        - name: {app_name}\n"
                f"          image: {image}\n"
                f"          ports:\n"
                f"            - containerPort: {port}\n"
            )
            files_created.append("k8s/deployment.yml")

            svc = k8s_dir / "service.yml"
            svc.write_text(
                f"apiVersion: v1\n"
                f"kind: Service\n"
                f"metadata:\n"
                f"  name: {app_name}\n"
                f"  namespace: {namespace}\n"
                f"spec:\n"
                f"  selector:\n"
                f"    app: {app_name}\n"
                f"  ports:\n"
                f"    - port: 80\n"
                f"      targetPort: {port}\n"
                f"  type: {svc_type}\n"
            )
            files_created.append("k8s/service.yml")

            return jsonify({
                "ok": True,
                "message": "Kubernetes manifests generated",
                "files_created": files_created,
            })

        # ── setup_ci ────────────────────────────────────────────
        if action == "setup_ci":
            branches_str = data.get("branches", "main, master")
            branches = [b.strip() for b in branches_str.split(",") if b.strip()]
            py_ver = data.get("python_version", "3.12")
            install_cmd = data.get("install_cmd", 'pip install -e ".[dev]"')
            test_cmd = data.get("test_cmd", "python -m pytest tests/ -v --tb=short")
            lint = data.get("lint", False)
            lint_cmd = data.get("lint_cmd", "ruff check src/")
            overwrite = data.get("overwrite", False)

            wf_dir = root / ".github" / "workflows"
            wf_dir.mkdir(parents=True, exist_ok=True)
            dest = wf_dir / "ci.yml"

            if dest.exists() and not overwrite:
                return jsonify({
                    "ok": False,
                    "error": "CI workflow already exists. Check 'Overwrite' to replace.",
                })

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

            return jsonify({
                "ok": True,
                "message": "CI workflow generated",
                "files_created": files_created,
            })

        # ── setup_terraform ─────────────────────────────────────
        if action == "setup_terraform":
            provider = data.get("provider", "aws")
            region = data.get("region", "us-east-1")
            project_name = data.get("project_name", "app")
            backend = data.get("backend", "local")
            overwrite = data.get("overwrite", False)

            tf_dir = root / "terraform"
            tf_dir.mkdir(exist_ok=True)
            tf_main = tf_dir / "main.tf"

            if tf_main.exists() and not overwrite:
                return jsonify({
                    "ok": False,
                    "error": "Terraform config exists. Check 'Overwrite' to replace.",
                })

            provider_blocks = {
                "aws": f'provider "aws" {{\n  region = "{region}"\n}}\n',
                "google": f'provider "google" {{\n  project = "{project_name}"\n  region  = "{region}"\n}}\n',
                "azurerm": f'provider "azurerm" {{\n  features {{}}\n}}\n',
                "digitalocean": f'provider "digitalocean" {{\n  # token = var.do_token\n}}\n',
            }
            prov_block = provider_blocks.get(provider, f'# provider "{provider}" {{}}\n')

            backend_blocks = {
                "local": "",
                "s3": f'  backend "s3" {{\n    bucket = "{project_name}-tfstate"\n    key    = "state/terraform.tfstate"\n    region = "{region}"\n  }}\n',
                "gcs": f'  backend "gcs" {{\n    bucket = "{project_name}-tfstate"\n    prefix = "terraform/state"\n  }}\n',
                "azurerm": f'  backend "azurerm" {{\n    resource_group_name  = "{project_name}-rg"\n    storage_account_name = "{project_name}sa"\n    container_name       = "tfstate"\n    key                  = "terraform.tfstate"\n  }}\n',
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

            return jsonify({
                "ok": True,
                "message": "Terraform configuration generated",
                "files_created": files_created,
            })

        return jsonify({"ok": False, "error": f"Unknown action: {action}"}), 400

    except subprocess.CalledProcessError as e:
        return jsonify({
            "ok": False,
            "error": f"Command failed: {e.cmd}",
            "stderr": (e.stderr or b"").decode(errors="replace"),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Wizard: delete generated configs ────────────────────────────


@devops_bp.route("/wizard/config", methods=["DELETE"])
def wizard_delete_config():
    """Delete wizard-generated config files.

    Body: {"target": "docker" | "k8s" | "ci" | "terraform" | "all"}
    """
    import shutil as _shutil

    data = request.get_json(silent=True) or {}
    target = data.get("target", "")
    root = _project_root()

    if not target:
        return jsonify({"ok": False, "error": "Missing 'target'"}), 400

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

    return jsonify({
        "ok": len(errors) == 0,
        "deleted": deleted,
        "errors": errors,
    })


@devops_bp.route("/devops/cache/bust", methods=["POST"])
def devops_cache_bust():
    """Bust server-side cache.

    Body: {"card": "security"}  — bust one card
    Body: {} or {"card": "all"} — bust all cards
    """
    data = request.get_json(silent=True) or {}
    card = data.get("card", "all")

    if card == "all":
        devops_cache.invalidate_all(_project_root())
        return jsonify({"ok": True, "busted": "all"})
    else:
        devops_cache.invalidate(_project_root(), card)
        return jsonify({"ok": True, "busted": card})


# ── Audit finding dismissals ────────────────────────────────────
# Dismiss = write ``# nosec: <reason>`` to the source line.
# The scanner respects # nosec and skips the line on next scan.


@devops_bp.route("/devops/audit/dismissals", methods=["POST"])
def audit_dismissals_add():
    """Dismiss finding(s) by writing # nosec to the source line(s).

    Body (batch):  {"items": [{"file": "...", "line": N}, ...], "comment": "reason"}
    Body (single): {"file": "path/to/file.py", "line": 42, "comment": "reason"}
    """
    from src.core.services.security_ops import dismiss_finding

    data = request.get_json(silent=True) or {}
    comment = data.get("comment", "")

    # Build list of items — batch or single
    items = data.get("items")
    if not items:
        file = data.get("file", "")
        line = data.get("line", 0)
        if not file or not line:
            return jsonify({"ok": False, "error": "file and line are required"}), 400
        items = [{"file": file, "line": line}]

    root = _project_root()
    results = []
    errors = []
    for item in items:
        r = dismiss_finding(root, item["file"], int(item["line"]), comment)
        results.append(r)
        if not r.get("ok"):
            errors.append(r)

    # Bust server cache once after all writes
    devops_cache.invalidate(root, "audit:l2:risks")
    devops_cache.invalidate(root, "security")

    # Log to audit activity so it shows in Debugging → Audit Log
    ok_items = [r for r in results if r.get("ok") and not r.get("already")]
    if ok_items:
        files_str = ", ".join(f"{r['file']}:{r['line']}" for r in ok_items)
        devops_cache.record_event(
            root,
            label="🚫 Finding Dismissed",
            summary=f"# nosec added to {len(ok_items)} line(s): {files_str}"
                    + (f" — {comment}" if comment else ""),
            detail={"items": ok_items, "comment": comment},
            card="dismissal",
        )

    return jsonify({"ok": len(errors) == 0, "count": len(results), "results": results})


@devops_bp.route("/devops/audit/dismissals", methods=["DELETE"])
def audit_dismissals_remove():
    """Undismiss a finding by removing # nosec from the source line.

    Body: {"file": "path/to/file.py", "line": 42}
    """
    from src.core.services.security_ops import undismiss_finding

    data = request.get_json(silent=True) or {}
    file = data.get("file", "")
    line = data.get("line", 0)

    if not file or not line:
        return jsonify({"ok": False, "error": "file and line are required"}), 400

    result = undismiss_finding(_project_root(), file, int(line))

    if not result.get("ok"):
        return jsonify(result), 400

    root = _project_root()
    devops_cache.invalidate(root, "audit:l2:risks")
    devops_cache.invalidate(root, "security")

    # Log the restore action
    if not result.get("already"):
        devops_cache.record_event(
            root,
            label="↩️ Finding Restored",
            summary=f"# nosec removed from {file}:{line}",
            detail={"file": file, "line": line},
            card="dismissal",
        )

    return jsonify(result)

