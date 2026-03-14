"""
QueryMediator — trilateral data hub.

Mediates between Backend (demand), Cache (memory), and Index (truth).

Quick start::

    from src.core.services.mediator import mediator

    # Query data
    result = mediator.get("posture.toolchain")
    data = result["data"]         # the actual value
    meta = result["meta"]         # source, age, seq

    # Invalidate (with cascade)
    mediator.put("posture.toolchain", cascade=True)

    # Diagnostics
    info = mediator.diag()

The module-level ``mediator`` is a singleton, initialized via
``init(project_root)`` during server startup (called from server.py).

Sub-modules::

    tree.py   — DataTree: hierarchical namespace, path resolution,
                dependency graph
    core.py   — QueryMediator: get/put/diag, cache management,
                compute locks
"""

from __future__ import annotations

import logging
from pathlib import Path

from .core import CacheEntry, QueryMediator
from .tree import DataTree, TreeNode, TreeRegistration

__all__ = [
    "DataTree",
    "TreeNode",
    "TreeRegistration",
    "QueryMediator",
    "CacheEntry",
    "mediator",
    "init",
    "get_mediator",
]

logger = logging.getLogger(__name__)

# ── Module singleton ───────────────────────────────────────────────

mediator: QueryMediator | None = None
"""The global mediator instance.  ``None`` until ``init()`` is called."""


def init(project_root: Path) -> QueryMediator:
    """Initialize the mediator singleton.

    Called once during server startup (from ``server.py``).
    Creates an empty DataTree and QueryMediator.  Nodes are
    registered by individual service modules during their own
    initialization.

    Parameters
    ----------
    project_root : Path
        Project root directory (same as Flask ``PROJECT_ROOT``).

    Returns
    -------
    QueryMediator
        The initialized mediator instance.
    """
    global mediator

    from .work_queue import WorkQueue

    tree = DataTree()
    _work_queue = WorkQueue(num_workers=4, capacity=6)
    mediator = QueryMediator(tree, project_root, work_queue=_work_queue)

    logger.info("mediator initialized (project_root=%s)", project_root)
    return mediator


def get_mediator() -> QueryMediator:
    """Get the mediator singleton.

    Raises
    ------
    RuntimeError
        If ``init()`` has not been called yet.
    """
    if mediator is None:
        raise RuntimeError(
            "Mediator not initialized.  Call mediator.init() first "
            "(usually from server.py during startup)."
        )
    return mediator
