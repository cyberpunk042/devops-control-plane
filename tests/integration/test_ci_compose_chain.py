"""
Integration tests for CI/CD Compose (0.5).

Tests the cross-domain compose function that orchestrates all CI
generators into coherent workflow files based on wizard state.

Covers:
    0.5.1 — Basic structure (unified vs split)
    0.5.2 — Job dependency chains
    0.5.3 — Domain integration
    0.5.4 — Multi-environment
"""

from __future__ import annotations

import yaml
import pytest

from src.core.services.ci_compose import compose_ci_workflows

pytestmark = pytest.mark.integration


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _docker_svc(name: str = "api", **kw) -> dict:
    return {
        "name": name, "image": f"{name}:latest",
        "registry": "ghcr.io/org", "registry_type": "ghcr",
        **kw,
    }


def _deploy_kubectl(**kw) -> dict:
    return {"method": "kubectl", "manifest_dir": "k8s", "namespace": "default", **kw}


def _deploy_helm(**kw) -> dict:
    return {
        "method": "helm", "release_name": "app",
        "chart_path": "charts/app", "namespace": "default", **kw,
    }


def _deploy_skaffold(**kw) -> dict:
    return {"method": "skaffold", "profile": "dev", **kw}


# ═══════════════════════════════════════════════════════════════════
#  0.5.1 — Basic structure
# ═══════════════════════════════════════════════════════════════════


class TestBasicStructure:
    """compose_ci_workflows basic structure."""

    def test_empty_state_returns_empty(self):
        """No CI-relevant config → empty list."""
        result = compose_ci_workflows({})
        assert result == []

    def test_unified_returns_single_file(self):
        """strategy=unified → single GeneratedFile."""
        state = {"stack_names": ["python"]}
        result = compose_ci_workflows(state, strategy="unified")
        assert len(result) == 1
        assert result[0].path == ".github/workflows/ci-cd.yml"

    def test_split_returns_multiple_files(self):
        """strategy=split → separate workflow files."""
        state = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
            "deploy_config": _deploy_kubectl(),
        }
        result = compose_ci_workflows(state, strategy="split")
        paths = [f.path for f in result]
        assert ".github/workflows/ci.yml" in paths
        assert ".github/workflows/docker.yml" in paths
        assert ".github/workflows/deploy.yml" in paths

    def test_unified_valid_yaml(self):
        """Unified output is valid YAML."""
        state = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
        }
        result = compose_ci_workflows(state, strategy="unified")
        content = result[0].content
        parsed = yaml.safe_load(content)
        assert "jobs" in parsed

    def test_split_all_valid_yaml(self):
        """All split output files are valid YAML."""
        state = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
            "deploy_config": _deploy_helm(),
        }
        result = compose_ci_workflows(state, strategy="split")
        for f in result:
            parsed = yaml.safe_load(f.content)
            assert "name" in parsed, f"Missing name in {f.path}"

    def test_project_name_in_workflow_name(self):
        """project_name flows into workflow name."""
        state = {"stack_names": ["python"]}
        result = compose_ci_workflows(state, project_name="MyApp")
        parsed = yaml.safe_load(result[0].content)
        assert "MyApp" in parsed["name"]


# ═══════════════════════════════════════════════════════════════════
#  0.5.2 — Job dependency chains
# ═══════════════════════════════════════════════════════════════════


class TestJobDependencyChains:
    """Test → build → deploy ordering."""

    def test_docker_needs_test(self):
        """Docker job depends on test job."""
        state = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
        }
        result = compose_ci_workflows(state, strategy="unified")
        content = result[0].content
        # Docker job should have a needs: referencing a test-related job
        assert "needs:" in content

    def test_deploy_needs_docker(self):
        """Deploy job depends on docker job."""
        state = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
            "deploy_config": _deploy_kubectl(),
        }
        result = compose_ci_workflows(state, strategy="unified")
        parsed = yaml.safe_load(result[0].content)
        jobs = parsed.get("jobs", {})
        # Deploy should depend on docker
        deploy = jobs.get("deploy", {})
        if deploy:
            assert "docker" in deploy.get("needs", [])

    def test_pr_test_only(self):
        """PRs trigger workflow (on.pull_request present)."""
        state = {"stack_names": ["python"]}
        result = compose_ci_workflows(state)
        parsed = yaml.safe_load(result[0].content)
        on_block = parsed.get("on", parsed.get(True, {}))
        assert "pull_request" in on_block

    def test_deploy_push_only(self):
        """Deploy jobs have if: github.event_name == 'push'."""
        state = {
            "stack_names": ["python"],
            "deploy_config": _deploy_kubectl(),
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "github.event_name == 'push'" in content

    def test_split_workflow_run_trigger(self):
        """Split docker workflow triggered by CI workflow_run."""
        state = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
        }
        result = compose_ci_workflows(state, strategy="split")
        docker_file = [f for f in result if "docker" in f.path][0]
        parsed = yaml.safe_load(docker_file.content)
        on_block = parsed.get("on", parsed.get(True, {}))
        assert "workflow_run" in on_block


