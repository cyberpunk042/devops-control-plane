"""
Integration tests for Terraform domain.

Covers milestones 0.6.6 (Wizard setup_terraform),
0.6.7 (Cleanup & error cases), 0.6.8 (Round-trip).

These tests use real file I/O but mock CLI availability.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.services.wizard_setup import setup_terraform
from src.core.services.wizard_setup import delete_generated_configs
from src.core.services.terraform_ops import terraform_status
from src.core.services.terraform_generate import generate_terraform


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════

_MOCK_CLI = {"available": False, "version": None}

pytestmark = pytest.mark.integration


def _status(project_root: Path) -> dict:
    """Call terraform_status with CLI mocked out."""
    with patch(
        "src.core.services.terraform_ops._terraform_available",
        return_value=_MOCK_CLI,
    ):
        return terraform_status(project_root)


def _write_files(root: Path, files: list[dict]) -> None:
    """Write generated files to disk."""
    for f in files:
        path = root / f["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f["content"])


# ═══════════════════════════════════════════════════════════════════
#  0.6.6 — Wizard: setup_terraform()
# ═══════════════════════════════════════════════════════════════════


class TestSetupTerraform:
    """setup_terraform() wizard integration."""

    def test_creates_four_files(self, tmp_path: Path):
        result = setup_terraform(tmp_path, {"provider": "aws"})
        assert result["ok"] is True
        assert (tmp_path / "terraform" / "main.tf").is_file()
        assert (tmp_path / "terraform" / "variables.tf").is_file()
        assert (tmp_path / "terraform" / "outputs.tf").is_file()
        assert (tmp_path / "terraform" / ".gitignore").is_file()

    def test_files_created_list(self, tmp_path: Path):
        result = setup_terraform(tmp_path, {"provider": "aws"})
        assert "files_created" in result
        assert len(result["files_created"]) == 4
        assert any("main.tf" in f for f in result["files_created"])
        assert any("variables.tf" in f for f in result["files_created"])

    def test_overwrite_guard_blocks(self, tmp_path: Path):
        setup_terraform(tmp_path, {"provider": "aws"})
        result = setup_terraform(tmp_path, {"provider": "aws"})
        assert result["ok"] is False
        assert "exist" in result["error"].lower() or "overwrite" in result["error"].lower()

    def test_overwrite_guard_allows(self, tmp_path: Path):
        setup_terraform(tmp_path, {"provider": "aws"})
        result = setup_terraform(tmp_path, {
            "provider": "aws", "overwrite": True,
        })
        assert result["ok"] is True

    def test_aws_provider_content(self, tmp_path: Path):
        setup_terraform(tmp_path, {"provider": "aws"})
        content = (tmp_path / "terraform" / "main.tf").read_text()
        assert "hashicorp/aws" in content

    def test_gcp_provider_content(self, tmp_path: Path):
        setup_terraform(tmp_path, {"provider": "google"})
        content = (tmp_path / "terraform" / "main.tf").read_text()
        assert "hashicorp/google" in content

    def test_azure_provider_content(self, tmp_path: Path):
        setup_terraform(tmp_path, {"provider": "azurerm"})
        content = (tmp_path / "terraform" / "main.tf").read_text()
        assert "hashicorp/azurerm" in content

    def test_s3_backend(self, tmp_path: Path):
        setup_terraform(tmp_path, {
            "provider": "aws", "backend": "s3",
        })
        content = (tmp_path / "terraform" / "main.tf").read_text()
        assert 'backend "s3"' in content

    def test_gcs_backend(self, tmp_path: Path):
        setup_terraform(tmp_path, {
            "provider": "google", "backend": "gcs",
        })
        content = (tmp_path / "terraform" / "main.tf").read_text()
        assert 'backend "gcs"' in content

    def test_local_backend(self, tmp_path: Path):
        setup_terraform(tmp_path, {
            "provider": "aws", "backend": "local",
        })
        content = (tmp_path / "terraform" / "main.tf").read_text()
        assert 'backend "local"' in content

    def test_round_trip_with_detection(self, tmp_path: Path):
        """Generate via wizard → detect → status confirms."""
        setup_terraform(tmp_path, {
            "provider": "aws", "backend": "s3",
        })
        status = _status(tmp_path)
        assert status["has_terraform"] is True
        assert any("aws" in p for p in status["providers"])
        assert status["backend"]["type"] == "s3"
        assert len(status["files"]) >= 3


# ═══════════════════════════════════════════════════════════════════
#  0.6.7 — Cleanup & Error Cases
# ═══════════════════════════════════════════════════════════════════


class TestTerraformCleanup:
    """Cleanup and error edge cases."""

    def test_delete_terraform_configs(self, tmp_path: Path):
        setup_terraform(tmp_path, {"provider": "aws"})
        assert (tmp_path / "terraform").is_dir()
        result = delete_generated_configs(tmp_path, "terraform")
        assert not (tmp_path / "terraform").is_dir()
        assert "terraform/" in result["deleted"]

    def test_delete_empty_project(self, tmp_path: Path):
        result = delete_generated_configs(tmp_path, "terraform")
        assert result["ok"] is True
        assert result["deleted"] == []

    def test_detection_without_cli(self, tmp_path: Path):
        """File-based detection works even when CLI is unavailable."""
        (tmp_path / "terraform").mkdir()
        (tmp_path / "terraform" / "main.tf").write_text(
            'provider "aws" { region = "us-east-1" }\n'
        )
        result = _status(tmp_path)
        assert result["has_terraform"] is True
        assert result["cli"]["available"] is False

    def test_invalid_tf_content(self, tmp_path: Path):
        """Invalid HCL-like content → detection returns result, no crash."""
        (tmp_path / "terraform").mkdir()
        (tmp_path / "terraform" / "main.tf").write_text(
            "this is not valid HCL { {{ invalid content\n"
        )
        result = _status(tmp_path)
        assert result["has_terraform"] is True
        # Resources may be empty since regex won't match, but no crash
        assert isinstance(result["resources"], list)

    def test_find_tf_root_none(self, tmp_path: Path):
        """No .tf files → detection returns has_terraform=False."""
        result = _status(tmp_path)
        assert result["has_terraform"] is False


# ═══════════════════════════════════════════════════════════════════
#  0.6.8 — Round-Trip Integration
# ═══════════════════════════════════════════════════════════════════


class TestTerraformRoundTrip:
    """Generate → detect → verify end-to-end."""

    def test_aws_s3_round_trip(self, tmp_path: Path):
        gen = generate_terraform(tmp_path, "aws", backend="s3",
                                  project_name="myapp")
        _write_files(tmp_path, gen["files"])
        status = _status(tmp_path)
        assert status["has_terraform"] is True
        assert "aws" in status["providers"] or any(
            "aws" in p for p in status["providers"]
        )
        assert status["backend"] is not None
        assert status["backend"]["type"] == "s3"
        assert len(status["files"]) >= 3  # main.tf, variables.tf, outputs.tf

    def test_gcp_gcs_round_trip(self, tmp_path: Path):
        gen = generate_terraform(tmp_path, "google", backend="gcs",
                                  project_name="myapp")
        _write_files(tmp_path, gen["files"])
        status = _status(tmp_path)
        assert status["has_terraform"] is True
        assert any("google" in p for p in status["providers"])
        assert status["backend"]["type"] == "gcs"

    def test_azure_round_trip(self, tmp_path: Path):
        gen = generate_terraform(tmp_path, "azurerm", backend="azurerm",
                                  project_name="myapp")
        _write_files(tmp_path, gen["files"])
        status = _status(tmp_path)
        assert status["has_terraform"] is True
        assert any("azurerm" in p for p in status["providers"])
        assert status["backend"]["type"] == "azurerm"

    def test_generate_cleanup_detect(self, tmp_path: Path):
        gen = generate_terraform(tmp_path, "aws", backend="local")
        _write_files(tmp_path, gen["files"])
        assert _status(tmp_path)["has_terraform"] is True
        delete_generated_configs(tmp_path, "terraform")
        assert _status(tmp_path)["has_terraform"] is False
