"""
Mock adapter — universal test double for all adapter operations.

Used in mock mode to simulate adapter behavior without touching
external tools. Configurable to return success, failure, or custom
responses per action.
"""

from __future__ import annotations

from src.adapters.base import Adapter, ExecutionContext
from src.core.models.action import Receipt


class MockAdapter(Adapter):
    """Universal mock adapter for testing.

    By default, returns success for everything. Can be configured
    with custom responses per action ID.
    """

    def __init__(
        self,
        adapter_name: str = "mock",
        available: bool = True,
        default_output: str = "[mock] executed",
    ):
        self._name = adapter_name
        self._available = available
        self._default_output = default_output
        self._responses: dict[str, Receipt] = {}
        self._call_log: list[ExecutionContext] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def call_log(self) -> list[ExecutionContext]:
        """All execution contexts this mock has received."""
        return self._call_log

    @property
    def call_count(self) -> int:
        """Number of times execute has been called."""
        return len(self._call_log)

    def is_available(self) -> bool:
        return self._available

    def set_response(self, action_id: str, receipt: Receipt) -> None:
        """Set a custom response for a specific action ID."""
        self._responses[action_id] = receipt

    def set_failure(self, action_id: str, error: str = "Mock failure") -> None:
        """Configure a specific action to fail."""
        self._responses[action_id] = Receipt.failure(
            adapter=self._name,
            action_id=action_id,
            error=error,
        )

    def validate(self, context: ExecutionContext) -> tuple[bool, str]:
        return True, ""

    def execute(self, context: ExecutionContext) -> Receipt:
        self._call_log.append(context)

        # Check for custom response
        if context.action.id in self._responses:
            return self._responses[context.action.id]

        # Default: success
        return Receipt.success(
            adapter=self._name,
            action_id=context.action.id,
            output=self._default_output,
            metadata={"mock": True},
        )

    def reset(self) -> None:
        """Clear call log and custom responses."""
        self._call_log.clear()
        self._responses.clear()
