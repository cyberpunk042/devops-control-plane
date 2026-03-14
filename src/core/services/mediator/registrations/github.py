"""
GitHub domain registrations — mediator nodes for GitHub API data.

    github.pulls      — Open PRs              (TTL=120s)
    github.runs       — GitHub Actions runs    (TTL=120s)
    github.workflows  — GitHub Actions workflows (TTL=120s)

These require GitHub CLI auth — resolvers fail gracefully
if ``gh`` is not installed or not authenticated.

All imports are DEFERRED into resolver functions to avoid loading
``git_ops`` at registration time.  Keeps startup fast.

Mapping to legacy card keys::

    "gh-pulls"       → github.pulls
    "gh-runs"        → github.runs
    "gh-workflows"   → github.workflows
"""

from __future__ import annotations

import logging

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.tree import TreeRegistration

logger = logging.getLogger(__name__)


def register_github(mediator: QueryMediator) -> None:
    """Register github.* nodes for GitHub API data.

    All heavy imports are deferred into resolver functions.
    """
    tree = mediator.tree
    root = mediator.project_root

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
        path="github.pulls",
        resolver=_resolve_gh_pulls,
        ttl=120,
        persist=True,
    ))

    tree.register(TreeRegistration(
        path="github.runs",
        resolver=_resolve_gh_runs,
        ttl=120,
        persist=True,
    ))

    tree.register(TreeRegistration(
        path="github.workflows",
        resolver=_resolve_gh_workflows,
        ttl=120,
        persist=True,
    ))

    logger.debug("registered github.* nodes (3 total)")
