"""
Go builder — builds Go binaries with structured SSE events.

Runs `go build` to produce distributable binaries.

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


class GoBuilder(ArtifactBuilder):
    """Builds Go binaries with structured events."""

    def name(self) -> str:
        return "go"

    def label(self) -> str:
        return "go (binary build)"

    def stages(self, target: ArtifactTarget) -> list[ArtifactStageInfo]:
        return [
            ArtifactStageInfo(name="check", label="Check Prerequisites"),
            ArtifactStageInfo(name="build", label="Build Binary"),
            ArtifactStageInfo(name="verify", label="Verify Output"),
        ]

    def build(
        self,
        target: ArtifactTarget,
        project_root: Path,
    ) -> Generator[dict, None, ArtifactBuildResult]:
        """Run go build with structured event streaming."""
        stage_list = self.stages(target)
        yield evt_pipeline_start(stage_list)

        pipeline_start = time.time()
        stage_results = []
        output_dir = target.output_dir or "dist/"

        build_env = {
            **os.environ,
            "DEVOPS_BUILD_TARGET": target.name,
            "DEVOPS_BUILD_KIND": target.kind,
            "DEVOPS_PROJECT_ROOT": str(project_root),
            "CGO_ENABLED": os.environ.get("CGO_ENABLED", "0"),
        }

        # ── Stage 1: Check prerequisites ──
        yield evt_stage_start("check", "Check Prerequisites")
        check_start = time.time()

        go_cmd = shutil.which("go")
        if not go_cmd:
            yield evt_log("go not found in PATH", "check")
            yield evt_stage_error("check", "go not found — install Go")
            yield evt_pipeline_done(ok=False, error="go not found")
            return ArtifactBuildResult(ok=False, target_name=target.name, error="go not found")

        go_mod = project_root / "go.mod"
        if not go_mod.exists():
            yield evt_log("No go.mod found", "check")
            yield evt_stage_error("check", "No go.mod found — run 'go mod init'")
            yield evt_pipeline_done(ok=False, error="No go.mod")
            return ArtifactBuildResult(ok=False, target_name=target.name, error="No go.mod")

        # Parse module path
        module_path = project_root.name
        try:
            for line in go_mod.read_text().splitlines():
                stripped = line.strip()
                if stripped.startswith("module "):
                    module_path = stripped.split(None, 1)[1].strip()
                    break
        except OSError:
            pass

        # Get go version
        try:
            ver_result = subprocess.run(
                ["go", "version"], capture_output=True, text=True, timeout=5,
            )
            go_version = ver_result.stdout.strip() if ver_result.returncode == 0 else "unknown"
        except (OSError, subprocess.TimeoutExpired):
            go_version = "unknown"

        yield evt_log(f"go: {go_version}", "check")
        yield evt_log(f"Module: {module_path}", "check")
        yield evt_log(f"Output: {output_dir}", "check")

        # Find build targets (main packages)
        main_files = list(project_root.glob("cmd/**/main.go")) + list(project_root.glob("main.go"))
        if main_files:
            yield evt_log(f"Found {len(main_files)} main package(s)", "check")
        else:
            yield evt_log("No main.go found — library module (build for validation only)", "check")

        check_ms = int((time.time() - check_start) * 1000)
        yield evt_stage_done("check", check_ms)
        stage_results.append({"name": "check", "status": "done", "duration_ms": check_ms})

        # ── Stage 2: Build ──
        yield evt_stage_start("build", "Build Binary")
        build_start = time.time()

        # Create output dir
        out_path = project_root / output_dir
        out_path.mkdir(parents=True, exist_ok=True)

        binary_name = module_path.split("/")[-1] if "/" in module_path else module_path
        cmd = target.build_cmd or f"go build -o {output_dir}{binary_name} ./..."

        try:
            proc = subprocess.Popen(
                cmd.split(),
                cwd=str(project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=build_env,
            )
            for line in iter(proc.stdout.readline, ""):
                yield evt_log(line.rstrip("\n"), "build")
            proc.wait()

            build_ms = int((time.time() - build_start) * 1000)

            if proc.returncode != 0:
                yield evt_stage_error("build", f"go build failed (exit {proc.returncode})", build_ms)
                stage_results.append({"name": "build", "status": "error", "duration_ms": build_ms})
                stage_results.append({"name": "verify", "status": "skipped"})
                total_ms = int((time.time() - pipeline_start) * 1000)
                yield evt_pipeline_done(ok=False, total_ms=total_ms, error="go build failed", stages=stage_results)
                return ArtifactBuildResult(ok=False, target_name=target.name, duration_ms=total_ms, error="go build failed")

            yield evt_stage_done("build", build_ms)
            stage_results.append({"name": "build", "status": "done", "duration_ms": build_ms})

        except Exception as e:
            build_ms = int((time.time() - build_start) * 1000)
            yield evt_stage_error("build", str(e), build_ms)
            stage_results.append({"name": "build", "status": "error"})
            yield evt_pipeline_done(ok=False, error=str(e), stages=stage_results)
            return ArtifactBuildResult(ok=False, target_name=target.name, error=str(e))

        # ── Stage 3: Verify output ──
        yield evt_stage_start("verify", "Verify Output")
        verify_start = time.time()

        if out_path.exists():
            built_files = [f for f in out_path.iterdir() if f.is_file()]
            if built_files:
                yield evt_log(f"Found {len(built_files)} artifact(s):", "verify")
                for f in sorted(built_files, key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
                    size_mb = f.stat().st_size / (1024 * 1024)
                    yield evt_log(f"  {f.name}  ({size_mb:.2f} MB)", "verify")
            else:
                yield evt_log(f"No files in {output_dir}", "verify")
        else:
            yield evt_log(f"Output directory not found: {output_dir}", "verify")

        verify_ms = int((time.time() - verify_start) * 1000)
        yield evt_stage_done("verify", verify_ms)
        stage_results.append({"name": "verify", "status": "done", "duration_ms": verify_ms})

        total_ms = int((time.time() - pipeline_start) * 1000)
        yield evt_pipeline_done(ok=True, total_ms=total_ms, stages=stage_results)

        return ArtifactBuildResult(
            ok=True, target_name=target.name,
            output_dir=str(out_path), duration_ms=total_ms,
        )
