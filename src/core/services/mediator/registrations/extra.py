"""
Extra domain registrations — mediator nodes for non-detect keys.

Covers keys that were previously only in the disk-based devops cache:

    extra.gh_pulls       — GitHub open PRs           (TTL=120s)
    extra.gh_runs        — GitHub Actions run history (TTL=120s)
    extra.gh_workflows   — GitHub Actions workflows   (TTL=120s)
    extra.project_status — Aggregate project status   (TTL=None, depends on devops.status)
    extra.wiz_detect     — Wizard detection snapshot   (TTL=120s)
    extra.audit_scores   — Audit scores               (TTL=300s)
    extra.audit_system   — L0 system profile           (TTL=300s)
    extra.audit_deps     — L1 dependencies             (TTL=300s)
    extra.audit_structure — L1 structure               (TTL=300s)
    extra.audit_clients  — L1 clients                  (TTL=300s)

These use the ``extra`` namespace to avoid confusion with existing domains.
The resolvers are the same functions used by the web routes.

All imports are DEFERRED into the resolver functions to avoid loading
heavy modules (git_ops, audit, wizard_ops) at registration time.
This keeps startup fast — imports only happen when a resolver fires.

Mapping to _INJECT_KEYS::

    "gh-pulls"       → extra.gh_pulls
    "gh-runs"        → extra.gh_runs
    "gh-workflows"   → extra.gh_workflows
    "project-status" → extra.project_status
    "wiz:detect"     → extra.wiz_detect
    "audit:scores"   → extra.audit_scores
    "audit:system"   → extra.audit_system
    "audit:deps"     → extra.audit_deps
    "audit:structure" → extra.audit_structure
    "audit:clients"  → extra.audit_clients
"""

from __future__ import annotations

import logging

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.tree import TreeRegistration

logger = logging.getLogger(__name__)


def register_extra(mediator: QueryMediator) -> None:
    """Register extra.* nodes for non-detect cache keys.

    All heavy imports are deferred into resolver functions to
    avoid loading git_ops, audit, wizard_ops at registration time.

    Parameters
    ----------
    mediator : QueryMediator
        The initialized mediator instance.
    """
    tree = mediator.tree
    root = mediator.project_root

    # ── GitHub API data ────────────────────────────────────────────
    # These require GitHub CLI auth — resolvers will fail gracefully
    # if gh is not installed or not authenticated.
    # Imports are DEFERRED — git_ops is only loaded when a resolver fires.

    def _resolve_gh_pulls():
        from src.core.services import git_ops
        return git_ops.gh_pulls(root)

    def _resolve_gh_runs():
        from src.core.services import git_ops
        return git_ops.gh_actions_runs(root)

    def _resolve_gh_workflows():
        from src.core.services import git_ops
        return git_ops.gh_actions_workflows(root)

    tree.register(TreeRegistration(
        path="extra.gh_pulls",
        resolver=_resolve_gh_pulls,
        ttl=120,
        persist=True,
    ))

    tree.register(TreeRegistration(
        path="extra.gh_runs",
        resolver=_resolve_gh_runs,
        ttl=120,
        persist=True,
    ))

    tree.register(TreeRegistration(
        path="extra.gh_workflows",
        resolver=_resolve_gh_workflows,
        ttl=120,
        persist=True,
    ))

    # ── Project status (reads from devops.status) ────────────────────
    # NOT a duplicate computation — reads from devops.status which
    # already calls run_all_probes via get_cached.
    # TTL=None → only recomputes when devops.status is invalidated.

    def _resolve_project_status():
        result = mediator.get("devops.status")
        return result.get("data") or {}

    tree.register(TreeRegistration(
        path="extra.project_status",
        resolver=_resolve_project_status,
        ttl=None,
        persist=True,
        depends_on=["devops.status"],
    ))

    # ── Wizard detection ───────────────────────────────────────────
    # Import deferred — wizard_ops only loaded when resolver fires.

    def _resolve_wiz_detect():
        from src.core.services.wizard_ops import wizard_detect
        return wizard_detect(root)

    tree.register(TreeRegistration(
        path="extra.wiz_detect",
        resolver=_resolve_wiz_detect,
        ttl=120,
        persist=True,
    ))

    # ── Audit L0/L1 ───────────────────────────────────────────────
    # Imports deferred — audit module only loaded when resolver fires.

    def _resolve_audit_scores():
        from src.core.services.audit import audit_scores
        return audit_scores(root)

    def _resolve_audit_system():
        from src.core.services.audit import l0_system_profile
        return l0_system_profile(root)

    def _resolve_audit_deps():
        from src.core.services.audit import l1_dependencies
        return l1_dependencies(root)

    def _resolve_audit_structure():
        from src.core.services.audit import l1_structure
        return l1_structure(root)

    def _resolve_audit_clients():
        from src.core.services.audit import l1_clients
        return l1_clients(root)

    tree.register(TreeRegistration(
        path="extra.audit_scores",
        resolver=_resolve_audit_scores,
        ttl=300,
        persist=True,
    ))

    tree.register(TreeRegistration(
        path="extra.audit_system",
        resolver=_resolve_audit_system,
        ttl=300,
        persist=True,
    ))

    tree.register(TreeRegistration(
        path="extra.audit_deps",
        resolver=_resolve_audit_deps,
        ttl=300,
        persist=True,
    ))

    tree.register(TreeRegistration(
        path="extra.audit_structure",
        resolver=_resolve_audit_structure,
        ttl=300,
        persist=True,
    ))

    tree.register(TreeRegistration(
        path="extra.audit_clients",
        resolver=_resolve_audit_clients,
        ttl=300,
        persist=True,
    ))

    logger.debug("registered extra.* nodes (10 total)")
