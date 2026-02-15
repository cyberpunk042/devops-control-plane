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

        if self.project:
            result["modules"] = [
                {"name": m.name, "path": m.path, "domain": m.domain, "stack": m.stack}
                for m in self.project.modules
            ]
            result["environments"] = [
                {"name": e.name, "default": e.default}
                for e in self.project.environments
            ]

        if self.state:
            result["state"] = {
                "project_name": self.state.project_name,
                "last_operation": {
                    "operation_id": self.state.last_operation.operation_id,
                    "automation": self.state.last_operation.automation,
                    "status": self.state.last_operation.status,
                    "actions_total": self.state.last_operation.actions_total,
                    "actions_succeeded": self.state.last_operation.actions_succeeded,
                    "actions_failed": self.state.last_operation.actions_failed,
                },
                "modules": {
                    name: {
                        "last_action_status": ms.last_action_status,
                        "last_action_at": ms.last_action_at,
                    }
                    for name, ms in self.state.modules.items()
                },
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


def get_capabilities(
    config_path: Path | None = None,
    project_root: Path | None = None,
) -> dict:
    """Resolve capabilities per module.

    Cross-references modules with their stacks and returns a
    map of capability → which modules support it and with what command.

    Returns:
        {capability_name: {name, description, modules: [...]}, ...}
        or {"error": "..."} on failure.
    """
    from src.core.config.stack_loader import discover_stacks
    from src.core.engine.executor import _resolve_stack

    if config_path is None:
        config_path = find_project_file(project_root)
    if config_path is None:
        return {"error": "No project.yml found"}

    project = load_project(config_path)
    root = project_root or config_path.parent.resolve()
    stacks_dir = root / "stacks"
    stacks = discover_stacks(stacks_dir)

    capabilities: dict[str, dict] = {}

    for m in project.modules:
        stack_name = m.stack or ""
        stack = _resolve_stack(stack_name, stacks) if stack_name else None
        if stack is None:
            continue

        for cap in stack.capabilities:
            if cap.name not in capabilities:
                capabilities[cap.name] = {
                    "name": cap.name,
                    "description": cap.description,
                    "modules": [],
                }
            capabilities[cap.name]["modules"].append({
                "module": m.name,
                "stack": stack.name,
                "command": cap.command,
                "adapter": cap.adapter or "shell",
            })

    return capabilities
