"""
Pip builder — builds pip wheel/sdist packages with structured SSE events.

Runs `python -m build` to produce distributable wheels and sdists.
Detects version from pyproject.toml or git tags.

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


class PipBuilder(ArtifactBuilder):
    """Builds pip wheel/sdist packages with structured events."""

    def name(self) -> str:
        return "pip"

    def label(self) -> str:
        return "pip (wheel/sdist)"

    def stages(self, target: ArtifactTarget) -> list[ArtifactStageInfo]:
        return [
            ArtifactStageInfo(name="check", label="Check Prerequisites"),
            ArtifactStageInfo(name="build", label="Build Package"),
            ArtifactStageInfo(name="verify", label="Verify Output"),
        ]

    def _detect_version(self, project_root: Path) -> str:
        """Try to detect the project version."""
        pyproject = project_root / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text()
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("version") and "=" in stripped:
                        val = stripped.split("=", 1)[1].strip().strip("\"'")
                        if val:
                            return val
            except OSError:
                pass

        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--always"],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass

        return "unknown"

    def _find_python(self, project_root: Path) -> str:
        """Find the best python command (venv-aware)."""
        venv_python = project_root / ".venv" / "bin" / "python"
        if venv_python.exists():
            return str(venv_python)
        if shutil.which("python3"):
            return "python3"
        if shutil.which("python"):
            return "python"
        return "python"

    def build(
        self,
        target: ArtifactTarget,
        project_root: Path,
    ) -> Generator[dict, None, ArtifactBuildResult]:
        """Run python -m build with structured event streaming."""
        stage_list = self.stages(target)
        yield evt_pipeline_start(stage_list)

        pipeline_start = time.time()
        stage_results = []

        build_env = {
            **os.environ,
            "DEVOPS_BUILD_TARGET": target.name,
            "DEVOPS_BUILD_KIND": target.kind,
            "DEVOPS_PROJECT_ROOT": str(project_root),
        }

        python_cmd = self._find_python(project_root)
        version = self._detect_version(project_root)
        output_dir = target.output_dir or "dist/"

        # ── Stage 1: Check prerequisites ──
        yield evt_stage_start("check", "Check Prerequisites")
        check_start = time.time()

        pyproject = project_root / "pyproject.toml"
        setup_py = project_root / "setup.py"
        if not pyproject.exists() and not setup_py.exists():
            yield evt_log("No pyproject.toml or setup.py found", "check")
            yield evt_stage_error("check", "No pyproject.toml or setup.py found")
            yield evt_pipeline_done(ok=False, error="No build configuration found")
            return ArtifactBuildResult(
                ok=False, target_name=target.name,
                error="No pyproject.toml or setup.py found",
            )

        yield evt_log(f"Python: {python_cmd}", "check")
        yield evt_log(f"Version: {version}", "check")
        yield evt_log(f"Output: {output_dir}", "check")

        # Check if build module is available
        try:
            check_proc = subprocess.run(
                [python_cmd, "-m", "build", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            if check_proc.returncode != 0:
                yield evt_log("python-build not installed, attempting install...", "check")
                pip_cmd = python_cmd.replace("python", "pip")
                install_proc = subprocess.run(
                    [pip_cmd, "install", "build"],
                    capture_output=True, text=True, timeout=60,
                )
                if install_proc.returncode != 0:
                    yield evt_stage_error("check", "Failed to install python build module")
                    yield evt_pipeline_done(ok=False, error="Missing build module")
                    return ArtifactBuildResult(
                        ok=False, target_name=target.name,
                        error="Failed to install python build module",
                    )
                yield evt_log("build module installed", "check")
            else:
                build_version = check_proc.stdout.strip()
                yield evt_log(f"build module: {build_version}", "check")
        except (OSError, subprocess.TimeoutExpired) as e:
            yield evt_stage_error("check", f"Python not accessible: {e}")
            yield evt_pipeline_done(ok=False, error=str(e))
            return ArtifactBuildResult(
                ok=False, target_name=target.name, error=str(e),
            )

        check_ms = int((time.time() - check_start) * 1000)
        yield evt_stage_done("check", check_ms)
        stage_results.append({"name": "check", "status": "done", "duration_ms": check_ms})

        # ── Stage 2: Build ──
        yield evt_stage_start("build", "Build Package")
        build_start = time.time()

        cmd = target.build_cmd or f"{python_cmd} -m build"
        cmd_parts = cmd.split()
        if "--outdir" not in cmd and "-o" not in cmd:
            cmd_parts.extend(["--outdir", str(project_root / output_dir)])

        try:
            proc = subprocess.Popen(
                cmd_parts,
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
                yield evt_stage_error(
                    "build",
                    f"python -m build failed (exit code {proc.returncode})",
                    build_ms,
                )
                stage_results.append({"name": "build", "status": "error", "duration_ms": build_ms})
                stage_results.append({"name": "verify", "status": "skipped"})
                total_ms = int((time.time() - pipeline_start) * 1000)
                yield evt_pipeline_done(
                    ok=False, total_ms=total_ms,
                    error=f"Build failed (exit code {proc.returncode})",
                    stages=stage_results,
                )
                return ArtifactBuildResult(
                    ok=False, target_name=target.name,
                    duration_ms=total_ms,
                    error=f"python -m build failed (exit code {proc.returncode})",
                )

            yield evt_stage_done("build", build_ms)
            stage_results.append({"name": "build", "status": "done", "duration_ms": build_ms})

        except Exception as e:
            build_ms = int((time.time() - build_start) * 1000)
            yield evt_stage_error("build", str(e), build_ms)
            stage_results.append({"name": "build", "status": "error", "duration_ms": build_ms})
            stage_results.append({"name": "verify", "status": "skipped"})
            total_ms = int((time.time() - pipeline_start) * 1000)
            yield evt_pipeline_done(ok=False, total_ms=total_ms, error=str(e), stages=stage_results)
            return ArtifactBuildResult(
                ok=False, target_name=target.name, duration_ms=total_ms, error=str(e),
            )

        # ── Stage 3: Verify output ──
        yield evt_stage_start("verify", "Verify Output")
        verify_start = time.time()

        out_path = project_root / output_dir
        if out_path.exists():
            built_files = list(out_path.glob("*.whl")) + list(out_path.glob("*.tar.gz"))
            if built_files:
                yield evt_log(f"Found {len(built_files)} artifact(s):", "verify")
                for f in sorted(built_files, key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
                    size_kb = f.stat().st_size / 1024
                    yield evt_log(f"  {f.name}  ({size_kb:.1f} KB)", "verify")
            else:
                yield evt_log("No .whl or .tar.gz files found in output", "verify")
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
