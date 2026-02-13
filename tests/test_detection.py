"""
Tests for detection — stack matching, version extraction, module discovery.
"""

import json
import textwrap
from pathlib import Path

from click.testing import CliRunner

from src.core.config.stack_loader import discover_stacks, load_stack
from src.core.models.project import ModuleRef, Project
from src.core.models.stack import DetectionRule, Stack
from src.core.services.detection import (
    detect_language,
    detect_modules,
    detect_version,
    match_stack,
)
from src.main import cli

# ── Stack Loader Tests ───────────────────────────────────────────────


class TestStackLoader:
    def test_load_stack_from_yaml(self, tmp_path: Path):
        stack_file = tmp_path / "stack.yml"
        stack_file.write_text(textwrap.dedent("""\
            name: test-stack
            description: "Test stack"
            detection:
              files_any_of:
                - test.txt
            capabilities:
              - name: check
                command: "echo ok"
        """))
        stack = load_stack(stack_file)
        assert stack is not None
        assert stack.name == "test-stack"
        assert stack.has_capability("check")

    def test_load_invalid_stack(self, tmp_path: Path):
        stack_file = tmp_path / "stack.yml"
        stack_file.write_text("- not a mapping\n")
        stack = load_stack(stack_file)
        assert stack is None

    def test_discover_stacks(self, tmp_path: Path):
        # Create two stack dirs
        for name in ["alpha", "beta"]:
            d = tmp_path / name
            d.mkdir()
            (d / "stack.yml").write_text(f"name: {name}\n")

        stacks = discover_stacks(tmp_path)
        assert len(stacks) == 2
        assert "alpha" in stacks
        assert "beta" in stacks

    def test_discover_skips_non_dirs(self, tmp_path: Path):
        (tmp_path / "random.txt").write_text("not a stack")
        stacks = discover_stacks(tmp_path)
        assert len(stacks) == 0

    def test_discover_missing_dir(self, tmp_path: Path):
        stacks = discover_stacks(tmp_path / "nonexistent")
        assert len(stacks) == 0

    def test_load_real_stacks(self):
        """Load the actual stack definitions from the repo."""
        stacks_dir = Path(__file__).parent.parent / "stacks"
        if stacks_dir.is_dir():
            stacks = discover_stacks(stacks_dir)
            assert len(stacks) >= 3
            assert "python" in stacks
            assert "node" in stacks
            assert "docker-compose" in stacks


# ── Stack Matching Tests ─────────────────────────────────────────────


class TestMatchStack:
    def _make_stacks(self) -> dict[str, Stack]:
        return {
            "python": Stack(
                name="python",
                detection=DetectionRule(files_any_of=["pyproject.toml", "setup.py"]),
            ),
            "node": Stack(
                name="node",
                detection=DetectionRule(files_any_of=["package.json"]),
            ),
            "docker": Stack(
                name="docker-compose",
                detection=DetectionRule(
                    files_any_of=["docker-compose.yml", "compose.yml"]
                ),
            ),
        }

    def test_match_python(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
        result = match_stack(tmp_path, self._make_stacks())
        assert result is not None
        assert result.name == "python"

    def test_match_node(self, tmp_path: Path):
        (tmp_path / "package.json").write_text('{"name": "test"}')
        result = match_stack(tmp_path, self._make_stacks())
        assert result is not None
        assert result.name == "node"

    def test_match_docker_compose(self, tmp_path: Path):
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")
        result = match_stack(tmp_path, self._make_stacks())
        assert result is not None
        assert result.name == "docker-compose"

    def test_no_match(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("# Hello")
        result = match_stack(tmp_path, self._make_stacks())
        assert result is None

    def test_match_content_contains(self, tmp_path: Path):
        stacks = {
            "fastapi": Stack(
                name="fastapi",
                detection=DetectionRule(
                    files_any_of=["pyproject.toml"],
                    content_contains={"pyproject.toml": "fastapi"},
                ),
            ),
        }
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname="test"\ndependencies=["fastapi"]\n'
        )
        result = match_stack(tmp_path, stacks)
        assert result is not None
        assert result.name == "fastapi"

    def test_content_contains_no_match(self, tmp_path: Path):
        stacks = {
            "fastapi": Stack(
                name="fastapi",
                detection=DetectionRule(
                    files_any_of=["pyproject.toml"],
                    content_contains={"pyproject.toml": "fastapi"},
                ),
            ),
        }
        (tmp_path / "pyproject.toml").write_text('[project]\nname="test"\n')
        result = match_stack(tmp_path, stacks)
        assert result is None

    def test_match_files_all_of(self, tmp_path: Path):
        stacks = {
            "strict": Stack(
                name="strict",
                detection=DetectionRule(
                    files_all_of=["Makefile", "pyproject.toml"],
                ),
            ),
        }
        (tmp_path / "Makefile").write_text("all:")
        (tmp_path / "pyproject.toml").write_text("[project]")
        result = match_stack(tmp_path, stacks)
        assert result is not None

    def test_files_all_of_partial(self, tmp_path: Path):
        stacks = {
            "strict": Stack(
                name="strict",
                detection=DetectionRule(
                    files_all_of=["Makefile", "pyproject.toml"],
                ),
            ),
        }
        (tmp_path / "Makefile").write_text("all:")
        # Missing pyproject.toml
        result = match_stack(tmp_path, stacks)
        assert result is None


# ── Version Detection Tests ──────────────────────────────────────────


class TestDetectVersion:
    def test_python_version(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\nversion = "1.2.3"\n'
        )
        version = detect_version(tmp_path, "python")
        assert version == "1.2.3"

    def test_node_version(self, tmp_path: Path):
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "test", "version": "4.5.6"})
        )
        version = detect_version(tmp_path, "node")
        assert version == "4.5.6"

    def test_no_version_files(self, tmp_path: Path):
        version = detect_version(tmp_path, "unknown")
        assert version is None


