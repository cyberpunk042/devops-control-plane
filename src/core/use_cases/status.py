"""
Status use case — aggregate project status from config + state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.core.config.loader import ConfigError, find_project_file, load_project
from src.core.models.project import Project
from src.core.models.state import ProjectState
from src.core.persistence.state_file import default_state_path, load_state


@dataclass
class StatusResult:
    """Aggregated project status."""

    project: Project | None = None
    state: ProjectState | None = None
    project_root: Path | None = None
    config_path: Path | None = None
    error: str | None = None

    # Summary counts
    module_count: int = 0
    environment_count: int = 0
    detected_count: int = 0
    current_environment: str = "dev"

    def to_dict(self) -> dict:
        """Convert to a JSON-serializable dictionary."""
        result: dict = {}
        if self.error:
            result["error"] = self.error
            return result

        result["project"] = {
            "name": self.project.name if self.project else "",
            "description": self.project.description if self.project else "",
            "repository": self.project.repository if self.project else "",
        }
        result["config_path"] = str(self.config_path) if self.config_path else None
        result["project_root"] = str(self.project_root) if self.project_root else None
        result["current_environment"] = self.current_environment
        result["modules"] = {
            "total": self.module_count,
            "detected": self.detected_count,
        }
        result["environments"] = self.environment_count

        if self.project:
            result["module_list"] = [
                {"name": m.name, "path": m.path, "stack": m.stack, "domain": m.domain}
                for m in self.project.modules
            ]
            result["environment_list"] = [
                {"name": e.name, "default": e.default}
                for e in self.project.environments
            ]

        if self.state and self.state.last_operation.operation_id:
            result["last_operation"] = {
                "id": self.state.last_operation.operation_id,
                "type": self.state.last_operation.automation,
                "status": self.state.last_operation.status,
                "at": self.state.last_operation.ended_at,
            }

        return result


def get_status(config_path: Path | None = None) -> StatusResult:
    """Get full project status.

    Args:
        config_path: Optional explicit path to project.yml.

    Returns:
        StatusResult with project info, state, and summaries.
    """
    result = StatusResult()

    # Find and load config
    try:
        if config_path is None:
            config_path = find_project_file()

        if config_path is None:
            result.error = "No project.yml found. Run 'controlplane init' to create one."
            return result

        project = load_project(config_path)
        result.project = project
        result.config_path = config_path
        result.project_root = config_path.parent.resolve()

    except ConfigError as e:
        result.error = str(e)
        return result

    # Load state
    state_path = default_state_path(result.project_root)
    state = load_state(state_path)
    result.state = state

    # Compute summaries
    result.module_count = len(project.modules)
    result.environment_count = len(project.environments)
    result.current_environment = state.current_environment
    result.detected_count = sum(
        1 for ms in state.modules.values() if ms.detected
    )

    return result
