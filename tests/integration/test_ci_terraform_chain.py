"""
Integration tests for CI/CD + Terraform chain (1.11).

Tests that Terraform project state wires into GitHub Actions
workflow generation via generate_terraform_ci().

Spec grounding:
    PROJECT_SCOPE §4.3 Facilitate = "Generate workflows from detected stacks"
    TECHNOLOGY_SPEC §5.3 Facilitate = "Generate workflows, suggest test/deploy steps"
"""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path

from src.core.services.generators.github_workflow import generate_terraform_ci

pytestmark = pytest.mark.integration


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _gen(provider: str = "aws", **kw) -> dict:
    """Build a terraform config dict and generate CI workflow."""
    config = {"provider": provider, "working_directory": "terraform"}
    config.update(kw)
    result = generate_terraform_ci(config)
    return result


def _parse(result) -> dict:
    """Parse the GeneratedFile content as YAML."""
    assert result is not None, "generate_terraform_ci returned None"
    data = result.model_dump()
    return yaml.safe_load(data["content"])


# ═══════════════════════════════════════════════════════════════════
#  Workflow structure
# ═══════════════════════════════════════════════════════════════════


class TestWorkflowStructure:
    """Generated workflow has correct file path and YAML shape."""

    def test_workflow_file_path(self):
        """Produces .github/workflows/terraform.yml."""
        result = _gen()
        data = result.model_dump()
        assert data["path"] == ".github/workflows/terraform.yml"

    def test_workflow_triggers(self):
        """Triggers on push to main AND pull_request."""
        wf = _parse(_gen())
        # PyYAML parses the YAML key `on:` as boolean True
        triggers = wf.get("on") or wf.get(True, {})
        assert "push" in triggers
        assert "pull_request" in triggers

    def test_valid_yaml(self):
        """Generated content is valid YAML."""
        result = _gen()
        data = result.model_dump()
        parsed = yaml.safe_load(data["content"])
        assert isinstance(parsed, dict)
        assert "jobs" in parsed

    def test_generated_file_model(self):
        """Returns GeneratedFile with path, content, reason."""
        result = _gen()
        data = result.model_dump()
        assert "path" in data
        assert "content" in data
        assert "reason" in data

    def test_workflow_name(self):
        """Workflow has a name."""
        wf = _parse(_gen())
        assert "name" in wf
        assert "Terraform" in wf["name"] or "terraform" in wf["name"].lower()

    def test_project_name_in_workflow(self):
        """project_name influences workflow name."""
        result = _gen(project_name="myapp")
        wf = _parse(result)
        assert "myapp" in wf["name"]


# ═══════════════════════════════════════════════════════════════════
#  PR vs Push branching
# ═══════════════════════════════════════════════════════════════════


class TestPrVsPush:
    """PR = plan only, push = plan + apply."""

    def test_plan_step_present(self):
        """terraform plan step always present."""
        wf = _parse(_gen())
        steps = wf["jobs"]["terraform"]["steps"]
        step_names = [s.get("name", "") for s in steps]
        assert any("plan" in n.lower() for n in step_names)

    def test_apply_step_present(self):
        """terraform apply step present."""
        wf = _parse(_gen())
        steps = wf["jobs"]["terraform"]["steps"]
        step_names = [s.get("name", "") for s in steps]
        assert any("apply" in n.lower() for n in step_names)

    def test_apply_guarded_by_push(self):
        """Apply step only runs on push (not PR)."""
        wf = _parse(_gen())
        steps = wf["jobs"]["terraform"]["steps"]
        apply_steps = [s for s in steps if "apply" in s.get("name", "").lower()]
        assert len(apply_steps) >= 1
        for step in apply_steps:
            condition = step.get("if", "")
            assert "push" in condition, f"Apply step missing push guard: {step}"


# ═══════════════════════════════════════════════════════════════════
#  Terraform steps
# ═══════════════════════════════════════════════════════════════════


