"""
ProjectState — the root state model.

This is the single document that captures everything about the current
project state. It's serialized to .state/current.json and loaded on
every operation.

Equivalent to the continuity-orchestrator's State model
(.state/current.json), generalized for any project domain.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def _now_iso() -> str:
    """Current UTC time as ISO string."""
    return datetime.now(UTC).isoformat()


class AdapterState(BaseModel):
    """Runtime state of an adapter."""

    name: str
    available: bool = False
    version: str | None = None
    last_used_at: str | None = None
    failure_count: int = 0
    circuit_state: str = "closed"  # closed, open, half_open


class ModuleState(BaseModel):
    """Runtime state of a module."""

    name: str
    detected: bool = False
    stack: str = ""
    version: str | None = None
    last_action_at: str | None = None
    last_action_status: str | None = None  # ok, failed, skipped


class OperationRecord(BaseModel):
    """Summary of the last operation."""

    operation_id: str = ""
    automation: str = ""
    started_at: str = ""
    ended_at: str = ""
    status: str = ""  # ok, partial, failed
    actions_total: int = 0
    actions_succeeded: int = 0
    actions_failed: int = 0


class ProjectState(BaseModel):
    """Root state model — serialized to .state/current.json.

    This is the observed reality of the project at a point in time.
    It's disposable and reproducible: delete it and the engine
    will regenerate everything from project.yml + detection.
    """

    # ── Schema ───────────────────────────────────────────────────
    schema_version: int = 1

    # ── Identity ─────────────────────────────────────────────────
    project_name: str = ""
    current_environment: str = "dev"

    # ── Timestamps ───────────────────────────────────────────────
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
    last_detection_at: str | None = None

    # ── Component state ──────────────────────────────────────────
    modules: dict[str, ModuleState] = Field(default_factory=dict)
    adapters: dict[str, AdapterState] = Field(default_factory=dict)

    # ── Last operation ───────────────────────────────────────────
    last_operation: OperationRecord = Field(default_factory=OperationRecord)

    # ── Extensible metadata ──────────────────────────────────────
    metadata: dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = _now_iso()

    def set_module_state(self, name: str, **kwargs: Any) -> None:
        """Update or create a module state entry."""
        if name in self.modules:
            for key, value in kwargs.items():
                setattr(self.modules[name], key, value)
        else:
            self.modules[name] = ModuleState(name=name, **kwargs)

    def set_adapter_state(self, name: str, **kwargs: Any) -> None:
        """Update or create an adapter state entry."""
        if name in self.adapters:
            for key, value in kwargs.items():
                setattr(self.adapters[name], key, value)
        else:
            self.adapters[name] = AdapterState(name=name, **kwargs)
