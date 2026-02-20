"""
CI/CD workflow compose — orchestrates all CI generators into a coherent set.

Takes the full wizard state and produces the right set of workflow files
based on which domains (stacks, Docker, K8s, Terraform, DNS) are enabled.

Two strategies:
    "unified"  — single ci-cd.yml with all jobs (test → build → deploy)
    "split"    — separate files linked via workflow_run triggers
"""

from __future__ import annotations

from src.core.models.template import GeneratedFile

# Re-use existing job generators
from src.core.services.generators.github_workflow import (
    _resolve_job,
    _docker_ci_job,
    _kubectl_deploy_ci_job,
    _skaffold_deploy_ci_job,
    _helm_deploy_ci_job,
    _terraform_ci_job,
    _dns_verify_ci_step,
    _cdn_purge_ci_step,
    _kubeconfig_step,
    _CDN_PURGE_COMMANDS,
)


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _build_test_jobs(stack_names: list[str]) -> list[str]:
    """Build test job YAML blocks from detected stack names."""
    blocks: list[str] = []
    seen: set[int] = set()
    for name in stack_names:
        gen = _resolve_job(name)
        if gen and id(gen) not in seen:
            blocks.append(gen())
            seen.add(id(gen))
    return blocks


def _build_docker_job(
    docker_services: list[dict],
    needs: list[str],
) -> str:
    """Build Docker build/push job YAML."""
    if not docker_services:
        return ""

    # For multiple services, build individual jobs; for one, use "docker"
    blocks: list[str] = []
    for svc in docker_services:
        job = _docker_ci_job(
            image_name=svc.get("name", "app"),
            registry=svc.get("registry", ""),
            registry_type=svc.get("registry_type", ""),
            build_args=svc.get("build_args"),
            use_buildx=svc.get("use_buildx", True),
            use_cache=svc.get("use_cache", True),
            dockerfile=svc.get("dockerfile", "Dockerfile"),
            context=svc.get("context", "."),
        )
        # Inject needs
        job = job.replace("needs: [test]", f"needs: {needs}")
        if len(docker_services) > 1:
            svc_name = svc.get("name", "app")
            job = job.replace("  docker:", f"  docker-{svc_name}:", 1)
        blocks.append(job)

    return "\n".join(blocks)


def _build_deploy_job(
    deploy_config: dict,
    needs: list[str],
) -> str:
    """Build K8s deploy job YAML."""
    method = deploy_config.get("method", "kubectl")

    if method == "kubectl":
        job = _kubectl_deploy_ci_job(
            manifest_dir=deploy_config.get("manifest_dir", "k8s"),
            namespace=deploy_config.get("namespace", ""),
            app_name=deploy_config.get("app_name", "app"),
            needs=needs,
        )
    elif method == "skaffold":
        job = _skaffold_deploy_ci_job(
            profile=deploy_config.get("profile", ""),
            default_repo=deploy_config.get("default_repo", ""),
            skaffold_file=deploy_config.get("skaffold_file", ""),
            needs=needs,
        )
    elif method == "helm":
        job = _helm_deploy_ci_job(
            release_name=deploy_config.get("release_name", "app"),
            chart_path=deploy_config.get("chart_path", "charts/app"),
            namespace=deploy_config.get("namespace", ""),
            values_file=deploy_config.get("values_file", ""),
            needs=needs,
        )
    else:
        return ""

    return job


def _build_terraform_job(
    terraform_config: dict,
    needs: list[str],
) -> str:
    """Build Terraform CI job YAML."""
    job = _terraform_ci_job(
        provider=terraform_config.get("provider", "aws"),
        working_directory=terraform_config.get("working_directory", "terraform"),
        workspaces=terraform_config.get("workspaces"),
    )
    # Inject needs
    if needs:
        job = job.replace("needs: [test]", f"needs: {needs}")
    return job


