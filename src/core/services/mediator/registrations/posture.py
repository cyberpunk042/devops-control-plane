"""
Posture domain registration — wires system posture into the mediator tree.

Registers 6 nodes matching the existing posture cache keys::

    posture.platform   — OS, kernel, glibc, WSL, arch  (TTL=inf)
    posture.toolchain  — installed tool versions vs EOL (TTL=300s)
    posture.project    — code health / project probes   (TTL=60s)
    posture.runtime    — circuit breakers, retry queue  (TTL=0, always fresh)
    posture.full       — assembled SystemPosture        (TTL=60s)
    posture.summary    — lightweight dict for nav badge (TTL=30s)

Dependency graph::

    posture.platform  ─┐
    posture.toolchain ─┤
    posture.project   ─┼──→ posture.full ──→ posture.summary
    posture.runtime   ─┘

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

    # ── Assembled nodes (depend on pillars) ────────────────────

    def _resolve_full():
        """Assemble full posture from the 4 pillars via the mediator.

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

        posture = SystemPosture(
            pillars={
                "platform": platform,
                "toolchain": toolchain,
                "project": project,
                "runtime": runtime,
            },
            scan_duration_ms=round((_time.time() - t0) * 1000),
        )
        posture.recompute_overall()
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

    logger.debug("registered posture.* nodes (6 total)")
