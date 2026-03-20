"""
Compat domain registration — feature database and orchestrator.

Registers the compat v2 system as mediator nodes so it behaves like
every other data source in the program: cached, persisted, lazy,
zero-cost on boot, zero-cost on cache hit.

Nodes::

    compat.registry       — FeatureRegistry (1000 entries, TTL=inf, persist=pickle)
    compat.orchestrator   — CompatOrchestrator (shared engines, TTL=inf, depends on registry)

The registry loads at BACKGROUND(5) priority on startup dispatch —
it's a sub-feature of posture, loads dead last when nothing else
needs capacity.  On warm restart, the pickle shard hydrates in <50ms.

Dependency graph::

    compat.registry
      └── compat.orchestrator
"""

from __future__ import annotations

import logging

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.tree import TreeRegistration

logger = logging.getLogger(__name__)


def _load_module_configs_light(project_root) -> list[dict]:
    """Load module configs from project.yml without importing compat packages.

    This avoids importing orchestrator.py (which eagerly imports all compat
    engines) during mediator registration — keeps startup fast.
    """
    try:
        import yaml
        config_path = project_root / "project.yml"
        if not config_path.is_file():
            return []
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        modules = data.get("modules", [])
        return [{"name": m.get("name", ""), "path": m.get("path", "")} for m in modules]
    except Exception as exc:
        logger.warning("Failed to load project.yml for compat registration: %s", exc)
        return []


def register_compat(mediator: QueryMediator) -> None:
    """Register compat.* nodes in the mediator tree.

    Parameters
    ----------
    mediator : QueryMediator
        The initialized mediator instance.
    """
    tree = mediator.tree
    root = mediator.project_root

    # ── compat.registry ───────────────────────────────────────
    def _resolve_registry():
        """Load the FeatureRegistry with Python entries only."""
        from src.core.services.compat.database.registry import FeatureRegistry

        registry = FeatureRegistry.load(language="python")
        logger.info(
            "compat.registry loaded: %d entries, %d languages",
            registry.count(),
            len(registry.languages()),
        )
        return registry

    tree.register(TreeRegistration(
        path="compat.registry",
        resolver=_resolve_registry,
        ttl=float("inf"),   # Entries don't change at runtime
        persist=False,       # TODO: add pickle shard for <50ms warm start
    ))

    # ── compat.orchestrator ───────────────────────────────────
    def _resolve_orchestrator():
        """Create a shared orchestrator from the cached registry."""
        from src.core.services.compat.orchestrator import CompatOrchestrator

        registry = mediator.get("compat.registry")["data"]
        return CompatOrchestrator.create_from_registry(
            registry=registry,
            project_root=root,
        )

    tree.register(TreeRegistration(
        path="compat.orchestrator",
        resolver=_resolve_orchestrator,
        ttl=float("inf"),
        depends_on=["compat.registry"],
    ))

    # ── compat.analysis.{module} — cached analysis per module ───
    #
    # Registered dynamically for each module in project.yml.
    # TTL=None (event-driven) — only recomputes when index.scan cascades
    # (i.e., when a file changes). Results persist to disk shard.

    try:
        module_configs = _load_module_configs_light(root)
        for mod in module_configs:
            mod_name = mod.get("name", "")
            mod_path = mod.get("path", "")
            if not mod_name or not mod_path:
                continue

            def _make_analysis_resolver(_mod_name, _mod_path):
                """Create a closure that captures module name/path."""
                def _resolve():
                    compat = mediator.get("compat.orchestrator")["data"]
                    module_dir = root / _mod_path
                    if not module_dir.is_dir():
                        return None

                    # Get target from module's version plan
                    target = "3.8"  # default
                    try:
                        plan = compat.get_plan(_mod_name)
                        if plan and plan.get("target"):
                            target = plan["target"]
                    except Exception:
                        pass

                    return compat.detection.analyze_module(
                        module_dir=module_dir,
                        target_version=target,
                        direction="downgrade",
                        project_root=root,
                    )
                return _resolve

            tree.register(TreeRegistration(
                path=f"compat.analysis.{mod_name}",
                resolver=_make_analysis_resolver(mod_name, mod_path),
                ttl=None,       # Event-driven only
                persist=False,   # Analysis results can be large; recompute is fast after M2
                depends_on=["index.scan", "compat.orchestrator"],
                size=3,         # Heavy — limits concurrency in WorkQueue
            ))

        logger.debug(
            "registered compat.* nodes (%d total: 2 core + %d analysis)",
            2 + len(module_configs),
            len(module_configs),
        )

        # Dispatch registry load at BACKGROUND(5) priority — sub-feature of posture,
        # loads dead last when nothing else needs capacity.
        # The orchestrator and analysis nodes depend on it, so they'll resolve
        # on first access after the registry is loaded.
        try:
            mediator.dispatch("compat.registry")
        except Exception:
            pass  # WorkQueue may not be configured (tests)

    except Exception as exc:
        logger.warning("Failed to register compat.analysis nodes: %s", exc)
        logger.debug("registered compat.* nodes (2 total, no analysis nodes)")
