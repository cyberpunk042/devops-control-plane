"""
Chat routes — thread management, messaging, @-references, sync.

Blueprint: chat_bp
Prefix: /api

Sub-modules:
    threads.py   — list, create, delete threads
    messages.py  — list, send, delete, update, move messages
    refs.py      — @-reference resolution and autocomplete
    sync.py      — push/pull sync and polling
"""

from __future__ import annotations

from flask import Blueprint

chat_bp = Blueprint("chat", __name__)

from . import threads, messages, refs, sync  # noqa: E402, F401
