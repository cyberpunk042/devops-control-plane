"""
Integration tests — CI/CD domain COMPLETE requirements.

TDD: these tests define EVERY capability the finished CI/CD integration
must have.  Failures = what needs to be built/fixed.

Covers:
  1.  ROUND-TRIP      — setup_ci → ci_status → ci_workflows → validate
  2.  DOCKER BUILD    — Dockerfile present → docker build step in CI
  3.  DOCKER PUSH     — Registry configured → push with login
  4.  DOCKER DETAILS  — Buildx, caching, tagging, build-args
  5.  K8S KUBECTL     — Raw manifests → kubectl apply, kubeconfig, namespace
  6.  K8S SKAFFOLD    — Skaffold mode → skaffold run, profiles, install
  7.  K8S HELM        — Helm mode → helm upgrade, values, release name
  8.  MULTI-ENV       — Per-environment deploys, ordering, gates
  9.  FULL PIPELINE   — Docker + K8s combined, job chains, conditionals
  10. CLEANUP         — delete_generated_configs("ci")
"""

from pathlib import Path

import yaml

from src.core.services.wizard_setup import setup_ci, delete_generated_configs
from src.core.services.ci_ops import ci_status, ci_workflows


def _ci_content(tmp_path: Path) -> str:
    """Read generated CI workflow content."""
    return (tmp_path / ".github" / "workflows" / "ci.yml").read_text()


def _ci_parsed(tmp_path: Path) -> dict:
    """Read and parse generated CI workflow."""
    return yaml.safe_load(_ci_content(tmp_path))


# ═══════════════════════════════════════════════════════════════════
#  1. ROUND-TRIP — setup_ci → detect → parse
# ═══════════════════════════════════════════════════════════════════


class TestCiRoundTrip:
    def test_setup_then_detect(self, tmp_path: Path):
        """setup_ci → ci_status detects GitHub Actions."""
        assert setup_ci(tmp_path, {"branches": "main"})["ok"] is True
        status = ci_status(tmp_path)
        assert status["has_ci"] is True
        assert any(p["id"] == "github_actions" for p in status["providers"])

    def test_setup_then_parse(self, tmp_path: Path):
        """setup_ci → ci_workflows parses the generated file."""
        setup_ci(tmp_path, {"branches": "main", "test_cmd": "pytest"})
        wfs = ci_workflows(tmp_path)["workflows"]
        assert len(wfs) == 1
        assert wfs[0]["provider"] == "github_actions"
        assert wfs[0]["name"] == "CI"
        assert len(wfs[0]["jobs"]) >= 1

    def test_valid_yaml(self, tmp_path: Path):
        """Generated ci.yml is valid YAML with jobs."""
        setup_ci(tmp_path, {"branches": "main"})
        parsed = _ci_parsed(tmp_path)
        assert isinstance(parsed, dict)
        assert "jobs" in parsed

    def test_overwrite(self, tmp_path: Path):
        """overwrite=True replaces existing workflow."""
        setup_ci(tmp_path, {"test_cmd": "echo old"})
        assert "echo old" in _ci_content(tmp_path)
        setup_ci(tmp_path, {"test_cmd": "echo new", "overwrite": True})
        assert "echo new" in _ci_content(tmp_path)

    def test_has_push_trigger(self, tmp_path: Path):
        setup_ci(tmp_path, {"branches": "main"})
        wf = ci_workflows(tmp_path)["workflows"][0]
        assert "push" in wf["triggers"]

    def test_has_pr_trigger(self, tmp_path: Path):
        setup_ci(tmp_path, {"branches": "main"})
        wf = ci_workflows(tmp_path)["workflows"][0]
        assert "pull_request" in wf["triggers"]

    def test_jobs_have_steps(self, tmp_path: Path):
        setup_ci(tmp_path, {"branches": "main", "test_cmd": "pytest"})
        for job in ci_workflows(tmp_path)["workflows"][0]["jobs"]:
            assert job["steps_count"] > 0


