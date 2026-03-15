"""
Correlation context — thread-local correlation ID for event chaining.

When an index cycle starts, it sets the correlation ID. Every mediator
computation during that cycle inherits the same correlation ID. When a
route handles a request, it sets a correlation ID for that operation.

All events emitted during the operation share the correlation ID,
forming a chain automatically.
"""

from __future__ import annotations

import threading

_local = threading.local()


def set_correlation(correlation_id: str | None) -> None:
    """Set the active correlation ID for this thread."""
    _local.correlation_id = correlation_id


def get_correlation() -> str | None:
    """Get the active correlation ID, or None."""
    return getattr(_local, "correlation_id", None)


def clear_correlation() -> None:
    """Clear the active correlation ID."""
    _local.correlation_id = None
