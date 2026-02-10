"""
Admin server shared helpers.

Functions used across multiple route blueprints. Each takes
`project_root` explicitly so they can be called from any context
without depending on closure variables.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def fresh_env(project_root: Path) -> dict:
    """Build subprocess env with fresh .env values.

    The server process's os.environ is stale — it was loaded at startup.
    This reads the current .env file on each call so test commands
    use the latest values.
    """
    env = {**os.environ, "TERM": "dumb"}
    env_file = project_root / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    # Strip surrounding quotes
                    if (
                        len(value) >= 2
                        and value[0] == value[-1]
                        and value[0] in ('"', "'")
                    ):
                        value = value[1:-1]
                    env[key] = value
    return env


def gh_repo_flag(project_root: Path) -> list:
    """Get -R repo flag for gh CLI commands.

    Required because mirror remotes cause gh to fail with
    'multiple remotes detected' when no -R is specified.
    """
    repo = fresh_env(project_root).get("GITHUB_REPOSITORY", "")
    return ["-R", repo] if repo else []
