"""Artifact builders package."""

from .base import ArtifactBuilder, ArtifactStageInfo  # noqa: F401
from .docker import DockerBuilder  # noqa: F401
from .makefile import MakefileBuilder  # noqa: F401
from .pip_builder import PipBuilder  # noqa: F401
from .script import ScriptBuilder  # noqa: F401


def get_builder(name: str) -> ArtifactBuilder | None:
    """Get an artifact builder by name."""
    _BUILDERS = {
        "makefile": MakefileBuilder,
        "pip": PipBuilder,
        "script": ScriptBuilder,
        "docker": DockerBuilder,
    }
    cls = _BUILDERS.get(name)
    return cls() if cls else None
