"""
Page builder base — abstract interface for static site generators.

Pipeline model
──────────────
Every builder exposes an ordered list of **named stages**. Each stage:
  - Takes input from the previous stage's output (or from the source dir).
  - Yields log lines as it runs (for SSE streaming to the UI).
  - Reports its own duration, status, and any error.

The pipeline is driven by the orchestrator (pages_engine / routes_pages_api):
  for stage_name in builder.pipeline_stages():
      for log_line in builder.run_stage(stage_name, segment, workspace):
          send_to_client(log_line)

Backward‑compatible methods (scaffold, build, preview, output_dir) remain
so that existing callers keep working while each builder is migrated to the
stage model. New code should use `pipeline_stages()` + `run_stage()`.

Stage conventions
─────────────────
  "source"    — Copy/filter source files into workspace
  "transform" — Convert formats (e.g. MD → MDX)
  "enrich"    — Apply remark/rehype plugins, augment frontmatter
  "scaffold"  — Generate builder config files (docusaurus.config.js, etc.)
  "install"   — Install dependencies (npm install, pip install)
  "build"     — Run the actual build command (npx docusaurus build, etc.)

Every pipeline implicitly ends with a "serve" stage handled by Flask
(not by the builder) — static files from output_dir() are served at
/pages/site/<segment>/.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator


# ── Data Models ─────────────────────────────────────────────────────


@dataclass
class BuilderInfo:
    """Metadata about a builder."""

    name: str
    label: str                          # Human-friendly name
    requires: list[str] = field(default_factory=list)  # External deps
    description: str = ""
    available: bool = False             # Populated by detect()
    install_hint: str = ""              # Human hint: "pip install mkdocs"
    install_cmd: list[str] = field(default_factory=list)  # Auto-install cmd


@dataclass
class SegmentConfig:
    """Configuration for a single site segment."""

    name: str
    source: str                         # Relative path to content folder
    builder: str = "raw"                # Builder name
    path: str = "/"                     # URL path prefix
    auto: bool = False                  # Auto-created from content_folders
    config: dict = field(default_factory=dict)  # Builder-specific config


@dataclass
class StageInfo:
    """Declaration of a pipeline stage (before execution)."""

    name: str                           # Machine name: "source", "transform", etc.
    label: str                          # Human label: "MD → MDX Transform"
    description: str = ""               # Optional longer description


@dataclass
class StageResult:
    """Result of executing one pipeline stage."""

    name: str
    label: str
    status: str = "pending"             # "pending" | "running" | "done" | "error" | "skipped"
    duration_ms: int = 0
    log_lines: list[str] = field(default_factory=list)
    error: str = ""
    detail: dict = field(default_factory=dict)  # Stage-specific stats (files_transformed, etc.)


@dataclass
class ConfigField:
    """Declaration of a configurable field for a builder's config modal.

    Types:
      - "text"     : single-line text input
      - "textarea" : multi-line text/YAML/JSON input
      - "number"   : numeric input
      - "select"   : dropdown with predefined options
      - "bool"     : toggle switch
    """

    key: str                            # Config dict key (e.g. "build_cmd")
    label: str                          # Human label
    type: str = "text"                  # "text" | "textarea" | "number" | "select" | "bool"
    description: str = ""               # Help text under the field
    default: Any = ""                   # Default value
    placeholder: str = ""               # Input placeholder
    options: dict[str, str] = field(default_factory=dict)  # For "select" type: {value: label}
    category: str = ""                  # Group heading (e.g. "Site Identity", "Build Options")
    required: bool = False              # Whether the field is required


@dataclass
class PipelineResult:
    """Result of a full pipeline execution."""

    segment: str
    builder: str
    stages: list[StageResult] = field(default_factory=list)
    ok: bool = False
    total_duration_ms: int = 0
    serve_url: str = ""                 # "/pages/site/docs/" — set after success
    output_dir: str = ""                # Absolute path to built output


@dataclass
class BuildResult:
    """Result of a segment build (legacy model — kept for backward compat)."""

    ok: bool
    segment: str
    output_dir: Path | None = None
    duration_ms: int = 0
    error: str = ""
    log: list[str] = field(default_factory=list)


# ── Log line type alias ─────────────────────────────────────────────

LogStream = Generator[str, None, None]
"""A generator that yields log line strings, one at a time."""


# ── Abstract Builder ────────────────────────────────────────────────


class PageBuilder(ABC):
    """Abstract base for page builders.

    Builders must implement:
      - info()             — metadata (name, label, deps, install hints)
      - pipeline_stages()  — ordered list of stage declarations
      - run_stage()        — execute one stage, yielding log lines
      - output_dir()       — where the built output lives

    Builders MAY override:
      - detect()           — custom dependency detection
      - scaffold()         — legacy: generate config (for old callers)
      - build()            — legacy: run build process (for old callers)
      - preview()          — start a dev server (hot‑reload for authoring)
    """

    # ── Required methods ────────────────────────────────────────────

    @abstractmethod
    def info(self) -> BuilderInfo:
        """Return builder metadata."""

    @abstractmethod
    def pipeline_stages(self) -> list[StageInfo]:
        """Declare the ordered pipeline stages this builder supports.

        Returns an ordered list of StageInfo. The orchestrator will call
        run_stage() for each, in order.

        Example for Docusaurus:
            [
                StageInfo("source",    "Resolve Source"),
                StageInfo("transform", "MD → MDX Transform"),
                StageInfo("enrich",    "Remark/Rehype Plugins"),
                StageInfo("scaffold",  "Generate Config"),
                StageInfo("install",   "npm install"),
                StageInfo("build",     "Docusaurus Build"),
            ]
        """

    @abstractmethod
    def run_stage(
        self,
        stage: str,
        segment: SegmentConfig,
        workspace: Path,
    ) -> LogStream:
        """Execute a single pipeline stage.

        This is a generator: yield one string per log line. The orchestrator
        captures timing and wraps each line in SSE events.

        Args:
            stage: Stage name (must match one from pipeline_stages()).
            segment: Segment configuration.
            workspace: Build workspace directory (.pages/<segment>/).

        Yields:
            Log line strings (without newlines).

        Raises:
            RuntimeError: If the stage fails. The orchestrator catches this
                          and records the error on the StageResult.
        """

    @abstractmethod
    def output_dir(self, workspace: Path) -> Path:
        """Path to the built output directory.

        Args:
            workspace: The workspace directory.

        Returns:
            Absolute path to the directory containing built static files.
        """

    # ── Optional methods (with defaults) ────────────────────────────

    def config_schema(self) -> list[ConfigField]:
        """Declare configurable fields for this builder.

        The UI renders these as form fields in the configuration modal.
        Override in subclasses to declare builder-specific fields.
        Returns an empty list by default (no extra config beyond title/tagline).
        """
        return []

    def detect(self) -> bool:
        """Check if this builder's dependencies are available."""
        for dep in self.info().requires:
            if shutil.which(dep) is None:
                return False
        return True

    def preview(
        self, segment: SegmentConfig, workspace: Path,
    ) -> tuple[subprocess.Popen, int]:
        """Start a dev server for local preview (hot‑reload).

        This is separate from Flask's integrated static serving.
        Use this for live authoring (docusaurus start, mkdocs serve, etc.).

        Returns:
            Tuple of (process, port).

        Raises:
            NotImplementedError: if the builder has no dev server.
        """
        raise NotImplementedError(
            f"Builder '{self.info().name}' does not support live preview"
        )

    # ── Legacy methods (backward compat) ────────────────────────────

    def scaffold(self, segment: SegmentConfig, workspace: Path) -> None:
        """Generate build config files in the workspace directory.

        Legacy method — new code should use run_stage().
        Default implementation runs all stages before "build".
        """
        stages = self.pipeline_stages()
        build_idx = next(
            (i for i, s in enumerate(stages) if s.name == "build"),
            len(stages),
        )
        for stage_info in stages[:build_idx]:
            # Exhaust the generator (discard log lines)
            for _line in self.run_stage(stage_info.name, segment, workspace):
                pass

    def build(self, segment: SegmentConfig, workspace: Path) -> subprocess.Popen:
        """Run the build stage, returning a process for streaming.

        Legacy method — new code should use run_stage("build", ...).
        Default implementation runs the "build" stage and raises if it
        doesn't produce a Popen (subclasses should override if needed).
        """
        raise NotImplementedError(
            "Legacy build() not implemented; use run_stage('build', ...)"
        )