def _build_post_deploy_steps(
    domains: list[str],
    cdn_provider: str,
) -> str:
    """Build post-deploy steps (DNS verify + CDN purge)."""
    steps: list[str] = []
    if domains:
        steps.append(_dns_verify_ci_step(domains))
    if cdn_provider:
        step = _cdn_purge_ci_step(cdn_provider)
        if step:
            steps.append(step)
    return "\n".join(steps)


def _build_env_deploy_jobs(
    deploy_config: dict,
    environments: list[str],
    needs: list[str],
) -> list[str]:
    """Build per-environment deploy jobs."""
    method = deploy_config.get("method", "kubectl")
    blocks: list[str] = []

    for env_name in environments:
        env_needs = needs[:]

        if method == "kubectl":
            job = _kubectl_deploy_ci_job(
                manifest_dir=deploy_config.get("manifest_dir", "k8s"),
                namespace=deploy_config.get("namespace", env_name),
                app_name=deploy_config.get("app_name", "app"),
                needs=env_needs,
            )
        elif method == "helm":
            job = _helm_deploy_ci_job(
                release_name=deploy_config.get("release_name", "app"),
                chart_path=deploy_config.get("chart_path", "charts/app"),
                namespace=deploy_config.get("namespace", env_name),
                values_file=f"charts/{deploy_config.get('release_name', 'app')}/values-{env_name}.yaml",
                needs=env_needs,
            )
        elif method == "skaffold":
            job = _skaffold_deploy_ci_job(
                profile=env_name,
                default_repo=deploy_config.get("default_repo", ""),
                skaffold_file=deploy_config.get("skaffold_file", ""),
                needs=env_needs,
            )
        else:
            continue

        # Make job name unique per environment
        job = job.replace("  deploy:", f"  deploy-{env_name}:", 1)
        job = job.replace("Deploy —", f"Deploy {env_name} —", 1)
        blocks.append(job)

    return blocks


# ═══════════════════════════════════════════════════════════════════
#  Unified strategy — single ci-cd.yml
# ═══════════════════════════════════════════════════════════════════


def _compose_unified(
    wizard_state: dict,
    project_name: str,
) -> list[GeneratedFile]:
    """Produce a single ci-cd.yml with all jobs."""
    stack_names = wizard_state.get("stack_names", [])
    docker_services = wizard_state.get("docker_services", [])
    deploy_config = wizard_state.get("deploy_config", {})
    terraform_config = wizard_state.get("terraform_config", {})
    domains = wizard_state.get("domains", [])
    cdn_provider = wizard_state.get("cdn_provider", "")
    environments = wizard_state.get("environments", [])

    job_blocks: list[str] = []
    # Track job names for dependency chaining
    last_jobs: list[str] = []

    # ── Test jobs ───────────────────────────────────────────────
    test_blocks = _build_test_jobs(stack_names)
    if test_blocks:
        job_blocks.extend(test_blocks)
        # Extract job names from blocks (first "  <name>:" line)
        for block in test_blocks:
            for line in block.splitlines():
                stripped = line.rstrip()
                if stripped.startswith("  ") and stripped.endswith(":") and not stripped.startswith("    "):
                    last_jobs.append(stripped.strip().rstrip(":"))
                    break

    # Default test job name if none found
    if not last_jobs and test_blocks:
        last_jobs = ["test"]

    # ── Terraform job (before build/deploy) ─────────────────────
    if terraform_config:
        tf_needs = last_jobs[:] if last_jobs else ["test"]
        tf_job = _build_terraform_job(terraform_config, tf_needs)
        if tf_job:
            job_blocks.append(tf_job)
            # Terraform runs in parallel with build, doesn't block

    # ── Docker build jobs ───────────────────────────────────────
    build_needs = last_jobs[:] if last_jobs else ["test"]
    if docker_services:
        docker_block = _build_docker_job(docker_services, build_needs)
        if docker_block:
            job_blocks.append(docker_block)
            if len(docker_services) > 1:
                last_jobs = [f"docker-{s.get('name', 'app')}" for s in docker_services]
            else:
                last_jobs = ["docker"]

    # ── Deploy jobs ─────────────────────────────────────────────
    if deploy_config:
        deploy_needs = last_jobs[:]

        if environments:
            env_blocks = _build_env_deploy_jobs(
                deploy_config, environments, deploy_needs,
            )
            job_blocks.extend(env_blocks)
        else:
            deploy_block = _build_deploy_job(deploy_config, deploy_needs)
            if deploy_block:
                job_blocks.append(deploy_block)

    # ── Post-deploy steps (append to last deploy job) ───────────
    if domains or cdn_provider:
        post_steps = _build_post_deploy_steps(domains, cdn_provider)
        if post_steps:
            # Add as a separate post-deploy job
            post_needs = []
            if environments:
                post_needs = [f"deploy-{e}" for e in environments]
            elif deploy_config:
                post_needs = ["deploy"]
            else:
                post_needs = last_jobs[:]

            post_job = f"""\
  post-deploy:
    name: Post-Deploy Checks
    runs-on: ubuntu-latest
    needs: {post_needs}
    if: github.event_name == 'push'

    steps:
      - uses: actions/checkout@v4

{post_steps}
"""
            job_blocks.append(post_job)

    if not job_blocks:
        return []

    # ── Assemble ────────────────────────────────────────────────
    wf_name = f"{project_name} CI/CD" if project_name else "CI/CD"
    header = f"""\
# Generated by DevOps Control Plane
name: {wf_name}

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read
  packages: write

jobs:
"""
    content = header + "\n".join(job_blocks)

    return [GeneratedFile(
        path=".github/workflows/ci-cd.yml",
        content=content,
        overwrite=False,
        reason=f"Unified CI/CD pipeline",
    )]


