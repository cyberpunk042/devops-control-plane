"""
Tests for Session Tracing — models, recorder, storage, summary.

These tests create isolated git repos in tmp directories and exercise
the full trace recording workflow.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from src.core.services.trace.models import SessionTrace, TraceEvent


# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════


def _init_test_repo(path: Path) -> Path:
    """Create a minimal git repo with one commit."""
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Trace Tester"],
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "trace@test.com"],
        capture_output=True, check=True,
    )
    readme = path / "README.md"
    readme.write_text("# Trace Test\n")
    subprocess.run(["git", "-C", str(path), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "initial"],
        capture_output=True, check=True,
    )
    return path


# ═══════════════════════════════════════════════════════════════════════
#  Model Tests
# ═══════════════════════════════════════════════════════════════════════


class TestTraceModels:
    """Tests for TraceEvent and SessionTrace models."""

    def test_trace_event_defaults(self):
        te = TraceEvent()
        assert te.seq == 0
        assert te.type == ""
        assert te.duration_ms == 0
        assert te.detail == {}

    def test_session_trace_defaults(self):
        st = SessionTrace()
        assert st.trace_id == ""
        assert st.name == ""
        assert st.started_at != ""
        assert st.events == []
        assert st.event_count == 0

    def test_ensure_id(self):
        st = SessionTrace()
        tid = st.ensure_id()
        assert tid.startswith("trace_")
        assert len(tid) > 15
        assert st.ensure_id() == tid  # idempotent

    def test_trace_event_fields(self):
        te = TraceEvent(
            seq=1,
            ts="2026-01-01T00:00:00Z",
            type="cache:done",
            key="docker",
            result="ok",
            duration_ms=1500,
            detail={"age_s": 42},
        )
        assert te.type == "cache:done"
        assert te.key == "docker"
        assert te.duration_ms == 1500


# ═══════════════════════════════════════════════════════════════════════
#  Summary Tests
# ═══════════════════════════════════════════════════════════════════════


class TestSummary:
    """Tests for deterministic summary generation."""

    def test_empty_events(self):
        from src.core.services.trace.trace_recorder import generate_summary
        assert generate_summary([]) == "empty trace"

    def test_single_domain(self):
        from src.core.services.trace.trace_recorder import generate_summary
        events = [
            TraceEvent(type="cache:done", result="ok"),
            TraceEvent(type="cache:miss", result="ok"),
            TraceEvent(type="cache:hit", result="ok"),
        ]
        summary = generate_summary(events)
        assert "3 cache refreshes" in summary

    def test_multiple_domains(self):
        from src.core.services.trace.trace_recorder import generate_summary
        events = [
            TraceEvent(type="cache:done", result="ok"),
            TraceEvent(type="vault:unlock", result="ok"),
            TraceEvent(type="vault:lock", result="ok"),
            TraceEvent(type="git:push", result="ok"),
        ]
        summary = generate_summary(events)
        assert "vault" in summary
        assert "cache" in summary
        assert "git" in summary

    def test_duration_in_summary(self):
        from src.core.services.trace.trace_recorder import generate_summary
        events = [
            TraceEvent(type="cache:done", duration_ms=5000),
            TraceEvent(type="cache:miss", duration_ms=3000),
        ]
        summary = generate_summary(events)
        assert "8.0s total" in summary

    def test_singular_label(self):
        from src.core.services.trace.trace_recorder import generate_summary
        events = [TraceEvent(type="cache:done")]
        summary = generate_summary(events)
        assert "1 cache refresh" in summary
        assert "refreshes" not in summary

    def test_unknown_domain(self):
        from src.core.services.trace.trace_recorder import generate_summary
        events = [TraceEvent(type="custom:something")]
        summary = generate_summary(events)
        assert "1 custom event" in summary


# ═══════════════════════════════════════════════════════════════════════
#  Recorder Tests
# ═══════════════════════════════════════════════════════════════════════


class TestRecorder:
    """Tests for start/stop recording lifecycle."""

    def test_start_stop_basic(self, tmp_path: Path):
        """Start and stop a recording — verify trace structure."""
        from src.core.services.trace.trace_recorder import start_recording, stop_recording
        repo = _init_test_repo(tmp_path / "repo")

        tid = start_recording(repo, name="Test trace", classification="debugging")
        assert tid.startswith("trace_")

        trace = stop_recording(tid)
        assert trace is not None
        assert trace.trace_id == tid
        assert trace.name == "Test trace"
        assert trace.classification == "debugging"
        assert trace.user == "Trace Tester"
        assert trace.ended_at != ""
        assert trace.duration_s >= 0

    def test_captures_bus_events(self, tmp_path: Path):
        """Events published to the bus during recording are captured."""
        from src.core.services.event_bus import bus
        from src.core.services.trace.trace_recorder import start_recording, stop_recording
        repo = _init_test_repo(tmp_path / "repo")

        tid = start_recording(repo, name="Bus capture test")

        # Publish some events while recording
        bus.publish("cache:done", key="docker", data={"status": "ok"}, duration_s=2.5)
        bus.publish("vault:unlock", key="main", data={"target": ".env"})
        bus.publish("git:push", key="origin")

        trace = stop_recording(tid)
        assert trace is not None
        # Should have at least the 3 events we published + trace:start
        # (trace:start is published by start_recording itself)
        event_types = [e.type for e in trace.events]
        assert "cache:done" in event_types
        assert "vault:unlock" in event_types
        assert "git:push" in event_types

    def test_filters_noise_events(self, tmp_path: Path):
        """Noise events (heartbeats, stale) are filtered out."""
        from src.core.services.event_bus import bus
        from src.core.services.trace.trace_recorder import start_recording, stop_recording
        repo = _init_test_repo(tmp_path / "repo")

        tid = start_recording(repo)
        bus.publish("sys:heartbeat")
        bus.publish("state:stale", key="docker")
        bus.publish("cache:done", key="docker")
        trace = stop_recording(tid)

        event_types = [e.type for e in trace.events]
        assert "sys:heartbeat" not in event_types
        assert "state:stale" not in event_types
        assert "cache:done" in event_types

    def test_concurrent_recordings(self, tmp_path: Path):
        """Multiple recordings can run concurrently with isolation."""
        from src.core.services.event_bus import bus
        from src.core.services.trace.trace_recorder import start_recording, stop_recording
        repo = _init_test_repo(tmp_path / "repo")

        tid1 = start_recording(repo, name="Recording 1")
        bus.publish("cache:done", key="docker")

        tid2 = start_recording(repo, name="Recording 2")
        bus.publish("vault:unlock", key="main")

        # Stop recording 1 — it should have cache:done and vault:unlock
        trace1 = stop_recording(tid1)
        # Stop recording 2 — it should have only vault:unlock
        trace2 = stop_recording(tid2)

        types1 = [e.type for e in trace1.events]
        types2 = [e.type for e in trace2.events]

        assert "cache:done" in types1
        assert "vault:unlock" in types1  # both events

        # Recording 2 started after cache:done, so it might not have it
        assert "vault:unlock" in types2

    def test_stop_nonexistent_returns_none(self, tmp_path: Path):
        from src.core.services.trace.trace_recorder import stop_recording
        result = stop_recording("nonexistent-trace-id")
        assert result is None

    def test_auto_summary_generated(self, tmp_path: Path):
        """Auto-summary is generated on stop."""
        from src.core.services.event_bus import bus
        from src.core.services.trace.trace_recorder import start_recording, stop_recording
        repo = _init_test_repo(tmp_path / "repo")

        tid = start_recording(repo)
        bus.publish("cache:done", key="docker", duration_s=2.0)
        bus.publish("cache:done", key="testing", duration_s=1.5)
        trace = stop_recording(tid)

        assert trace.auto_summary != ""
        assert trace.auto_summary != "empty trace"

    def test_active_recordings(self, tmp_path: Path):
        """active_recordings() returns currently recording trace_ids."""
        from src.core.services.trace.trace_recorder import (
            active_recordings,
            start_recording,
            stop_recording,
        )
        repo = _init_test_repo(tmp_path / "repo")

        tid = start_recording(repo)
        assert tid in active_recordings()

        stop_recording(tid)
        assert tid not in active_recordings()


# ═══════════════════════════════════════════════════════════════════════
#  Storage Tests
# ═══════════════════════════════════════════════════════════════════════


class TestTraceStorage:
    """Tests for save/list/get trace operations."""

    def test_save_and_get(self, tmp_path: Path):
        """Save a trace and retrieve it."""
        from src.core.services.event_bus import bus
        from src.core.services.trace.trace_recorder import (
            get_trace,
            save_trace,
            start_recording,
            stop_recording,
        )
        repo = _init_test_repo(tmp_path / "repo")

        tid = start_recording(repo, name="Save test")
        bus.publish("cache:done", key="docker")
        trace = stop_recording(tid)
        assert trace is not None

        save_trace(repo, trace)

        # Get it back
        loaded = get_trace(repo, tid)
        assert loaded is not None
        assert loaded.trace_id == tid
        assert loaded.name == "Save test"
        assert loaded.event_count == trace.event_count

    def test_save_and_list(self, tmp_path: Path):
        """Save multiple traces and list them."""
        from src.core.services.event_bus import bus
        from src.core.services.trace.trace_recorder import (
            list_traces,
            save_trace,
            start_recording,
            stop_recording,
        )
        repo = _init_test_repo(tmp_path / "repo")

        # Record and save trace 1
        tid1 = start_recording(repo, name="Trace 1")
        bus.publish("cache:done", key="docker")
        t1 = stop_recording(tid1)
        save_trace(repo, t1)

        # Record and save trace 2
        tid2 = start_recording(repo, name="Trace 2")
        bus.publish("vault:unlock", key="main")
        t2 = stop_recording(tid2)
        save_trace(repo, t2)

        # List
        traces = list_traces(repo)
        assert len(traces) >= 2
        ids = [t.trace_id for t in traces]
        assert tid1 in ids
        assert tid2 in ids

    def test_get_trace_events(self, tmp_path: Path):
        """Retrieve individual trace events."""
        from src.core.services.event_bus import bus
        from src.core.services.trace.trace_recorder import (
            get_trace_events,
            save_trace,
            start_recording,
            stop_recording,
        )
        repo = _init_test_repo(tmp_path / "repo")

        tid = start_recording(repo)
        bus.publish("cache:done", key="docker", duration_s=1.5)
        trace = stop_recording(tid)
        save_trace(repo, trace)

        events = get_trace_events(repo, tid)
        assert len(events) >= 1
        # Events are dicts
        assert any(e.get("type") == "cache:done" for e in events)

    def test_get_nonexistent_trace(self, tmp_path: Path):
        """get_trace returns None for nonexistent trace."""
        from src.core.services.trace.trace_recorder import get_trace
        repo = _init_test_repo(tmp_path / "repo")
        assert get_trace(repo, "nonexistent") is None

    def test_list_traces_limit(self, tmp_path: Path):
        """list_traces respects the n limit."""
        from src.core.services.trace.trace_recorder import (
            list_traces,
            save_trace,
            start_recording,
            stop_recording,
        )
        repo = _init_test_repo(tmp_path / "repo")

        for i in range(5):
            tid = start_recording(repo, name=f"Trace {i}")
            trace = stop_recording(tid)
            save_trace(repo, trace)

        traces = list_traces(repo, n=3)
        assert len(traces) == 3


# ═══════════════════════════════════════════════════════════════════════
#  Event Bus Integration
# ═══════════════════════════════════════════════════════════════════════


class TestTraceEventBus:
    """Tests that trace operations publish to the event bus."""

    def test_start_publishes_event(self, tmp_path: Path):
        """start_recording publishes a trace:start event."""
        from src.core.services.event_bus import bus
        from src.core.services.trace.trace_recorder import start_recording, stop_recording
        repo = _init_test_repo(tmp_path / "repo")

        initial_seq = bus.seq
        tid = start_recording(repo, name="Bus test")

        found = False
        with bus._lock:
            for event in bus._buffer:
                if (event.get("type") == "trace:start"
                        and event.get("key") == tid
                        and event.get("seq", 0) > initial_seq):
                    found = True
                    assert event["data"]["name"] == "Bus test"
                    break
        assert found, "trace:start event not found"

        stop_recording(tid)

    def test_stop_publishes_event(self, tmp_path: Path):
        """stop_recording publishes a trace:stop event."""
        from src.core.services.event_bus import bus
        from src.core.services.trace.trace_recorder import start_recording, stop_recording
        repo = _init_test_repo(tmp_path / "repo")

        tid = start_recording(repo, name="Stop bus test")
        pre_stop_seq = bus.seq
        stop_recording(tid)

        found = False
        with bus._lock:
            for event in bus._buffer:
                if (event.get("type") == "trace:stop"
                        and event.get("key") == tid
                        and event.get("seq", 0) > pre_stop_seq):
                    found = True
                    break
        assert found, "trace:stop event not found"


# ═══════════════════════════════════════════════════════════════════════
#  EventBus Listener Tests
# ═══════════════════════════════════════════════════════════════════════


class TestBusListeners:
    """Tests for add_listener / remove_listener on EventBus."""

    def test_add_and_receive(self):
        """Added listener receives published events."""
        import queue as q_mod
        from src.core.services.event_bus import bus

        listener = q_mod.Queue(maxsize=100)
        bus.add_listener(listener)

        try:
            bus.publish("test:listener", key="hello")
            event = listener.get(timeout=1)
            assert event["type"] == "test:listener"
            assert event["key"] == "hello"
        finally:
            bus.remove_listener(listener)

    def test_remove_stops_delivery(self):
        """Removed listener stops receiving events."""
        import queue as q_mod
        from src.core.services.event_bus import bus

        listener = q_mod.Queue(maxsize=100)
        bus.add_listener(listener)
        bus.remove_listener(listener)

        bus.publish("test:after_remove", key="x")
        assert listener.empty()

    def test_duplicate_add_is_idempotent(self):
        """Adding the same listener twice doesn't duplicate it."""
        import queue as q_mod
        from src.core.services.event_bus import bus

        listener = q_mod.Queue(maxsize=100)
        bus.add_listener(listener)
        bus.add_listener(listener)  # duplicate

        try:
            initial_count = bus.subscriber_count
            bus.publish("test:dup", key="y")
            # Should only get ONE event, not two
            event = listener.get(timeout=1)
            assert event["type"] == "test:dup"
            assert listener.empty()  # no duplicate
        finally:
            bus.remove_listener(listener)