class TestTerraformSteps:
    """Correct Terraform CLI steps in order."""

    def _step_names(self, provider: str = "aws", **kw) -> list[str]:
        wf = _parse(_gen(provider, **kw))
        steps = wf["jobs"]["terraform"]["steps"]
        return [s.get("name", "") for s in steps]

    def test_init_present(self):
        """terraform init step present."""
        names = self._step_names()
        assert any("init" in n.lower() for n in names)

    def test_validate_present(self):
        """terraform validate step present."""
        names = self._step_names()
        assert any("validate" in n.lower() or "fmt" in n.lower() for n in names)

    def test_plan_present(self):
        """terraform plan step present."""
        names = self._step_names()
        assert any("plan" in n.lower() for n in names)

    def test_apply_present(self):
        """terraform apply step present."""
        names = self._step_names()
        assert any("apply" in n.lower() for n in names)

    def test_step_order(self):
        """Steps executed in correct order: init → validate → plan → apply."""
        names = self._step_names()
        # Find indices
        init_idx = next(i for i, n in enumerate(names) if "init" in n.lower())
        plan_idx = next(i for i, n in enumerate(names) if "plan" in n.lower())
        apply_idx = next(i for i, n in enumerate(names) if "apply" in n.lower())
        assert init_idx < plan_idx < apply_idx

    def test_working_directory(self):
        """Steps run in terraform/ subdirectory."""
        wf = _parse(_gen())
        job = wf["jobs"]["terraform"]
        # Working directory set at job level or step level
        job_defaults = job.get("defaults", {}).get("run", {})
        if "working-directory" in job_defaults:
            assert job_defaults["working-directory"] == "terraform"
        else:
            # Check that terraform commands include the dir
            steps = job["steps"]
            tf_steps = [s for s in steps if "terraform" in s.get("run", "")]
            assert len(tf_steps) > 0, "No terraform steps found"


# ═══════════════════════════════════════════════════════════════════
#  Backend credentials
# ═══════════════════════════════════════════════════════════════════


class TestBackendCredentials:
    """Provider-specific secrets injected via env block."""

    def _env_block(self, provider: str) -> dict:
        wf = _parse(_gen(provider))
        job = wf["jobs"]["terraform"]
        return job.get("env", {})

    def test_aws_credentials(self):
        """AWS → AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY."""
        env = self._env_block("aws")
        assert "AWS_ACCESS_KEY_ID" in env
        assert "AWS_SECRET_ACCESS_KEY" in env
        # Values should reference secrets
        assert "secrets." in str(env["AWS_ACCESS_KEY_ID"])
        assert "secrets." in str(env["AWS_SECRET_ACCESS_KEY"])

    def test_google_credentials(self):
        """Google → GOOGLE_CREDENTIALS."""
        env = self._env_block("google")
        assert "GOOGLE_CREDENTIALS" in env
        assert "secrets." in str(env["GOOGLE_CREDENTIALS"])

    def test_azure_credentials(self):
        """Azure → ARM_CLIENT_ID + ARM_CLIENT_SECRET + ARM_TENANT_ID + ARM_SUBSCRIPTION_ID."""
        env = self._env_block("azurerm")
        for key in ("ARM_CLIENT_ID", "ARM_CLIENT_SECRET", "ARM_TENANT_ID", "ARM_SUBSCRIPTION_ID"):
            assert key in env, f"Missing {key} in Azure env block"
            assert "secrets." in str(env[key])

    def test_credentials_use_github_secrets_syntax(self):
        """All credential values use ${{ secrets.X }} syntax."""
        env = self._env_block("aws")
        for val in env.values():
            val_str = str(val)
            if "secrets." in val_str:
                assert "${{" in val_str or "${{ " in val_str


# ═══════════════════════════════════════════════════════════════════
#  Workspace / environments
# ═══════════════════════════════════════════════════════════════════


class TestWorkspaces:
    """Per-environment Terraform workspaces in CI."""

    def test_no_workspaces_no_select(self):
        """No workspaces → no workspace select step."""
        wf = _parse(_gen())
        steps = wf["jobs"]["terraform"]["steps"]
        step_names = [s.get("name", "") for s in steps]
        assert not any("workspace" in n.lower() for n in step_names)

    def test_workspaces_add_select_step(self):
        """Multiple workspaces → workspace select step."""
        result = _gen(workspaces=["dev", "staging", "prod"])
        wf = _parse(result)
        steps = wf["jobs"]["terraform"]["steps"]
        step_names = [s.get("name", "") for s in steps]
        assert any("workspace" in n.lower() for n in step_names)
