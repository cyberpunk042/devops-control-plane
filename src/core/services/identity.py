"""
Identity resolution.

Reads project.yml owners and matches against the local git identity.
No external dependencies beyond standard lib + PyYAML.
No network calls. Used by web, CLI, and TUI layers.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def get_git_user_name(project_root: Path) -> str | None:
    """Read ``git config user.name`` for the repo at *project_root*.

    Returns the stripped display name, or ``None`` if git is not
    configured or not installed.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), "config", "user.name"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def get_project_owners(project_root: Path) -> list[dict]:
    """Read the ``owners`` list from ``project.yml``.

    Each entry is a dict with at least ``name`` (str).
    Returns ``[]`` if the field is absent, empty, or unparseable.
    """
    yml_path = project_root / "project.yml"
    if not yml_path.is_file():
        return []
    try:
        with open(yml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return []
        owners_raw = data.get("owners")
        if not owners_raw or not isinstance(owners_raw, list):
            return []
        # Normalise: accept both dicts and bare strings
        owners: list[dict] = []
        for entry in owners_raw:
            if isinstance(entry, dict) and entry.get("name"):
                owners.append(entry)
            elif isinstance(entry, str) and entry.strip():
                owners.append({"name": entry.strip()})
        return owners
    except (yaml.YAMLError, OSError) as exc:
        logger.debug("Failed to read owners from project.yml: %s", exc)
        return []


def is_owner(project_root: Path) -> bool:
    """Check if the current git user is a project owner.

    Comparison is case-insensitive and stripped.
    """
    git_user = get_git_user_name(project_root)
    if not git_user:
        return False
    owners = get_project_owners(project_root)
    if not owners:
        return False
    git_lower = git_user.lower().strip()
    return any(
        o.get("name", "").lower().strip() == git_lower
        for o in owners
    )


def get_dev_mode_status(project_root: Path) -> dict:
    """Return full dev-mode status for the frontend.

    Returns::

        {
            "dev_mode": bool,        # final resolved state (owner match)
            "is_owner": bool,        # identity match result
            "git_user": str | None,  # current git user.name
            "owners": list[str],     # configured owner names
        }
    """
    git_user = get_git_user_name(project_root)
    owners = get_project_owners(project_root)
    owner_names = [o.get("name", "") for o in owners]

    owner_match = False
    if git_user and owners:
        git_lower = git_user.lower().strip()
        owner_match = any(
            name.lower().strip() == git_lower for name in owner_names
        )

    return {
        "dev_mode": owner_match,
        "is_owner": owner_match,
        "git_user": git_user,
        "owners": owner_names,
    }
