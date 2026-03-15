"""
Events package — Event Sourcing system for the Solution Control Plane.

Every operation → immutable Event → EventStore → Projections → Timeline.
"""

from src.core.services.events.models import Event
from src.core.services.events.store import EventStore
from src.core.services.events.correlation import (
    set_correlation,
    get_correlation,
    clear_correlation,
)

__all__ = [
    "Event",
    "EventStore",
    "set_correlation",
    "get_correlation",
    "clear_correlation",
]
