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

    # ── Version intelligence (network-heavy, long TTL) ────────

    def _resolve_versions():
        from src.core.services.dependency_mgr.scanner import parse_manifests
        from src.core.services.dependency_mgr.version_intel import (
            resolve_version_intel, version_intel_to_dict,
        )
        from src.core.services.dependency_mgr.models import ManifestInfo
        from src.core.services.dependency_mgr import get_registry

        manifests_result = mediator.get("dependency.manifests")
        if not manifests_result or not manifests_result.get("data"):
            return {}

        manifests_raw = manifests_result["data"]
        manifests = [ManifestInfo.from_dict(m) for m in manifests_raw]

        registry = get_registry()
        parsed = parse_manifests(mediator.project_root, manifests, registry)
        intel = resolve_version_intel(parsed, registry)
        return version_intel_to_dict(intel)

    tree.register(TreeRegistration(
        path="dependency.versions",
        resolver=_resolve_versions,
        ttl=3600,            # 1 hour — network calls, expensive
        persist=True,
        depends_on=["dependency.manifests"],
        size=2,
    ))

    # ── Venv info (detect available environments) ──────────────

    def _resolve_venv_info():
        from src.core.services.dependency_mgr.venv_info import detect_venvs, check_venv_health

        result = detect_venvs(mediator.project_root)

        # Proactive health check — creates notifications if venv issues detected
        check_venv_health(mediator.project_root)

        return result

    tree.register(TreeRegistration(
        path="dependency.venvs",
        resolver=_resolve_venv_info,
        ttl=300,
        persist=False,  # Venv state changes at runtime
        size=1,
    ))

    # ── Installed packages (from active venv) ────────────────

    def _resolve_installed():
        from src.core.services.dependency_mgr.venv_info import get_installed_packages
        return get_installed_packages(mediator.project_root)

    tree.register(TreeRegistration(
        path="dependency.installed",
        resolver=_resolve_installed,
        ttl=300,
        persist=True,
        size=1,
    ))

    # ── Phase 2: full tree with parsed dependencies ───────────

    def _resolve_tree():
        from src.core.services.dependency_mgr.scanner import parse_manifests
        from src.core.services.dependency_mgr.tree import build_tree
        from src.core.services.dependency_mgr.state import get_active_notes
        from src.core.services.dependency_mgr.version_intel import version_intel_from_dict
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

        # Version intelligence (may be empty if not yet computed)
        vi_result = mediator.peek("dependency.versions")
        version_intel = {}
        if vi_result and vi_result.get("data"):
            try:
                version_intel = version_intel_from_dict(vi_result["data"])
            except Exception:
                pass

        # Installed packages from active venv
        try:
            inst_result = mediator.get("dependency.installed")
            installed = inst_result.get("data", {}) if inst_result else {}
        except Exception:
            installed = {}

        root = build_tree(manifests, registry, parsed=parsed, notes=notes,
                          version_intel=version_intel, installed_packages=installed)
        return root.to_dict()

    tree.register(TreeRegistration(
        path="dependency.tree",
        resolver=_resolve_tree,
        ttl=300,
        persist=True,
        depends_on=["dependency.manifests", "dependency.installed"],
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
