"""Artifact builders package."""

from .base import ArtifactBuilder, ArtifactStageInfo  # noqa: F401
from .cargo import CargoBuilder  # noqa: F401
from .docker import DockerBuilder  # noqa: F401
from .dotnet import DotnetBuilder  # noqa: F401
from .gem import GemBuilder  # noqa: F401
from .go import GoBuilder  # noqa: F401
from .gradle import GradleBuilder  # noqa: F401
from .makefile import MakefileBuilder  # noqa: F401
from .maven import MavenBuilder  # noqa: F401
from .mix import MixBuilder  # noqa: F401
from .npm import NpmBuilder  # noqa: F401
from .pip_builder import PipBuilder  # noqa: F401
from .script import ScriptBuilder  # noqa: F401


def get_builder(name: str) -> ArtifactBuilder | None:
    """Get an artifact builder by name.

    Every stack has a dedicated builder with proper validation,
    staging, and output verification.
    """
    _BUILDERS: dict[str, type[ArtifactBuilder]] = {
        # Core builders
        "makefile": MakefileBuilder,
        "pip": PipBuilder,
        "script": ScriptBuilder,
        "docker": DockerBuilder,
        # Stack-specific builders
        "npm": NpmBuilder,
        "cargo": CargoBuilder,
        "go": GoBuilder,
        "maven": MavenBuilder,
        "gradle": GradleBuilder,
        "dotnet": DotnetBuilder,
        "mix": MixBuilder,
        "gem": GemBuilder,
    }
    cls = _BUILDERS.get(name)
    return cls() if cls else None


