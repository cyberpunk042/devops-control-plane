"""
Project model — the root identity of a managed project.

Loaded from project.yml, this is the canonical truth about what
the project is, what it contains, and how it's organized.
"""

from __future__ import annotations

from typing import Literal

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


class ModuleDeferral(BaseModel):
    """A deferred posture warning — team decision to address later."""

    until: str = ""       # target date: "2026-09-01" or "Q3 2026"
    reason: str = ""      # why it's deferred


class ModuleVersionPlanStep(BaseModel):
    """A single step in a version upgrade checklist.

    The ``id`` field links the step to an automation handler.
    Format: ``{automation_id}:{suffix}`` for generated steps,
    ``custom:{suffix}`` for user-added steps, or ``""`` for
    legacy steps created before the generator existed.
    """

    id: str = ""
    label: str
    description: str = ""
    done: bool = False


class ModuleVersionPlan(BaseModel):
    """A version upgrade plan — team commitment to raise the floor."""

    target: str = ""      # target floor version, e.g. "3.12"
    date: str = ""        # target date, e.g. "Q3 2026"
    checklist: list[ModuleVersionPlanStep] = Field(default_factory=list)


class ModuleRef(BaseModel):
    """A module reference declared in project.yml.

    This is a declaration of intent: "this module exists at this path
    and uses this stack." The actual module state is discovered later
    by the detection service.

    Decision fields (version_strategy, version_note, deferral, version_plan)
    are team decisions — version-controlled, shared, visible to everyone.
    """

    # Identity
    name: str
    path: str
    domain: str = "service"
    stack: str = ""
    description: str = ""

    # Decisions
    version_strategy: Literal["latest", "compatibility", ""] = ""
    version_note: str = ""
    deferral: ModuleDeferral | None = None
    version_plan: ModuleVersionPlan | None = None


class WebSettings(BaseModel):
    """Web admin panel server settings.

    Controls port binding, fallback ports, host address, and log file path.
    If the preferred port is occupied by another process,
    the server will try each fallback port in order.
    """

    port: int = 8000
    fallback_ports: list[int] = Field(
        default_factory=lambda: [8001, 8002, 8080, 8888, 9000],
    )
    host: str = "127.0.0.1"
    log_file: str = ".state/web.log"


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
    web: WebSettings = Field(default_factory=WebSettings)

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
