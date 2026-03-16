"""
Bundler ecosystem adapter — Ruby package management.

Manifest: ``Gemfile`` (Ruby DSL, line-based).
Lock: ``Gemfile.lock``.
CLI: ``bundle``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ..ecosystem import EcosystemAdapter
from ..models import DeclaredDep, ManifestInfo, ParsedManifest
from ..parsers.generic_parser import GenericParser

logger = logging.getLogger(__name__)

_RE_GEM = re.compile(r"""gem\s+['"]([^'"]+)['"](?:\s*,\s*['"]([^'"]+))?""")


class BundlerAdapter(EcosystemAdapter):
    """Ecosystem adapter for Ruby (Bundler)."""

    @property
    def id(self) -> str:
        return "bundler"

    @property
    def name(self) -> str:
        return "Ruby (bundler)"

    @property
    def cli(self) -> str:
        return "bundle"

    def detect(self, directory: Path) -> list[ManifestInfo]:
        gemfile = directory / "Gemfile"
        if not gemfile.is_file():
            return []
        lock = "Gemfile.lock" if (directory / "Gemfile.lock").is_file() else None
        return [ManifestInfo(
            ecosystem="bundler", manifest_file="Gemfile", manifest_path=".",
            lock_file=lock, cli="bundle", cli_available=self.is_available(),
            mtime=gemfile.stat().st_mtime,
        )]

    def parse_manifest(self, manifest: Path, lock_file: Path | None) -> ParsedManifest:
        deps: list[DeclaredDep] = []
        dev_deps: list[DeclaredDep] = []
        source_path = "."

        try:
            in_group = ""
            for line in manifest.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or not stripped:
                    continue
                # Track group blocks: group :development do ... end
                if stripped.startswith("group"):
                    if ":development" in stripped or ":test" in stripped:
                        in_group = "dev"
                    continue
                if stripped == "end":
                    in_group = ""
                    continue

                m = _RE_GEM.match(stripped)
                if m:
                    name = m.group(1)
                    ver = m.group(2) or ""
                    is_dev = in_group == "dev" or ":development" in stripped or ":test" in stripped
                    dep = DeclaredDep(
                        name=name, version_spec=ver, pinned_version="",
                        group="dev" if is_dev else "main",
                        source_file="Gemfile", source_path=source_path,
                    )
                    if is_dev:
                        dev_deps.append(dep)
                    else:
                        deps.append(dep)
        except (OSError, UnicodeDecodeError):
            logger.debug("Failed to parse %s", manifest, exc_info=True)

        info = ManifestInfo(
            ecosystem="bundler", manifest_file=manifest.name, manifest_path=source_path,
            lock_file=lock_file.name if lock_file else None,
            cli="bundle", cli_available=True,
            mtime=manifest.stat().st_mtime if manifest.is_file() else 0.0,
        )
        return ParsedManifest(info=info, dependencies=tuple(deps),
                              dev_dependencies=tuple(dev_deps), total=len(deps) + len(dev_deps))

    def install_cmd(self, directory: Path, *, dev: bool = False, frozen: bool = True) -> list[str]:
        return ["bundle", "install"]

    def update_cmd(self, directory: Path, packages: list[str] | None = None) -> list[str]:
        if packages:
            return ["bundle", "update"] + packages
        return ["bundle", "update"]

    def update_single_cmd(self, directory: Path, package: str, version: str | None = None) -> list[str]:
        return ["bundle", "update", package]

    def snapshot_files(self, directory: Path) -> list[Path]:
        return [directory / n for n in ("Gemfile", "Gemfile.lock") if (directory / n).is_file()]

    def restore_cmd(self, directory: Path) -> list[str]:
        return ["bundle", "install"]

    def create_output_parser(self, scope: str) -> GenericParser:
        return GenericParser(scope, "bundler")

    def fetch_latest_version(self, package: str) -> str | None:
        return None

    def check_deprecated(self, package: str, version: str) -> tuple[bool, str]:
        return False, ""
