"""
Raw builder — copies static files into the build output.

Pipeline stages:
  1. source  — Copy files from source dir (excluding hidden dirs, __pycache__)
  2. build   — (no-op for raw; the copy IS the build)

This is the simplest builder and the only one guaranteed to work
everywhere (zero dependencies). It copies the source folder directly
to the output directory.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import (
    BuilderInfo,
    LogStream,
    PageBuilder,
    SegmentConfig,
    StageInfo,
)


class RawBuilder(PageBuilder):
    """Copy-only builder — no external tooling required."""

    def info(self) -> BuilderInfo:
        return BuilderInfo(
            name="raw",
            label="Static Files",
            requires=[],
            description="Copies files directly with no build step. Always available.",
            available=True,
        )

    def detect(self) -> bool:
        return True  # Always available

    # ── Pipeline stages ─────────────────────────────────────────────

    def pipeline_stages(self) -> list[StageInfo]:
        return [
            StageInfo("source", "Copy Source Files",
                      "Copy files to build output (excludes hidden dirs)"),
        ]

    def run_stage(
        self,
        stage: str,
        segment: SegmentConfig,
        workspace: Path,
    ) -> LogStream:
        if stage == "source":
            yield from self._stage_source(segment, workspace)
        else:
            raise RuntimeError(f"Unknown stage: {stage}")

    # ── Stage implementations ───────────────────────────────────────

    def _stage_source(self, segment: SegmentConfig, workspace: Path) -> LogStream:
        """Copy source files to workspace/build/, excluding hidden dirs."""
        source = Path(segment.source).resolve()
        output = workspace / "build"

        if output.exists():
            shutil.rmtree(output)
        output.mkdir(parents=True, exist_ok=True)

        yield f"Source: {source}"
        yield f"Output: {output}"

        # Use rsync to exclude hidden dirs; fall back to cp
        if shutil.which("rsync"):
            cmd = [
                "rsync", "-rv",
                "--exclude", ".*",
                "--exclude", "__pycache__",
                str(source) + "/", str(output) + "/",
            ]
        else:
            cmd = ["cp", "-rv", str(source) + "/.", str(output)]

        yield f"▶ {' '.join(cmd)}"

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if proc.stdout:
            for line in proc.stdout:
                yield line.rstrip()
        proc.wait()

        if proc.returncode != 0:
            raise RuntimeError(f"Copy failed (exit code {proc.returncode})")

        # Count output files
        file_count = sum(1 for _ in output.rglob("*") if _.is_file())
        yield f"Copied {file_count} files"

    # ── Output dir ──────────────────────────────────────────────────

    def output_dir(self, workspace: Path) -> Path:
        return workspace / "build"

    # ── Preview (live dev server) ───────────────────────────────────

    def preview(
        self, segment: SegmentConfig, workspace: Path,
    ) -> tuple[subprocess.Popen, int]:
        """Serve built files with Python's http.server."""
        import random
        import sys

        port = random.randint(8000, 8099)
        build_dir = workspace / "build"
        if not build_dir.is_dir():
            build_dir.mkdir(parents=True, exist_ok=True)

        proc = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(port)],
            cwd=str(build_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return proc, port
