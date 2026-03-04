"""
Docker builder — builds container images with structured SSE events.

Runs `docker build` (or `podman build`) to produce container images.
Stages: detect → build → inspect
"""

from __future__ import annotations

import os
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


class DockerBuilder(ArtifactBuilder):
    """Builds Docker/Podman container images with structured events."""

    def name(self) -> str:
        return "docker"

    def label(self) -> str:
        return "Docker"

    def stages(self, target: ArtifactTarget) -> list[ArtifactStageInfo]:
        return [
            ArtifactStageInfo(name="detect", label="Detect Engine"),
            ArtifactStageInfo(name="build", label="Build Image"),
            ArtifactStageInfo(name="inspect", label="Inspect Image"),
        ]

    def _detect_engine(self) -> str | None:
        """Detect which container engine is available."""
        for engine in ["docker", "podman"]:
            try:
                result = subprocess.run(
                    [engine, "version"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    return engine
            except (OSError, subprocess.TimeoutExpired):
                continue
        return None

    def _resolve_tag(self, target: ArtifactTarget, project_root: Path) -> str:
        """Resolve the image tag from config or project name."""
        tag = target.config.get("tag", "")
        if tag:
            return tag

        project_name = project_root.name.lower().replace("_", "-")

        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--always"],
                cwd=str(project_root),
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                version = result.stdout.strip()
                return f"{project_name}:{version}"
        except (OSError, subprocess.TimeoutExpired):
            pass

        return f"{project_name}:latest"

    def build(
        self,
        target: ArtifactTarget,
        project_root: Path,
    ) -> Generator[dict, None, ArtifactBuildResult]:
        """Run docker build with structured event streaming."""
        stage_list = self.stages(target)
        yield evt_pipeline_start(stage_list)

        pipeline_start = time.time()
        stage_results = []

        # ── Stage 1: Detect engine ──
        yield evt_stage_start("detect", "Detect Engine")
        detect_start = time.time()

        engine = self._detect_engine()
        if not engine:
            yield evt_log("Neither docker nor podman found", "detect")
            yield evt_stage_error("detect", "No container engine found")
            stage_results.append({"name": "detect", "status": "error"})
            stage_results.append({"name": "build", "status": "skipped"})
            stage_results.append({"name": "inspect", "status": "skipped"})
            yield evt_pipeline_done(
                ok=False, error="No container engine found (docker/podman)",
                stages=stage_results,
            )
            return ArtifactBuildResult(
                ok=False, target_name=target.name,
                error="No container engine found",
            )

        dockerfile = target.config.get("dockerfile", "Dockerfile")
        dockerfile_path = project_root / dockerfile
        if not dockerfile_path.exists():
            yield evt_log(f"{dockerfile} not found at {project_root}", "detect")
            yield evt_stage_error("detect", f"{dockerfile} not found")
            stage_results.append({"name": "detect", "status": "error"})
            stage_results.append({"name": "build", "status": "skipped"})
            stage_results.append({"name": "inspect", "status": "skipped"})
            yield evt_pipeline_done(
                ok=False, error=f"{dockerfile} not found", stages=stage_results,
            )
            return ArtifactBuildResult(
                ok=False, target_name=target.name, error=f"{dockerfile} not found",
            )

        tag = self._resolve_tag(target, project_root)
        yield evt_log(f"Engine: {engine}", "detect")
        yield evt_log(f"Tag: {tag}", "detect")
        yield evt_log(f"Dockerfile: {dockerfile}", "detect")

        detect_ms = int((time.time() - detect_start) * 1000)
        yield evt_stage_done("detect", detect_ms)
        stage_results.append({"name": "detect", "status": "done", "duration_ms": detect_ms})

        # ── Stage 2: Build image ──
        yield evt_stage_start("build", "Build Image")
        build_start = time.time()

        cmd = [engine, "build", "-t", tag]
        if dockerfile != "Dockerfile":
            cmd.extend(["-f", dockerfile])
        context = target.config.get("context", ".")
        cmd.append(context)
        for key, val in target.config.get("build_args", {}).items():
            cmd.extend(["--build-arg", f"{key}={val}"])

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env={
                    **os.environ,
                    "DEVOPS_BUILD_TARGET": target.name,
                    "DEVOPS_BUILD_KIND": target.kind,
                    "DEVOPS_PROJECT_ROOT": str(project_root),
                    "DOCKER_BUILDKIT": "1",
                },
            )

            for line in iter(proc.stdout.readline, ""):
                yield evt_log(line.rstrip("\n"), "build")

            proc.wait()
            build_ms = int((time.time() - build_start) * 1000)

            if proc.returncode != 0:
                yield evt_stage_error(
                    "build",
                    f"{engine} build failed (exit code {proc.returncode})",
                    build_ms,
                )
                stage_results.append({"name": "build", "status": "error", "duration_ms": build_ms})
                stage_results.append({"name": "inspect", "status": "skipped"})
                total_ms = int((time.time() - pipeline_start) * 1000)
                yield evt_pipeline_done(
                    ok=False, total_ms=total_ms,
                    error=f"{engine} build failed",
                    stages=stage_results,
                )
                return ArtifactBuildResult(
                    ok=False, target_name=target.name,
                    duration_ms=total_ms,
                    error=f"{engine} build failed (exit code {proc.returncode})",
                )

            yield evt_stage_done("build", build_ms)
            stage_results.append({"name": "build", "status": "done", "duration_ms": build_ms})

        except Exception as e:
            build_ms = int((time.time() - build_start) * 1000)
            yield evt_stage_error("build", str(e), build_ms)
            stage_results.append({"name": "build", "status": "error", "duration_ms": build_ms})
            stage_results.append({"name": "inspect", "status": "skipped"})
            total_ms = int((time.time() - pipeline_start) * 1000)
            yield evt_pipeline_done(ok=False, total_ms=total_ms, error=str(e), stages=stage_results)
            return ArtifactBuildResult(
                ok=False, target_name=target.name, duration_ms=total_ms, error=str(e),
            )

        # ── Stage 3: Inspect image ──
        yield evt_stage_start("inspect", "Inspect Image")
        inspect_start = time.time()

        try:
            inspect_proc = subprocess.run(
                [engine, "image", "inspect", tag, "--format", "{{.Size}}"],
                capture_output=True, text=True, timeout=10,
            )
            if inspect_proc.returncode == 0:
                size_bytes = int(inspect_proc.stdout.strip())
                size_mb = size_bytes / (1024 * 1024)
                yield evt_log(f"Image: {tag}  ({size_mb:.1f} MB)", "inspect")
            else:
                yield evt_log(f"Image: {tag}  (size unknown)", "inspect")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            yield evt_log(f"Image: {tag}  (inspect failed)", "inspect")

        inspect_ms = int((time.time() - inspect_start) * 1000)
        yield evt_stage_done("inspect", inspect_ms)
        stage_results.append({"name": "inspect", "status": "done", "duration_ms": inspect_ms})

        total_ms = int((time.time() - pipeline_start) * 1000)
        yield evt_pipeline_done(ok=True, total_ms=total_ms, stages=stage_results)

        return ArtifactBuildResult(
            ok=True, target_name=target.name,
            output_dir=tag, duration_ms=total_ms,
        )
