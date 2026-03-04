"""
Mix builder — builds Elixir projects with structured SSE events.

Runs `mix deps.get` → `mix compile` → optional `mix release`.

Stages: check → deps → build → verify
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


class MixBuilder(ArtifactBuilder):
    """Builds Elixir projects via Mix with structured events."""

    def name(self) -> str:
        return "mix"

    def label(self) -> str:
        return "Mix (compile/release)"

    def stages(self, target: ArtifactTarget) -> list[ArtifactStageInfo]:
        return [
            ArtifactStageInfo(name="check", label="Check Prerequisites"),
            ArtifactStageInfo(name="deps", label="Get Dependencies"),
            ArtifactStageInfo(name="build", label="Compile & Release"),
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
        output_dir = target.output_dir or "_build/prod/rel/"

        build_env = {
            **os.environ,
            "MIX_ENV": "prod",
            "DEVOPS_BUILD_TARGET": target.name,
        }

        # ── Check ──
        yield evt_stage_start("check", "Check Prerequisites")
        check_start = time.time()

        mix_cmd = shutil.which("mix")
        if not mix_cmd:
            yield evt_log("mix not found in PATH", "check")
            yield evt_stage_error("check", "mix not found — install Elixir")
            yield evt_pipeline_done(ok=False, error="mix not found")
            return ArtifactBuildResult(ok=False, target_name=target.name, error="mix not found")

        mix_exs = project_root / "mix.exs"
        if not mix_exs.exists():
            yield evt_log("No mix.exs found", "check")
            yield evt_stage_error("check", "No mix.exs found")
            yield evt_pipeline_done(ok=False, error="No mix.exs")
            return ArtifactBuildResult(ok=False, target_name=target.name, error="No mix.exs")

        yield evt_log(f"mix: {mix_cmd}", "check")
        yield evt_log(f"MIX_ENV: prod", "check")
        yield evt_log(f"Output: {output_dir}", "check")

        check_ms = int((time.time() - check_start) * 1000)
        yield evt_stage_done("check", check_ms)
        stage_results.append({"name": "check", "status": "done", "duration_ms": check_ms})

        # ── Deps ──
        yield evt_stage_start("deps", "Get Dependencies")
        deps_start = time.time()

        try:
            proc = subprocess.Popen(
                ["mix", "deps.get"],
                cwd=str(project_root),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=build_env,
            )
            for line in iter(proc.stdout.readline, ""):
                yield evt_log(line.rstrip("\n"), "deps")
            proc.wait()
            deps_ms = int((time.time() - deps_start) * 1000)

            if proc.returncode != 0:
                yield evt_stage_error("deps", f"mix deps.get failed (exit {proc.returncode})", deps_ms)
                stage_results.append({"name": "deps", "status": "error"})
                yield evt_pipeline_done(ok=False, error="deps.get failed", stages=stage_results)
                return ArtifactBuildResult(ok=False, target_name=target.name, error="mix deps.get failed")

            yield evt_stage_done("deps", deps_ms)
            stage_results.append({"name": "deps", "status": "done", "duration_ms": deps_ms})
        except Exception as e:
            yield evt_stage_error("deps", str(e))
            yield evt_pipeline_done(ok=False, error=str(e), stages=stage_results)
            return ArtifactBuildResult(ok=False, target_name=target.name, error=str(e))

        # ── Build ──
        yield evt_stage_start("build", "Compile & Release")
        build_start = time.time()

        cmd = target.build_cmd or "mix compile && mix release"
        try:
            proc = subprocess.Popen(
                ["bash", "-c", cmd],
                cwd=str(project_root),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=build_env,
            )
            for line in iter(proc.stdout.readline, ""):
                yield evt_log(line.rstrip("\n"), "build")
            proc.wait()
            build_ms = int((time.time() - build_start) * 1000)

            if proc.returncode != 0:
                yield evt_stage_error("build", f"mix compile/release failed (exit {proc.returncode})", build_ms)
                stage_results.append({"name": "build", "status": "error", "duration_ms": build_ms})
                stage_results.append({"name": "verify", "status": "skipped"})
                total_ms = int((time.time() - pipeline_start) * 1000)
                yield evt_pipeline_done(ok=False, total_ms=total_ms, error="mix failed", stages=stage_results)
                return ArtifactBuildResult(ok=False, target_name=target.name, duration_ms=total_ms, error="mix failed")

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
            release_dirs = [d for d in out_path.iterdir() if d.is_dir()]
            if release_dirs:
                yield evt_log(f"Found {len(release_dirs)} release(s):", "verify")
                for d in release_dirs:
                    yield evt_log(f"  {d.name}/", "verify")
            else:
                yield evt_log("Release directory empty", "verify")
        else:
            yield evt_log(f"Output directory not found: {output_dir}", "verify")
            yield evt_log("(mix compile may have succeeded without mix release)", "verify")

        verify_ms = int((time.time() - verify_start) * 1000)
        yield evt_stage_done("verify", verify_ms)
        stage_results.append({"name": "verify", "status": "done", "duration_ms": verify_ms})

        total_ms = int((time.time() - pipeline_start) * 1000)
        yield evt_pipeline_done(ok=True, total_ms=total_ms, stages=stage_results)
        return ArtifactBuildResult(ok=True, target_name=target.name, output_dir=str(out_path), duration_ms=total_ms)
