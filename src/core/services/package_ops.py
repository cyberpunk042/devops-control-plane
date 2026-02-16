"""
Package management operations — channel-independent service.

Provides dependency detection, outdated package checking, security
auditing, and install/update operations across all supported
package managers (pip, npm, go mod, cargo, etc.).

Maps stack names to the appropriate package manager commands.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Package manager definitions ─────────────────────────────────


_PACKAGE_MANAGERS: dict[str, dict] = {
    "pip": {
        "name": "pip",
        "stacks": ["python"],
        "files": ["requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile"],
        "lock_files": ["requirements.txt", "Pipfile.lock", "poetry.lock", "pdm.lock"],
        "cli": "pip",
    },
    "npm": {
        "name": "npm",
        "stacks": ["node", "typescript"],
        "files": ["package.json"],
        "lock_files": ["package-lock.json", "yarn.lock", "pnpm-lock.yaml"],
        "cli": "npm",
    },
    "go": {
        "name": "go modules",
        "stacks": ["go"],
        "files": ["go.mod"],
        "lock_files": ["go.sum"],
        "cli": "go",
    },
    "cargo": {
        "name": "cargo",
        "stacks": ["rust"],
        "files": ["Cargo.toml"],
        "lock_files": ["Cargo.lock"],
        "cli": "cargo",
    },
    "maven": {
        "name": "Maven",
        "stacks": ["java-maven", "java"],
        "files": ["pom.xml"],
        "lock_files": [],
        "cli": "mvn",
    },
    "gradle": {
        "name": "Gradle",
        "stacks": ["java-gradle"],
        "files": ["build.gradle", "build.gradle.kts"],
        "lock_files": ["gradle.lockfile"],
        "cli": "gradle",
    },
    "dotnet": {
        "name": ".NET (NuGet)",
        "stacks": ["dotnet"],
        "files": ["*.csproj", "*.fsproj"],
        "lock_files": ["packages.lock.json"],
        "cli": "dotnet",
    },
    "mix": {
        "name": "Mix (Hex)",
        "stacks": ["elixir"],
        "files": ["mix.exs"],
        "lock_files": ["mix.lock"],
        "cli": "mix",
    },
    "bundler": {
        "name": "Bundler",
        "stacks": ["ruby"],
        "files": ["Gemfile"],
        "lock_files": ["Gemfile.lock"],
        "cli": "bundle",
    },
}


def _run(
    args: list[str],
    cwd: Path,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    """Run a command and return the result."""
    return subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ═══════════════════════════════════════════════════════════════════
#  Detect
# ═══════════════════════════════════════════════════════════════════


def _detect_pm_for_dir(directory: Path) -> list[dict]:
    """Detect package managers in a directory."""
    found = []

    for pm_id, spec in _PACKAGE_MANAGERS.items():
        dep_files = []
        for pattern in spec["files"]:
            if "*" in pattern:
                dep_files.extend(str(p.relative_to(directory)) for p in directory.glob(pattern))
            elif (directory / pattern).is_file():
                dep_files.append(pattern)

        if not dep_files:
            continue

        lock_files = [f for f in spec["lock_files"] if (directory / f).is_file()]
        cli_available = shutil.which(spec["cli"]) is not None

        found.append({
            "id": pm_id,
            "name": spec["name"],
            "cli": spec["cli"],
            "cli_available": cli_available,
            "dependency_files": dep_files,
            "lock_files": lock_files,
            "has_lock": len(lock_files) > 0,
        })

    return found


def package_status(project_root: Path) -> dict:
    """Package management status: detected managers, dependency files.

    Returns:
        {
            "managers": [{id, name, cli, cli_available, dependency_files, lock_files}, ...],
            "total_managers": int,
            "has_packages": bool,
        }
    """
    managers = _detect_pm_for_dir(project_root)

    return {
        "managers": managers,
        "total_managers": len(managers),
        "has_packages": len(managers) > 0,
    }


def package_status_per_module(
    project_root: Path,
    modules: list[dict],
) -> dict:
    """Package status per module.

    Returns:
        {
            "modules": {
                module_name: {managers: [...], has_packages: bool},
                ...
            },
        }
    """
    result: dict[str, dict] = {}

    for mod in modules:
        name = mod.get("name", "")
        path = mod.get("path", "")
        if not name or not path:
            continue

        module_dir = project_root / path
        if not module_dir.is_dir():
            result[name] = {"managers": [], "has_packages": False}
            continue

        managers = _detect_pm_for_dir(module_dir)
        result[name] = {
            "managers": managers,
            "has_packages": len(managers) > 0,
        }

    return {"modules": result}


# ═══════════════════════════════════════════════════════════════════
# Re-exports — backward compatibility
# ═══════════════════════════════════════════════════════════════════

from src.core.services.package_actions import (  # noqa: F401, E402
    package_outdated,
    package_audit,
    package_list,
    package_install,
    package_update,
)

