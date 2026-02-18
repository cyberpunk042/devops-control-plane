"""
Unit tests for Terraform detection and generation.

Covers milestones 0.6.1 (Detection) and 0.6.2 (Generation).
Detection tests mock _terraform_available so they run without the CLI.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.services.terraform_ops import (
    terraform_status,
    _classify_tf_file,
    _find_tf_root,
)
from src.core.services.terraform_generate import generate_terraform


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════

_MOCK_CLI = {"available": False, "version": None}


def _status(project_root: Path) -> dict:
    """Call terraform_status with CLI mocked out."""
    with patch(
        "src.core.services.terraform_ops._terraform_available",
        return_value=_MOCK_CLI,
    ):
        return terraform_status(project_root)


def _write_tf(path: Path, content: str = "# empty\n") -> None:
    """Write a .tf file, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# ═══════════════════════════════════════════════════════════════════
#  0.6.1 — Detection: terraform_status()
# ═══════════════════════════════════════════════════════════════════


class TestTerraformStatusEmpty:
    """Empty project → no Terraform detected."""

    def test_empty_project(self, tmp_path: Path):
        result = _status(tmp_path)
        assert result["has_terraform"] is False
        assert result["files"] == []
        assert result["providers"] == []
        assert result["modules"] == []
        assert result["resources"] == []
        assert result["backend"] is None
        assert result["initialized"] is False

    def test_return_shape(self, tmp_path: Path):
        """All required keys are present even on empty project."""
        result = _status(tmp_path)
        required_keys = {
            "has_terraform", "cli", "root", "files", "providers",
            "modules", "resources", "backend", "initialized",
        }
        assert required_keys.issubset(result.keys()), (
            f"Missing keys: {required_keys - result.keys()}"
        )


