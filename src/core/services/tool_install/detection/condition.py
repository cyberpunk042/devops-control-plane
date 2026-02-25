"""
L3 Detection — Condition evaluation.

Evaluates post_install conditions against system profile.
Read-only — uses shutil.which and os.path for checks.
"""

from __future__ import annotations

import logging
import os
import shutil

logger = logging.getLogger(__name__)


def _evaluate_condition(
    condition: str | None,
    system_profile: dict,
) -> bool:
    """Evaluate a post_install condition against the system profile.

    Args:
        condition: One of ``"has_systemd"``, ``"not_root"``,
                   ``"not_container"``, or ``None``.
        system_profile: Phase 1 system detection output.

    Returns:
        True if the condition is met (step should be included).
    """
    if condition is None:
        return True
    if condition == "has_systemd":
        return system_profile.get("capabilities", {}).get("systemd", False)
    if condition == "has_openrc":
        return (
            system_profile.get("init_system", {}).get("type") == "openrc"
        )
    if condition == "not_root":
        return not system_profile.get("capabilities", {}).get("is_root", False)
    if condition == "is_root":
        return system_profile.get("capabilities", {}).get("is_root", False)
    if condition == "not_container":
        return not system_profile.get("container", {}).get("in_container", False)
    if condition == "has_docker":
        return shutil.which("docker") is not None
    if condition.startswith("file_exists:"):
        target_path = condition.split(":", 1)[1]
        return os.path.isfile(target_path)
    logger.warning("Unknown post_install condition: %s", condition)
    return True
