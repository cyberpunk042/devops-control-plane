"""
Tests for scripts config I/O — load/save from project.yml.

Covers:
- No project.yml → returns defaults
- project.yml without scripts: → returns defaults
- project.yml with scripts: → returns configured values
- Partial scripts: section → missing fields get defaults
- save_scripts_config → writes proper YAML, preserves other sections
- Nested history and execution subsections
"""

import yaml

from src.core.services.scripts.config import load_scripts_config, save_scripts_config
from src.core.services.scripts.models import ScriptConfig


class TestLoadScriptsConfig:
    """Config loading tests."""

    def test_no_project_yml(self, tmp_path):
        """No project.yml file → returns defaults."""
        config = load_scripts_config(tmp_path)
        assert config.root == "scripts"
        assert config.template_source == "auto"
        assert config.default_output == "scripts/output"
        assert config.history_max_runs == 100
        assert config.execution_default_timeout == 300

    def test_empty_project_yml(self, tmp_path):
        """Empty project.yml → returns defaults."""
        (tmp_path / "project.yml").write_text("", encoding="utf-8")
        config = load_scripts_config(tmp_path)
        assert config.root == "scripts"

    def test_project_yml_without_scripts_section(self, tmp_path):
        """project.yml exists but has no scripts: section → returns defaults."""
        yml_data = {"version": 1, "name": "test-project"}
        (tmp_path / "project.yml").write_text(
            yaml.dump(yml_data), encoding="utf-8",
        )
        config = load_scripts_config(tmp_path)
        assert config.root == "scripts"
        assert config.template_source == "auto"

    def test_full_scripts_section(self, tmp_path):
        """project.yml with full scripts: section → returns configured values."""
        yml_data = {
            "version": 1,
            "name": "test-project",
            "scripts": {
                "root": "ops/scripts",
                "template_source": "always",
                "default_output": "output/reports",
                "history": {
                    "max_runs": 50,
                    "persist_output": False,
                },
                "execution": {
                    "default_timeout": 600,
                    "parallel": True,
                    "venv_python": "/usr/bin/python3",
                },
                "categories": ["audit", "ops"],
            },
        }
        (tmp_path / "project.yml").write_text(
            yaml.dump(yml_data, default_flow_style=False), encoding="utf-8",
        )
        config = load_scripts_config(tmp_path)
        assert config.root == "ops/scripts"
        assert config.template_source == "always"
        assert config.default_output == "output/reports"
        assert config.history_max_runs == 50
        assert config.history_persist_output is False
        assert config.execution_default_timeout == 600
        assert config.execution_parallel is True
        assert config.execution_venv_python == "/usr/bin/python3"
        assert config.categories == ["audit", "ops"]

    def test_partial_scripts_section(self, tmp_path):
        """Partial scripts: section → missing fields get defaults."""
        yml_data = {
            "version": 1,
            "scripts": {
                "root": "my-scripts",
            },
        }
        (tmp_path / "project.yml").write_text(
            yaml.dump(yml_data, default_flow_style=False), encoding="utf-8",
        )
        config = load_scripts_config(tmp_path)
        assert config.root == "my-scripts"
        # All others should be defaults
        assert config.template_source == "auto"
        assert config.default_output == "scripts/output"
        assert config.history_max_runs == 100
        assert config.history_persist_output is True
        assert config.execution_default_timeout == 300
        assert config.execution_parallel is False
        assert config.execution_venv_python == "auto"
        assert "ops" in config.categories  # default includes ops

    def test_partial_history_section(self, tmp_path):
        """scripts: with partial history: → missing history fields get defaults."""
        yml_data = {
            "scripts": {
                "root": "scripts",
                "history": {
                    "max_runs": 25,
                    # persist_output missing → defaults to True
                },
            },
        }
        (tmp_path / "project.yml").write_text(
            yaml.dump(yml_data, default_flow_style=False), encoding="utf-8",
        )
        config = load_scripts_config(tmp_path)
        assert config.history_max_runs == 25
        assert config.history_persist_output is True

    def test_partial_execution_section(self, tmp_path):
        """scripts: with partial execution: → missing execution fields get defaults."""
        yml_data = {
            "scripts": {
                "root": "scripts",
                "execution": {
                    "default_timeout": 60,
                    # parallel and venv_python missing → defaults
                },
            },
        }
        (tmp_path / "project.yml").write_text(
            yaml.dump(yml_data, default_flow_style=False), encoding="utf-8",
        )
        config = load_scripts_config(tmp_path)
        assert config.execution_default_timeout == 60
        assert config.execution_parallel is False
        assert config.execution_venv_python == "auto"


