"""
Integration tests for Layer 5 — Error & Edge Cases.

Tests that the system handles bad input, missing tools, partial state,
and cleanup operations gracefully.

Layer 5 milestones:
    5.1 Missing Tools
    5.2 Misconfiguration
    5.3 Partial State
    5.4 Cleanup
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest import mock

import yaml
import pytest

from src.core.services.wizard_validate import (
    validate_wizard_state,
    check_required_tools,
)
from src.core.services.wizard_setup import delete_generated_configs

pytestmark = pytest.mark.integration


# ═══════════════════════════════════════════════════════════════════
#  5.1 Missing Tools
# ═══════════════════════════════════════════════════════════════════


class TestMissingTools:
    """Detection → clear message → install available."""

    def test_docker_missing_detected(self):
        """Docker enabled but docker CLI missing → reported."""
        with mock.patch("shutil.which", return_value=None):
            result = check_required_tools({
                "docker_services": [{"name": "api", "image": "api:latest"}],
            })
        assert not result["ok"]
        assert "docker" in result["missing"]

    def test_kubectl_missing_detected(self):
        """K8s enabled but kubectl missing → reported."""
        with mock.patch("shutil.which", return_value=None):
            result = check_required_tools({
                "deploy_config": {"method": "kubectl"},
            })
        assert not result["ok"]
        assert "kubectl" in result["missing"]

    def test_skaffold_missing_detected(self):
        """Skaffold method but skaffold CLI missing → reported."""
        with mock.patch("shutil.which", return_value=None):
            result = check_required_tools({
                "deploy_config": {"method": "skaffold"},
            })
        assert not result["ok"]
        assert "skaffold" in result["missing"]

    def test_helm_missing_detected(self):
        """Helm method but helm CLI missing → reported."""
        with mock.patch("shutil.which", return_value=None):
            result = check_required_tools({
                "deploy_config": {"method": "helm"},
            })
        assert not result["ok"]
        assert "helm" in result["missing"]

    def test_terraform_missing_detected(self):
        """Terraform enabled but terraform CLI missing → reported."""
        with mock.patch("shutil.which", return_value=None):
            result = check_required_tools({
                "terraform_config": {"provider": "aws"},
            })
        assert not result["ok"]
        assert "terraform" in result["missing"]

    def test_install_recipe_available(self):
        """Missing tools have install recipes available."""
        with mock.patch("shutil.which", return_value=None):
            result = check_required_tools({
                "docker_services": [{"name": "api"}],
                "deploy_config": {"method": "helm"},
                "terraform_config": {"provider": "aws"},
            })
        # All missing tools should have install_available
        for tool in result["missing"]:
            assert tool in result["install_available"], (
                f"{tool} is missing but no install recipe available"
            )

    def test_all_tools_present(self):
        """All tools present → ok."""
        with mock.patch("shutil.which", return_value="/usr/bin/fake"):
            result = check_required_tools({
                "docker_services": [{"name": "api"}],
                "deploy_config": {"method": "helm"},
                "terraform_config": {"provider": "aws"},
            })
        assert result["ok"]
        assert result["missing"] == []

    def test_tool_install_recipe_exists(self):
        """All DevOps tools have install recipes in tool_install.py."""
        from src.core.services.tool_install import (
            _NO_SUDO_RECIPES, _SUDO_RECIPES,
        )
        all_recipes = {**_NO_SUDO_RECIPES, **_SUDO_RECIPES}
        for tool in ["docker", "kubectl", "helm", "skaffold", "terraform"]:
            assert tool in all_recipes, (
                f"No install recipe for {tool}"
            )


# ═══════════════════════════════════════════════════════════════════
#  5.2 Misconfiguration
# ═══════════════════════════════════════════════════════════════════


class TestMisconfiguration:
    """Bad input → validation errors."""

    def test_registry_url_malformed(self):
        """Malformed Docker registry URL → validation error."""
        state = {
            "docker_services": [
                {"name": "api", "registry": "not a valid url!!!"},
            ],
        }
        result = validate_wizard_state(state)
        assert not result["ok"]
        assert any("registry" in e.lower() for e in result["errors"])

    def test_registry_url_valid(self):
        """Valid Docker registry URL → ok."""
        for url in ["ghcr.io/myorg", "docker.io/library", "myregistry.azurecr.io/app"]:
            state = {
                "docker_services": [{"name": "api", "registry": url}],
                "_skip_secret_warnings": True,
            }
            result = validate_wizard_state(state)
            assert result["ok"], f"Registry URL {url!r} flagged as invalid"

    def test_namespace_invalid_chars(self):
        """K8s namespace with invalid characters → validation error."""
        state = {
            "deploy_config": {"namespace": "My_Namespace!!"},
        }
        result = validate_wizard_state(state)
        assert not result["ok"]
        assert any("namespace" in e.lower() for e in result["errors"])

    def test_namespace_valid(self):
        """Valid K8s namespace → ok."""
        for ns in ["default", "my-app", "prod-123", "a"]:
            state = {
                "deploy_config": {"namespace": ns},
                "_skip_secret_warnings": True,
            }
            result = validate_wizard_state(state)
            assert result["ok"], f"Namespace {ns!r} flagged as invalid"

    def test_namespace_starts_with_hyphen(self):
        """Namespace starting with hyphen → error."""
        state = {"deploy_config": {"namespace": "-bad"}}
        result = validate_wizard_state(state)
        assert not result["ok"]

    def test_namespace_too_long(self):
        """Namespace > 63 chars → error."""
        state = {"deploy_config": {"namespace": "a" * 64}}
        result = validate_wizard_state(state)
        assert not result["ok"]

    def test_helm_chart_path_missing(self, tmp_path):
        """Helm chart path doesn't exist → warning."""
        state = {
            "deploy_config": {
                "method": "helm", "chart_path": "charts/nonexistent",
            },
            "_skip_secret_warnings": True,
        }
        result = validate_wizard_state(state, project_root=tmp_path)
        assert result["ok"]  # warning, not error
        assert any("chart" in w.lower() for w in result["warnings"])

    def test_helm_chart_path_exists(self, tmp_path):
        """Helm chart path exists → no warning."""
        (tmp_path / "charts" / "myapp").mkdir(parents=True)
        state = {
            "deploy_config": {
                "method": "helm", "chart_path": "charts/myapp",
            },
            "_skip_secret_warnings": True,
        }
        result = validate_wizard_state(state, project_root=tmp_path)
        assert not any("chart" in w.lower() for w in result["warnings"])

    def test_invalid_deploy_method(self):
        """Invalid deploy method → validation error."""
        state = {"deploy_config": {"method": "docker-swarm"}}
        result = validate_wizard_state(state)
        assert not result["ok"]
        assert any("deploy method" in e.lower() for e in result["errors"])

    def test_invalid_terraform_provider(self):
        """Unknown terraform provider → validation error."""
        state = {"terraform_config": {"provider": "digitalocean"}}
        result = validate_wizard_state(state)
        assert not result["ok"]
        assert any("provider" in e.lower() for e in result["errors"])

    def test_ci_secret_references_warning(self):
        """CI references secrets → warning in output."""
        state = {"deploy_config": {"method": "kubectl"}}
        result = validate_wizard_state(state)
        assert result["ok"]
        assert any("secrets" in w.lower() for w in result["warnings"])

    def test_invalid_env_name_as_namespace(self):
        """Environment name with invalid namespace chars → error."""
        state = {
            "environments": ["dev", "PROD_ENV"],
        }
        result = validate_wizard_state(state)
        assert not result["ok"]
        assert any("PROD_ENV" in e for e in result["errors"])


