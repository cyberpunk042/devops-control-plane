"""
Audit domain registrations — mediator nodes for audit data.

L0/L1 (fast, TTL=300s):

    audit.scores    — Composite audit scores
    audit.system    — L0 system profile
    audit.deps      — L1 dependencies
    audit.structure — L1 project structure
    audit.clients   — L1 clients / consumers

L2 + enriched (heavy, TTL=600s):

    audit.system_deep       — L0 deep system profile
    audit.l2_structure      — L2 structure analysis
    audit.l2_quality        — L2 code health
    audit.l2_repo           — L2 repo health
    audit.l2_risks          — L2 risk aggregation
    audit.scores_enriched   — L2-enriched composite scores

All imports are DEFERRED into resolver functions to avoid loading
the audit module at registration time.  Keeps startup fast.

Mapping to legacy card keys::

    "audit:scores"          → audit.scores
    "audit:system"          → audit.system
    "audit:deps"            → audit.deps
    "audit:structure"       → audit.structure
    "audit:clients"         → audit.clients
    "audit:system:deep"     → audit.system_deep
    "audit:l2:structure"    → audit.l2_structure
    "audit:l2:quality"      → audit.l2_quality
    "audit:l2:repo"         → audit.l2_repo
    "audit:l2:risks"        → audit.l2_risks
    "audit:scores:enriched" → audit.scores_enriched
"""

from __future__ import annotations

import logging

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.tree import TreeRegistration

logger = logging.getLogger(__name__)


def register_audit(mediator: QueryMediator) -> None:
    """Register audit.* nodes for audit data.

    All heavy imports are deferred into resolver functions.
    """
    tree = mediator.tree
    root = mediator.project_root

    # ── L0/L1 — fast probes (TTL=300s) ─────────────────────────

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
        path="audit.scores",
        resolver=_resolve_audit_scores,
        ttl=300,
        persist=True,
        mtime_paths=[
            "pyproject.toml", "requirements.txt",
            "package.json", "project.yml",
            "tests/", "docs/", ".gitignore",
        ],
    ))

    tree.register(TreeRegistration(
        path="audit.system",
        resolver=_resolve_audit_system,
        ttl=300,
        persist=True,
        mtime_paths=["project.yml", "stacks/"],
    ))

    tree.register(TreeRegistration(
        path="audit.deps",
        resolver=_resolve_audit_deps,
        ttl=300,
        persist=True,
        mtime_paths=[
            "pyproject.toml", "requirements.txt", "requirements-dev.txt",
            "package.json", "package-lock.json",
            "Cargo.toml", "go.mod", "Gemfile", "mix.exs",
        ],
    ))

    tree.register(TreeRegistration(
        path="audit.structure",
        resolver=_resolve_audit_structure,
        ttl=300,
        persist=True,
        mtime_paths=[
            "project.yml", "src/", "Dockerfile",
            "docker-compose.yml", "docker-compose.yaml",
            ".github/workflows/", "Makefile",
        ],
    ))

    tree.register(TreeRegistration(
        path="audit.clients",
        resolver=_resolve_audit_clients,
        ttl=300,
        persist=True,
        mtime_paths=[
            "pyproject.toml", "requirements.txt",
            "package.json", "go.mod", "Cargo.toml",
        ],
    ))

    # ── L2 + enriched — heavy probes (TTL=600s) ───────────────

    def _resolve_audit_system_deep():
        from src.core.services.audit.l0_detection import l0_system_profile
        return l0_system_profile(root, deep=True)

    def _resolve_l2_structure():
        from src.core.services.audit.l2_structure import l2_structure
        return l2_structure(root)

    def _resolve_l2_quality():
        from src.core.services.audit.l2_quality import l2_quality
        return l2_quality(root)

    def _resolve_l2_repo():
        from src.core.services.audit.l2_repo import l2_repo
        return l2_repo(root)

    def _resolve_l2_risks():
        from src.core.services.audit.l2_risk import l2_risks
        return l2_risks(root)

    def _resolve_audit_scores_enriched():
        from src.core.services.audit.scoring import audit_scores_enriched
        return audit_scores_enriched(root)

    tree.register(TreeRegistration(
        path="audit.system_deep",
        resolver=_resolve_audit_system_deep,
        ttl=600,
        persist=True,
    ))

    tree.register(TreeRegistration(
        path="audit.l2_structure",
        resolver=_resolve_l2_structure,
        ttl=600,
        persist=True,
    ))

    tree.register(TreeRegistration(
        path="audit.l2_quality",
        resolver=_resolve_l2_quality,
        ttl=600,
        persist=True,
    ))

    tree.register(TreeRegistration(
        path="audit.l2_repo",
        resolver=_resolve_l2_repo,
        ttl=600,
        persist=True,
    ))

    tree.register(TreeRegistration(
        path="audit.l2_risks",
        resolver=_resolve_l2_risks,
        ttl=600,
        persist=True,
    ))

    tree.register(TreeRegistration(
        path="audit.scores_enriched",
        resolver=_resolve_audit_scores_enriched,
        ttl=600,
        persist=True,
    ))

    logger.debug("registered audit.* nodes (11 total)")
