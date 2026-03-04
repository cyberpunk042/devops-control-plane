"""
Maven builder — builds Java projects with structured SSE events.

Runs `mvn package` to produce JARs/WARs.

Stages: check → build → verify
"""

from __future__ import annotations

import os
import shutil
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


class MavenBuilder(ArtifactBuilder):
    """Builds Java projects via Maven with structured events."""

    def name(self) -> str:
        return "maven"

    def label(self) -> str:
        return "Maven (mvn package)"

    def stages(self, target: ArtifactTarget) -> list[ArtifactStageInfo]:
        return [
            ArtifactStageInfo(name="check", label="Check Prerequisites"),
            ArtifactStageInfo(name="build", label="Build Package"),
            ArtifactStageInfo(name="verify", label="Verify Output"),
        ]

    def build(
        self,
        target: ArtifactTarget,
        project_root: Path,
    ) -> Generator[dict, None, ArtifactBuildResult]:
        stage_list = self.stages(target)
        yield evt_pipeline_start(stage_list)

        pipeline_start = time.time()
        stage_results = []
        output_dir = target.output_dir or "target/"

        build_env = {
            **os.environ,
            "DEVOPS_BUILD_TARGET": target.name,
            "DEVOPS_BUILD_KIND": target.kind,
        }

        # ── Check ──
        yield evt_stage_start("check", "Check Prerequisites")
        check_start = time.time()

        mvn_cmd = shutil.which("mvn")
        if not mvn_cmd:
            yield evt_log("mvn not found in PATH", "check")
            yield evt_stage_error("check", "mvn not found — install Maven")
            yield evt_pipeline_done(ok=False, error="mvn not found")
            return ArtifactBuildResult(ok=False, target_name=target.name, error="mvn not found")

        pom = project_root / "pom.xml"
        if not pom.exists():
            yield evt_log("No pom.xml found", "check")
            yield evt_stage_error("check", "No pom.xml found")
            yield evt_pipeline_done(ok=False, error="No pom.xml")
            return ArtifactBuildResult(ok=False, target_name=target.name, error="No pom.xml")

        yield evt_log(f"mvn: {mvn_cmd}", "check")
        yield evt_log(f"Output: {output_dir}", "check")

        check_ms = int((time.time() - check_start) * 1000)
        yield evt_stage_done("check", check_ms)
        stage_results.append({"name": "check", "status": "done", "duration_ms": check_ms})

        # ── Build ──
        yield evt_stage_start("build", "Build Package")
        build_start = time.time()

        cmd = target.build_cmd or "mvn package -DskipTests"
        try:
            proc = subprocess.Popen(
                cmd.split(),
                cwd=str(project_root),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=build_env,
            )
            for line in iter(proc.stdout.readline, ""):
                yield evt_log(line.rstrip("\n"), "build")
            proc.wait()
            build_ms = int((time.time() - build_start) * 1000)

            if proc.returncode != 0:
                yield evt_stage_error("build", f"mvn failed (exit {proc.returncode})", build_ms)
                stage_results.append({"name": "build", "status": "error", "duration_ms": build_ms})
                stage_results.append({"name": "verify", "status": "skipped"})
                total_ms = int((time.time() - pipeline_start) * 1000)
                yield evt_pipeline_done(ok=False, total_ms=total_ms, error="mvn failed", stages=stage_results)
                return ArtifactBuildResult(ok=False, target_name=target.name, duration_ms=total_ms, error="mvn failed")

            yield evt_stage_done("build", build_ms)
            stage_results.append({"name": "build", "status": "done", "duration_ms": build_ms})
        except Exception as e:
            build_ms = int((time.time() - build_start) * 1000)
            yield evt_stage_error("build", str(e), build_ms)
            yield evt_pipeline_done(ok=False, error=str(e), stages=stage_results)
            return ArtifactBuildResult(ok=False, target_name=target.name, error=str(e))

        # ── Verify ──
        yield evt_stage_start("verify", "Verify Output")
        verify_start = time.time()

        out_path = project_root / output_dir
        if out_path.exists():
            jars = list(out_path.glob("*.jar")) + list(out_path.glob("*.war"))
            if jars:
                yield evt_log(f"Found {len(jars)} artifact(s):", "verify")
                for f in sorted(jars, key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
                    size_kb = f.stat().st_size / 1024
                    yield evt_log(f"  {f.name}  ({size_kb:.1f} KB)", "verify")
            else:
                yield evt_log("No .jar/.war files found in target/", "verify")
        else:
            yield evt_log(f"Output directory not found: {output_dir}", "verify")

        verify_ms = int((time.time() - verify_start) * 1000)
        yield evt_stage_done("verify", verify_ms)
        stage_results.append({"name": "verify", "status": "done", "duration_ms": verify_ms})

        total_ms = int((time.time() - pipeline_start) * 1000)
        yield evt_pipeline_done(ok=True, total_ms=total_ms, stages=stage_results)
        return ArtifactBuildResult(ok=True, target_name=target.name, output_dir=str(out_path), duration_ms=total_ms)