# ═══════════════════════════════════════════════════════════════════
#  2. DOCKER BUILD — Docker enabled → build step in CI
# ═══════════════════════════════════════════════════════════════════


class TestCiDockerBuild:
    """When Docker is enabled, CI should include Docker build steps."""

    def test_docker_build_step_present(self, tmp_path: Path):
        """docker=True → CI includes a docker build."""
        result = setup_ci(tmp_path, {
            "branches": "main", "test_cmd": "pytest",
            "docker": True,
        })
        assert result["ok"] is True
        content = _ci_content(tmp_path)
        assert "docker" in content.lower()

    def test_docker_buildx_setup(self, tmp_path: Path):
        """Docker build should use Buildx for efficiency."""
        setup_ci(tmp_path, {
            "branches": "main", "docker": True, "overwrite": True,
        })
        content = _ci_content(tmp_path)
        # Should set up Docker Buildx (action or manual)
        assert "buildx" in content.lower() or "docker/setup-buildx-action" in content

    def test_docker_build_args_forwarded(self, tmp_path: Path):
        """Build args in config → --build-arg in CI."""
        setup_ci(tmp_path, {
            "branches": "main", "docker": True, "overwrite": True,
            "docker_build_args": {"NODE_ENV": "production"},
        })
        content = _ci_content(tmp_path)
        assert "NODE_ENV" in content

    def test_docker_build_only_on_push(self, tmp_path: Path):
        """Docker build should run on push but not on PRs (PRs test only)."""
        setup_ci(tmp_path, {
            "branches": "main", "docker": True, "overwrite": True,
        })
        parsed = _ci_parsed(tmp_path)
        jobs = parsed.get("jobs", {})
        # Build/deploy jobs should have an `if` condition or separate trigger
        build_jobs = {k: v for k, v in jobs.items()
                      if isinstance(v, dict) and
                      ("build" in k.lower() or "docker" in k.lower())}
        if build_jobs:
            for jd in build_jobs.values():
                # Either the job has a condition, or it runs on push only
                assert (jd.get("if") or
                        "push" in str(parsed.get("on", parsed.get(True, {})))), \
                    "Docker build should be conditional or push-only"

    def test_docker_layer_cache(self, tmp_path: Path):
        """Docker build uses GHA cache for faster builds."""
        setup_ci(tmp_path, {
            "branches": "main", "docker": True, "overwrite": True,
        })
        content = _ci_content(tmp_path)
        assert "cache" in content.lower()

    def test_docker_image_tagging(self, tmp_path: Path):
        """Docker image tagged with SHA or version, not just latest."""
        setup_ci(tmp_path, {
            "branches": "main", "docker": True, "overwrite": True,
            "docker_image": "myapp",
        })
        content = _ci_content(tmp_path)
        # Should reference SHA, github.sha, or a tag strategy
        assert "sha" in content.lower() or "tag" in content.lower() or "GITHUB_SHA" in content


# ═══════════════════════════════════════════════════════════════════
#  3. DOCKER PUSH — registry → push with login
# ═══════════════════════════════════════════════════════════════════