class TestSaveScriptsConfig:
    """Config saving tests."""

    def test_save_creates_section(self, tmp_path):
        """save_scripts_config creates the scripts: section."""
        yml_data = {"version": 1, "name": "test-project"}
        yml_path = tmp_path / "project.yml"
        yml_path.write_text(
            yaml.dump(yml_data, default_flow_style=False), encoding="utf-8",
        )

        config = ScriptConfig(root="my-scripts", template_source="never")
        save_scripts_config(tmp_path, config)

        data = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
        assert "scripts" in data
        assert data["scripts"]["root"] == "my-scripts"
        assert data["scripts"]["template_source"] == "never"

    def test_save_preserves_other_sections(self, tmp_path):
        """save_scripts_config preserves existing sections."""
        yml_data = {
            "version": 1,
            "name": "test-project",
            "artifacts": {"targets": []},
        }
        yml_path = tmp_path / "project.yml"
        yml_path.write_text(
            yaml.dump(yml_data, default_flow_style=False), encoding="utf-8",
        )

        save_scripts_config(tmp_path, ScriptConfig())

        data = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert data["name"] == "test-project"
        assert data["artifacts"] == {"targets": []}
        assert "scripts" in data

    def test_save_writes_nested_sections(self, tmp_path):
        """save_scripts_config writes history and execution subsections."""
        yml_path = tmp_path / "project.yml"
        yml_path.write_text("version: 1\n", encoding="utf-8")

        config = ScriptConfig(
            history_max_runs=25,
            history_persist_output=False,
            execution_default_timeout=60,
            execution_parallel=True,
            execution_venv_python="/opt/python/bin/python3",
        )
        save_scripts_config(tmp_path, config)

        data = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
        assert data["scripts"]["history"]["max_runs"] == 25
        assert data["scripts"]["history"]["persist_output"] is False
        assert data["scripts"]["execution"]["default_timeout"] == 60
        assert data["scripts"]["execution"]["parallel"] is True
        assert data["scripts"]["execution"]["venv_python"] == "/opt/python/bin/python3"

    def test_save_creates_file_if_missing(self, tmp_path):
        """save_scripts_config creates project.yml if it doesn't exist."""
        save_scripts_config(tmp_path, ScriptConfig())

        yml_path = tmp_path / "project.yml"
        assert yml_path.is_file()
        data = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
        assert data["scripts"]["root"] == "scripts"

    def test_save_overwrites_existing_scripts_section(self, tmp_path):
        """save_scripts_config overwrites the existing scripts: section."""
        yml_data = {
            "version": 1,
            "scripts": {
                "root": "old-scripts",
                "template_source": "never",
            },
        }
        yml_path = tmp_path / "project.yml"
        yml_path.write_text(
            yaml.dump(yml_data, default_flow_style=False), encoding="utf-8",
        )

        save_scripts_config(tmp_path, ScriptConfig(root="new-scripts"))

        data = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
        assert data["scripts"]["root"] == "new-scripts"
        assert data["scripts"]["template_source"] == "auto"  # default, not "never"

    def test_roundtrip(self, tmp_path):
        """save → load returns the same config."""
        original = ScriptConfig(
            root="my-scripts",
            template_source="always",
            default_output="reports/",
            history_max_runs=50,
            history_persist_output=False,
            execution_default_timeout=600,
            execution_parallel=True,
            execution_venv_python="/usr/bin/python3",
            categories=["audit", "ops", "debug"],
        )

        save_scripts_config(tmp_path, original)
        loaded = load_scripts_config(tmp_path)

        assert loaded.root == original.root
        assert loaded.template_source == original.template_source
        assert loaded.default_output == original.default_output
        assert loaded.history_max_runs == original.history_max_runs
        assert loaded.history_persist_output == original.history_persist_output
        assert loaded.execution_default_timeout == original.execution_default_timeout
        assert loaded.execution_parallel == original.execution_parallel
        assert loaded.execution_venv_python == original.execution_venv_python
        assert loaded.categories == original.categories
