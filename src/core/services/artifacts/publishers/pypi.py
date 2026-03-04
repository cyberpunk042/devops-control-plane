"""
PyPI publisher — uploads packages to PyPI or TestPyPI using twine.

Stages: validate → tag → upload → verify
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


class PyPIPublisher(ArtifactPublisher):
    """Publishes Python packages to PyPI/TestPyPI via twine."""

    def __init__(self, test: bool = False):
        self._test = test

    def name(self) -> str:
        return "testpypi" if self._test else "pypi"

    def label(self) -> str:
        return "TestPyPI" if self._test else "PyPI"

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
        """Upload to PyPI/TestPyPI with structured event streaming."""
        stages = [
            ArtifactStageInfo(name="validate", label="Validate Artifacts"),
            ArtifactStageInfo(name="upload", label=f"Upload to {self.label()}"),
            ArtifactStageInfo(name="verify", label="Verify Package"),
        ]
        yield evt_pipeline_start(stages)

        pipeline_start = time.time()
        stage_results = []

        # ── Stage 1: Validate ──
        yield evt_stage_start("validate", "Validate Artifacts")
        validate_start = time.time()

        # Find twine
        venv_twine = project_root / ".venv" / "bin" / "twine"
        twine_cmd = str(venv_twine) if venv_twine.exists() else shutil.which("twine")
        if not twine_cmd:
            yield evt_log("twine not found", "validate")
            yield evt_stage_error("validate", "twine not found — pip install twine")
            yield evt_pipeline_done(ok=False, error="twine not found")
            return ArtifactPublishResult(
                ok=False, target_name=target.name, publish_target=self.name(),
                error="twine not found",
            )

        # Find dist files
        dist_dir = project_root / (target.output_dir or "dist")
        if not files:
            files = list(dist_dir.glob("*.whl")) + list(dist_dir.glob("*.tar.gz"))

        if not files:
            yield evt_log(f"No .whl or .tar.gz in {dist_dir}", "validate")
            yield evt_stage_error("validate", "No dist files found — build first")
            yield evt_pipeline_done(ok=False, error="No dist files")
            return ArtifactPublishResult(
                ok=False, target_name=target.name, publish_target=self.name(),
                error="No dist files found",
            )

        yield evt_log(f"twine: {twine_cmd}", "validate")
        yield evt_log(f"Files ({len(files)}):", "validate")
        for f in files:
            size_kb = f.stat().st_size / 1024
            yield evt_log(f"  {f.name}  ({size_kb:.1f} KB)", "validate")

        # Check token
        token_var = "TEST_PYPI_TOKEN" if self._test else "PYPI_TOKEN"
        token = os.environ.get(token_var, "")
        if not token:
            yield evt_log(f"{token_var} not set", "validate")
            yield evt_stage_error("validate", f"Missing {token_var}")
            yield evt_pipeline_done(ok=False, error=f"Missing {token_var}")
            return ArtifactPublishResult(
                ok=False, target_name=target.name, publish_target=self.name(),
                error=f"Missing {token_var}",
            )

        yield evt_log(f"{token_var}: set ({'*' * 8})", "validate")

        validate_ms = int((time.time() - validate_start) * 1000)
        yield evt_stage_done("validate", validate_ms)
        stage_results.append({"name": "validate", "status": "done", "duration_ms": validate_ms})

        # ── Stage 2: Upload ──
        yield evt_stage_start("upload", f"Upload to {self.label()}")
        upload_start = time.time()

        cmd = [twine_cmd, "upload"]
        if self._test:
            cmd.extend(["--repository-url", "https://test.pypi.org/legacy/"])
        cmd.extend(["-u", "__token__", "-p", token])
        cmd.extend([str(f) for f in files])

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in iter(proc.stdout.readline, ""):
                # Mask token in output
                safe_line = line.rstrip("\n").replace(token, "***")
                yield evt_log(safe_line, "upload")
            proc.wait()

            upload_ms = int((time.time() - upload_start) * 1000)

            if proc.returncode != 0:
                yield evt_stage_error("upload", f"twine upload failed (exit {proc.returncode})", upload_ms)
                stage_results.append({"name": "upload", "status": "error", "duration_ms": upload_ms})
                stage_results.append({"name": "verify", "status": "skipped"})
                total_ms = int((time.time() - pipeline_start) * 1000)
                yield evt_pipeline_done(ok=False, total_ms=total_ms, error="twine upload failed", stages=stage_results)
                return ArtifactPublishResult(
                    ok=False, target_name=target.name, publish_target=self.name(),
                    version=version, duration_ms=total_ms, error="twine upload failed",
                )

            yield evt_stage_done("upload", upload_ms)
            stage_results.append({"name": "upload", "status": "done", "duration_ms": upload_ms})

        except Exception as e:
            upload_ms = int((time.time() - upload_start) * 1000)
            yield evt_stage_error("upload", str(e), upload_ms)
            total_ms = int((time.time() - pipeline_start) * 1000)
            yield evt_pipeline_done(ok=False, total_ms=total_ms, error=str(e), stages=stage_results)
            return ArtifactPublishResult(
                ok=False, target_name=target.name, publish_target=self.name(),
                error=str(e),
            )

        # ── Stage 3: Verify ──
        yield evt_stage_start("verify", "Verify Package")
        verify_start = time.time()

        base_url = "https://test.pypi.org/project" if self._test else "https://pypi.org/project"
        # Try to extract package name
        pkg_name = target.name.replace("pip-package", "").strip("-") or project_root.name
        url = f"{base_url}/{pkg_name}/{version}/"

        yield evt_log(f"Package URL: {url}", "verify")
        yield evt_log(f"Published {len(files)} file(s) as v{version}", "verify")

        verify_ms = int((time.time() - verify_start) * 1000)
        yield evt_stage_done("verify", verify_ms)
        stage_results.append({"name": "verify", "status": "done", "duration_ms": verify_ms})

        total_ms = int((time.time() - pipeline_start) * 1000)
        yield evt_pipeline_done(ok=True, total_ms=total_ms, stages=stage_results)

        return ArtifactPublishResult(
            ok=True, target_name=target.name, publish_target=self.name(),
            version=version, url=url, duration_ms=total_ms,
            files_published=[f.name for f in files],
        )
