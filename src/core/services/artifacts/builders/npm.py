"""
npm builder — builds Node.js packages with structured SSE events.

Runs `npm ci` + `npm run build` or `npm pack` to produce distributable artifacts.

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


class NpmBuilder(ArtifactBuilder):
    """Builds Node.js packages with structured events."""

    def name(self) -> str:
        return "npm"

    def label(self) -> str:
        return "npm (build/pack)"

    def stages(self, target: ArtifactTarget) -> list[ArtifactStageInfo]:
        return [
            ArtifactStageInfo(name="check", label="Check Prerequisites"),
            ArtifactStageInfo(name="install", label="Install Dependencies"),
            ArtifactStageInfo(name="build", label="Build Package"),
            ArtifactStageInfo(name="verify", label="Verify Output"),
        ]

    def build(
        self,
        target: ArtifactTarget,
        project_root: Path,
    ) -> Generator[dict, None, ArtifactBuildResult]:
        """Run npm build with structured event streaming."""
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
        }

        # ── Stage 1: Check prerequisites ──
        yield evt_stage_start("check", "Check Prerequisites")
        check_start = time.time()

        npm_cmd = shutil.which("npm")
        if not npm_cmd:
            yield evt_log("npm not found in PATH", "check")
            yield evt_stage_error("check", "npm not found — install Node.js")
            yield evt_pipeline_done(ok=False, error="npm not found")
            return ArtifactBuildResult(
                ok=False, target_name=target.name, error="npm not found",
            )

        package_json = project_root / "package.json"
        if not package_json.exists():
            yield evt_log("No package.json found", "check")
            yield evt_stage_error("check", "No package.json found")
            yield evt_pipeline_done(ok=False, error="No package.json found")
            return ArtifactBuildResult(
                ok=False, target_name=target.name, error="No package.json",
            )

        # Read package info
        import json as _json
        try:
            pkg_data = _json.loads(package_json.read_text())
            pkg_name = pkg_data.get("name", "unknown")
            pkg_version = pkg_data.get("version", "0.0.0")
            pkg_scripts = pkg_data.get("scripts", {})
        except (OSError, _json.JSONDecodeError):
            pkg_name, pkg_version, pkg_scripts = "unknown", "0.0.0", {}

        yield evt_log(f"npm: {npm_cmd}", "check")
        yield evt_log(f"Package: {pkg_name}@{pkg_version}", "check")
        yield evt_log(f"Output: {output_dir}", "check")

        has_build_script = "build" in pkg_scripts
        yield evt_log(f"Build script: {'yes' if has_build_script else 'no (will npm pack)'}", "check")

        check_ms = int((time.time() - check_start) * 1000)
        yield evt_stage_done("check", check_ms)
        stage_results.append({"name": "check", "status": "done", "duration_ms": check_ms})

        # ── Stage 2: Install dependencies ──
        yield evt_stage_start("install", "Install Dependencies")
        install_start = time.time()

        # Use npm ci if lock file exists, else npm install
        lock_file = project_root / "package-lock.json"
        install_cmd = ["npm", "ci"] if lock_file.exists() else ["npm", "install"]

        try:
            proc = subprocess.Popen(
                install_cmd,
                cwd=str(project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=build_env,
            )
            for line in iter(proc.stdout.readline, ""):
                yield evt_log(line.rstrip("\n"), "install")
            proc.wait()

            install_ms = int((time.time() - install_start) * 1000)

            if proc.returncode != 0:
                yield evt_stage_error("install", f"npm install failed (exit {proc.returncode})", install_ms)
                stage_results.append({"name": "install", "status": "error", "duration_ms": install_ms})
                stage_results.append({"name": "build", "status": "skipped"})
                stage_results.append({"name": "verify", "status": "skipped"})
                total_ms = int((time.time() - pipeline_start) * 1000)
                yield evt_pipeline_done(ok=False, total_ms=total_ms, error="npm install failed", stages=stage_results)
                return ArtifactBuildResult(ok=False, target_name=target.name, duration_ms=total_ms, error="npm install failed")

            yield evt_stage_done("install", install_ms)
            stage_results.append({"name": "install", "status": "done", "duration_ms": install_ms})

        except Exception as e:
            install_ms = int((time.time() - install_start) * 1000)
            yield evt_stage_error("install", str(e), install_ms)
            stage_results.append({"name": "install", "status": "error"})
            yield evt_pipeline_done(ok=False, error=str(e), stages=stage_results)
            return ArtifactBuildResult(ok=False, target_name=target.name, error=str(e))

        # ── Stage 3: Build ──
        yield evt_stage_start("build", "Build Package")
        build_start = time.time()

        if target.build_cmd:
            cmd = target.build_cmd
        elif has_build_script:
            cmd = "npm run build"
        else:
            cmd = "npm pack"

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
                yield evt_stage_error("build", f"Build failed (exit {proc.returncode})", build_ms)
                stage_results.append({"name": "build", "status": "error", "duration_ms": build_ms})
                stage_results.append({"name": "verify", "status": "skipped"})
                total_ms = int((time.time() - pipeline_start) * 1000)
                yield evt_pipeline_done(ok=False, total_ms=total_ms, error="Build failed", stages=stage_results)
                return ArtifactBuildResult(ok=False, target_name=target.name, duration_ms=total_ms, error="Build failed")

            yield evt_stage_done("build", build_ms)
            stage_results.append({"name": "build", "status": "done", "duration_ms": build_ms})

        except Exception as e:
            build_ms = int((time.time() - build_start) * 1000)
            yield evt_stage_error("build", str(e), build_ms)
            stage_results.append({"name": "build", "status": "error"})
            yield evt_pipeline_done(ok=False, error=str(e), stages=stage_results)
            return ArtifactBuildResult(ok=False, target_name=target.name, error=str(e))

        # ── Stage 4: Verify output ──
        yield evt_stage_start("verify", "Verify Output")
        verify_start = time.time()

        out_path = project_root / output_dir
        if out_path.exists():
            built_files = list(out_path.iterdir())
            file_count = sum(1 for f in built_files if f.is_file())
            yield evt_log(f"Found {file_count} file(s) in {output_dir}", "verify")
            for f in sorted(built_files, key=lambda p: p.stat().st_mtime if p.is_file() else 0, reverse=True)[:8]:
                if f.is_file():
                    size_kb = f.stat().st_size / 1024
                    yield evt_log(f"  {f.name}  ({size_kb:.1f} KB)", "verify")
        else:
            # Check for .tgz from npm pack
            tgz_files = list(project_root.glob("*.tgz"))
            if tgz_files:
                yield evt_log(f"Found {len(tgz_files)} .tgz package(s):", "verify")
                for f in tgz_files:
                    size_kb = f.stat().st_size / 1024
                    yield evt_log(f"  {f.name}  ({size_kb:.1f} KB)", "verify")
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
