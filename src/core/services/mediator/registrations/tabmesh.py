"""
Tab Mesh domain — CDP status mediator node.

Registers ``tabmesh.cdp_status`` to cache Chrome DevTools Protocol
availability.  Persisted to disk.  Hydrated on server restart.
Updated by the boot warm-up task and invalidated on CDP failure.
"""

from __future__ import annotations

import logging
import time

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.tree import TreeRegistration

logger = logging.getLogger(__name__)


def register_tabmesh(mediator: QueryMediator) -> None:
    """Register tab mesh nodes in the mediator tree."""
    tree = mediator.tree

    tree.register(TreeRegistration(
        path="tabmesh.cdp_status",
        resolver=_resolve_cdp_status,
        ttl=300,          # 5 min — Chrome doesn't restart often
        persist=True,     # survives server restart
        size=1,
    ))


def _resolve_cdp_status() -> dict:
    """Check Chrome DevTools Protocol availability.

    Calls cdp_client.is_available() to check if Chrome's
    /json/version endpoint is reachable via any transport channel.
    """
    try:
        from src.ui.web.cdp_client import is_available, try_discover_endpoint

        endpoint = try_discover_endpoint()
        available = is_available() if endpoint else False

        return {
            "available": available,
            "endpoint": endpoint,
            "ts": time.time(),
        }
    except Exception as exc:
        logger.debug("CDP status check failed: %s", exc)
        return {
            "available": False,
            "endpoint": None,
            "error": str(exc),
            "ts": time.time(),
        }