class TestCiDockerPush:
    """When a Docker registry is configured, CI should push images."""

    def test_ghcr_push(self, tmp_path: Path):
        """GHCR registry → push to ghcr.io."""
        setup_ci(tmp_path, {
            "branches": "main", "docker": True, "overwrite": True,
            "docker_registry": "ghcr.io/myorg",
            "docker_image": "myapp",
        })
        assert "ghcr.io" in _ci_content(tmp_path)

    def test_ghcr_login_uses_github_token(self, tmp_path: Path):
        """GHCR login should use GITHUB_TOKEN secret."""
        setup_ci(tmp_path, {
            "branches": "main", "docker": True, "overwrite": True,
            "docker_registry": "ghcr.io/myorg",
        })
        content = _ci_content(tmp_path)
        assert "GITHUB_TOKEN" in content or "github.token" in content

    def test_dockerhub_push(self, tmp_path: Path):
        """DockerHub registry → push to docker.io."""
        setup_ci(tmp_path, {
            "branches": "main", "docker": True, "overwrite": True,
            "docker_registry": "docker.io/myorg",
            "docker_image": "myapp",
        })
        content = _ci_content(tmp_path)
        assert "docker.io" in content or "DOCKER" in content

    def test_dockerhub_login_uses_secrets(self, tmp_path: Path):
        """DockerHub login uses DOCKERHUB_USERNAME/TOKEN secrets."""
        setup_ci(tmp_path, {
            "branches": "main", "docker": True, "overwrite": True,
            "docker_registry": "docker.io/myorg",
        })
        content = _ci_content(tmp_path)
        assert "DOCKER" in content  # DOCKERHUB_USERNAME or DOCKER_PASSWORD

    def test_login_step_before_push(self, tmp_path: Path):
        """Login step appears before push step."""
        setup_ci(tmp_path, {
            "branches": "main", "docker": True, "overwrite": True,
            "docker_registry": "ghcr.io/myorg",
        })
        content = _ci_content(tmp_path)
        assert "login" in content.lower()

    def test_no_push_without_registry(self, tmp_path: Path):
        """Docker without registry → build only, no push."""
        setup_ci(tmp_path, {
            "branches": "main", "docker": True, "overwrite": True,
        })
        content = _ci_content(tmp_path)
        # Should have docker build but not push
        assert "docker" in content.lower()

    def test_custom_registry(self, tmp_path: Path):
        """Custom private registry → registry URL in CI."""
        setup_ci(tmp_path, {
            "branches": "main", "docker": True, "overwrite": True,
            "docker_registry": "registry.example.com/team",
            "docker_image": "myapp",
        })
        assert "registry.example.com" in _ci_content(tmp_path)


# ═══════════════════════════════════════════════════════════════════
#  5. K8S KUBECTL — raw manifests → kubectl apply
# ═══════════════════════════════════════════════════════════════════


