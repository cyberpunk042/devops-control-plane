"""
Artifact builder base — abstract interface for artifact builders.

Each builder knows how to produce a specific kind of artifact
(pip wheel, Makefile target, tarball, container image, etc.).

Builders yield structured event dicts for SSE streaming to the UI.

Event types:
  pipeline_start  — Emitted once at the start. Contains stage list.
  stage_start     — Emitted when a stage begins.
  log             — A single log line within the current stage.
  stage_done      — Emitted when a stage completes successfully.
  stage_error     — Emitted when a stage fails.
  pipeline_done   — Emitted once at the end. Contains success/failure + timing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

from ..engine import ArtifactBuildResult, ArtifactTarget


@dataclass
class ArtifactStageInfo:
    """Metadata about a build stage."""

    name: str
    label: str
    description: str = ""


# ── Event helpers (use these in builders) ───────────────────────────


def evt_pipeline_start(stages: list[ArtifactStageInfo]) -> dict:
    """Emit pipeline_start event."""
    return {
        "type": "pipeline_start",
        "stages": [{"name": s.name, "label": s.label} for s in stages],
    }


def evt_stage_start(stage: str, label: str = "") -> dict:
    """Emit stage_start event."""
    return {"type": "stage_start", "stage": stage, "label": label or stage}


def evt_log(line: str, stage: str = "") -> dict:
    """Emit a log line event."""
    return {"type": "log", "stage": stage, "line": line}


def evt_stage_done(stage: str, duration_ms: int = 0) -> dict:
    """Emit stage_done event."""
    return {"type": "stage_done", "stage": stage, "duration_ms": duration_ms}


def evt_stage_error(stage: str, error: str, duration_ms: int = 0) -> dict:
    """Emit stage_error event."""
    return {
        "type": "stage_error",
        "stage": stage,
        "error": error,
        "duration_ms": duration_ms,
    }


def evt_pipeline_done(
    ok: bool,
    total_ms: int = 0,
    error: str = "",
    stages: list[dict] | None = None,
) -> dict:
    """Emit pipeline_done event."""
    return {
        "type": "pipeline_done",
        "ok": ok,
        "total_ms": total_ms,
        "error": error,
        "stages": stages or [],
    }


class ArtifactBuilder(ABC):
    """Base class for artifact builders.

    Event contract:
      The build() generator MUST emit events in this order:
        1. pipeline_start (once, first)
        2. For each stage:
           a. stage_start
           b. log (zero or more)
           c. stage_done or stage_error
        3. pipeline_done (once, last)
      The generator returns an ArtifactBuildResult via StopIteration.
    """

    @abstractmethod
    def name(self) -> str:
        """Builder identifier (e.g. 'makefile', 'pip', 'docker')."""
        ...

    @abstractmethod
    def label(self) -> str:
        """Human-readable label."""
        ...

    @abstractmethod
    def stages(self, target: ArtifactTarget) -> list[ArtifactStageInfo]:
        """Return the ordered list of build stages for this target."""
        ...

    @abstractmethod
    def build(
        self,
        target: ArtifactTarget,
        project_root: Path,
    ) -> Generator[dict, None, ArtifactBuildResult]:
        """Run the full build, yielding structured event dicts.

        The generator yields dicts (see Event types above)
        and returns an ArtifactBuildResult when complete.
        """
        ...
