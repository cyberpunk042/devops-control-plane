"""
Posture domain registration — wires system posture into the mediator tree.

Registers 7 nodes matching the existing posture cache keys::

    posture.platform   — OS, kernel, glibc, WSL, arch  (TTL=inf)
    posture.toolchain  — installed tool versions vs EOL (TTL=300s)
    posture.project    — code health / project probes   (TTL=60s)
    posture.runtime    — circuit breakers, retry queue  (TTL=0, always fresh)
    posture.modules    — module stack health / floor    (TTL=60s)
    posture.full       — assembled SystemPosture        (TTL=60s)
    posture.summary    — lightweight dict for nav badge (TTL=30s)

Dependency graph::

    posture.platform  ─┐
    posture.toolchain ─┤
    posture.project   ─┼──→ posture.full ──→ posture.summary
    posture.runtime   ─┤
    posture.modules   ─┘

Resolvers point to the RAW scanner/bridge functions in the
orchestrator module (not the cached wrappers).  The mediator
provides its own caching layer.
"""

from __future__ import annotations

import logging
import math

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.tree import TreeRegistration

logger = logging.getLogger(__name__)


def register_posture(mediator: QueryMediator) -> None:
    """Register posture.* nodes in the mediator tree.

    Each node maps to an existing scanner/bridge function from
    ``system_posture.orchestrator``.  The resolvers are the raw
    functions (with error isolation built in), not the cached
    ``get_or_compute()`` wrappers.

    Parameters
    ----------
    mediator : QueryMediator
        The initialized mediator instance.
    """
    tree = mediator.tree

    # ── Import existing scanner/bridge wrappers ────────────────
    # These are the orchestrator's internal functions that handle
    # error isolation (try/except) already.
    from src.core.services.system_posture.orchestrator import (
        _bridge_modules,
        _bridge_project,
        _bridge_runtime,
        _scan_platform,
        _scan_toolchain,
    )

    # ── Pillar nodes (leaf scanners) ───────────────────────────

    tree.register(TreeRegistration(
        path="posture.platform",
        resolver=_scan_platform,
        ttl=math.inf,       # OS/kernel doesn't change until restart
        persist=True,
    ))

    tree.register(TreeRegistration(
        path="posture.toolchain",
        resolver=_scan_toolchain,
        ttl=300,             # 5 minutes
        persist=True,
    ))

    tree.register(TreeRegistration(
        path="posture.project",
        resolver=lambda: _bridge_project(mediator.project_root),
        ttl=60,              # 1 minute (underlying is mtime-cached)
        persist=True,
        depends_on=["devops.*"],
    ))

    tree.register(TreeRegistration(
        path="posture.runtime",
        resolver=_bridge_runtime,
        ttl=0,               # always fresh — mediator skips cache
    ))

    tree.register(TreeRegistration(
        path="posture.modules",
        resolver=lambda: _bridge_modules(mediator.project_root),
        ttl=60,              # 1 minute (bridges to detection + config)
        persist=True,
    ))

    # ── Assembled nodes (depend on pillars) ────────────────────

    def _resolve_full():
        """Assemble full posture from all 5 pillars via the mediator.

        Instead of calling _assemble_posture (which goes through the
        old cache's get_or_compute), we get each pillar from the
        mediator itself.  This ensures the mediator's cache is the
        single source and cascade works properly.
        """
        from src.core.services.system_posture.models import SystemPosture
        import time as _time

        t0 = _time.time()

        platform = mediator.get("posture.platform")["data"]
        toolchain = mediator.get("posture.toolchain")["data"]
        project = mediator.get("posture.project")["data"]
        runtime = mediator.get("posture.runtime")["data"]
        modules = mediator.get("posture.modules")["data"]

        posture = SystemPosture(
            pillars={
                "platform": platform,
                "toolchain": toolchain,
                "project": project,
                "runtime": runtime,
                "modules": modules,
            },
            scan_duration_ms=round((_time.time() - t0) * 1000),
        )
        posture.recompute_overall()

        # Detect rank changes → emit timeline events
        try:
            old = mediator.peek("posture.full")
            if old is not None:
                old_data = old.get("data")
                # Only compare when old_data is a real SystemPosture with computed ranks
                # (skip on first computation after startup or disk hydration)
                if (old_data
                        and hasattr(old_data, "pillars")
                        and hasattr(old_data, "overall_rank")
                        and hasattr(old_data.overall_rank, "severity")):
                    from src.core.services.events.emit import emit_event
                    for pname, new_pillar in posture.pillars.items():
                        old_pillar = old_data.pillars.get(pname)
                        if old_pillar is None or not hasattr(old_pillar, "rank"):
                            continue
                        old_rank = old_pillar.rank
                        new_rank = new_pillar.rank
                        if (not hasattr(old_rank, "severity")
                                or not hasattr(new_rank, "severity")):
                            continue
                        if old_rank != new_rank:
                            direction = "degraded" if new_rank.severity > old_rank.severity else "improved"
                            emit_event(
                                f"posture.rank.{direction}",
                                summary=f"Posture {pname}: {old_rank.value} → {new_rank.value}",
                                status="warning" if direction == "degraded" else "ok",
                                detail={
                                    "pillar": pname,
                                    "was": old_rank.value,
                                    "now": new_rank.value,
                                    "direction": direction,
                                },
                            )
                    # Overall rank change
                    if (hasattr(old_data, "overall_rank")
                            and old_data.overall_rank != posture.overall_rank):
                        direction = ("degraded"
                                     if posture.overall_rank.severity > old_data.overall_rank.severity
                                     else "improved")
                        emit_event(
                            f"posture.overall.{direction}",
                            summary=f"Posture overall: {old_data.overall_rank.value} → {posture.overall_rank.value}",
                            status="warning" if direction == "degraded" else "ok",
                            detail={
                                "was": old_data.overall_rank.value,
                                "now": posture.overall_rank.value,
                                "status": posture.overall_status,
                            },
                        )
        except Exception:
            pass  # posture events are supplementary, never break computation

        return posture

    tree.register(TreeRegistration(
        path="posture.full",
        resolver=_resolve_full,
        ttl=1200,            # 20 min — cascade handles real changes
        persist=True,
        depends_on=[
            "posture.platform",
            "posture.toolchain",
            "posture.project",
            "posture.runtime",
            "posture.modules",
        ],
    ))

    def _resolve_summary():
        """Derive summary from full posture via the mediator."""
        full = mediator.get("posture.full")["data"]
        return full.to_summary_dict()

    tree.register(TreeRegistration(
        path="posture.summary",
        resolver=_resolve_summary,
        ttl=600,             # 10 min — cascade handles real changes
        persist=True,
        depends_on=["posture.full"],
    ))

    logger.debug("registered posture.* nodes (7 total)")
