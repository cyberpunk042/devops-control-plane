"""
.NET builder — builds C#/.NET projects with structured SSE events.

Runs `dotnet build` / `dotnet publish`.

Stages: check → restore → build → verify
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


class DotnetBuilder(ArtifactBuilder):
    """Builds .NET projects with structured events."""

    def name(self) -> str:
        return "dotnet"

    def label(self) -> str:
        return "dotnet (build/publish)"

    def stages(self, target: ArtifactTarget) -> list[ArtifactStageInfo]:
        return [
            ArtifactStageInfo(name="check", label="Check Prerequisites"),
            ArtifactStageInfo(name="restore", label="Restore Dependencies"),
            ArtifactStageInfo(name="build", label="Build / Publish"),
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
        output_dir = target.output_dir or "dist/"

        build_env = {
            **os.environ,
            "DEVOPS_BUILD_TARGET": target.name,
            "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
        }

        # ── Check ──
        yield evt_stage_start("check", "Check Prerequisites")
        check_start = time.time()

        dotnet_cmd = shutil.which("dotnet")
        if not dotnet_cmd:
            yield evt_log("dotnet not found in PATH", "check")
            yield evt_stage_error("check", "dotnet not found — install .NET SDK")
            yield evt_pipeline_done(ok=False, error="dotnet not found")
            return ArtifactBuildResult(ok=False, target_name=target.name, error="dotnet not found")

        csprojs = list(project_root.glob("*.csproj")) + list(project_root.glob("*.sln"))
        if not csprojs:
            yield evt_log("No .csproj or .sln found", "check")
            yield evt_stage_error("check", "No .csproj or .sln found")
            yield evt_pipeline_done(ok=False, error="No project file")
            return ArtifactBuildResult(ok=False, target_name=target.name, error="No .csproj/.sln")

        yield evt_log(f"dotnet: {dotnet_cmd}", "check")
        yield evt_log(f"Project: {csprojs[0].name}", "check")
        yield evt_log(f"Output: {output_dir}", "check")

        check_ms = int((time.time() - check_start) * 1000)
        yield evt_stage_done("check", check_ms)
        stage_results.append({"name": "check", "status": "done", "duration_ms": check_ms})

        # ── Restore ──
        yield evt_stage_start("restore", "Restore Dependencies")
        restore_start = time.time()

        try:
            proc = subprocess.Popen(
                ["dotnet", "restore"],
                cwd=str(project_root),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=build_env,
            )
            for line in iter(proc.stdout.readline, ""):
                yield evt_log(line.rstrip("\n"), "restore")
            proc.wait()
            restore_ms = int((time.time() - restore_start) * 1000)

            if proc.returncode != 0:
                yield evt_stage_error("restore", f"dotnet restore failed (exit {proc.returncode})", restore_ms)
                stage_results.append({"name": "restore", "status": "error"})
                yield evt_pipeline_done(ok=False, error="restore failed", stages=stage_results)
                return ArtifactBuildResult(ok=False, target_name=target.name, error="dotnet restore failed")

            yield evt_stage_done("restore", restore_ms)
            stage_results.append({"name": "restore", "status": "done", "duration_ms": restore_ms})
        except Exception as e:
            yield evt_stage_error("restore", str(e))
            yield evt_pipeline_done(ok=False, error=str(e), stages=stage_results)
            return ArtifactBuildResult(ok=False, target_name=target.name, error=str(e))

        # ── Build ──
        yield evt_stage_start("build", "Build / Publish")
        build_start = time.time()

        cmd = target.build_cmd or f"dotnet publish -c Release -o {output_dir}"
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
                yield evt_stage_error("build", f"dotnet build failed (exit {proc.returncode})", build_ms)
                stage_results.append({"name": "build", "status": "error", "duration_ms": build_ms})
                stage_results.append({"name": "verify", "status": "skipped"})
                total_ms = int((time.time() - pipeline_start) * 1000)
                yield evt_pipeline_done(ok=False, total_ms=total_ms, error="dotnet build failed", stages=stage_results)
                return ArtifactBuildResult(ok=False, target_name=target.name, duration_ms=total_ms, error="dotnet build failed")

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
            dlls = list(out_path.glob("*.dll")) + list(out_path.glob("*.nupkg"))
            exes = list(out_path.glob("*.exe")) + [f for f in out_path.iterdir() if f.is_file() and not f.suffix]
            all_files = dlls + exes
            if all_files:
                yield evt_log(f"Found {len(all_files)} artifact(s):", "verify")
                for f in sorted(all_files, key=lambda p: p.stat().st_mtime, reverse=True)[:8]:
                    size_kb = f.stat().st_size / 1024
                    yield evt_log(f"  {f.name}  ({size_kb:.1f} KB)", "verify")
            else:
                yield evt_log("No output files found", "verify")
        else:
            yield evt_log(f"Output directory not found: {output_dir}", "verify")

        verify_ms = int((time.time() - verify_start) * 1000)
        yield evt_stage_done("verify", verify_ms)
        stage_results.append({"name": "verify", "status": "done", "duration_ms": verify_ms})

        total_ms = int((time.time() - pipeline_start) * 1000)
        yield evt_pipeline_done(ok=True, total_ms=total_ms, stages=stage_results)
        return ArtifactBuildResult(ok=True, target_name=target.name, output_dir=str(out_path), duration_ms=total_ms)
