"""
Maven ecosystem adapter — Java package management.

Manifest: ``pom.xml`` (XML).
Lock: None (Maven uses repository resolution).
CLI: ``mvn``.

Parses ``<dependencies>`` section using stdlib ``xml.etree.ElementTree``.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from ..ecosystem import EcosystemAdapter
from ..models import DeclaredDep, ManifestInfo, ParsedManifest
from ..parsers.generic_parser import GenericParser

logger = logging.getLogger(__name__)

# Maven POM namespace
_NS = {"m": "http://maven.apache.org/POM/4.0.0"}


class MavenAdapter(EcosystemAdapter):
    """Ecosystem adapter for Java (Maven)."""

    @property
    def id(self) -> str:
        return "maven"

    @property
    def name(self) -> str:
        return "Java (Maven)"

    @property
    def cli(self) -> str:
        return "mvn"

    def detect(self, directory: Path) -> list[ManifestInfo]:
        pom = directory / "pom.xml"
        if not pom.is_file():
            return []
        return [ManifestInfo(
            ecosystem="maven", manifest_file="pom.xml", manifest_path=".",
            lock_file=None, cli="mvn", cli_available=self.is_available(),
            mtime=pom.stat().st_mtime,
        )]

    def parse_manifest(self, manifest: Path, lock_file: Path | None) -> ParsedManifest:
        deps: list[DeclaredDep] = []
        dev_deps: list[DeclaredDep] = []
        source_path = "."

        try:
            tree = ET.parse(manifest)
            root = tree.getroot()

            # Handle both namespaced and non-namespaced POMs
            # Try namespaced first
            dep_els = root.findall(".//m:dependencies/m:dependency", _NS)
            if not dep_els:
                dep_els = root.findall(".//dependencies/dependency")

            for dep_el in dep_els:
                group_id = _text(dep_el, "groupId") or _text(dep_el, "m:groupId", _NS)
                artifact_id = _text(dep_el, "artifactId") or _text(dep_el, "m:artifactId", _NS)
                version = _text(dep_el, "version") or _text(dep_el, "m:version", _NS)
                scope = _text(dep_el, "scope") or _text(dep_el, "m:scope", _NS)

                if not artifact_id:
                    continue

                name = f"{group_id}:{artifact_id}" if group_id else artifact_id
                is_dev = scope in ("test", "provided")

                dep = DeclaredDep(
                    name=name,
                    version_spec=version or "",
                    pinned_version=version or "",
                    group="dev" if is_dev else "main",
                    source_file="pom.xml",
                    source_path=source_path,
                )
                if is_dev:
                    dev_deps.append(dep)
                else:
                    deps.append(dep)

        except (ET.ParseError, OSError) as exc:
            logger.debug("Failed to parse %s: %s", manifest, exc)

        info = ManifestInfo(
            ecosystem="maven", manifest_file=manifest.name, manifest_path=source_path,
            lock_file=None, cli="mvn", cli_available=True,
            mtime=manifest.stat().st_mtime if manifest.is_file() else 0.0,
        )
        return ParsedManifest(info=info, dependencies=tuple(deps),
                              dev_dependencies=tuple(dev_deps), total=len(deps) + len(dev_deps))

    def install_cmd(self, directory: Path, *, dev: bool = False, frozen: bool = True) -> list[str]:
        return ["mvn", "dependency:resolve", "-q"]

    def update_cmd(self, directory: Path, packages: list[str] | None = None) -> list[str]:
        # Maven doesn't have a native "update all deps" command
        # versions-maven-plugin is the closest
        return ["mvn", "versions:use-latest-releases", "-q"]

    def update_single_cmd(self, directory: Path, package: str, version: str | None = None) -> list[str]:
        # Maven requires POM edits — no single-command update
        return ["mvn", "versions:use-latest-releases", "-q"]

    def snapshot_files(self, directory: Path) -> list[Path]:
        pom = directory / "pom.xml"
        return [pom] if pom.is_file() else []

    def restore_cmd(self, directory: Path) -> list[str]:
        return ["mvn", "dependency:resolve", "-q"]

    def create_output_parser(self, scope: str) -> GenericParser:
        return GenericParser(scope, "maven")

    def fetch_latest_version(self, package: str) -> str | None:
        return None

    def check_deprecated(self, package: str, version: str) -> tuple[bool, str]:
        return False, ""


def _text(el: ET.Element, tag: str, ns: dict | None = None) -> str:
    """Extract text from a child element, or empty string."""
    child = el.find(tag, ns) if ns else el.find(tag)
    return (child.text or "").strip() if child is not None else ""
