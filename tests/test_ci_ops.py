"""
Tests for ci_ops — workflow parsing, auditing, coverage analysis.

Pure unit tests: YAML files on disk → parsed dicts.
No CI provider connections required.
"""

import textwrap
from pathlib import Path

from src.core.services.ci_ops import (
    _parse_github_workflow,
    _audit_github_workflow,
    ci_coverage,
)


# ═══════════════════════════════════════════════════════════════════
#  _parse_github_workflow
# ═══════════════════════════════════════════════════════════════════


class TestParseGithubWorkflow:
    def test_standard_workflow(self, tmp_path: Path):
        """Standard CI workflow → name, triggers, jobs extracted."""
        wf = tmp_path / "ci.yml"
        wf.write_text(textwrap.dedent("""\
            name: CI
            on:
              push:
                branches: [main]
              pull_request:
                branches: [main]
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                  - run: pytest tests/
        """))
        result = _parse_github_workflow(wf, tmp_path)
        assert result is not None
        assert result["name"] == "CI"
        assert result["provider"] == "github_actions"
        assert "push" in result["triggers"]
        assert "pull_request" in result["triggers"]
        assert len(result["jobs"]) == 1
        assert result["jobs"][0]["id"] == "test"
        assert result["jobs"][0]["runs_on"] == "ubuntu-latest"
        assert result["jobs"][0]["steps_count"] == 2

    def test_workflow_with_multiple_jobs(self, tmp_path: Path):
        """Workflow with build + deploy jobs."""
        wf = tmp_path / "deploy.yml"
        wf.write_text(textwrap.dedent("""\
            name: Deploy
            on: [push]
            jobs:
              build:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                  - run: make build
              deploy:
                runs-on: ubuntu-latest
                needs: [build]
                steps:
                  - uses: actions/checkout@v4
                  - run: make deploy
        """))
        result = _parse_github_workflow(wf, tmp_path)
        assert len(result["jobs"]) == 2
        deploy_job = next(j for j in result["jobs"] if j["id"] == "deploy")
        assert deploy_job["needs"] == ["build"]

    def test_invalid_yaml_returns_issues(self, tmp_path: Path):
        """Invalid YAML → result with parse error issue."""
        wf = tmp_path / "broken.yml"
        wf.write_text("not: valid: yaml: {{{\n")
        result = _parse_github_workflow(wf, tmp_path)
        assert result is not None
        assert len(result["issues"]) > 0
        assert "parse" in result["issues"][0].lower() or "Failed" in result["issues"][0]


# ═══════════════════════════════════════════════════════════════════
#  _audit_github_workflow
# ═══════════════════════════════════════════════════════════════════


class TestAuditGithubWorkflow:
    def test_unpinned_action_flagged(self, tmp_path: Path):
        """Action without @version → issue reported."""
        data = {
            "jobs": {
                "test": {
                    "steps": [
                        {"uses": "actions/checkout"},  # missing @v4
                    ],
                },
            },
        }
        issues = _audit_github_workflow(data, tmp_path / "ci.yml")
        assert len(issues) == 1
        assert "not pinned" in issues[0]

    def test_pinned_action_clean(self, tmp_path: Path):
        """Action with @version → no issues."""
        data = {
            "jobs": {
                "test": {
                    "steps": [
                        {"uses": "actions/checkout@v4"},
                        {"run": "pytest tests/"},
                    ],
                },
            },
        }
        issues = _audit_github_workflow(data, tmp_path / "ci.yml")
        assert len(issues) == 0

    def test_empty_run_flagged(self, tmp_path: Path):
        """Step with empty run command → issue reported."""
        data = {
            "jobs": {
                "test": {
                    "steps": [
                        {"name": "empty step", "run": "  # just a comment\n"},
                    ],
                },
            },
        }
        issues = _audit_github_workflow(data, tmp_path / "ci.yml")
        assert len(issues) == 1
        assert "empty run" in issues[0].lower()

    def test_no_jobs_flagged(self, tmp_path: Path):
        """Workflow with no jobs → issue reported."""
        issues = _audit_github_workflow({}, tmp_path / "ci.yml")
        assert any("No jobs" in i for i in issues)

    def test_job_with_no_steps_flagged(self, tmp_path: Path):
        """Job with empty steps → issue reported."""
        data = {
            "jobs": {
                "empty": {
                    "steps": [],
                },
            },
        }
        issues = _audit_github_workflow(data, tmp_path / "ci.yml")
        assert any("no steps" in i.lower() for i in issues)


# ═══════════════════════════════════════════════════════════════════
#  ci_coverage
# ═══════════════════════════════════════════════════════════════════


class TestCiCoverage:
    def test_module_covered_by_path(self, tmp_path: Path):
        """Module path appears in CI file → covered."""
        gha_dir = tmp_path / ".github" / "workflows"
        gha_dir.mkdir(parents=True)
        (gha_dir / "ci.yml").write_text(textwrap.dedent("""\
            name: CI
            on: [push]
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - run: pytest services/api/
        """))
        modules = [
            {"name": "api", "path": "services/api", "stack_name": "python"},
        ]
        result = ci_coverage(tmp_path, modules)
        assert "api" in result["covered"]
        assert result["coverage_pct"] == 100.0

    def test_module_not_covered(self, tmp_path: Path):
        """Module not referenced in any CI file → uncovered."""
        gha_dir = tmp_path / ".github" / "workflows"
        gha_dir.mkdir(parents=True)
        (gha_dir / "ci.yml").write_text(textwrap.dedent("""\
            name: CI
            on: [push]
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - run: echo hello
        """))
        modules = [
            {"name": "web", "path": "services/web", "stack_name": "node"},
        ]
        result = ci_coverage(tmp_path, modules)
        assert "web" in result["uncovered"]
        assert result["coverage_pct"] == 0.0

    def test_stack_based_coverage(self, tmp_path: Path):
        """Python module covered by 'pytest' in CI → covered via stack."""
        gha_dir = tmp_path / ".github" / "workflows"
        gha_dir.mkdir(parents=True)
        (gha_dir / "ci.yml").write_text(textwrap.dedent("""\
            name: CI
            on: [push]
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - run: pytest
        """))
        modules = [
            {"name": "core", "path": "src/core", "stack_name": "python"},
        ]
        result = ci_coverage(tmp_path, modules)
        assert "core" in result["covered"]

    def test_no_ci_files(self, tmp_path: Path):
        """No CI files → everything uncovered."""
        modules = [
            {"name": "api", "path": "services/api", "stack_name": "python"},
        ]
        result = ci_coverage(tmp_path, modules)
        assert "api" in result["uncovered"]
        assert result["coverage_pct"] == 0.0