# ═══════════════════════════════════════════════════════════════════
#  0.5.3 — Domain integration
# ═══════════════════════════════════════════════════════════════════


class TestDomainIntegration:
    """Each domain section in wizard state → correct jobs in output."""

    def test_stack_names_produce_test_jobs(self):
        """stack_names → test jobs in output."""
        state = {"stack_names": ["python"]}
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "pytest" in content.lower() or "test" in content.lower()

    def test_docker_services_produce_build_jobs(self):
        """docker_services → Docker build jobs in output."""
        state = {"docker_services": [_docker_svc()]}
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "docker" in content.lower()
        assert "build" in content.lower()

    def test_deploy_kubectl(self):
        """deploy_config (kubectl) → kubectl deploy job."""
        state = {"deploy_config": _deploy_kubectl()}
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "kubectl" in content

    def test_deploy_helm(self):
        """deploy_config (helm) → helm deploy job."""
        state = {"deploy_config": _deploy_helm()}
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "helm" in content

    def test_deploy_skaffold(self):
        """deploy_config (skaffold) → skaffold deploy job."""
        state = {"deploy_config": _deploy_skaffold()}
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "skaffold" in content

    def test_terraform_config_produces_tf_job(self):
        """terraform_config → terraform job in output."""
        state = {"terraform_config": {"provider": "aws"}}
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "terraform" in content.lower()

    def test_dns_cdn_post_deploy(self):
        """domains + cdn_provider → post-deploy steps."""
        state = {
            "deploy_config": _deploy_kubectl(),
            "domains": ["example.com"],
            "cdn_provider": "cloudflare",
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "dig" in content
        assert "cloudflare" in content.lower()

    def test_full_pipeline_all_domains(self):
        """All domains enabled → unified file has all sections."""
        state = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
            "deploy_config": _deploy_helm(),
            "terraform_config": {"provider": "aws"},
            "domains": ["example.com"],
            "cdn_provider": "cloudflare",
        }
        result = compose_ci_workflows(state, strategy="unified")
        content = result[0].content
        assert "pytest" in content.lower() or "python" in content.lower()
        assert "docker" in content.lower()
        assert "helm" in content.lower()
        assert "terraform" in content.lower()
        assert "dig" in content


# ═══════════════════════════════════════════════════════════════════
#  0.5.4 — Multi-environment
# ═══════════════════════════════════════════════════════════════════


class TestMultiEnvironment:
    """Per-environment deploy jobs."""

    def test_env_deploy_jobs_created(self):
        """environments → per-env deploy jobs."""
        state = {
            "deploy_config": _deploy_kubectl(),
            "environments": ["dev", "staging", "prod"],
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "deploy-dev" in content
        assert "deploy-staging" in content
        assert "deploy-prod" in content

    def test_env_namespace_in_deploy(self):
        """Environment name used as namespace."""
        state = {
            "deploy_config": _deploy_kubectl(namespace=""),
            "environments": ["staging"],
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "staging" in content

    def test_helm_env_values_file(self):
        """Helm deploy per env → values-{env}.yaml."""
        state = {
            "deploy_config": _deploy_helm(),
            "environments": ["dev", "prod"],
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "values-dev.yaml" in content
        assert "values-prod.yaml" in content

    def test_split_env_deploys(self):
        """Split strategy also generates per-env deploy jobs."""
        state = {
            "stack_names": ["python"],
            "deploy_config": _deploy_helm(),
            "environments": ["dev", "prod"],
        }
        result = compose_ci_workflows(state, strategy="split")
        deploy_file = [f for f in result if "deploy" in f.path][0]
        content = deploy_file.content
        assert "deploy-dev" in content
        assert "deploy-prod" in content
