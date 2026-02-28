"""
Wizard setup — CI/CD workflow generation.

Composes GitHub Actions workflow YAML from wizard state:
test jobs (stack-aware), Docker build/push, K8s deployment
(kubectl / skaffold / helm), multi-environment pipelines.

Channel-independent: no Flask or HTTP dependency.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  CI helpers
# ═══════════════════════════════════════════════════════════════════


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


def _append_coverage_step(steps: list[dict], tool: str = "codecov") -> None:
    """Append a coverage upload step to a test job's step list."""
    if tool == "coveralls":
        steps.append({
            "name": "Upload coverage to Coveralls",
            "uses": "coverallsapp/github-action@v2",
            "with": {"github-token": "${{ secrets.GITHUB_TOKEN }}"},
        })
    else:
        # Default: Codecov
        steps.append({
            "name": "Upload coverage to Codecov",
            "uses": "codecov/codecov-action@v4",
            "with": {"token": "${{ secrets.CODECOV_TOKEN }}"},
        })


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


# ═══════════════════════════════════════════════════════════════════
#  Main CI setup
# ═══════════════════════════════════════════════════════════════════


def setup_ci(root: Path, data: dict) -> dict:
    """Generate CI workflow YAML from wizard state.

    Composes test, Docker build/push, and K8s deploy jobs based on
    the ``data`` dict.  Uses ``yaml.dump()`` for reliable output.

    Supported data keys:
        branches       – comma-separated trigger branches (default "main, master")
        trigger_type   – "push-pr" | "push" | "pr" | "manual" | "schedule"
        cron_schedule  – cron expression when trigger_type is "schedule"
        python_version – Python version for test job (default "3.12")
        install_cmd    – pip install command (default 'pip install -e ".[dev]"')
        test_cmd       – test command (default "python -m pytest tests/ -v --tb=short")
        lint           – bool, add lint step
        lint_cmd       – lint command (default "ruff check src/")
        typecheck      – bool, add type-check step
        typecheck_cmd  – type-check command (default "mypy src/ --ignore-missing-imports")
        coverage       – bool, add coverage upload step
        coverage_tool  – "codecov" | "coveralls" (default "codecov")
        overwrite      – bool, replace existing ci.yml

        concurrency_group   – concurrency group name (default "ci-${{ github.ref }}")
        cancel_in_progress  – bool, cancel in-progress runs (default True)

        env_vars            – dict of global env vars for all jobs

        docker              – bool, add Docker build job
        docker_registry     – registry URL (e.g. "ghcr.io/myorg")
        docker_image        – image name (e.g. "myapp")
        docker_build_args   – dict of build-arg key→value
        docker_push         – bool, push to registry

        k8s                 – bool, add K8s deploy job
        k8s_deploy_method   – "kubectl" | "skaffold" | "helm"
        k8s_manifest_dir    – manifest directory for kubectl
        k8s_namespace       – namespace flag
        helm_chart          – Helm chart path
        helm_release        – Helm release name
        skaffold_file       – custom skaffold file path

        environments        – list of env dicts for multi-env deploys
            Each: {name, namespace, branch, kubeconfig_secret,
                   skaffold_profile, values_file,
                   env_vars: dict, secrets: list[str],
                   require_approval: bool}
    """
    import yaml as _yaml

    from src.core.services import devops_cache

    # ── Parse inputs ────────────────────────────────────────────────
    branches_str = data.get("branches", "main, master")
    branches = [b.strip() for b in branches_str.split(",") if b.strip()]
    trigger_type = data.get("trigger_type", "push-pr")
    cron_schedule = data.get("cron_schedule", "")
    py_ver = data.get("python_version", "3.12")
    install_cmd = data.get("install_cmd", 'pip install -e ".[dev]"')
    test_cmd = data.get("test_cmd", "")
    lint = data.get("lint", False)
    lint_cmd = data.get("lint_cmd", "ruff check src/")
    typecheck = data.get("typecheck", False)
    typecheck_cmd = data.get("typecheck_cmd", "mypy src/ --ignore-missing-imports")
    coverage = data.get("coverage", False)
    coverage_tool = data.get("coverage_tool", "codecov")
    overwrite = data.get("overwrite", False)

    concurrency_group = data.get("concurrency_group", "ci-${{ github.ref }}")
    cancel_in_progress = data.get("cancel_in_progress", True)

    global_env_vars: dict = data.get("env_vars", {})

    stacks: list[str] = data.get("stacks", [])

    docker_enabled = data.get("docker", False)
    docker_registry = data.get("docker_registry", "")
    docker_image = data.get("docker_image", "app")
    docker_build_args = data.get("docker_build_args", {})
    docker_push = data.get("docker_push", bool(docker_registry))  # noqa: F841

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

    # ── Build trigger (on:) from trigger_type ───────────────────────
    trigger: dict = {}
    if trigger_type == "push":
        trigger["push"] = {"branches": branches}
    elif trigger_type == "pr":
        trigger["pull_request"] = {"branches": branches}
    elif trigger_type == "manual":
        trigger["workflow_dispatch"] = {}
    elif trigger_type == "schedule":
        trigger["schedule"] = [{"cron": cron_schedule or "0 6 * * 1"}]
        trigger["workflow_dispatch"] = {}  # always allow manual trigger too
    else:  # "push-pr" (default)
        trigger["push"] = {"branches": branches}
        trigger["pull_request"] = {"branches": branches}

    # ── Build workflow dict ─────────────────────────────────────────
    workflow: dict = {
        "name": "CI",
        "on": trigger,
        "permissions": {"contents": "read"},
        "concurrency": {
            "group": concurrency_group,
            "cancel-in-progress": cancel_in_progress,
        },
        "jobs": {},
    }

    # Global env vars
    if global_env_vars:
        workflow["env"] = global_env_vars

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
            {"uses": "actions/setup-python@v5", "with": {"python-version": py_ver, "cache": "pip"}},
            {"name": "Install dependencies", "run": install_cmd},
        ]
        if lint:
            test_steps.append({"name": "Lint", "run": lint_cmd})
        if typecheck:
            test_steps.append({"name": "Type check", "run": typecheck_cmd})
        test_steps.append({"name": "Run tests", "run": test_cmd})
        if coverage:
            _append_coverage_step(test_steps, coverage_tool)

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
            {"uses": "actions/setup-python@v5", "with": {"python-version": py_ver, "cache": "pip"}},
            {"name": "Install dependencies", "run": install_cmd},
        ]
        if lint:
            test_steps.append({"name": "Lint", "run": lint_cmd})
        if typecheck:
            test_steps.append({"name": "Type check", "run": typecheck_cmd})
        test_steps.append({"name": "Run tests", "run": default_test_cmd})
        if coverage:
            _append_coverage_step(test_steps, coverage_tool)

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

        docker_job: dict = {
            "runs-on": "ubuntu-latest",
            "needs": ["test"] if has_test_job else [],
            "steps": docker_steps,
        }
        # Only gate on push if push is a configured trigger
        if trigger_type in ("push", "push-pr"):
            docker_job["if"] = "github.event_name == 'push'"
        workflow["jobs"]["docker"] = docker_job

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

                # GitHub Environment protection (enables approval gates)
                if env.get("require_approval"):
                    job_def["environment"] = env_name

                # Per-environment env vars and secrets
                job_env: dict = {}
                for k, v in (env.get("env_vars") or {}).items():
                    job_env[k] = v
                for secret_name in (env.get("secrets") or []):
                    job_env[secret_name] = f"${{{{ secrets.{secret_name} }}}}"
                if job_env:
                    job_def["env"] = job_env

                # Branch constraint
                if branch:
                    job_def["if"] = (
                        f"github.event_name == 'push' && "
                        f"github.ref == 'refs/heads/{branch}'"
                    )
                elif trigger_type in ("push", "push-pr"):
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
            deploy_job: dict = {
                "runs-on": "ubuntu-latest",
                "needs": [prev_job] if prev_job else [],
                "steps": deploy_steps,
            }
            if trigger_type in ("push", "push-pr"):
                deploy_job["if"] = "github.event_name == 'push'"
            workflow["jobs"]["deploy"] = deploy_job

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
