"""
Dependency Manager — scope-aware package management with live observability.

New service for M2 (Dependency Intelligence). Not an extension of
``packages_svc`` or ``tool_install`` — different execution model.

``packages_svc`` = lightweight status checks for individual packages.
``dependency_mgr`` = scope-aware grouped operations with streaming,
    version intelligence, rollback, and remediation.

Public API::

    from src.core.services.dependency_mgr import get_registry

    registry = get_registry()
    adapter = registry.get("pip")
"""

from __future__ import annotations

from .ecosystem import EcosystemRegistry

_registry: EcosystemRegistry | None = None


def get_registry() -> EcosystemRegistry:
    """Get the singleton ecosystem adapter registry.

    Lazily initializes and registers all adapters on first call.
    """
    global _registry
    if _registry is None:
        _registry = EcosystemRegistry()
        _register_adapters(_registry)
    return _registry


def _register_adapters(registry: EcosystemRegistry) -> None:
    """Register all ecosystem adapters.

    Add new adapters here — one line per ecosystem.
    """
    from .adapters.pip_adapter import PipAdapter
    from .adapters.npm_adapter import NpmAdapter
    from .adapters.go_adapter import GoAdapter
    from .adapters.cargo_adapter import CargoAdapter
    from .adapters.bundler_adapter import BundlerAdapter
    from .adapters.maven_adapter import MavenAdapter
    from .adapters.gradle_adapter import GradleAdapter
    from .adapters.mix_adapter import MixAdapter
    from .adapters.dotnet_adapter import DotnetAdapter

    registry.register(PipAdapter())
    registry.register(NpmAdapter())
    registry.register(GoAdapter())
    registry.register(CargoAdapter())
    registry.register(BundlerAdapter())
    registry.register(MavenAdapter())
    registry.register(GradleAdapter())
    registry.register(MixAdapter())
    registry.register(DotnetAdapter())
