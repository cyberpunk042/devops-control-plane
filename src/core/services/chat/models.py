"""
Chat models — data shapes for messages and threads.

Pure Pydantic models with no I/O.
"""

from __future__ import annotations

import secrets
import socket
import string
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _hostname() -> str:
    return socket.gethostname()


def _make_msg_id() -> str:
    """Generate a unique message ID: msg_<timestamp>_<4char>."""
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    return f"msg_{ts}_{suffix}"


def _make_thread_id() -> str:
    """Generate a unique thread ID: thread_<timestamp>_<4char>."""
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    return f"thread_{ts}_{suffix}"


class MessageFlags(BaseModel):
    """Per-message control flags."""

    publish: bool = False       # eligible for public rendering
    encrypted: bool = False     # text field is ENC:v1:...


class ChatMessage(BaseModel):
    """A single chat message.

    Stored as:
      - JSONL line in git notes (run-attached messages)
      - JSONL line in .ledger/chat/threads/<id>/messages.jsonl (thread messages)
    """

    id: str = ""
    ts: str = Field(default_factory=_now_iso)
    user: str = ""
    hostname: str = ""
    text: str = ""
    thread_id: str | None = None
    run_id: str | None = None
    trace_id: str | None = None                    # linked trace recording
    refs: list[str] = Field(default_factory=list)  # @-references found in text
    source: Literal["manual", "trace", "system"] = "manual"
    flags: MessageFlags = Field(default_factory=MessageFlags)

    def ensure_id(self) -> str:
        """Ensure message id is set, generating one if empty."""
        if not self.id:
            self.id = _make_msg_id()
        return self.id

    def to_jsonl(self) -> str:
        """Serialize to a single JSONL line (no trailing newline)."""
        return self.model_dump_json()

    @classmethod
    def from_jsonl(cls, line: str) -> ChatMessage:
        """Parse a ChatMessage from a JSONL line."""
        return cls.model_validate_json(line.strip())


class Thread(BaseModel):
    """A conversation thread.

    Stored as thread.json in .ledger/chat/threads/<thread_id>/.
    """

    thread_id: str = ""
    title: str = ""
    created_at: str = Field(default_factory=_now_iso)
    created_by: str = ""
    anchor_run: str | None = None
    tags: list[str] = Field(default_factory=list)

    def ensure_id(self) -> str:
        """Ensure thread_id is set, generating one if empty."""
        if not self.thread_id:
            self.thread_id = _make_thread_id()
        return self.thread_id
