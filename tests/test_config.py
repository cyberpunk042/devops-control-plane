"""
Tests for configuration loading — project.yml parsing and validation.
"""

import textwrap
from pathlib import Path

import pytest

from src.core.config.loader import ConfigError, find_project_file, load_project


@pytest.fixture
def valid_project_yml(tmp_path: Path) -> Path:
    """Create a valid project.yml in a temp directory."""
    content = textwrap.dedent("""\
        version: 1
        name: test-project
        description: "A test project"
        repository: "github.com/test/project"

        domains:
          - service
          - library

        environments:
          - name: dev
            description: "Development"
            default: true
          - name: prod
            description: "Production"

        modules:
          - name: api
            path: services/api
            domain: service
            stack: python-fastapi
          - name: lib
            path: libs/common
            domain: library
            stack: python-lib

        external:
          ci: github-actions
          registry: ghcr.io
    """)
    path = tmp_path / "project.yml"
    path.write_text(content)
    return path


@pytest.fixture
def wrapped_project_yml(tmp_path: Path) -> Path:
    """Create a project.yml with content under a 'project:' key."""
    content = textwrap.dedent("""\
        version: 1
        project:
          name: wrapped-project
          description: "Wrapped format"
        domains:
          - ops
        modules:
          - name: cli
            path: src/cli
    """)
    path = tmp_path / "project.yml"
    path.write_text(content)
    return path


@pytest.fixture
def minimal_project_yml(tmp_path: Path) -> Path:
    """Create a minimal project.yml with just a name."""
    content = "name: minimal\n"
    path = tmp_path / "project.yml"
    path.write_text(content)
    return path


class TestLoadProject:
    """Tests for load_project()."""

    def test_load_valid_config(self, valid_project_yml: Path):
        project = load_project(valid_project_yml)
        assert project.name == "test-project"
        assert project.description == "A test project"
        assert len(project.modules) == 2
        assert len(project.environments) == 2
        assert project.external.ci == "github-actions"

    def test_load_minimal_config(self, minimal_project_yml: Path):
        project = load_project(minimal_project_yml)
        assert project.name == "minimal"
        assert project.modules == []

    def test_load_wrapped_format(self, wrapped_project_yml: Path):
        """project.yml with a 'project:' wrapper key should work."""
        project = load_project(wrapped_project_yml)
        assert project.name == "wrapped-project"

    def test_modules_populated(self, valid_project_yml: Path):
        project = load_project(valid_project_yml)
        api = project.get_module("api")
        assert api is not None
        assert api.stack == "python-fastapi"
        assert api.domain == "service"

    def test_environments_populated(self, valid_project_yml: Path):
        project = load_project(valid_project_yml)
        dev = project.get_environment("dev")
        assert dev is not None
        assert dev.default is True

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(ConfigError, match="not found"):
            load_project(tmp_path / "nonexistent.yml")

    def test_invalid_yaml_raises(self, tmp_path: Path):
        path = tmp_path / "project.yml"
        path.write_text(":: invalid: yaml: [")
        with pytest.raises(ConfigError, match="Invalid YAML"):
            load_project(path)

    def test_non_mapping_raises(self, tmp_path: Path):
        path = tmp_path / "project.yml"
        path.write_text("- just\n- a\n- list\n")
        with pytest.raises(ConfigError, match="Expected a YAML mapping"):
            load_project(path)

    def test_missing_name_raises(self, tmp_path: Path):
        path = tmp_path / "project.yml"
        path.write_text("description: no name here\n")
        with pytest.raises(ConfigError, match="Invalid project configuration"):
            load_project(path)

    def test_auto_search_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """When no project.yml exists anywhere, raise ConfigError."""
        # Use an isolated temp dir so we don't find the repo's real project.yml
        isolated = tmp_path / "isolated"
        isolated.mkdir()
        monkeypatch.chdir(isolated)
        with pytest.raises(ConfigError, match=r"No project\.yml found"):
            load_project(None)


class TestFindProjectFile:
    """Tests for find_project_file()."""

    def test_find_in_current_dir(self, tmp_path: Path):
        (tmp_path / "project.yml").write_text("name: test\n")
        result = find_project_file(tmp_path)
        assert result is not None
        assert result.name == "project.yml"

    def test_find_in_parent_dir(self, tmp_path: Path):
        (tmp_path / "project.yml").write_text("name: test\n")
        subdir = tmp_path / "src" / "core"
        subdir.mkdir(parents=True)
        result = find_project_file(subdir)
        assert result is not None
        assert result.parent == tmp_path

    def test_not_found_returns_none(self, tmp_path: Path):
        subdir = tmp_path / "deep" / "nested"
        subdir.mkdir(parents=True)
        result = find_project_file(subdir)
        assert result is None
