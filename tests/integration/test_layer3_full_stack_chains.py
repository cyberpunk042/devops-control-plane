"""
Integration tests for Layer 3 — Full Stack Chains.

Tests that compose_ci_workflows() handles full-stack wizard states
with 4+ domains simultaneously enabled.

Layer 3 milestones:
    3.1 Docker + K8s + Skaffold + CI/CD + Multi-Env
    3.2 Docker + K8s + Helm + CI/CD + Multi-Env
    3.3 Docker + K8s + Terraform + CI/CD
    3.4 Everything
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


# ═══════════════════════════════════════════════════════════════════
#  3.1 Docker + K8s + Skaffold + CI/CD + Multi-Env
# ═══════════════════════════════════════════════════════════════════


class TestFullStackSkaffold:
    """Docker + K8s + Skaffold + CI/CD + Multi-Env."""

    def _state(self):
        return {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
            "deploy_config": {"method": "skaffold"},
            "environments": ["dev", "staging", "prod"],
        }

    def test_unified_has_all_sections(self):
        """Unified workflow has test, docker, per-env skaffold deploy."""
        result = compose_ci_workflows(self._state(), strategy="unified")
        content = result[0].content
        assert "skaffold" in content
        assert "deploy-dev" in content
        assert "deploy-staging" in content
        assert "deploy-prod" in content

    def test_split_generates_all_files(self):
        """Split strategy → ci + docker + deploy files."""
        result = compose_ci_workflows(self._state(), strategy="split")
        paths = [f.path for f in result]
        assert any("ci" in p for p in paths)
        assert any("docker" in p for p in paths)
        assert any("deploy" in p for p in paths)

    def test_pr_test_only(self):
        """PR trigger present → test runs on PR."""
        result = compose_ci_workflows(self._state())
        parsed = yaml.safe_load(result[0].content)
        on_block = parsed.get("on", parsed.get(True, {}))
        assert "pull_request" in on_block

    def test_deploy_push_only(self):
        """Deploy jobs constrained to push."""
        result = compose_ci_workflows(self._state())
        content = result[0].content
        assert "github.event_name == 'push'" in content


# ═══════════════════════════════════════════════════════════════════
#  3.2 Docker + K8s + Helm + CI/CD + Multi-Env
# ═══════════════════════════════════════════════════════════════════


class TestFullStackHelm:
    """Docker + K8s + Helm + CI/CD + Multi-Env."""

    def _state(self):
        return {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
            "deploy_config": {
                "method": "helm", "release_name": "app",
                "chart_path": "charts/app",
            },
            "environments": ["dev", "staging", "prod"],
        }

    def test_unified_has_test_build_deploy(self):
        """Unified: test → docker → helm per env."""
        result = compose_ci_workflows(self._state())
        content = result[0].content
        parsed = yaml.safe_load(content)
        jobs = parsed.get("jobs", {})
        # Should have test-related, docker, and per-env deploy jobs
        assert len(jobs) >= 4  # test + docker + at least 2 deploy-envs

    def test_helm_values_per_env(self):
        """Each env uses values-{env}.yaml."""
        result = compose_ci_workflows(self._state())
        content = result[0].content
        assert "values-dev.yaml" in content
        assert "values-staging.yaml" in content
        assert "values-prod.yaml" in content

    def test_image_tag_set(self):
        """Helm --set image.tag=${{ github.sha }}."""
        result = compose_ci_workflows(self._state())
        content = result[0].content
        assert "image.tag" in content
        assert "github.sha" in content

    def test_deploy_push_only(self):
        """Deploy only on push to main."""
        result = compose_ci_workflows(self._state())
        content = result[0].content
        assert "github.event_name == 'push'" in content


# ═══════════════════════════════════════════════════════════════════
#  3.3 Docker + K8s + Terraform + CI/CD
# ═══════════════════════════════════════════════════════════════════


class TestFullStackTerraform:
    """Docker + K8s + Terraform + CI/CD."""

    def _state(self):
        return {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
            "deploy_config": {"method": "kubectl"},
            "terraform_config": {"provider": "aws", "working_directory": "terraform"},
        }

    def test_unified_has_terraform_and_deploy(self):
        """CI has terraform, docker, and deploy jobs."""
        result = compose_ci_workflows(self._state())
        content = result[0].content
        assert "terraform" in content.lower()
        assert "docker" in content.lower()
        assert "kubectl" in content

    def test_split_generates_terraform_file(self):
        """Split strategy has dedicated terraform.yml."""
        result = compose_ci_workflows(self._state(), strategy="split")
        paths = [f.path for f in result]
        assert any("terraform" in p for p in paths)


# ═══════════════════════════════════════════════════════════════════
#  3.4 Everything
# ═══════════════════════════════════════════════════════════════════


class TestEverything:
    """Docker + K8s (Helm) + Terraform + CI/CD + DNS + Multi-Env."""

    def _state(self):
        return {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
            "deploy_config": {
                "method": "helm", "release_name": "app",
                "chart_path": "charts/app",
            },
            "terraform_config": {"provider": "aws"},
            "domains": ["example.com", "api.example.com"],
            "cdn_provider": "cloudflare",
            "environments": ["dev", "staging", "prod"],
        }

    def test_unified_everything(self):
        """Single file has every section."""
        result = compose_ci_workflows(self._state(), strategy="unified")
        assert len(result) == 1
        content = result[0].content
        # Test
        assert "python" in content.lower() or "pytest" in content.lower()
        # Docker
        assert "docker" in content.lower()
        # Helm
        assert "helm" in content
        # Terraform
        assert "terraform" in content.lower()
        # DNS
        assert "dig" in content
        # CDN
        assert "cloudflare" in content.lower()
        # Multi-env
        assert "deploy-dev" in content
        assert "deploy-prod" in content

    def test_unified_is_valid_yaml(self):
        """Full stack unified output is valid YAML."""
        result = compose_ci_workflows(self._state())
        parsed = yaml.safe_load(result[0].content)
        assert "jobs" in parsed

    def test_split_everything(self):
        """Split produces multiple files with correct domains."""
        result = compose_ci_workflows(self._state(), strategy="split")
        assert len(result) >= 4  # ci + docker + terraform + deploy + post-deploy
        paths = [f.path for f in result]
        assert any("ci" in p for p in paths)
        assert any("docker" in p for p in paths)
        assert any("terraform" in p for p in paths)
        assert any("deploy" in p for p in paths)

    def test_split_all_valid_yaml(self):
        """All split files are valid YAML."""
        result = compose_ci_workflows(self._state(), strategy="split")
        for f in result:
            parsed = yaml.safe_load(f.content)
            assert "name" in parsed, f"Missing name in {f.path}"

    def test_project_name_everywhere(self):
        """project_name flows through all workflows."""
        result = compose_ci_workflows(
            self._state(), strategy="split", project_name="SuperApp",
        )
        for f in result:
            parsed = yaml.safe_load(f.content)
            assert "SuperApp" in parsed.get("name", ""), f"Missing project name in {f.path}"
