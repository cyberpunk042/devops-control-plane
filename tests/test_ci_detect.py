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
        assert result["total_workflows"] == 1
        gh = next(p for p in result["providers"] if p["id"] == "github_actions")
        assert gh["name"] == "GitHub Actions"
        assert gh["workflows"] == 1

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
        result = ci_status(tmp_path)
        assert result["has_ci"] is True
        gl = next(p for p in result["providers"] if p["id"] == "gitlab_ci")
        assert gl["name"] == "GitLab CI"
        assert gl["workflows"] == 1
        assert result["total_workflows"] == 1

    def test_detects_gitlab_ci_yaml(self, tmp_path: Path):
        (tmp_path / ".gitlab-ci.yaml").write_text("stages: [build]\n")
        result = ci_status(tmp_path)
        assert result["has_ci"] is True
        gl = next(p for p in result["providers"] if p["id"] == "gitlab_ci")
        assert gl["name"] == "GitLab CI"
        assert gl["workflows"] == 1

    def test_detects_jenkinsfile(self, tmp_path: Path):
        (tmp_path / "Jenkinsfile").write_text("pipeline { }\n")
        result = ci_status(tmp_path)
        assert result["has_ci"] is True
        jk = next(p for p in result["providers"] if p["id"] == "jenkins")
        assert jk["name"] == "Jenkins"
        assert jk["workflows"] == 1

    def test_detects_circleci(self, tmp_path: Path):
        d = tmp_path / ".circleci"
        d.mkdir()
        (d / "config.yml").write_text("version: 2.1\n")
        result = ci_status(tmp_path)
        assert result["has_ci"] is True
        cc = next(p for p in result["providers"] if p["id"] == "circleci")
        assert cc["name"] == "CircleCI"
        assert cc["workflows"] == 1

    def test_detects_travis(self, tmp_path: Path):
        (tmp_path / ".travis.yml").write_text("language: python\n")
        result = ci_status(tmp_path)
        assert result["has_ci"] is True
        tv = next(p for p in result["providers"] if p["id"] == "travis")
        assert tv["name"] == "Travis CI"
        assert tv["workflows"] == 1

    def test_detects_azure_pipelines(self, tmp_path: Path):
        (tmp_path / "azure-pipelines.yml").write_text("trigger: [main]\n")
        result = ci_status(tmp_path)
        assert result["has_ci"] is True
        az = next(p for p in result["providers"] if p["id"] == "azure_pipelines")
        assert az["name"] == "Azure Pipelines"
        assert az["workflows"] == 1

    def test_detects_bitbucket_pipelines(self, tmp_path: Path):
        (tmp_path / "bitbucket-pipelines.yml").write_text("pipelines:\n")
        result = ci_status(tmp_path)
        assert result["has_ci"] is True
        bb = next(p for p in result["providers"] if p["id"] == "bitbucket_pipelines")
        assert bb["name"] == "Bitbucket Pipelines"
        assert bb["workflows"] == 1

    def test_multi_provider(self, tmp_path: Path):
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: CI\n")
        (tmp_path / ".gitlab-ci.yml").write_text("stages: [test]\n")
        result = ci_status(tmp_path)
        assert result["has_ci"] is True
        ids = {p["id"] for p in result["providers"]}
        assert "github_actions" in ids
        assert "gitlab_ci" in ids
        assert result["total_workflows"] == 2

    def test_ignores_non_yaml(self, tmp_path: Path):
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: CI\n")
        (wf_dir / "README.md").write_text("docs\n")
        (wf_dir / "script.sh").write_text("echo hi\n")
        result = ci_status(tmp_path)
        gh = next(p for p in result["providers"] if p["id"] == "github_actions")
        assert gh["workflows"] == 1
        assert result["total_workflows"] == 1

    def test_return_shape(self, tmp_path: Path):
        """ci_status() always returns the full shape, even for empty projects."""
        result = ci_status(tmp_path)
        assert "providers" in result
        assert "total_workflows" in result
        assert "has_ci" in result
        assert isinstance(result["providers"], list)
        assert isinstance(result["total_workflows"], int)
        assert isinstance(result["has_ci"], bool)

    def test_provider_shape(self, tmp_path: Path):
        """Each provider dict has exactly id, name, workflows."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: CI\n")
        result = ci_status(tmp_path)
        for p in result["providers"]:
            assert "id" in p, f"Missing 'id' in provider {p}"
            assert "name" in p, f"Missing 'name' in provider {p}"
            assert "workflows" in p, f"Missing 'workflows' in provider {p}"
            assert isinstance(p["id"], str)
            assert isinstance(p["name"], str)
            assert isinstance(p["workflows"], int)
            assert p["workflows"] >= 0


# ═══════════════════════════════════════════════════════════════════
#  ci_workflows
# ═══════════════════════════════════════════════════════════════════


class TestCiWorkflows:
    def test_empty_project(self, tmp_path: Path):
        result = ci_workflows(tmp_path)
        assert "workflows" in result
        assert result["workflows"] == []
        assert isinstance(result["workflows"], list)

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
        wf = wfs[0]
        assert wf["provider"] == "github_actions"
        assert wf["name"] == "CI"
        assert isinstance(wf["triggers"], list)
        assert "push" in wf["triggers"]
        assert isinstance(wf["jobs"], list)
        assert len(wf["jobs"]) == 1
        assert wf["jobs"][0]["id"] == "test"
        assert wf["jobs"][0]["steps_count"] == 2
        assert wf["jobs"][0]["runs_on"] == "ubuntu-latest"
        assert isinstance(wf["issues"], list)

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
        wf = wfs[0]
        assert wf["provider"] == "jenkins"
        assert wf["name"] == "Jenkinsfile"
        assert isinstance(wf["triggers"], list)
        assert isinstance(wf["jobs"], list)
        assert isinstance(wf["issues"], list)

    def test_multi_provider_combined(self, tmp_path: Path):
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: CI\non: [push]\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo\n")
        (tmp_path / ".gitlab-ci.yml").write_text("job:\n  script: echo\n")
        wfs = ci_workflows(tmp_path)["workflows"]
        providers = {w["provider"] for w in wfs}
        assert "github_actions" in providers
        assert "gitlab_ci" in providers
        assert len(wfs) == 2

    def test_sorted_order(self, tmp_path: Path):
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "z.yml").write_text("name: Z\non: [push]\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo\n")
        (wf_dir / "a.yml").write_text("name: A\non: [push]\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo\n")
        gha = [w for w in ci_workflows(tmp_path)["workflows"] if w["provider"] == "github_actions"]
        assert gha[0]["name"] == "A"

    def test_workflow_shape(self, tmp_path: Path):
        """Every parsed workflow has the required keys."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: CI\non: [push]\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo\n")
        for wf in ci_workflows(tmp_path)["workflows"]:
            assert "file" in wf, f"Missing 'file' in workflow {wf}"
            assert "provider" in wf, f"Missing 'provider' in workflow {wf}"
            assert "name" in wf, f"Missing 'name' in workflow {wf}"
            assert "triggers" in wf, f"Missing 'triggers' in workflow {wf}"
            assert "jobs" in wf, f"Missing 'jobs' in workflow {wf}"
            assert "issues" in wf, f"Missing 'issues' in workflow {wf}"
            assert isinstance(wf["file"], str)
            assert isinstance(wf["provider"], str)
            assert isinstance(wf["triggers"], list)
            assert isinstance(wf["jobs"], list)
            assert isinstance(wf["issues"], list)


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
        """All 10 standard GitLab CI meta keys should be skipped."""
        gl = tmp_path / ".gitlab-ci.yml"
        gl.write_text(textwrap.dedent("""\
            stages: [a]
            variables:
              X: 1
            include: r.yml
            default:
              image: py
            image: node
            before_script:
              - echo setup
            after_script:
              - echo teardown
            workflow:
              rules:
                - if: $CI_PIPELINE_SOURCE == "push"
            cache:
              paths:
                - .cache/
            services:
              - postgres:latest
            real_job:
              script: echo
        """))
        result = _parse_gitlab_ci(gl, tmp_path)
        assert len(result["jobs"]) == 1
        assert result["jobs"][0]["id"] == "real_job"

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
