"""
DevOps wizard — setup actions (generate configs, apply settings).

Split from routes_devops.py for maintainability.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from flask import current_app, jsonify, request

from src.core.services import devops_cache
from src.ui.web.routes_devops import devops_bp


def _project_root() -> Path:
    return current_app.config["PROJECT_ROOT"]


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
            results: list[str] = []

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
                # Count patterns
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
                    # Extract short hash
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
            )

            return jsonify({
                "ok": True,
                "message": "Git repository configured",
                "files_created": files_created,
                "results": results,
            })

        # ── setup_github ────────────────────────────────────────
        if action == "setup_github":
            from src.core.services import secrets_ops

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
                summary=f"GitHub configured: {len(results.get('environments_created', []))} env(s), {results.get('secrets_pushed', 0)} secret(s)",
                detail=results,
                card="wizard",
            )

            return jsonify({
                "ok": True,
                "message": "GitHub configuration applied",
                "results": results,
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

            devops_cache.record_event(
                root,
                label="🐳 Docker Setup",
                summary=f"Docker configured ({', '.join(files_created)})",
                detail={"files_created": files_created},
                card="wizard",
            )

            return jsonify({
                "ok": True,
                "message": "Docker configuration generated",
                "files_created": files_created,
            })

        # ── setup_k8s ───────────────────────────────────────────
        if action == "setup_k8s":
            from src.core.services.k8s_ops import (
                wizard_state_to_resources,
                generate_k8s_wizard,
                _generate_skaffold,
            )

            # Translate wizard state → flat resource list
            resources = wizard_state_to_resources(data)

            # Generate manifests (returns {ok, files} or {error})
            result = generate_k8s_wizard(root, resources)
            if result.get("error"):
                return jsonify({"ok": False, "error": result["error"]}), 400

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
                # Respect overwrite flag — don't clobber existing user-edited files
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
                summary=f"K8s manifests generated ({len(files_created)} files" + (f", {len(skipped)} skipped" if skipped else "") + ")",
                detail={"files_created": files_created, "files_skipped": skipped},
                card="wizard",
            )

            return jsonify(resp)

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

            devops_cache.record_event(
                root,
                label="⚙️ CI Setup",
                summary=f"CI workflow generated ({', '.join(files_created)})",
                detail={"files_created": files_created, "branches": branches},
                card="wizard",
            )

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

            devops_cache.record_event(
                root,
                label="🏗️ Terraform Setup",
                summary=f"Terraform config generated (provider={provider}, backend={backend})",
                detail={"files_created": files_created, "provider": provider, "backend": backend},
                card="wizard",
            )

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

    devops_cache.record_event(
        root,
        label="🗑️ Wizard Config Deleted",
        summary=f"Wizard config deleted: {', '.join(deleted) or 'nothing'}" + (f" ({len(errors)} error(s))" if errors else ""),
        detail={"target": target, "deleted": deleted, "errors": errors},
        card="wizard",
    )

    return jsonify({
        "ok": len(errors) == 0,
        "deleted": deleted,
        "errors": errors,
    })
