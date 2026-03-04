"""
Version resolution for artifact publishing.

Resolution order:
  1. pyproject.toml → version
  2. setup.py → version
  3. git describe --tags
  4. git rev-parse --short HEAD
  5. Fallback: 0.0.0-dev
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def resolve_version(project_root: Path) -> tuple[str, str]:
    """Resolve the current project version.

    Returns:
        (version, source) — e.g. ("0.1.0", "pyproject.toml")
    """
    # 1. pyproject.toml
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("version") and "=" in stripped:
                    val = stripped.split("=", 1)[1].strip().strip("\"'")
                    if val and val != "0.0.0":
                        return (val, "pyproject.toml")
        except OSError:
            pass

    # 2. setup.py
    setup_py = project_root / "setup.py"
    if setup_py.exists():
        try:
            content = setup_py.read_text()
            m = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
            if m:
                return (m.group(1), "setup.py")
        except OSError:
            pass

    # 3. Git tag
    try:
        r = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=str(project_root),
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            tag = r.stdout.strip()
            # Strip leading 'v' if present
            version = tag.lstrip("v")
            return (version, f"git tag ({tag})")
    except (OSError, subprocess.TimeoutExpired):
        pass

    # 4. Git short hash
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(project_root),
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return (f"0.0.0-dev+{r.stdout.strip()}", "git hash")
    except (OSError, subprocess.TimeoutExpired):
        pass

    # 5. Fallback
    return ("0.0.0-dev", "fallback")


def bump_version(current: str, bump_type: str) -> str:
    """Bump a semver version string.

    Args:
        current: Current version (e.g. "0.1.0")
        bump_type: "patch", "minor", or "major"

    Returns:
        Bumped version string.
    """
    # Strip pre-release suffix for bumping
    base = current.split("-")[0].split("+")[0]
    parts = base.split(".")
    if len(parts) < 3:
        parts.extend(["0"] * (3 - len(parts)))

    try:
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    except (ValueError, IndexError):
        return current

    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return current


def get_last_tag(project_root: Path) -> str | None:
    """Get the most recent git tag, or None."""
    try:
        r = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=str(project_root),
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None
