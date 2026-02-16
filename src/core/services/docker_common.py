"""Docker shared helpers — low-level command runners."""

from __future__ import annotations

import subprocess
from pathlib import Path
import logging

logger = logging.getLogger(__name__)



def run_docker(
    *args: str,
    cwd: Path,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    """Run a docker command and return the result."""
    return subprocess.run(
        ["docker", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def run_compose(
    *args: str,
    cwd: Path,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Run a docker compose command and return the result."""
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