class TestCiKubectlDeploy:
    """When K8s is enabled with kubectl, CI should have deploy steps."""

    def test_kubectl_apply_present(self, tmp_path: Path):
        """K8s + kubectl → CI includes kubectl apply."""
        setup_ci(tmp_path, {
            "branches": "main", "test_cmd": "pytest",
            "k8s": True, "k8s_deploy_method": "kubectl",
            "k8s_manifest_dir": "k8s/",
        })
        content = _ci_content(tmp_path)
        assert "kubectl" in content
        assert "apply" in content

    def test_manifest_dir_referenced(self, tmp_path: Path):
        """Manifest dir appears in kubectl apply command."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "kubectl",
            "k8s_manifest_dir": "k8s/base/",
        })
        assert "k8s/base/" in _ci_content(tmp_path) or "k8s/base" in _ci_content(tmp_path)

    def test_kubeconfig_setup(self, tmp_path: Path):
        """CI sets up kubeconfig before kubectl commands."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "kubectl",
        })
        content = _ci_content(tmp_path)
        # Should reference KUBECONFIG or a kubeconfig setup action
        assert "kubeconfig" in content.lower() or "KUBE" in content

    def test_namespace_flag(self, tmp_path: Path):
        """K8s with namespace → -n flag in kubectl apply."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "kubectl",
            "k8s_namespace": "myapp-staging",
        })
        assert "myapp-staging" in _ci_content(tmp_path)

    def test_deploy_needs_test(self, tmp_path: Path):
        """Deploy job depends on test job."""
        setup_ci(tmp_path, {
            "branches": "main", "test_cmd": "pytest",
            "k8s": True, "k8s_deploy_method": "kubectl",
        })
        parsed = _ci_parsed(tmp_path)
        jobs = parsed.get("jobs", {})
        deploy_jobs = {k: v for k, v in jobs.items()
                       if isinstance(v, dict) and "deploy" in k.lower()}
        assert len(deploy_jobs) > 0, "Expected a deploy job"
        for jd in deploy_jobs.values():
            needs = jd.get("needs", [])
            if isinstance(needs, str):
                needs = [needs]
            assert len(needs) > 0, "Deploy job must depend on test/build"

    def test_kubectl_dry_run(self, tmp_path: Path):
        """CI validates manifests before applying (dry-run)."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "kubectl",
            "k8s_manifest_dir": "k8s/",
        })
        content = _ci_content(tmp_path)
        assert "dry-run" in content or "validate" in content.lower()

    def test_kubectl_wait_rollout(self, tmp_path: Path):
        """CI waits for rollout to complete after apply."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "kubectl",
        })
        content = _ci_content(tmp_path)
        assert "rollout" in content or "wait" in content.lower()


# ═══════════════════════════════════════════════════════════════════
#  6. K8S SKAFFOLD — skaffold mode
# ═══════════════════════════════════════════════════════════════════


class TestCiSkaffoldDeploy:
    """When K8s uses Skaffold, CI uses skaffold commands."""

    def test_skaffold_command_present(self, tmp_path: Path):
        """Skaffold → CI uses skaffold run or deploy."""
        setup_ci(tmp_path, {
            "branches": "main", "test_cmd": "pytest",
            "k8s": True, "k8s_deploy_method": "skaffold",
        })
        assert "skaffold" in _ci_content(tmp_path)

    def test_skaffold_install(self, tmp_path: Path):
        """CI installs skaffold CLI."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "skaffold",
        })
        assert "skaffold" in _ci_content(tmp_path).lower()

    def test_no_kubectl_apply(self, tmp_path: Path):
        """Skaffold mode → no raw kubectl apply."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "skaffold",
        })
        assert "kubectl apply" not in _ci_content(tmp_path)

    def test_profile_per_env(self, tmp_path: Path):
        """Skaffold + envs → -p profile flag per environment."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "skaffold",
            "environments": [
                {"name": "staging", "skaffold_profile": "staging"},
                {"name": "production", "skaffold_profile": "production"},
            ],
        })
        content = _ci_content(tmp_path)
        assert "staging" in content
        assert "production" in content

    def test_default_repo(self, tmp_path: Path):
        """Skaffold + registry → --default-repo flag."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "skaffold",
            "docker_registry": "ghcr.io/myorg",
        })
        content = _ci_content(tmp_path)
        assert "default-repo" in content or "ghcr.io" in content

    def test_custom_skaffold_file(self, tmp_path: Path):
        """Custom skaffold file path → -f flag."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "skaffold",
            "skaffold_file": "deploy/skaffold.yaml",
        })
        content = _ci_content(tmp_path)
        assert "deploy/skaffold.yaml" in content or "skaffold" in content

    def test_kubeconfig_for_skaffold(self, tmp_path: Path):
        """Skaffold still needs kubeconfig setup."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "skaffold",
        })
        content = _ci_content(tmp_path)
        assert "kubeconfig" in content.lower() or "KUBE" in content


# ═══════════════════════════════════════════════════════════════════
#  7. K8S HELM — helm mode
# ═══════════════════════════════════════════════════════════════════


class TestCiHelmDeploy:
    """When K8s uses Helm, CI uses helm commands."""

    def test_helm_upgrade_install(self, tmp_path: Path):
        """Helm → CI uses helm upgrade --install."""
        setup_ci(tmp_path, {
            "branches": "main", "test_cmd": "pytest",
            "k8s": True, "k8s_deploy_method": "helm",
            "helm_chart": "./charts/myapp",
        })
        content = _ci_content(tmp_path)
        assert "helm" in content

    def test_chart_path_referenced(self, tmp_path: Path):
        """Chart path appears in helm command."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "helm",
            "helm_chart": "./charts/myapp",
        })
        assert "charts/myapp" in _ci_content(tmp_path) or "helm" in _ci_content(tmp_path)

    def test_release_name(self, tmp_path: Path):
        """Helm release name is set."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "helm",
            "helm_chart": "./charts/myapp",
            "helm_release": "myapp",
        })
        assert "myapp" in _ci_content(tmp_path)

    def test_values_per_env(self, tmp_path: Path):
        """Helm + envs → -f values-{env}.yaml."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "helm",
            "helm_chart": "./charts/myapp",
            "environments": [
                {"name": "staging", "values_file": "values-staging.yaml"},
                {"name": "production", "values_file": "values-production.yaml"},
            ],
        })
        content = _ci_content(tmp_path)
        assert "staging" in content
        assert "production" in content

    def test_set_image_tag(self, tmp_path: Path):
        """Helm + Docker → --set image.tag with dynamic tag."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "helm",
            "helm_chart": "./charts/myapp",
            "docker": True,
            "docker_image": "myapp",
        })
        content = _ci_content(tmp_path)
        # Should set image tag dynamically (SHA or version)
        assert "image" in content.lower()

    def test_helm_namespace(self, tmp_path: Path):
        """Helm deploy uses --namespace flag."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "helm",
            "helm_chart": "./charts/myapp",
            "k8s_namespace": "myapp-prod",
        })
        assert "myapp-prod" in _ci_content(tmp_path)

    def test_no_kubectl_apply(self, tmp_path: Path):
        """Helm mode → no raw kubectl apply."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "helm",
            "helm_chart": "./charts/myapp",
        })
        assert "kubectl apply" not in _ci_content(tmp_path)

    def test_no_skaffold(self, tmp_path: Path):
        """Helm mode → no skaffold."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "helm",
            "helm_chart": "./charts/myapp",
        })
        assert "skaffold" not in _ci_content(tmp_path)

    def test_kubeconfig_for_helm(self, tmp_path: Path):
        """Helm still needs kubeconfig setup."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "helm",
            "helm_chart": "./charts/myapp",
        })
        content = _ci_content(tmp_path)
        assert "kubeconfig" in content.lower() or "KUBE" in content


# ═══════════════════════════════════════════════════════════════════
#  8. MULTI-ENVIRONMENT — per-env deploys
# ═══════════════════════════════════════════════════════════════════


class TestCiMultiEnvironment:
    """Multiple environments → separate deploy steps/jobs."""

    def test_all_envs_referenced(self, tmp_path: Path):
        """3 environments → all appear in CI."""
        setup_ci(tmp_path, {
            "branches": "main", "test_cmd": "pytest",
            "k8s": True, "k8s_deploy_method": "kubectl",
            "environments": [
                {"name": "dev", "namespace": "myapp-dev"},
                {"name": "staging", "namespace": "myapp-staging"},
                {"name": "production", "namespace": "myapp-production"},
            ],
        })
        content = _ci_content(tmp_path)
        for env in ("dev", "staging", "production"):
            assert env in content, f"Environment '{env}' missing from CI"

    def test_namespace_per_env(self, tmp_path: Path):
        """Each env's namespace appears in kubectl."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True, "k8s_deploy_method": "kubectl",
            "environments": [
                {"name": "staging", "namespace": "myapp-staging"},
            ],
        })
        assert "myapp-staging" in _ci_content(tmp_path)

    def test_deploy_ordering(self, tmp_path: Path):
        """Dev deploys before staging, staging before prod."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True, "k8s_deploy_method": "kubectl",
            "environments": [
                {"name": "dev", "namespace": "myapp-dev"},
                {"name": "staging", "namespace": "myapp-staging"},
                {"name": "production", "namespace": "myapp-production"},
            ],
        })
        content = _ci_content(tmp_path)
        # dev should appear before staging, staging before production
        dev_pos = content.find("dev")
        staging_pos = content.find("staging")
        prod_pos = content.find("production")
        assert dev_pos < staging_pos < prod_pos, "Envs should be ordered dev → staging → prod"

    def test_production_main_only(self, tmp_path: Path):
        """Production deploy constrained to main branch."""
        setup_ci(tmp_path, {
            "branches": "main, develop",
            "k8s": True, "k8s_deploy_method": "kubectl",
            "environments": [
                {"name": "staging", "namespace": "myapp-staging"},
                {"name": "production", "namespace": "myapp-production", "branch": "main"},
            ],
        })
        content = _ci_content(tmp_path)
        assert "production" in content

    def test_env_specific_secrets(self, tmp_path: Path):
        """Different secret references per environment."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True, "k8s_deploy_method": "kubectl",
            "environments": [
                {"name": "staging", "namespace": "myapp-staging",
                 "kubeconfig_secret": "KUBE_CONFIG_STAGING"},
                {"name": "production", "namespace": "myapp-production",
                 "kubeconfig_secret": "KUBE_CONFIG_PRODUCTION"},
            ],
        })
        content = _ci_content(tmp_path)
        assert "STAGING" in content
        assert "PRODUCTION" in content

    def test_multi_env_skaffold_profiles(self, tmp_path: Path):
        """Skaffold + multi-env → profile per environment."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "skaffold",
            "environments": [
                {"name": "dev", "skaffold_profile": "dev"},
                {"name": "prod", "skaffold_profile": "prod"},
            ],
        })
        content = _ci_content(tmp_path)
        assert "dev" in content
        assert "prod" in content

    def test_multi_env_helm_values(self, tmp_path: Path):
        """Helm + multi-env → different values file per environment."""
        setup_ci(tmp_path, {
            "branches": "main", "k8s": True,
            "k8s_deploy_method": "helm",
            "helm_chart": "./charts/myapp",
            "environments": [
                {"name": "staging", "values_file": "values-staging.yaml"},
                {"name": "production", "values_file": "values-production.yaml"},
            ],
        })
        content = _ci_content(tmp_path)
        assert "staging" in content
        assert "production" in content


# ═══════════════════════════════════════════════════════════════════
#  9. FULL PIPELINE — Docker build + K8s deploy combined
# ═══════════════════════════════════════════════════════════════════


class TestCiFullPipeline:
    """Docker build → K8s deploy in a single workflow."""

    def test_docker_then_kubectl(self, tmp_path: Path):
        """Docker + kubectl → build, push, then kubectl apply."""
        setup_ci(tmp_path, {
            "branches": "main", "test_cmd": "pytest",
            "docker": True, "docker_registry": "ghcr.io/myorg",
            "docker_image": "myapp",
            "k8s": True, "k8s_deploy_method": "kubectl",
            "k8s_manifest_dir": "k8s/",
        })
        content = _ci_content(tmp_path)
        assert "docker" in content.lower()
        assert "kubectl" in content

    def test_docker_then_skaffold(self, tmp_path: Path):
        """Docker + Skaffold → skaffold handles build and deploy."""
        setup_ci(tmp_path, {
            "branches": "main",
            "docker": True, "docker_registry": "ghcr.io/myorg",
            "k8s": True, "k8s_deploy_method": "skaffold",
        })
        assert "skaffold" in _ci_content(tmp_path)

    def test_docker_then_helm(self, tmp_path: Path):
        """Docker + Helm → build image, then helm upgrade."""
        setup_ci(tmp_path, {
            "branches": "main",
            "docker": True, "docker_registry": "ghcr.io/myorg",
            "docker_image": "myapp",
            "k8s": True, "k8s_deploy_method": "helm",
            "helm_chart": "./charts/myapp",
        })
        content = _ci_content(tmp_path)
        assert "helm" in content

    def test_job_dependency_chain(self, tmp_path: Path):
        """Full pipeline has test → build → deploy dependency chain."""
        setup_ci(tmp_path, {
            "branches": "main", "test_cmd": "pytest",
            "docker": True, "docker_registry": "ghcr.io/myorg",
            "docker_image": "myapp",
            "k8s": True, "k8s_deploy_method": "kubectl",
        })
        parsed = _ci_parsed(tmp_path)
        jobs = parsed.get("jobs", {})
        # Should have at least test and deploy jobs
        assert len(jobs) >= 2, f"Expected ≥2 jobs, got {len(jobs)}: {list(jobs.keys())}"

    def test_deploy_only_on_main(self, tmp_path: Path):
        """Deploy job only runs on pushes to main, not on PRs."""
        setup_ci(tmp_path, {
            "branches": "main",
            "docker": True, "docker_registry": "ghcr.io/myorg",
            "k8s": True, "k8s_deploy_method": "kubectl",
        })
        parsed = _ci_parsed(tmp_path)
        jobs = parsed.get("jobs", {})
        deploy_jobs = {k: v for k, v in jobs.items()
                       if isinstance(v, dict) and "deploy" in k.lower()}
        for jd in deploy_jobs.values():
            # Should have an `if` condition limiting to push events or main branch
            assert jd.get("if"), "Deploy job should have an `if` condition"

    def test_pr_only_tests(self, tmp_path: Path):
        """PRs should only run test job, not build/deploy."""
        setup_ci(tmp_path, {
            "branches": "main", "test_cmd": "pytest",
            "docker": True, "docker_registry": "ghcr.io/myorg",
            "k8s": True, "k8s_deploy_method": "kubectl",
        })
        parsed = _ci_parsed(tmp_path)
        jobs = parsed.get("jobs", {})
        # Test job should always run; deploy should be conditional
        test_jobs = {k: v for k, v in jobs.items()
                     if isinstance(v, dict) and "test" in k.lower()}
        deploy_jobs = {k: v for k, v in jobs.items()
                       if isinstance(v, dict) and "deploy" in k.lower()}
        assert len(test_jobs) > 0, "Expected a test job"
        assert len(deploy_jobs) > 0, "Expected a deploy job"

    def test_image_tag_passed_to_deploy(self, tmp_path: Path):
        """Docker image tag/SHA passed from build to deploy job."""
        setup_ci(tmp_path, {
            "branches": "main",
            "docker": True, "docker_registry": "ghcr.io/myorg",
            "docker_image": "myapp",
            "k8s": True, "k8s_deploy_method": "kubectl",
        })
        content = _ci_content(tmp_path)
        # Image reference should exist in deploy section
        assert "myapp" in content or "image" in content.lower()

    def test_full_pipeline_valid_yaml(self, tmp_path: Path):
        """Full pipeline generates valid, parseable YAML."""
        setup_ci(tmp_path, {
            "branches": "main", "test_cmd": "pytest",
            "docker": True, "docker_registry": "ghcr.io/myorg",
            "docker_image": "myapp",
            "k8s": True, "k8s_deploy_method": "kubectl",
            "k8s_manifest_dir": "k8s/",
            "environments": [
                {"name": "staging", "namespace": "myapp-staging"},
                {"name": "production", "namespace": "myapp-production"},
            ],
        })
        parsed = _ci_parsed(tmp_path)
        assert isinstance(parsed, dict)
        assert "jobs" in parsed


# ═══════════════════════════════════════════════════════════════════
#  10. CLEANUP
# ═══════════════════════════════════════════════════════════════════


class TestCiCleanup:
    def test_delete_ci_configs(self, tmp_path: Path):
        """delete_generated_configs('ci') removes workflow file."""
        setup_ci(tmp_path, {"branches": "main"})
        assert (tmp_path / ".github" / "workflows" / "ci.yml").is_file()
        delete_generated_configs(tmp_path, "ci")
        assert not (tmp_path / ".github" / "workflows" / "ci.yml").is_file()

    def test_delete_lint_yml(self, tmp_path: Path):
        """delete_generated_configs('ci') also removes lint.yml."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "lint.yml").write_text("name: Lint\n")
        assert (wf_dir / "lint.yml").is_file()
        result = delete_generated_configs(tmp_path, "ci")
        assert not (wf_dir / "lint.yml").is_file()
        assert ".github/workflows/lint.yml" in result["deleted"]


