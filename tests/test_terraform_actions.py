"""
Unit tests for Terraform CLI actions (mocked subprocess).

Covers milestones 0.6.3 (CLI wrappers), 0.6.4 (Action wrappers),
and 0.6.5 (Observe — validate, state, workspaces).

Every test mocks subprocess.run so no real `terraform` CLI is needed.
"""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.services.terraform_ops import (
    _run_terraform,
    _terraform_available,
    terraform_validate,
    terraform_plan,
    terraform_state,
    terraform_workspaces,
)
from src.core.services.terraform_actions import (
    terraform_init,
    terraform_apply,
    terraform_output,
    terraform_destroy,
    terraform_workspace_select,
    terraform_fmt,
)


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _write_tf(path: Path, content: str = "# empty\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _make_initialized(tmp_path: Path) -> Path:
    """Create a minimal TF project with .terraform/ directory."""
    tf_dir = tmp_path / "terraform"
    _write_tf(tf_dir / "main.tf", 'provider "aws" {}\n')
    (tf_dir / ".terraform").mkdir()
    return tf_dir


def _mock_result(stdout: str = "", stderr: str = "", rc: int = 0):
    """Create a mock subprocess.CompletedProcess."""
    return subprocess.CompletedProcess(
        args=["terraform"], returncode=rc,
        stdout=stdout, stderr=stderr,
    )


def _cli_available():
    """Mock _terraform_available returning available."""
    return {"available": True, "version": "1.9.0"}


def _cli_unavailable():
    """Mock _terraform_available returning unavailable."""
    return {"available": False}


# ═══════════════════════════════════════════════════════════════════
#  0.6.3 — CLI Wrappers: _terraform_available, _run_terraform
# ═══════════════════════════════════════════════════════════════════


class TestTerraformAvailable:
    """_terraform_available() CLI detection."""

    def test_cli_installed(self):
        mock_result = _mock_result(stdout="Terraform v1.9.0\n")
        with patch("src.core.services.terraform_ops.subprocess.run",
                    return_value=mock_result):
            result = _terraform_available()
            assert result["available"] is True
            assert "1.9.0" in result["version"]

    def test_cli_not_installed(self):
        with patch("src.core.services.terraform_ops.subprocess.run",
                    side_effect=FileNotFoundError):
            result = _terraform_available()
            assert result["available"] is False

    def test_run_terraform_calls_subprocess(self, tmp_path: Path):
        mock_result = _mock_result(stdout="ok\n")
        with patch("src.core.services.terraform_ops.subprocess.run",
                    return_value=mock_result) as mock_run:
            _run_terraform("init", "-no-color", cwd=tmp_path, timeout=60)
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert "init" in call_args[0][0]
            assert str(call_args[1]["cwd"]) == str(tmp_path)


# ═══════════════════════════════════════════════════════════════════
#  0.6.4 — Action Wrappers: init, apply, destroy, output, fmt
# ═══════════════════════════════════════════════════════════════════


class TestTerraformInit:
    """terraform_init() tests."""

    def test_success(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        with patch("src.core.services.terraform_actions._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_actions._run_terraform",
                    return_value=_mock_result(stdout="Initialized\n")):
            result = terraform_init(tmp_path)
            assert result["ok"] is True
            assert "Initialized" in result["output"]

    def test_no_tf_files(self, tmp_path: Path):
        result = terraform_init(tmp_path)
        assert result["ok"] is False
        assert "No Terraform files" in result["error"]

    def test_cli_not_available(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        with patch("src.core.services.terraform_actions._terraform_available",
                    return_value=_cli_unavailable()):
            result = terraform_init(tmp_path)
            assert result["ok"] is False
            assert "not available" in result["error"]

    def test_upgrade_flag(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        with patch("src.core.services.terraform_actions._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_actions._run_terraform",
                    return_value=_mock_result(stdout="ok")) as mock_run:
            terraform_init(tmp_path, upgrade=True)
            call_args = mock_run.call_args[0]
            assert "-upgrade" in call_args

    def test_timeout(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        with patch("src.core.services.terraform_actions._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_actions._run_terraform",
                    side_effect=subprocess.TimeoutExpired("terraform", 120)):
            result = terraform_init(tmp_path)
            assert result["ok"] is False
            assert "timed out" in result["error"]


class TestTerraformApply:
    """terraform_apply() tests."""

    def test_success(self, tmp_path: Path):
        tf_dir = _make_initialized(tmp_path)
        with patch("src.core.services.terraform_actions._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_actions._run_terraform",
                    return_value=_mock_result(
                        stdout="Apply complete! Resources: 1 added, 0 changed, 0 destroyed."
                    )):
            result = terraform_apply(tmp_path)
            assert result["ok"] is True
            assert "changes" in result

    def test_not_initialized(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        with patch("src.core.services.terraform_actions._terraform_available",
                    return_value=_cli_available()):
            result = terraform_apply(tmp_path)
            assert result["ok"] is False
            assert "not initialized" in result["error"].lower()

    def test_auto_approve_flag(self, tmp_path: Path):
        tf_dir = _make_initialized(tmp_path)
        with patch("src.core.services.terraform_actions._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_actions._run_terraform",
                    return_value=_mock_result()) as mock_run:
            terraform_apply(tmp_path, auto_approve=True)
            call_args = mock_run.call_args[0]
            assert "-auto-approve" in call_args

    def test_timeout(self, tmp_path: Path):
        tf_dir = _make_initialized(tmp_path)
        with patch("src.core.services.terraform_actions._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_actions._run_terraform",
                    side_effect=subprocess.TimeoutExpired("terraform", 300)):
            result = terraform_apply(tmp_path)
            assert result["ok"] is False
            assert "timed out" in result["error"]


class TestTerraformPlan:
    """terraform_plan() tests."""

    def test_success(self, tmp_path: Path):
        tf_dir = _make_initialized(tmp_path)
        with patch("src.core.services.terraform_ops._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_ops._run_terraform",
                    return_value=_mock_result(
                        stdout="Plan: 2 to add, 1 to change, 0 to destroy."
                    )):
            result = terraform_plan(tmp_path)
            assert result["ok"] is True
            assert "changes" in result

    def test_not_initialized(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        with patch("src.core.services.terraform_ops._terraform_available",
                    return_value=_cli_available()):
            result = terraform_plan(tmp_path)
            assert result["ok"] is False
            assert "not initialized" in result["error"].lower()

    def test_var_file(self, tmp_path: Path):
        tf_dir = _make_initialized(tmp_path)
        with patch("src.core.services.terraform_ops._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_ops._run_terraform",
                    return_value=_mock_result(
                        stdout="Plan: 0 to add, 0 to change, 0 to destroy."
                    )) as mock_run:
            result = terraform_plan(tmp_path, var_file="prod.tfvars")
            assert result["ok"] is True
            call_args = mock_run.call_args[0]
            assert "-var-file" in call_args
            assert "prod.tfvars" in call_args


class TestTerraformDestroy:
    """terraform_destroy() tests."""

    def test_success(self, tmp_path: Path):
        tf_dir = _make_initialized(tmp_path)
        with patch("src.core.services.terraform_actions._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_actions._run_terraform",
                    return_value=_mock_result(stdout="Destroy complete!")):
            result = terraform_destroy(tmp_path)
            assert result["ok"] is True

    def test_not_initialized(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        with patch("src.core.services.terraform_actions._terraform_available",
                    return_value=_cli_available()):
            result = terraform_destroy(tmp_path)
            assert result["ok"] is False
            assert "not initialized" in result["error"].lower()

    def test_auto_approve_flag(self, tmp_path: Path):
        tf_dir = _make_initialized(tmp_path)
        with patch("src.core.services.terraform_actions._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_actions._run_terraform",
                    return_value=_mock_result()) as mock_run:
            terraform_destroy(tmp_path, auto_approve=True)
            call_args = mock_run.call_args[0]
            assert "-auto-approve" in call_args


class TestTerraformOutput:
    """terraform_output() tests."""

    def test_json_parsed(self, tmp_path: Path):
        tf_dir = _make_initialized(tmp_path)
        mock_output = json.dumps({
            "vpc_id": {"value": "vpc-123", "type": "string", "sensitive": False},
            "db_password": {"value": "***", "type": "string", "sensitive": True},
        })
        with patch("src.core.services.terraform_actions._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_actions._run_terraform",
                    return_value=_mock_result(stdout=mock_output)):
            result = terraform_output(tmp_path)
            assert result["ok"] is True
            assert "vpc_id" in result["outputs"]
            assert result["outputs"]["vpc_id"]["value"] == "vpc-123"
            assert result["outputs"]["db_password"]["sensitive"] is True

    def test_no_outputs(self, tmp_path: Path):
        tf_dir = _make_initialized(tmp_path)
        with patch("src.core.services.terraform_actions._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_actions._run_terraform",
                    return_value=_mock_result(
                        rc=1, stderr="no outputs defined"
                    )):
            result = terraform_output(tmp_path)
            assert result["ok"] is True
            assert result["outputs"] == {}


class TestTerraformFmt:
    """terraform_fmt() tests."""

    def test_success(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        with patch("src.core.services.terraform_actions._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_actions._run_terraform",
                    return_value=_mock_result(stdout="main.tf\n")):
            result = terraform_fmt(tmp_path)
            assert result["ok"] is True
            assert "main.tf" in result["files"]
            assert result["count"] == 1

    def test_no_tf_files(self, tmp_path: Path):
        result = terraform_fmt(tmp_path)
        assert result["ok"] is False
        assert "No Terraform files" in result["error"]


# ═══════════════════════════════════════════════════════════════════
#  0.6.5 — Observe: validate, state, workspaces
# ═══════════════════════════════════════════════════════════════════


class TestTerraformValidate:
    """terraform_validate() tests."""

    def test_valid(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        mock_json = json.dumps({"valid": True, "diagnostics": []})
        with patch("src.core.services.terraform_ops._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_ops._run_terraform",
                    return_value=_mock_result(stdout=mock_json)):
            result = terraform_validate(tmp_path)
            assert result["ok"] is True
            assert result["valid"] is True
            assert result["errors"] == []

    def test_invalid(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        mock_json = json.dumps({
            "valid": False,
            "diagnostics": [
                {"summary": "Missing required argument", "severity": "error"},
                {"summary": "Deprecated attribute", "severity": "warning"},
            ],
        })
        with patch("src.core.services.terraform_ops._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_ops._run_terraform",
                    return_value=_mock_result(stdout=mock_json)):
            result = terraform_validate(tmp_path)
            assert result["ok"] is True
            assert result["valid"] is False
            assert len(result["errors"]) == 2
            assert result["errors"][0]["severity"] == "error"

    def test_cli_not_available(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        with patch("src.core.services.terraform_ops._terraform_available",
                    return_value=_cli_unavailable()):
            result = terraform_validate(tmp_path)
            assert result["ok"] is False
            assert "not available" in result["error"]


class TestTerraformState:
    """terraform_state() tests."""

    def test_has_resources(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        mock_output = "aws_instance.web\naws_s3_bucket.data\n"
        with patch("src.core.services.terraform_ops._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_ops._run_terraform",
                    return_value=_mock_result(stdout=mock_output)):
            result = terraform_state(tmp_path)
            assert result["ok"] is True
            assert result["count"] == 2
            assert result["resources"][0]["type"] == "aws_instance"
            assert result["resources"][0]["name"] == "web"

    def test_module_address(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        mock_output = "module.vpc.aws_vpc.main\n"
        with patch("src.core.services.terraform_ops._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_ops._run_terraform",
                    return_value=_mock_result(stdout=mock_output)):
            result = terraform_state(tmp_path)
            assert result["ok"] is True
            r = result["resources"][0]
            assert r["module"] == "vpc"
            assert r["type"] == "aws_vpc"
            assert r["name"] == "main"

    def test_data_address(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        mock_output = "data.aws_ami.latest\n"
        with patch("src.core.services.terraform_ops._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_ops._run_terraform",
                    return_value=_mock_result(stdout=mock_output)):
            result = terraform_state(tmp_path)
            assert result["ok"] is True
            r = result["resources"][0]
            assert r["type"] == "data.aws_ami"
            assert r["name"] == "latest"

    def test_no_state(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        with patch("src.core.services.terraform_ops._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_ops._run_terraform",
                    return_value=_mock_result(
                        rc=1, stderr="No state file was found!"
                    )):
            result = terraform_state(tmp_path)
            assert result["ok"] is True
            assert result["resources"] == []
            assert result["count"] == 0


class TestTerraformWorkspaces:
    """terraform_workspaces() tests."""

    def test_parse_current(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        mock_output = "  dev\n* staging\n  production\n"
        with patch("src.core.services.terraform_ops._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_ops._run_terraform",
                    return_value=_mock_result(stdout=mock_output)):
            result = terraform_workspaces(tmp_path)
            assert result["ok"] is True
            assert result["current"] == "staging"

    def test_multiple_workspaces(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        mock_output = "* default\n  dev\n  staging\n"
        with patch("src.core.services.terraform_ops._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_ops._run_terraform",
                    return_value=_mock_result(stdout=mock_output)):
            result = terraform_workspaces(tmp_path)
            assert result["ok"] is True
            assert len(result["workspaces"]) == 3
            assert "dev" in result["workspaces"]
            assert "staging" in result["workspaces"]


class TestTerraformWorkspaceSelect:
    """terraform_workspace_select() tests."""

    def test_existing_workspace(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        with patch("src.core.services.terraform_actions._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_actions._run_terraform",
                    return_value=_mock_result(stdout="Switched to workspace dev")):
            result = terraform_workspace_select(tmp_path, "dev")
            assert result["ok"] is True
            assert result["created"] is False

    def test_new_workspace(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        # First select fails (workspace doesn't exist), then new succeeds
        with patch("src.core.services.terraform_actions._terraform_available",
                    return_value=_cli_available()), \
             patch("src.core.services.terraform_actions._run_terraform",
                    side_effect=[
                        _mock_result(rc=1, stderr="Workspace does not exist"),
                        _mock_result(stdout="Created workspace staging"),
                    ]):
            result = terraform_workspace_select(tmp_path, "staging")
            assert result["ok"] is True
            assert result["created"] is True

    def test_empty_name(self, tmp_path: Path):
        _write_tf(tmp_path / "terraform" / "main.tf")
        result = terraform_workspace_select(tmp_path, "")
        assert result["ok"] is False
        assert "Missing" in result["error"] or "workspace" in result["error"].lower()
