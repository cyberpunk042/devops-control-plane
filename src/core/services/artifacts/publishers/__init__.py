"""
Publisher registry — maps publisher names to classes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import ArtifactPublisher


_PUBLISHERS: dict[str, type["ArtifactPublisher"]] = {}


def _register_defaults() -> None:
    """Lazily register built-in publishers."""
    if _PUBLISHERS:
        return

    from .github_release import GitHubReleasePublisher

    _PUBLISHERS["github-release"] = GitHubReleasePublisher
    # Future:
    # from .pypi import PyPIPublisher
    # _PUBLISHERS["pypi"] = PyPIPublisher
    # _PUBLISHERS["testpypi"] = TestPyPIPublisher
    # from .registry import ContainerRegistryPublisher
    # _PUBLISHERS["ghcr"] = ContainerRegistryPublisher


def get_publisher(name: str) -> "ArtifactPublisher | None":
    """Get a publisher instance by name."""
    _register_defaults()
    cls = _PUBLISHERS.get(name)
    return cls() if cls else None


def list_publishers() -> list[str]:
    """List registered publisher names."""
    _register_defaults()
    return list(_PUBLISHERS.keys())
