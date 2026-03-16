"""
Go modules ecosystem adapter.

Manifest: ``go.mod`` (line-based).
Lock: ``go.sum``.
CLI: ``go``.

Commands: ``go mod download``, ``go get -u ./...``, ``go get -u <module>``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ..ecosystem import EcosystemAdapter
from ..models import DeclaredDep, ManifestInfo, ParsedManifest
from ..parsers.go_parser import GoParser

logger = logging.getLogger(__name__)

_RE_REQUIRE = re.compile(r"^\s*(\S+)\s+(v\S+)")


class GoAdapter(EcosystemAdapter):
    """Ecosystem adapter for Go modules."""

    @property
    def id(self) -> str:
        return "go"

    @property
    def name(self) -> str:
        return "Go"

    @property
    def cli(self) -> str:
        return "go"

    # ── Detection ─────────────────────────────────────────────

    def detect(self, directory: Path) -> list[ManifestInfo]:
        go_mod = directory / "go.mod"
        if not go_mod.is_file():
            return []

        lock = "go.sum" if (directory / "go.sum").is_file() else None

        return [ManifestInfo(
            ecosystem="go",
            manifest_file="go.mod",
            manifest_path=".",
            lock_file=lock,
            cli="go",
            cli_available=self.is_available(),
            mtime=go_mod.stat().st_mtime,
        )]

    # ── Parsing ───────────────────────────────────────────────

    def parse_manifest(
        self, manifest: Path, lock_file: Path | None,
    ) -> ParsedManifest:
        deps: list[DeclaredDep] = []
        source_path = "."

        try:
            content = manifest.read_text(encoding="utf-8")
            in_require = False
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("require ("):
                    in_require = True
                    continue
                if stripped == ")":
                    in_require = False
                    continue
                if in_require or stripped.startswith("require "):
                    text = stripped.replace("require ", "").strip()
                    # Skip indirect dependencies
                    if "// indirect" in text:
                        continue
                    m = _RE_REQUIRE.match(text)
                    if m:
                        module_path = m.group(1)
                        version = m.group(2)
                        deps.append(DeclaredDep(
                            name=module_path,
                            version_spec=version,
                            pinned_version=version.lstrip("v"),
                            group="main",
                            source_file="go.mod",
                            source_path=source_path,
                        ))
        except (OSError, UnicodeDecodeError):
            logger.debug("Failed to parse %s", manifest, exc_info=True)

        info = ManifestInfo(
            ecosystem="go",
            manifest_file=manifest.name,
            manifest_path=source_path,
            lock_file=lock_file.name if lock_file else None,
            cli="go",
            cli_available=True,
            mtime=manifest.stat().st_mtime if manifest.is_file() else 0.0,
        )

        return ParsedManifest(
            info=info,
            dependencies=tuple(deps),
            dev_dependencies=(),
            total=len(deps),
        )

    # ── Commands ──────────────────────────────────────────────

    def install_cmd(
        self, directory: Path, *, dev: bool = False, frozen: bool = True,
    ) -> list[str]:
        return ["go", "mod", "download"]

    def update_cmd(
        self, directory: Path, packages: list[str] | None = None,
    ) -> list[str]:
        if packages:
            return ["go", "get", "-u"] + packages
        return ["go", "get", "-u", "./..."]

    def update_single_cmd(
        self, directory: Path, package: str, version: str | None = None,
    ) -> list[str]:
        if version:
            return ["go", "get", f"{package}@v{version}" if not version.startswith("v") else f"{package}@{version}"]
        return ["go", "get", "-u", package]

    # ── Rollback ──────────────────────────────────────────────

    def snapshot_files(self, directory: Path) -> list[Path]:
        files: list[Path] = []
        for name in ("go.mod", "go.sum"):
            path = directory / name
            if path.is_file():
                files.append(path)
        return files

    def restore_cmd(self, directory: Path) -> list[str]:
        return ["go", "mod", "download"]

    # ── Output parser ─────────────────────────────────────────

    def create_output_parser(self, scope: str) -> GoParser:
        return GoParser(scope)

    # ── Version intelligence (stubs) ──────────────────────────

    def fetch_latest_version(self, package: str) -> str | None:
        return None

    def check_deprecated(self, package: str, version: str) -> tuple[bool, str]:
        return False, ""
