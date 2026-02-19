"""
Trace recorder — start/stop recording, save traces, generate summaries.

Uses the event bus queue listener mechanism to capture events during
recording, stores traces on the ledger branch.
"""

from __future__ import annotations

import json
import logging
import queue
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.services.ledger.worktree import (
    current_head_sha,
    current_user,
    ensure_worktree,
    ledger_add_and_commit,
    worktree_path,
)
from src.core.services.trace.models import SessionTrace, TraceEvent

try:
    from src.core.services.event_bus import bus as _bus
except Exception:  # pragma: no cover
    _bus = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Event types to ignore — noise that adds no value to traces
_NOISE_TYPES = frozenset({
    "sys:heartbeat",
    "state:stale",
    "sys:ready",
    "state:snapshot",
})

# ═══════════════════════════════════════════════════════════════════════
#  Active recordings registry
# ═══════════════════════════════════════════════════════════════════════

# Maps trace_id → recording state
_active: dict[str, "_Recording"] = {}


class _Recording:
    """State for an active recording session."""

    __slots__ = ("trace_id", "name", "classification", "user",
                 "code_ref", "project_root", "started_at", "q")

    def __init__(
        self,
        trace_id: str,
        project_root: Path,
        name: str,
        classification: str,
        user: str,
        code_ref: str,
    ) -> None:
        self.trace_id = trace_id
        self.project_root = project_root
        self.name = name
        self.classification = classification
        self.user = user
        self.code_ref = code_ref
        self.started_at = datetime.now(UTC).isoformat()
        self.q: queue.Queue[dict] = queue.Queue(maxsize=1000)


# ═══════════════════════════════════════════════════════════════════════
#  Event conversion
# ═══════════════════════════════════════════════════════════════════════


def _bus_event_to_trace_event(event: dict) -> TraceEvent | None:
    """Convert a bus event dict to a TraceEvent, or None if noise."""
    event_type = event.get("type", "")
    if event_type in _NOISE_TYPES:
        return None

    duration_ms = 0
    if "duration_s" in event:
        try:
            duration_ms = int(float(event["duration_s"]) * 1000)
        except (ValueError, TypeError):
            pass

    result = ""
    data = event.get("data", {})
    if "error" in event:
        result = "failed"
    elif "status" in data:
        result = data["status"]
    elif event_type.endswith(":done"):
        result = "ok"

    return TraceEvent(
        seq=event.get("seq", 0),
        ts=datetime.fromtimestamp(event.get("ts", 0), tz=UTC).isoformat()
            if event.get("ts") else datetime.now(UTC).isoformat(),
        type=event_type,
        key=event.get("key", ""),
        target=data.get("target", event.get("key", "")),
        result=result,
        duration_ms=duration_ms,
        detail={k: v for k, v in data.items()
                if k not in ("target", "status")} if data else {},
    )


# ═══════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════


def start_recording(
    project_root: Path,
    *,
    name: str = "",
    classification: str = "",
    user: str = "",
) -> str:
    """Start recording. Returns trace_id.

    Registers a queue listener on the event bus to capture all events
    published during the recording.

    Args:
        project_root: Repository root.
        name: Human-readable name for this trace.
        classification: Category (deployment, debugging, config, exploration).
        user: Author (defaults to git config user.name).

    Returns:
        The trace_id for this recording.
    """
    if not user:
        user = current_user(project_root)

    code_ref = current_head_sha(project_root) or ""

    trace = SessionTrace(
        name=name,
        classification=classification,
        user=user,
        code_ref=code_ref,
    )
    trace.ensure_id()

    rec = _Recording(
        trace_id=trace.trace_id,
        project_root=project_root,
        name=name,
        classification=classification,
        user=user,
        code_ref=code_ref,
    )

    # Register queue listener on the bus
    if _bus is not None:
        _bus.add_listener(rec.q)

    _active[trace.trace_id] = rec

    # Publish trace:start
    if _bus is not None:
        try:
            _bus.publish(
                "trace:start",
                key=trace.trace_id,
                data={
                    "name": name,
                    "classification": classification,
                    "user": user,
                },
            )
        except Exception:
            pass

    logger.info("Recording started: %s (%s)", trace.trace_id, name or "unnamed")
    return trace.trace_id


