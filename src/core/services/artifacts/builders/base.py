"""
Artifact builder base — abstract interface for artifact builders.

Each builder knows how to produce a specific kind of artifact
(pip wheel, Makefile target, tarball, container image, etc.).

Builders yield log lines as they run, enabling SSE streaming
to the admin panel UI.
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


class ArtifactBuilder(ABC):
    """Base class for artifact builders."""

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
    ) -> Generator[str, None, ArtifactBuildResult]:
        """Run the full build, yielding log lines.

        The generator yields strings (log lines for SSE streaming)
        and returns an ArtifactBuildResult when complete.
        """
        ...
