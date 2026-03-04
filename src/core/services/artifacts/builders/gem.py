"""
Gem builder — builds Ruby gems with structured SSE events.

Runs `bundle install` → `gem build`.

Stages: check → install → build → verify
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


class GemBuilder(ArtifactBuilder):
    """Builds Ruby gems with structured events."""

    def name(self) -> str:
        return "gem"

    def label(self) -> str:
        return "gem (build)"

    def stages(self, target: ArtifactTarget) -> list[ArtifactStageInfo]:
        return [
            ArtifactStageInfo(name="check", label="Check Prerequisites"),
            ArtifactStageInfo(name="install", label="Install Dependencies"),
            ArtifactStageInfo(name="build", label="Build Gem"),
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

        build_env = {
            **os.environ,
            "DEVOPS_BUILD_TARGET": target.name,
        }

        # ── Check ──
        yield evt_stage_start("check", "Check Prerequisites")
        check_start = time.time()

        gem_cmd = shutil.which("gem")
        if not gem_cmd:
            yield evt_log("gem not found in PATH", "check")
            yield evt_stage_error("check", "gem not found — install Ruby")
            yield evt_pipeline_done(ok=False, error="gem not found")
            return ArtifactBuildResult(ok=False, target_name=target.name, error="gem not found")

        gemspecs = list(project_root.glob("*.gemspec"))
        if not gemspecs:
            yield evt_log("No .gemspec file found", "check")
            yield evt_stage_error("check", "No .gemspec found")
            yield evt_pipeline_done(ok=False, error="No .gemspec")
            return ArtifactBuildResult(ok=False, target_name=target.name, error="No .gemspec")

        gemspec_name = gemspecs[0].name
        yield evt_log(f"gem: {gem_cmd}", "check")
        yield evt_log(f"Gemspec: {gemspec_name}", "check")

        has_gemfile = (project_root / "Gemfile").exists()
        bundle_cmd = shutil.which("bundle")
        yield evt_log(f"Gemfile: {'yes' if has_gemfile else 'no'}", "check")
        yield evt_log(f"bundle: {bundle_cmd or 'not found'}", "check")

        check_ms = int((time.time() - check_start) * 1000)
        yield evt_stage_done("check", check_ms)
        stage_results.append({"name": "check", "status": "done", "duration_ms": check_ms})

        # ── Install ──
        yield evt_stage_start("install", "Install Dependencies")
        install_start = time.time()

        if has_gemfile and bundle_cmd:
            try:
                proc = subprocess.Popen(
                    ["bundle", "install"],
                    cwd=str(project_root),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, env=build_env,
                )
                for line in iter(proc.stdout.readline, ""):
                    yield evt_log(line.rstrip("\n"), "install")
                proc.wait()
                install_ms = int((time.time() - install_start) * 1000)

                if proc.returncode != 0:
                    yield evt_stage_error("install", f"bundle install failed (exit {proc.returncode})", install_ms)
                    stage_results.append({"name": "install", "status": "error"})
                    yield evt_pipeline_done(ok=False, error="bundle install failed", stages=stage_results)
                    return ArtifactBuildResult(ok=False, target_name=target.name, error="bundle install failed")

                yield evt_stage_done("install", install_ms)
                stage_results.append({"name": "install", "status": "done", "duration_ms": install_ms})
            except Exception as e:
                yield evt_stage_error("install", str(e))
                yield evt_pipeline_done(ok=False, error=str(e), stages=stage_results)
                return ArtifactBuildResult(ok=False, target_name=target.name, error=str(e))
        else:
            yield evt_log("No Gemfile or bundle — skipping dependency install", "install")
            install_ms = int((time.time() - install_start) * 1000)
            yield evt_stage_done("install", install_ms)
            stage_results.append({"name": "install", "status": "done", "duration_ms": install_ms})

        # ── Build ──
        yield evt_stage_start("build", "Build Gem")
        build_start = time.time()

        cmd = target.build_cmd or f"gem build {gemspec_name}"
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
                yield evt_stage_error("build", f"gem build failed (exit {proc.returncode})", build_ms)
                stage_results.append({"name": "build", "status": "error", "duration_ms": build_ms})
                stage_results.append({"name": "verify", "status": "skipped"})
                total_ms = int((time.time() - pipeline_start) * 1000)
                yield evt_pipeline_done(ok=False, total_ms=total_ms, error="gem build failed", stages=stage_results)
                return ArtifactBuildResult(ok=False, target_name=target.name, duration_ms=total_ms, error="gem build failed")

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

        gems = list(project_root.glob("*.gem"))
        if gems:
            yield evt_log(f"Found {len(gems)} .gem file(s):", "verify")
            for f in sorted(gems, key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
                size_kb = f.stat().st_size / 1024
                yield evt_log(f"  {f.name}  ({size_kb:.1f} KB)", "verify")
        else:
            yield evt_log("No .gem files found", "verify")

        verify_ms = int((time.time() - verify_start) * 1000)
        yield evt_stage_done("verify", verify_ms)
        stage_results.append({"name": "verify", "status": "done", "duration_ms": verify_ms})

        total_ms = int((time.time() - pipeline_start) * 1000)
        yield evt_pipeline_done(ok=True, total_ms=total_ms, stages=stage_results)
        return ArtifactBuildResult(
            ok=True, target_name=target.name,
            output_dir=str(project_root), duration_ms=total_ms,
        )
