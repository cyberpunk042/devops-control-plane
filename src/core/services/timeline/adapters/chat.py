"""
ChatAdapter — reads .ledger/chat/threads/.

One timeline entry per event:
  - Thread creation → subtype: thread_created
  - Each message   → subtype: message
  - (Thread deletion is not persisted as a message; handled at delete time)

All events in a thread share chain_id = thread_id.

Sources produced: CHAT (always)
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.services.timeline.adapters._util import iso_to_ts
from src.core.services.timeline.models import (
    Actor,
    ChainRole,
    EntryStatus,
    Locality,
    Source,
    TimelineEntry,
)

logger = logging.getLogger(__name__)

_MAX_SUMMARY_LEN = 120


def _truncate(text: str, max_len: int = _MAX_SUMMARY_LEN) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


class ChatAdapter:
    """Reads .ledger/chat/threads/ and produces TimelineEntry list.

    Uses list_threads() and list_messages() from chat.chat_ops.
    No noise filter on user/trace messages; system noise is dropped.
    """

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    def load(self) -> list[TimelineEntry]:
        """Return one entry per thread creation + one per message."""
        from src.core.services.chat.chat_ops import list_messages, list_threads

        threads = list_threads(self._root)
        result: list[TimelineEntry] = []

        for thread in threads:
            try:
                # Thread creation entry
                creation = self._thread_creation_entry(thread)
                if creation is not None:
                    result.append(creation)
            except Exception as exc:
                logger.warning("chat: skipping thread creation %s: %s", thread.thread_id, exc)

            # Message entries
            try:
                messages = list_messages(
                    self._root, thread_id=thread.thread_id, n=10_000
                )
                for msg in messages:
                    try:
                        entry = self._message_entry(msg, thread.thread_id)
                        if entry is not None:
                            result.append(entry)
                    except Exception as exc:
                        logger.warning("chat: skipping message %s: %s", getattr(msg, "id", "?"), exc)
            except Exception as exc:
                logger.warning("chat: skipping messages for thread %s: %s", thread.thread_id, exc)

        return result

    def _thread_creation_entry(self, thread) -> TimelineEntry | None:
        ts = iso_to_ts(thread.created_at)
        if ts == 0.0:
            return None

        summary = thread.title if thread.title else f"Thread {thread.thread_id}"

        detail: dict = {}
        if thread.created_by:
            detail["created_by"] = thread.created_by
        if thread.anchor_run:
            detail["anchor_run"] = thread.anchor_run
        if thread.tags:
            detail["tags"] = thread.tags

        return TimelineEntry(
            id=f"chat:thread:{thread.thread_id}",
            ts=ts,
            ref=thread.thread_id,
            source=Source.CHAT,
            subtype="thread_created",
            actor=Actor.USER,
            status=EntryStatus.OK,
            severity=None,
            locality=Locality.SHARED,
            env=[],
            modules=[],
            summary=summary,
            detail=detail or None,
            chain_id=thread.thread_id,
            chain_role=ChainRole.ORIGIN,
            chain_parent_ref=None,
        )

    def _message_entry(self, msg, thread_id: str) -> TimelineEntry | None:
        ts = iso_to_ts(msg.ts)
        if ts == 0.0:
            return None

        # Noise filter: drop system heartbeat/ack messages
        if msg.source == "system" and _is_system_noise(msg.text):
            return None

        summary = _truncate(msg.text) if msg.text else "(empty message)"

        detail: dict = {
            "text": msg.text,
            "source": msg.source,
        }
        if msg.user:
            detail["user"] = msg.user
        if msg.refs:
            detail["refs"] = msg.refs
        if msg.run_id:
            detail["run_id"] = msg.run_id
            detail["run_chain"] = msg.run_id  # secondary chain link
        if msg.trace_id:
            detail["trace_id"] = msg.trace_id

        return TimelineEntry(
            id=f"chat:msg:{msg.id}",
            ts=ts,
            ref=msg.id,
            source=Source.CHAT,
            subtype="message",
            actor=Actor.USER,
            status=EntryStatus.OK,
            severity=None,
            locality=Locality.SHARED,
            env=[],
            modules=[],
            summary=summary,
            detail=detail,
            chain_id=thread_id,
            chain_role=ChainRole.STEP,
            chain_parent_ref=thread_id,
            hostname=msg.hostname or None,
        )


def _is_system_noise(text: str) -> bool:
    """Return True for known system noise patterns (heartbeat, sync acks)."""
    lower = text.lower()
    noise_phrases = (
        "heartbeat",
        "sync ack",
        "keepalive",
        "connection confirmed",
        "ping",
    )
    return any(phrase in lower for phrase in noise_phrases)
