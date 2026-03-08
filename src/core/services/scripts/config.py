"""
Scripts config I/O — load and save ScriptConfig from project.yml.

Reads the scripts: section from project.yml and maps it to a
ScriptConfig dataclass. Falls back to sensible defaults if the
section is missing.

Same pattern as artifacts/engine.py: _load_project_yml() → get section.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.core.services.scripts.models import ScriptConfig


def load_scripts_config(project_root: Path) -> ScriptConfig:
    """Load scripts configuration from project.yml.

    Falls back to sensible defaults if section is missing.
    Same pattern as artifacts: _load_project_yml() → _get_section().

    Returns:
        ScriptConfig with values from project.yml, or defaults.
    """
    yml = project_root / "project.yml"
    if not yml.is_file():
        return ScriptConfig()

    data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
    scripts_data = data.get("scripts", {})
    if not scripts_data:
        return ScriptConfig()

    history = scripts_data.get("history", {})
    execution = scripts_data.get("execution", {})

    return ScriptConfig(
        root=scripts_data.get("root", "scripts"),
        template_source=scripts_data.get("template_source", "auto"),
        default_output=scripts_data.get("default_output", "scripts/output"),
        history_max_runs=history.get("max_runs", 100),
        history_persist_output=history.get("persist_output", True),
        execution_default_timeout=execution.get("default_timeout", 300),
        execution_parallel=execution.get("parallel", False),
        execution_venv_python=execution.get("venv_python", "auto"),
        categories=scripts_data.get("categories", [
            "audit", "generator", "analyzer", "debug", "ops", "general",
        ]),
    )


def save_scripts_config(project_root: Path, config: ScriptConfig) -> None:
    """Write scripts configuration to project.yml.

    Creates the scripts: section if it doesn't exist.
    Preserves all other sections in the file.
    """
    yml = project_root / "project.yml"
    data: dict = {}
    if yml.is_file():
        data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}

    data["scripts"] = {
        "root": config.root,
        "template_source": config.template_source,
        "default_output": config.default_output,
        "history": {
            "max_runs": config.history_max_runs,
            "persist_output": config.history_persist_output,
        },
        "execution": {
            "default_timeout": config.execution_default_timeout,
            "parallel": config.execution_parallel,
            "venv_python": config.execution_venv_python,
        },
        "categories": config.categories,
    }

    yml.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
