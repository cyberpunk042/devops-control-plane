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
import sys
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
        # pip is special: use sys.executable -m pip since bare 'pip'
        # may not be in PATH inside a venv
        if pm_id == "pip":
            try:
                r = subprocess.run(
                    [sys.executable, "-m", "pip", "--version"],
                    capture_output=True, timeout=5,
                )
                cli_available = r.returncode == 0
            except Exception:
                cli_available = False
        else:
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

    # Collect CLI tool IDs from detected managers
    tool_ids = list(dict.fromkeys(
        m["cli"] for m in managers if m.get("cli") and not m.get("cli_available")
    ))
    from src.core.services.tool_requirements import check_required_tools
    missing = check_required_tools(tool_ids) if tool_ids else []

    return {
        "managers": managers,
        "total_managers": len(managers),
        "has_packages": len(managers) > 0,
        "missing_tools": missing,
    }


def package_status_enriched(project_root: Path) -> dict:
    """Package status with installed package lists.

    Extends ``package_status`` by calling ``package_list`` for each
    detected manager that has its CLI available.  The installed
    packages are appended under ``installed_packages``.

    Returns::

        {
            "managers": [...],
            "total_managers": int,
            "has_packages": bool,
            "installed_packages": {
                "pip": [{"name": "...", "version": "..."}, ...],
                ...
            },
            "total_installed": int,
        }
    """
    from src.core.services.package_actions import package_list as _pkg_list

    base = package_status(project_root)
    installed: dict[str, list[dict]] = {}
    total_installed = 0

    for mgr in base.get("managers", []):
        mgr_id = mgr.get("id", "")
        if not mgr.get("cli_available") or not mgr_id:
            continue
        try:
            result = _pkg_list(project_root, manager=mgr_id)
            if result.get("ok"):
                pkgs = result.get("packages", [])
                installed[mgr_id] = pkgs
                total_installed += len(pkgs)
        except Exception:
            logger.debug("package_list failed for %s", mgr_id, exc_info=True)

    base["installed_packages"] = installed
    base["total_installed"] = total_installed
    return base


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

