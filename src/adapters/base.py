"""
Adapter base — the protocol contract between engine and tools.

This defines the abstract interface that every adapter must implement.
The engine only talks to adapters through this protocol, never
directly to external tools.

Directly modeled on the continuity-orchestrator's Adapter base class,
proven across 13 adapters in production.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from src.core.models.action import Action, Receipt


class ExecutionContext(BaseModel):
    """Everything an adapter needs to execute an action.

    This is the adapter's view of the world: the action to perform,
    the project root, the environment, and any resolved parameters.
    """

    action: Action
    project_root: str = "."
    environment: str = "dev"
    module_path: str | None = None
    dry_run: bool = False
    params: dict[str, Any] = Field(default_factory=dict)

    @property
    def working_dir(self) -> str:
        """Resolved working directory for the action."""
        if self.module_path:
            return f"{self.project_root}/{self.module_path}"
        return self.project_root


class Adapter(ABC):
    """Abstract base class for all adapters.

    Adapters perform external side effects and return receipts.
    They NEVER raise exceptions — failures are captured in the Receipt.

    To create a new adapter:
        1. Subclass Adapter
        2. Implement name, is_available, validate, execute
        3. Register it in the AdapterRegistry
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The adapter identifier (e.g., 'shell', 'docker', 'git')."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this adapter's underlying tool is available.

        For example, a Docker adapter checks if the docker CLI exists.
        Should be fast and never raise.
        """

    @abstractmethod
    def validate(self, context: ExecutionContext) -> tuple[bool, str]:
        """Validate that the action can be executed.

        Returns:
            (is_valid, error_message). error_message is empty if valid.
        """

    @abstractmethod
    def execute(self, context: ExecutionContext) -> Receipt:
        """Execute the action and return a receipt.

        MUST never raise exceptions. All failures are captured
        in the Receipt with status='failed'.
        """

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
