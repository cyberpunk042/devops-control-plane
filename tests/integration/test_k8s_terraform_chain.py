"""
Integration tests for K8s + Terraform chain (1.10).

Tests how K8s wizard state (namespace, services, provider) wires
into Terraform IaC generation via generate_terraform_k8s().

Spec grounding:
    TECHNOLOGY_SPEC §3.4 Facilitate = "Generate IaC from needs"
    PROJECT_SCOPE §4.5 Facilitate = "Generate Terraform configs from needs"
"""

from __future__ import annotations

import pytest
from pathlib import Path

from src.core.services.terraform_generate import generate_terraform_k8s

pytestmark = pytest.mark.integration


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _svc(name: str = "api", image: str = "myapp:latest", **kw) -> dict:
    """Build a service dict matching K8s wizard _services shape."""
    base = {"name": name, "image": image, "kind": "Deployment", "port": 8000}
    base.update(kw)
    return base


def _gen(tmp_path: Path, provider: str = "aws", **kw) -> dict:
    """Call generate_terraform_k8s with reasonable defaults."""
    return generate_terraform_k8s(
        tmp_path,
        provider,
        **kw,
    )


def _file_content(result: dict, filename: str) -> str:
    """Extract content for a given filename from result files."""
    for f in result.get("files", []):
        if f["path"].endswith(filename):
            return f["content"]
    return ""


# ═══════════════════════════════════════════════════════════════════
#  Provider routing
# ═══════════════════════════════════════════════════════════════════


class TestProviderRouting:
    """Correct cloud resources generated per provider."""

    def test_aws_eks(self, tmp_path: Path):
        """provider=aws → EKS cluster + ECR registry."""
        r = _gen(tmp_path, "aws", services=[_svc()])
        assert r["ok"] is True
        main = _file_content(r, "main.tf")
        assert "aws_eks_cluster" in main
        assert "aws_ecr_repository" in main

    def test_google_gke(self, tmp_path: Path):
        """provider=google → GKE cluster + Artifact Registry."""
        r = _gen(tmp_path, "google", services=[_svc()])
        assert r["ok"] is True
        main = _file_content(r, "main.tf")
        assert "google_container_cluster" in main
        assert "google_artifact_registry_repository" in main

    def test_azurerm_aks(self, tmp_path: Path):
        """provider=azurerm → AKS cluster + ACR."""
        r = _gen(tmp_path, "azurerm", services=[_svc()])
        assert r["ok"] is True
        main = _file_content(r, "main.tf")
        assert "azurerm_kubernetes_cluster" in main
        assert "azurerm_container_registry" in main

    def test_unknown_provider_error(self, tmp_path: Path):
        """Unknown provider → error dict, no crash."""
        r = _gen(tmp_path, "nonsense")
        assert "error" in r
        assert r.get("ok") is not True


# ═══════════════════════════════════════════════════════════════════
#  Namespace flow
# ═══════════════════════════════════════════════════════════════════


class TestNamespaceFlow:
    """K8s namespace → Terraform kubernetes_namespace resource."""

    def test_namespace_creates_resource(self, tmp_path: Path):
        """K8s namespace → kubernetes_namespace in k8s.tf, default in variables.tf."""
        r = _gen(tmp_path, "aws", namespace="production")
        assert r["ok"] is True
        k8s_tf = _file_content(r, "k8s.tf")
        assert "kubernetes_namespace" in k8s_tf
        assert "var.namespace" in k8s_tf
        # The literal value is the default in variables.tf
        variables = _file_content(r, "variables.tf")
        assert "production" in variables

    def test_no_namespace_no_resource(self, tmp_path: Path):
        """No namespace → no namespace resource in k8s.tf."""
        r = _gen(tmp_path, "aws", namespace="")
        assert r["ok"] is True
        k8s_tf = _file_content(r, "k8s.tf")
        assert "kubernetes_namespace" not in k8s_tf


# ═══════════════════════════════════════════════════════════════════
#  Service → Registry
# ═══════════════════════════════════════════════════════════════════


class TestServiceRegistry:
    """Services with images → container registry resource."""

    def test_services_create_registry(self, tmp_path: Path):
        """Services with images → registry resource in main.tf."""
        r = _gen(tmp_path, "aws", services=[_svc()])
        main = _file_content(r, "main.tf")
        assert "aws_ecr_repository" in main

    def test_no_services_no_registry(self, tmp_path: Path):
        """No services → no registry resource."""
        r = _gen(tmp_path, "aws", services=[])
        assert r["ok"] is True
        main = _file_content(r, "main.tf")
        assert "ecr_repository" not in main.lower()

    def test_multiple_services_single_registry(self, tmp_path: Path):
        """Multiple services → one registry resource (not one per service)."""
        r = _gen(tmp_path, "aws", services=[
            _svc("api", "api:latest"),
            _svc("web", "web:latest"),
            _svc("worker", "worker:latest"),
        ])
        main = _file_content(r, "main.tf")
        # Should have exactly one registry resource, not three
        assert main.count("aws_ecr_repository") == 1


# ═══════════════════════════════════════════════════════════════════
#  Outputs for K8s
# ═══════════════════════════════════════════════════════════════════