def stop_recording(
    trace_id: str,
    *,
    auto_post: bool = True,
) -> SessionTrace | None:
    """Stop recording. Drains the queue, generates auto-summary.

    Args:
        trace_id: The trace_id from start_recording.
        auto_post: If True (default), auto-post summary to chat.

    Returns:
        The complete SessionTrace (not yet saved), or None if not found.
    """
    rec = _active.pop(trace_id, None)
    if rec is None:
        logger.warning("No active recording for %s", trace_id)
        return None

    # Unregister from bus
    if _bus is not None:
        _bus.remove_listener(rec.q)

    # Drain the queue → TraceEvent list
    events: list[TraceEvent] = []
    while True:
        try:
            raw = rec.q.get_nowait()
            te = _bus_event_to_trace_event(raw)
            if te is not None:
                events.append(te)
        except queue.Empty:
            break

    ended_at = datetime.now(UTC).isoformat()
    started_ts = rec.started_at
    duration_s = 0.0
    try:
        start_dt = datetime.fromisoformat(started_ts)
        end_dt = datetime.fromisoformat(ended_at)
        duration_s = round((end_dt - start_dt).total_seconds(), 2)
    except (ValueError, TypeError):
        pass

    summary = generate_summary(events)

    trace = SessionTrace(
        trace_id=trace_id,
        name=rec.name,
        classification=rec.classification,
        started_at=started_ts,
        ended_at=ended_at,
        user=rec.user,
        code_ref=rec.code_ref,
        events=events,
        auto_summary=summary,
        event_count=len(events),
        duration_s=duration_s,
    )

    # Publish trace:stop
    if _bus is not None:
        try:
            _bus.publish(
                "trace:stop",
                key=trace_id,
                data={
                    "name": rec.name,
                    "event_count": len(events),
                    "duration_s": duration_s,
                    "summary": summary,
                },
            )
        except Exception:
            pass

    # Auto-post trace summary to chat
    if auto_post:
        try:
            post_trace_to_chat(rec.project_root, trace)
        except Exception as e:
            # Chat failure must never break trace recording
            logger.warning("Failed to auto-post trace to chat: %s", e)

    logger.info(
        "Recording stopped: %s (%d events, %.1fs)",
        trace_id, len(events), duration_s,
    )
    return trace


def post_trace_to_chat(
    project_root: Path,
    trace: SessionTrace,
    *,
    thread_id: str | None = None,
) -> None:
    """Post a trace summary as a chat message.

    Creates a chat message with source='trace', linking the trace_id
    and referencing it via @trace:.

    Args:
        project_root: Repository root.
        trace: The completed SessionTrace.
        thread_id: Optional thread to post to (defaults to general).
    """
    try:
        from src.core.services.chat.chat_ops import send_message
    except ImportError:
        logger.debug("chat_ops not available, skipping trace auto-post")
        return

    # Build the message text
    name_part = f"**{trace.name}** " if trace.name else ""
    classification_part = f"[{trace.classification}] " if trace.classification else ""
    text = (
        f"📋 Trace recorded: {name_part}{classification_part}"
        f"@trace:{trace.trace_id}\n"
        f"{trace.auto_summary}"
    )

    send_message(
        project_root,
        text,
        user=trace.user,
        thread_id=thread_id,
        trace_id=trace.trace_id,
        source="trace",
    )

    logger.debug("Trace %s auto-posted to chat", trace.trace_id)


