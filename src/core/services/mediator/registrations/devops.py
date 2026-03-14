"""
DevOps domain registration — direct compute into the mediator tree.

Registers 14 nodes (13 card nodes + 1 aggregate).  Each resolver calls
the compute function DIRECTLY — no ``get_cached()`` wrapper.  The mediator
is the sole data hub:

    - Staleness via cascade (detect.* → devops.*) + mtime_paths (on detect nodes)
    - Persistence via mediator shards (persist=True)
    - Activity logging via the activity subscriber
    - EventBus events via the compat subscriber

Each devops.* node depends on the corresponding detect.* node::

    devops.docker  ──depends_on──→  detect.docker
    devops.k8s     ──depends_on──→  detect.k8s
    ...

Phase 4 added **inter-devops dependencies** that mirror the devops cache's
``_CASCADE`` dict.  When git changes, github/docker/ci/pages may be affected::

    devops.github  ──depends_on──→  devops.git
    devops.docker  ──depends_on──→  devops.git
    devops.ci      ──depends_on──→  devops.git, devops.docker, devops.github
    devops.k8s     ──depends_on──→  devops.docker
    devops.dns     ──depends_on──→  devops.pages

Phase 4 also added ``devops.status`` — an aggregate node that depends on
ALL devops.* card nodes via glob, replacing ``_AGGREGATE_KEYS``.

TTL is ``None`` for all devops nodes because freshness is determined by
cascade invalidation + mtime_paths on the upstream detect nodes, not
the mediator's TTL system.
"""

from __future__ import annotations

import logging

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.tree import TreeRegistration

logger = logging.getLogger(__name__)


# ── Inter-devops dependencies (Phase 4) ───────────────────────────
#
# These mirror the devops cache's _CASCADE dict in reverse direction.
#
# _CASCADE["git"]    = ["github", "docker", "ci", "pages"]
# → devops.github  additionally depends_on devops.git
# → devops.docker  additionally depends_on devops.git
# → devops.ci      additionally depends_on devops.git
# → devops.pages   additionally depends_on devops.git
#
# _CASCADE["docker"] = ["ci", "k8s"]
# → devops.ci      additionally depends_on devops.docker
# → devops.k8s     additionally depends_on devops.docker
#
# _CASCADE["github"] = ["ci"]
# → devops.ci      additionally depends_on devops.github
#
# _CASCADE["pages"]  = ["dns"]
# → devops.dns     additionally depends_on devops.pages

_INTER_DEVOPS_DEPS: dict[str, list[str]] = {
    "devops.github": ["devops.git"],
    "devops.docker": ["devops.git"],
    "devops.ci":     ["devops.git", "devops.docker", "devops.github"],
    # NOTE: _CASCADE also has git→pages and pages→dns, but there is no
    # devops.pages node (pages uses complex inlined compute in the route).
    # These cascade rules are handled by the legacy _CASCADE fallback.
    "devops.k8s":    ["devops.docker"],
}


def register_devops(mediator: QueryMediator) -> None:
    """Register devops.* nodes in the mediator tree.

    Each node calls its compute function directly — the mediator provides
    caching, persistence, and staleness detection.  No ``get_cached()``
    wrapper is involved.

    Parameters
    ----------
    mediator : QueryMediator
        The initialized mediator instance.
    """
    tree = mediator.tree
    root = mediator.project_root

    # ── Deferred imports ──────────────────────────────────────────
    from src.core.services import (
        dns_cdn_ops,
        docker_ops,
        docs_ops,
        env_ops,
        k8s_ops,
        package_ops,
        quality_ops,
        security_ops,
        testing_ops,
    )
    from src.core.services import ci_ops
    from src.core.services import git_ops
    from src.core.services.terraform import ops as terraform_ops

    # ── Security has a composite resolver ──────────────────────────
    def _compute_security():
        scan = security_ops.scan_secrets(root)
        posture = security_ops.security_posture(root)
        return {
            "findings": scan.get("findings", []),
            "finding_count": scan.get("count", 0),
            "posture": posture,
        }

    # ── Node definitions ──────────────────────────────────────────
    #
    # Each resolver calls compute directly — mediator handles caching.
    # TTL=None → staleness via cascade + mtime_paths on detect nodes.
    # persist=True → mediator writes/reads JSON shards for cold start.
    # depends_on → detect.* node + inter-devops deps.
    #
    # NOTE: detect.* nodes have the same resolvers but are NOT dispatched
    # proactively — they exist for cascade invalidation and on-demand
    # queries only.  Dispatch only sends devops.* to avoid duplication.

    _nodes = [
        ("devops.docker",    lambda: docker_ops.docker_status(root),    2),
        ("devops.k8s",       lambda: k8s_ops.k8s_status(root),          2),
        ("devops.git",       lambda: git_ops.git_status(root),           1),
        ("devops.github",    lambda: git_ops.gh_status(root),            2),
        ("devops.ci",        lambda: ci_ops.ci_status(root),             1),
        ("devops.terraform", lambda: terraform_ops.terraform_status(root), 2),
        ("devops.env",       lambda: env_ops.env_card_status(root),      2),
        ("devops.security",  _compute_security,                          3),
        ("devops.packages",  lambda: package_ops.package_status_enriched(root), 1),
        ("devops.quality",   lambda: quality_ops.quality_status(root),   1),
        ("devops.testing",   lambda: testing_ops.testing_status(root),   2),
        ("devops.docs",      lambda: docs_ops.docs_status(root),         1),
        ("devops.dns",       lambda: dns_cdn_ops.dns_cdn_status(root),   1),
    ]

    for mediator_path, compute_fn, node_size in _nodes:
        # Base dependency: the corresponding detect.* node
        detect_dep = mediator_path.replace("devops.", "detect.", 1)
        deps = [detect_dep]

        # Inter-devops dependencies (Phase 4)
        deps.extend(_INTER_DEVOPS_DEPS.get(mediator_path, []))

        tree.register(TreeRegistration(
            path=mediator_path,
            resolver=compute_fn,
            ttl=None,
            persist=True,
            depends_on=deps,
            size=node_size,
        ))


    # ── Aggregate node: devops.status (Phase 4) ───────────────────
    #
    # Depends on ALL devops card nodes via glob.  When any card is
    # invalidated, devops.status is also invalidated.  This replaces
    # the hardcoded _AGGREGATE_KEYS = ["project-status"].
    from src.core.services.project_probes import (
        compute_progress,
        run_all_probes,
        suggest_next,
    )

    def _compute_status():
        statuses = run_all_probes(root)
        return {
            "integrations": statuses,
            "suggested_next": suggest_next(statuses),
            "progress": compute_progress(statuses),
        }

    tree.register(TreeRegistration(
        path="devops.status",
        resolver=_compute_status,
        ttl=None,
        persist=True,
        depends_on=["devops.*"],
    ))

    logger.debug("registered devops.* nodes (14 total, 13 cards + 1 aggregate)")
