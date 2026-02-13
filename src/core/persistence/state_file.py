"""
State file persistence — atomic read/write for ProjectState.

State is stored as JSON in .state/current.json. Writes are atomic
(write to temp file, then rename) to prevent corruption if the
process crashes mid-write.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from src.core.models.state import ProjectState

logger = logging.getLogger(__name__)

# Default state file path (relative to project root)
DEFAULT_STATE_DIR = ".state"
DEFAULT_STATE_FILE = "current.json"


def default_state_path(project_root: Path) -> Path:
    """Get the default state file path for a project."""
    return project_root / DEFAULT_STATE_DIR / DEFAULT_STATE_FILE


def load_state(path: Path) -> ProjectState:
    """Load project state from a JSON file.

    Args:
        path: Path to the state JSON file.

    Returns:
        ProjectState model. If the file doesn't exist, returns a fresh state.
    """
    if not path.is_file():
        logger.info("No state file at %s — starting fresh", path)
        return ProjectState()

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        state = ProjectState.model_validate(data)
        logger.debug("Loaded state from %s (updated_at=%s)", path, state.updated_at)
        return state
    except json.JSONDecodeError as e:
        logger.warning("Corrupt state file %s: %s — starting fresh", path, e)
        return ProjectState()
    except Exception as e:
        logger.warning("Cannot load state from %s: %s — starting fresh", path, e)
        return ProjectState()


def save_state(state: ProjectState, path: Path) -> None:
    """Save project state to a JSON file (atomic write).

    Uses write-to-temp-then-rename to prevent corruption.

    Args:
        state: The state to save.
        path: Target path for the state file.
    """
    state.touch()

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Serialize
    data = state.model_dump(mode="json")
    content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    # Atomic write: temp file in same directory, then rename
    try:
        _fd, tmp_path = tempfile.mkstemp(
            dir=path.parent,
            prefix=".state_",
            suffix=".tmp",
        )
        tmp = Path(tmp_path)
        try:
            tmp.write_text(content, encoding="utf-8")
            tmp.rename(path)
            logger.debug("State saved to %s", path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
    except Exception as e:
        logger.error("Failed to save state to %s: %s", path, e)
        raise
