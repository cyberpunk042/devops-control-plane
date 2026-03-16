"""
.NET ecosystem adapter — NuGet package management.

Manifest: ``*.csproj`` or ``*.fsproj`` (XML).
Lock: ``packages.lock.json`` (optional).
CLI: ``dotnet``.

Parses ``<PackageReference Include="X" Version="Y" />`` elements
using stdlib ``xml.etree.ElementTree``.

Detection uses glob patterns for ``*.csproj`` / ``*.fsproj``.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from ..ecosystem import EcosystemAdapter
from ..models import DeclaredDep, ManifestInfo, ParsedManifest
from ..parsers.generic_parser import GenericParser

logger = logging.getLogger(__name__)

_GLOB_PATTERNS = ("*.csproj", "*.fsproj")


class DotnetAdapter(EcosystemAdapter):
    """Ecosystem adapter for .NET (NuGet)."""

    @property
    def id(self) -> str:
        return "dotnet"

    @property
    def name(self) -> str:
        return ".NET (NuGet)"

    @property
    def cli(self) -> str:
        return "dotnet"

    def detect(self, directory: Path) -> list[ManifestInfo]:
        found: list[ManifestInfo] = []
        lock = "packages.lock.json" if (directory / "packages.lock.json").is_file() else None

        for pattern in _GLOB_PATTERNS:
            for proj_file in directory.glob(pattern):
                if proj_file.is_file():
                    found.append(ManifestInfo(
                        ecosystem="dotnet",
                        manifest_file=proj_file.name,
                        manifest_path=".",
                        lock_file=lock,
                        cli="dotnet",
                        cli_available=self.is_available(),
                        mtime=proj_file.stat().st_mtime,
                    ))

        return found

    def parse_manifest(self, manifest: Path, lock_file: Path | None) -> ParsedManifest:
        deps: list[DeclaredDep] = []
        source_path = "."

        try:
            tree = ET.parse(manifest)
            root = tree.getroot()

            # <PackageReference Include="Newtonsoft.Json" Version="13.0.3" />
            # May or may not have a namespace
            for ref in root.iter("PackageReference"):
                name = ref.get("Include", "")
                version = ref.get("Version", "")
                if not name:
                    continue

                # Check for PrivateAssets="all" (typically dev/build tooling)
                private = ref.get("PrivateAssets", "")
                is_dev = private.lower() == "all"

                deps.append(DeclaredDep(
                    name=name,
                    version_spec=version,
                    pinned_version=version,
                    group="dev" if is_dev else "main",
                    source_file=manifest.name,
                    source_path=source_path,
                ))

        except (ET.ParseError, OSError) as exc:
            logger.debug("Failed to parse %s: %s", manifest, exc)

        info = ManifestInfo(
            ecosystem="dotnet", manifest_file=manifest.name, manifest_path=source_path,
            lock_file=lock_file.name if lock_file else None,
            cli="dotnet", cli_available=True,
            mtime=manifest.stat().st_mtime if manifest.is_file() else 0.0,
        )
        return ParsedManifest(info=info, dependencies=tuple(deps),
                              dev_dependencies=(), total=len(deps))

    def install_cmd(self, directory: Path, *, dev: bool = False, frozen: bool = True) -> list[str]:
        return ["dotnet", "restore"]

    def update_cmd(self, directory: Path, packages: list[str] | None = None) -> list[str]:
        # dotnet doesn't have a native "update all" — use dotnet outdated tool
        return ["dotnet", "restore"]

    def update_single_cmd(self, directory: Path, package: str, version: str | None = None) -> list[str]:
        if version:
            return ["dotnet", "add", "package", package, "--version", version]
        return ["dotnet", "add", "package", package]

    def snapshot_files(self, directory: Path) -> list[Path]:
        files: list[Path] = []
        for pattern in _GLOB_PATTERNS:
            for proj_file in directory.glob(pattern):
                if proj_file.is_file():
                    files.append(proj_file)
        lock = directory / "packages.lock.json"
        if lock.is_file():
            files.append(lock)
        return files

    def restore_cmd(self, directory: Path) -> list[str]:
        return ["dotnet", "restore"]

    def create_output_parser(self, scope: str) -> GenericParser:
        return GenericParser(scope, "dotnet")

    def fetch_latest_version(self, package: str) -> str | None:
        return None

    def check_deprecated(self, package: str, version: str) -> tuple[bool, str]:
        return False, ""
