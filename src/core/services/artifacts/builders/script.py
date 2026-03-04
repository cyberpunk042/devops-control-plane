"""
Script builder — runs arbitrary shell scripts with structured SSE events.

Used for custom build/release/bundle scripts that don't fit
the makefile or pip patterns.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Generator

from ..engine import ArtifactBuildResult, ArtifactTarget
from .base import (
    ArtifactBuilder,
    ArtifactStageInfo,
    evt_log,
    evt_pipeline_done,
    evt_pipeline_start,
    evt_stage_done,
    evt_stage_error,
    evt_stage_start,
)


class ScriptBuilder(ArtifactBuilder):
    """Runs arbitrary shell scripts with structured event streaming."""

    def name(self) -> str:
        return "script"

    def label(self) -> str:
        return "Shell Script"

    def stages(self, target: ArtifactTarget) -> list[ArtifactStageInfo]:
        cmd = target.build_cmd or target.build_target or "script"
        return [ArtifactStageInfo(
            name="run",
            label="Run Script",
            description=cmd,
        )]

    def build(
        self,
        target: ArtifactTarget,
        project_root: Path,
    ) -> Generator[dict, None, ArtifactBuildResult]:
        """Run the build script with structured event streaming."""
        stage_list = self.stages(target)
        yield evt_pipeline_start(stage_list)

        cmd = target.build_cmd or target.build_target
        if not cmd:
            yield evt_stage_start("run", "Run Script")
            yield evt_stage_error("run", "No build_cmd or build_target specified")
            yield evt_pipeline_done(ok=False, error="No command specified")
            return ArtifactBuildResult(
                ok=False, target_name=target.name, error="No command specified",
            )

        # Resolve script path relative to project root
        script_path = project_root / cmd
        if script_path.exists() and not script_path.stat().st_mode & 0o111:
            cmd_parts = ["bash", str(script_path)]
        elif script_path.exists():
            cmd_parts = [str(script_path)]
        else:
            cmd_parts = ["bash", "-c", cmd]

        yield evt_stage_start("run", "Run Script")
        yield evt_log(f"Command: {cmd}", "run")

        t0 = time.time()

        try:
            proc = subprocess.Popen(
                cmd_parts,
                cwd=str(project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env={
                    **os.environ,
                    "DEVOPS_BUILD_TARGET": target.name,
                    "DEVOPS_BUILD_KIND": target.kind,
                    "DEVOPS_PROJECT_ROOT": str(project_root),
                    "DEVOPS_OUTPUT_DIR": str(
                        project_root / (target.output_dir or "dist/")
                    ),
                },
            )

            for line in iter(proc.stdout.readline, ""):
                yield evt_log(line.rstrip("\n"), "run")

            proc.wait()
            duration_ms = int((time.time() - t0) * 1000)

            if proc.returncode == 0:
                yield evt_stage_done("run", duration_ms)
                yield evt_pipeline_done(
                    ok=True, total_ms=duration_ms,
                    stages=[{"name": "run", "status": "done", "duration_ms": duration_ms}],
                )
                return ArtifactBuildResult(
                    ok=True, target_name=target.name,
                    output_dir=target.output_dir or "dist/",
                    duration_ms=duration_ms,
                )
            else:
                yield evt_stage_error(
                    "run",
                    f"Script failed (exit code {proc.returncode})",
                    duration_ms,
                )
                yield evt_pipeline_done(
                    ok=False, total_ms=duration_ms,
                    error=f"Script failed (exit code {proc.returncode})",
                    stages=[{"name": "run", "status": "error", "duration_ms": duration_ms}],
                )
                return ArtifactBuildResult(
                    ok=False, target_name=target.name,
                    duration_ms=duration_ms,
                    error=f"Script failed with exit code {proc.returncode}",
                )

        except FileNotFoundError:
            duration_ms = int((time.time() - t0) * 1000)
            yield evt_stage_error("run", f"Script not found: {cmd}", duration_ms)
            yield evt_pipeline_done(ok=False, total_ms=duration_ms, error=f"Script not found: {cmd}")
            return ArtifactBuildResult(
                ok=False, target_name=target.name,
                duration_ms=duration_ms, error=f"Script not found: {cmd}",
            )

        except Exception as e:
            duration_ms = int((time.time() - t0) * 1000)
            yield evt_stage_error("run", str(e), duration_ms)
            yield evt_pipeline_done(ok=False, total_ms=duration_ms, error=str(e))
            return ArtifactBuildResult(
                ok=False, target_name=target.name,
                duration_ms=duration_ms, error=str(e),
            )
