"""
Tests for CLI commands — status, config check, and global options.
"""

import json
import textwrap
from pathlib import Path

from click.testing import CliRunner

from src.main import cli


class TestCLIGlobal:
    """Tests for global CLI behavior."""

    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "DevOps Control Plane" in result.output

    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestStatusCommand:
    """Tests for the status command."""

    def _make_project(self, tmp_path: Path) -> Path:
        """Create a minimal project.yml for testing."""
        content = textwrap.dedent("""\
            name: test-project
            description: "A test project"
            repository: "github.com/test/project"
            environments:
              - name: dev
                default: true
            modules:
              - name: api
                path: src/api
                stack: python-fastapi
                domain: service
        """)
        config = tmp_path / "project.yml"
        config.write_text(content)
        # Create the module directory
        (tmp_path / "src" / "api").mkdir(parents=True)
        return config

    def test_status_with_project(self, tmp_path: Path):
        config = self._make_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(config), "status"])
        assert result.exit_code == 0
        assert "test-project" in result.output
        assert "api" in result.output

    def test_status_json(self, tmp_path: Path):
        config = self._make_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(config), "status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["project"]["name"] == "test-project"
        assert data["modules"]["total"] == 1

    def test_status_missing_config(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 1
        assert "No project.yml" in result.output

    def test_status_missing_config_json(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["status", "--json"])
        assert result.exit_code == 0  # JSON mode doesn't exit 1
        data = json.loads(result.output)
        assert "error" in data


class TestConfigCheckCommand:
    """Tests for the config check command."""

    def _make_project(self, tmp_path: Path, content: str | None = None) -> Path:
        if content is None:
            content = textwrap.dedent("""\
                name: test-project
                environments:
                  - name: dev
                    default: true
                modules:
                  - name: api
                    path: src/api
            """)
        config = tmp_path / "project.yml"
        config.write_text(content)
        return config

    def test_valid_config(self, tmp_path: Path):
        config = self._make_project(tmp_path)
        # Create module path to avoid warning
        (tmp_path / "src" / "api").mkdir(parents=True)
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(config), "config", "check"])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_valid_config_json(self, tmp_path: Path):
        config = self._make_project(tmp_path)
        (tmp_path / "src" / "api").mkdir(parents=True)
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(config), "config", "check", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["valid"] is True

    def test_missing_config(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "check"])
        assert result.exit_code == 1

    def test_warnings_shown(self, tmp_path: Path):
        # No modules = warning
        content = "name: test\n"
        config = self._make_project(tmp_path, content)
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(config), "config", "check"])
        assert result.exit_code == 0  # warnings don't fail
        assert "Warning" in result.output or "⚠" in result.output

    def test_duplicate_modules_fail(self, tmp_path: Path):
        content = textwrap.dedent("""\
            name: test
            modules:
              - name: api
                path: src/api
              - name: api
                path: src/api2
        """)
        config = self._make_project(tmp_path, content)
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(config), "config", "check"])
        assert result.exit_code == 1
        assert "Duplicate" in result.output

    def test_config_check_json_with_errors(self, tmp_path: Path):
        content = textwrap.dedent("""\
            name: test
            modules:
              - name: api
                path: src/api
              - name: api
                path: src/api2
        """)
        config = self._make_project(tmp_path, content)
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(config), "config", "check", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["valid"] is False
        assert len(data["errors"]) > 0
