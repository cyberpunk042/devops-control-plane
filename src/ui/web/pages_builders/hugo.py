"""
Hugo builder — single binary, no runtime dependencies.

Pipeline stages:
  1. scaffold  — Generate hugo.toml, symlink content
  2. build     — Run `hugo` to produce static output

Uses the `hugo` CLI to build static sites from Markdown.
"""

from __future__ import annotations

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


class HugoBuilder(PageBuilder):
    """Build docs with Hugo."""

    def info(self) -> BuilderInfo:
        return BuilderInfo(
            name="hugo",
            label="Hugo",
            requires=["hugo"],
            description="Fast static site generator. Single binary, no runtime.",
            install_hint="Downloads Hugo binary to ~/.local/bin/",
            install_cmd=["__hugo_binary__"],  # Sentinel — handled by install endpoint
        )

    # ── Pipeline stages ─────────────────────────────────────────────

    def pipeline_stages(self) -> list[StageInfo]:
        return [
            StageInfo("scaffold", "Generate Hugo Config",
                      "Create hugo.toml and symlink content directory"),
            StageInfo("build", "Hugo Build",
                      "Run hugo to generate static HTML"),
        ]

    def config_schema(self) -> list[ConfigField]:
        return [
            ConfigField(
                key="base_url", label="Base URL", type="text",
                description="Base URL for the Hugo site (must match hosting path)",
                placeholder="/pages/site/mysite/",
                category="Site Identity",
            ),
            ConfigField(
                key="theme", label="Theme", type="text",
                description="Hugo theme name (must be installed in themes/ directory)",
                placeholder="ananke",
                category="Appearance",
            ),
            ConfigField(
                key="menu", label="Menu Items", type="textarea",
                description="TOML menu configuration (main navigation)",
                placeholder='[[menu.main]]\n  name = "Home"\n  url = "/"\n  weight = 1',
                category="Navigation",
            ),
            ConfigField(
                key="params", label="Site Parameters", type="textarea",
                description="TOML [params] section for custom site variables",
                placeholder='description = "My site"\nfeatured_image = "/images/hero.jpg"',
                category="Advanced",
            ),
            ConfigField(
                key="hugo_extra", label="Raw Config Override", type="textarea",
                description="Raw TOML appended to hugo.toml (advanced)",
                placeholder='[markup.highlight]\n  style = "monokai"',
                category="Advanced",
            ),
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
        """Generate a minimal Hugo config in the workspace."""
        workspace.mkdir(parents=True, exist_ok=True)

        source = Path(segment.source).resolve()
        site_name = segment.config.get("title", segment.name.title())
        # baseURL must match Flask hosting at /pages/site/<name>/
        base_url = segment.config.get("base_url", f"/pages/site/{segment.name}/")

        # Symlink content dir
        content_link = workspace / "content"
        if content_link.exists() or content_link.is_symlink():
            content_link.unlink()
        content_link.symlink_to(source)
        yield f"Linked content → {source}"

        # Write hugo.toml
        config_lines = [f'baseURL = "{base_url}"',
                        f'title = "{site_name}"',
                        'publishDir = "build"',
                        '',
                        '[markup.goldmark.renderer]',
                        '  unsafe = true']

        # Theme
        theme = segment.config.get("theme", "")
        if theme:
            config_lines.insert(3, f'theme = "{theme}"')

        # Menu items
        menu_toml = segment.config.get("menu", "")
        if menu_toml:
            config_lines.append('')
            config_lines.append(menu_toml)

        # Params
        params_toml = segment.config.get("params", "")
        if params_toml:
            config_lines.append('')
            config_lines.append('[params]')
            config_lines.append(params_toml)

        # Raw override
        hugo_extra = segment.config.get("hugo_extra", "")
        if hugo_extra:
            config_lines.append('')
            config_lines.append(hugo_extra)

        (workspace / "hugo.toml").write_text('\n'.join(config_lines) + '\n', encoding="utf-8")
        yield "Generated hugo.toml"

    def _stage_build(self, segment: SegmentConfig, workspace: Path) -> LogStream:
        """Run hugo build."""
        cmd = [
            "hugo",
            "--source", str(workspace),
            "--destination", str(workspace / "build"),
        ]
        yield f"▶ {' '.join(cmd)}"

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if proc.stdout:
            for line in proc.stdout:
                yield line.rstrip()
        proc.wait()

        if proc.returncode != 0:
            raise RuntimeError(f"hugo build failed (exit code {proc.returncode})")

        yield "Build complete"

    # ── Output dir ──────────────────────────────────────────────────

    def output_dir(self, workspace: Path) -> Path:
        return workspace / "build"

    # ── Preview (live dev server) ───────────────────────────────────

    def preview(
        self, segment: SegmentConfig, workspace: Path,
    ) -> tuple[subprocess.Popen, int]:
        """Start hugo server for live preview."""
        import random

        port = random.randint(8200, 8299)
        proc = subprocess.Popen(
            ["hugo", "server", "--source", str(workspace),
             "--port", str(port), "--bind", "127.0.0.1",
             "--disableLiveReload", "--noHTTPCache"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return proc, port