def save_trace(project_root: Path, trace: SessionTrace) -> None:
    """Save trace to ledger worktree (local files only, no git commit).

    Traces are local-first. Call share_trace() to commit and push to git.

    Args:
        project_root: Repository root.
        trace: The SessionTrace to save.
    """
    ensure_worktree(project_root)

    trace_dir = _traces_dir(project_root) / trace.trace_id
    trace_dir.mkdir(parents=True, exist_ok=True)

    # Write trace.json (metadata without events to keep it small)
    meta = trace.model_dump(mode="json", exclude={"events"})
    trace_file = trace_dir / "trace.json"
    trace_file.write_text(
        json.dumps(meta, indent=2) + "\n",
        encoding="utf-8",
    )

    # Write events.jsonl
    if trace.events:
        events_file = trace_dir / "events.jsonl"
        with events_file.open("w", encoding="utf-8") as f:
            for event in trace.events:
                f.write(event.model_dump_json() + "\n")

    logger.info("Trace saved (local): %s", trace.trace_id)


def share_trace(project_root: Path, trace_id: str) -> bool:
    """Share a trace — commit to git and mark as shared.

    Args:
        project_root: Repository root.
        trace_id: The trace to share.

    Returns:
        True if shared successfully, False if trace not found.
    """
    trace = get_trace(project_root, trace_id)
    if trace is None:
        logger.warning("Cannot share trace %s: not found", trace_id)
        return False

    if trace.shared:
        logger.debug("Trace %s already shared", trace_id)
        return True

    # Update shared flag and re-write trace.json
    trace.shared = True
    trace_dir = _traces_dir(project_root) / trace_id
    trace_file = trace_dir / "trace.json"
    meta = trace.model_dump(mode="json", exclude={"events"})
    trace_file.write_text(
        json.dumps(meta, indent=2) + "\n",
        encoding="utf-8",
    )

    # Commit to ledger branch
    rel_paths = [f"ledger/traces/{trace_id}/trace.json"]
    events_file = trace_dir / "events.jsonl"
    if events_file.is_file():
        rel_paths.append(f"ledger/traces/{trace_id}/events.jsonl")

    ledger_add_and_commit(
        project_root,
        paths=rel_paths,
        message=f"trace(shared): {trace_id} ({trace.event_count} events)",
    )

    logger.info("Trace shared: %s", trace_id)
    return True


def unshare_trace(project_root: Path, trace_id: str) -> bool:
    """Mark a trace as unshared (local-only).

    Note: this does NOT remove existing git history — it only flips the
    shared flag so future syncs won't include it.

    Args:
        project_root: Repository root.
        trace_id: The trace to unshare.

    Returns:
        True if updated, False if not found.
    """
    trace = get_trace(project_root, trace_id)
    if trace is None:
        return False

    trace.shared = False
    _rewrite_trace_json(project_root, trace)

    # Commit the flag change so it syncs to other machines
    ledger_add_and_commit(
        project_root,
        paths=[f"ledger/traces/{trace_id}/trace.json"],
        message=f"trace(unshared): {trace_id}",
    )

    logger.info("Trace unshared: %s", trace_id)
    return True


def update_trace(
    project_root: Path,
    trace_id: str,
    *,
    name: str | None = None,
    classification: str | None = None,
) -> bool:
    """Update trace metadata (name, classification).

    Args:
        project_root: Repository root.
        trace_id: The trace to update.
        name: New name (None = keep current).
        classification: New classification (None = keep current).

    Returns:
        True if updated, False if not found.
    """
    trace = get_trace(project_root, trace_id)
    if trace is None:
        return False

    if name is not None:
        trace.name = name
    if classification is not None:
        trace.classification = classification

    _rewrite_trace_json(project_root, trace)
    logger.info("Trace updated: %s (name=%s)", trace_id, trace.name)
    return True


def _rewrite_trace_json(project_root: Path, trace: SessionTrace) -> None:
    """Re-write trace.json for an existing trace."""
    trace_dir = _traces_dir(project_root) / trace.trace_id
    trace_file = trace_dir / "trace.json"
    meta = trace.model_dump(mode="json", exclude={"events"})
    trace_file.write_text(
        json.dumps(meta, indent=2) + "\n",
        encoding="utf-8",
    )

