"""
Integration tests for K8s + CI/CD deploy chain (1.5, 1.6, 1.7).

Tests how K8s deployment config controls CI workflow generation
for kubectl, Skaffold, and Helm deploy strategies.
"""

from __future__ import annotations

import yaml
import pytest

from src.core.services.generators.github_workflow import generate_k8s_deploy_ci

pytestmark = pytest.mark.integration


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _gen(config: dict, **kwargs) -> dict:
    """Call generate_k8s_deploy_ci and return content + parsed YAML."""
    result = generate_k8s_deploy_ci(config, **kwargs)
    assert result is not None, "generate_k8s_deploy_ci returned None"
    content = result.content
    parsed = yaml.safe_load(content)
    return {"content": content, "parsed": parsed, "result": result}


# ═══════════════════════════════════════════════════════════════════
#  1.5 — K8s + CI/CD (kubectl)
# ═══════════════════════════════════════════════════════════════════


class TestKubectlDeploy:
    """Kubectl deploy CI job generation."""

    def test_kubectl_apply(self):
        """K8s + kubectl → CI has kubectl apply."""
        out = _gen({"method": "kubectl", "manifest_dir": "k8s"})
        assert "kubectl apply -f k8s/" in out["content"]

    def test_manifest_dir(self):
        """Manifest dir referenced in apply command."""
        out = _gen({"method": "kubectl", "manifest_dir": "deploy/manifests"})
        assert "kubectl apply -f deploy/manifests/" in out["content"]

    def test_namespace_flag(self):
        """Namespace → -n flag in kubectl commands."""
        out = _gen({"method": "kubectl", "namespace": "prod"})
        assert "-n prod" in out["content"]

    def test_depends_on_test(self):
        """Deploy job depends on test."""
        out = _gen({"method": "kubectl"})
        deploy_job = out["parsed"]["jobs"]["deploy"]
        assert "test" in deploy_job.get("needs", [])

    def test_custom_needs(self):
        """Deploy job depends on docker build."""
        out = _gen({"method": "kubectl", "needs": ["docker"]})
        deploy_job = out["parsed"]["jobs"]["deploy"]
        assert "docker" in deploy_job.get("needs", [])

    def test_kubeconfig_from_secret(self):
        """Deploy job sets up kubeconfig from secret."""
        out = _gen({"method": "kubectl"})
        assert "KUBECONFIG" in out["content"]
        assert "base64 -d" in out["content"]

    def test_dry_run(self):
        """Deploy job runs dry-run before apply."""
        out = _gen({"method": "kubectl"})
        assert "--dry-run=server" in out["content"]

    def test_rollout_status(self):
        """Deploy job waits for rollout."""
        out = _gen({"method": "kubectl", "app_name": "myapi"})
        assert "kubectl rollout status deployment/myapi" in out["content"]

    def test_push_only(self):
        """Deploy job only runs on push."""
        out = _gen({"method": "kubectl"})
        deploy_job = out["parsed"]["jobs"]["deploy"]
        assert deploy_job.get("if") == "github.event_name == 'push'"

    def test_valid_yaml(self):
        """Generated YAML is valid."""
        out = _gen({"method": "kubectl"})
        assert out["parsed"] is not None
        assert "jobs" in out["parsed"]


# ═══════════════════════════════════════════════════════════════════
#  1.6 — K8s + CI/CD (Skaffold)
# ═══════════════════════════════════════════════════════════════════


