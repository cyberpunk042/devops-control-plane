"""Dependency analyzer — check external package compatibility.

Checks whether a module's dependencies (from requirements.txt,
pyproject.toml, package.json, etc.) support the target version.

Queries package registries (PyPI, npm, etc.) for version constraints.
Caches responses to minimize network calls.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Cache TTL in seconds
_CACHE_TTL = 3600


@dataclass
class PackageCompatResult:
    """Compatibility result for a single package."""
    package: str
    installed_version: str = ""
    requires_python: str = ""         # e.g., ">=3.8"
    min_version: str = ""             # Parsed minimum: "3.8"
    compatible: bool = True
    unknown: bool = False             # Could not determine
    note: str = ""
    alternatives: list[dict] = field(default_factory=list)


@dataclass
class DependencyAnalysisResult:
    """Result of analyzing all dependencies."""
    module_dir: str
    language: str
    target_version: str
    manifest_file: str = ""

    packages: list[PackageCompatResult] = field(default_factory=list)

    @property
    def compatible_count(self) -> int:
        return sum(1 for p in self.packages if p.compatible and not p.unknown)

    @property
    def incompatible_count(self) -> int:
        return sum(1 for p in self.packages if not p.compatible and not p.unknown)

    @property
    def unknown_count(self) -> int:
        return sum(1 for p in self.packages if p.unknown)

    @property
    def all_compatible(self) -> bool:
        return self.incompatible_count == 0

    @property
    def incompatible_packages(self) -> list[PackageCompatResult]:
        return [p for p in self.packages if not p.compatible and not p.unknown]

    @property
    def dependency_floor(self) -> str:
        """Highest minimum Python version among all deps."""
        highest = ""
        for p in self.packages:
            if p.min_version and not p.unknown:
                if not highest or _compare_versions(p.min_version, highest) > 0:
                    highest = p.min_version
        return highest

    def summary(self) -> dict:
        return {
            "total": len(self.packages),
            "compatible": self.compatible_count,
            "incompatible": self.incompatible_count,
            "unknown": self.unknown_count,
            "dependency_floor": self.dependency_floor,
            "all_compatible": self.all_compatible,
        }


class DependencyAnalyzer:
    """Analyze external dependency compatibility."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, Any]] = {}

    def analyze(
        self,
        module_dir: Path,
        language: str,
        target_version: str,
    ) -> DependencyAnalysisResult:
        """Analyze all dependencies for target version compatibility."""
        result = DependencyAnalysisResult(
            module_dir=str(module_dir),
            language=language,
            target_version=target_version,
        )

        if language == "python":
            return self._analyze_python(module_dir, target_version, result)
        # Other languages: placeholder
        return result

    def _analyze_python(
        self,
        module_dir: Path,
        target_version: str,
        result: DependencyAnalysisResult,
    ) -> DependencyAnalysisResult:
        """Analyze Python dependencies from requirements.txt or pyproject.toml."""
        # Find manifest
        deps: list[str] = []

        req_file = module_dir / "requirements.txt"
        pyproject = module_dir / "pyproject.toml"

        if req_file.is_file():
            result.manifest_file = str(req_file)
            deps = self._parse_requirements_txt(req_file)
        elif pyproject.is_file():
            result.manifest_file = str(pyproject)
            deps = self._parse_pyproject_deps(pyproject)

        if not deps:
            # Try parent directory requirements
            parent_req = module_dir.parent / "requirements.txt"
            if parent_req.is_file():
                result.manifest_file = str(parent_req)
                deps = self._parse_requirements_txt(parent_req)

        # Check each dependency
        for dep_name in deps:
            pkg_result = self._check_python_package(dep_name, target_version)
            result.packages.append(pkg_result)

        return result

    def _parse_requirements_txt(self, path: Path) -> list[str]:
        """Parse package names from requirements.txt."""
        deps = []
        try:
            for line in path.read_text(encoding="utf-8").split("\n"):
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                # Extract package name (before version specifier)
                match = re.match(r"^([a-zA-Z0-9_-]+)", line)
                if match:
                    deps.append(match.group(1).lower())
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", path, exc)
        return deps

    def _parse_pyproject_deps(self, path: Path) -> list[str]:
        """Parse dependencies from pyproject.toml."""
        deps = []
        try:
            content = path.read_text(encoding="utf-8")
            # Simple parsing — look for dependencies list
            in_deps = False
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("dependencies") and "=" in stripped:
                    in_deps = True
                    continue
                if in_deps:
                    if stripped.startswith("]"):
                        in_deps = False
                        continue
                    # Extract package name from "package>=1.0"
                    match = re.match(r'"([a-zA-Z0-9_-]+)', stripped)
                    if match:
                        deps.append(match.group(1).lower())
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", path, exc)
        return deps

    def _check_python_package(
        self,
        package: str,
        target_version: str,
    ) -> PackageCompatResult:
        """Check a single Python package's compatibility via PyPI."""
        result = PackageCompatResult(package=package)

        # Check cache
        cache_key = f"pypi:{package}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            pypi_data = cached
        else:
            pypi_data = self._query_pypi(package)
            if pypi_data:
                self._set_cached(cache_key, pypi_data)

        if not pypi_data:
            result.unknown = True
            result.note = "Could not query PyPI"
            return result

        # Extract requires-python from latest version
        info = pypi_data.get("info", {})
        requires_python = info.get("requires_python", "")
        version = info.get("version", "")

        result.installed_version = version
        result.requires_python = requires_python or ""

        if not requires_python:
            # No constraint — compatible with all versions
            result.compatible = True
            result.note = "No requires-python specified"
            return result

        # Parse minimum version from requires-python
        min_ver = self._parse_min_version(requires_python)
        result.min_version = min_ver

        # Check if target satisfies the constraint
        if min_ver:
            result.compatible = _compare_versions(target_version, min_ver) >= 0
            if not result.compatible:
                result.note = f"Requires Python {requires_python}, target is {target_version}"
        else:
            result.compatible = True
            result.note = f"Could not parse requires-python: {requires_python}"

        return result

    def _query_pypi(self, package: str) -> dict | None:
        """Query PyPI JSON API for package metadata."""
        try:
            import urllib.request
            url = f"https://pypi.org/pypi/{package}/json"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return json.loads(resp.read())
        except Exception as exc:
            logger.debug("PyPI query failed for %s: %s", package, exc)
        return None

    def _parse_min_version(self, requires_python: str) -> str:
        """Extract minimum Python version from requires-python string.

        Examples:
            ">=3.8" → "3.8"
            ">=3.8,<4" → "3.8"
            "~=3.8" → "3.8"
            ">=3.7.1" → "3.7"
        """
        # Find the >= or ~= constraint
        match = re.search(r">=?\s*(\d+\.\d+)", requires_python)
        if match:
            return match.group(1)
        match = re.search(r"~=\s*(\d+\.\d+)", requires_python)
        if match:
            return match.group(1)
        return ""

    # ── Cache ────────────────────────────────────────────────────

    def _get_cached(self, key: str) -> Any | None:
        """Get a cached value if still valid."""
        entry = self._cache.get(key)
        if entry and (time.time() - entry[0]) < _CACHE_TTL:
            return entry[1]
        return None

    def _set_cached(self, key: str, value: Any) -> None:
        """Cache a value."""
        self._cache[key] = (time.time(), value)


def _compare_versions(a: str, b: str) -> int:
    """Compare two dotted version strings. Returns -1, 0, or 1."""
    try:
        pa = tuple(int(x) for x in a.split("."))
        pb = tuple(int(x) for x in b.split("."))
        if pa < pb:
            return -1
        if pa > pb:
            return 1
        return 0
    except (ValueError, TypeError):
        return 0
