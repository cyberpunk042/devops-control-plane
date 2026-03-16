"""
pip ecosystem adapter — Python package management.

Handles 3 manifest formats:
  - ``requirements.txt`` — line-based (most common)
  - ``pyproject.toml`` — TOML / PEP 621 (modern)
  - ``Pipfile`` — TOML / Pipenv

Lock file detection: ``Pipfile.lock``, ``poetry.lock``, ``pdm.lock``, ``uv.lock``.
For ``requirements.txt`` with pinned versions (``==``), the file IS the lock.

All commands use ``sys.executable -m pip`` to ensure the correct venv.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from pathlib import Path

from ..ecosystem import EcosystemAdapter
from ..models import DeclaredDep, ManifestInfo, ParsedManifest
from ..parsers.pip_parser import PipParser

logger = logging.getLogger(__name__)

# Manifest files in detection priority order
_MANIFEST_FILES = ("requirements.txt", "pyproject.toml", "Pipfile")

# Lock files to check
_LOCK_FILES = ("Pipfile.lock", "poetry.lock", "pdm.lock", "uv.lock")

# Regex for parsing requirement lines: name + optional version spec
_RE_REQ = re.compile(r"^([a-zA-Z0-9_.-]+)\s*(\[.*?\])?\s*([<>=!~]+.+)?$")

# Regex for PEP 508 dep strings: "flask>=3.0" or "click[extra]>=8.0;python_version>='3.8'"
_RE_PEP508 = re.compile(r"^([a-zA-Z0-9_.-]+)\s*(\[.*?\])?\s*([<>=!~,\s\d.*]+)?")


def _pip_cmd(*args: str) -> list[str]:
    """Build pip command using the current interpreter."""
    return [sys.executable, "-m", "pip", *args]


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


class PipAdapter(EcosystemAdapter):
    """Ecosystem adapter for Python (pip)."""

    @property
    def id(self) -> str:
        return "pip"

    @property
    def name(self) -> str:
        return "Python (pip)"

    @property
    def cli(self) -> str:
        return "pip"

    # ── Detection ─────────────────────────────────────────────

    def detect(self, directory: Path) -> list[ManifestInfo]:
        found: list[ManifestInfo] = []
        lock = self._find_lock(directory)

        for filename in _MANIFEST_FILES:
            path = directory / filename
            if path.is_file():
                found.append(ManifestInfo(
                    ecosystem="pip",
                    manifest_file=filename,
                    manifest_path=".",  # Scanner normalizes this
                    lock_file=lock,
                    cli="pip",
                    cli_available=self.is_available(),
                    mtime=path.stat().st_mtime,
                ))

        return found

    def is_available(self) -> bool:
        """pip uses sys.executable -m pip (not bare 'pip' in PATH)."""
        try:
            r = subprocess.run(
                _pip_cmd("--version"),
                capture_output=True, timeout=5,
            )
            return r.returncode == 0
        except Exception:
            return False

    # ── Parsing ───────────────────────────────────────────────

    def parse_manifest(
        self, manifest: Path, lock_file: Path | None,
    ) -> ParsedManifest:
        filename = manifest.name.lower()
        source_path = "."  # Scanner fills the real relative path

        if filename == "requirements.txt":
            deps, dev_deps = self._parse_requirements_txt(manifest, source_path)
        elif filename == "pyproject.toml":
            deps, dev_deps = self._parse_pyproject_toml(manifest, source_path)
        elif filename == "pipfile":
            deps, dev_deps = self._parse_pipfile(manifest, source_path)
        else:
            deps, dev_deps = [], []

        info = ManifestInfo(
            ecosystem="pip",
            manifest_file=manifest.name,
            manifest_path=source_path,
            lock_file=lock_file.name if lock_file else None,
            cli="pip",
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
        # Prefer requirements.txt if it exists
        if (directory / "requirements.txt").is_file():
            return _pip_cmd("install", "-r", "requirements.txt")

        # pyproject.toml
        if (directory / "pyproject.toml").is_file():
            if dev:
                return _pip_cmd("install", "-e", ".[dev]")
            return _pip_cmd("install", "-e", ".")

        # Pipfile — use pipenv if available, otherwise pip
        if (directory / "Pipfile").is_file():
            return _pip_cmd("install")

        return _pip_cmd("install")

    def update_cmd(
        self, directory: Path, packages: list[str] | None = None,
    ) -> list[str]:
        if packages:
            return _pip_cmd("install", "--upgrade", *packages)

        # Update all from manifest
        if (directory / "requirements.txt").is_file():
            return _pip_cmd("install", "--upgrade", "-r", "requirements.txt")
        if (directory / "pyproject.toml").is_file():
            return _pip_cmd("install", "--upgrade", "-e", ".")
        return _pip_cmd("install", "--upgrade")

    def update_single_cmd(
        self, directory: Path, package: str, version: str | None = None,
    ) -> list[str]:
        if version:
            return _pip_cmd("install", f"{package}=={version}")
        return _pip_cmd("install", "--upgrade", package)

    # ── Rollback ──────────────────────────────────────────────

    def snapshot_files(self, directory: Path) -> list[Path]:
        files: list[Path] = []
        for name in (*_MANIFEST_FILES, *_LOCK_FILES):
            path = directory / name
            if path.is_file():
                files.append(path)
        return files

    def restore_cmd(self, directory: Path) -> list[str]:
        return self.install_cmd(directory)

    # ── Output parser ─────────────────────────────────────────

    def create_output_parser(self, scope: str) -> PipParser:
        return PipParser(scope)

    # ── Version intelligence (stubs — Phase 3) ────────────────

    def fetch_latest_version(self, package: str) -> str | None:
        return None

    def check_deprecated(
        self, package: str, version: str,
    ) -> tuple[bool, str]:
        return False, ""

    # ── Internal: lock file detection ─────────────────────────

    @staticmethod
    def _find_lock(directory: Path) -> str | None:
        for name in _LOCK_FILES:
            if (directory / name).is_file():
                return name
        return None

    # ── Internal: requirements.txt parser ─────────────────────

    @staticmethod
    def _parse_requirements_txt(
        path: Path, source_path: str,
    ) -> tuple[list[DeclaredDep], list[DeclaredDep]]:
        deps: list[DeclaredDep] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                # Skip empty, comments, options, recursive includes, editables
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                # Strip environment markers ("; python_version >= '3.8'")
                if ";" in line:
                    line = line.split(";")[0].strip()
                # Parse name + version spec
                m = _RE_REQ.match(line)
                if m:
                    name = m.group(1)
                    version_spec = (m.group(3) or "").strip()
                    pinned = ""
                    if version_spec.startswith("=="):
                        pinned = version_spec[2:].strip()
                    deps.append(DeclaredDep(
                        name=name,
                        version_spec=version_spec,
                        pinned_version=pinned,
                        group="main",
                        source_file="requirements.txt",
                        source_path=source_path,
                    ))
        except (OSError, UnicodeDecodeError):
            logger.debug("Failed to parse %s", path, exc_info=True)
        return deps, []

    # ── Internal: pyproject.toml parser ───────────────────────

    @staticmethod
    def _parse_pyproject_toml(
        path: Path, source_path: str,
    ) -> tuple[list[DeclaredDep], list[DeclaredDep]]:
        data = _load_toml(path)
        if not data:
            return [], []

        deps: list[DeclaredDep] = []
        dev_deps: list[DeclaredDep] = []

        def _parse_dep_str(dep_str: str, group: str) -> DeclaredDep | None:
            m = _RE_PEP508.match(dep_str.strip())
            if not m:
                return None
            name = m.group(1)
            version_spec = (m.group(3) or "").strip().rstrip(",")
            pinned = ""
            if version_spec.startswith("=="):
                pinned = version_spec[2:].strip()
            return DeclaredDep(
                name=name,
                version_spec=version_spec,
                pinned_version=pinned,
                group=group,
                source_file="pyproject.toml",
                source_path=source_path,
            )

        # [project.dependencies]
        for dep_str in data.get("project", {}).get("dependencies", []):
            dep = _parse_dep_str(dep_str, "main")
            if dep:
                deps.append(dep)

        # [project.optional-dependencies.*]
        for group_name, group_deps in (
            data.get("project", {}).get("optional-dependencies", {}).items()
        ):
            target = dev_deps if group_name in ("dev", "test", "testing") else deps
            for dep_str in group_deps:
                dep = _parse_dep_str(dep_str, group_name)
                if dep:
                    target.append(dep)

        # Poetry: [tool.poetry.dependencies]
        poetry = data.get("tool", {}).get("poetry", {})
        for name, spec in poetry.get("dependencies", {}).items():
            if name.lower() == "python":
                continue
            ver = spec if isinstance(spec, str) else ""
            deps.append(DeclaredDep(
                name=name,
                version_spec=ver,
                pinned_version="",
                group="main",
                source_file="pyproject.toml",
                source_path=source_path,
            ))
        for name, spec in poetry.get("dev-dependencies", {}).items():
            ver = spec if isinstance(spec, str) else ""
            dev_deps.append(DeclaredDep(
                name=name,
                version_spec=ver,
                pinned_version="",
                group="dev",
                source_file="pyproject.toml",
                source_path=source_path,
            ))

        return deps, dev_deps

    # ── Internal: Pipfile parser ──────────────────────────────

    @staticmethod
    def _parse_pipfile(
        path: Path, source_path: str,
    ) -> tuple[list[DeclaredDep], list[DeclaredDep]]:
        data = _load_toml(path)
        if not data:
            return [], []

        deps: list[DeclaredDep] = []
        dev_deps: list[DeclaredDep] = []

        for name, spec in data.get("packages", {}).items():
            ver = spec if isinstance(spec, str) else ""
            if ver == "*":
                ver = ""
            deps.append(DeclaredDep(
                name=name,
                version_spec=ver,
                pinned_version="",
                group="main",
                source_file="Pipfile",
                source_path=source_path,
            ))

        for name, spec in data.get("dev-packages", {}).items():
            ver = spec if isinstance(spec, str) else ""
            if ver == "*":
                ver = ""
            dev_deps.append(DeclaredDep(
                name=name,
                version_spec=ver,
                pinned_version="",
                group="dev",
                source_file="Pipfile",
                source_path=source_path,
            ))

        return deps, dev_deps
