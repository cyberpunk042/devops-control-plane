"""
Tests for ci_ops — provider detection, workflow listing, content gathering.

Pure unit tests: files on disk → parsed dicts.
No CI provider connections required.
"""

import textwrap
from pathlib import Path

from src.core.services.ci_ops import (
    ci_status,
    ci_workflows,
    _parse_gitlab_ci,
    _gather_ci_content,
    _check_stack_coverage,
)


# ═══════════════════════════════════════════════════════════════════
#  ci_status — provider detection
# ═══════════════════════════════════════════════════════════════════


class TestCiStatus:
    def test_empty_project(self, tmp_path: Path):
        """No CI files → has_ci=False, providers=[]."""
        result = ci_status(tmp_path)
        assert result["has_ci"] is False
        assert result["providers"] == []
        assert result["total_workflows"] == 0

    def test_detects_github_actions(self, tmp_path: Path):
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: CI\n")
        result = ci_status(tmp_path)
        assert result["has_ci"] is True
        assert any(p["id"] == "github_actions" for p in result["providers"])

    def test_counts_github_workflows(self, tmp_path: Path):
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        for name in ("ci.yml", "lint.yml", "deploy.yaml"):
            (wf_dir / name).write_text(f"name: {name}\n")
        result = ci_status(tmp_path)
        gh = next(p for p in result["providers"] if p["id"] == "github_actions")
        assert gh["workflows"] == 3
        assert result["total_workflows"] == 3

    def test_detects_gitlab_ci(self, tmp_path: Path):
        (tmp_path / ".gitlab-ci.yml").write_text("stages: [build]\n")
        assert any(p["id"] == "gitlab_ci" for p in ci_status(tmp_path)["providers"])

    def test_detects_gitlab_ci_yaml(self, tmp_path: Path):
        (tmp_path / ".gitlab-ci.yaml").write_text("stages: [build]\n")
        assert any(p["id"] == "gitlab_ci" for p in ci_status(tmp_path)["providers"])

    def test_detects_jenkinsfile(self, tmp_path: Path):
        (tmp_path / "Jenkinsfile").write_text("pipeline { }\n")
        assert any(p["id"] == "jenkins" for p in ci_status(tmp_path)["providers"])

    def test_detects_circleci(self, tmp_path: Path):
        d = tmp_path / ".circleci"
        d.mkdir()
        (d / "config.yml").write_text("version: 2.1\n")
        assert any(p["id"] == "circleci" for p in ci_status(tmp_path)["providers"])

    def test_detects_travis(self, tmp_path: Path):
        (tmp_path / ".travis.yml").write_text("language: python\n")
        assert any(p["id"] == "travis" for p in ci_status(tmp_path)["providers"])

    def test_detects_azure_pipelines(self, tmp_path: Path):
        (tmp_path / "azure-pipelines.yml").write_text("trigger: [main]\n")
        assert any(p["id"] == "azure_pipelines" for p in ci_status(tmp_path)["providers"])

    def test_detects_bitbucket_pipelines(self, tmp_path: Path):
        (tmp_path / "bitbucket-pipelines.yml").write_text("pipelines:\n")
        assert any(p["id"] == "bitbucket_pipelines" for p in ci_status(tmp_path)["providers"])

    def test_multi_provider(self, tmp_path: Path):
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: CI\n")
        (tmp_path / ".gitlab-ci.yml").write_text("stages: [test]\n")
        ids = {p["id"] for p in ci_status(tmp_path)["providers"]}
        assert "github_actions" in ids
        assert "gitlab_ci" in ids

    def test_ignores_non_yaml(self, tmp_path: Path):
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: CI\n")
        (wf_dir / "README.md").write_text("docs\n")
        gh = next(p for p in ci_status(tmp_path)["providers"] if p["id"] == "github_actions")
        assert gh["workflows"] == 1


# ═══════════════════════════════════════════════════════════════════
#  ci_workflows
# ═══════════════════════════════════════════════════════════════════


