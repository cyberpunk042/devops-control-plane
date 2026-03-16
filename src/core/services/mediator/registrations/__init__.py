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
    from .dependencies import register_dependencies

    register_index(mediator)    # root of the tree — everything depends on this
    register_detect(mediator)   # detect.* depends on index.classify
    register_devops(mediator)   # devops.* depends on detect.*
    register_posture(mediator)  # posture.* depends on devops.*
    register_github(mediator)   # github.* — leaf, no cascade deps
    register_audit(mediator)    # audit.* — leaf, no cascade deps
    register_catalog(mediator)  # catalog.* — leaf, no cascade deps
    register_tabmesh(mediator)  # tabmesh.* — CDP status, leaf, no cascade deps
    register_dependencies(mediator)  # dependency.* depends on index.scan
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
    # mediator_timeline subscriber removed — replaced by OperationTracker

    # ── Event Store (after all nodes + subscribers) ────────────────
    from src.core.services.events.store import EventStore
    event_store = EventStore(mediator.project_root / ".state")
    event_store.load_cold(days=7)  # warm up from recent history
    mediator.set_event_store(event_store)

    # Seed event store from hydrated cache — creates events for every
    # node that has cached data, so the timeline shows the full state
    # immediately on startup (not just after the first computation).
    if event_store.count() == 0:
        _seed_events_from_cache(mediator, event_store)

    # timeline.data depends on index.scan — it recomputes automatically
    # after every index cycle via the mediator dependency cascade.
    # No polling needed. SSE pushes cache:done live.
    #
    # Force an early computation so the timeline shows historical events
    # immediately on startup (loaded from JSONL cold storage), not just
    # after the first index cycle completes.
    if event_store.count() > 0:
        try:
            mediator.get("timeline.data", force=True)
            logger.info("mediator: timeline.data pre-computed from %d cold events",
                        event_store.count())
        except Exception:
            logger.debug("mediator: timeline.data pre-compute failed", exc_info=True)

    logger.info(
        "mediator: registered %d nodes (%s)",
        len(mediator.tree.all_paths()),
        ", ".join(sorted(mediator.tree.all_paths())),
    )


def _seed_events_from_cache(mediator, event_store) -> None:
    """Create events from all currently cached mediator nodes.

    Called on startup when the event store is empty but the mediator
    has data from disk hydration. This ensures the timeline shows
    the full state immediately, not just after the first cycle.
    """
    import time
    from src.core.services.events.models import Event
    from src.core.services.events.enrichment import (
        derive_event_type,
        extract_summary,
        extract_result_summary,
    )

    seed_corr = f"seed-{int(time.time())}"
    seeded = 0

    for path in sorted(mediator.tree.all_paths()):
        if path.startswith(("timeline.", "detect.", "tabmesh.")):
            continue
        try:
            result = mediator.peek(path)
            if result is None:
                continue
            data = result.get("data")
            if data is None:
                continue

            evt_type = derive_event_type(path)
            summary = extract_summary(path, data)
            detail = extract_result_summary(path, data)
            computed_at = result.get("computed_at", time.time())

            event_store.append(Event(
                id="",
                ts=computed_at,
                type=evt_type,
                correlation_id=seed_corr,
                source="mediator",
                path=path,
                status="ok",
                duration_ms=0,
                summary=summary,
                detail={"result": detail, "source": "hydrated"},
            ))
            seeded += 1
        except Exception:
            pass

    logger.info("mediator: seeded %d events from cache", seeded)
