"""
Action and Receipt models — the execution contract.

Actions represent requested operations. Receipts represent results.
This is the fundamental I/O contract between the engine and adapters:
the engine sends Actions, adapters return Receipts. Never exceptions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


def _now_iso() -> str:
    """Current UTC time as ISO string."""
    return datetime.now(UTC).isoformat()


class Action(BaseModel):
    """A requested operation to be executed by an adapter.

    Actions are the engine's way of saying "do this thing."
    They are created by the planning service and dispatched
    through the adapter registry.
    """

    id: str                         # unique action identifier
    name: str = ""                  # human-readable name
    adapter: str                    # which adapter handles this
    capability: str = ""            # stack capability name
    params: dict[str, Any] = Field(default_factory=dict)
    for_module: str | None = None   # target module (None = project-wide)


class Receipt(BaseModel):
    """Result of an adapter execution.

    Receipts capture the full outcome of an action. The adapter
    NEVER raises exceptions — failures are captured here.

    This is directly inspired by the continuity-orchestrator's
    Receipt model, proven across 13 adapters in production.
    """

    adapter: str
    action_id: str
    status: Literal["ok", "skipped", "failed"] = "ok"

    started_at: str = Field(default_factory=_now_iso)
    ended_at: str = Field(default_factory=_now_iso)
    duration_ms: int = 0

    output: str = ""
    error: str | None = None
    delivery_id: str | None = None   # unique execution trace identifier

    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Whether the action succeeded."""
        return self.status == "ok"

    @property
    def failed(self) -> bool:
        """Whether the action failed."""
        return self.status == "failed"

    @classmethod
    def success(
        cls,
        adapter: str,
        action_id: str,
        output: str = "",
        **kwargs: Any,
    ) -> Receipt:
        """Create a success receipt."""
        return cls(
            adapter=adapter,
            action_id=action_id,
            status="ok",
            output=output,
            **kwargs,
        )

    @classmethod
    def failure(
        cls,
        adapter: str,
        action_id: str,
        error: str,
        **kwargs: Any,
    ) -> Receipt:
        """Create a failure receipt."""
        return cls(
            adapter=adapter,
            action_id=action_id,
            status="failed",
            error=error,
            **kwargs,
        )

    @classmethod
    def skip(
        cls,
        adapter: str,
        action_id: str,
        reason: str = "",
        **kwargs: Any,
    ) -> Receipt:
        """Create a skip receipt."""
        return cls(
            adapter=adapter,
            action_id=action_id,
            status="skipped",
            output=reason,
            **kwargs,
        )
