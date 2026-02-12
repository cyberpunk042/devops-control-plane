"""
Sphinx builder — Python documentation generator.

Pipeline stages:
  1. scaffold  — Generate conf.py, symlink source directory
  2. build     — Run `sphinx-build -b html`

Uses Sphinx (Python) to build docs from RST or Markdown (via MyST).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .base import (
    BuilderInfo,
    ConfigField,
    LogStream,
    PageBuilder,
    SegmentConfig,
    StageInfo,
)


class SphinxBuilder(PageBuilder):
    """Build docs with Sphinx."""

    def info(self) -> BuilderInfo:
        return BuilderInfo(
            name="sphinx",
            label="Sphinx",
            requires=[],
            description="Python documentation generator. Supports RST and Markdown (MyST).",
            install_hint="pip install sphinx myst-parser",
            install_cmd=["pip", "install", "sphinx", "myst-parser"],
        )

    def detect(self) -> bool:
        """Check if sphinx-build is available."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "sphinx", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def config_schema(self) -> list[ConfigField]:
        return [
            ConfigField(
                key="theme", label="Theme", type="select",
                description="Sphinx HTML theme for rendering",
                default="auto",
                category="Appearance",
                options={
                    "auto": "Auto-detect (alabaster default)",
                    "alabaster": "Alabaster (built-in)",
                    "sphinx_rtd_theme": "Read the Docs",
                    "furo": "Furo (modern)",
                    "pydata_sphinx_theme": "PyData",
                },
            ),
            ConfigField(
                key="author", label="Author", type="text",
                description="Project author name",
                placeholder="Your Name",
                category="Site Identity",
            ),
            ConfigField(
                key="extensions", label="Extensions", type="textarea",
                description="Comma-separated list of Sphinx extensions",
                placeholder="autodoc, napoleon, intersphinx, myst_parser",
                category="Extensions",
            ),
            ConfigField(
                key="exclude_patterns", label="Exclude Patterns", type="textarea",
                description="Comma-separated glob patterns to exclude",
                placeholder="_build, .DS_Store, *.secret",
                category="Build Options",
            ),
            ConfigField(
                key="conf_extra", label="Raw conf.py Override", type="textarea",
                description="Raw Python code appended to conf.py (advanced)",
                placeholder="html_theme_options = {'navigation_depth': 3}",
                category="Advanced",
            ),
        ]

    # ── Pipeline stages ─────────────────────────────────────────────

    def pipeline_stages(self) -> list[StageInfo]:
        return [
            StageInfo("scaffold", "Generate Sphinx Config",
                      "Create conf.py and symlink source directory"),
            StageInfo("build", "Sphinx Build",
                      "Run sphinx-build to generate HTML output"),
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
        """Generate a minimal Sphinx conf.py in the workspace."""
        workspace.mkdir(parents=True, exist_ok=True)

        source = Path(segment.source).resolve()
        site_name = segment.config.get("title", segment.name.title())

        # Symlink source
        source_link = workspace / "source"
        if source_link.exists() or source_link.is_symlink():
            source_link.unlink()
        source_link.symlink_to(source)
        yield f"Linked source → {source}"

        # Determine extensions
        has_myst = False
        try:
            result = subprocess.run(
                [sys.executable, "-c", "import myst_parser"],
                capture_output=True, timeout=5,
            )
            has_myst = result.returncode == 0
        except Exception:
            pass

        ext_list = []
        if has_myst:
            ext_list.append("myst_parser")
            yield "MyST parser detected — Markdown support enabled"

        # Merge user extensions
        user_ext = segment.config.get("extensions", "")
        if user_ext:
            for ext in user_ext.split(","):
                ext = ext.strip()
                if ext and ext not in ext_list:
                    ext_list.append(ext)

        extensions_str = repr(ext_list)

        # Theme
        theme_cfg = segment.config.get("theme", "auto")
        if theme_cfg == "auto":
            theme_name = "alabaster"
        else:
            theme_name = theme_cfg

        # Exclude patterns
        exclude_cfg = segment.config.get("exclude_patterns", "")
        if exclude_cfg:
            excludes = [p.strip() for p in exclude_cfg.split(",") if p.strip()]
        else:
            excludes = ["_build", ".DS_Store"]

        # Author
        author = segment.config.get("author", "")

        # Generate conf.py
        conf_lines = ["# Auto-generated by DevOps Control Plane",
                      f"project = '{site_name}'",
                      f"extensions = {extensions_str}",
                      f"exclude_patterns = {repr(excludes)}",
                      f"html_theme = '{theme_name}'"]
        if author:
            conf_lines.append(f"author = '{author}'")

        # Raw override
        conf_extra = segment.config.get("conf_extra", "")
        if conf_extra:
            conf_lines.append("")
            conf_lines.append(conf_extra)

        conf_lines.append("")
        (workspace / "conf.py").write_text("\n".join(conf_lines), encoding="utf-8")
        yield "Generated conf.py"

    def _stage_build(self, segment: SegmentConfig, workspace: Path) -> LogStream:
        """Run sphinx-build."""
        cmd = [
            sys.executable, "-m", "sphinx",
            "-b", "html",
            str(workspace / "source"),
            str(workspace / "build"),
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
            raise RuntimeError(f"sphinx-build failed (exit code {proc.returncode})")

        yield "Build complete"

    # ── Output dir ──────────────────────────────────────────────────

    def output_dir(self, workspace: Path) -> Path:
        return workspace / "build"

    # ── Preview (live dev server) ───────────────────────────────────

    def preview(
        self, segment: SegmentConfig, workspace: Path,
    ) -> tuple[subprocess.Popen, int]:
        """Serve built docs with Python's http.server."""
        import random

        port = random.randint(8400, 8499)
        build_dir = workspace / "build"
        proc = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(port)],
            cwd=str(build_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return proc, port
