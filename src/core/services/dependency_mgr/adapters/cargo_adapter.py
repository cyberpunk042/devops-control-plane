"""
Cargo ecosystem adapter — Rust package management.

Manifest: ``Cargo.toml`` (TOML).
Lock: ``Cargo.lock``.
CLI: ``cargo``.

Three dependency sections: ``[dependencies]``, ``[dev-dependencies]``,
``[build-dependencies]``.

Uses TOML parsing with ``tomllib``/``tomli`` fallback, same as pip adapter.
Falls back to regex-based section parsing if TOML library unavailable.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ..ecosystem import EcosystemAdapter
from ..models import DeclaredDep, ManifestInfo, ParsedManifest
from ..parsers.cargo_parser import CargoParser

logger = logging.getLogger(__name__)


def _load_toml(path: Path) -> dict:
    """Load a TOML file.  Returns empty dict on failure."""
    try:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


class CargoAdapter(EcosystemAdapter):
    """Ecosystem adapter for Rust (Cargo)."""

    @property
    def id(self) -> str:
        return "cargo"

    @property
    def name(self) -> str:
        return "Rust (cargo)"

    @property
    def cli(self) -> str:
        return "cargo"

    # ── Detection ─────────────────────────────────────────────

    def detect(self, directory: Path) -> list[ManifestInfo]:
        cargo_toml = directory / "Cargo.toml"
        if not cargo_toml.is_file():
            return []

        lock = "Cargo.lock" if (directory / "Cargo.lock").is_file() else None

        return [ManifestInfo(
            ecosystem="cargo",
            manifest_file="Cargo.toml",
            manifest_path=".",
            lock_file=lock,
            cli="cargo",
            cli_available=self.is_available(),
            mtime=cargo_toml.stat().st_mtime,
        )]

    # ── Parsing ───────────────────────────────────────────────

    def parse_manifest(
        self, manifest: Path, lock_file: Path | None,
    ) -> ParsedManifest:
        data = _load_toml(manifest)
        source_path = "."

        deps: list[DeclaredDep] = []
        dev_deps: list[DeclaredDep] = []

        if data:
            deps = self._parse_section(data, "dependencies", "main", manifest.name, source_path)
            dev_deps = self._parse_section(data, "dev-dependencies", "dev", manifest.name, source_path)
            build_deps = self._parse_section(data, "build-dependencies", "build", manifest.name, source_path)
            deps.extend(build_deps)
        else:
            # Fallback: regex-based parsing
            deps, dev_deps = self._parse_regex(manifest, source_path)

        info = ManifestInfo(
            ecosystem="cargo",
            manifest_file=manifest.name,
            manifest_path=source_path,
            lock_file=lock_file.name if lock_file else None,
            cli="cargo",
            cli_available=True,
            mtime=manifest.stat().st_mtime if manifest.is_file() else 0.0,
        )

        return ParsedManifest(
            info=info,
            dependencies=tuple(deps),
            dev_dependencies=tuple(dev_deps),
            total=len(deps) + len(dev_deps),
        )

    # ── Commands ──────────────────────────────────────────────

    def install_cmd(
        self, directory: Path, *, dev: bool = False, frozen: bool = True,
    ) -> list[str]:
        return ["cargo", "fetch"]

    def update_cmd(
        self, directory: Path, packages: list[str] | None = None,
    ) -> list[str]:
        if packages:
            cmd = ["cargo", "update"]
            for p in packages:
                cmd.extend(["-p", p])
            return cmd
        return ["cargo", "update"]

    def update_single_cmd(
        self, directory: Path, package: str, version: str | None = None,
    ) -> list[str]:
        if version:
            return ["cargo", "update", "-p", package, "--precise", version]
        return ["cargo", "update", "-p", package]

    # ── Rollback ──────────────────────────────────────────────

    def snapshot_files(self, directory: Path) -> list[Path]:
        files: list[Path] = []
        for name in ("Cargo.toml", "Cargo.lock"):
            path = directory / name
            if path.is_file():
                files.append(path)
        return files

    def restore_cmd(self, directory: Path) -> list[str]:
        return ["cargo", "fetch"]

    # ── Output parser ─────────────────────────────────────────

    def create_output_parser(self, scope: str) -> CargoParser:
        return CargoParser(scope)

    # ── Version intelligence (stubs) ──────────────────────────

    def fetch_latest_version(self, package: str) -> str | None:
        return None

    def check_deprecated(self, package: str, version: str) -> tuple[bool, str]:
        return False, ""

    # ── Internal: TOML section parser ─────────────────────────

    @staticmethod
    def _parse_section(
        data: dict, section: str, group: str,
        source_file: str, source_path: str,
    ) -> list[DeclaredDep]:
        deps: list[DeclaredDep] = []
        section_data = data.get(section, {})

        for name, spec in section_data.items():
            if isinstance(spec, str):
                # Simple: serde = "1.0"
                version_spec = spec
            elif isinstance(spec, dict):
                # Complex: serde = { version = "1.0", features = [...] }
                version_spec = spec.get("version", "")
            else:
                version_spec = ""

            pinned = ""
            stripped = version_spec.strip()
            if stripped and stripped[0].isdigit():
                # Exact or starts with digit — treat as pinned
                pinned = stripped

            deps.append(DeclaredDep(
                name=name,
                version_spec=version_spec,
                pinned_version=pinned,
                group=group,
                source_file=source_file,
                source_path=source_path,
            ))

        return deps

    # ── Internal: regex fallback parser ───────────────────────

    @staticmethod
    def _parse_regex(
        path: Path, source_path: str,
    ) -> tuple[list[DeclaredDep], list[DeclaredDep]]:
        """Fallback when TOML library is unavailable."""
        deps: list[DeclaredDep] = []
        dev_deps: list[DeclaredDep] = []

        try:
            content = path.read_text(encoding="utf-8")
            section = ""
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("["):
                    section = stripped.strip("[]").strip()
                    continue
                if section not in ("dependencies", "dev-dependencies", "build-dependencies"):
                    continue
                # name = "version"
                m = re.match(r'^([a-zA-Z0-9_-]+)\s*=\s*"([^"]*)"', stripped)
                if m:
                    name, ver = m.group(1), m.group(2)
                elif "=" in stripped:
                    name = stripped.split("=")[0].strip()
                    ver_m = re.search(r'version\s*=\s*"([^"]*)"', stripped)
                    ver = ver_m.group(1) if ver_m else ""
                else:
                    continue

                if not name or name.startswith("#"):
                    continue

                dep = DeclaredDep(
                    name=name,
                    version_spec=ver,
                    pinned_version=ver if ver and ver[0].isdigit() else "",
                    group="dev" if section == "dev-dependencies" else ("build" if section == "build-dependencies" else "main"),
                    source_file=path.name,
                    source_path=source_path,
                )
                if section == "dev-dependencies":
                    dev_deps.append(dep)
                else:
                    deps.append(dep)
        except (OSError, UnicodeDecodeError):
            pass

        return deps, dev_deps
