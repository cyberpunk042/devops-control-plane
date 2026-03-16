"""
Dependency domain registration — wires dependency_mgr into the mediator tree.

Registers 3 nodes::

    dependency.manifests  — Phase 1 detection (fast, depends on index.scan)
    dependency.tree       — Full tree with parsed deps (depends on manifests)
    dependency.summary    — Dashboard card counts (depends on tree)

Dependency graph::

    index.scan ──→ dependency.manifests ──→ dependency.tree ──→ dependency.summary
"""

from __future__ import annotations

import logging

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.tree import TreeRegistration

logger = logging.getLogger(__name__)


def register_dependencies(mediator: QueryMediator) -> None:
    """Register dependency.* nodes in the mediator tree.

    Parameters
    ----------
    mediator : QueryMediator
        The initialized mediator instance.
    """
    tree = mediator.tree

    # ── Phase 1: manifest detection (lightweight) ─────────────

    def _resolve_manifests():
        from src.core.services.dependency_mgr.scanner import detect_manifests
        from src.core.services.dependency_mgr import get_registry

        index_result = mediator.get("index.scan")
        modules = []
        if index_result and index_result.get("data"):
            data = index_result["data"]
            if isinstance(data, dict):
                modules = data.get("modules", [])

        registry = get_registry()
        manifests = detect_manifests(mediator.project_root, modules, registry)
        return [m.to_dict() for m in manifests]

    tree.register(TreeRegistration(
        path="dependency.manifests",
        resolver=_resolve_manifests,
        ttl=300,             # 5 minutes
        persist=True,
        depends_on=["index.scan"],
        size=1,
    ))

    # ── Phase 2: full tree with parsed dependencies ───────────

    def _resolve_tree():
        from src.core.services.dependency_mgr.scanner import parse_manifests
        from src.core.services.dependency_mgr.tree import build_tree
        from src.core.services.dependency_mgr.state import get_active_notes
        from src.core.services.dependency_mgr.models import ManifestInfo
        from src.core.services.dependency_mgr import get_registry

        manifests_result = mediator.get("dependency.manifests")
        if not manifests_result or not manifests_result.get("data"):
            return {"id": "global", "label": "Global", "level": "global"}

        manifests_raw = manifests_result["data"]
        manifests = [ManifestInfo.from_dict(m) for m in manifests_raw]

        registry = get_registry()
        parsed = parse_manifests(mediator.project_root, manifests, registry)
        notes = get_active_notes(mediator.project_root)

        root = build_tree(manifests, registry, parsed=parsed, notes=notes)
        return root.to_dict()

    tree.register(TreeRegistration(
        path="dependency.tree",
        resolver=_resolve_tree,
        ttl=300,
        persist=True,
        depends_on=["dependency.manifests"],
        size=2,
    ))

    # ── Summary for dashboard card ────────────────────────────

    def _resolve_summary():
        tree_result = mediator.get("dependency.tree")
        if not tree_result or not tree_result.get("data"):
            return {"ecosystems": 0, "total_packages": 0, "outdated": 0, "deprecated": 0}

        tree_data = tree_result["data"]
        children = tree_data.get("children", [])
        ecosystems = len(children)
        total_pkgs = sum(len(eco.get("children", [])) for eco in children)
        outdated = _count_status(children, "outdated")
        deprecated = _count_status(children, "deprecated")

        return {
            "ecosystems": ecosystems,
            "total_packages": total_pkgs,
            "outdated": outdated,
            "deprecated": deprecated,
        }

    tree.register(TreeRegistration(
        path="dependency.summary",
        resolver=_resolve_summary,
        ttl=300,
        persist=True,
        depends_on=["dependency.tree"],
        size=1,
    ))


def _count_status(ecosystem_nodes: list, status: str) -> int:
    """Count packages with a given status across all ecosystem nodes."""
    count = 0
    for eco in ecosystem_nodes:
        for pkg in eco.get("children", []):
            if pkg.get("status") == status:
                count += 1
    return count
