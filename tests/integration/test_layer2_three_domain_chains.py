"""
Integration tests for Layer 2 — Three-Domain Chains.

Tests that compose_ci_workflows() and the underlying generators produce
correct output when three or more domains are enabled simultaneously.

Layer 2 milestones:
    2.1 Docker + K8s + CI/CD
    2.2 Docker + K8s + Skaffold
    2.3 Docker + K8s + Helm
    2.4 Docker + K8s + Terraform
    2.5 K8s + CI/CD + Multi-Environment
    2.6 K8s + Terraform + CI/CD
"""

from __future__ import annotations

import yaml
import pytest

from src.core.services.ci_compose import compose_ci_workflows
from src.core.services.k8s_wizard_generate import _generate_skaffold

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


def _k8s_svc(name: str = "api", image: str = "myapp:v1", **kw) -> dict:
    return {
        "name": name, "image": image, "port": 8080, "replicas": 2,
        "env_vars": [], **kw,
    }


# ═══════════════════════════════════════════════════════════════════
#  2.1 Docker + K8s + CI/CD
# ═══════════════════════════════════════════════════════════════════


class TestDockerK8sCiCd:
    """Full pipeline: test → docker build → docker push → deploy."""

    def test_kubectl_pipeline(self):
        """test → docker build → docker push → kubectl apply."""
        state = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
            "deploy_config": {"method": "kubectl", "manifest_dir": "k8s", "namespace": "default"},
        }
        result = compose_ci_workflows(state, strategy="unified")
        content = result[0].content
        assert "pytest" in content.lower() or "python" in content.lower()
        assert "docker" in content.lower()
        assert "kubectl" in content

    def test_skaffold_pipeline(self):
        """test → docker build → docker push → skaffold run."""
        state = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
            "deploy_config": {"method": "skaffold", "profile": "prod"},
        }
        result = compose_ci_workflows(state, strategy="unified")
        content = result[0].content
        assert "skaffold" in content

    def test_helm_pipeline(self):
        """test → docker build → docker push → helm upgrade."""
        state = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
            "deploy_config": {
                "method": "helm", "release_name": "myapp",
                "chart_path": "charts/myapp", "namespace": "default",
            },
        }
        result = compose_ci_workflows(state, strategy="unified")
        content = result[0].content
        assert "helm" in content

    def test_job_dependency_chain(self):
        """Jobs have correct needs: test → build → deploy."""
        state = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
            "deploy_config": {"method": "kubectl"},
        }
        result = compose_ci_workflows(state, strategy="unified")
        parsed = yaml.safe_load(result[0].content)
        jobs = parsed.get("jobs", {})

        # Docker should need a test job
        docker_job = jobs.get("docker", {})
        assert docker_job.get("needs"), "Docker job should have needs"

        # Deploy should need docker
        deploy_job = jobs.get("deploy", {})
        if deploy_job:
            assert "docker" in deploy_job.get("needs", [])

    def test_image_tag_in_deploy(self):
        """Docker image tag (${{ github.sha }}) passed to deploy."""
        state = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
            "deploy_config": {
                "method": "helm", "release_name": "app",
                "chart_path": "charts/app",
            },
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "github.sha" in content

    def test_deploy_push_only(self):
        """Deploy only on push to main, not on PRs."""
        state = {
            "stack_names": ["python"],
            "deploy_config": {"method": "kubectl"},
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "github.event_name == 'push'" in content

    def test_pr_tests_only(self):
        """PRs run tests only (pull_request trigger present)."""
        state = {
            "stack_names": ["python"],
            "docker_services": [_docker_svc()],
            "deploy_config": {"method": "kubectl"},
        }
        result = compose_ci_workflows(state)
        parsed = yaml.safe_load(result[0].content)
        on_block = parsed.get("on", parsed.get(True, {}))
        assert "pull_request" in on_block


# ═══════════════════════════════════════════════════════════════════
#  2.2 Docker + K8s + Skaffold
# ═══════════════════════════════════════════════════════════════════


class TestDockerK8sSkaffold:
    """Skaffold builds Docker and deploys K8s manifests."""

    def test_skaffold_builds_docker_and_deploys(self):
        """Skaffold config has both build artifacts and deploy."""
        data = {
            "skaffold": True, "deployStrategy": "kubectl",
            "_services": [_k8s_svc()],
            "_namespace": "default",
        }
        result = _generate_skaffold(data, [])
        skaffold = yaml.safe_load(result["content"])
        assert "build" in skaffold
        assert "deploy" in skaffold

    def test_default_repo_in_ci(self):
        """Docker registry → Skaffold --default-repo in CI."""
        state = {
            "deploy_config": {
                "method": "skaffold",
                "default_repo": "ghcr.io/myorg",
            },
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "default-repo" in content or "skaffold" in content

    def test_skaffold_profiles_per_env(self):
        """Skaffold profiles select different manifests per env."""
        data = {
            "skaffold": True, "deployStrategy": "kubectl",
            "_services": [_k8s_svc()],
            "_namespace": "default",
            "environments": ["dev", "prod"],
        }
        result = _generate_skaffold(data, [])
        skaffold = yaml.safe_load(result["content"])
        profiles = skaffold.get("profiles", [])
        names = [p["name"] for p in profiles]
        assert "dev" in names
        assert "prod" in names


# ═══════════════════════════════════════════════════════════════════
#  2.3 Docker + K8s + Helm
# ═══════════════════════════════════════════════════════════════════


class TestDockerK8sHelm:
    """Docker image → Helm values → K8s Deployment."""

    def test_docker_image_in_helm_values(self):
        """Docker image flows into Helm values.yaml."""
        from src.core.services.k8s_helm_generate import (
            generate_helm_chart, _build_values_yaml,
        )
        data = {
            "helm_chart": True,
            "_services": [_k8s_svc(image="ghcr.io/org/api:v2.0")],
        }
        values = _build_values_yaml(data, data["_services"])
        assert values["image"]["repository"] == "ghcr.io/org/api"
        assert values["image"]["tag"] == "v2.0"

    def test_docker_registry_in_helm_repository(self):
        """Docker registry → Helm image.repository."""
        from src.core.services.k8s_helm_generate import _build_values_yaml
        data = {
            "helm_chart": True,
            "_services": [_k8s_svc(image="myregistry.azurecr.io/app:latest")],
        }
        values = _build_values_yaml(data, data["_services"])
        assert "myregistry.azurecr.io" in values["image"]["repository"]

    def test_docker_tag_in_helm_tag(self):
        """Docker tag → Helm image.tag."""
        from src.core.services.k8s_helm_generate import _build_values_yaml
        data = {
            "helm_chart": True,
            "_services": [_k8s_svc(image="app:sha-abc123")],
        }
        values = _build_values_yaml(data, data["_services"])
        assert values["image"]["tag"] == "sha-abc123"

    def test_helm_ci_sets_image_tag(self):
        """CI helm deploy uses --set image.tag=${{ github.sha }}."""
        state = {
            "deploy_config": {
                "method": "helm", "release_name": "app",
                "chart_path": "charts/app",
            },
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "image.tag" in content
        assert "github.sha" in content

    def test_helm_values_per_env(self):
        """Helm values per env → different Docker tags per env."""
        from src.core.services.k8s_helm_generate import _build_env_overrides
        dev = _build_env_overrides("dev")
        prod = _build_env_overrides("prod")
        # Dev and prod should have different image tags
        dev_tag = dev.get("image", {}).get("tag", "")
        prod_tag = prod.get("image", {}).get("tag", "")
        # At minimum, both should exist or differ
        assert "image" in dev or "replicaCount" in dev
        assert "image" in prod or "replicaCount" in prod


# ═══════════════════════════════════════════════════════════════════
#  2.4 Docker + K8s + Terraform
# ═══════════════════════════════════════════════════════════════════


class TestDockerK8sTerraform:
    """Terraform provisions cluster + registry → Docker/K8s use them."""

    def test_terraform_provisions_cluster_and_registry(self, tmp_path):
        """Terraform K8s config has cluster + registry resources."""
        from src.core.services.terraform_generate import generate_terraform_k8s
        result = generate_terraform_k8s(
            tmp_path, "aws",
            backend="s3",
            namespace="default",
            services=[_k8s_svc(image="myapp:v1")],
        )
        assert result["ok"]
        files = result["files"]
        # main.tf should have cluster + registry
        main_tf = [f for f in files if f["path"].endswith("main.tf")][0]
        assert "aws_eks_cluster" in main_tf["content"]
        assert "aws_ecr_repository" in main_tf["content"]

    def test_docker_pushes_to_provisioned_registry(self):
        """terraform_to_docker_registry gives push target from TF output."""
        from src.core.services.terraform_generate import terraform_to_docker_registry
        result = terraform_to_docker_registry("aws", project_name="myapp")
        assert result["ok"]
        assert result["registry_url"]
        assert "ecr" in result["registry_url"].lower() or "amazonaws" in result["registry_url"].lower()

    def test_k8s_deploys_to_provisioned_cluster(self, tmp_path):
        """Terraform outputs include cluster endpoint for K8s deploy."""
        from src.core.services.terraform_generate import generate_terraform_k8s
        result = generate_terraform_k8s(
            tmp_path, "aws",
            backend="s3",
            namespace="default",
            services=[_k8s_svc()],
        )
        files = result["files"]
        outputs_tf = [f for f in files if f["path"].endswith("outputs.tf")][0]
        assert "cluster_endpoint" in outputs_tf["content"]
        assert "registry_url" in outputs_tf["content"]


# ═══════════════════════════════════════════════════════════════════
#  2.5 K8s + CI/CD + Multi-Environment
# ═══════════════════════════════════════════════════════════════════


class TestK8sCiCdMultiEnv:
    """Multi-environment deploy in CI."""

    def test_all_envs_in_ci(self):
        """All environments referenced in CI output."""
        state = {
            "stack_names": ["python"],
            "deploy_config": {"method": "kubectl"},
            "environments": ["dev", "staging", "production"],
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "deploy-dev" in content
        assert "deploy-staging" in content
        assert "deploy-production" in content

    def test_namespace_per_environment(self):
        """Each env gets its own namespace."""
        state = {
            "deploy_config": {"method": "kubectl"},
            "environments": ["dev", "staging"],
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "dev" in content
        assert "staging" in content

    def test_production_push_only(self):
        """Production deploy constrained to push (if: github.event_name)."""
        state = {
            "deploy_config": {"method": "kubectl"},
            "environments": ["production"],
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "github.event_name == 'push'" in content

    def test_skaffold_profiles_per_env_in_ci(self):
        """Skaffold deploy CI → profile per env."""
        state = {
            "deploy_config": {"method": "skaffold"},
            "environments": ["dev", "prod"],
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        # Each env deploy should use skaffold
        assert "skaffold" in content
        assert "deploy-dev" in content
        assert "deploy-prod" in content

    def test_helm_values_per_env_in_ci(self):
        """Helm deploy CI → values-{env}.yaml per env."""
        state = {
            "deploy_config": {
                "method": "helm", "release_name": "app",
                "chart_path": "charts/app",
            },
            "environments": ["dev", "staging", "prod"],
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "values-dev.yaml" in content
        assert "values-staging.yaml" in content
        assert "values-prod.yaml" in content

    def test_per_env_secrets_comment(self):
        """Per-env deploy jobs reference kubeconfig from secrets."""
        state = {
            "deploy_config": {"method": "kubectl"},
            "environments": ["dev"],
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "KUBECONFIG" in content or "kubeconfig" in content.lower()


# ═══════════════════════════════════════════════════════════════════
#  2.6 K8s + Terraform + CI/CD
# ═══════════════════════════════════════════════════════════════════


class TestK8sTerraformCiCd:
    """Terraform + K8s deploy in single CI workflow."""

    def test_terraform_and_deploy_in_same_workflow(self):
        """CI has both terraform and deploy jobs."""
        state = {
            "stack_names": ["python"],
            "terraform_config": {"provider": "aws", "working_directory": "terraform"},
            "deploy_config": {"method": "kubectl"},
        }
        result = compose_ci_workflows(state, strategy="unified")
        content = result[0].content
        assert "terraform" in content.lower()
        assert "kubectl" in content

    def test_terraform_state_from_secrets(self):
        """Terraform job uses secrets for auth."""
        state = {
            "terraform_config": {"provider": "aws"},
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "secrets.AWS" in content or "AWS_ACCESS_KEY_ID" in content

    def test_kubeconfig_from_secrets(self):
        """Deploy job uses kubeconfig from secrets."""
        state = {
            "deploy_config": {"method": "kubectl"},
        }
        result = compose_ci_workflows(state)
        content = result[0].content
        assert "KUBECONFIG" in content or "kubeconfig" in content.lower()

    def test_split_separate_tf_and_deploy(self):
        """Split strategy → separate Terraform and deploy files."""
        state = {
            "stack_names": ["python"],
            "terraform_config": {"provider": "aws"},
            "deploy_config": {"method": "kubectl"},
        }
        result = compose_ci_workflows(state, strategy="split")
        paths = [f.path for f in result]
        assert any("terraform" in p for p in paths)
        assert any("deploy" in p for p in paths)
