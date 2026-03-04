"""
GitHub Release publisher — creates releases and uploads artifacts.

Uses the `gh` CLI (already authenticated) via the project's `run_gh` helper.

Stages: validate → tag → release → upload → verify
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Generator

from src.core.services.git.ops import run_gh, run_git

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


class GitHubReleasePublisher(ArtifactPublisher):
    """Creates GitHub Releases and uploads built artifacts."""

    def name(self) -> str:
        return "github-release"

    def label(self) -> str:
        return "GitHub Release"

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
        """Create a GitHub Release with attached files."""

        tag = tag_name or f"v{version}"
        stage_list = [
            ArtifactStageInfo(name="validate", label="Validate"),
            ArtifactStageInfo(name="tag", label="Create Tag"),
            ArtifactStageInfo(name="release", label="Create Release"),
            ArtifactStageInfo(name="upload", label="Upload Artifacts"),
            ArtifactStageInfo(name="verify", label="Verify Release"),
        ]
        yield evt_pipeline_start(stage_list)
        pipeline_start = time.time()
        stage_results = []

        # ── Stage 1: Validate ──
        yield evt_stage_start("validate", "Validate")
        val_start = time.time()

        # Check gh auth
        r = run_gh("auth", "status", cwd=project_root, timeout=10)
        if r.returncode != 0:
            yield evt_log("gh CLI not authenticated", "validate")
            yield evt_stage_error("validate", "gh auth failed — run 'gh auth login'")
            _skip_remaining(stage_results, ["validate", "tag", "release", "upload", "verify"], "validate")
            yield evt_pipeline_done(ok=False, error="gh not authenticated", stages=stage_results)
            return ArtifactPublishResult(
                ok=False, target_name=target.name,
                publish_target="github-release", error="gh not authenticated",
            )
        yield evt_log("gh CLI authenticated ✓", "validate")

        # Check files exist
        existing_files = [f for f in files if f.exists()]
        if not existing_files:
            yield evt_log(f"No files found to upload ({len(files)} paths checked)", "validate")
            yield evt_stage_error("validate", "No publishable files found")
            _skip_remaining(stage_results, ["validate", "tag", "release", "upload", "verify"], "validate")
            yield evt_pipeline_done(ok=False, error="No files to upload", stages=stage_results)
            return ArtifactPublishResult(
                ok=False, target_name=target.name,
                publish_target="github-release", error="No files to upload",
            )
        for f in existing_files:
            size_kb = f.stat().st_size / 1024
            yield evt_log(f"  {f.name}  ({size_kb:.1f} KB)", "validate")
        yield evt_log(f"{len(existing_files)} file(s) ready", "validate")

        # Check if tag already exists (locally or remote)
        r = run_git("tag", "--list", tag, cwd=project_root)
        if r.returncode == 0 and tag in r.stdout.strip().splitlines():
            yield evt_log(f"Tag '{tag}' already exists locally", "validate")
            # Check if release exists
            r2 = run_gh("release", "view", tag, "--json", "tagName", cwd=project_root, timeout=15)
            if r2.returncode == 0:
                yield evt_log(f"Release '{tag}' already exists on GitHub", "validate")
                yield evt_stage_error("validate", f"Release {tag} already exists")
                _skip_remaining(stage_results, ["validate", "tag", "release", "upload", "verify"], "validate")
                yield evt_pipeline_done(ok=False, error=f"Release {tag} already exists", stages=stage_results)
                return ArtifactPublishResult(
                    ok=False, target_name=target.name,
                    publish_target="github-release", version=version,
                    error=f"Release {tag} already exists",
                )

        val_ms = int((time.time() - val_start) * 1000)
        yield evt_stage_done("validate", val_ms)
        stage_results.append({"name": "validate", "status": "done", "duration_ms": val_ms})

        # ── Stage 2: Tag ──
        yield evt_stage_start("tag", "Create Tag")
        tag_start = time.time()

        # Check if tag exists locally
        r = run_git("tag", "--list", tag, cwd=project_root)
        tag_exists = r.returncode == 0 and tag in r.stdout.strip().splitlines()

        if not tag_exists:
            yield evt_log(f"Creating tag: {tag}", "tag")
            r = run_git("tag", "-a", tag, "-m", f"Release {tag}", cwd=project_root)
            if r.returncode != 0:
                yield evt_stage_error("tag", f"git tag failed: {r.stderr.strip()}")
                _skip_remaining(stage_results, ["tag", "release", "upload", "verify"], "tag")
                total_ms = int((time.time() - pipeline_start) * 1000)
                yield evt_pipeline_done(ok=False, total_ms=total_ms, error="git tag failed", stages=stage_results)
                return ArtifactPublishResult(
                    ok=False, target_name=target.name,
                    publish_target="github-release", version=version,
                    duration_ms=total_ms, error=f"git tag failed: {r.stderr.strip()}",
                )
            yield evt_log(f"Tag {tag} created ✓", "tag")
        else:
            yield evt_log(f"Tag {tag} already exists locally ✓", "tag")

        # Push tag
        yield evt_log(f"Pushing tag {tag} to origin…", "tag")
        r = run_git("push", "origin", tag, cwd=project_root, timeout=30)
        if r.returncode != 0:
            stderr = r.stderr.strip()
            # "already exists" is OK
            if "already exists" not in stderr.lower():
                yield evt_stage_error("tag", f"git push tag failed: {stderr}")
                _skip_remaining(stage_results, ["tag", "release", "upload", "verify"], "tag")
                total_ms = int((time.time() - pipeline_start) * 1000)
                yield evt_pipeline_done(ok=False, total_ms=total_ms, error="push tag failed", stages=stage_results)
                return ArtifactPublishResult(
                    ok=False, target_name=target.name,
                    publish_target="github-release", version=version,
                    duration_ms=total_ms, error=f"push tag failed: {stderr}",
                )
            yield evt_log("Tag already pushed ✓", "tag")
        else:
            yield evt_log("Tag pushed to origin ✓", "tag")

        tag_ms = int((time.time() - tag_start) * 1000)
        yield evt_stage_done("tag", tag_ms)
        stage_results.append({"name": "tag", "status": "done", "duration_ms": tag_ms})

        # ── Stage 3: Create Release ──
        yield evt_stage_start("release", "Create Release")
        rel_start = time.time()

        release_args = ["release", "create", tag, "--title", f"v{version}"]

        if release_notes:
            release_args.extend(["--notes", release_notes])
        else:
            release_args.append("--generate-notes")

        yield evt_log(f"Creating release: {tag}", "release")
        r = run_gh(*release_args, cwd=project_root, timeout=30)
        if r.returncode != 0:
            yield evt_log(f"stderr: {r.stderr.strip()}", "release")
            yield evt_stage_error("release", f"gh release create failed: {r.stderr.strip()}")
            _skip_remaining(stage_results, ["release", "upload", "verify"], "release")
            total_ms = int((time.time() - pipeline_start) * 1000)
            yield evt_pipeline_done(ok=False, total_ms=total_ms, error="release create failed", stages=stage_results)
            return ArtifactPublishResult(
                ok=False, target_name=target.name,
                publish_target="github-release", version=version,
                duration_ms=total_ms, error=f"release create failed: {r.stderr.strip()}",
            )

        release_url = r.stdout.strip()
        yield evt_log(f"Release created: {release_url}", "release")

        rel_ms = int((time.time() - rel_start) * 1000)
        yield evt_stage_done("release", rel_ms)
        stage_results.append({"name": "release", "status": "done", "duration_ms": rel_ms})

        # ── Stage 4: Upload artifacts ──
        yield evt_stage_start("upload", "Upload Artifacts")
        up_start = time.time()

        uploaded = []
        for f in existing_files:
            yield evt_log(f"Uploading: {f.name} ({f.stat().st_size / 1024:.1f} KB)", "upload")
            r = run_gh("release", "upload", tag, str(f), "--clobber", cwd=project_root, timeout=120)
            if r.returncode != 0:
                yield evt_log(f"Failed to upload {f.name}: {r.stderr.strip()}", "upload")
            else:
                uploaded.append(f.name)
                yield evt_log(f"  ✓ {f.name} uploaded", "upload")

        if not uploaded:
            yield evt_stage_error("upload", "No files were uploaded successfully")
            _skip_remaining(stage_results, ["upload", "verify"], "upload")
            total_ms = int((time.time() - pipeline_start) * 1000)
            yield evt_pipeline_done(ok=False, total_ms=total_ms, error="Upload failed", stages=stage_results)
            return ArtifactPublishResult(
                ok=False, target_name=target.name,
                publish_target="github-release", version=version,
                duration_ms=total_ms, error="No files uploaded",
            )

        up_ms = int((time.time() - up_start) * 1000)
        yield evt_stage_done("upload", up_ms)
        stage_results.append({"name": "upload", "status": "done", "duration_ms": up_ms})

        # ── Stage 5: Verify ──
        yield evt_stage_start("verify", "Verify Release")
        ver_start = time.time()

        r = run_gh(
            "release", "view", tag,
            "--json", "tagName,url,assets",
            cwd=project_root, timeout=15,
        )
        final_url = release_url
        if r.returncode == 0:
            try:
                info = json.loads(r.stdout)
                final_url = info.get("url", release_url)
                assets = info.get("assets", [])
                yield evt_log(f"Release: {final_url}", "verify")
                yield evt_log(f"Assets: {len(assets)}", "verify")
                for a in assets:
                    yield evt_log(f"  📦 {a.get('name', '?')}  ({a.get('size', 0) / 1024:.1f} KB)", "verify")
            except (json.JSONDecodeError, KeyError):
                yield evt_log("Release exists but could not parse details", "verify")
        else:
            yield evt_log("Could not verify release (non-critical)", "verify")

        ver_ms = int((time.time() - ver_start) * 1000)
        yield evt_stage_done("verify", ver_ms)
        stage_results.append({"name": "verify", "status": "done", "duration_ms": ver_ms})

        total_ms = int((time.time() - pipeline_start) * 1000)
        yield evt_pipeline_done(ok=True, total_ms=total_ms, stages=stage_results)

        return ArtifactPublishResult(
            ok=True, target_name=target.name,
            publish_target="github-release",
            version=version, url=final_url,
            duration_ms=total_ms,
            files_published=uploaded,
        )


def run_git(
    *args: str, cwd: Path, timeout: int = 30
) -> "subprocess.CompletedProcess[str]":
    """Run a git command. Thin wrapper for subprocess."""
    import subprocess
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        import subprocess as sp
        return sp.CompletedProcess(
            args=["git", *args], returncode=127,
            stdout="", stderr="git not found",
        )
    except subprocess.TimeoutExpired:
        import subprocess as sp
        return sp.CompletedProcess(
            args=["git", *args], returncode=124,
            stdout="", stderr=f"git timed out ({timeout}s)",
        )


def _skip_remaining(
    results: list[dict], all_stages: list[str], failed: str,
) -> None:
    """Mark the failed stage as error and remaining as skipped."""
    found_failed = False
    for s in all_stages:
        if s == failed:
            results.append({"name": s, "status": "error"})
            found_failed = True
        elif found_failed:
            results.append({"name": s, "status": "skipped"})
