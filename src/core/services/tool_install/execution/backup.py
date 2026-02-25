"""
L4 Execution — Pre-step backup.

Creates timestamped backups before risky steps.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.core.services.tool_install.execution.subprocess_runner import _run_subprocess

logger = logging.getLogger(__name__)


def _backup_before_step(
    step: dict,
    *,
    sudo_password: str = "",
) -> list[str]:
    """Back up paths listed in ``step["backup_before"]``.

    Creates timestamped copies (``PATH.bak.YYYYMMDD_HHMMSS``)
    using ``cp -rp`` (recursive, preserve attributes).  Failures
    are logged but do **not** abort the step—the caller decides
    whether to proceed.

    Returns:
        List of created backup paths (may be empty).
    """
    paths = step.get("backup_before", [])
    if not paths:
        return []

    import time as _bk_time

    ts = _bk_time.strftime("%Y%m%d_%H%M%S")
    backed_up: list[str] = []

    for path_str in paths:
        path = Path(path_str)
        if not path.exists():
            logger.debug("backup_before: path does not exist, skipping: %s", path_str)
            continue
        backup_dest = f"{path_str}.bak.{ts}"
        result = _run_subprocess(
            ["cp", "-rp", path_str, backup_dest],
            needs_sudo=step.get("needs_sudo", False),
            sudo_password=sudo_password,
            timeout=15,
        )
        if result["ok"]:
            backed_up.append(backup_dest)
            logger.info("Backed up %s → %s", path_str, backup_dest)
        else:
            logger.warning(
                "backup_before failed for %s: %s",
                path_str, result.get("error", "unknown"),
            )

    return backed_up

