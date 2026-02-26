"""
Dev Overrides — system profile resolution with dev override support.

When a project owner has the stage debugger active with a system profile
override, API calls include ``X-Dev-System-Override`` header. This module
provides the entry-point function that respects that header while falling
back to real ``_detect_os()`` for normal requests.

Used by routes_audit.py in place of direct ``_detect_os()`` calls.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from flask import request

logger = logging.getLogger(__name__)


def resolve_system_profile(project_root: Path) -> tuple[dict[str, Any], bool]:
    """Resolve the system profile, respecting dev overrides.

    Checks the ``X-Dev-System-Override`` request header. If present
    and the caller is a verified project owner, returns the
    corresponding system preset instead of the real OS profile.

    Args:
        project_root: Path to the project root (for owner verification).

    Returns:
        Tuple of (system_profile_dict, is_override).
        ``is_override`` is True when a dev preset was used.
    """
    override_header = request.headers.get("X-Dev-System-Override")

    if override_header:
        try:
            override = json.loads(override_header)
            preset_id = override.get("preset_id", "")
        except (json.JSONDecodeError, TypeError):
            preset_id = ""

        if preset_id:
            # Safety: verify the caller is an owner
            from src.core.services.identity import is_owner
            if not is_owner(project_root):
                logger.warning(
                    "System override from non-owner ignored (preset=%s)",
                    preset_id,
                )
            else:
                # Import presets from the scenario engine
                from src.core.services.dev_scenarios import SYSTEM_PRESETS
                if preset_id in SYSTEM_PRESETS:
                    logger.info(
                        "Dev override active: using system preset '%s'",
                        preset_id,
                    )
                    return SYSTEM_PRESETS[preset_id], True
                else:
                    logger.warning(
                        "Unknown system preset '%s', falling back to real",
                        preset_id,
                    )

    # No override — use real detection
    from src.core.services.audit.l0_detection import _detect_os
    return _detect_os(), False