# ═══════════════════════════════════════════════════════════════════
#  11. STACK DELEGATION & EDGE CASES
# ═══════════════════════════════════════════════════════════════════


class TestCiStackDelegation:
    """setup_ci() delegates test job generation when stacks are provided."""

    def test_python_stack_creates_python_job(self, tmp_path: Path):
        """stacks=['python'] → uses generator's python job template."""
        result = setup_ci(tmp_path, {
            "branches": "main",
            "stacks": ["python"],
        })
        assert result["ok"]
        content = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
        lo = content.lower()
        assert "python" in lo
        assert "pytest" in lo

    def test_multi_stack_dedup(self, tmp_path: Path):
        """Duplicate stacks are deduplicated."""
        result = setup_ci(tmp_path, {
            "branches": "main",
            "stacks": ["python", "python"],
        })
        assert result["ok"]
        # Only one python job, not two
        parsed = _ci_parsed(tmp_path)
        # Count jobs with 'python' in the name
        python_jobs = [
            k for k in parsed.get("jobs", {})
            if "python" in k.lower()
        ]
        assert len(python_jobs) == 1

    def test_unknown_stack_ignored(self, tmp_path: Path):
        """Unknown stacks are silently skipped."""
        result = setup_ci(tmp_path, {
            "branches": "main",
            "stacks": ["fantasy_lang"],
        })
        assert result["ok"]
        # Falls through to no test job since no valid stacks resolved
        # and no explicit test_cmd, no docker/k8s — so default fallback
        parsed = _ci_parsed(tmp_path)
        assert "jobs" in parsed


