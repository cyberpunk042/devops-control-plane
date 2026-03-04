"""
Custom builder — user-defined build pipeline.

Pipeline modes:
  A. Single-command mode (default):
     1. scaffold  — Prepare workspace
     2. build     — Run build_cmd

  B. Multi-stage mode (when ``stages`` is configured):
     Each stage runs its own command with independent timing,
     logging, and error handling. Stages are fully observable
     via SSE streaming.

The custom builder adapts to existing project build scripts.
It injects control-plane environment variables so scripts can
output to .pages/ workspace without modification, OR scripts
can read DEVOPS_* env vars to redirect output.

Operable Script Spec:
  A build script is "fully operable" when it supports:
    - DEVOPS_OUTPUT_DIR: redirect build output to this directory
    - DEVOPS_SEGMENT_NAME: the segment name being built
    - DEVOPS_WORKSPACE_DIR: the .pages/<segment> workspace path
    - DEVOPS_PROJECT_ROOT: the project root directory
    - Exit code 0 on success, non-zero on failure
    - stdout/stderr for log streaming

  A script is "partially operable" when it works but doesn't
  read DEVOPS_* env vars — the control plane will run it and
  read output from the configured output_dir.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .base import (
    BuilderInfo,
    ConfigField,
    LogStream,
    PageBuilder,
    SegmentConfig,
    StageInfo,
)


class CustomBuilder(PageBuilder):
    """User-defined build process with multi-stage pipeline support."""

    # ── Internal state for dynamic stages ───────────────────────────

    _segment: SegmentConfig | None = None

    def info(self) -> BuilderInfo:
        return BuilderInfo(
            name="custom",
            label="Custom Build",
            requires=[],
            description="User-defined build command. Fully flexible.",
            available=True,
        )

    def detect(self) -> bool:
        return True  # Always available — the user provides the command

    def config_schema(self) -> list[ConfigField]:
        return [
            # ── Build ──────────────────────────────────────────────
            ConfigField(
                key="build_cmd", label="Build Command", type="textarea",
                description=(
                    "Shell command to run for building. "
                    "Used when no custom stages are defined."
                ),
                placeholder="./scripts/build_site.sh",
                category="Build",
            ),
            ConfigField(
                key="build_cwd", label="Working Directory", type="select",
                description=(
                    "Where to execute build commands. "
                    "'project_root' runs from your project folder (for project scripts). "
                    "'workspace' runs from .pages/<segment>/ (for isolated builds)."
                ),
                default="project_root",
                options={
                    "project_root": "Project Root (recommended for existing scripts)",
                    "workspace": "Workspace (.pages/<segment>/)",
                },
                category="Build",
            ),
            ConfigField(
                key="output_dir", label="Output Directory", type="text",
                description=(
                    "Directory containing built files. "
                    "Relative to the working directory (project root or workspace)."
                ),
                default="build",
                placeholder="site/build",
                category="Build",
            ),

            # ── Preview ────────────────────────────────────────────
            ConfigField(
                key="preview_cmd", label="Preview Command", type="textarea",
                description="Shell command to start a dev server for live preview",
                placeholder="./scripts/build_site.sh --serve",
                category="Preview",
            ),
            ConfigField(
                key="preview_port", label="Preview Port", type="number",
                description="Port the preview dev server listens on",
                default="8300",
                placeholder="3000",
                category="Preview",
            ),

            # ── Environment ────────────────────────────────────────
            ConfigField(
                key="env_vars", label="Environment Variables", type="textarea",
                description=(
                    "KEY=VALUE pairs (one per line) passed to build commands. "
                    "Control-plane vars (DEVOPS_*) are injected automatically."
                ),
                placeholder="SITE_URL=https://example.com\nBASE_URL=/",
                category="Environment",
            ),

            # ── Stages (Advanced) ──────────────────────────────────
            # Stages are configured as a YAML/JSON list in the config
            # modal or pre-filled by the pipeline scanner. Each stage:
            #   {name: "migration", label: "Content Migration",
            #    cmd: "python3 scripts/migrate.py"}
            # The UI will present these as an editable stage list.
        ]

    # ── Pipeline stages (dynamic) ───────────────────────────────────

    def pipeline_stages(self) -> list[StageInfo]:
        """Return pipeline stages — dynamic if custom stages are configured."""
        if self._segment and self._segment.config.get("stages"):
            stages = self._segment.config["stages"]
            return [
                StageInfo(
                    name=s.get("name", f"stage_{i}"),
                    label=s.get("label", s.get("name", f"Stage {i+1}")),
                    description=s.get("description", ""),
                )
                for i, s in enumerate(stages)
            ]

        # Default: scaffold + build
        return [
            StageInfo("scaffold", "Setup Workspace",
                      "Prepare workspace for build"),
            StageInfo("build", "Custom Build",
                      "Run user-provided build command"),
        ]

    def run_stage(
        self,
        stage: str,
        segment: SegmentConfig,
        workspace: Path,
    ) -> LogStream:
        # Store segment for dynamic pipeline_stages()
        self._segment = segment

        # Check if this is a custom-defined stage
        custom_stages = segment.config.get("stages", [])
        if custom_stages:
            for s in custom_stages:
                if s.get("name") == stage:
                    yield from self._run_custom_stage(s, segment, workspace)
                    return

        # Default stages
        if stage == "scaffold":
            yield from self._stage_scaffold(segment, workspace)
        elif stage == "build":
            yield from self._stage_build(segment, workspace)
        else:
            raise RuntimeError(f"Unknown stage: {stage}")

    # ── Environment construction ────────────────────────────────────

    def _build_env(
        self,
        segment: SegmentConfig,
        workspace: Path,
    ) -> dict[str, str]:
        """Build the full environment for subprocess execution.

        Merges:
          1. Current process env
          2. User-defined env_vars from config
          3. DEVOPS_* control-plane variables (always injected)
        """
        env = dict(os.environ)

        # User-defined env vars
        env_str = segment.config.get("env_vars", "")
        if env_str:
            for line in env_str.strip().splitlines():
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()

        # Control-plane variables — always injected
        project_root = self._resolve_project_root(workspace)
        env["DEVOPS_SEGMENT_NAME"] = segment.name
        env["DEVOPS_WORKSPACE_DIR"] = str(workspace)
        env["DEVOPS_PROJECT_ROOT"] = str(project_root)
        env["DEVOPS_OUTPUT_DIR"] = str(
            self._resolve_output_dir(segment, workspace)
        )

        return env

    def _resolve_project_root(self, workspace: Path) -> Path:
        """Derive project root from workspace path.

        Workspace is always at <project_root>/.pages/<segment>/
        so project root is 2 levels up.
        """
        return workspace.parent.parent

    def _resolve_cwd(self, segment: SegmentConfig, workspace: Path) -> str:
        """Resolve the working directory for command execution."""
        cwd_mode = segment.config.get("build_cwd", "project_root")
        if cwd_mode == "workspace":
            return str(workspace)
        # Default: project_root
        return str(self._resolve_project_root(workspace))

    def _resolve_output_dir(
        self,
        segment: SegmentConfig,
        workspace: Path,
    ) -> Path:
        """Resolve the output directory path.

        output_dir config is relative to CWD (project root or workspace).
        """
        output_rel = segment.config.get("output_dir", "build")
        cwd_mode = segment.config.get("build_cwd", "project_root")

        if cwd_mode == "workspace":
            return workspace / output_rel
        return self._resolve_project_root(workspace) / output_rel

    # ── Default stages ──────────────────────────────────────────────

    def _stage_scaffold(self, segment: SegmentConfig, workspace: Path) -> LogStream:
        """Prepare workspace.

        For project_root mode: just ensure workspace exists.
        For workspace mode: symlink source content.
        """
        workspace.mkdir(parents=True, exist_ok=True)

        cwd_mode = segment.config.get("build_cwd", "project_root")
        if cwd_mode == "workspace":
            # Symlink source into workspace
            source = Path(segment.source).resolve()
            content_link = workspace / "content"
            if content_link.exists() or content_link.is_symlink():
                content_link.unlink()
            content_link.symlink_to(source)
            yield f"Linked content → {source}"
        else:
            project_root = self._resolve_project_root(workspace)
            yield f"Project root: {project_root}"
            yield f"Workspace: {workspace}"
            output = self._resolve_output_dir(segment, workspace)
            yield f"Output target: {output}"

    def _stage_build(self, segment: SegmentConfig, workspace: Path) -> LogStream:
        """Run the user-provided build command."""
        build_cmd = segment.config.get(
            "build_cmd", "echo 'No build_cmd configured'"
        )
        cwd = self._resolve_cwd(segment, workspace)
        env = self._build_env(segment, workspace)

        yield f"▶ {build_cmd}"
        yield f"  cwd: {cwd}"

        yield from self._exec_command(build_cmd, cwd, env)

    # ── Custom stage execution ──────────────────────────────────────

    def _run_custom_stage(
        self,
        stage_def: dict,
        segment: SegmentConfig,
        workspace: Path,
    ) -> LogStream:
        """Execute a user-defined pipeline stage."""
        cmd = stage_def.get("cmd", "")
        label = stage_def.get("label", stage_def.get("name", "Unknown"))

        if not cmd:
            yield f"⏭️  {label}: no command defined, skipping"
            return

        # Allow per-stage CWD override (defaults to segment build_cwd)
        stage_cwd = stage_def.get("cwd")
        if stage_cwd == "workspace":
            cwd = str(workspace)
        elif stage_cwd == "project_root":
            cwd = str(self._resolve_project_root(workspace))
        elif stage_cwd:
            # Relative to project root
            cwd = str(self._resolve_project_root(workspace) / stage_cwd)
        else:
            cwd = self._resolve_cwd(segment, workspace)

        env = self._build_env(segment, workspace)

        # Per-stage env overrides
        stage_env = stage_def.get("env", {})
        if stage_env:
            env.update(stage_env)

        yield f"▶ {cmd}"

        yield from self._exec_command(cmd, cwd, env)

    # ── Shared command execution ────────────────────────────────────

    def _exec_command(
        self, cmd: str, cwd: str, env: dict,
    ) -> LogStream:
        """Run a shell command, yielding stdout/stderr lines."""
        proc = subprocess.Popen(
            cmd,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        if proc.stdout:
            for line in proc.stdout:
                yield line.rstrip()
        proc.wait()

        if proc.returncode != 0:
            raise RuntimeError(
                f"Command failed (exit code {proc.returncode}): {cmd}"
            )

        yield "✓ Done"

    # ── Output dir ──────────────────────────────────────────────────

    def output_dir(self, workspace: Path) -> Path:
        """Return the output directory.

        When called from the pipeline runner, we need the segment config
        to resolve output_dir properly. Fall back to workspace/build.
        """
        if self._segment:
            return self._resolve_output_dir(self._segment, workspace)
        return workspace / "build"

    # ── Preview (live dev server) ───────────────────────────────────

    def preview(
        self, segment: SegmentConfig, workspace: Path,
    ) -> tuple[subprocess.Popen, int]:
        """Run the user-provided preview command."""
        preview_cmd = segment.config.get("preview_cmd")
        port = int(segment.config.get("preview_port", 8300))

        if not preview_cmd:
            raise NotImplementedError(
                "No preview_cmd configured for this segment"
            )

        cwd = self._resolve_cwd(segment, workspace)
        env = self._build_env(segment, workspace)

        proc = subprocess.Popen(
            preview_cmd,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        return proc, port
