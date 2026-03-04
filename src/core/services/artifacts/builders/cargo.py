"""
Cargo builder — builds Rust crates with structured SSE events.

Runs `cargo build --release` to produce binaries/libraries.

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


class CargoBuilder(ArtifactBuilder):
    """Builds Rust crates with structured events."""

    def name(self) -> str:
        return "cargo"

    def label(self) -> str:
        return "cargo (release build)"

    def stages(self, target: ArtifactTarget) -> list[ArtifactStageInfo]:
        return [
            ArtifactStageInfo(name="check", label="Check Prerequisites"),
            ArtifactStageInfo(name="build", label="Build Release"),
            ArtifactStageInfo(name="verify", label="Verify Output"),
        ]

    def build(
        self,
        target: ArtifactTarget,
        project_root: Path,
    ) -> Generator[dict, None, ArtifactBuildResult]:
        """Run cargo build --release with structured event streaming."""
        stage_list = self.stages(target)
        yield evt_pipeline_start(stage_list)

        pipeline_start = time.time()
        stage_results = []
        output_dir = target.output_dir or "target/release/"

        build_env = {
            **os.environ,
            "DEVOPS_BUILD_TARGET": target.name,
            "DEVOPS_BUILD_KIND": target.kind,
            "DEVOPS_PROJECT_ROOT": str(project_root),
        }

        # ── Stage 1: Check prerequisites ──
        yield evt_stage_start("check", "Check Prerequisites")
        check_start = time.time()

        cargo_cmd = shutil.which("cargo")
        if not cargo_cmd:
            yield evt_log("cargo not found in PATH", "check")
            yield evt_stage_error("check", "cargo not found — install Rust toolchain (rustup)")
            yield evt_pipeline_done(ok=False, error="cargo not found")
            return ArtifactBuildResult(ok=False, target_name=target.name, error="cargo not found")

        cargo_toml = project_root / "Cargo.toml"
        if not cargo_toml.exists():
            yield evt_log("No Cargo.toml found", "check")
            yield evt_stage_error("check", "No Cargo.toml found")
            yield evt_pipeline_done(ok=False, error="No Cargo.toml")
            return ArtifactBuildResult(ok=False, target_name=target.name, error="No Cargo.toml")

        # Parse crate name/version
        crate_name = project_root.name
        crate_version = "0.0.0"
        try:
            for line in cargo_toml.read_text().splitlines():
                stripped = line.strip()
                if stripped.startswith("name") and "=" in stripped:
                    crate_name = stripped.split("=", 1)[1].strip().strip('"\'')
                elif stripped.startswith("version") and "=" in stripped:
                    crate_version = stripped.split("=", 1)[1].strip().strip('"\'')
        except OSError:
            pass

        yield evt_log(f"cargo: {cargo_cmd}", "check")
        yield evt_log(f"Crate: {crate_name}@{crate_version}", "check")
        yield evt_log(f"Output: {output_dir}", "check")

        check_ms = int((time.time() - check_start) * 1000)
        yield evt_stage_done("check", check_ms)
        stage_results.append({"name": "check", "status": "done", "duration_ms": check_ms})

        # ── Stage 2: Build ──
        yield evt_stage_start("build", "Build Release")
        build_start = time.time()

        cmd = target.build_cmd or "cargo build --release"

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
                yield evt_stage_error("build", f"cargo build failed (exit {proc.returncode})", build_ms)
                stage_results.append({"name": "build", "status": "error", "duration_ms": build_ms})
                stage_results.append({"name": "verify", "status": "skipped"})
                total_ms = int((time.time() - pipeline_start) * 1000)
                yield evt_pipeline_done(ok=False, total_ms=total_ms, error="cargo build failed", stages=stage_results)
                return ArtifactBuildResult(ok=False, target_name=target.name, duration_ms=total_ms, error="cargo build failed")

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

        out_path = project_root / output_dir
        if out_path.exists():
            # Look for binaries (no extension or .exe)
            built_files = [f for f in out_path.iterdir() if f.is_file() and not f.name.startswith(".")]
            binaries = [f for f in built_files if not f.suffix or f.suffix == ".exe"]
            libs = [f for f in built_files if f.suffix in (".rlib", ".so", ".dylib", ".dll")]

            if binaries:
                yield evt_log(f"Found {len(binaries)} binary(s):", "verify")
                for f in binaries[:5]:
                    size_kb = f.stat().st_size / 1024
                    yield evt_log(f"  {f.name}  ({size_kb:.1f} KB)", "verify")
            if libs:
                yield evt_log(f"Found {len(libs)} library(s):", "verify")
                for f in libs[:5]:
                    size_kb = f.stat().st_size / 1024
                    yield evt_log(f"  {f.name}  ({size_kb:.1f} KB)", "verify")
            if not binaries and not libs:
                yield evt_log("No binary or library files found", "verify")
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
