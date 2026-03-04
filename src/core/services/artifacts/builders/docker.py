"""
Docker builder — builds container images with streaming output.

Runs `docker build` (or `podman build`) to produce container images.
Supports tagging, build args, and multi-stage builds.

Does NOT push — that's a separate publish step (Phase 5).
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Generator

from ..engine import ArtifactBuildResult, ArtifactTarget
from .base import ArtifactBuilder, ArtifactStageInfo


class DockerBuilder(ArtifactBuilder):
    """Builds Docker/Podman container images."""

    def name(self) -> str:
        return "docker"

    def label(self) -> str:
        return "Docker"

    def stages(self, target: ArtifactTarget) -> list[ArtifactStageInfo]:
        return [ArtifactStageInfo(
            name="build",
            label="Build Image",
            description="docker build",
        )]

    def _detect_engine(self) -> str | None:
        """Detect which container engine is available."""
        for engine in ["docker", "podman"]:
            try:
                result = subprocess.run(
                    [engine, "version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    return engine
            except (OSError, subprocess.TimeoutExpired):
                continue
        return None

    def _resolve_tag(self, target: ArtifactTarget, project_root: Path) -> str:
        """Resolve the image tag from config or project name."""
        # Check config for explicit tag
        tag = target.config.get("tag", "")
        if tag:
            return tag

        # Default: project directory name + ":latest"
        project_name = project_root.name.lower().replace("_", "-")

        # Try git describe for version
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--always"],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=5,
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
    ) -> Generator[str, None, ArtifactBuildResult]:
        """Run docker build with streaming output."""

        # Detect container engine
        engine = self._detect_engine()
        if not engine:
            yield "❌ Neither docker nor podman found"
            yield "   Install Docker: https://docs.docker.com/get-docker/"
            yield "   Or Podman: https://podman.io/getting-started/installation"
            return ArtifactBuildResult(
                ok=False,
                target_name=target.name,
                error="No container engine found (docker/podman)",
            )

        # Check for Dockerfile
        dockerfile = target.config.get("dockerfile", "Dockerfile")
        dockerfile_path = project_root / dockerfile
        if not dockerfile_path.exists():
            yield f"❌ {dockerfile} not found at {project_root}"
            return ArtifactBuildResult(
                ok=False,
                target_name=target.name,
                error=f"{dockerfile} not found",
            )

        tag = self._resolve_tag(target, project_root)

        # Build command
        cmd = [engine, "build"]

        # Add tag
        cmd.extend(["-t", tag])

        # Add Dockerfile if non-default
        if dockerfile != "Dockerfile":
            cmd.extend(["-f", dockerfile])

        # Add build context (project root)
        context = target.config.get("context", ".")
        cmd.append(context)

        # Add any extra build args from config
        build_args = target.config.get("build_args", {})
        for key, val in build_args.items():
            cmd.extend(["--build-arg", f"{key}={val}"])

        yield f"━━━ 🐳 Building container image ━━━"
        yield f"    Engine: {engine}"
        yield f"    Tag: {tag}"
        yield f"    Dockerfile: {dockerfile}"
        yield f"    Context: {context}"
        yield f"    Project: {project_root}"
        yield ""

        t0 = time.time()

        try:
            proc = subprocess.Popen(
                cmd,
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
                    "DOCKER_BUILDKIT": "1",
                },
            )

            for line in iter(proc.stdout.readline, ""):
                yield line.rstrip("\n")

            proc.wait()
            duration_ms = int((time.time() - t0) * 1000)

            if proc.returncode == 0:
                # Get image size
                try:
                    inspect = subprocess.run(
                        [engine, "image", "inspect", tag,
                         "--format", "{{.Size}}"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if inspect.returncode == 0:
                        size_bytes = int(inspect.stdout.strip())
                        size_mb = size_bytes / (1024 * 1024)
                        yield ""
                        yield f"📦 Image: {tag}  ({size_mb:.1f} MB)"
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    pass

                yield ""
                yield f"✅ Container build succeeded in {duration_ms}ms"
                return ArtifactBuildResult(
                    ok=True,
                    target_name=target.name,
                    output_dir=tag,
                    duration_ms=duration_ms,
                )
            else:
                yield ""
                yield f"❌ Container build failed (exit code {proc.returncode})"
                return ArtifactBuildResult(
                    ok=False,
                    target_name=target.name,
                    duration_ms=duration_ms,
                    error=f"{engine} build failed with exit code {proc.returncode}",
                )

        except FileNotFoundError:
            duration_ms = int((time.time() - t0) * 1000)
            yield f"❌ '{engine}' command not found"
            return ArtifactBuildResult(
                ok=False,
                target_name=target.name,
                duration_ms=duration_ms,
                error=f"{engine} command not found",
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
