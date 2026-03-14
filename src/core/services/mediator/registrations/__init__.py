"""
Node registrations for the mediator tree.

Each sub-module registers one domain's nodes.  Called from
server.py via ``register_all()`` after the mediator is initialized.

Adding a new domain
───────────────────
1. Create ``registrations/<domain>.py`` with a ``register_<domain>()`` function.
2. Import and call it from ``register_all()`` below.
3. The registration function receives the mediator instance and registers
   tree nodes via ``mediator.tree.register(TreeRegistration(...))``.
"""

from __future__ import annotations

import logging

from src.core.services.mediator.core import QueryMediator

logger = logging.getLogger(__name__)


def register_all(mediator: QueryMediator) -> None:
    """Register all domain nodes in the mediator tree.

    Called once during server startup, after ``mediator.init()``.

    Registration order matters: index first (root of tree),
    then detect, then devops (depends on detect), then posture,
    then github, audit, catalog (leaf domains, no cascading deps).
    """
    from .index import register_index
    from .posture import register_posture
    from .detect import register_detect
    from .devops import register_devops
    from .github import register_github
    from .audit import register_audit
    from .catalog import register_catalog

    from .tabmesh import register_tabmesh
    from .timeline import register_timeline

    register_index(mediator)    # root of the tree — everything depends on this
    register_detect(mediator)   # detect.* depends on index.classify
    register_devops(mediator)   # devops.* depends on detect.*
    register_posture(mediator)  # posture.* depends on devops.*
    register_github(mediator)   # github.* — leaf, no cascade deps
    register_audit(mediator)    # audit.* — leaf, no cascade deps
    register_catalog(mediator)  # catalog.* — leaf, no cascade deps
    register_tabmesh(mediator)  # tabmesh.* — CDP status, leaf, no cascade deps
    register_timeline(mediator) # timeline.* — 23 nodes, own source adapters

    # ── Subscribers (after all domains) ────────────────────────
    from src.core.services.mediator.subscribers.activity import (
        register_activity_subscriber,
    )
    from src.core.services.mediator.subscribers.eventbus_bridge import (
        register_eventbus_bridge,
    )
    from src.core.services.mediator.subscribers.timeline import (
        register_timeline_subscriber,
    )
    register_activity_subscriber(mediator)
    register_eventbus_bridge(mediator)
    register_timeline_subscriber(mediator)

    logger.info(
        "mediator: registered %d nodes (%s)",
        len(mediator.tree.all_paths()),
        ", ".join(sorted(mediator.tree.all_paths())),
    )
