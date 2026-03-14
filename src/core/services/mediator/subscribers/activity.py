"""
Activity logging subscriber for the mediator.

Replicates the side effects of ``devops_cache.get_cached()`` that are
NOT caching — specifically activity logging and audit staging.

Registered during ``register_all()`` after all domain nodes.
Fires on ``"computed"`` events for devops.* and audit.* paths.

This is Chunk 3 of the mediator v2 infrastructure plan.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.services.mediator.core import QueryMediator

logger = logging.getLogger(__name__)


# ── Path → card_key mapping ────────────────────────────────────────
#
# The activity log and audit staging use legacy card keys like
# "docker", "security", "audit:scores".  Mediator paths use dot
# notation: "devops.docker", "audit.scores".  This mapping converts.

_PATH_TO_CARD_KEY: dict[str, str] = {
    # devops domain
    "devops.docker": "docker",
    "devops.k8s": "k8s",
    "devops.git": "git",
    "devops.github": "github",
    "devops.ci": "ci",
    "devops.terraform": "terraform",
    "devops.env": "env",
    "devops.security": "security",
    "devops.packages": "packages",
    "devops.quality": "quality",
    "devops.testing": "testing",
    "devops.docs": "docs",
    "devops.dns": "dns",
    "devops.status": "project-status",
    # github domain
    "github.pulls": "gh-pulls",
    "github.runs": "gh-runs",
    "github.workflows": "gh-workflows",
    # detect domain
    "detect.wizard": "wiz:detect",
    # audit domain
    "audit.scores": "audit:scores",
    "audit.system": "audit:system",
    "audit.deps": "audit:deps",
    "audit.structure": "audit:structure",
    "audit.clients": "audit:clients",
    "audit.system_deep": "audit:system:deep",
    "audit.l2_structure": "audit:l2:structure",
    "audit.l2_quality": "audit:l2:quality",
    "audit.l2_repo": "audit:l2:repo",
    "audit.l2_risks": "audit:l2:risks",
    "audit.scores_enriched": "audit:scores:enriched",
    # catalog domain
    "catalog.tools": "tools",
    "catalog.builders": "builders",
    "catalog.scripts": "scripts",
    "catalog.pages": "pages",
}


def _path_to_card_key(path: str) -> str:
    """Convert mediator path to legacy card key.

    Tries the lookup table first, then falls back to stripping
    the domain prefix: "devops.docker" → "docker".
    """
    if path in _PATH_TO_CARD_KEY:
        return _PATH_TO_CARD_KEY[path]
    # Fallback: strip first segment
    parts = path.split(".", 1)
    return parts[1] if len(parts) > 1 else path


def _on_computed(event: dict[str, Any]) -> None:
    """Subscriber callback — fires after a resolver runs in get().

    Performs:
    1. Activity logging via ``record_scan_activity()``
    2. Audit staging via ``stage_audit()`` (status=ok only)
    """
    if event.get("type") != "computed":
        return

    meta = event.get("compute_meta")
    if meta is None:
        return

    paths = event.get("paths", [])
    if not paths:
        return

    path = paths[0]
    card_key = _path_to_card_key(path)
    data = meta.get("data", {})
    elapsed_s = meta.get("elapsed_s", 0.0)

    # Determine status from data
    if isinstance(data, dict) and "error" in data:
        status = "error"
        error_msg = str(data.get("error", ""))[:200]
    else:
        status = "ok"
        error_msg = ""

    # 1. Activity logging
    try:
        from src.core.services.devops.activity import (
            record_scan_activity,
            _extract_summary,
        )
        record_scan_activity(
            _project_root, card_key, status, elapsed_s,
            data if isinstance(data, dict) else {},
            error_msg,
        )
    except Exception:
        logger.debug("Activity logging failed for %s", path, exc_info=True)

    # 2. Audit staging (only on success)
    if status == "ok":
        try:
            from src.core.services.audit_staging import stage_audit
            from src.core.services.devops.activity import _extract_summary

            summary = _extract_summary(
                card_key, data if isinstance(data, dict) else {},
            )
            stage_audit(
                _project_root, card_key, status, elapsed_s,
                data if isinstance(data, dict) else {},
                summary,
            )
        except Exception:
            logger.debug("Audit staging failed for %s", path, exc_info=True)


# Module-level state — set by register_activity_subscriber()
_project_root = None


def register_activity_subscriber(mediator: QueryMediator) -> str:
    """Register the activity logging subscriber on the mediator.

    Subscribes to all paths (``"*"``) and filters in the callback
    to only process devops.* and audit.* paths (and their extra.*
    equivalents during the transition period).

    Returns the subscription ID.
    """
    global _project_root
    _project_root = mediator.project_root

    sub_id = mediator.subscribe("*", _on_computed)
    logger.info(
        "mediator: activity subscriber registered (sub_id=%s)", sub_id,
    )
    return sub_id
