"""
Tests for generators/github_workflow — CI and lint workflow generation.

Pure unit tests: stack names in → GeneratedFile out.
No subprocess required.
"""

from pathlib import Path

import yaml

from src.core.services.generators.github_workflow import (
    generate_ci,
    generate_lint,
    _resolve_job,
    _python_ci_job,
    _node_ci_job,
    _go_ci_job,
    _rust_ci_job,
    _java_maven_ci_job,
    _java_gradle_ci_job,
)


# ═══════════════════════════════════════════════════════════════════
#  _resolve_job
# ═══════════════════════════════════════════════════════════════════


class TestResolveJob:
    def test_exact_python(self):
        assert _resolve_job("python") is _python_ci_job

    def test_exact_node(self):
        assert _resolve_job("node") is _node_ci_job

    def test_exact_typescript(self):
        assert _resolve_job("typescript") is _node_ci_job

    def test_exact_go(self):
        assert _resolve_job("go") is _go_ci_job

    def test_exact_rust(self):
        assert _resolve_job("rust") is _rust_ci_job

    def test_exact_java_maven(self):
        assert _resolve_job("java-maven") is _java_maven_ci_job

    def test_exact_java_gradle(self):
        assert _resolve_job("java-gradle") is _java_gradle_ci_job

    def test_prefix_python_flask(self):
        assert _resolve_job("python-flask") is _python_ci_job

    def test_prefix_node_express(self):
        assert _resolve_job("node-express") is _node_ci_job

    def test_prefix_go_gin(self):
        assert _resolve_job("go-gin") is _go_ci_job

    def test_unknown(self):
        assert _resolve_job("cobol") is None


# ═══════════════════════════════════════════════════════════════════
#  generate_ci
# ═══════════════════════════════════════════════════════════════════


class TestGenerateCi:
    def test_python(self, tmp_path: Path):
        r = generate_ci(tmp_path, ["python"])
        assert r is not None
        assert "pytest" in r.content
        assert "ruff" in r.content

    def test_node(self, tmp_path: Path):
        r = generate_ci(tmp_path, ["node"])
        assert r is not None
        assert "npm ci" in r.content

    def test_go(self, tmp_path: Path):
        r = generate_ci(tmp_path, ["go"])
        assert r is not None
        assert "go test" in r.content

    def test_rust(self, tmp_path: Path):
        r = generate_ci(tmp_path, ["rust"])
        assert r is not None
        assert "cargo test" in r.content

    def test_java_maven(self, tmp_path: Path):
        r = generate_ci(tmp_path, ["java-maven"])
        assert r is not None
        assert "mvn" in r.content

    def test_java_gradle(self, tmp_path: Path):
        r = generate_ci(tmp_path, ["java-gradle"])
        assert r is not None
        assert "gradlew" in r.content

    def test_multi_stack(self, tmp_path: Path):
        r = generate_ci(tmp_path, ["python", "node"])
        assert r is not None
        assert "pytest" in r.content
        assert "npm ci" in r.content

    def test_unknown_returns_none(self, tmp_path: Path):
        assert generate_ci(tmp_path, ["cobol"]) is None

    def test_empty_returns_none(self, tmp_path: Path):
        assert generate_ci(tmp_path, []) is None

    def test_project_name(self, tmp_path: Path):
        r = generate_ci(tmp_path, ["python"], project_name="my-project")
        assert "my-project CI" in r.content

    def test_no_project_name(self, tmp_path: Path):
        r = generate_ci(tmp_path, ["python"])
        assert "name: CI" in r.content

    def test_deduplication(self, tmp_path: Path):
        r = generate_ci(tmp_path, ["python", "python-flask"])
        assert r.content.count("name: Python") == 1

    def test_overwrite_false(self, tmp_path: Path):
        assert generate_ci(tmp_path, ["python"]).overwrite is False

    def test_reason_mentions_stacks(self, tmp_path: Path):
        r = generate_ci(tmp_path, ["python", "go"])
        assert "python" in r.reason
        assert "go" in r.reason

    def test_actions_pinned(self, tmp_path: Path):
        r = generate_ci(tmp_path, ["python"])
        for line in r.content.splitlines():
            s = line.strip()
            if s.startswith("- uses:") or s.startswith("uses:"):
                uses_val = s.split("uses:")[-1].strip()
                if uses_val and not uses_val.startswith("$"):
                    assert "@" in uses_val, f"Unpinned: {uses_val}"

    def test_permissions(self, tmp_path: Path):
        assert "permissions:" in generate_ci(tmp_path, ["python"]).content

    def test_valid_yaml(self, tmp_path: Path):
        r = generate_ci(tmp_path, ["python"])
        parsed = yaml.safe_load(r.content)
        assert isinstance(parsed, dict)
        assert "jobs" in parsed

    def test_path(self, tmp_path: Path):
        assert generate_ci(tmp_path, ["python"]).path == ".github/workflows/ci.yml"


# ═══════════════════════════════════════════════════════════════════
#  generate_lint
# ═══════════════════════════════════════════════════════════════════


class TestGenerateLint:
    def test_python(self, tmp_path: Path):
        r = generate_lint(tmp_path, ["python"])
        assert r is not None
        assert r.path == ".github/workflows/lint.yml"
        assert "ruff" in r.content
        assert "mypy" in r.content

    def test_node(self, tmp_path: Path):
        r = generate_lint(tmp_path, ["node"])
        assert r is not None
        assert "lint" in r.content.lower()

    def test_typescript(self, tmp_path: Path):
        assert generate_lint(tmp_path, ["typescript"]) is not None

    def test_unknown_returns_none(self, tmp_path: Path):
        assert generate_lint(tmp_path, ["cobol"]) is None

    def test_empty_returns_none(self, tmp_path: Path):
        assert generate_lint(tmp_path, []) is None

    def test_overwrite_false(self, tmp_path: Path):
        assert generate_lint(tmp_path, ["python"]).overwrite is False

    def test_valid_yaml(self, tmp_path: Path):
        parsed = yaml.safe_load(generate_lint(tmp_path, ["python"]).content)
        assert isinstance(parsed, dict)
