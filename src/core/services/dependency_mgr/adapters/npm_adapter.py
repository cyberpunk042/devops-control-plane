"""
npm ecosystem adapter — Node.js package management.

Handles one manifest format: ``package.json`` (JSON).
Detects sub-variants by lock file: npm (default), yarn, pnpm.

Lock file detection:
  - ``package-lock.json`` → npm cli
  - ``yarn.lock`` → yarn cli
  - ``pnpm-lock.yaml`` → pnpm cli
  - None → npm cli (fresh resolve)

Commands adapt to the detected sub-variant automatically.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from ..ecosystem import EcosystemAdapter
from ..models import DeclaredDep, ManifestInfo, ParsedManifest
from ..parsers.npm_parser import NpmParser

logger = logging.getLogger(__name__)

# Lock files in detection priority order
_LOCK_FILES = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml")

# Lock file → CLI mapping
_LOCK_TO_CLI = {
    "package-lock.json": "npm",
    "yarn.lock": "yarn",
    "pnpm-lock.yaml": "pnpm",
}


class NpmAdapter(EcosystemAdapter):
    """Ecosystem adapter for Node.js (npm/yarn/pnpm)."""

    @property
    def id(self) -> str:
        return "npm"

    @property
    def name(self) -> str:
        return "Node (npm)"

    @property
    def cli(self) -> str:
        return "npm"

    # ── Detection ─────────────────────────────────────────────

    def detect(self, directory: Path) -> list[ManifestInfo]:
        pkg_json = directory / "package.json"
        if not pkg_json.is_file():
            return []

        lock = self._find_lock(directory)

        return [ManifestInfo(
            ecosystem="npm",
            manifest_file="package.json",
            manifest_path=".",  # Scanner normalizes this
            lock_file=lock,
            cli=self._resolve_cli(lock),
            cli_available=self._check_cli(lock),
            mtime=pkg_json.stat().st_mtime,
        )]

    def is_available(self) -> bool:
        return shutil.which("npm") is not None

    # ── Parsing ───────────────────────────────────────────────

    def parse_manifest(
        self, manifest: Path, lock_file: Path | None,
    ) -> ParsedManifest:
        deps: list[DeclaredDep] = []
        dev_deps: list[DeclaredDep] = []
        source_path = "."

        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}

        # dependencies → main
        for name, version_spec in data.get("dependencies", {}).items():
            deps.append(self._make_dep(name, version_spec, "main", manifest.name, source_path))

        # peerDependencies → peer
        for name, version_spec in data.get("peerDependencies", {}).items():
            deps.append(self._make_dep(name, version_spec, "peer", manifest.name, source_path))

        # optionalDependencies → optional
        for name, version_spec in data.get("optionalDependencies", {}).items():
            deps.append(self._make_dep(name, version_spec, "optional", manifest.name, source_path))

        # devDependencies → dev
        for name, version_spec in data.get("devDependencies", {}).items():
            dev_deps.append(self._make_dep(name, version_spec, "dev", manifest.name, source_path))

        info = ManifestInfo(
            ecosystem="npm",
            manifest_file=manifest.name,
            manifest_path=source_path,
            lock_file=lock_file.name if lock_file else None,
            cli=self._resolve_cli(lock_file.name if lock_file else None),
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
        lock = self._find_lock(directory)
        cli = self._resolve_cli(lock)

        if cli == "yarn":
            if frozen and lock:
                return ["yarn", "install", "--frozen-lockfile"]
            return ["yarn", "install"]

        if cli == "pnpm":
            if frozen and lock:
                return ["pnpm", "install", "--frozen-lockfile"]
            return ["pnpm", "install"]

        # npm (default)
        if frozen and lock:
            return ["npm", "ci"]
        return ["npm", "install"]

    def update_cmd(
        self, directory: Path, packages: list[str] | None = None,
    ) -> list[str]:
        lock = self._find_lock(directory)
        cli = self._resolve_cli(lock)

        if packages:
            if cli == "yarn":
                return ["yarn", "upgrade", *packages]
            if cli == "pnpm":
                return ["pnpm", "update", *packages]
            return ["npm", "update", *packages]

        # Update all
        if cli == "yarn":
            return ["yarn", "upgrade"]
        if cli == "pnpm":
            return ["pnpm", "update"]
        return ["npm", "update"]

    def update_single_cmd(
        self, directory: Path, package: str, version: str | None = None,
    ) -> list[str]:
        lock = self._find_lock(directory)
        cli = self._resolve_cli(lock)
        target = f"{package}@{version}" if version else f"{package}@latest"

        if cli == "yarn":
            return ["yarn", "add", target]
        if cli == "pnpm":
            return ["pnpm", "add", target]
        return ["npm", "install", target]

    # ── Rollback ──────────────────────────────────────────────

    def snapshot_files(self, directory: Path) -> list[Path]:
        files: list[Path] = []
        pkg = directory / "package.json"
        if pkg.is_file():
            files.append(pkg)
        for name in _LOCK_FILES:
            path = directory / name
            if path.is_file():
                files.append(path)
        return files

    def restore_cmd(self, directory: Path) -> list[str]:
        return self.install_cmd(directory, frozen=True)

    # ── Output parser ─────────────────────────────────────────

    def create_output_parser(self, scope: str) -> NpmParser:
        return NpmParser(scope)

    # ── Version intelligence ─────────────────────────────────

    def fetch_latest_version(self, package: str) -> str | None:
        """Query npm registry for the latest version."""
        try:
            import urllib.request
            import json as _json
            # Scoped packages: @scope/name → URL-encode the /
            url = f"https://registry.npmjs.org/{package.replace('/', '%2F')}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read())
                return data.get("dist-tags", {}).get("latest")
        except Exception:
            return None

    def check_deprecated(
        self, package: str, version: str,
    ) -> tuple[bool, str]:
        """Check npm registry for deprecation message."""
        try:
            import urllib.request
            import json as _json
            url = f"https://registry.npmjs.org/{package.replace('/', '%2F')}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read())
                # Check specific version
                ver_data = data.get("versions", {}).get(version, {})
                dep_msg = ver_data.get("deprecated", "")
                if dep_msg:
                    return True, dep_msg
                # Check latest version deprecation (whole package deprecated)
                latest_ver = data.get("dist-tags", {}).get("latest", "")
                if latest_ver:
                    latest_data = data.get("versions", {}).get(latest_ver, {})
                    dep_msg = latest_data.get("deprecated", "")
                    if dep_msg:
                        return True, dep_msg
        except Exception:
            pass
        return False, ""

    # ── Internal helpers ──────────────────────────────────────

    @staticmethod
    def _find_lock(directory: Path) -> str | None:
        for name in _LOCK_FILES:
            if (directory / name).is_file():
                return name
        return None

    @staticmethod
    def _resolve_cli(lock_file: str | None) -> str:
        if lock_file:
            return _LOCK_TO_CLI.get(lock_file, "npm")
        return "npm"

    @staticmethod
    def _check_cli(lock_file: str | None) -> bool:
        cli = NpmAdapter._resolve_cli(lock_file)
        return shutil.which(cli) is not None

    @staticmethod
    def _make_dep(
        name: str, version_spec: str, group: str,
        source_file: str, source_path: str,
    ) -> DeclaredDep:
        # Pinned = exact version (no ^, ~, >=, etc.)
        pinned = ""
        stripped = version_spec.strip()
        if stripped and stripped[0].isdigit():
            pinned = stripped
        return DeclaredDep(
            name=name,
            version_spec=version_spec,
            pinned_version=pinned,
            group=group,
            source_file=source_file,
            source_path=source_path,
        )
