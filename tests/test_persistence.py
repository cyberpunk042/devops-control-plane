"""
Tests for persistence — state file and audit ledger.
"""

import json
from pathlib import Path

from src.core.models.state import ProjectState
from src.core.persistence.audit import AuditEntry, AuditWriter
from src.core.persistence.state_file import load_state, save_state


class TestStateFile:
    """Tests for state file persistence."""

    def test_save_and_load(self, tmp_path: Path):
        """State roundtrips through save/load."""
        path = tmp_path / ".state" / "current.json"
        state = ProjectState(project_name="test-project")
        state.set_module_state("api", detected=True, stack="python")
        state.set_adapter_state("docker", available=True, version="24.0")

        save_state(state, path)
        assert path.is_file()

        loaded = load_state(path)
        assert loaded.project_name == "test-project"
        assert loaded.modules["api"].detected is True
        assert loaded.adapters["docker"].version == "24.0"

    def test_load_missing_returns_fresh(self, tmp_path: Path):
        """Missing state file returns a fresh state."""
        path = tmp_path / "nonexistent.json"
        state = load_state(path)
        assert state.project_name == ""
        assert state.modules == {}

    def test_load_corrupt_returns_fresh(self, tmp_path: Path):
        """Corrupt JSON returns a fresh state."""
        path = tmp_path / "corrupt.json"
        path.write_text("not json at all {{{")
        state = load_state(path)
        assert state.project_name == ""

    def test_save_creates_directories(self, tmp_path: Path):
        """Save creates parent directories automatically."""
        path = tmp_path / "deep" / "nested" / "state.json"
        state = ProjectState(project_name="nested-test")
        save_state(state, path)
        assert path.is_file()

    def test_save_is_valid_json(self, tmp_path: Path):
        """Saved file is valid, human-readable JSON."""
        path = tmp_path / "state.json"
        state = ProjectState(project_name="json-test")
        save_state(state, path)

        raw = path.read_text()
        data = json.loads(raw)
        assert data["project_name"] == "json-test"
        assert data["schema_version"] == 1

    def test_save_atomic_no_partial(self, tmp_path: Path):
        """No partial writes are left behind."""
        path = tmp_path / "state.json"
        state = ProjectState(project_name="atomic")
        save_state(state, path)

        # No temp files should remain
        tmp_files = list(tmp_path.glob(".state_*.tmp"))
        assert len(tmp_files) == 0

    def test_save_updates_timestamp(self, tmp_path: Path):
        """Save calls touch(), updating updated_at."""
        path = tmp_path / "state.json"
        state = ProjectState(project_name="ts-test")
        old_ts = state.updated_at
        import time
        time.sleep(0.01)
        save_state(state, path)
        loaded = load_state(path)
        assert loaded.updated_at != old_ts

    def test_sequential_saves(self, tmp_path: Path):
        """Multiple saves to the same file work correctly."""
        path = tmp_path / "state.json"
        state = ProjectState(project_name="v1")
        save_state(state, path)

        state.project_name = "v2"
        state.set_module_state("api", detected=True)
        save_state(state, path)

        loaded = load_state(path)
        assert loaded.project_name == "v2"
        assert "api" in loaded.modules


class TestAuditWriter:
    """Tests for the audit ledger."""

    def test_write_and_read(self, tmp_path: Path):
        writer = AuditWriter(path=tmp_path / "audit.ndjson")
        entry = AuditEntry(
            operation_id="op-001",
            operation_type="detect",
            status="ok",
            actions_total=3,
            actions_succeeded=3,
        )
        writer.write(entry)

        entries = writer.read_all()
        assert len(entries) == 1
        assert entries[0].operation_id == "op-001"
        assert entries[0].status == "ok"

    def test_append_multiple(self, tmp_path: Path):
        writer = AuditWriter(path=tmp_path / "audit.ndjson")
        for i in range(5):
            writer.write(AuditEntry(operation_id=f"op-{i:03d}", operation_type="test"))

        entries = writer.read_all()
        assert len(entries) == 5
        assert entries[0].operation_id == "op-000"
        assert entries[4].operation_id == "op-004"

    def test_read_recent(self, tmp_path: Path):
        writer = AuditWriter(path=tmp_path / "audit.ndjson")
        for i in range(10):
            writer.write(AuditEntry(operation_id=f"op-{i:03d}"))

        recent = writer.read_recent(3)
        assert len(recent) == 3
        assert recent[0].operation_id == "op-007"
        assert recent[2].operation_id == "op-009"

    def test_entry_count(self, tmp_path: Path):
        writer = AuditWriter(path=tmp_path / "audit.ndjson")
        assert writer.entry_count() == 0

        for i in range(7):
            writer.write(AuditEntry(operation_id=f"op-{i}"))
        assert writer.entry_count() == 7

    def test_read_empty_ledger(self, tmp_path: Path):
        writer = AuditWriter(path=tmp_path / "nonexistent.ndjson")
        assert writer.read_all() == []
        assert writer.entry_count() == 0

    def test_corrupt_lines_skipped(self, tmp_path: Path):
        """Corrupt lines in the ledger are skipped gracefully."""
        path = tmp_path / "audit.ndjson"
        path.write_text(
            '{"operation_id": "good-1", "operation_type": "test"}\n'
            "this is not json\n"
            '{"operation_id": "good-2", "operation_type": "test"}\n'
        )
        writer = AuditWriter(path=path)
        entries = writer.read_all()
        assert len(entries) == 2
        assert entries[0].operation_id == "good-1"
        assert entries[1].operation_id == "good-2"

    def test_creates_parent_directories(self, tmp_path: Path):
        writer = AuditWriter(path=tmp_path / "deep" / "nested" / "audit.ndjson")
        writer.write(AuditEntry(operation_id="test"))
        assert writer.path.is_file()

    def test_ndjson_format(self, tmp_path: Path):
        """Each entry is a single line of valid JSON."""
        path = tmp_path / "audit.ndjson"
        writer = AuditWriter(path=path)
        writer.write(AuditEntry(operation_id="op-1"))
        writer.write(AuditEntry(operation_id="op-2"))

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)  # each line is valid JSON
            assert "operation_id" in data

    def test_entry_fields_serialized(self, tmp_path: Path):
        writer = AuditWriter(path=tmp_path / "audit.ndjson")
        entry = AuditEntry(
            operation_id="full-test",
            operation_type="automate",
            automation="lint",
            environment="dev",
            modules_affected=["api", "web"],
            status="partial",
            actions_total=5,
            actions_succeeded=3,
            actions_failed=2,
            duration_ms=1234,
            errors=["module web: lint failed"],
            context={"trigger": "manual"},
        )
        writer.write(entry)

        loaded = writer.read_all()[0]
        assert loaded.automation == "lint"
        assert loaded.modules_affected == ["api", "web"]
        assert loaded.actions_failed == 2
        assert loaded.errors == ["module web: lint failed"]
        assert loaded.context["trigger"] == "manual"