class TestOutputs:
    """Cross-domain outputs for K8s to consume."""

    def test_cluster_endpoint_output(self, tmp_path: Path):
        """cluster_endpoint output always present."""
        r = _gen(tmp_path, "aws")
        outputs = _file_content(r, "outputs.tf")
        assert "cluster_endpoint" in outputs

    def test_cluster_ca_output(self, tmp_path: Path):
        """cluster_ca_certificate output always present."""
        r = _gen(tmp_path, "aws")
        outputs = _file_content(r, "outputs.tf")
        assert "cluster_ca_certificate" in outputs

    def test_kubeconfig_command_output(self, tmp_path: Path):
        """kubeconfig_command output always present."""
        r = _gen(tmp_path, "aws")
        outputs = _file_content(r, "outputs.tf")
        assert "kubeconfig_command" in outputs

    def test_kubeconfig_command_provider_specific(self, tmp_path: Path):
        """kubeconfig_command uses provider-specific CLI."""
        # AWS uses 'aws eks update-kubeconfig'
        r_aws = _gen(tmp_path, "aws")
        out_aws = _file_content(r_aws, "outputs.tf")
        assert "aws eks" in out_aws

        # GCP uses 'gcloud container clusters get-credentials'
        r_gcp = _gen(tmp_path, "google")
        out_gcp = _file_content(r_gcp, "outputs.tf")
        assert "gcloud" in out_gcp

    def test_registry_url_when_services(self, tmp_path: Path):
        """registry_url output present when services have images."""
        r = _gen(tmp_path, "aws", services=[_svc()])
        outputs = _file_content(r, "outputs.tf")
        assert "registry_url" in outputs

    def test_no_registry_url_without_services(self, tmp_path: Path):
        """No registry_url output when no services."""
        r = _gen(tmp_path, "aws", services=[])
        outputs = _file_content(r, "outputs.tf")
        assert "registry_url" not in outputs


# ═══════════════════════════════════════════════════════════════════
#  Variables
# ═══════════════════════════════════════════════════════════════════


class TestVariables:
    """Variables propagated from wizard state."""

    def test_namespace_variable(self, tmp_path: Path):
        """namespace variable in variables.tf."""
        r = _gen(tmp_path, "aws", namespace="staging")
        variables = _file_content(r, "variables.tf")
        assert "namespace" in variables
        assert "staging" in variables

    def test_node_count_variable(self, tmp_path: Path):
        """node_count variable with default."""
        r = _gen(tmp_path, "aws", node_count=3)
        variables = _file_content(r, "variables.tf")
        assert "node_count" in variables

    def test_node_size_variable(self, tmp_path: Path):
        """node_size variable with provider-appropriate default."""
        r = _gen(tmp_path, "aws")
        variables = _file_content(r, "variables.tf")
        assert "node_size" in variables
        # AWS default should be a t3/t2 instance type
        assert "t3" in variables or "t2" in variables

    def test_project_name_variable(self, tmp_path: Path):
        """project_name variable propagated."""
        r = _gen(tmp_path, "aws", project_name="my-project")
        variables = _file_content(r, "variables.tf")
        assert "project" in variables
        assert "my-project" in variables

    def test_region_variable(self, tmp_path: Path):
        """region variable with provider default."""
        r = _gen(tmp_path, "aws")
        variables = _file_content(r, "variables.tf")
        assert "region" in variables
        assert "us-east-1" in variables


# ═══════════════════════════════════════════════════════════════════
#  File structure
# ═══════════════════════════════════════════════════════════════════


class TestFileStructure:
    """Correct files generated with expected paths."""

    def test_main_tf(self, tmp_path: Path):
        """terraform/main.tf generated."""
        r = _gen(tmp_path, "aws")
        paths = [f["path"] for f in r["files"]]
        assert "terraform/main.tf" in paths

    def test_variables_tf(self, tmp_path: Path):
        """terraform/variables.tf generated."""
        r = _gen(tmp_path, "aws")
        paths = [f["path"] for f in r["files"]]
        assert "terraform/variables.tf" in paths

    def test_outputs_tf(self, tmp_path: Path):
        """terraform/outputs.tf generated."""
        r = _gen(tmp_path, "aws")
        paths = [f["path"] for f in r["files"]]
        assert "terraform/outputs.tf" in paths

    def test_k8s_tf(self, tmp_path: Path):
        """terraform/k8s.tf generated."""
        r = _gen(tmp_path, "aws", namespace="default")
        paths = [f["path"] for f in r["files"]]
        assert "terraform/k8s.tf" in paths

    def test_gitignore(self, tmp_path: Path):
        """terraform/.gitignore generated."""
        r = _gen(tmp_path, "aws")
        paths = [f["path"] for f in r["files"]]
        assert "terraform/.gitignore" in paths

    def test_generated_file_model(self, tmp_path: Path):
        """Files use GeneratedFile dict shape (path, content, reason)."""
        r = _gen(tmp_path, "aws")
        for f in r["files"]:
            assert "path" in f
            assert "content" in f
            assert "reason" in f

    def test_all_content_has_terraform_keyword(self, tmp_path: Path):
        """All .tf files contain 'terraform' or valid HCL constructs."""
        r = _gen(tmp_path, "aws", namespace="prod", services=[_svc()])
        for f in r["files"]:
            if f["path"].endswith(".tf"):
                content = f["content"]
                # HCL files should have blocks: resource, variable, output, provider, terraform
                has_hcl = any(
                    kw in content
                    for kw in ("resource ", "variable ", "output ", "provider ", "terraform {")
                )
                assert has_hcl, f"No HCL construct in {f['path']}"

    def test_backend_flows(self, tmp_path: Path):
        """Backend parameter flows into main.tf."""
        r = _gen(tmp_path, "aws", backend="s3")
        main = _file_content(r, "main.tf")
        assert 's3' in main
