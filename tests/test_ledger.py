"""
Tests for the git-native ledger — models, worktree, and ledger operations.

These tests create isolated git repos in tmp directories and exercise
the full ledger workflow.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from src.core.services.ledger.models import Run, RunEvent, _make_run_id


# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════


def _init_test_repo(path: Path) -> Path:
    """Create a minimal git repo with one commit (needed for HEAD)."""
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test User"],
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@test.com"],
        capture_output=True, check=True,
    )
    # Create initial commit
    readme = path / "README.md"
    readme.write_text("# Test\n")
    subprocess.run(["git", "-C", str(path), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "initial"],
        capture_output=True, check=True,
    )
    return path


# ═══════════════════════════════════════════════════════════════════════
#  Model Tests
# ═══════════════════════════════════════════════════════════════════════


class TestRunModel:
    """Tests for the Run Pydantic model."""

    def test_default_values(self):
        run = Run(type="detect")
        assert run.run_id == ""
        assert run.type == "detect"
        assert run.status == "ok"
        assert run.started_at != ""
        assert run.ended_at != ""

    def test_ensure_id_generates(self):
        run = Run(type="detect")
        run_id = run.ensure_id()
        assert run_id.startswith("run_")
        assert "_detect_" in run_id
        assert len(run_id) > 20

    def test_ensure_id_idempotent(self):
        run = Run(type="detect")
        id1 = run.ensure_id()
        id2 = run.ensure_id()
        assert id1 == id2

    def test_ensure_id_preserves_explicit(self):
        run = Run(run_id="my-custom-id", type="detect")
        assert run.ensure_id() == "my-custom-id"

    def test_tag_message_roundtrip(self):
        run = Run(type="apply", subtype="k8s:apply", status="ok", summary="Applied 3 resources")
        run.ensure_id()
        msg = run.to_tag_message()
        restored = Run.from_tag_message(msg)
        assert restored.run_id == run.run_id
        assert restored.type == "apply"
        assert restored.subtype == "k8s:apply"
        assert restored.summary == "Applied 3 resources"

    def test_tag_message_is_compact_json(self):
        run = Run(type="detect")
        run.ensure_id()
        msg = run.to_tag_message()
        # Should be valid JSON in a single line
        data = json.loads(msg)
        assert "run_id" in data
        assert "\n" not in msg

    def test_metadata_field(self):
        run = Run(type="detect", metadata={"scan_count": 42, "targets": ["api", "web"]})
        msg = run.to_tag_message()
        restored = Run.from_tag_message(msg)
        assert restored.metadata["scan_count"] == 42
        assert restored.metadata["targets"] == ["api", "web"]


class TestRunEvent:
    """Tests for the RunEvent model."""

    def test_event_defaults(self):
        event = RunEvent(seq=1, type="adapter:execute")
        assert event.seq == 1
        assert event.ts != ""
        assert event.detail == {}

    def test_event_serialization(self):
        event = RunEvent(
            seq=1, type="adapter:execute", adapter="shell",
            action_id="a-1", status="ok", duration_ms=142,
        )
        data = event.model_dump(mode="json")
        line = json.dumps(data)
        restored = json.loads(line)
        assert restored["adapter"] == "shell"
        assert restored["duration_ms"] == 142


class TestMakeRunId:
    """Tests for the run_id generator."""

    def test_format(self):
        run_id = _make_run_id("detect")
        parts = run_id.split("_")
        assert parts[0] == "run"
        assert "T" in parts[1]      # timestamp
        assert parts[2] == "detect"  # type
        assert len(parts[3]) == 4    # random suffix

    def test_uniqueness(self):
        ids = {_make_run_id("detect") for _ in range(100)}
        assert len(ids) == 100  # all unique

    def test_type_sanitization(self):
        run_id = _make_run_id("k8s:apply")
        assert ":" not in run_id
        assert "k8s-apply" in run_id


# ═══════════════════════════════════════════════════════════════════════
#  Worktree Tests
# ═══════════════════════════════════════════════════════════════════════


class TestWorktree:
    """Tests for worktree management."""

    def test_worktree_path(self, tmp_path: Path):
        from src.core.services.ledger.worktree import worktree_path
        wt = worktree_path(tmp_path)
        assert wt == tmp_path / ".ledger"

    def test_ensure_worktree_creates_branch_and_dir(self, tmp_path: Path):
        from src.core.services.ledger.worktree import ensure_worktree
        repo = _init_test_repo(tmp_path / "repo")
        wt = ensure_worktree(repo)
        assert wt.is_dir()
        assert (wt / ".git").exists()

        # Branch should exist
        r = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", "refs/heads/scp-ledger"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0

    def test_ensure_worktree_idempotent(self, tmp_path: Path):
        from src.core.services.ledger.worktree import ensure_worktree
        repo = _init_test_repo(tmp_path / "repo")
        wt1 = ensure_worktree(repo)
        wt2 = ensure_worktree(repo)
        assert wt1 == wt2
        assert wt1.is_dir()

    def test_ensure_worktree_adds_gitignore(self, tmp_path: Path):
        from src.core.services.ledger.worktree import ensure_worktree
        repo = _init_test_repo(tmp_path / "repo")
        ensure_worktree(repo)
        gitignore = repo / ".gitignore"
        assert gitignore.is_file()
        content = gitignore.read_text()
        assert ".ledger/" in content

    def test_ensure_worktree_preserves_existing_gitignore(self, tmp_path: Path):
        from src.core.services.ledger.worktree import ensure_worktree
        repo = _init_test_repo(tmp_path / "repo")
        gitignore = repo / ".gitignore"
        gitignore.write_text("node_modules/\n.env\n")
        ensure_worktree(repo)
        content = gitignore.read_text()
        assert "node_modules/" in content
        assert ".env" in content
        assert ".ledger/" in content

    def test_create_run_tag(self, tmp_path: Path):
        from src.core.services.ledger.worktree import (
            create_run_tag,
            current_head_sha,
            list_run_tags,
            read_tag_message,
        )
        repo = _init_test_repo(tmp_path / "repo")
        head = current_head_sha(repo)
        assert head is not None

        ok = create_run_tag(repo, "scp/run/test-run-1", head, message='{"type":"detect"}')
        assert ok is True

        tags = list_run_tags(repo)
        assert "scp/run/test-run-1" in tags

        msg = read_tag_message(repo, "scp/run/test-run-1")
        assert msg is not None
        assert "detect" in msg

    def test_current_user(self, tmp_path: Path):
        from src.core.services.ledger.worktree import current_user
        repo = _init_test_repo(tmp_path / "repo")
        user = current_user(repo)
        assert user == "Test User"


# ═══════════════════════════════════════════════════════════════════════
#  Ledger Operations Tests
# ═══════════════════════════════════════════════════════════════════════


class TestLedgerOps:
    """Tests for the ledger business logic — the full workflow."""

    def test_record_and_list(self, tmp_path: Path):
        """Record a run and list it back."""
        from src.core.services.ledger.ledger_ops import list_runs, record_run
        repo = _init_test_repo(tmp_path / "repo")

        run = Run(type="detect", summary="Full detection scan")
        run_id = record_run(repo, run)

        assert run_id.startswith("run_")
        assert "_detect_" in run_id

        runs = list_runs(repo)
        assert len(runs) >= 1
        found = next((r for r in runs if r.run_id == run_id), None)
        assert found is not None
        assert found.type == "detect"
        assert found.summary == "Full detection scan"

    def test_record_with_events(self, tmp_path: Path):
        """Record a run with events and read them back."""
        from src.core.services.ledger.ledger_ops import get_run_events, record_run
        repo = _init_test_repo(tmp_path / "repo")

        events = [
            {"seq": 1, "type": "adapter:execute", "adapter": "shell", "status": "ok"},
            {"seq": 2, "type": "adapter:execute", "adapter": "git", "status": "ok"},
            {"seq": 3, "type": "run:complete", "summary": "Done"},
        ]
        run = Run(type="apply")
        run_id = record_run(repo, run, events=events)

        loaded_events = get_run_events(repo, run_id)
        assert len(loaded_events) == 3
        assert loaded_events[0]["adapter"] == "shell"
        assert loaded_events[2]["summary"] == "Done"

    def test_record_fills_code_ref(self, tmp_path: Path):
        """Record auto-fills code_ref from HEAD."""
        from src.core.services.ledger.ledger_ops import get_run, record_run
        from src.core.services.ledger.worktree import current_head_sha
        repo = _init_test_repo(tmp_path / "repo")
        expected_head = current_head_sha(repo)

        run = Run(type="detect")
        run_id = record_run(repo, run)

        loaded = get_run(repo, run_id)
        assert loaded is not None
        assert loaded.code_ref == expected_head

    def test_record_fills_user(self, tmp_path: Path):
        """Record auto-fills user from git config."""
        from src.core.services.ledger.ledger_ops import get_run, record_run
        repo = _init_test_repo(tmp_path / "repo")

        run = Run(type="detect")
        run_id = record_run(repo, run)

        loaded = get_run(repo, run_id)
        assert loaded is not None
        assert loaded.user == "Test User"

    def test_get_run_not_found(self, tmp_path: Path):
        """get_run returns None for unknown run_id."""
        from src.core.services.ledger.ledger_ops import get_run
        repo = _init_test_repo(tmp_path / "repo")
        result = get_run(repo, "nonexistent-run-id")
        assert result is None

    def test_get_run_events_no_file(self, tmp_path: Path):
        """get_run_events returns [] when no events file exists."""
        from src.core.services.ledger.ledger_ops import get_run_events, record_run
        repo = _init_test_repo(tmp_path / "repo")

        run = Run(type="detect")
        run_id = record_run(repo, run)  # no events passed

        events = get_run_events(repo, run_id)
        assert events == []

    def test_list_runs_newest_first(self, tmp_path: Path):
        """list_runs returns newest runs first."""
        import time
        from src.core.services.ledger.ledger_ops import list_runs, record_run
        repo = _init_test_repo(tmp_path / "repo")

        id1 = record_run(repo, Run(type="first"))
        # Sleep >1s to guarantee different second-level timestamps
        # (git tag creatordate has second resolution)
        time.sleep(1.1)
        id2 = record_run(repo, Run(type="second"))

        runs = list_runs(repo, n=10)
        assert len(runs) >= 2
        # Newest first
        run_ids = [r.run_id for r in runs]
        assert run_ids.index(id2) < run_ids.index(id1)

    def test_list_runs_limit(self, tmp_path: Path):
        """list_runs respects the n limit."""
        from src.core.services.ledger.ledger_ops import list_runs, record_run
        repo = _init_test_repo(tmp_path / "repo")

        for i in range(5):
            record_run(repo, Run(type=f"run-{i}"))

        runs = list_runs(repo, n=3)
        assert len(runs) == 3

    def test_run_json_on_disk(self, tmp_path: Path):
        """run.json is written to the worktree and is valid JSON."""
        from src.core.services.ledger.ledger_ops import record_run
        from src.core.services.ledger.worktree import worktree_path
        repo = _init_test_repo(tmp_path / "repo")

        run = Run(type="detect", summary="test")
        run_id = record_run(repo, run)

        run_json = worktree_path(repo) / "ledger" / "runs" / run_id / "run.json"
        assert run_json.is_file()
        data = json.loads(run_json.read_text())
        assert data["type"] == "detect"
        assert data["summary"] == "test"

    def test_ensure_ledger_idempotent(self, tmp_path: Path):
        """ensure_ledger can be called multiple times safely."""
        from src.core.services.ledger.ledger_ops import ensure_ledger
        repo = _init_test_repo(tmp_path / "repo")
        p1 = ensure_ledger(repo)
        p2 = ensure_ledger(repo)
        assert p1 == p2
        assert p1.is_dir()

    def test_works_without_remote(self, tmp_path: Path):
        """All operations work in a repo with no remote."""
        from src.core.services.ledger.ledger_ops import (
            get_run,
            list_runs,
            record_run,
        )
        repo = _init_test_repo(tmp_path / "repo")
        # No remote — should not error
        run = Run(type="detect")
        run_id = record_run(repo, run)
        runs = list_runs(repo)
        assert len(runs) >= 1
        loaded = get_run(repo, run_id)
        assert loaded is not None


# ═══════════════════════════════════════════════════════════════════════
#  Event Bus Integration Tests
# ═══════════════════════════════════════════════════════════════════════


class TestEventBusIntegration:
    """Tests that record_run publishes to the event bus."""

    def test_record_publishes_event(self, tmp_path: Path):
        """record_run publishes a ledger:run event to the bus."""
        from src.core.services.event_bus import bus
        from src.core.services.ledger.ledger_ops import record_run
        repo = _init_test_repo(tmp_path / "repo")

        # Record the initial bus sequence
        initial_seq = bus.seq

        run = Run(type="detect", summary="Bus test")
        run_id = record_run(repo, run)

        # Bus should have received at least one new event
        assert bus.seq > initial_seq

        # Check the buffer for our event
        found = False
        with bus._lock:
            for event in bus._buffer:
                if event.get("type") == "ledger:run" and event.get("key") == run_id:
                    found = True
                    assert event["data"]["type"] == "detect"
                    assert event["data"]["summary"] == "Bus test"
                    break
        assert found, "ledger:run event not found in bus buffer"


# ═══════════════════════════════════════════════════════════════════════
#  Push / Pull Tests (with local bare remote)
# ═══════════════════════════════════════════════════════════════════════


def _init_repo_with_remote(tmp_path: Path) -> tuple[Path, Path]:
    """Create a repo + a bare remote and link them.

    Returns (repo_path, bare_remote_path).
    """
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], capture_output=True, check=True)

    repo = _init_test_repo(tmp_path / "repo")
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", str(bare)],
        capture_output=True, check=True,
    )
    # Push main branch so remote has something
    subprocess.run(
        ["git", "-C", str(repo), "push", "-u", "origin", "HEAD"],
        capture_output=True, check=True,
    )
    return repo, bare


class TestPushPull:
    """Tests for push/pull with a local bare remote."""

    def test_push_ledger(self, tmp_path: Path):
        """push_ledger pushes branch and tags to origin."""
        from src.core.services.ledger.ledger_ops import push_ledger, record_run
        repo, bare = _init_repo_with_remote(tmp_path)

        run = Run(type="detect", summary="Push test")
        run_id = record_run(repo, run)

        ok = push_ledger(repo)
        assert ok is True

        # Verify remote has the scp-ledger branch
        r = subprocess.run(
            ["git", "-C", str(bare), "branch", "--list"],
            capture_output=True, text=True,
        )
        assert "scp-ledger" in r.stdout

        # Verify remote has the tag
        r = subprocess.run(
            ["git", "-C", str(bare), "tag", "-l", "scp/run/*"],
            capture_output=True, text=True,
        )
        assert run_id in r.stdout

    def test_pull_ledger_from_remote(self, tmp_path: Path):
        """Pull runs recorded by another clone."""
        from src.core.services.ledger.ledger_ops import (
            list_runs,
            pull_ledger,
            push_ledger,
            record_run,
        )
        from src.core.services.ledger.worktree import ensure_worktree

        # Clone 1: record and push
        repo1, bare = _init_repo_with_remote(tmp_path)
        run = Run(type="detect", summary="From clone 1")
        run_id = record_run(repo1, run)
        push_ledger(repo1)

        # Clone 2: fresh clone from the same bare remote
        repo2 = tmp_path / "clone2"
        subprocess.run(
            ["git", "clone", str(bare), str(repo2)],
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo2), "config", "user.name", "Clone2 User"],
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo2), "config", "user.email", "clone2@test.com"],
            capture_output=True, check=True,
        )

        # Pull ledger into clone 2
        ensure_worktree(repo2)
        pull_ledger(repo2)

        # Clone 2 should see the run from clone 1
        runs = list_runs(repo2)
        found = next((r for r in runs if r.run_id == run_id), None)
        assert found is not None, f"Run {run_id} not found in clone 2"
        assert found.summary == "From clone 1"
