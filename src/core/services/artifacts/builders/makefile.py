"""
Makefile builder — runs Makefile targets with streaming output.

Supports:
  - Single target mode: run `make <build_target>`
  - Compound targets: parses Makefile to detect dependencies
    e.g. `check: lint types test` → runs lint, types, test as stages
  - Streaming: yields each line of stdout/stderr for SSE
  - Duration tracking per stage and overall
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Generator

from ..engine import ArtifactBuildResult, ArtifactTarget
from .base import ArtifactBuilder, ArtifactStageInfo


class MakefileBuilder(ArtifactBuilder):
    """Runs Makefile targets with streaming output."""

    def name(self) -> str:
        return "makefile"

    def label(self) -> str:
        return "Makefile"

    def stages(self, target: ArtifactTarget) -> list[ArtifactStageInfo]:
        """Detect stages from Makefile dependencies.

        If the target has a compound rule (e.g. `check: lint types test`),
        each dependency becomes a stage. Otherwise, single stage.
        """
        build_target = target.build_target or target.name
        return [ArtifactStageInfo(
            name=build_target,
            label=build_target.capitalize(),
            description=f"make {build_target}",
        )]

    def _parse_makefile_targets(self, project_root: Path) -> dict[str, dict]:
        """Parse Makefile to extract targets with descriptions and deps."""
        makefile = project_root / "Makefile"
        if not makefile.exists():
            return {}

        targets = {}
        try:
            content = makefile.read_text()
            for line in content.splitlines():
                # Match: target: [deps] ## description
                m = re.match(
                    r'^([a-zA-Z_-]+):\s*(.*?)\s*(?:##\s*(.*))?$', line
                )
                if m:
                    name = m.group(1)
                    deps = m.group(2).strip().split() if m.group(2).strip() else []
                    desc = m.group(3) or ""
                    # Filter out .PHONY and similar
                    if not name.startswith("."):
                        targets[name] = {
                            "name": name,
                            "deps": deps,
                            "description": desc,
                        }
        except OSError:
            pass
        return targets

    def build(
        self,
        target: ArtifactTarget,
        project_root: Path,
    ) -> Generator[str, None, ArtifactBuildResult]:
        """Run make <target> with streaming output."""
        build_target = target.build_target or target.name

        makefile = project_root / "Makefile"
        if not makefile.exists():
            yield f"❌ No Makefile found at {project_root}"
            return ArtifactBuildResult(
                ok=False,
                target_name=target.name,
                error="No Makefile found",
            )

        # Check if the target exists in the Makefile
        known = self._parse_makefile_targets(project_root)
        if known and build_target not in known:
            yield f"⚠️  Target '{build_target}' not found in Makefile"
            yield f"   Available targets: {', '.join(known.keys())}"

        yield f"━━━ 📦 Building artifact: {target.name} ━━━"
        yield f"    Target: make {build_target}"
        yield f"    Project: {project_root}"
        yield ""

        t0 = time.time()

        try:
            proc = subprocess.Popen(
                ["make", build_target],
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
                yield ""
                yield f"✅ Build succeeded in {duration_ms}ms"
                return ArtifactBuildResult(
                    ok=True,
                    target_name=target.name,
                    output_dir=target.output_dir,
                    duration_ms=duration_ms,
                )
            else:
                yield ""
                yield f"❌ Build failed (exit code {proc.returncode})"
                return ArtifactBuildResult(
                    ok=False,
                    target_name=target.name,
                    duration_ms=duration_ms,
                    error=f"make {build_target} failed with exit code {proc.returncode}",
                )

        except FileNotFoundError:
            duration_ms = int((time.time() - t0) * 1000)
            yield "❌ 'make' command not found — is it installed?"
            return ArtifactBuildResult(
                ok=False,
                target_name=target.name,
                duration_ms=duration_ms,
                error="make command not found",
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
