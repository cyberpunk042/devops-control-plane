"""
Gradle ecosystem adapter — Java/Kotlin package management.

Manifest: ``build.gradle`` or ``build.gradle.kts`` (Groovy/Kotlin DSL).
Lock: ``gradle.lockfile`` (optional).
CLI: ``gradle``.

Parsing is regex-based on the DSL — covers common patterns:
  ``implementation 'group:artifact:version'``
  ``testImplementation "group:artifact:version"``
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ..ecosystem import EcosystemAdapter
from ..models import DeclaredDep, ManifestInfo, ParsedManifest
from ..parsers.generic_parser import GenericParser

logger = logging.getLogger(__name__)

_MANIFEST_FILES = ("build.gradle", "build.gradle.kts")

# Matches: implementation 'group:artifact:version'
# Also: testImplementation, compileOnly, runtimeOnly, api, etc.
_RE_DEP = re.compile(
    r"""(?:implementation|api|compileOnly|runtimeOnly|testImplementation|"""
    r"""testCompileOnly|testRuntimeOnly|annotationProcessor)\s*"""
    r"""['"(]([^'"():]+):([^'"():]+):([^'"()]+)['")]""",
)

_DEV_CONFIGS = {"testImplementation", "testCompileOnly", "testRuntimeOnly"}


class GradleAdapter(EcosystemAdapter):
    """Ecosystem adapter for Java/Kotlin (Gradle)."""

    @property
    def id(self) -> str:
        return "gradle"

    @property
    def name(self) -> str:
        return "Java (Gradle)"

    @property
    def cli(self) -> str:
        return "gradle"

    def detect(self, directory: Path) -> list[ManifestInfo]:
        for filename in _MANIFEST_FILES:
            path = directory / filename
            if path.is_file():
                lock = "gradle.lockfile" if (directory / "gradle.lockfile").is_file() else None
                return [ManifestInfo(
                    ecosystem="gradle", manifest_file=filename, manifest_path=".",
                    lock_file=lock, cli="gradle", cli_available=self.is_available(),
                    mtime=path.stat().st_mtime,
                )]
        return []

    def parse_manifest(self, manifest: Path, lock_file: Path | None) -> ParsedManifest:
        deps: list[DeclaredDep] = []
        dev_deps: list[DeclaredDep] = []
        source_path = "."

        try:
            content = manifest.read_text(encoding="utf-8")
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("//") or not stripped:
                    continue

                m = _RE_DEP.search(stripped)
                if m:
                    group_id, artifact_id, version = m.group(1), m.group(2), m.group(3)
                    name = f"{group_id}:{artifact_id}"
                    # Check if this is a test/dev config
                    is_dev = any(cfg in stripped for cfg in _DEV_CONFIGS)

                    dep = DeclaredDep(
                        name=name, version_spec=version, pinned_version=version,
                        group="dev" if is_dev else "main",
                        source_file=manifest.name, source_path=source_path,
                    )
                    if is_dev:
                        dev_deps.append(dep)
                    else:
                        deps.append(dep)

        except (OSError, UnicodeDecodeError):
            logger.debug("Failed to parse %s", manifest, exc_info=True)

        info = ManifestInfo(
            ecosystem="gradle", manifest_file=manifest.name, manifest_path=source_path,
            lock_file=lock_file.name if lock_file else None,
            cli="gradle", cli_available=True,
            mtime=manifest.stat().st_mtime if manifest.is_file() else 0.0,
        )
        return ParsedManifest(info=info, dependencies=tuple(deps),
                              dev_dependencies=tuple(dev_deps), total=len(deps) + len(dev_deps))

    def install_cmd(self, directory: Path, *, dev: bool = False, frozen: bool = True) -> list[str]:
        return ["gradle", "dependencies", "--no-daemon", "-q"]

    def update_cmd(self, directory: Path, packages: list[str] | None = None) -> list[str]:
        # Gradle requires build file edits — no native update command
        # Use the dependencies task to at least resolve and report
        return ["gradle", "dependencies", "--no-daemon", "-q"]

    def update_single_cmd(self, directory: Path, package: str, version: str | None = None) -> list[str]:
        return ["gradle", "dependencies", "--no-daemon", "-q"]

    def snapshot_files(self, directory: Path) -> list[Path]:
        files: list[Path] = []
        for name in (*_MANIFEST_FILES, "gradle.lockfile"):
            path = directory / name
            if path.is_file():
                files.append(path)
        return files

    def restore_cmd(self, directory: Path) -> list[str]:
        return ["gradle", "dependencies", "--no-daemon", "-q"]

    def create_output_parser(self, scope: str) -> GenericParser:
        return GenericParser(scope, "gradle")

    def fetch_latest_version(self, package: str) -> str | None:
        return None

    def check_deprecated(self, package: str, version: str) -> tuple[bool, str]:
        return False, ""