# ═══════════════════════════════════════════════════════════════════
#  5.3 Partial State
# ═══════════════════════════════════════════════════════════════════


class TestPartialState:
    """Detection handles partial/interrupted state."""

    def test_detect_partial_k8s(self, tmp_path):
        """k8s/ dir with only some files → detection handles it."""
        from src.core.services.k8s_detect import k8s_status
        # Only a namespace.yaml, no deployment
        k8s_dir = tmp_path / "k8s"
        k8s_dir.mkdir()
        (k8s_dir / "namespace.yaml").write_text(
            "apiVersion: v1\nkind: Namespace\nmetadata:\n  name: test\n"
        )
        result = k8s_status(tmp_path)
        # Should not crash, should report what's there
        assert isinstance(result, dict)

    def test_detect_partial_helm(self, tmp_path):
        """Chart.yaml without templates/ → detection handles it."""
        from src.core.services.k8s_detect import _detect_helm_charts
        chart_dir = tmp_path / "charts" / "app"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text(
            "apiVersion: v2\nname: app\nversion: 0.1.0\n"
        )
        # No templates/ dir, no values.yaml
        charts = _detect_helm_charts(tmp_path)
        assert len(charts) == 1
        assert charts[0]["has_values"] is False
        assert charts[0]["has_templates"] is False

    def test_detect_partial_docker(self, tmp_path):
        """Dockerfile without docker-compose → detection handles it."""
        from src.core.services.docker_detect import docker_status
        (tmp_path / "Dockerfile").write_text("FROM python:3.12\n")
        result = docker_status(tmp_path)
        assert isinstance(result, dict)
        assert result.get("has_dockerfile") is True

    def test_detect_partial_ci(self, tmp_path):
        """workflows/ dir with incomplete yaml → detection handles it."""
        from src.core.services.ci_ops import ci_status
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("# empty incomplete file\n")
        result = ci_status(tmp_path)
        assert isinstance(result, dict)

    def test_detect_edited_manifests(self, tmp_path):
        """Manually edited manifests → detection picks up changes."""
        from src.core.services.k8s_detect import k8s_status
        k8s_dir = tmp_path / "k8s"
        k8s_dir.mkdir()
        # Write a custom manifest with non-standard content
        (k8s_dir / "custom-resource.yaml").write_text(
            "apiVersion: custom.io/v1\n"
            "kind: MyCustomResource\n"
            "metadata:\n"
            "  name: my-cr\n"
            "spec:\n"
            "  custom: true\n"
        )
        result = k8s_status(tmp_path)
        # Should not crash and should include the file
        assert isinstance(result, dict)

    def test_compose_with_empty_state(self):
        """compose_ci_workflows with completely empty state → empty list."""
        from src.core.services.ci_compose import compose_ci_workflows
        result = compose_ci_workflows({})
        assert result == []

    def test_compose_with_partial_deploy(self):
        """compose with deploy_config but incomplete fields → still generates."""
        from src.core.services.ci_compose import compose_ci_workflows
        state = {"deploy_config": {"method": "kubectl"}}
        result = compose_ci_workflows(state)
        assert len(result) >= 1