def generate_summary(events: list[TraceEvent]) -> str:
    """Generate a one-line summary from trace events (deterministic).

    Counts events by type domain and formats a human-readable string.
    Example: "3 cache refreshes, 1 vault unlock, 2 git ops — 12 events total"
    """
    if not events:
        return "empty trace"

    # Count by domain (first part of type before ":")
    domain_counts: Counter[str] = Counter()
    for e in events:
        domain = e.type.split(":")[0] if ":" in e.type else e.type
        domain_counts[domain] += 1

    # Human-readable labels
    _LABELS: dict[str, tuple[str, str]] = {
        "cache": ("cache refresh", "cache refreshes"),
        "vault": ("vault op", "vault ops"),
        "git": ("git op", "git ops"),
        "ledger": ("ledger write", "ledger writes"),
        "chat": ("chat message", "chat messages"),
        "trace": ("trace event", "trace events"),
    }

    parts: list[str] = []
    for domain, count in domain_counts.most_common():
        singular, plural = _LABELS.get(domain, (f"{domain} event", f"{domain} events"))
        label = singular if count == 1 else plural
        parts.append(f"{count} {label}")

    summary = ", ".join(parts)

    # Total duration from events
    total_ms = sum(e.duration_ms for e in events)
    if total_ms > 0:
        if total_ms > 60_000:
            summary += f" — {total_ms / 60_000:.1f}min total"
        elif total_ms > 1000:
            summary += f" — {total_ms / 1000:.1f}s total"
        else:
            summary += f" — {total_ms}ms total"

    return summary


def list_traces(project_root: Path, n: int = 20) -> list[SessionTrace]:
    """List saved traces from ledger branch, newest-first.

    Args:
        project_root: Repository root.
        n: Maximum number of traces to return.

    Returns:
        List of SessionTrace (without events loaded — use get_trace_events for those).
    """
    traces_root = _traces_dir(project_root)
    if not traces_root.is_dir():
        return []

    traces: list[SessionTrace] = []
    try:
        for td in sorted(traces_root.iterdir(), reverse=True):
            if not td.is_dir():
                continue
            trace_file = td / "trace.json"
            if not trace_file.is_file():
                continue
            try:
                data = json.loads(trace_file.read_text(encoding="utf-8"))
                traces.append(SessionTrace.model_validate(data))
            except Exception as e:
                logger.warning("Skipping corrupt trace %s: %s", td.name, e)

            if len(traces) >= n:
                break
    except OSError as e:
        logger.error("Failed to list traces: %s", e)

    # Sort by started_at descending (directory sort may not match timestamp order)
    traces.sort(key=lambda t: t.started_at, reverse=True)
    return traces[:n]


def get_trace(project_root: Path, trace_id: str) -> SessionTrace | None:
    """Load a single trace by ID.

    Returns None if not found.
    """
    trace_file = _traces_dir(project_root) / trace_id / "trace.json"
    if not trace_file.is_file():
        return None
    try:
        data = json.loads(trace_file.read_text(encoding="utf-8"))
        return SessionTrace.model_validate(data)
    except Exception as e:
        logger.error("Failed to load trace %s: %s", trace_id, e)
        return None


def get_trace_events(project_root: Path, trace_id: str) -> list[dict]:
    """Load trace events from events.jsonl.

    Returns a list of raw dicts (not TraceEvent models — keeps it flexible).
    """
    events_file = _traces_dir(project_root) / trace_id / "events.jsonl"
    if not events_file.is_file():
        return []

    events: list[dict] = []
    try:
        for line in events_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.warning("Skipping corrupt event line: %s", e)
    except OSError as e:
        logger.error("Failed to read trace events for %s: %s", trace_id, e)

    return events


def active_recordings() -> list[str]:
    """Return trace_ids of all active recordings."""
    return list(_active.keys())


# ═══════════════════════════════════════════════════════════════════════
#  Internal helpers
# ═══════════════════════════════════════════════════════════════════════


def _traces_dir(project_root: Path) -> Path:
    """Return the traces directory on the ledger branch."""
    return worktree_path(project_root) / "ledger" / "traces"