# ═══════════════════════════════════════════════════════════════════
#  Split strategy — separate files with workflow_run
# ═══════════════════════════════════════════════════════════════════


def _compose_split(
    wizard_state: dict,
    project_name: str,
) -> list[GeneratedFile]:
    """Produce separate workflow files linked via workflow_run."""
    stack_names = wizard_state.get("stack_names", [])
    docker_services = wizard_state.get("docker_services", [])
    deploy_config = wizard_state.get("deploy_config", {})
    terraform_config = wizard_state.get("terraform_config", {})
    domains = wizard_state.get("domains", [])
    cdn_provider = wizard_state.get("cdn_provider", "")
    environments = wizard_state.get("environments", [])

    files: list[GeneratedFile] = []
    # Track previous workflow names for workflow_run triggers
    ci_wf_name = f"{project_name} CI" if project_name else "CI"
    docker_wf_name = f"{project_name} Docker" if project_name else "Docker"
    deploy_wf_name = f"{project_name} Deploy" if project_name else "Deploy"

    # ── CI (test) workflow ──────────────────────────────────────
    test_blocks = _build_test_jobs(stack_names)
    if test_blocks:
        header = f"""\
# Generated by DevOps Control Plane
name: {ci_wf_name}

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
"""
        content = header + "\n".join(test_blocks)
        files.append(GeneratedFile(
            path=".github/workflows/ci.yml",
            content=content,
            overwrite=False,
            reason=f"CI test workflow for {len(stack_names)} stack(s)",
        ))

    # ── Docker (build) workflow ─────────────────────────────────
    if docker_services:
        trigger_on = ci_wf_name if test_blocks else None

        if trigger_on:
            on_block = f"""\
on:
  workflow_run:
    workflows: ["{trigger_on}"]
    types: [completed]
    branches: [main]
"""
        else:
            on_block = """\
on:
  push:
    branches: [main]
"""

        docker_block = _build_docker_job(docker_services, ["test"])
        # In split mode, no test job — remove needs
        docker_block = docker_block.replace("needs: ['test']", "needs: []")
        docker_block = docker_block.replace("needs: [\"test\"]", "needs: []")

        header = f"""\
# Generated by DevOps Control Plane
name: {docker_wf_name}

{on_block}
permissions:
  contents: read
  packages: write

jobs:
"""
        content = header + docker_block
        files.append(GeneratedFile(
            path=".github/workflows/docker.yml",
            content=content,
            overwrite=False,
            reason=f"Docker build workflow for {len(docker_services)} service(s)",
        ))

    # ── Terraform workflow (independent) ────────────────────────
    if terraform_config:
        tf_job = _build_terraform_job(terraform_config, [])
        # Reset needs for standalone
        tf_job = tf_job.replace("needs: []", "")
        tf_wf_name = f"{project_name} Terraform" if project_name else "Terraform"

        header = f"""\
# Generated by DevOps Control Plane
name: {tf_wf_name}

on:
  push:
    branches: [main]
    paths:
      - '{terraform_config.get("working_directory", "terraform")}/**'
  pull_request:
    branches: [main]
    paths:
      - '{terraform_config.get("working_directory", "terraform")}/**'

permissions:
  contents: read

jobs:
"""
        content = header + tf_job
        files.append(GeneratedFile(
            path=".github/workflows/terraform.yml",
            content=content,
            overwrite=False,
            reason=f"Terraform CI for {terraform_config.get('provider', 'aws')}",
        ))

    # ── Deploy workflow ─────────────────────────────────────────
    if deploy_config:
        trigger_from = docker_wf_name if docker_services else ci_wf_name if test_blocks else None

        if trigger_from:
            on_block = f"""\
on:
  workflow_run:
    workflows: ["{trigger_from}"]
    types: [completed]
    branches: [main]
"""
        else:
            on_block = """\
on:
  push:
    branches: [main]
"""

        deploy_blocks: list[str] = []
        if environments:
            env_blocks = _build_env_deploy_jobs(deploy_config, environments, [])
            # Remove needs for standalone
            for block in env_blocks:
                block = block.replace("needs: []", "")
                deploy_blocks.append(block)
        else:
            deploy_block = _build_deploy_job(deploy_config, [])
            deploy_block = deploy_block.replace("needs: []", "")
            deploy_blocks.append(deploy_block)

        header = f"""\
# Generated by DevOps Control Plane
name: {deploy_wf_name}

{on_block}
permissions:
  contents: read

jobs:
"""
        content = header + "\n".join(deploy_blocks)
        files.append(GeneratedFile(
            path=".github/workflows/deploy.yml",
            content=content,
            overwrite=False,
            reason=f"K8s deploy via {deploy_config.get('method', 'kubectl')}",
        ))

    # ── Post-deploy workflow ────────────────────────────────────
    if domains or cdn_provider:
        from src.core.services.generators.github_workflow import (
            generate_deploy_post_steps,
        )
        post_file = generate_deploy_post_steps(
            {"domains": domains, "cdn_provider": cdn_provider},
            project_name=project_name,
        )
        if post_file:
            files.append(post_file)

    return files


# ═══════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════


def compose_ci_workflows(
    wizard_state: dict,
    *,
    strategy: str = "unified",
    project_name: str = "",
) -> list[GeneratedFile]:
    """Compose CI/CD workflow files from wizard state.

    Cross-domain orchestrator: takes the full wizard state and produces
    the right set of GitHub Actions workflow files with correct job
    dependencies, image tag passing, and PR/push branching.

    Args:
        wizard_state: Dict with any of:
            stack_names: list[str]        — detected language stacks → test jobs
            docker_services: list[dict]   — Docker services → build jobs
            deploy_config: dict           — K8s deploy config → deploy jobs
            terraform_config: dict        — Terraform config → infra jobs
            domains: list[str]            — domains → DNS verify post-deploy
            cdn_provider: str             — CDN provider → cache purge post-deploy
            environments: list[str]       — environments → per-env deploy jobs
        strategy: "unified" (single file) or "split" (separate files).
        project_name: For workflow naming.

    Returns:
        List of GeneratedFile. Empty if nothing to generate.
    """
    if strategy == "split":
        return _compose_split(wizard_state, project_name)
    return _compose_unified(wizard_state, project_name)
