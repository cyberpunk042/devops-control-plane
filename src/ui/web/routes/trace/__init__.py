"""
Trace routes — session tracing for the Debugging tab.

Blueprint: trace_bp
Prefix: /api

Sub-modules:
    recording.py — start, stop, active recordings
    queries.py   — list, get, events
    sharing.py   — share, unshare, update, delete
"""

from __future__ import annotations

from flask import Blueprint

trace_bp = Blueprint("trace", __name__)

from . import recording, queries, sharing  # noqa: E402, F401
