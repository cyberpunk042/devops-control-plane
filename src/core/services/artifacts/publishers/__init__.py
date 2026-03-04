"""
Publisher registry — maps publisher names to classes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import ArtifactPublisher


_PUBLISHERS: dict[str, type["ArtifactPublisher"]] = {}
_INITIALIZED = False


def _register_defaults() -> None:
    """Lazily register built-in publishers."""
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    from .github_release import GitHubReleasePublisher
    from .pypi import PyPIPublisher
    from .npm_publisher import NpmPublisher

    _PUBLISHERS["github-release"] = GitHubReleasePublisher
    _PUBLISHERS["pypi"] = PyPIPublisher
    _PUBLISHERS["npm"] = NpmPublisher


def get_publisher(name: str) -> "ArtifactPublisher | None":
    """Get a publisher instance by name."""
    _register_defaults()

    # Special case: testpypi is PyPIPublisher(test=True)
    if name == "testpypi":
        from .pypi import PyPIPublisher
        return PyPIPublisher(test=True)

    cls = _PUBLISHERS.get(name)
    return cls() if cls else None


def list_publishers() -> list[str]:
    """List registered publisher names."""
    _register_defaults()
    return list(_PUBLISHERS.keys()) + ["testpypi"]

