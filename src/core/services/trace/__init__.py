"""
SCP Session Tracing — opt-in recording of operations.

Public API:
    from src.core.services.trace import start_recording, stop_recording
    from src.core.services.trace import save_trace, share_trace, list_traces, get_trace
    from src.core.services.trace import generate_summary, post_trace_to_chat
"""

from src.core.services.trace.models import SessionTrace, TraceEvent
from src.core.services.trace.trace_recorder import (
    active_recordings,
    delete_trace,
    generate_summary,
    get_trace,
    get_trace_events,
    list_traces,
    post_trace_to_chat,
    save_trace,
    share_trace,
    start_recording,
    stop_recording,
    unshare_trace,
    update_trace,
)

__all__ = [
    "SessionTrace",
    "TraceEvent",
    "active_recordings",
    "delete_trace",
    "generate_summary",
    "get_trace",
    "get_trace_events",
    "list_traces",
    "post_trace_to_chat",
    "save_trace",
    "share_trace",
    "start_recording",
    "stop_recording",
    "unshare_trace",
    "update_trace",
]
