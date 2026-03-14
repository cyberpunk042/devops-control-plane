"""
Operation context — thread-local operation_id for cross-layer linking.

When a CLI operation is executing, the executor sets the current
operation_id via ``set_operation_id()``. Downstream code (mediator
subscribers, audit staging, ledger ops) reads it via
``get_operation_id()`` to link events back to the triggering operation.

This avoids threading operation_id through every function signature
in the call chain.

Usage::

    from src.core.engine.operation_context import (
        get_operation_id,
        set_operation_id,
    )

    # In executor (start of operation):
    set_operation_id(plan.operation_id)

    # In any downstream code:
    op_id = get_operation_id()  # returns str or None

    # In executor (end of operation):
    set_operation_id(None)
"""

from __future__ import annotations

_current_operation_id: str | None = None


def set_operation_id(op_id: str | None) -> None:
    """Set the current operation_id (called by executor)."""
    global _current_operation_id
    _current_operation_id = op_id


def get_operation_id() -> str | None:
    """Get the current operation_id, or None if no operation is active."""
    return _current_operation_id
