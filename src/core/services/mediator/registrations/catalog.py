"""
Catalog domain registrations — mediator nodes for system catalog data.

    catalog.tools    — Tool availability status   (TTL=120s)
    catalog.builders — Page builders listing       (TTL=120s)
    catalog.scripts  — Scripts summary             (TTL=120s)
    catalog.pages    — Pages segments listing       (TTL=120s)

All imports are DEFERRED into resolver functions to avoid loading
heavy modules at registration time.

Mapping to legacy card keys::

    "tools"    → catalog.tools
    "builders" → catalog.builders
    "scripts"  → catalog.scripts
    "pages"    → catalog.pages
"""

from __future__ import annotations

import logging

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.tree import TreeRegistration

logger = logging.getLogger(__name__)


def register_catalog(mediator: QueryMediator) -> None:
    """Register catalog.* nodes for system catalog data.

    All heavy imports are deferred into resolver functions.
    """
    tree = mediator.tree
    root = mediator.project_root

    def _resolve_tools():
        from src.core.services.tool_install.path_refresh import (
            refresh_server_path,
        )
        refresh_server_path()
        from src.core.services.audit.l0_detection import detect_tools
        from src.core.services.tool_install import TOOL_RECIPES

        tools = detect_tools()
        for t in tools:
            tid = t["id"]
            recipe = TOOL_RECIPES.get(tid)
            t["has_recipe"] = recipe is not None
            t["needs_sudo"] = (
                any(recipe["needs_sudo"].values()) if recipe else False
            )
        available = sum(1 for t in tools if t["available"])
        missing = [t for t in tools if not t["available"]]
        return {
            "tools": tools,
            "total": len(tools),
            "available": available,
            "missing_count": len(missing),
            "missing": missing,
        }

    tree.register(TreeRegistration(
        path="catalog.tools",
        resolver=_resolve_tools,
        ttl=120,
        persist=True,
    ))

    def _resolve_builders():
        from src.core.services.pages.engine import list_builders_detail
        return {"builders": list_builders_detail()}

    tree.register(TreeRegistration(
        path="catalog.builders",
        resolver=_resolve_builders,
        ttl=120,
        persist=True,
    ))

    def _resolve_scripts():
        from src.core.services.scripts.registry import get_scripts_summary
        return get_scripts_summary(root)

    tree.register(TreeRegistration(
        path="catalog.scripts",
        resolver=_resolve_scripts,
        ttl=120,
        persist=True,
    ))

    def _resolve_pages():
        from src.core.services.pages.engine import (
            get_segments as _get_segs,
            get_build_status as _build_status,
        )
        segments = _get_segs(root)
        return {
            "segments": [
                {
                    "name": s.name,
                    "source": s.source,
                    "builder": s.builder,
                    "path": s.path,
                    "auto": s.auto,
                    "config": s.config,
                    "build_status": _build_status(root, s.name),
                }
                for s in segments
            ]
        }

    tree.register(TreeRegistration(
        path="catalog.pages",
        resolver=_resolve_pages,
        ttl=120,
        persist=True,
    ))

    logger.debug("registered catalog.* nodes (4 total)")
