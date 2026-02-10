"""
Config check use case — validate project.yml and report issues.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.core.config.loader import ConfigError, find_project_file, load_project
from src.core.models.project import Project


@dataclass
class ConfigCheckResult:
    """Result of configuration validation."""

    valid: bool = False
    project: Project | None = None
    config_path: Path | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "config_path": str(self.config_path) if self.config_path else None,
            "errors": self.errors,
            "warnings": self.warnings,
            "project_name": self.project.name if self.project else None,
            "module_count": len(self.project.modules) if self.project else 0,
            "environment_count": len(self.project.environments) if self.project else 0,
        }


def check_config(config_path: Path | None = None) -> ConfigCheckResult:
    """Validate project configuration and report issues.

    Args:
        config_path: Optional explicit path to project.yml.

    Returns:
        ConfigCheckResult with validation status and any issues.
    """
    result = ConfigCheckResult()

    # Find config
    try:
        if config_path is None:
            config_path = find_project_file()

        if config_path is None:
            result.errors.append("No project.yml found.")
            return result

        result.config_path = config_path

    except ConfigError as e:
        result.errors.append(str(e))
        return result

    # Load and validate
    try:
        project = load_project(config_path)
        result.project = project
    except ConfigError as e:
        result.errors.append(str(e))
        return result

    # Semantic checks
    if not project.environments:
        result.warnings.append("No environments defined. Consider adding at least 'dev'.")

    if not project.modules:
        result.warnings.append("No modules defined. The project has nothing to manage.")

    # Check for duplicate module names
    names = [m.name for m in project.modules]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        result.errors.append(f"Duplicate module names: {', '.join(sorted(dupes))}")

    # Check for duplicate environment names
    env_names = [e.name for e in project.environments]
    env_dupes = {n for n in env_names if env_names.count(n) > 1}
    if env_dupes:
        result.errors.append(f"Duplicate environment names: {', '.join(sorted(env_dupes))}")

    # Check default environment count
    defaults = [e for e in project.environments if e.default]
    if len(defaults) > 1:
        result.warnings.append(
            f"Multiple default environments: {', '.join(e.name for e in defaults)}. "
            "Only the first will be used."
        )

    # Check module paths exist (relative to project root)
    project_root = config_path.parent
    for mod in project.modules:
        mod_path = project_root / mod.path
        if not mod_path.exists():
            result.warnings.append(f"Module '{mod.name}' path does not exist: {mod.path}")

    # Result
    result.valid = len(result.errors) == 0
    return result
