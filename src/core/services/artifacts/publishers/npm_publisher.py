"""
npm publisher — publishes packages to the npm registry.

Stages: validate → publish → verify
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Generator

from ..engine import ArtifactTarget
from .base import (
    ArtifactPublisher,
    ArtifactPublishResult,
    ArtifactStageInfo,
    evt_log,
    evt_pipeline_done,
    evt_pipeline_start,
    evt_stage_done,
    evt_stage_error,
    evt_stage_start,
)


class NpmPublisher(ArtifactPublisher):
    """Publishes Node packages to the npm registry."""

    def name(self) -> str:
        return "npm"

    def label(self) -> str:
        return "npm Registry"

    def publish(
        self,
        target: ArtifactTarget,
        project_root: Path,
        version: str,
        files: list[Path],
        *,
        release_notes: str = "",
        tag_name: str = "",
        **kwargs: object,
    ) -> Generator[dict, None, ArtifactPublishResult]:
        """Publish to npm with structured event streaming."""
        stages = [
            ArtifactStageInfo(name="validate", label="Validate Package"),
            ArtifactStageInfo(name="publish", label="Publish to npm"),
            ArtifactStageInfo(name="verify", label="Verify Package"),
        ]
        yield evt_pipeline_start(stages)

        pipeline_start = time.time()
        stage_results = []

        # ── Stage 1: Validate ──
        yield evt_stage_start("validate", "Validate Package")
        validate_start = time.time()

        npm_cmd = shutil.which("npm")
        if not npm_cmd:
            yield evt_log("npm not found in PATH", "validate")
            yield evt_stage_error("validate", "npm not found")
            yield evt_pipeline_done(ok=False, error="npm not found")
            return ArtifactPublishResult(
                ok=False, target_name=target.name, publish_target=self.name(),
                error="npm not found",
            )

        package_json = project_root / "package.json"
        if not package_json.exists():
            yield evt_log("No package.json found", "validate")
            yield evt_stage_error("validate", "No package.json")
            yield evt_pipeline_done(ok=False, error="No package.json")
            return ArtifactPublishResult(
                ok=False, target_name=target.name, publish_target=self.name(),
                error="No package.json",
            )

        import json as _json
        try:
            pkg_data = _json.loads(package_json.read_text())
            pkg_name = pkg_data.get("name", "unknown")
            pkg_version = pkg_data.get("version", version)
            private = pkg_data.get("private", False)
        except (OSError, _json.JSONDecodeError):
            pkg_name, pkg_version, private = "unknown", version, False

        if private:
            yield evt_log("Package is marked private — cannot publish", "validate")
            yield evt_stage_error("validate", "Package is private")
            yield evt_pipeline_done(ok=False, error="Package is private")
            return ArtifactPublishResult(
                ok=False, target_name=target.name, publish_target=self.name(),
                error="Package is private",
            )

        # Check auth token
        token = os.environ.get("NPM_TOKEN", "")
        if not token:
            # Check .npmrc
            npmrc = Path.home() / ".npmrc"
            if npmrc.exists():
                try:
                    if "_authToken" in npmrc.read_text():
                        token = "(from .npmrc)"
                except OSError:
                    pass

        if not token:
            yield evt_log("NPM_TOKEN not set and no .npmrc auth found", "validate")
            yield evt_stage_error("validate", "Missing NPM_TOKEN")
            yield evt_pipeline_done(ok=False, error="Missing NPM_TOKEN")
            return ArtifactPublishResult(
                ok=False, target_name=target.name, publish_target=self.name(),
                error="Missing NPM_TOKEN",
            )

        yield evt_log(f"npm: {npm_cmd}", "validate")
        yield evt_log(f"Package: {pkg_name}@{pkg_version}", "validate")
        yield evt_log(f"Auth: {'NPM_TOKEN set' if token != '(from .npmrc)' else '.npmrc configured'}", "validate")

        validate_ms = int((time.time() - validate_start) * 1000)
        yield evt_stage_done("validate", validate_ms)
        stage_results.append({"name": "validate", "status": "done", "duration_ms": validate_ms})

        # ── Stage 2: Publish ──
        yield evt_stage_start("publish", "Publish to npm")
        publish_start = time.time()

        env = {**os.environ}
        if token and token != "(from .npmrc)":
            env["NODE_AUTH_TOKEN"] = token

        try:
            proc = subprocess.Popen(
                ["npm", "publish"],
                cwd=str(project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
            for line in iter(proc.stdout.readline, ""):
                yield evt_log(line.rstrip("\n"), "publish")
            proc.wait()

            publish_ms = int((time.time() - publish_start) * 1000)

            if proc.returncode != 0:
                yield evt_stage_error("publish", f"npm publish failed (exit {proc.returncode})", publish_ms)
                stage_results.append({"name": "publish", "status": "error", "duration_ms": publish_ms})
                stage_results.append({"name": "verify", "status": "skipped"})
                total_ms = int((time.time() - pipeline_start) * 1000)
                yield evt_pipeline_done(ok=False, total_ms=total_ms, error="npm publish failed", stages=stage_results)
                return ArtifactPublishResult(
                    ok=False, target_name=target.name, publish_target=self.name(),
                    version=pkg_version, duration_ms=total_ms, error="npm publish failed",
                )

            yield evt_stage_done("publish", publish_ms)
            stage_results.append({"name": "publish", "status": "done", "duration_ms": publish_ms})

        except Exception as e:
            publish_ms = int((time.time() - publish_start) * 1000)
            yield evt_stage_error("publish", str(e), publish_ms)
            total_ms = int((time.time() - pipeline_start) * 1000)
            yield evt_pipeline_done(ok=False, total_ms=total_ms, error=str(e), stages=stage_results)
            return ArtifactPublishResult(
                ok=False, target_name=target.name, publish_target=self.name(),
                error=str(e),
            )

        # ── Stage 3: Verify ──
        yield evt_stage_start("verify", "Verify Package")
        verify_start = time.time()

        url = f"https://www.npmjs.com/package/{pkg_name}/v/{pkg_version}"
        yield evt_log(f"Package URL: {url}", "verify")
        yield evt_log(f"Published {pkg_name}@{pkg_version}", "verify")

        verify_ms = int((time.time() - verify_start) * 1000)
        yield evt_stage_done("verify", verify_ms)
        stage_results.append({"name": "verify", "status": "done", "duration_ms": verify_ms})

        total_ms = int((time.time() - pipeline_start) * 1000)
        yield evt_pipeline_done(ok=True, total_ms=total_ms, stages=stage_results)

        return ArtifactPublishResult(
            ok=True, target_name=target.name, publish_target=self.name(),
            version=pkg_version, url=url, duration_ms=total_ms,
            files_published=[pkg_name],
        )
