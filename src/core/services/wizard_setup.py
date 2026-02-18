"""
Wizard setup actions — generate configs, apply settings, delete configs.

Channel-independent: no Flask, no HTTP dependency.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


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
    """Generate Dockerfile and optional docker-compose.yml / .dockerignore.

    Supported data keys:
        base_image, workdir, install_cmd, port, cmd, overwrite, compose,
        dockerignore, registry, image_name, build_args.
    """
    from src.core.services import devops_cache

    base_image = data.get("base_image", "python:3.12-slim")
    workdir = data.get("workdir", "/app")
    install_cmd = data.get("install_cmd", "pip install -e .")
    port = data.get("port", "8080")
    cmd = data.get("cmd", "python -m src")
    overwrite = data.get("overwrite", False)
    compose = data.get("compose", False)
    dockerignore = data.get("dockerignore", False)
    registry = data.get("registry", None)
    image_name = data.get("image_name", None)
    build_args = data.get("build_args", None)

    files_created: list[str] = []

    cmd_parts = cmd.split()
    cmd_json = ", ".join(f'"{p}"' for p in cmd_parts)

    dest = root / "Dockerfile"
    if dest.exists() and not overwrite:
        return {
            "ok": False,
            "error": "Dockerfile already exists. Check 'Overwrite' to replace.",
        }

    # Build ARG directives if build_args provided
    arg_lines = ""
    if isinstance(build_args, dict) and build_args:
        arg_lines = "\n".join(f"ARG {k}" for k in build_args) + "\n\n"

    dest.write_text(
        f"FROM {base_image}\n\n"
        f"{arg_lines}"
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

    if dockerignore:
        ignore_dest = root / ".dockerignore"
        if not ignore_dest.exists() or overwrite:
            ignore_dest.write_text(
                "# Generated by DevOps Control Plane\n"
                ".git\n"
                ".gitignore\n"
                "__pycache__\n"
                "*.pyc\n"
                ".venv\n"
                "venv\n"
                "node_modules\n"
                ".env\n"
                ".env.*\n"
                "*.log\n"
                "Dockerfile\n"
                "docker-compose*.yml\n"
                ".dockerignore\n"
            )
            files_created.append(".dockerignore")

    devops_cache.record_event(
        root,
        label="🐳 Docker Setup",
        summary=f"Docker configured ({', '.join(files_created)})",
        detail={"files_created": files_created},
        card="wizard",
        action="configured",
        target="docker",
    )

    result: dict = {
        "ok": True,
        "message": "Docker configuration generated",
        "files_created": files_created,
    }

    # Echo back optional config for downstream use
    if registry:
        result["registry"] = registry
    if image_name:
        result["image_name"] = image_name
    if build_args:
        result["build_args"] = build_args

    return result


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


def _build_test_jobs_from_stacks(
    stacks: list[str],
    resolve_job: callable,
) -> dict[str, dict]:
    """Bridge stack generators (YAML strings) → workflow job dicts.

    Calls the per-stack job generators from
    ``generators/github_workflow.py``, parses the YAML fragment they
    return, and merges the resulting job dicts.
    """
    import yaml as _yaml

    jobs: dict[str, dict] = {}
    seen: set[int] = set()

    for stack_name in stacks:
        gen = resolve_job(stack_name)
        if gen is None or id(gen) in seen:
            continue
        seen.add(id(gen))
        fragment = gen()  # returns a YAML string fragment like "  python:\n ..."
        try:
            parsed = _yaml.safe_load(fragment)
        except Exception:
            continue
        if isinstance(parsed, dict):
            jobs.update(parsed)

    return jobs


def setup_ci(root: Path, data: dict) -> dict:
    """Generate CI workflow YAML from wizard state.

    Composes test, Docker build/push, and K8s deploy jobs based on
    the ``data`` dict.  Uses ``yaml.dump()`` for reliable output.

    Supported data keys:
        branches       – comma-separated trigger branches (default "main, master")
        python_version – Python version for test job (default "3.12")
        install_cmd    – pip install command (default 'pip install -e ".[dev]"')
        test_cmd       – test command (default "python -m pytest tests/ -v --tb=short")
        lint           – bool, add lint step
        lint_cmd       – lint command (default "ruff check src/")
        overwrite      – bool, replace existing ci.yml

        docker              – bool, add Docker build job
        docker_registry     – registry URL (e.g. "ghcr.io/myorg")
        docker_image        – image name (e.g. "myapp")
        docker_build_args   – dict of build-arg key→value

        k8s                 – bool, add K8s deploy job
        k8s_deploy_method   – "kubectl" | "skaffold" | "helm"
        k8s_manifest_dir    – manifest directory for kubectl
        k8s_namespace       – namespace flag
        helm_chart          – Helm chart path
        helm_release        – Helm release name
        skaffold_file       – custom skaffold file path

        environments        – list of env dicts for multi-env deploys
            Each: {name, namespace, branch, kubeconfig_secret,
                   skaffold_profile, values_file}
    """
    import yaml as _yaml

    from src.core.services import devops_cache

    # ── Parse inputs ────────────────────────────────────────────────
    branches_str = data.get("branches", "main, master")
    branches = [b.strip() for b in branches_str.split(",") if b.strip()]
    py_ver = data.get("python_version", "3.12")
    install_cmd = data.get("install_cmd", 'pip install -e ".[dev]"')
    test_cmd = data.get("test_cmd", "")
    lint = data.get("lint", False)
    lint_cmd = data.get("lint_cmd", "ruff check src/")
    overwrite = data.get("overwrite", False)

    stacks: list[str] = data.get("stacks", [])

    docker_enabled = data.get("docker", False)
    docker_registry = data.get("docker_registry", "")
    docker_image = data.get("docker_image", "app")
    docker_build_args = data.get("docker_build_args", {})

    k8s_enabled = data.get("k8s", False)
    k8s_method = data.get("k8s_deploy_method", "kubectl")
    k8s_manifest_dir = data.get("k8s_manifest_dir", "k8s/")
    k8s_namespace = data.get("k8s_namespace", "")
    helm_chart = data.get("helm_chart", "")
    helm_release = data.get("helm_release", "")
    skaffold_file = data.get("skaffold_file", "")

    environments: list[dict] = data.get("environments", [])

    # ── Validate: mutually exclusive deploy methods ─────────────────
    if k8s_enabled and k8s_method not in ("kubectl", "skaffold", "helm"):
        return {
            "ok": False,
            "error": f"Invalid k8s_deploy_method: {k8s_method!r}. "
                     f"Must be 'kubectl', 'skaffold', or 'helm'.",
        }

    # ── Guard: file exists ──────────────────────────────────────────
    wf_dir = root / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    dest = wf_dir / "ci.yml"

    if dest.exists() and not overwrite:
        return {
            "ok": False,
            "error": "CI workflow already exists. Check 'Overwrite' to replace.",
        }

    # ── Build workflow dict ─────────────────────────────────────────
    workflow: dict = {
        "name": "CI",
        "on": {
            "push": {"branches": branches},
            "pull_request": {"branches": branches},
        },
        "permissions": {"contents": "read"},
        "jobs": {},
    }

    # ── 1. Test job ─────────────────────────────────────────────────
    #  Priority: stacks → explicit test_cmd → default Python fallback.
    #  When only Docker/K8s is enabled (no stacks, no test_cmd), skip
    #  the test job entirely.
    has_test_job = False

    if stacks:
        # Delegate to generators/github_workflow.py
        from src.core.services.generators.github_workflow import _resolve_job

        test_jobs = _build_test_jobs_from_stacks(stacks, _resolve_job)
        if test_jobs:
            workflow["jobs"].update(test_jobs)
            has_test_job = True
    elif test_cmd:
        # Explicit test command (legacy / wizard mode)
        test_steps: list[dict] = [
            {"uses": "actions/checkout@v4"},
            {"uses": "actions/setup-python@v5", "with": {"python-version": py_ver}},
            {"name": "Install dependencies", "run": install_cmd},
            {"name": "Run tests", "run": test_cmd},
        ]
        if lint:
            test_steps.append({"name": "Lint", "run": lint_cmd})

        workflow["jobs"]["test"] = {
            "runs-on": "ubuntu-latest",
            "steps": test_steps,
        }
        has_test_job = True
    elif not (docker_enabled or k8s_enabled):
        # No stacks, no test_cmd, no Docker, no K8s → default Python fallback
        default_test_cmd = "python -m pytest tests/ -v --tb=short"
        test_steps = [
            {"uses": "actions/checkout@v4"},
            {"uses": "actions/setup-python@v5", "with": {"python-version": py_ver}},
            {"name": "Install dependencies", "run": install_cmd},
            {"name": "Run tests", "run": default_test_cmd},
        ]
        if lint:
            test_steps.append({"name": "Lint", "run": lint_cmd})

        workflow["jobs"]["test"] = {
            "runs-on": "ubuntu-latest",
            "steps": test_steps,
        }
        has_test_job = True
    # else: Docker/K8s only — no test job

    # ── 2. Docker build/push job ────────────────────────────────────
    if docker_enabled:
        # Permissions for GHCR push
        if docker_registry and "ghcr.io" in docker_registry:
            workflow["permissions"]["packages"] = "write"

        docker_steps: list[dict] = [
            {"uses": "actions/checkout@v4"},
            {"name": "Set up Docker Buildx",
             "uses": "docker/setup-buildx-action@v3"},
        ]

        # Registry login
        if docker_registry:
            if "ghcr.io" in docker_registry:
                docker_steps.append({
                    "name": "Login to GHCR",
                    "uses": "docker/login-action@v3",
                    "with": {
                        "registry": "ghcr.io",
                        "username": "${{ github.actor }}",
                        "password": "${{ secrets.GITHUB_TOKEN }}",
                    },
                })
            elif "docker.io" in docker_registry:
                docker_steps.append({
                    "name": "Login to DockerHub",
                    "uses": "docker/login-action@v3",
                    "with": {
                        "username": "${{ secrets.DOCKERHUB_USERNAME }}",
                        "password": "${{ secrets.DOCKERHUB_TOKEN }}",
                    },
                })
            else:
                docker_steps.append({
                    "name": f"Login to {docker_registry}",
                    "uses": "docker/login-action@v3",
                    "with": {
                        "registry": docker_registry.split("/")[0],
                        "username": "${{ secrets.REGISTRY_USERNAME }}",
                        "password": "${{ secrets.REGISTRY_PASSWORD }}",
                    },
                })

        # Image tag
        full_image = (
            f"{docker_registry}/{docker_image}"
            if docker_registry else docker_image
        )
        tags = f"{full_image}:${{{{ github.sha }}}},{full_image}:latest"

        # Build args
        build_args_str = ""
        if isinstance(docker_build_args, dict) and docker_build_args:
            build_args_str = "\n".join(
                f"{k}={v}" for k, v in docker_build_args.items()
            )

        build_push_with: dict = {
            "context": ".",
            "push": bool(docker_registry),
            "tags": tags,
            "cache-from": "type=gha",
            "cache-to": "type=gha,mode=max",
        }
        if build_args_str:
            build_push_with["build-args"] = build_args_str

        docker_steps.append({
            "name": "Build and push Docker image",
            "uses": "docker/build-push-action@v5",
            "with": build_push_with,
        })

        workflow["jobs"]["docker"] = {
            "runs-on": "ubuntu-latest",
            "needs": ["test"] if has_test_job else [],
            "if": "github.event_name == 'push'",
            "steps": docker_steps,
        }

    # ── 3. K8s deploy job(s) ────────────────────────────────────────
    if k8s_enabled:
        prev_job = (
            "docker" if docker_enabled
            else "test" if has_test_job
            else None
        )

        if environments:
            # Multi-environment: one deploy job per environment
            for i, env in enumerate(environments):
                env_name = env.get("name", f"env{i}")
                job_id = f"deploy-{env_name}"
                ns = env.get("namespace", k8s_namespace) or ""
                branch = env.get("branch", "")
                kube_secret = env.get("kubeconfig_secret", "KUBECONFIG")

                # Chain environments: each depends on previous
                if i == 0:
                    needs = [prev_job] if prev_job else []
                else:
                    prev_env = environments[i - 1].get("name", f"env{i-1}")
                    needs = [f"deploy-{prev_env}"]

                deploy_steps = _build_deploy_steps(
                    method=k8s_method,
                    kubeconfig_secret=kube_secret,
                    namespace=ns,
                    manifest_dir=k8s_manifest_dir,
                    helm_chart=helm_chart,
                    helm_release=helm_release,
                    skaffold_file=skaffold_file,
                    docker_registry=docker_registry,
                    docker_image=docker_image,
                    docker_enabled=docker_enabled,
                    env=env,
                )

                job_def: dict = {
                    "runs-on": "ubuntu-latest",
                    "needs": needs,
                    "steps": deploy_steps,
                }

                # Branch constraint
                if branch:
                    job_def["if"] = (
                        f"github.event_name == 'push' && "
                        f"github.ref == 'refs/heads/{branch}'"
                    )
                else:
                    job_def["if"] = "github.event_name == 'push'"

                workflow["jobs"][job_id] = job_def
        else:
            # Single deploy job
            deploy_steps = _build_deploy_steps(
                method=k8s_method,
                kubeconfig_secret="KUBECONFIG",
                namespace=k8s_namespace,
                manifest_dir=k8s_manifest_dir,
                helm_chart=helm_chart,
                helm_release=helm_release,
                skaffold_file=skaffold_file,
                docker_registry=docker_registry,
                docker_image=docker_image,
                docker_enabled=docker_enabled,
            )
            workflow["jobs"]["deploy"] = {
                "runs-on": "ubuntu-latest",
                "needs": [prev_job] if prev_job else [],
                "if": "github.event_name == 'push'",
                "steps": deploy_steps,
            }

    # ── Write YAML ──────────────────────────────────────────────────
    content = _yaml.dump(
        workflow,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    dest.write_text(content, encoding="utf-8")

    files_created = [".github/workflows/ci.yml"]

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


def _build_deploy_steps(
    *,
    method: str,
    kubeconfig_secret: str,
    namespace: str,
    manifest_dir: str,
    helm_chart: str,
    helm_release: str,
    skaffold_file: str,
    docker_registry: str,
    docker_image: str,
    docker_enabled: bool,
    env: dict | None = None,
) -> list[dict]:
    """Build deploy steps for a single environment."""
    steps: list[dict] = [
        {"uses": "actions/checkout@v4"},
        {
            "name": "Set up kubeconfig",
            "run": (
                "mkdir -p $HOME/.kube && "
                f"echo \"${{{{ secrets.{kubeconfig_secret} }}}}\" "
                "> $HOME/.kube/config"
            ),
        },
    ]

    if method == "kubectl":
        # Dry-run validation
        ns_flag = f" -n {namespace}" if namespace else ""
        steps.append({
            "name": "Validate manifests",
            "run": (
                f"kubectl apply -f {manifest_dir} --dry-run=client"
                f"{ns_flag}"
            ),
        })
        # Apply
        steps.append({
            "name": "Deploy with kubectl",
            "run": f"kubectl apply -f {manifest_dir}{ns_flag}",
        })
        # Rollout wait
        steps.append({
            "name": "Wait for rollout",
            "run": f"kubectl rollout status deployment --timeout=300s{ns_flag}",
        })

    elif method == "skaffold":
        # Install skaffold
        steps.append({
            "name": "Install Skaffold",
            "run": (
                "curl -Lo skaffold https://storage.googleapis.com/skaffold"
                "/releases/v2.13.2/skaffold-linux-amd64 && "
                "chmod +x skaffold && sudo mv skaffold /usr/local/bin/"
            ),
        })
        # Build skaffold command
        cmd = "skaffold run"
        if skaffold_file:
            cmd += f" -f {skaffold_file}"
        if env and env.get("skaffold_profile"):
            cmd += f" -p {env['skaffold_profile']}"
        if docker_registry:
            cmd += f" --default-repo={docker_registry}"
        steps.append({
            "name": "Deploy with Skaffold",
            "run": cmd,
        })

    elif method == "helm":
        # Build helm command
        release = helm_release or "app"
        chart = helm_chart or "./charts/app"
        cmd = f"helm upgrade --install {release} {chart}"
        if namespace:
            cmd += f" --namespace {namespace}"
        if env and env.get("values_file"):
            cmd += f" -f {env['values_file']}"
        if docker_enabled:
            tag = "${{ github.sha }}"
            full_image = (
                f"{docker_registry}/{docker_image}"
                if docker_registry else docker_image
            )
            cmd += f" --set image.repository={full_image}"
            cmd += f" --set image.tag={tag}"
        steps.append({
            "name": "Deploy with Helm",
            "run": cmd,
        })

    return steps


def setup_terraform(root: Path, data: dict) -> dict:
    """Generate Terraform scaffolding via generate_terraform().

    Delegates to the generator to produce main.tf, variables.tf,
    outputs.tf, and .gitignore — then writes them to disk.
    """
    from src.core.services import devops_cache
    from src.core.services.terraform_generate import generate_terraform

    provider = data.get("provider", "aws")
    backend = data.get("backend", "local")
    project_name = data.get("project_name", root.name)
    overwrite = data.get("overwrite", False)

    tf_dir = root / "terraform"
    tf_main = tf_dir / "main.tf"

    if tf_main.exists() and not overwrite:
        return {
            "ok": False,
            "error": "Terraform config exists. Check 'Overwrite' to replace.",
        }

    # Delegate to the generator
    gen_result = generate_terraform(
        root,
        provider,
        backend=backend,
        project_name=project_name,
    )
    if "error" in gen_result:
        return {"ok": False, "error": gen_result["error"]}

    # Write generated files to disk
    files_created: list[str] = []
    for f in gen_result["files"]:
        path = root / f["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f["content"])
        files_created.append(f["path"])

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
                for ci_file in ["ci.yml", "lint.yml"]:
                    ci = root / ".github" / "workflows" / ci_file
                    if ci.is_file():
                        ci.unlink()
                        deleted.append(f".github/workflows/{ci_file}")
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
