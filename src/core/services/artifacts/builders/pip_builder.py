"""
Pip builder — builds pip wheel/sdist packages with streaming output.

Runs `python -m build` to produce distributable wheels and sdists.
Detects version from pyproject.toml or git tags.

Produces output in the configured output_dir (default: dist/).
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Generator

from ..engine import ArtifactBuildResult, ArtifactTarget
from .base import ArtifactBuilder, ArtifactStageInfo


class PipBuilder(ArtifactBuilder):
    """Builds pip wheel/sdist packages."""

    def name(self) -> str:
        return "pip"

    def label(self) -> str:
        return "pip (wheel/sdist)"

    def stages(self, target: ArtifactTarget) -> list[ArtifactStageInfo]:
        """Pip build has a single stage."""
        return [ArtifactStageInfo(
            name="build",
            label="Build",
            description="python -m build",
        )]

    def _detect_version(self, project_root: Path) -> str:
        """Try to detect the project version."""
        # 1. Try pyproject.toml
        pyproject = project_root / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text()
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("version") and "=" in stripped:
                        # version = "0.1.0"
                        val = stripped.split("=", 1)[1].strip().strip("\"'")
                        if val:
                            return val
            except OSError:
                pass

        # 2. Try git describe
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

    def build(
        self,
        target: ArtifactTarget,
        project_root: Path,
    ) -> Generator[str, None, ArtifactBuildResult]:
        """Run python -m build with streaming output."""

        # Check prerequisites
        pyproject = project_root / "pyproject.toml"
        setup_py = project_root / "setup.py"
        if not pyproject.exists() and not setup_py.exists():
            yield "❌ No pyproject.toml or setup.py found"
            return ArtifactBuildResult(
                ok=False,
                target_name=target.name,
                error="No pyproject.toml or setup.py found",
            )

        version = self._detect_version(project_root)
        output_dir = target.output_dir or "dist/"

        yield "━━━ 📦 Building pip package ━━━"
        yield f"    Target: {target.name}"
        yield f"    Version: {version}"
        yield f"    Output: {output_dir}"
        yield f"    Project: {project_root}"
        yield ""

        # Build command
        cmd = target.build_cmd or "python -m build"
        cmd_parts = cmd.split()

        # Add output dir if not already specified
        if "--outdir" not in cmd and "-o" not in cmd:
            cmd_parts.extend(["--outdir", str(project_root / output_dir)])

        t0 = time.time()

        try:
            # Check if build module is available
            check = subprocess.run(
                ["python", "-m", "build", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if check.returncode != 0:
                yield "⚠️  python-build not installed. Installing..."
                install_proc = subprocess.run(
                    ["pip", "install", "build"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if install_proc.returncode != 0:
                    yield f"❌ Failed to install build: {install_proc.stderr}"
                    return ArtifactBuildResult(
                        ok=False,
                        target_name=target.name,
                        error="Failed to install python build module",
                    )
                yield "    ✅ build module installed"
                yield ""

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
                },
            )

            for line in iter(proc.stdout.readline, ""):
                yield line.rstrip("\n")

            proc.wait()
            duration_ms = int((time.time() - t0) * 1000)

            if proc.returncode == 0:
                # List built artifacts
                out_path = project_root / output_dir
                if out_path.exists():
                    built_files = list(out_path.glob("*.whl")) + list(out_path.glob("*.tar.gz"))
                    if built_files:
                        yield ""
                        yield "📦 Built artifacts:"
                        for f in sorted(built_files, key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
                            size_kb = f.stat().st_size / 1024
                            yield f"    {f.name}  ({size_kb:.1f} KB)"

                yield ""
                yield f"✅ Package build succeeded in {duration_ms}ms"
                return ArtifactBuildResult(
                    ok=True,
                    target_name=target.name,
                    output_dir=str(out_path),
                    duration_ms=duration_ms,
                )
            else:
                yield ""
                yield f"❌ Package build failed (exit code {proc.returncode})"
                return ArtifactBuildResult(
                    ok=False,
                    target_name=target.name,
                    duration_ms=duration_ms,
                    error=f"python -m build failed with exit code {proc.returncode}",
                )

        except FileNotFoundError:
            duration_ms = int((time.time() - t0) * 1000)
            yield "❌ 'python' command not found"
            return ArtifactBuildResult(
                ok=False,
                target_name=target.name,
                duration_ms=duration_ms,
                error="python command not found",
            )
        except Exception as e:
            duration_ms = int((time.time() - t0) * 1000)
            yield f"❌ Build error: {e}"
            return ArtifactBuildResult(
                ok=False,
                target_name=target.name,
                duration_ms=duration_ms,
                error=str(e),
            )
