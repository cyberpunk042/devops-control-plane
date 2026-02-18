"""
Integration tests for Docker + Terraform chain (1.14).

Tests the cross-domain bridge: Terraform provisions container
registries (ECR/GAR/ACR) → Docker CI gets matching registry config.

Spec grounding:
    Terraform provisions container registries → Docker CI needs matching login.
    generate_terraform_k8s() outputs registry_url.
    generate_docker_ci() accepts registry_type.
"""

from __future__ import annotations

import pytest

from src.core.services.terraform_generate import terraform_to_docker_registry

pytestmark = pytest.mark.integration


# ═══════════════════════════════════════════════════════════════════
#  Provider → registry mapping
# ═══════════════════════════════════════════════════════════════════


class TestProviderRegistryMapping:
    """Terraform provider maps to Docker registry config."""

    def test_aws_ecr_registry(self):
        """AWS → ECR registry type."""
        result = terraform_to_docker_registry("aws", project_name="myapp")
        assert result["registry_type"] == "ecr"
        assert result["ok"] is True

    def test_google_gar_registry(self):
        """Google → GAR registry type."""
        result = terraform_to_docker_registry("google", project_name="myapp")
        assert result["registry_type"] == "gar"
        assert result["ok"] is True

    def test_azure_acr_registry(self):
        """Azure → ACR registry type."""
        result = terraform_to_docker_registry("azurerm", project_name="myapp")
        assert result["registry_type"] == "acr"
        assert result["ok"] is True

    def test_registry_url_present(self):
        """Returns registry URL pattern from Terraform output."""
        for provider in ("aws", "google", "azurerm"):
            result = terraform_to_docker_registry(provider, project_name="myapp")
            assert "registry_url" in result
            assert result["registry_url"], f"Empty registry URL for {provider}"

    def test_unknown_provider(self):
        """Unknown provider → error or empty result."""
        result = terraform_to_docker_registry("unknown", project_name="myapp")
        assert result.get("ok") is False or result.get("registry_type") == ""


# ═══════════════════════════════════════════════════════════════════
#  Docker CI integration
# ═══════════════════════════════════════════════════════════════════


class TestDockerCiIntegration:
    """Bridge output feeds into Docker CI workflow generation."""

    def test_aws_ecr_url_format(self):
        """AWS ECR URL includes account/region pattern."""
        result = terraform_to_docker_registry("aws", project_name="myapp")
        url = result["registry_url"]
        # ECR URLs look like: <account>.dkr.ecr.<region>.amazonaws.com
        assert "ecr" in url.lower() or "amazonaws" in url.lower()

    def test_google_gar_url_format(self):
        """Google GAR URL includes pkg.dev pattern."""
        result = terraform_to_docker_registry("google", project_name="myapp")
        url = result["registry_url"]
        assert "pkg.dev" in url.lower() or "gcr.io" in url.lower()

    def test_azure_acr_url_format(self):
        """Azure ACR URL includes azurecr.io pattern."""
        result = terraform_to_docker_registry("azurerm", project_name="myapp")
        url = result["registry_url"]
        assert "azurecr.io" in url.lower()

    def test_credentials_mapping_aws(self):
        """AWS credentials mapped to correct secrets."""
        result = terraform_to_docker_registry("aws", project_name="myapp")
        creds = result.get("credentials", {})
        assert "AWS_ACCESS_KEY_ID" in creds or "aws" in str(creds).lower()

    def test_credentials_mapping_google(self):
        """Google credentials mapped to correct secrets."""
        result = terraform_to_docker_registry("google", project_name="myapp")
        creds = result.get("credentials", {})
        assert "GOOGLE" in str(creds).upper() or "GCP" in str(creds).upper()

    def test_credentials_mapping_azure(self):
        """Azure credentials mapped to correct secrets."""
        result = terraform_to_docker_registry("azurerm", project_name="myapp")
        creds = result.get("credentials", {})
        assert "ACR" in str(creds).upper() or "AZURE" in str(creds).upper()

    def test_login_action_present(self):
        """Registry config includes login action or command."""
        for provider in ("aws", "google", "azurerm"):
            result = terraform_to_docker_registry(provider, project_name="myapp")
            assert "login_step" in result or "login_action" in result


# ═══════════════════════════════════════════════════════════════════
#  Cross-domain outputs
# ═══════════════════════════════════════════════════════════════════


class TestCrossDomainOutputs:
    """Terraform output → Docker push target."""

    def test_registry_url_as_push_target(self):
        """registry_url from Terraform → Docker push target."""
        for provider in ("aws", "google", "azurerm"):
            result = terraform_to_docker_registry(provider, project_name="myapp")
            assert result["registry_url"]
            # URL should be usable as docker push target
            assert "/" in result["registry_url"] or "." in result["registry_url"]

    def test_project_name_in_url(self):
        """Project name appears in registry URL."""
        result = terraform_to_docker_registry("aws", project_name="myapp")
        assert "myapp" in result["registry_url"]

    def test_region_param_flows(self):
        """Optional region param flows into URL where applicable."""
        result = terraform_to_docker_registry(
            "google", project_name="myapp", region="us-central1"
        )
        assert "us-central1" in result["registry_url"]
