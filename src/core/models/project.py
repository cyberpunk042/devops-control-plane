"""
Project model — the root identity of a managed project.

Loaded from project.yml, this is the canonical truth about what
the project is, what it contains, and how it's organized.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Environment(BaseModel):
    """A deployment context (dev, staging, production)."""

    name: str
    description: str = ""
    default: bool = False


class ExternalLinks(BaseModel):
    """Links to external systems (informational, resolved by adapters)."""

    ci: str | None = None
    registry: str | None = None
    monitoring: str | None = None
    extra: dict[str, str] = Field(default_factory=dict)


class ModuleRef(BaseModel):
    """A module reference declared in project.yml.

    This is a declaration of intent: "this module exists at this path
    and uses this stack." The actual module state is discovered later
    by the detection service.
    """

    name: str
    path: str
    domain: str = "service"
    stack: str = ""
    description: str = ""


class Project(BaseModel):
    """Root project identity — loaded from project.yml.

    This is the canonical truth. If something isn't declared here,
    it doesn't exist to the control plane.
    """

    version: int = 1

    name: str
    description: str = ""
    repository: str = ""

    domains: list[str] = Field(default_factory=lambda: ["service"])
    environments: list[Environment] = Field(default_factory=list)
    modules: list[ModuleRef] = Field(default_factory=list)
    external: ExternalLinks = Field(default_factory=ExternalLinks)

    def get_environment(self, name: str) -> Environment | None:
        """Look up an environment by name."""
        for env in self.environments:
            if env.name == name:
                return env
        return None

    def default_environment(self) -> Environment | None:
        """Get the default environment, or the first one."""
        for env in self.environments:
            if env.default:
                return env
        return self.environments[0] if self.environments else None

    def get_module(self, name: str) -> ModuleRef | None:
        """Look up a module reference by name."""
        for mod in self.modules:
            if mod.name == name:
                return mod
        return None

    def modules_by_domain(self, domain: str) -> list[ModuleRef]:
        """Get all modules in a given domain."""
        return [m for m in self.modules if m.domain == domain]