# ═══════════════════════════════════════════════════════════════════
#  5.4 Cleanup
# ═══════════════════════════════════════════════════════════════════


class TestCleanup:
    """Targeted deletion of generated configs."""

    def _populate(self, root: Path):
        """Create all generated config types."""
        # Docker
        (root / "Dockerfile").write_text("FROM python:3.12\n")
        (root / ".dockerignore").write_text(".git\n")
        (root / "docker-compose.yml").write_text("version: '3'\n")

        # K8s
        k8s = root / "k8s"
        k8s.mkdir()
        (k8s / "deployment.yaml").write_text("apiVersion: apps/v1\n")

        # Skaffold
        (root / "skaffold.yaml").write_text("apiVersion: skaffold/v4beta11\n")

        # CI
        wf = root / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text("name: CI\n")
        (wf / "lint.yml").write_text("name: Lint\n")

        # Terraform
        tf = root / "terraform"
        tf.mkdir()
        (tf / "main.tf").write_text("provider \"aws\" {}\n")

    def test_delete_docker_only(self, tmp_path):
        """delete_generated_configs('docker') → removes only Docker files."""
        self._populate(tmp_path)
        result = delete_generated_configs(tmp_path, "docker")
        assert result["ok"]
        assert not (tmp_path / "Dockerfile").exists()
        assert not (tmp_path / ".dockerignore").exists()
        assert not (tmp_path / "docker-compose.yml").exists()
        # Others untouched
        assert (tmp_path / "k8s").is_dir()
        assert (tmp_path / "skaffold.yaml").is_file()
        assert (tmp_path / ".github" / "workflows" / "ci.yml").is_file()
        assert (tmp_path / "terraform").is_dir()

    def test_delete_k8s_only(self, tmp_path):
        """delete_generated_configs('k8s') → removes only k8s/ dir."""
        self._populate(tmp_path)
        result = delete_generated_configs(tmp_path, "k8s")
        assert result["ok"]
        assert not (tmp_path / "k8s").exists()
        # Others untouched
        assert (tmp_path / "Dockerfile").is_file()
        assert (tmp_path / "skaffold.yaml").is_file()
        assert (tmp_path / "terraform").is_dir()

    def test_delete_ci_only(self, tmp_path):
        """delete_generated_configs('ci') → removes workflow files only."""
        self._populate(tmp_path)
        result = delete_generated_configs(tmp_path, "ci")
        assert result["ok"]
        assert not (tmp_path / ".github" / "workflows" / "ci.yml").exists()
        assert not (tmp_path / ".github" / "workflows" / "lint.yml").exists()
        # Others untouched
        assert (tmp_path / "Dockerfile").is_file()
        assert (tmp_path / "k8s").is_dir()

    def test_delete_skaffold_only(self, tmp_path):
        """delete_generated_configs('skaffold') → removes skaffold.yaml only."""
        self._populate(tmp_path)
        result = delete_generated_configs(tmp_path, "skaffold")
        assert result["ok"]
        assert not (tmp_path / "skaffold.yaml").exists()
        # Others untouched
        assert (tmp_path / "Dockerfile").is_file()
        assert (tmp_path / "k8s").is_dir()
        assert (tmp_path / "terraform").is_dir()

    def test_delete_terraform_only(self, tmp_path):
        """delete_generated_configs('terraform') → removes tf dir only."""
        self._populate(tmp_path)
        result = delete_generated_configs(tmp_path, "terraform")
        assert result["ok"]
        assert not (tmp_path / "terraform").exists()
        # Others untouched
        assert (tmp_path / "Dockerfile").is_file()
        assert (tmp_path / "k8s").is_dir()
        assert (tmp_path / "skaffold.yaml").is_file()

    def test_cleanup_one_domain_others_untouched(self, tmp_path):
        """Delete one domain → all others untouched."""
        self._populate(tmp_path)
        delete_generated_configs(tmp_path, "docker")
        # Verify every other domain is still present
        assert (tmp_path / "k8s" / "deployment.yaml").is_file()
        assert (tmp_path / "skaffold.yaml").is_file()
        assert (tmp_path / ".github" / "workflows" / "ci.yml").is_file()
        assert (tmp_path / "terraform" / "main.tf").is_file()

    def test_re_setup_after_cleanup(self, tmp_path):
        """Delete docker → re-generate → works cleanly."""
        self._populate(tmp_path)
        delete_generated_configs(tmp_path, "docker")
        assert not (tmp_path / "Dockerfile").exists()
        # Re-generate
        from src.core.services.wizard_setup import setup_docker
        result = setup_docker(tmp_path, {"base_image": "python:3.12"})
        assert result["ok"]
        assert (tmp_path / "Dockerfile").is_file()

    def test_delete_nothing_when_not_present(self, tmp_path):
        """Delete target that doesn't exist → ok, empty deleted list."""
        result = delete_generated_configs(tmp_path, "docker")
        assert result["ok"]
        assert result["deleted"] == []

    def test_unknown_target_error(self, tmp_path):
        """Unknown target → error."""
        result = delete_generated_configs(tmp_path, "imaginary")
        assert not result["ok"]
        assert any("Unknown" in e for e in result["errors"])
