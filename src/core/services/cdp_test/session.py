"""
Active recording session management.

Manages the lifecycle of a recording session — from injection
to step capture to finalization.

Thread-safe: the recorder POSTs events from a browser thread
while the admin panel reads state from the Flask request thread.

Only ONE recording session can be active at a time.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Recording Session ──────────────────────────────────────────


@dataclass
class RecordingSession:
    """An active recording session."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    target_url: str = ""                # Base URL being recorded
    target_id: str = ""                 # Chrome target ID
    target_ws_url: str = ""             # WebSocket debugger URL
    status: str = "recording"           # "recording" | "paused" | "stopped"
    steps: list[dict] = field(default_factory=list)
    started_at: str = field(default_factory=_now_iso)
    paused_at: str = ""

    _lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False,
    )

    def add_step(self, step_data: dict) -> dict:
        """Thread-safe step addition.

        Returns the enriched step dict (with id and sequence).
        """
        with self._lock:
            step = {
                "id": str(uuid.uuid4()),
                "sequence": len(self.steps),
                **step_data,
            }
            self.steps.append(step)
            return step

    def insert_step_after(self, after_step_id: str, step_data: dict) -> dict:
        """Insert a step after the step with after_step_id.

        If after_step_id is empty or not found, appends to end.
        Renumbers all subsequent steps' sequence values.

        Returns the enriched step dict.
        """
        with self._lock:
            insert_idx = len(self.steps)  # default: append
            if after_step_id:
                for i, s in enumerate(self.steps):
                    if s.get("id") == after_step_id:
                        insert_idx = i + 1
                        break

            step = {
                "id": str(uuid.uuid4()),
                "sequence": insert_idx,
                **step_data,
            }
            self.steps.insert(insert_idx, step)

            # Renumber subsequent steps
            for j in range(insert_idx + 1, len(self.steps)):
                self.steps[j]["sequence"] = j

            return step

    def modify_step(self, step_id: str, updates: dict) -> dict | None:
        """Modify an existing step's fields in-place.

        Finds the step by ID and applies the key/value pairs from
        updates to it.  Used by I/O configuration to change a step's
        value (input binding) or set export_as (output export) without
        inserting a new step.

        Returns the modified step dict, or None if step_id not found.
        """
        with self._lock:
            for step in self.steps:
                if step.get("id") == step_id:
                    step.update(updates)
                    return step
            return None

    def clear_steps(self) -> None:
        """Clear all recorded steps (restart)."""
        with self._lock:
            self.steps.clear()

    def get_steps(self) -> list[dict]:
        """Thread-safe copy of current steps."""
        with self._lock:
            return list(self.steps)

    @property
    def step_count(self) -> int:
        with self._lock:
            return len(self.steps)


# ── Module-level singleton ─────────────────────────────────────

_active_session: RecordingSession | None = None
_session_lock = threading.Lock()


def get_active_session() -> RecordingSession | None:
    """Return the active recording session, or None."""
    with _session_lock:
        return _active_session


def create_session(
    target_url: str,
    target_id: str,
    target_ws_url: str,
) -> RecordingSession:
    """Create a new recording session.

    Ends any existing session first.

    Args:
        target_url: The URL being recorded (e.g. http://localhost:3000)
        target_id: Chrome CDP target ID
        target_ws_url: WebSocket debugger URL for the target

    Returns:
        The new RecordingSession.
    """
    global _active_session
    with _session_lock:
        if _active_session is not None:
            logger.warning(
                "Ending existing session %s to start new one",
                _active_session.id,
            )
            _active_session.status = "stopped"

        session = RecordingSession(
            target_url=target_url,
            target_id=target_id,
            target_ws_url=target_ws_url,
        )
        _active_session = session
        logger.info(
            "Recording session created: %s → %s",
            session.id, target_url,
        )
        return session


def end_session() -> RecordingSession | None:
    """End the active session and return it.

    Returns None if no session was active.
    """
    global _active_session
    with _session_lock:
        session = _active_session
        if session is not None:
            session.status = "stopped"
            _active_session = None
            logger.info(
                "Recording session ended: %s (%d steps)",
                session.id, session.step_count,
            )
        return session
