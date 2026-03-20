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


def register_all(mediator: QueryMediator, *, _debug_checkpoint=None) -> None:
    """Register all domain nodes in the mediator tree.

    Called once during server startup, after ``mediator.init()``.

    Registration order matters: index first (root of tree),
    then detect, then devops (depends on detect), then posture,
    then github, audit, catalog (leaf domains, no cascading deps).

    Parameters
    ----------
    _debug_checkpoint : callable | None
        If provided, called with a label string after each step.
        Used by ``--debug-startup`` to profile registration.
    """
    _cp = _debug_checkpoint or (lambda label: None)

    from .index import register_index
    from .posture import register_posture
    from .detect import register_detect
    from .devops import register_devops
    from .github import register_github
    from .audit import register_audit
    from .catalog import register_catalog

    from .compat import register_compat
    from .tabmesh import register_tabmesh
    from .timeline import register_timeline
    from .dependencies import register_dependencies
    _cp("  ↳ domain imports")

    register_index(mediator)
    _cp("  ↳ register index")
    register_detect(mediator)
    _cp("  ↳ register detect")
    register_devops(mediator)
    _cp("  ↳ register devops")
    register_posture(mediator)
    _cp("  ↳ register posture")
    register_github(mediator)
    _cp("  ↳ register github")
    register_audit(mediator)
    _cp("  ↳ register audit")
    register_catalog(mediator)
    _cp("  ↳ register catalog")
    register_compat(mediator)
    _cp("  ↳ register compat")
    register_tabmesh(mediator)
    _cp("  ↳ register tabmesh")
    register_dependencies(mediator)
    _cp("  ↳ register dependencies")
    register_timeline(mediator)
    _cp("  ↳ register timeline")

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
    _cp("  ↳ subscribers")

    # ── Event Store (after all nodes + subscribers) ────────────────
    from src.core.services.events.store import EventStore
    event_store = EventStore(mediator.project_root / ".state")
    mediator.set_event_store(event_store)

    # Load cold events + timeline in background — don't block startup.
    # Timeline becomes available after background load completes.
    def _boot_event_store():
        event_store.load_cold(days=7)
        logger.info("event store: loaded %d cold events", event_store.count())
        if event_store.count() == 0:
            _seed_events_from_cache(mediator, event_store)
        # Recompute timeline.data now that events are loaded
        try:
            mediator.get("timeline.data", force=True)
        except Exception:
            pass

    try:
        from src.core.services.mediator.work_queue import WorkItem, Priority
        wq = mediator._work_queue
        if wq is not None:
            wq.submit(WorkItem(
                priority=Priority.LOW,
                size=2,
                path="boot.event_store",
                resolver=_boot_event_store,
            ))
        else:
            _boot_event_store()  # No work queue — run synchronously
    except Exception:
        _boot_event_store()  # Fallback
    _cp("  ↳ event store + timeline dispatched")

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
