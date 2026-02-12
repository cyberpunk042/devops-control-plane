"""
MkDocs builder — Python-based documentation generator.

Pipeline stages:
  1. scaffold  — Generate mkdocs.yml from segment config
  2. build     — Run `mkdocs build`

Uses MkDocs (pip install mkdocs) to build static docs from Markdown.
Supports Material for MkDocs theme if installed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

from .base import (
    BuilderInfo,
    ConfigField,
    LogStream,
    PageBuilder,
    SegmentConfig,
    StageInfo,
)


class MkDocsBuilder(PageBuilder):
    """Build docs with MkDocs."""

    def info(self) -> BuilderInfo:
        return BuilderInfo(
            name="mkdocs",
            label="MkDocs",
            requires=[],
            description="Python-based documentation generator. Supports Material theme.",
            install_hint="pip install mkdocs mkdocs-material",
            install_cmd=["pip", "install", "mkdocs", "mkdocs-material"],
        )

    def detect(self) -> bool:
        """Check if mkdocs is importable in the current Python env."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "mkdocs", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def config_schema(self) -> list[ConfigField]:
        return [
            ConfigField(
                key="theme", label="Theme", type="select",
                description="MkDocs theme to use for rendering",
                default="auto",
                category="Appearance",
                options={
                    "auto": "Auto-detect (Material if installed, else default)",
                    "material": "Material for MkDocs",
                    "mkdocs": "MkDocs Default",
                    "readthedocs": "Read the Docs",
                },
            ),
            ConfigField(
                key="site_url", label="Site URL", type="text",
                description="Canonical URL for the site (for SEO and sitemap)",
                placeholder="https://docs.example.com",
                category="Site Identity",
            ),
            ConfigField(
                key="repo_url", label="Repository URL", type="text",
                description="Link to source repository (shown in header)",
                placeholder="https://github.com/org/repo",
                category="Site Identity",
            ),
            ConfigField(
                key="plugins", label="Plugins", type="textarea",
                description="YAML list of MkDocs plugins (e.g. search, minify)",
                placeholder="- search\n- minify",
                category="Extensions",
            ),
            ConfigField(
                key="markdown_extensions", label="Markdown Extensions", type="textarea",
                description="YAML list of Python Markdown extensions",
                placeholder="- admonition\n- codehilite\n- toc:\n    permalink: true",
                category="Extensions",
            ),
            ConfigField(
                key="extra_css", label="Extra CSS", type="textarea",
                description="YAML list of extra CSS files to include",
                placeholder="- css/custom.css",
                category="Assets",
            ),
            ConfigField(
                key="extra_javascript", label="Extra JavaScript", type="textarea",
                description="YAML list of extra JS files to include",
                placeholder="- js/custom.js",
                category="Assets",
            ),
            ConfigField(
                key="mkdocs", label="Raw Config Override", type="textarea",
                description="Raw YAML merged into mkdocs.yml (advanced — overrides everything above)",
                placeholder="nav:\n  - Home: index.md\n  - About: about.md",
                category="Advanced",
            ),
        ]

    # ── Pipeline stages ─────────────────────────────────────────────

    def pipeline_stages(self) -> list[StageInfo]:
        return [
            StageInfo("scaffold", "Generate mkdocs.yml",
                      "Create MkDocs config file in workspace"),
            StageInfo("build", "MkDocs Build",
                      "Run mkdocs build to generate static HTML"),
        ]

    def run_stage(
        self,
        stage: str,
        segment: SegmentConfig,
        workspace: Path,
    ) -> LogStream:
        if stage == "scaffold":
            yield from self._stage_scaffold(segment, workspace)
        elif stage == "build":
            yield from self._stage_build(segment, workspace)
        else:
            raise RuntimeError(f"Unknown stage: {stage}")

    # ── Stage implementations ───────────────────────────────────────

    def _stage_scaffold(self, segment: SegmentConfig, workspace: Path) -> LogStream:
        """Generate mkdocs.yml in the workspace."""
        workspace.mkdir(parents=True, exist_ok=True)

        source = Path(segment.source).resolve()
        site_name = segment.config.get("title", segment.name.title())

        # Theme: configurable, with auto-detect fallback
        theme_cfg = segment.config.get("theme", "auto")
        if theme_cfg == "auto":
            has_material = False
            try:
                result = subprocess.run(
                    [sys.executable, "-c", "import material"],
                    capture_output=True, timeout=5,
                )
                has_material = result.returncode == 0
            except Exception:
                pass
            theme_name = "material" if has_material else "mkdocs"
        else:
            theme_name = theme_cfg
        yield f"Theme: {theme_name}"

        # Build mkdocs.yml
        config: dict = {
            "site_name": site_name,
            "docs_dir": str(source),
            "site_dir": str(workspace / "build"),
            "theme": {
                "name": theme_name,
            },
        }

        # Merge structured config fields
        if segment.config.get("site_url"):
            config["site_url"] = segment.config["site_url"]
        if segment.config.get("repo_url"):
            config["repo_url"] = segment.config["repo_url"]
        if segment.config.get("plugins"):
            try:
                import yaml as _y
                config["plugins"] = _y.safe_load(segment.config["plugins"])
            except Exception:
                pass
        if segment.config.get("markdown_extensions"):
            try:
                import yaml as _y
                config["markdown_extensions"] = _y.safe_load(segment.config["markdown_extensions"])
            except Exception:
                pass
        if segment.config.get("extra_css"):
            try:
                import yaml as _y
                config["extra_css"] = _y.safe_load(segment.config["extra_css"])
            except Exception:
                pass
        if segment.config.get("extra_javascript"):
            try:
                import yaml as _y
                config["extra_javascript"] = _y.safe_load(segment.config["extra_javascript"])
            except Exception:
                pass

        # Merge any user-provided raw config override (last — wins)
        user_config = segment.config.get("mkdocs", {})
        if isinstance(user_config, str):
            try:
                user_config = yaml.safe_load(user_config) or {}
            except Exception:
                user_config = {}
        if isinstance(user_config, dict):
            config.update(user_config)

        mkdocs_yml = workspace / "mkdocs.yml"
        mkdocs_yml.write_text(yaml.dump(config, default_flow_style=False), encoding="utf-8")
        yield f"Generated {mkdocs_yml.name}"

    def _stage_build(self, segment: SegmentConfig, workspace: Path) -> LogStream:
        """Run mkdocs build."""
        cmd = [
            sys.executable, "-m", "mkdocs", "build",
            "--config-file", str(workspace / "mkdocs.yml"),
            "--strict",
        ]
        yield f"▶ {' '.join(cmd)}"

        proc = subprocess.Popen(
            cmd,
            cwd=str(workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if proc.stdout:
            for line in proc.stdout:
                yield line.rstrip()
        proc.wait()

        if proc.returncode != 0:
            raise RuntimeError(f"mkdocs build failed (exit code {proc.returncode})")

        yield "Build complete"

    # ── Output dir ──────────────────────────────────────────────────

    def output_dir(self, workspace: Path) -> Path:
        return workspace / "build"

    # ── Preview (live dev server) ───────────────────────────────────

    def preview(
        self, segment: SegmentConfig, workspace: Path,
    ) -> tuple[subprocess.Popen, int]:
        """Start mkdocs serve for live preview."""
        import random

        port = random.randint(8100, 8199)
        proc = subprocess.Popen(
            [sys.executable, "-m", "mkdocs", "serve",
             "--config-file", str(workspace / "mkdocs.yml"),
             "--dev-addr", f"127.0.0.1:{port}",
             "--no-livereload"],
            cwd=str(workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return proc, port