# ── Pipeline Runner Utility ─────────────────────────────────────────


def run_pipeline(
    builder: PageBuilder,
    segment: SegmentConfig,
    workspace: Path,
) -> PipelineResult:
    """Run a builder's full pipeline, collecting results for all stages.

    This is the non-streaming version. For SSE streaming, use the
    stage-by-stage approach in the route handler.

    Returns:
        PipelineResult with aggregated stage results.
    """
    stages_info = builder.pipeline_stages()
    result = PipelineResult(
        segment=segment.name,
        builder=segment.builder,
    )

    total_start = time.monotonic()
    all_ok = True

    for si in stages_info:
        sr = StageResult(name=si.name, label=si.label, status="running")
        stage_start = time.monotonic()

        try:
            for line in builder.run_stage(si.name, segment, workspace):
                sr.log_lines.append(line)
            sr.status = "done"
        except RuntimeError as e:
            sr.status = "error"
            sr.error = str(e)
            all_ok = False
        except Exception as e:
            sr.status = "error"
            sr.error = f"Unexpected error: {e}"
            all_ok = False

        sr.duration_ms = int((time.monotonic() - stage_start) * 1000)
        result.stages.append(sr)

        # Stop pipeline on first error
        if not all_ok:
            # Mark remaining stages as skipped
            remaining = stages_info[stages_info.index(si) + 1:]
            for rem in remaining:
                result.stages.append(
                    StageResult(name=rem.name, label=rem.label, status="skipped")
                )
            break

    result.ok = all_ok
    result.total_duration_ms = int((time.monotonic() - total_start) * 1000)

    if all_ok:
        output = builder.output_dir(workspace)
        result.output_dir = str(output)
        result.serve_url = f"/pages/site/{segment.name}/"

    return result
