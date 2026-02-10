"""
Configuration loader — reads project.yml into domain models.

This is the primary entry point for loading project configuration.
It reads YAML, validates against Pydantic schemas, and returns
typed domain objects.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from src.core.models.project import Project

logger = logging.getLogger(__name__)

# Default config filename
PROJECT_CONFIG_FILE = "project.yml"


class ConfigError(Exception):
    """Raised when project configuration is invalid or missing."""


def find_project_file(start_dir: Path | None = None) -> Path | None:
    """Search for project.yml starting from the given directory, walking up.

    This allows running commands from subdirectories and still finding
    the project root.

    Args:
        start_dir: Directory to start searching from (default: cwd).

    Returns:
        Path to project.yml, or None if not found.
    """
    current = (start_dir or Path.cwd()).resolve()

    for _ in range(20):  # safety limit
        candidate = current / PROJECT_CONFIG_FILE
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            break  # filesystem root
        current = parent

    return None


def load_project(path: Path | None = None) -> Project:
    """Load and validate project configuration.

    Args:
        path: Explicit path to project.yml. If None, searches upward.

    Returns:
        Validated Project model.

    Raises:
        ConfigError: If the file is missing or invalid.
    """
    if path is None:
        path = find_project_file()

    if path is None:
        raise ConfigError(
            f"No {PROJECT_CONFIG_FILE} found. "
            "Run 'controlplane init' to create one, or specify --config."
        )

    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")

    logger.debug("Loading project config from %s", path)

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"Cannot read {path}: {e}") from e

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {path}: {e}") from e

    if not isinstance(data, dict):
        raise ConfigError(f"Expected a YAML mapping in {path}, got {type(data).__name__}")

    # The YAML may wrap everything under a "project" key or be flat
    project_data = data.get("project", data) if "project" in data else data

    # Merge top-level keys that sit alongside "project"
    for key in ("version", "domains", "environments", "modules", "external"):
        if key in data and key not in project_data:
            project_data[key] = data[key]

    try:
        project = Project.model_validate(project_data)
    except Exception as e:
        raise ConfigError(f"Invalid project configuration: {e}") from e

    logger.info("Loaded project '%s' with %d modules", project.name, len(project.modules))
    return project


def project_root(config_path: Path) -> Path:
    """Get the project root directory from a config file path."""
    return config_path.parent.resolve()
