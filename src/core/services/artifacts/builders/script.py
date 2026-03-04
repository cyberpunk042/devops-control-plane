"""
Script builder — runs arbitrary shell scripts with streaming output.

Used for custom build/release/bundle scripts that don't fit
the makefile or pip patterns. The script path is specified
via build_cmd on the artifact target.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Generator

from ..engine import ArtifactBuildResult, ArtifactTarget
from .base import ArtifactBuilder, ArtifactStageInfo


class ScriptBuilder(ArtifactBuilder):
    """Runs arbitrary shell scripts."""

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
    ) -> Generator[str, None, ArtifactBuildResult]:
        """Run the build script with streaming output."""
        cmd = target.build_cmd or target.build_target
        if not cmd:
            yield "❌ No build_cmd or build_target specified"
            return ArtifactBuildResult(
                ok=False,
                target_name=target.name,
                error="No command specified",
            )

        # Resolve script path relative to project root
        script_path = project_root / cmd
        if script_path.exists() and not script_path.stat().st_mode & 0o111:
            yield f"⚠️  Script {cmd} is not executable, trying with bash..."
            cmd_parts = ["bash", str(script_path)]
        elif script_path.exists():
            cmd_parts = [str(script_path)]
        else:
            # Try as a shell command
            cmd_parts = ["bash", "-c", cmd]

        yield f"━━━ 📦 Running script: {target.name} ━━━"
        yield f"    Command: {cmd}"
        yield f"    Project: {project_root}"
        yield ""

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
                    **__import__("os").environ,
                    "DEVOPS_BUILD_TARGET": target.name,
                    "DEVOPS_BUILD_KIND": target.kind,
                    "DEVOPS_PROJECT_ROOT": str(project_root),
                    "DEVOPS_OUTPUT_DIR": str(
                        project_root / (target.output_dir or "dist/")
                    ),
                },
            )

            for line in iter(proc.stdout.readline, ""):
                yield line.rstrip("\n")

            proc.wait()
            duration_ms = int((time.time() - t0) * 1000)

            if proc.returncode == 0:
                yield ""
                yield f"✅ Script succeeded in {duration_ms}ms"
                return ArtifactBuildResult(
                    ok=True,
                    target_name=target.name,
                    output_dir=target.output_dir or "dist/",
                    duration_ms=duration_ms,
                )
            else:
                yield ""
                yield f"❌ Script failed (exit code {proc.returncode})"
                return ArtifactBuildResult(
                    ok=False,
                    target_name=target.name,
                    duration_ms=duration_ms,
                    error=f"Script failed with exit code {proc.returncode}",
                )

        except FileNotFoundError:
            duration_ms = int((time.time() - t0) * 1000)
            yield f"❌ Script not found: {cmd}"
            return ArtifactBuildResult(
                ok=False,
                target_name=target.name,
                duration_ms=duration_ms,
                error=f"Script not found: {cmd}",
            )
        except Exception as e:
            duration_ms = int((time.time() - t0) * 1000)
            yield f"❌ Error: {e}"
            return ArtifactBuildResult(
                ok=False,
                target_name=target.name,
                duration_ms=duration_ms,
                error=str(e),
            )
