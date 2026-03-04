"""
Makefile builder — runs Makefile targets with structured SSE events.

Supports:
  - Single target mode: run `make <build_target>`
  - Compound targets: parses Makefile to detect dependencies
    e.g. `check: lint types test` → runs lint, types, test as stages
  - Streaming: yields structured event dicts for SSE
  - Duration tracking per stage and overall
"""

from __future__ import annotations

import os
import re
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


class MakefileBuilder(ArtifactBuilder):
    """Runs Makefile targets with structured event streaming."""

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
                m = re.match(
                    r'^([a-zA-Z_][\w-]*):\s*(.*?)(?:\s*##\s*(.*))?$', line
                )
                if m:
                    name = m.group(1)
                    deps = m.group(2).strip().split() if m.group(2).strip() else []
                    desc = m.group(3) or ""
                    if not name.startswith("."):
                        targets[name] = {
                            "name": name,
                            "deps": deps,
                            "description": desc,
                        }
        except OSError:
            pass
        return targets

    def _detect_stages(
        self, target: ArtifactTarget, project_root: Path
    ) -> list[ArtifactStageInfo]:
        """Detect actual stages by parsing Makefile dependencies.

        If the build_target has dependencies that are themselves Makefile
        targets (e.g. `check: lint types test`), each dep becomes a stage.
        Otherwise, the target itself is the single stage.
        """
        build_target = target.build_target or target.name
        known = self._parse_makefile_targets(project_root)

        if build_target in known:
            deps = known[build_target].get("deps", [])
            # Only use deps as stages if they are themselves Makefile targets
            dep_stages = [d for d in deps if d in known]
            if dep_stages:
                return [
                    ArtifactStageInfo(
                        name=d,
                        label=known[d].get("description", "")
                            or d.capitalize(),
                    )
                    for d in dep_stages
                ]

        # Single stage
        desc = ""
        if build_target in known:
            desc = known[build_target].get("description", "")
        return [ArtifactStageInfo(
            name=build_target,
            label=desc or build_target.capitalize(),
            description=f"make {build_target}",
        )]

    def build(
        self,
        target: ArtifactTarget,
        project_root: Path,
    ) -> Generator[dict, None, ArtifactBuildResult]:
        """Run make target(s) with structured event streaming."""
        build_target = target.build_target or target.name
        makefile = project_root / "Makefile"

        if not makefile.exists():
            yield evt_pipeline_start([])
            yield evt_pipeline_done(
                ok=False, error="No Makefile found"
            )
            return ArtifactBuildResult(
                ok=False, target_name=target.name, error="No Makefile found"
            )

        # Detect stages from Makefile deps
        stage_list = self._detect_stages(target, project_root)
        yield evt_pipeline_start(stage_list)

        pipeline_start = time.time()
        stage_results = []
        all_ok = True

        # Build environment
        build_env = {
            **os.environ,
            "DEVOPS_BUILD_TARGET": target.name,
            "DEVOPS_BUILD_KIND": target.kind,
            "DEVOPS_PROJECT_ROOT": str(project_root),
        }

        # Run each stage independently if compound target, or single target
        if len(stage_list) > 1:
            # Compound: run each dep target separately
            for stage_info in stage_list:
                ok, duration_ms = yield from self._run_make_stage(
                    stage_info.name, stage_info, project_root, build_env
                )
                stage_results.append({
                    "name": stage_info.name,
                    "status": "done" if ok else "error",
                    "duration_ms": duration_ms,
                })
                if not ok:
                    all_ok = False
                    # Mark remaining stages as skipped
                    for remaining in stage_list[stage_list.index(stage_info) + 1:]:
                        stage_results.append({
                            "name": remaining.name,
                            "status": "skipped",
                        })
                    break
        else:
            # Single target
            stage_info = stage_list[0]
            ok, duration_ms = yield from self._run_make_stage(
                build_target, stage_info, project_root, build_env
            )
            stage_results.append({
                "name": stage_info.name,
                "status": "done" if ok else "error",
                "duration_ms": duration_ms,
            })
            all_ok = ok

        total_ms = int((time.time() - pipeline_start) * 1000)
        error = ""
        if not all_ok:
            failed = [s for s in stage_results if s["status"] == "error"]
            error = f"Stage failed: {failed[0]['name']}" if failed else "Build failed"

        yield evt_pipeline_done(
            ok=all_ok, total_ms=total_ms, error=error, stages=stage_results
        )

        return ArtifactBuildResult(
            ok=all_ok,
            target_name=target.name,
            output_dir=target.output_dir,
            duration_ms=total_ms,
            error=error,
        )

    def _run_make_stage(
        self,
        make_target: str,
        stage_info: ArtifactStageInfo,
        project_root: Path,
        env: dict,
    ) -> Generator[dict, None, tuple[bool, int]]:
        """Run a single `make <target>` and yield structured events.

        Returns (ok, duration_ms).
        """
        yield evt_stage_start(stage_info.name, stage_info.label)

        t0 = time.time()

        try:
            proc = subprocess.Popen(
                ["make", make_target],
                cwd=str(project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )

            for line in iter(proc.stdout.readline, ""):
                yield evt_log(line.rstrip("\n"), stage_info.name)

            proc.wait()
            duration_ms = int((time.time() - t0) * 1000)

            if proc.returncode == 0:
                yield evt_stage_done(stage_info.name, duration_ms)
                return (True, duration_ms)
            else:
                yield evt_stage_error(
                    stage_info.name,
                    f"make {make_target} failed (exit code {proc.returncode})",
                    duration_ms,
                )
                return (False, duration_ms)

        except FileNotFoundError:
            duration_ms = int((time.time() - t0) * 1000)
            yield evt_stage_error(
                stage_info.name,
                "'make' command not found — is it installed?",
                duration_ms,
            )
            return (False, duration_ms)

        except Exception as e:
            duration_ms = int((time.time() - t0) * 1000)
            yield evt_stage_error(
                stage_info.name, str(e), duration_ms
            )
            return (False, duration_ms)
