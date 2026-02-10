"""
Module model — a project component with detected state.

Modules are the building blocks of a project. Each module has a declared
identity (from project.yml) and a discovered state (from detection).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ModuleHealth(BaseModel):
    """Health snapshot of a module."""

    status: str = "unknown"  # healthy, degraded, unhealthy, unknown
    message: str = ""
    last_checked_at: str | None = None


class Module(BaseModel):
    """A project module with both declared and discovered state.

    The declared fields (name, path, domain, stack_name) come from
    project.yml. The discovered fields are populated by the detection
    service and may change between runs.
    """

    # ── Declared (from project.yml) ──────────────────────────────
    name: str
    path: str
    domain: str = "service"
    stack_name: str = ""         # reference to a stack definition
    description: str = ""

    # ── Discovered (from detection) ──────────────────────────────
    detected: bool = False       # has detection run on this module?
    detected_stack: str = ""     # what stack was actually detected
    version: str | None = None   # detected version (from pyproject.toml, package.json, etc.)
    language: str | None = None  # primary language (python, node, go, etc.)
    dependencies: list[str] = Field(default_factory=list)  # inter-module deps

    # ── Runtime state ────────────────────────────────────────────
    health: ModuleHealth = Field(default_factory=ModuleHealth)

    @property
    def effective_stack(self) -> str:
        """The stack to use: detected overrides declared if available."""
        return self.detected_stack or self.stack_name

    @property
    def is_detected(self) -> bool:
        """Whether detection has run and found this module."""
        return self.detected
