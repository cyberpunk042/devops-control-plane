"""
Integration tests for Layer 4 — Order of Execution Variants.

Tests that compose_ci_workflows() correctly adapts its output when
domains are added incrementally in different orders.

Layer 4 milestones:
    4.1 Docker first
    4.2 K8s first
    4.3 CI first
    4.4 Terraform first
    4.5 Re-run after changes
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
#  4.1 Docker first
# ═══════════════════════════════════════════════════════════════════


class TestDockerFirst:
    """Enable Docker → then K8s → then CI → full pipeline."""

    def test_docker_only(self):
        """Docker alone → docker build job, no deploy."""
        state = {"docker_services": [_docker_svc()]}
        result = compose_ci_workflows(state)
        assert len(result) == 1
        content = result[0].content
        assert "docker" in content.lower()
        # No deploy
        assert "kubectl" not in content
        assert "helm" not in content.lower()

    def test_docker_then_k8s(self):
        """Docker + K8s → docker build + deploy."""
        state = {
            "docker_services": [_docker_svc()],
            "deploy_config": {"method": "kubectl"},
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "docker" in content.lower()
        assert "kubectl" in content

    def test_docker_then_ci(self):
        """Docker + CI → test + docker build."""
        state = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "python" in content.lower() or "pytest" in content.lower()
        assert "docker" in content.lower()

    def test_docker_then_k8s_then_ci(self):
        """Docker + K8s + CI → full pipeline."""
        state = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
            "deploy_config": {"method": "kubectl"},
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "docker" in content.lower()
        assert "kubectl" in content


# ═══════════════════════════════════════════════════════════════════
#  4.2 K8s first
# ═══════════════════════════════════════════════════════════════════


class TestK8sFirst:
    """Enable K8s → then Docker → then CI."""

    def test_k8s_only(self):
        """K8s alone → deploy job only."""
        state = {"deploy_config": {"method": "kubectl"}}
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "kubectl" in content

    def test_k8s_then_docker(self):
        """K8s + Docker → docker build + deploy (deploy needs docker)."""
        state = {
            "docker_services": [_docker_svc()],
            "deploy_config": {"method": "kubectl"},
        }
        result = compose_ci_workflows(state)
        parsed = yaml.safe_load(result[0].content)
        jobs = parsed.get("jobs", {})
        deploy_job = jobs.get("deploy", {})
        if deploy_job:
            assert "docker" in deploy_job.get("needs", [])

    def test_k8s_then_docker_then_ci(self):
        """K8s + Docker + CI → full pipeline."""
        state = {
            "stack_names": ["node"],
            "docker_services": [_docker_svc()],
            "deploy_config": {"method": "helm", "release_name": "app", "chart_path": "charts/app"},
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "node" in content.lower() or "npm" in content.lower()
        assert "docker" in content.lower()
        assert "helm" in content


# ═══════════════════════════════════════════════════════════════════
#  4.3 CI first
# ═══════════════════════════════════════════════════════════════════


class TestCiFirst:
    """Enable CI alone → then Docker → then K8s → full pipeline."""

    def test_ci_alone(self):
        """CI alone → test-only workflow."""
        state = {"stack_names": ["python"]}
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "python" in content.lower() or "pytest" in content.lower()
        assert "docker" not in content.lower()
        assert "kubectl" not in content
        assert "deploy" not in content.lower() or "post-deploy" in content.lower()

    def test_ci_then_docker(self):
        """CI + Docker → test + docker build."""
        state = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "docker" in content.lower()

    def test_ci_then_k8s(self):
        """CI + K8s → test + deploy."""
        state = {
            "stack_names": ["python"],
            "deploy_config": {"method": "kubectl"},
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "kubectl" in content

    def test_ci_then_docker_then_k8s(self):
        """CI + Docker + K8s → full pipeline."""
        state = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
            "deploy_config": {"method": "kubectl"},
        }
        result = compose_ci_workflows(state)
        parsed = yaml.safe_load(result[0].content)
        jobs = parsed.get("jobs", {})
        assert len(jobs) >= 3  # test + docker + deploy


# ═══════════════════════════════════════════════════════════════════
#  4.4 Terraform first
# ═══════════════════════════════════════════════════════════════════


class TestTerraformFirst:
    """Enable Terraform → then K8s / Docker."""

    def test_terraform_alone(self):
        """Terraform alone → Terraform job only."""
        state = {"terraform_config": {"provider": "aws"}}
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "terraform" in content.lower()

    def test_terraform_then_k8s(self):
        """Terraform + K8s → terraform + deploy in same pipeline."""
        state = {
            "terraform_config": {"provider": "aws"},
            "deploy_config": {"method": "kubectl"},
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "terraform" in content.lower()
        assert "kubectl" in content

    def test_terraform_then_docker(self):
        """Terraform + Docker → terraform + docker build."""
        state = {
            "terraform_config": {"provider": "aws"},
            "docker_services": [_docker_svc()],
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "terraform" in content.lower()
        assert "docker" in content.lower()


# ═══════════════════════════════════════════════════════════════════
#  4.5 Re-run after changes
# ═══════════════════════════════════════════════════════════════════


class TestRerunAfterChanges:
    """Compose adapts when wizard state changes."""

    def test_change_deploy_method(self):
        """kubectl → helm → output changes."""
        base = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
        }
        # With kubectl
        state1 = {**base, "deploy_config": {"method": "kubectl"}}
        r1 = compose_ci_workflows(state1)
        assert "kubectl" in r1[0].content

        # Switch to helm
        state2 = {**base, "deploy_config": {
            "method": "helm", "release_name": "app", "chart_path": "charts/app",
        }}
        r2 = compose_ci_workflows(state2)
        assert "helm" in r2[0].content
        assert "kubectl" not in r2[0].content

    def test_add_environment(self):
        """Adding env → new deploy job appears."""
        base = {
            "deploy_config": {"method": "kubectl"},
        }
        # No envs
        r1 = compose_ci_workflows(base)
        assert "deploy-staging" not in r1[0].content

        # Add staging
        r2 = compose_ci_workflows({**base, "environments": ["dev", "staging"]})
        assert "deploy-staging" in r2[0].content

    def test_remove_docker(self):
        """Removing docker → no docker job."""
        full = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
            "deploy_config": {"method": "kubectl"},
        }
        r1 = compose_ci_workflows(full)
        assert "docker" in r1[0].content.lower()

        # Remove docker
        no_docker = {
            "stack_names": ["python"],
            "deploy_config": {"method": "kubectl"},
        }
        r2 = compose_ci_workflows(no_docker)
        # No docker job
        parsed = yaml.safe_load(r2[0].content)
        assert "docker" not in parsed.get("jobs", {})

    def test_add_dns_cdn(self):
        """Adding DNS/CDN → post-deploy steps appear."""
        base = {"deploy_config": {"method": "kubectl"}}
        r1 = compose_ci_workflows(base)
        assert "dig" not in r1[0].content

        with_dns = {**base, "domains": ["example.com"], "cdn_provider": "cloudflare"}
        r2 = compose_ci_workflows(with_dns)
        assert "dig" in r2[0].content
        assert "cloudflare" in r2[0].content.lower()