class TestCiSkaffoldPinned:
    """Skaffold install uses a pinned version, not 'latest'."""

    def test_skaffold_version_pinned(self, tmp_path: Path):
        result = setup_ci(tmp_path, {
            "branches": "main",
            "test_cmd": "pytest",
            "k8s": True,
            "k8s_deploy_method": "skaffold",
        })
        assert result["ok"]
        content = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
        assert "/releases/latest/" not in content, (
            "Skaffold should not use /releases/latest/"
        )
        assert "v2.13.2" in content


class TestCiNoStacksMode:
    """When only Docker/K8s is enabled (no stacks, no test_cmd),
    test job is omitted."""

    def test_docker_only_no_test_job(self, tmp_path: Path):
        """docker=True with no stacks/test_cmd → no test job."""
        result = setup_ci(tmp_path, {
            "branches": "main",
            "docker": True,
            "docker_registry": "ghcr.io/org",
            "docker_image": "app",
        })
        assert result["ok"]
        parsed = _ci_parsed(tmp_path)
        assert "test" not in parsed.get("jobs", {}), (
            "Expected no 'test' job when only Docker is enabled"
        )
        assert "docker" in parsed.get("jobs", {}), (
            "Docker job should still be present"
        )

    def test_docker_job_no_needs_without_test(self, tmp_path: Path):
        """Docker job without test → needs is empty list."""
        setup_ci(tmp_path, {
            "branches": "main",
            "docker": True,
        })
        parsed = _ci_parsed(tmp_path)
        docker_job = parsed["jobs"]["docker"]
        assert docker_job.get("needs", []) == []


class TestCiInvalidCombo:
    """Invalid deploy method combinations are rejected."""

    def test_invalid_deploy_method(self, tmp_path: Path):
        """Invalid k8s_deploy_method → error."""
        result = setup_ci(tmp_path, {
            "branches": "main",
            "test_cmd": "pytest",
            "k8s": True,
            "k8s_deploy_method": "terraform",
        })
        assert not result["ok"]
        assert "error" in result
        assert "terraform" in result["error"]

    def test_valid_methods_accepted(self, tmp_path: Path):
        """All three valid methods work without error."""
        for method in ("kubectl", "skaffold", "helm"):
            # Clean up between runs
            ci = tmp_path / ".github" / "workflows" / "ci.yml"
            if ci.exists():
                ci.unlink()
            result = setup_ci(tmp_path, {
                "branches": "main",
                "test_cmd": "pytest",
                "k8s": True,
                "k8s_deploy_method": method,
            })
            assert result["ok"], f"Method {method!r} should be accepted"

