"""
Stack model — technology knowledge.

Stacks define how a kind of module behaves: what it needs, how to
detect it, and what automations are available. Stacks are reusable
across modules and projects.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DetectionRule(BaseModel):
    """How to detect this stack in a directory.

    Detection checks for the presence of specific files and optionally
    searches file contents for identifying strings.
    """

    files_any_of: list[str] = Field(default_factory=list)
    files_all_of: list[str] = Field(default_factory=list)
    content_contains: dict[str, str] = Field(default_factory=dict)
    # e.g. {"pyproject.toml": "fastapi"} — file must contain string


class AdapterRequirement(BaseModel):
    """A required tool adapter with optional version constraint."""

    adapter: str          # adapter name (e.g., "python", "docker")
    min_version: str = "" # minimum version (e.g., "3.11")


class StackCapability(BaseModel):
    """A named capability that this stack supports.

    Maps automation names to adapter commands, allowing the engine
    to know what a stack can do without hardcoding behavior.
    """

    name: str             # capability name (e.g., "install", "lint", "test")
    adapter: str = ""     # which adapter handles this
    command: str = ""     # default command pattern
    description: str = ""


class Stack(BaseModel):
    """Technology knowledge — how a kind of module behaves.

    Stacks are loaded from stacks/<name>/stack.yml and matched to
    modules during detection.
    """

    name: str
    description: str = ""
    domain: str = "service"

    # What this stack needs
    requires: list[AdapterRequirement] = Field(default_factory=list)

    # How to detect it
    detection: DetectionRule = Field(default_factory=DetectionRule)

    # What it can do
    capabilities: list[StackCapability] = Field(default_factory=list)

    def has_capability(self, name: str) -> bool:
        """Check if this stack supports a named capability."""
        return any(c.name == name for c in self.capabilities)

    def get_capability(self, name: str) -> StackCapability | None:
        """Look up a capability by name."""
        for cap in self.capabilities:
            if cap.name == name:
                return cap
        return None

    @property
    def capability_names(self) -> list[str]:
        """List all supported capability names."""
        return [c.name for c in self.capabilities]
