"""
Shared audit helper — one source of truth for recording audit events.

Replaces the 17+ identical ``_audit()`` copy-paste functions across service
modules.  Every service that needs audit logging imports from here.

Usage (preferred — factory pattern)::

    from src.core.services.audit_helpers import make_auditor

    _audit = make_auditor("vault")

    # Then in any function:
    _audit("🔒 Vault Locked", "Vault locked by user", action="locked")

Usage (direct, when card varies per call)::

    from src.core.services.audit_helpers import audit_event

    audit_event("vault", "🔒 Vault Locked", "Vault locked by user")

The helper is fail-safe: if no project root is set (e.g. unit tests without
a project context), the call silently returns.  It never raises.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def audit_event(
    card: str,
    label: str,
    summary: str,
    **kwargs: Any,
) -> None:
    """Record an audit event if a project root is registered.

    Args:
        card: The card/domain this event belongs to (e.g. "vault", "backup").
        label: Short emoji-prefixed label (e.g. "🔒 Vault Locked").
        summary: Human-readable description of what happened.
        **kwargs: Additional fields passed to ``record_event``
            (action, target, detail, before_state, after_state).
    """
    try:
        from src.core.context import get_project_root

        root = get_project_root()
    except Exception:
        return
    if root is None:
        return

    try:
        from src.core.services.devops_cache import record_event

        record_event(root, label=label, summary=summary, card=card, **kwargs)
    except Exception as exc:
        logger.debug("Failed to record audit event: %s", exc)


def make_auditor(card: str) -> Callable[..., None]:
    """Create a module-level ``_audit`` function pre-bound to a card name.

    Returns a callable with signature ``(label, summary, **kwargs) -> None``
    that is a drop-in replacement for the old per-module ``_audit()`` function.

    Usage::

        _audit = make_auditor("vault")
        _audit("🔒 Locked", "Vault locked by user")
    """

    def _audit(label: str, summary: str, **kwargs: Any) -> None:
        audit_event(card, label, summary, **kwargs)

    return _audit
