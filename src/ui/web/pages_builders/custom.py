"""
Custom builder — user-defined build command.

Pipeline stages:
  1. scaffold  — Symlink source content directory
  2. build     — Run user-provided shell command

Delegates to a user-provided shell command. The user specifies:
  - build_cmd: the command to run (e.g., "make html", "npm run build")
  - output_dir: where the built files end up (relative to workspace)
  - preview_cmd: optional dev server command
  - preview_port: port the dev server listens on
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .base import (
    BuilderInfo,
    ConfigField,
    LogStream,
    PageBuilder,
    SegmentConfig,
    StageInfo,
)


class CustomBuilder(PageBuilder):
    """User-defined build process."""

    def info(self) -> BuilderInfo:
        return BuilderInfo(
            name="custom",
            label="Custom Build",
            requires=[],
            description="User-defined build command. Fully flexible.",
            available=True,
        )

    def detect(self) -> bool:
        return True  # Always available — the user provides the command

    def config_schema(self) -> list[ConfigField]:
        return [
            ConfigField(
                key="build_cmd", label="Build Command", type="textarea",
                description="Shell command to run for building (executed in workspace directory)",
                placeholder="npm run build",
                category="Build",
                required=True,
            ),
            ConfigField(
                key="output_dir", label="Output Directory", type="text",
                description="Directory containing built files (relative to workspace)",
                default="build",
                placeholder="build",
                category="Build",
            ),
            ConfigField(
                key="preview_cmd", label="Preview Command", type="textarea",
                description="Shell command to start a dev server for live preview",
                placeholder="npm run dev",
                category="Preview",
            ),
            ConfigField(
                key="preview_port", label="Preview Port", type="number",
                description="Port the preview dev server listens on",
                default="8300",
                placeholder="8300",
                category="Preview",
            ),
            ConfigField(
                key="env_vars", label="Environment Variables", type="textarea",
                description="KEY=VALUE pairs (one per line) passed to the build command",
                placeholder="NODE_ENV=production\nCI=true",
                category="Advanced",
            ),
        ]

    # ── Pipeline stages ─────────────────────────────────────────────

    def pipeline_stages(self) -> list[StageInfo]:
        return [
            StageInfo("scaffold", "Setup Workspace",
                      "Symlink source content directory"),
            StageInfo("build", "Custom Build",
                      "Run user-provided build command"),
        ]

    def run_stage(
        self,
        stage: str,
        segment: SegmentConfig,
        workspace: Path,
    ) -> LogStream:
        if stage == "scaffold":
            yield from self._stage_scaffold(segment, workspace)
        elif stage == "build":
            yield from self._stage_build(segment, workspace)
        else:
            raise RuntimeError(f"Unknown stage: {stage}")

    # ── Stage implementations ───────────────────────────────────────

    def _stage_scaffold(self, segment: SegmentConfig, workspace: Path) -> LogStream:
        """Create workspace and symlink source."""
        workspace.mkdir(parents=True, exist_ok=True)

        source = Path(segment.source).resolve()
        content_link = workspace / "content"
        if content_link.exists() or content_link.is_symlink():
            content_link.unlink()
        content_link.symlink_to(source)
        yield f"Linked content → {source}"

    def _stage_build(self, segment: SegmentConfig, workspace: Path) -> LogStream:
        """Run the user-provided build command."""
        build_cmd = segment.config.get("build_cmd", "echo 'No build_cmd configured'")
        yield f"▶ {build_cmd}"

        # Parse environment variables
        env = None
        env_str = segment.config.get("env_vars", "")
        if env_str:
            import os
            env = dict(os.environ)
            for line in env_str.strip().splitlines():
                line = line.strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()

        proc = subprocess.Popen(
            build_cmd,
            shell=True,
            cwd=str(workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        if proc.stdout:
            for line in proc.stdout:
                yield line.rstrip()
        proc.wait()

        if proc.returncode != 0:
            raise RuntimeError(f"Custom build failed (exit code {proc.returncode})")

        yield "Build complete"

    # ── Output dir ──────────────────────────────────────────────────

    def output_dir(self, workspace: Path) -> Path:
        # Allow user to override output directory name
        return workspace / "build"  # TODO: read from segment config when available

    # ── Preview (live dev server) ───────────────────────────────────

    def preview(
        self, segment: SegmentConfig, workspace: Path,
    ) -> tuple[subprocess.Popen, int]:
        """Run the user-provided preview command."""
        preview_cmd = segment.config.get("preview_cmd")
        port = segment.config.get("preview_port", 8300)

        if not preview_cmd:
            raise NotImplementedError("No preview_cmd configured for this segment")

        proc = subprocess.Popen(
            preview_cmd,
            shell=True,
            cwd=str(workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return proc, port
