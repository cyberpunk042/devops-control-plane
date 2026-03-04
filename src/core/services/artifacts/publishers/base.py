"""
Publisher base class and result model.

Publishers yield structured events (same contract as builders)
so the frontend build modal can display publish progress identically.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator

from ..engine import ArtifactTarget
from ..builders.base import (  # noqa: F401 — re-export for publishers
    ArtifactStageInfo,
    evt_log,
    evt_pipeline_done,
    evt_pipeline_start,
    evt_stage_done,
    evt_stage_error,
    evt_stage_start,
)


@dataclass
class ArtifactPublishResult:
    """Result of publishing an artifact."""

    ok: bool
    target_name: str          # artifact target (pip-package, container)
    publish_target: str       # where it went (github-release, pypi, ghcr)
    version: str = ""
    url: str = ""             # release URL or package URL
    duration_ms: int = 0
    error: str = ""
    files_published: list[str] = field(default_factory=list)


class ArtifactPublisher(ABC):
    """Base class for artifact publishers."""

    @abstractmethod
    def name(self) -> str:
        """Publisher identifier (e.g. 'github-release')."""
        ...

    @abstractmethod
    def label(self) -> str:
        """Human-readable label (e.g. 'GitHub Release')."""
        ...

    @abstractmethod
    def publish(
        self,
        target: ArtifactTarget,
        project_root: Path,
        version: str,
        files: list[Path],
        *,
        release_notes: str = "",
        tag_name: str = "",
        **kwargs: object,
    ) -> Generator[dict, None, ArtifactPublishResult]:
        """Publish artifacts with structured event streaming.

        Yields:
            Structured event dicts (pipeline_start, stage_start, log, etc.)

        Returns:
            ArtifactPublishResult via StopIteration.value
        """
        ...
