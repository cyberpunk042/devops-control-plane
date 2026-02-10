"""
Detection use case — orchestrate module discovery.

Ties together config loading, stack discovery, detection service,
and state persistence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path

from src.core.config.loader import ConfigError, find_project_file, load_project
from src.core.config.stack_loader import discover_stacks
from src.core.models.project import Project
from src.core.persistence.state_file import default_state_path, load_state, save_state
from src.core.services.detection import DetectionResult, detect_modules

logger = logging.getLogger(__name__)


@dataclass
class DetectResult:
    """Result of the detect use case."""

    detection: DetectionResult | None = None
    project: Project | None = None
    project_root: Path | None = None
    stacks_loaded: int = 0
    state_saved: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        result: dict = {}
        if self.error:
            result["error"] = self.error
            return result

        result["project_name"] = self.project.name if self.project else ""
        result["project_root"] = str(self.project_root)
        result["stacks_loaded"] = self.stacks_loaded
        result["state_saved"] = self.state_saved

        if self.detection:
            result["detection"] = self.detection.to_dict()

        return result


def run_detect(
    config_path: Path | None = None,
    stacks_dir: Path | None = None,
    save: bool = True,
) -> DetectResult:
    """Run module detection on the project.

    Args:
        config_path: Optional explicit path to project.yml.
        stacks_dir: Optional override for stacks directory.
        save: Whether to save detection results to state file.

    Returns:
        DetectResult with detection findings.
    """
    result = DetectResult()

    # Load project config
    try:
        if config_path is None:
            config_path = find_project_file()
        if config_path is None:
            result.error = "No project.yml found."
            return result

        project = load_project(config_path)
        result.project = project
        result.project_root = config_path.parent.resolve()

    except ConfigError as e:
        result.error = str(e)
        return result

    project_root = result.project_root
    assert project_root is not None

    # Discover stacks
    if stacks_dir is None:
        stacks_dir = project_root / "stacks"
    stacks = discover_stacks(stacks_dir)
    result.stacks_loaded = len(stacks)

    # Run detection
    detection = detect_modules(project, project_root, stacks)
    result.detection = detection

    # Persist to state
    if save:
        state_path = default_state_path(project_root)
        state = load_state(state_path)
        state.project_name = project.name

        from datetime import datetime

        state.last_detection_at = datetime.now(UTC).isoformat()

        for module in detection.modules:
            state.set_module_state(
                module.name,
                detected=module.detected,
                stack=module.effective_stack,
                version=module.version,
            )

        save_state(state, state_path)
        result.state_saved = True

    return result