class TestSkaffoldDeploy:
    """Skaffold deploy CI job generation."""

    def test_skaffold_run(self):
        """K8s + skaffold → CI has skaffold run."""
        out = _gen({"method": "skaffold"})
        assert "skaffold run" in out["content"]

    def test_installs_skaffold(self):
        """CI installs skaffold CLI."""
        out = _gen({"method": "skaffold"})
        assert "Install Skaffold" in out["content"]
        assert "skaffold-linux-amd64" in out["content"]

    def test_no_kubectl_apply(self):
        """No raw kubectl apply in CI output."""
        out = _gen({"method": "skaffold"})
        assert "kubectl apply" not in out["content"]

    def test_profile_flag(self):
        """Skaffold profile via --profile flag."""
        out = _gen({"method": "skaffold", "profile": "prod"})
        assert "--profile prod" in out["content"]

    def test_default_repo(self):
        """Skaffold --default-repo from config."""
        out = _gen({"method": "skaffold", "default_repo": "ghcr.io/org"})
        assert "--default-repo ghcr.io/org" in out["content"]

    def test_custom_filename(self):
        """Custom skaffold file path."""
        out = _gen({"method": "skaffold", "skaffold_file": "deploy/skaffold.yaml"})
        assert "--filename deploy/skaffold.yaml" in out["content"]

    def test_kubeconfig(self):
        """Deploy job sets up kubeconfig."""
        out = _gen({"method": "skaffold"})
        assert "KUBECONFIG" in out["content"]

    def test_push_only(self):
        """Deploy job only runs on push."""
        out = _gen({"method": "skaffold"})
        deploy_job = out["parsed"]["jobs"]["deploy"]
        assert deploy_job.get("if") == "github.event_name == 'push'"

    def test_valid_yaml(self):
        """Generated YAML is valid."""
        out = _gen({"method": "skaffold"})
        assert out["parsed"] is not None


# ═══════════════════════════════════════════════════════════════════
#  1.7 — K8s + CI/CD (Helm)
# ═══════════════════════════════════════════════════════════════════


class TestHelmDeploy:
    """Helm deploy CI job generation."""

    def test_helm_upgrade_install(self):
        """K8s + helm → CI has helm upgrade --install."""
        out = _gen({"method": "helm", "release_name": "myapp", "chart_path": "charts/myapp"})
        assert "helm upgrade --install myapp charts/myapp" in out["content"]

    def test_chart_path(self):
        """Chart path referenced."""
        out = _gen({"method": "helm", "chart_path": "charts/api"})
        assert "charts/api" in out["content"]

    def test_release_name(self):
        """Release name matches service."""
        out = _gen({"method": "helm", "release_name": "myapi"})
        assert "helm upgrade --install myapi" in out["content"]

    def test_values_file(self):
        """Values file per environment."""
        out = _gen({"method": "helm", "values_file": "values-prod.yaml"})
        assert "-f values-prod.yaml" in out["content"]

    def test_image_tag_set(self):
        """--set image.tag=${{ github.sha }}."""
        out = _gen({"method": "helm"})
        assert "--set image.tag=" in out["content"]
        assert "github.sha" in out["content"]

    def test_namespace(self):
        """Namespace via --namespace."""
        out = _gen({"method": "helm", "namespace": "prod"})
        assert "--namespace prod" in out["content"]

    def test_no_kubectl_apply(self):
        """No kubectl apply in CI output."""
        out = _gen({"method": "helm"})
        assert "kubectl apply" not in out["content"]

    def test_no_skaffold(self):
        """No skaffold in CI output."""
        out = _gen({"method": "helm"})
        assert "skaffold" not in out["content"].lower()

    def test_kubeconfig(self):
        """Deploy job sets up kubeconfig."""
        out = _gen({"method": "helm"})
        assert "KUBECONFIG" in out["content"]

    def test_push_only(self):
        """Deploy job only runs on push."""
        out = _gen({"method": "helm"})
        deploy_job = out["parsed"]["jobs"]["deploy"]
        assert deploy_job.get("if") == "github.event_name == 'push'"

    def test_valid_yaml(self):
        """Generated YAML is valid."""
        out = _gen({"method": "helm"})
        assert out["parsed"] is not None

    def test_depends_on_docker(self):
        """Deploy job depends on docker build."""
        out = _gen({"method": "helm", "needs": ["docker"]})
        deploy_job = out["parsed"]["jobs"]["deploy"]
        assert "docker" in deploy_job.get("needs", [])
