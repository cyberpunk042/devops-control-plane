"""Adapters — tool bindings for external integrations.

Public re-exports for convenient access.
"""

from src.adapters.base import Adapter, ExecutionContext
from src.adapters.mock import MockAdapter
from src.adapters.registry import AdapterRegistry

__all__ = [
    "Adapter",
    "AdapterRegistry",
    "ExecutionContext",
    "MockAdapter",
]
