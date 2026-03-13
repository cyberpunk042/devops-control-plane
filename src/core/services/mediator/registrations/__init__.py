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
    then extra (gh-pulls, audit, project-status — depends on devops).
    """
    from .index import register_index
    from .posture import register_posture
    from .detect import register_detect
    from .devops import register_devops
    from .extra import register_extra

    register_index(mediator)    # root of the tree — everything depends on this
    register_detect(mediator)
    register_devops(mediator)
    register_posture(mediator)
    register_extra(mediator)    # last — extra.project_status depends on devops.status
    logger.info(
        "mediator: registered %d nodes (%s)",
        len(mediator.tree.all_paths()),
        ", ".join(sorted(mediator.tree.all_paths())),
    )