class TestTerraformStatusRootDiscovery:
    """_find_tf_root and root directory detection."""

    def test_tf_in_project_root(self, tmp_path: Path):
        _write_tf(tmp_path / "main.tf")
        result = _status(tmp_path)
        assert result["has_terraform"] is True
        assert result["root"] == "."

    def test_terraform_directory(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        result = _status(tmp_path)
        assert result["has_terraform"] is True
        assert result["root"] == "terraform"

    def test_infra_directory(self, tmp_path: Path):
        _write_tf(tmp_path / "infra" / "main.tf")
        result = _status(tmp_path)
        assert result["has_terraform"] is True
        assert result["root"] == "infra"

    def test_infrastructure_directory(self, tmp_path: Path):
        _write_tf(tmp_path / "infrastructure" / "main.tf")
        result = _status(tmp_path)
        assert result["has_terraform"] is True
        assert result["root"] == "infrastructure"

    def test_terraform_preferred_over_root(self, tmp_path: Path):
        """terraform/ is checked before project root in priority order."""
        _write_tf(tmp_path / "main.tf")
        _write_tf(tmp_path / "terraform" / "main.tf")
        result = _status(tmp_path)
        assert result["root"] == "terraform"

    def test_no_tf_files_anywhere(self, tmp_path: Path):
        """_find_tf_root returns None when no .tf files exist."""
        result = _find_tf_root(tmp_path)
        assert result is None


class TestTerraformStatusInitialized:
    """Initialized detection (.terraform directory)."""

    def test_initialized_true(self, tmp_path: Path):
        tf_dir = tmp_path / "terraform"
        _write_tf(tf_dir / "main.tf")
        (tf_dir / ".terraform").mkdir()
        result = _status(tmp_path)
        assert result["initialized"] is True

    def test_initialized_false(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        result = _status(tmp_path)
        assert result["initialized"] is False


class TestTerraformStatusSkipDirs:
    """Skip directories are not scanned."""

    def test_skip_node_modules(self, tmp_path: Path):
        _write_tf(tmp_path / "node_modules" / "main.tf")
        result = _status(tmp_path)
        assert result["has_terraform"] is False

    def test_skip_venv(self, tmp_path: Path):
        _write_tf(tmp_path / ".venv" / "main.tf")
        result = _status(tmp_path)
        assert result["has_terraform"] is False

    def test_skip_dot_terraform(self, tmp_path: Path):
        """Files inside .terraform/ are not listed as project tf files."""
        tf_dir = tmp_path / "terraform"
        _write_tf(tf_dir / "main.tf")
        _write_tf(tf_dir / ".terraform" / "providers.tf")
        result = _status(tmp_path)
        tf_paths = [f["path"] for f in result["files"]]
        assert not any(".terraform" in p for p in tf_paths)


class TestClassifyTfFile:
    """_classify_tf_file returns correct type strings."""

    @pytest.mark.parametrize("filename,expected", [
        ("main.tf", "main"),
        ("variables.tf", "variables"),
        ("vars.tf", "variables"),
        ("outputs.tf", "outputs"),
        ("providers.tf", "providers"),
        ("provider.tf", "providers"),
        ("backend.tf", "backend"),
        ("state.tf", "backend"),
        ("terraform.tf", "versions"),
        ("versions.tf", "versions"),
        ("data.tf", "data"),
        ("datasources.tf", "data"),
        ("modules_vpc.tf", "modules"),
        ("random.tf", "other"),
        ("networking.tf", "other"),
    ])
    def test_classification(self, filename: str, expected: str):
        assert _classify_tf_file(filename) == expected


class TestTerraformStatusParsing:
    """Provider, module, resource, backend parsing."""

    def test_provider_block_parsed(self, tmp_path: Path):
        _write_tf(tmp_path / "main.tf", textwrap.dedent("""\
            provider "aws" {
              region = "us-east-1"
            }
        """))
        result = _status(tmp_path)
        assert "aws" in result["providers"]

    def test_required_providers_parsed(self, tmp_path: Path):
        _write_tf(tmp_path / "main.tf", textwrap.dedent("""\
            terraform {
              required_providers {
                aws = {
                  source  = "hashicorp/aws"
                  version = "~> 5.0"
                }
              }
            }
        """))
        result = _status(tmp_path)
        assert "hashicorp/aws" in result["providers"]

    def test_multiple_providers_sorted(self, tmp_path: Path):
        _write_tf(tmp_path / "main.tf", textwrap.dedent("""\
            provider "google" {}
            provider "aws" {}
        """))
        result = _status(tmp_path)
        assert result["providers"] == ["aws", "google"]

    def test_module_parsed(self, tmp_path: Path):
        _write_tf(tmp_path / "main.tf", textwrap.dedent("""\
            module "vpc" {
              source = "./modules/vpc"
            }
        """))
        result = _status(tmp_path)
        assert len(result["modules"]) == 1
        assert result["modules"][0]["name"] == "vpc"
        assert result["modules"][0]["source"] == "./modules/vpc"

    def test_resource_parsed(self, tmp_path: Path):
        _write_tf(tmp_path / "main.tf", textwrap.dedent("""\
            resource "aws_instance" "web" {
              ami = "ami-123"
            }
        """))
        result = _status(tmp_path)
        assert len(result["resources"]) == 1
        r = result["resources"][0]
        assert r["type"] == "aws_instance"
        assert r["name"] == "web"
        assert "file" in r

    def test_data_source_parsed(self, tmp_path: Path):
        _write_tf(tmp_path / "main.tf", textwrap.dedent("""\
            data "aws_ami" "latest" {
              most_recent = true
            }
        """))
        result = _status(tmp_path)
        assert len(result["resources"]) == 1
        r = result["resources"][0]
        assert r["type"] == "data.aws_ami"
        assert r["name"] == "latest"

    def test_backend_s3_parsed(self, tmp_path: Path):
        _write_tf(tmp_path / "main.tf", textwrap.dedent("""\
            terraform {
              backend "s3" {
                bucket = "my-bucket"
              }
            }
        """))
        result = _status(tmp_path)
        assert result["backend"] is not None
        assert result["backend"]["type"] == "s3"

    def test_backend_gcs_parsed(self, tmp_path: Path):
        _write_tf(tmp_path / "main.tf", textwrap.dedent("""\
            terraform {
              backend "gcs" {
                bucket = "my-bucket"
              }
            }
        """))
        result = _status(tmp_path)
        assert result["backend"] is not None
        assert result["backend"]["type"] == "gcs"

    def test_backend_azurerm_parsed(self, tmp_path: Path):
        _write_tf(tmp_path / "main.tf", textwrap.dedent("""\
            terraform {
              backend "azurerm" {
                resource_group_name = "my-rg"
              }
            }
        """))
        result = _status(tmp_path)
        assert result["backend"] is not None
        assert result["backend"]["type"] == "azurerm"

    def test_no_backend(self, tmp_path: Path):
        _write_tf(tmp_path / "main.tf", 'provider "aws" {}\n')
        result = _status(tmp_path)
        assert result["backend"] is None

    def test_resource_count_matches(self, tmp_path: Path):
        _write_tf(tmp_path / "main.tf", textwrap.dedent("""\
            resource "aws_instance" "a" {}
            resource "aws_s3_bucket" "b" {}
            data "aws_ami" "c" {}
        """))
        result = _status(tmp_path)
        assert result["resource_count"] == len(result["resources"])
        assert result["resource_count"] == 3

    def test_nested_tf_files(self, tmp_path: Path):
        """Nested .tf files under the TF root are found."""
        tf_dir = tmp_path / "terraform"
        _write_tf(tf_dir / "main.tf", 'provider "aws" {}\n')
        _write_tf(tf_dir / "modules" / "vpc" / "main.tf",
                  'resource "aws_vpc" "main" {}\n')
        result = _status(tmp_path)
        paths = [f["path"] for f in result["files"]]
        assert any("modules/vpc" in p for p in paths)


# ═══════════════════════════════════════════════════════════════════
#  0.6.2 — Generation: generate_terraform()
# ═══════════════════════════════════════════════════════════════════


class TestGenerateTerraform:
    """generate_terraform() produces correct scaffolding."""

    def test_return_shape(self, tmp_path: Path):
        result = generate_terraform(tmp_path, "aws")
        assert result.get("ok") is True
        assert isinstance(result["files"], list)
        for f in result["files"]:
            assert "path" in f
            assert "content" in f
            assert "reason" in f

    def test_unknown_provider(self, tmp_path: Path):
        result = generate_terraform(tmp_path, "fantasy_cloud")
        assert "error" in result
        assert "fantasy_cloud" in result["error"]

    def test_aws_provider(self, tmp_path: Path):
        result = generate_terraform(tmp_path, "aws")
        main = _find_file(result, "main.tf")
        assert "hashicorp/aws" in main["content"]
        assert "region = var.region" in main["content"]

    def test_gcp_provider(self, tmp_path: Path):
        result = generate_terraform(tmp_path, "google")
        main = _find_file(result, "main.tf")
        assert "hashicorp/google" in main["content"]
        assert "project = var.project" in main["content"]

    def test_azure_provider(self, tmp_path: Path):
        result = generate_terraform(tmp_path, "azurerm")
        main = _find_file(result, "main.tf")
        assert "hashicorp/azurerm" in main["content"]
        assert "features {}" in main["content"]

    def test_digitalocean_provider(self, tmp_path: Path):
        result = generate_terraform(tmp_path, "digitalocean")
        main = _find_file(result, "main.tf")
        assert "digitalocean/digitalocean" in main["content"]

    def test_local_backend(self, tmp_path: Path):
        result = generate_terraform(tmp_path, "aws", backend="local")
        main = _find_file(result, "main.tf")
        assert 'backend "local"' in main["content"]

    def test_s3_backend(self, tmp_path: Path):
        result = generate_terraform(tmp_path, "aws", backend="s3",
                                     project_name="myapp")
        main = _find_file(result, "main.tf")
        assert 'backend "s3"' in main["content"]
        assert "myapp" in main["content"]

    def test_gcs_backend(self, tmp_path: Path):
        result = generate_terraform(tmp_path, "google", backend="gcs")
        main = _find_file(result, "main.tf")
        assert 'backend "gcs"' in main["content"]

    def test_azurerm_backend(self, tmp_path: Path):
        result = generate_terraform(tmp_path, "azurerm", backend="azurerm")
        main = _find_file(result, "main.tf")
        assert 'backend "azurerm"' in main["content"]

    def test_variables_tf_content(self, tmp_path: Path):
        result = generate_terraform(tmp_path, "aws", project_name="myapp")
        variables = _find_file(result, "variables.tf")
        content = variables["content"]
        assert 'variable "project"' in content
        assert 'variable "environment"' in content
        assert 'variable "region"' in content
        assert 'variable "tags"' in content

    def test_environment_validation(self, tmp_path: Path):
        result = generate_terraform(tmp_path, "aws")
        variables = _find_file(result, "variables.tf")
        content = variables["content"]
        assert "dev" in content
        assert "staging" in content
        assert "production" in content
        assert "validation" in content

    def test_outputs_tf_generated(self, tmp_path: Path):
        result = generate_terraform(tmp_path, "aws")
        outputs = _find_file(result, "outputs.tf")
        assert outputs is not None
        assert "Outputs" in outputs["content"] or "output" in outputs["content"].lower()

    def test_gitignore_generated(self, tmp_path: Path):
        result = generate_terraform(tmp_path, "aws")
        gi = _find_file(result, ".gitignore")
        assert gi is not None
        content = gi["content"]
        assert ".terraform/" in content
        assert "*.tfstate" in content
        assert "*.tfplan" in content
        assert "crash.log" in content

    def test_all_files_overwrite_false(self, tmp_path: Path):
        result = generate_terraform(tmp_path, "aws")
        for f in result["files"]:
            assert f.get("overwrite") is False, (
                f"File {f['path']} should have overwrite=False"
            )

    def test_four_files_generated(self, tmp_path: Path):
        result = generate_terraform(tmp_path, "aws")
        assert len(result["files"]) == 4


# ── Helpers ─────────────────────────────────────────────────────────


def _find_file(result: dict, name: str) -> dict | None:
    """Find a file in the generation result by name suffix."""
    for f in result.get("files", []):
        if f["path"].endswith(name):
            return f
    return None