# ── Language Detection Tests ─────────────────────────────────────────


class TestDetectLanguage:
    def test_python(self):
        assert detect_language("python") == "python"
        assert detect_language("python-fastapi") == "python"

    def test_node(self):
        assert detect_language("node") == "javascript"
        assert detect_language("node-nextjs") == "javascript"

    def test_unknown(self):
        assert detect_language("unknown-stack") is None


# ── Module Detection Tests ───────────────────────────────────────────


class TestDetectModules:
    def _make_project(self, tmp_path: Path) -> tuple[Project, dict[str, Stack]]:
        """Create a test project with fixture directories."""
        # Create module directories
        api_dir = tmp_path / "services" / "api"
        api_dir.mkdir(parents=True)
        (api_dir / "pyproject.toml").write_text(
            '[project]\nname = "api"\nversion = "2.0.0"\n'
        )

        web_dir = tmp_path / "services" / "web"
        web_dir.mkdir(parents=True)
        (web_dir / "package.json").write_text(
            json.dumps({"name": "web", "version": "1.0.0"})
        )

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "README.md").write_text("# Docs")

        project = Project(
            name="test-project",
            modules=[
                ModuleRef(name="api", path="services/api", stack="python"),
                ModuleRef(name="web", path="services/web", stack="node"),
                ModuleRef(name="docs", path="docs", stack="markdown"),
                ModuleRef(name="missing", path="services/missing", stack="python"),
            ],
        )

        stacks = {
            "python": Stack(
                name="python",
                detection=DetectionRule(files_any_of=["pyproject.toml", "setup.py"]),
            ),
            "node": Stack(
                name="node",
                detection=DetectionRule(files_any_of=["package.json"]),
            ),
        }

        return project, stacks

    def test_detect_all_modules(self, tmp_path: Path):
        project, stacks = self._make_project(tmp_path)
        result = detect_modules(project, tmp_path, stacks)
        assert result.total_modules == 4
        assert result.total_detected == 3  # docs exists but no stack match
        assert "missing" in result.unmatched_refs

    def test_detect_python_module(self, tmp_path: Path):
        project, stacks = self._make_project(tmp_path)
        result = detect_modules(project, tmp_path, stacks)
        api = result.get_module("api")
        assert api is not None
        assert api.detected is True
        assert api.detected_stack == "python"
        assert api.version == "2.0.0"
        assert api.language == "python"

    def test_detect_node_module(self, tmp_path: Path):
        project, stacks = self._make_project(tmp_path)
        result = detect_modules(project, tmp_path, stacks)
        web = result.get_module("web")
        assert web is not None
        assert web.detected is True
        assert web.detected_stack == "node"
        assert web.version == "1.0.0"

    def test_missing_module_tracked(self, tmp_path: Path):
        project, stacks = self._make_project(tmp_path)
        result = detect_modules(project, tmp_path, stacks)
        missing = result.get_module("missing")
        assert missing is not None
        assert missing.detected is False

    def test_to_dict(self, tmp_path: Path):
        project, stacks = self._make_project(tmp_path)
        result = detect_modules(project, tmp_path, stacks)
        d = result.to_dict()
        assert d["total"] == 4
        assert d["detected"] == 3
        assert len(d["modules"]) == 4


# ── CLI Detect Command Tests ────────────────────────────────────────


class TestDetectCLI:
    def _setup_project(self, tmp_path: Path) -> Path:
        """Create a project with stacks and modules for CLI testing."""
        config = tmp_path / "project.yml"
        config.write_text(textwrap.dedent("""\
            name: cli-test
            modules:
              - name: api
                path: src/api
                stack: python
        """))

        # Module dir with pyproject.toml
        api_dir = tmp_path / "src" / "api"
        api_dir.mkdir(parents=True)
        (api_dir / "pyproject.toml").write_text(
            '[project]\nname = "api"\nversion = "1.0.0"\n'
        )

        # Stack definition
        stack_dir = tmp_path / "stacks" / "python"
        stack_dir.mkdir(parents=True)
        (stack_dir / "stack.yml").write_text(textwrap.dedent("""\
            name: python
            detection:
              files_any_of:
                - pyproject.toml
            capabilities:
              - name: test
                command: pytest
        """))

        return config

    def test_detect_command(self, tmp_path: Path):
        config = self._setup_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(config), "detect", "--no-save"])
        assert result.exit_code == 0
        assert "api" in result.output
        assert "python" in result.output

    def test_detect_json(self, tmp_path: Path):
        config = self._setup_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--config", str(config), "detect", "--json", "--no-save"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["detection"]["detected"] == 1
        assert data["stacks_loaded"] == 1

    def test_detect_saves_state(self, tmp_path: Path):
        config = self._setup_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(config), "detect"])
        assert result.exit_code == 0
        assert (tmp_path / ".state" / "current.json").is_file()

    def test_detect_then_status(self, tmp_path: Path):
        """After detection, status shows detected markers."""
        config = self._setup_project(tmp_path)
        runner = CliRunner()

        # Run detect first
        runner.invoke(cli, ["--config", str(config), "detect"])

        # Then check status
        result = runner.invoke(cli, ["--config", str(config), "status"])
        assert result.exit_code == 0
        assert "✓" in result.output  # detection marker