# ═══════════════════════════════════════════════════════════════════════
#  audit_refs Field on SessionTrace
# ═══════════════════════════════════════════════════════════════════════


class TestAuditRefsField:
    """Tests for audit_refs field on SessionTrace (Gap 2 from spec)."""

    def test_audit_refs_defaults_empty(self):
        st = SessionTrace()
        assert st.audit_refs == []

    def test_audit_refs_roundtrip(self):
        st = SessionTrace(
            trace_id="trace_test",
            audit_refs=["op_123", "op_456"],
        )
        data = st.model_dump(mode="json")
        restored = SessionTrace.model_validate(data)
        assert restored.audit_refs == ["op_123", "op_456"]

    def test_audit_refs_in_json(self):
        st = SessionTrace(
            trace_id="trace_test",
            audit_refs=["op_abc"],
        )
        data = st.model_dump(mode="json")
        assert "audit_refs" in data
        assert data["audit_refs"] == ["op_abc"]


# ═══════════════════════════════════════════════════════════════════════
#  Trace → Chat Auto-Post
# ═══════════════════════════════════════════════════════════════════════


class TestTraceAutoPost:
    """Tests for automatic chat message posting when a trace stops."""

    def test_auto_post_creates_chat_message(self, tmp_path: Path):
        """stop_recording with auto_post=True creates a chat message."""
        from src.core.services.event_bus import bus
        from src.core.services.trace.trace_recorder import start_recording, stop_recording

        repo = _init_test_repo(tmp_path / "repo")

        tid = start_recording(repo, name="Deploy v1.2", classification="deployment")
        bus.publish("cache:done", key="docker", duration_s=1.0)
        trace = stop_recording(tid, auto_post=True)

        assert trace is not None

        # Check that a chat message was created in the general thread
        from src.core.services.chat.chat_ops import list_threads

        threads = list_threads(repo)
        general = next((t for t in threads if t.title == "general"), None)
        if general is not None:
            from src.core.services.chat.chat_ops import list_messages
            messages = list_messages(repo, thread_id=general.thread_id)
            trace_msgs = [m for m in messages if m.source == "trace" and m.trace_id == tid]
            assert len(trace_msgs) >= 1
            msg = trace_msgs[0]
            assert f"@trace:{tid}" in msg.text
            assert msg.trace_id == tid
            assert f"@trace:{tid}" in msg.refs

    def test_auto_post_disabled(self, tmp_path: Path):
        """stop_recording with auto_post=False does NOT create a chat message."""
        from src.core.services.event_bus import bus
        from src.core.services.trace.trace_recorder import start_recording, stop_recording

        repo = _init_test_repo(tmp_path / "repo")

        tid = start_recording(repo, name="Silent trace")
        bus.publish("cache:done", key="docker")
        trace = stop_recording(tid, auto_post=False)

        assert trace is not None

        # No chat messages should exist
        from src.core.services.chat.chat_ops import list_threads
        threads = list_threads(repo)
        assert len(threads) == 0  # No thread was created

    def test_auto_post_includes_trace_name(self, tmp_path: Path):
        """Auto-posted message includes trace name and classification."""
        from src.core.services.event_bus import bus
        from src.core.services.trace.trace_recorder import start_recording, stop_recording

        repo = _init_test_repo(tmp_path / "repo")

        tid = start_recording(repo, name="Config update", classification="config")
        bus.publish("vault:unlock", key="main")
        trace = stop_recording(tid, auto_post=True)

        from src.core.services.chat.chat_ops import list_threads, list_messages
        threads = list_threads(repo)
        general = next((t for t in threads if t.title == "General"), None)
        assert general is not None

        messages = list_messages(repo, thread_id=general.thread_id)
        trace_msgs = [m for m in messages if m.trace_id == tid]
        assert len(trace_msgs) >= 1
        assert "Config update" in trace_msgs[0].text
        assert "[config]" in trace_msgs[0].text

    def test_post_trace_to_chat_explicit(self, tmp_path: Path):
        """post_trace_to_chat can be called explicitly with a thread_id."""
        from src.core.services.chat.chat_ops import create_thread, list_messages
        from src.core.services.trace.trace_recorder import post_trace_to_chat

        repo = _init_test_repo(tmp_path / "repo")

        thread = create_thread(repo, "Deployment log")
        trace = SessionTrace(
            trace_id="trace_manual_test",
            name="Manual deploy",
            classification="deployment",
            user="Trace Tester",
            auto_summary="2 vault ops, 1 git op",
        )

        post_trace_to_chat(repo, trace, thread_id=thread.thread_id)

        messages = list_messages(repo, thread_id=thread.thread_id)
        assert len(messages) >= 1
        msg = messages[0]
        assert msg.trace_id == "trace_manual_test"
        assert msg.source == "trace"
        assert "@trace:trace_manual_test" in msg.text
        assert "Manual deploy" in msg.text

