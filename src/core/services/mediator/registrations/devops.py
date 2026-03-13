"""
DevOps domain registration — bridges devops cache cards into the mediator tree.

Registers 14 nodes (13 card nodes + 1 aggregate) that wrap ``get_cached()``
from the devops cache module.  Each resolver goes THROUGH ``get_cached`` to
preserve all its side effects:

    - mtime-based staleness checking
    - per-key thread locking
    - file persistence (.state/devops_cache.json)
    - EventBus publishing (cache:hit, cache:miss, cache:done, cache:error)
    - activity logging (.state/audit_activity.json)
    - audit staging (.state/pending_audits.json)
    - _cache metadata injection

Each devops.* node depends on the corresponding detect.* node::

    devops.docker  ──depends_on──→  detect.docker
    devops.k8s     ──depends_on──→  detect.k8s
    ...

Phase 4 added **inter-devops dependencies** that mirror the devops cache's
``_CASCADE`` dict.  When git changes, github/docker/ci/pages may be affected::

    devops.github  ──depends_on──→  devops.git
    devops.docker  ──depends_on──→  devops.git
    devops.ci      ──depends_on──→  devops.git, devops.docker, devops.github
    devops.pages   ──depends_on──→  devops.git
    devops.k8s     ──depends_on──→  devops.docker
    devops.dns     ──depends_on──→  devops.pages

Phase 4 also added ``devops.status`` — an aggregate node that depends on
ALL devops.* card nodes via glob, replacing ``_AGGREGATE_KEYS``.

TTL is ``None`` for all devops nodes because freshness is determined by
``get_cached``'s own mtime logic, not the mediator's TTL system.
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

    Each node wraps ``get_cached()`` so all devops cache side effects
    (activity logging, audit staging, EventBus, persistence) are preserved.
    Nodes depend on the corresponding ``detect.*`` node for cascade, plus
    inter-devops dependencies mirroring the devops cache ``_CASCADE`` dict.

    Parameters
    ----------
    mediator : QueryMediator
        The initialized mediator instance.
    """
    tree = mediator.tree
    root = mediator.project_root

    # ── Deferred imports ──────────────────────────────────────────
    from src.core.services.devops.cache import get_cached
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
    # Pattern: each resolver wraps get_cached to preserve all side effects.
    # TTL=None → freshness delegated to get_cached's mtime logic.
    # persist=False → devops cache handles its own persistence.
    # depends_on → detect.* node + inter-devops deps from _INTER_DEVOPS_DEPS.

    _nodes = [
        ("devops.docker",    "docker",    lambda: docker_ops.docker_status(root)),
        ("devops.k8s",       "k8s",       lambda: k8s_ops.k8s_status(root)),
        ("devops.git",       "git",       lambda: git_ops.git_status(root)),
        ("devops.github",    "github",    lambda: git_ops.gh_status(root)),
        ("devops.ci",        "ci",        lambda: ci_ops.ci_status(root)),
        ("devops.terraform", "terraform", lambda: terraform_ops.terraform_status(root)),
        ("devops.env",       "env",       lambda: env_ops.env_card_status(root)),
        ("devops.security",  "security",  _compute_security),
        ("devops.packages",  "packages",  lambda: package_ops.package_status_enriched(root)),
        ("devops.quality",   "quality",   lambda: quality_ops.quality_status(root)),
        ("devops.testing",   "testing",   lambda: testing_ops.testing_status(root)),
        ("devops.docs",      "docs",      lambda: docs_ops.docs_status(root)),
        ("devops.dns",       "dns",       lambda: dns_cdn_ops.dns_cdn_status(root)),
    ]

    for mediator_path, cache_key, compute_fn in _nodes:
        # Base dependency: the corresponding detect.* node
        detect_dep = mediator_path.replace("devops.", "detect.", 1)
        deps = [detect_dep]

        # Inter-devops dependencies (Phase 4)
        deps.extend(_INTER_DEVOPS_DEPS.get(mediator_path, []))

        # Build a resolver that wraps get_cached.
        # We use a default arg to capture the loop variables correctly.
        def _make_resolver(ck, fn):
            return lambda: get_cached(root, ck, fn)

        tree.register(TreeRegistration(
            path=mediator_path,
            resolver=_make_resolver(cache_key, compute_fn),
            ttl=None,
            persist=False,
            depends_on=deps,
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
        resolver=lambda: get_cached(root, "project-status", _compute_status),
        ttl=None,
        persist=False,
        depends_on=["devops.*"],
    ))

    logger.debug("registered devops.* nodes (14 total, 13 cards + 1 aggregate)")
