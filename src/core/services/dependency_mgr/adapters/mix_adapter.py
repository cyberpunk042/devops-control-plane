"""
Mix ecosystem adapter — Elixir package management.

Manifest: ``mix.exs`` (Elixir source).
Lock: ``mix.lock``.
CLI: ``mix``.

Parsing is regex-based: ``{:name, "~> version"}`` patterns.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ..ecosystem import EcosystemAdapter
from ..models import DeclaredDep, ManifestInfo, ParsedManifest
from ..parsers.generic_parser import GenericParser

logger = logging.getLogger(__name__)

# {:name, "~> 1.0"} or {:name, "~> 1.0", only: :test}
_RE_DEP = re.compile(r'\{:(\w+),\s*"([^"]*)"')


class MixAdapter(EcosystemAdapter):
    """Ecosystem adapter for Elixir (Mix/Hex)."""

    @property
    def id(self) -> str:
        return "mix"

    @property
    def name(self) -> str:
        return "Elixir (mix)"

    @property
    def cli(self) -> str:
        return "mix"

    def detect(self, directory: Path) -> list[ManifestInfo]:
        mix_exs = directory / "mix.exs"
        if not mix_exs.is_file():
            return []
        lock = "mix.lock" if (directory / "mix.lock").is_file() else None
        return [ManifestInfo(
            ecosystem="mix", manifest_file="mix.exs", manifest_path=".",
            lock_file=lock, cli="mix", cli_available=self.is_available(),
            mtime=mix_exs.stat().st_mtime,
        )]

    def parse_manifest(self, manifest: Path, lock_file: Path | None) -> ParsedManifest:
        deps: list[DeclaredDep] = []
        dev_deps: list[DeclaredDep] = []
        source_path = "."

        try:
            content = manifest.read_text(encoding="utf-8")
            for m in _RE_DEP.finditer(content):
                name = m.group(1)
                version = m.group(2)
                # Check for "only: :test" or "only: :dev" after the match
                after = content[m.end():m.end() + 40]
                is_dev = "only:" in after and (":test" in after or ":dev" in after)

                dep = DeclaredDep(
                    name=name, version_spec=version, pinned_version="",
                    group="dev" if is_dev else "main",
                    source_file="mix.exs", source_path=source_path,
                )
                if is_dev:
                    dev_deps.append(dep)
                else:
                    deps.append(dep)
        except (OSError, UnicodeDecodeError):
            logger.debug("Failed to parse %s", manifest, exc_info=True)

        info = ManifestInfo(
            ecosystem="mix", manifest_file=manifest.name, manifest_path=source_path,
            lock_file=lock_file.name if lock_file else None,
            cli="mix", cli_available=True,
            mtime=manifest.stat().st_mtime if manifest.is_file() else 0.0,
        )
        return ParsedManifest(info=info, dependencies=tuple(deps),
                              dev_dependencies=tuple(dev_deps), total=len(deps) + len(dev_deps))

    def install_cmd(self, directory: Path, *, dev: bool = False, frozen: bool = True) -> list[str]:
        return ["mix", "deps.get"]

    def update_cmd(self, directory: Path, packages: list[str] | None = None) -> list[str]:
        if packages:
            return ["mix", "deps.update"] + packages
        return ["mix", "deps.update", "--all"]

    def update_single_cmd(self, directory: Path, package: str, version: str | None = None) -> list[str]:
        return ["mix", "deps.update", package]

    def snapshot_files(self, directory: Path) -> list[Path]:
        return [directory / n for n in ("mix.exs", "mix.lock") if (directory / n).is_file()]

    def restore_cmd(self, directory: Path) -> list[str]:
        return ["mix", "deps.get"]

    def create_output_parser(self, scope: str) -> GenericParser:
        return GenericParser(scope, "mix")

    def fetch_latest_version(self, package: str) -> str | None:
        return None

    def check_deprecated(self, package: str, version: str) -> tuple[bool, str]:
        return False, ""