class TestCiWorkflows:
    def test_empty_project(self, tmp_path: Path):
        assert ci_workflows(tmp_path)["workflows"] == []

    def test_github_workflow_parsed(self, tmp_path: Path):
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(textwrap.dedent("""\
            name: CI
            on: [push]
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                  - run: pytest
        """))
        wfs = ci_workflows(tmp_path)["workflows"]
        assert len(wfs) == 1
        assert wfs[0]["provider"] == "github_actions"
        assert wfs[0]["name"] == "CI"

    def test_gitlab_parsed(self, tmp_path: Path):
        (tmp_path / ".gitlab-ci.yml").write_text(textwrap.dedent("""\
            stages: [build, test]
            build_job:
              stage: build
              script: [make build]
            test_job:
              stage: test
              script: [make test, make coverage]
        """))
        wfs = ci_workflows(tmp_path)["workflows"]
        assert len(wfs) == 1
        assert wfs[0]["provider"] == "gitlab_ci"
        assert len(wfs[0]["jobs"]) == 2

    def test_jenkinsfile_listed(self, tmp_path: Path):
        (tmp_path / "Jenkinsfile").write_text("pipeline { }\n")
        wfs = ci_workflows(tmp_path)["workflows"]
        assert len(wfs) == 1
        assert wfs[0]["provider"] == "jenkins"

    def test_multi_provider_combined(self, tmp_path: Path):
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: CI\non: [push]\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo\n")
        (tmp_path / ".gitlab-ci.yml").write_text("job:\n  script: echo\n")
        providers = {w["provider"] for w in ci_workflows(tmp_path)["workflows"]}
        assert "github_actions" in providers
        assert "gitlab_ci" in providers

    def test_sorted_order(self, tmp_path: Path):
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "z.yml").write_text("name: Z\non: [push]\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo\n")
        (wf_dir / "a.yml").write_text("name: A\non: [push]\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo\n")
        gha = [w for w in ci_workflows(tmp_path)["workflows"] if w["provider"] == "github_actions"]
        assert gha[0]["name"] == "A"


# ═══════════════════════════════════════════════════════════════════
#  _parse_gitlab_ci
# ═══════════════════════════════════════════════════════════════════


class TestParseGitlabCi:
    def test_extracts_jobs(self, tmp_path: Path):
        gl = tmp_path / ".gitlab-ci.yml"
        gl.write_text("stages: [build]\nvariables:\n  CI: 'true'\nbuild:\n  stage: build\n  script: [make]\n")
        result = _parse_gitlab_ci(gl, tmp_path)
        assert len(result["jobs"]) == 1
        assert result["jobs"][0]["id"] == "build"

    def test_skips_dot_templates(self, tmp_path: Path):
        gl = tmp_path / ".gitlab-ci.yml"
        gl.write_text(".template:\n  script: echo\nreal:\n  script: echo\n")
        result = _parse_gitlab_ci(gl, tmp_path)
        assert len(result["jobs"]) == 1
        assert result["jobs"][0]["id"] == "real"

    def test_skips_meta_keys(self, tmp_path: Path):
        gl = tmp_path / ".gitlab-ci.yml"
        gl.write_text("stages: [a]\nvariables:\n  X: 1\ninclude: r.yml\ndefault:\n  image: py\nimage: node\njob:\n  script: echo\n")
        result = _parse_gitlab_ci(gl, tmp_path)
        assert len(result["jobs"]) == 1

    def test_invalid_yaml(self, tmp_path: Path):
        gl = tmp_path / ".gitlab-ci.yml"
        gl.write_text("{{bad}}")
        result = _parse_gitlab_ci(gl, tmp_path)
        assert len(result["issues"]) > 0


# ═══════════════════════════════════════════════════════════════════
#  _gather_ci_content / _check_stack_coverage
# ═══════════════════════════════════════════════════════════════════


class TestGatherCiContent:
    def test_empty(self, tmp_path: Path):
        assert _gather_ci_content(tmp_path) == ""

    def test_gathers_gha(self, tmp_path: Path):
        d = tmp_path / ".github" / "workflows"
        d.mkdir(parents=True)
        (d / "ci.yml").write_text("run: pytest\n")
        assert "pytest" in _gather_ci_content(tmp_path)

    def test_gathers_gitlab(self, tmp_path: Path):
        (tmp_path / ".gitlab-ci.yml").write_text("script: ruff\n")
        assert "ruff" in _gather_ci_content(tmp_path)

    def test_gathers_jenkinsfile(self, tmp_path: Path):
        (tmp_path / "Jenkinsfile").write_text("sh 'npm test'\n")
        assert "npm test" in _gather_ci_content(tmp_path)


class TestCheckStackCoverage:
    def test_python_pytest(self):
        assert _check_stack_coverage("python", "run: pytest") == "pytest"

    def test_node_npm_test(self):
        assert _check_stack_coverage("node", "npm test") == "npm test"

    def test_go_test(self):
        assert _check_stack_coverage("go", "go test ./...") == "go test"

    def test_rust_cargo(self):
        assert _check_stack_coverage("rust", "cargo test") == "cargo test"

    def test_prefix_match(self):
        assert _check_stack_coverage("python-flask", "pytest") == "pytest"

    def test_no_match(self):
        assert _check_stack_coverage("cobol", "echo hello") is None

    def test_no_content_match(self):
        assert _check_stack_coverage("python", "npm test") is None
