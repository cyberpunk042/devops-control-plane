"""
Tests for the SCP Chat — models, crypto, chat_ops.

These tests create isolated git repos in tmp directories and exercise
the full chat workflow including encryption.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from src.core.services.chat.models import ChatMessage, MessageFlags, Thread


# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════


def _init_test_repo(path: Path) -> Path:
    """Create a minimal git repo with one commit + a recorded run (for run-attached tests)."""
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Chat Tester"],
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "chat@test.com"],
        capture_output=True, check=True,
    )
    readme = path / "README.md"
    readme.write_text("# Chat Test\n")
    subprocess.run(["git", "-C", str(path), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "initial"],
        capture_output=True, check=True,
    )
    return path


def _init_repo_with_run(path: Path) -> tuple[Path, str]:
    """Create a test repo and record a run (returns repo_path, run_id)."""
    from src.core.services.ledger.ledger_ops import record_run
    from src.core.services.ledger.models import Run

    repo = _init_test_repo(path)
    run_id = record_run(repo, Run(type="detect", summary="Test run"))
    return repo, run_id


def _set_enc_key(repo: Path, key: str = "test-chat-key-2024") -> None:
    """Write CONTENT_VAULT_ENC_KEY to .env in the repo."""
    env_file = repo / ".env"
    env_file.write_text(f"CONTENT_VAULT_ENC_KEY={key}\n")


# ═══════════════════════════════════════════════════════════════════════
#  Model Tests
# ═══════════════════════════════════════════════════════════════════════


class TestChatModels:
    """Tests for ChatMessage and Thread models."""

    def test_default_values(self):
        msg = ChatMessage()
        assert msg.id == ""
        assert msg.text == ""
        assert msg.source == "manual"
        assert msg.flags.publish is False
        assert msg.flags.encrypted is False
        assert msg.ts != ""

    def test_ensure_id(self):
        msg = ChatMessage()
        mid = msg.ensure_id()
        assert mid.startswith("msg_")
        assert len(mid) > 15
        # Idempotent
        assert msg.ensure_id() == mid

    def test_jsonl_roundtrip(self):
        msg = ChatMessage(
            text="Hello world",
            user="tester",
            run_id="run_123",
            source="manual",
            flags=MessageFlags(publish=True),
        )
        msg.ensure_id()
        line = msg.to_jsonl()
        restored = ChatMessage.from_jsonl(line)
        assert restored.id == msg.id
        assert restored.text == "Hello world"
        assert restored.user == "tester"
        assert restored.run_id == "run_123"
        assert restored.flags.publish is True

    def test_thread_defaults(self):
        thread = Thread()
        assert thread.thread_id == ""
        assert thread.title == ""
        assert thread.created_at != ""
        assert thread.tags == []

    def test_thread_ensure_id(self):
        thread = Thread()
        tid = thread.ensure_id()
        assert tid.startswith("thread_")
        assert len(tid) > 15
        assert thread.ensure_id() == tid

    def test_message_flags_defaults(self):
        flags = MessageFlags()
        assert flags.publish is False
        assert flags.encrypted is False


# ═══════════════════════════════════════════════════════════════════════
#  Crypto Tests
# ═══════════════════════════════════════════════════════════════════════


class TestChatCrypto:
    """Tests for chat_crypto encrypt/decrypt."""

    def test_encrypt_decrypt_roundtrip(self, tmp_path: Path):
        from src.core.services.chat.chat_crypto import decrypt_text, encrypt_text
        repo = tmp_path / "repo"
        repo.mkdir()
        _set_enc_key(repo)

        original = "This is a secret message 🔐"
        encrypted = encrypt_text(original, repo)

        assert encrypted.startswith("ENC:v1:")
        assert original not in encrypted

        decrypted = decrypt_text(encrypted, repo)
        assert decrypted == original

    def test_encrypt_no_key_raises(self, tmp_path: Path):
        from src.core.services.chat.chat_crypto import encrypt_text
        repo = tmp_path / "repo"
        repo.mkdir()
        # No .env → no key

        with pytest.raises(ValueError, match="CONTENT_VAULT_ENC_KEY"):
            encrypt_text("secret", repo)

    def test_decrypt_no_key_raises(self, tmp_path: Path):
        from src.core.services.chat.chat_crypto import decrypt_text
        repo = tmp_path / "repo"
        repo.mkdir()

        with pytest.raises(ValueError, match="CONTENT_VAULT_ENC_KEY"):
            decrypt_text("ENC:v1:abc:def:ghi", repo)

    def test_decrypt_wrong_key_raises(self, tmp_path: Path):
        from src.core.services.chat.chat_crypto import decrypt_text, encrypt_text
        repo = tmp_path / "repo"
        repo.mkdir()
        _set_enc_key(repo, "correct-key")
        encrypted = encrypt_text("secret", repo)

        _set_enc_key(repo, "wrong-key")
        with pytest.raises(ValueError, match="Decryption failed"):
            decrypt_text(encrypted, repo)

    def test_is_encrypted(self):
        from src.core.services.chat.chat_crypto import is_encrypted
        assert is_encrypted("ENC:v1:abc:def:ghi") is True
        assert is_encrypted("Hello world") is False
        assert is_encrypted("") is False

    def test_decrypt_bad_format_raises(self, tmp_path: Path):
        from src.core.services.chat.chat_crypto import decrypt_text
        repo = tmp_path / "repo"
        repo.mkdir()
        _set_enc_key(repo)

        with pytest.raises(ValueError, match="Not an encrypted"):
            decrypt_text("not encrypted", repo)

        with pytest.raises(ValueError, match="expected salt:iv:ciphertext"):
            decrypt_text("ENC:v1:only-one-part", repo)


# ═══════════════════════════════════════════════════════════════════════
#  Chat Ops Tests
# ═══════════════════════════════════════════════════════════════════════


class TestChatOps:
    """Tests for the chat business logic."""

    def test_send_to_thread(self, tmp_path: Path):
        """Send a message to a thread (file-based storage)."""
        from src.core.services.chat.chat_ops import create_thread, list_messages, send_message
        repo = _init_test_repo(tmp_path / "repo")

        thread = create_thread(repo, "Deployment discussion")
        msg = send_message(repo, "Starting deployment", thread_id=thread.thread_id)

        assert msg.id.startswith("msg_")
        assert msg.thread_id == thread.thread_id
        assert msg.text == "Starting deployment"
        assert msg.user == "Chat Tester"

        # Read back
        messages = list_messages(repo, thread_id=thread.thread_id)
        assert len(messages) == 1
        assert messages[0].id == msg.id
        assert messages[0].text == "Starting deployment"

    def test_send_to_run(self, tmp_path: Path):
        """Send a message attached to a run (git notes)."""
        from src.core.services.chat.chat_ops import list_messages, send_message
        repo, run_id = _init_repo_with_run(tmp_path / "repo")

        msg = send_message(repo, "Run completed successfully", run_id=run_id)

        assert msg.run_id == run_id
        assert msg.text == "Run completed successfully"

        # Read back from notes
        messages = list_messages(repo, run_id=run_id)
        assert len(messages) >= 1
        found = next((m for m in messages if m.id == msg.id), None)
        assert found is not None
        assert found.text == "Run completed successfully"

    def test_send_general_thread(self, tmp_path: Path):
        """Message with no run_id and no thread_id goes to general thread."""
        from src.core.services.chat.chat_ops import GENERAL_THREAD_ID, list_messages, send_message
        repo = _init_test_repo(tmp_path / "repo")

        msg = send_message(repo, "Hello everyone")

        assert msg.thread_id == GENERAL_THREAD_ID

        # General thread should have the message
        messages = list_messages(repo, thread_id=GENERAL_THREAD_ID)
        assert len(messages) == 1
        assert messages[0].text == "Hello everyone"

    def test_send_to_both(self, tmp_path: Path):
        """Message with both run_id and thread_id writes to both locations."""
        from src.core.services.chat.chat_ops import (
            create_thread,
            list_messages,
            send_message,
        )
        repo, run_id = _init_repo_with_run(tmp_path / "repo")
        thread = create_thread(repo, "Dual tracking")

        msg = send_message(
            repo, "Dual-stored message",
            run_id=run_id,
            thread_id=thread.thread_id,
        )

        # Readable from notes
        run_msgs = list_messages(repo, run_id=run_id)
        assert any(m.id == msg.id for m in run_msgs)

        # Readable from thread
        thread_msgs = list_messages(repo, thread_id=thread.thread_id)
        assert any(m.id == msg.id for m in thread_msgs)

    def test_encrypted_message(self, tmp_path: Path):
        """Encrypted message round-trip."""
        from src.core.services.chat.chat_ops import create_thread, list_messages, send_message
        repo = _init_test_repo(tmp_path / "repo")
        _set_enc_key(repo)

        thread = create_thread(repo, "Secret ops")
        msg = send_message(
            repo, "Top secret deployment",
            thread_id=thread.thread_id,
            encrypt=True,
        )

        assert msg.flags.encrypted is True
        assert msg.text.startswith("ENC:v1:")

        # list_messages auto-decrypts
        messages = list_messages(repo, thread_id=thread.thread_id)
        assert len(messages) == 1
        assert messages[0].text == "Top secret deployment"

    def test_encrypted_message_no_key_list(self, tmp_path: Path):
        """Encrypted messages show [encrypted] when key unavailable."""
        from src.core.services.chat.chat_ops import create_thread, list_messages, send_message
        repo = _init_test_repo(tmp_path / "repo")
        _set_enc_key(repo)

        thread = create_thread(repo, "Secret ops")
        send_message(
            repo, "Secret message",
            thread_id=thread.thread_id,
            encrypt=True,
        )

        # Remove the key
        (repo / ".env").unlink()

        # Should show [encrypted]
        messages = list_messages(repo, thread_id=thread.thread_id)
        assert len(messages) == 1
        assert messages[0].text == "[encrypted]"
        assert messages[0].flags.encrypted is True

    def test_encrypt_no_key_errors(self, tmp_path: Path):
        """encrypt=True without key raises ValueError."""
        from src.core.services.chat.chat_ops import send_message
        repo = _init_test_repo(tmp_path / "repo")
        # No .env

        with pytest.raises(ValueError, match="CONTENT_VAULT_ENC_KEY"):
            send_message(repo, "secret", encrypt=True)

    def test_create_and_list_threads(self, tmp_path: Path):
        """Create multiple threads and list them."""
        from src.core.services.chat.chat_ops import create_thread, list_threads
        repo = _init_test_repo(tmp_path / "repo")

        t1 = create_thread(repo, "Thread A")
        t2 = create_thread(repo, "Thread B", tags=["deployment"])

        threads = list_threads(repo)
        assert len(threads) >= 2
        ids = [t.thread_id for t in threads]
        assert t1.thread_id in ids
        assert t2.thread_id in ids

        # t2 should have tags
        t2_loaded = next(t for t in threads if t.thread_id == t2.thread_id)
        assert "deployment" in t2_loaded.tags

    def test_thread_with_anchor_run(self, tmp_path: Path):
        """Thread can be anchored to a run."""
        from src.core.services.chat.chat_ops import create_thread, list_threads
        repo, run_id = _init_repo_with_run(tmp_path / "repo")

        thread = create_thread(repo, "Run discussion", anchor_run=run_id)
        assert thread.anchor_run == run_id

        threads = list_threads(repo)
        found = next(t for t in threads if t.thread_id == thread.thread_id)
        assert found.anchor_run == run_id

    def test_list_messages_newest_first(self, tmp_path: Path):
        """Messages are returned newest-first."""
        import time
        from src.core.services.chat.chat_ops import create_thread, list_messages, send_message
        repo = _init_test_repo(tmp_path / "repo")

        thread = create_thread(repo, "Ordering test")
        m1 = send_message(repo, "First", thread_id=thread.thread_id)
        time.sleep(0.05)  # Ensure different timestamp
        m2 = send_message(repo, "Second", thread_id=thread.thread_id)

        messages = list_messages(repo, thread_id=thread.thread_id)
        assert len(messages) == 2
        # Newest first
        assert messages[0].id == m2.id
        assert messages[1].id == m1.id

    def test_list_messages_limit(self, tmp_path: Path):
        """list_messages respects the n limit."""
        from src.core.services.chat.chat_ops import create_thread, list_messages, send_message
        repo = _init_test_repo(tmp_path / "repo")

        thread = create_thread(repo, "Limit test")
        for i in range(5):
            send_message(repo, f"Message {i}", thread_id=thread.thread_id)

        messages = list_messages(repo, thread_id=thread.thread_id, n=3)
        assert len(messages) == 3

    def test_publish_flag(self, tmp_path: Path):
        """publish=True sets the flag correctly."""
        from src.core.services.chat.chat_ops import create_thread, list_messages, send_message
        repo = _init_test_repo(tmp_path / "repo")

        thread = create_thread(repo, "Public test")
        msg = send_message(
            repo, "Public announcement",
            thread_id=thread.thread_id,
            publish=True,
        )
        assert msg.flags.publish is True

        messages = list_messages(repo, thread_id=thread.thread_id)
        assert messages[0].flags.publish is True

    def test_system_source(self, tmp_path: Path):
        """source='system' is preserved."""
        from src.core.services.chat.chat_ops import create_thread, list_messages, send_message
        repo = _init_test_repo(tmp_path / "repo")

        thread = create_thread(repo, "System test")
        msg = send_message(
            repo, "Auto-generated message",
            thread_id=thread.thread_id,
            source="system",
        )
        assert msg.source == "system"

        messages = list_messages(repo, thread_id=thread.thread_id)
        assert messages[0].source == "system"

    def test_empty_thread_returns_empty(self, tmp_path: Path):
        """list_messages on empty thread returns []."""
        from src.core.services.chat.chat_ops import create_thread, list_messages
        repo = _init_test_repo(tmp_path / "repo")

        thread = create_thread(repo, "Empty thread")
        messages = list_messages(repo, thread_id=thread.thread_id)
        assert messages == []

    def test_nonexistent_run_returns_empty(self, tmp_path: Path):
        """list_messages for nonexistent run returns []."""
        from src.core.services.chat.chat_ops import list_messages
        repo = _init_test_repo(tmp_path / "repo")

        messages = list_messages(repo, run_id="nonexistent-run")
        assert messages == []


# ═══════════════════════════════════════════════════════════════════════
#  Event Bus Integration
# ═══════════════════════════════════════════════════════════════════════


class TestChatEventBus:
    """Tests that send_message publishes to the event bus."""

    def test_send_publishes_event(self, tmp_path: Path):
        """send_message publishes a chat:message event."""
        from src.core.services.chat.chat_ops import create_thread, send_message
        from src.core.services.event_bus import bus
        repo = _init_test_repo(tmp_path / "repo")

        initial_seq = bus.seq
        thread = create_thread(repo, "Bus test")
        msg = send_message(repo, "Bus test message", thread_id=thread.thread_id)

        assert bus.seq > initial_seq

        found = False
        with bus._lock:
            for event in bus._buffer:
                if event.get("type") == "chat:message" and event.get("key") == msg.id:
                    found = True
                    assert event["data"]["user"] == "Chat Tester"
                    assert event["data"]["thread_id"] == thread.thread_id
                    break
        assert found, "chat:message event not found in bus buffer"


# ═══════════════════════════════════════════════════════════════════════
#  New Fields (refs, trace_id) Tests
# ═══════════════════════════════════════════════════════════════════════


class TestNewModelFields:
    """Tests for refs and trace_id fields on ChatMessage."""

    def test_refs_defaults_empty(self):
        msg = ChatMessage()
        assert msg.refs == []

    def test_trace_id_defaults_none(self):
        msg = ChatMessage()
        assert msg.trace_id is None

    def test_refs_roundtrip(self):
        msg = ChatMessage(
            text="See @run:run_123",
            refs=["@run:run_123"],
        )
        msg.ensure_id()
        line = msg.to_jsonl()
        restored = ChatMessage.from_jsonl(line)
        assert restored.refs == ["@run:run_123"]

    def test_trace_id_roundtrip(self):
        msg = ChatMessage(
            text="About this trace",
            trace_id="trace_20260217T120000Z_a1b2",
        )
        msg.ensure_id()
        line = msg.to_jsonl()
        restored = ChatMessage.from_jsonl(line)
        assert restored.trace_id == "trace_20260217T120000Z_a1b2"

    def test_send_auto_parses_refs(self, tmp_path: Path):
        """send_message auto-populates refs from text."""
        from src.core.services.chat.chat_ops import create_thread, list_messages, send_message
        repo = _init_test_repo(tmp_path / "repo")

        thread = create_thread(repo, "Refs test")
        msg = send_message(
            repo,
            "Deployed @run:run_123 per @thread:thread_456",
            thread_id=thread.thread_id,
        )

        assert msg.refs == ["@run:run_123", "@thread:thread_456"]

        # Read back
        messages = list_messages(repo, thread_id=thread.thread_id)
        assert messages[0].refs == ["@run:run_123", "@thread:thread_456"]

    def test_send_no_refs(self, tmp_path: Path):
        """send_message with no @-references results in empty refs list."""
        from src.core.services.chat.chat_ops import create_thread, send_message
        repo = _init_test_repo(tmp_path / "repo")

        thread = create_thread(repo, "No refs")
        msg = send_message(repo, "Plain message", thread_id=thread.thread_id)
        assert msg.refs == []

    def test_send_with_trace_id(self, tmp_path: Path):
        """send_message passes trace_id through."""
        from src.core.services.chat.chat_ops import create_thread, list_messages, send_message
        repo = _init_test_repo(tmp_path / "repo")

        thread = create_thread(repo, "Trace ref")
        msg = send_message(
            repo, "Trace summary",
            thread_id=thread.thread_id,
            trace_id="trace_test_123",
        )
        assert msg.trace_id == "trace_test_123"

        messages = list_messages(repo, thread_id=thread.thread_id)
        assert messages[0].trace_id == "trace_test_123"


# ═══════════════════════════════════════════════════════════════════════
#  chat_refs Tests
# ═══════════════════════════════════════════════════════════════════════


class TestParseRefs:
    """Tests for parse_refs."""

    def test_single_ref(self):
        from src.core.services.chat.chat_refs import parse_refs
        assert parse_refs("See @run:run_123") == ["@run:run_123"]

    def test_multiple_refs(self):
        from src.core.services.chat.chat_refs import parse_refs
        result = parse_refs("@run:run_1 linked to @thread:thread_2 and @trace:trace_3")
        assert result == ["@run:run_1", "@thread:thread_2", "@trace:trace_3"]

    def test_no_refs(self):
        from src.core.services.chat.chat_refs import parse_refs
        assert parse_refs("No references here") == []
        assert parse_refs("") == []

    def test_duplicate_refs_deduplicated(self):
        from src.core.services.chat.chat_refs import parse_refs
        result = parse_refs("@run:run_1 and again @run:run_1")
        assert result == ["@run:run_1"]

    def test_invalid_type_ignored(self):
        from src.core.services.chat.chat_refs import parse_refs
        assert parse_refs("@invalid:foo_123") == []

    def test_user_ref(self):
        from src.core.services.chat.chat_refs import parse_refs
        assert parse_refs("cc @user:JohnDoe") == ["@user:JohnDoe"]

    def test_ref_parts(self):
        from src.core.services.chat.chat_refs import parse_ref_parts
        assert parse_ref_parts("@run:run_123") == ("run", "run_123")
        assert parse_ref_parts("@thread:t_1") == ("thread", "t_1")
        assert parse_ref_parts("not a ref") is None
        assert parse_ref_parts("@invalid:foo") is None


class TestResolveRef:
    """Tests for resolve_ref."""

    def test_resolve_run_exists(self, tmp_path: Path):
        from src.core.services.chat.chat_refs import resolve_ref
        repo, run_id = _init_repo_with_run(tmp_path / "repo")

        result = resolve_ref(f"@run:{run_id}", repo)
        assert result is not None
        assert result["type"] == "run"
        assert result["exists"] is True
        assert result["run_type"] == "detect"

    def test_resolve_run_not_found(self, tmp_path: Path):
        from src.core.services.chat.chat_refs import resolve_ref
        repo = _init_test_repo(tmp_path / "repo")

        result = resolve_ref("@run:nonexistent", repo)
        assert result is not None
        assert result["exists"] is False

    def test_resolve_thread_exists(self, tmp_path: Path):
        from src.core.services.chat.chat_ops import create_thread
        from src.core.services.chat.chat_refs import resolve_ref
        repo = _init_test_repo(tmp_path / "repo")

        thread = create_thread(repo, "Resolvable thread")
        result = resolve_ref(f"@thread:{thread.thread_id}", repo)
        assert result is not None
        assert result["exists"] is True
        assert result["title"] == "Resolvable thread"

    def test_resolve_user(self, tmp_path: Path):
        from src.core.services.chat.chat_refs import resolve_ref
        repo = _init_test_repo(tmp_path / "repo")

        result = resolve_ref("@user:JohnDoe", repo)
        assert result is not None
        assert result["type"] == "user"
        assert result["name"] == "JohnDoe"

    def test_resolve_invalid_ref(self, tmp_path: Path):
        from src.core.services.chat.chat_refs import resolve_ref
        repo = _init_test_repo(tmp_path / "repo")

        assert resolve_ref("not a ref", repo) is None


class TestAutocomplete:
    """Tests for autocomplete."""

    def test_type_completion(self, tmp_path: Path):
        from src.core.services.chat.chat_refs import autocomplete
        repo = _init_test_repo(tmp_path / "repo")

        # "@" alone should suggest nothing (no type yet)
        # "@r" should suggest "@run:"
        result = autocomplete("@r", repo)
        assert "@run:" in result

    def test_type_completion_all(self, tmp_path: Path):
        from src.core.services.chat.chat_refs import autocomplete
        repo = _init_test_repo(tmp_path / "repo")

        result = autocomplete("@", repo)
        assert len(result) == 8  # run, thread, trace, user, commit, branch, audit, code

    def test_run_autocomplete(self, tmp_path: Path):
        from src.core.services.chat.chat_refs import autocomplete
        repo, run_id = _init_repo_with_run(tmp_path / "repo")

        result = autocomplete("@run:", repo)
        assert any(run_id in r for r in result)

    def test_thread_autocomplete(self, tmp_path: Path):
        from src.core.services.chat.chat_ops import create_thread
        from src.core.services.chat.chat_refs import autocomplete
        repo = _init_test_repo(tmp_path / "repo")

        thread = create_thread(repo, "Autocomplete test")
        result = autocomplete("@thread:", repo)
        assert any(thread.thread_id in r for r in result)

    def test_no_prefix_returns_empty(self, tmp_path: Path):
        from src.core.services.chat.chat_refs import autocomplete
        repo = _init_test_repo(tmp_path / "repo")

        assert autocomplete("no at sign", repo) == []


# ═══════════════════════════════════════════════════════════════════════
#  New @-reference types (commit, branch, audit, code)
# ═══════════════════════════════════════════════════════════════════════


class TestNewRefTypes:
    """Tests for expanded @-reference types."""

    def test_parse_commit_ref(self):
        from src.core.services.chat.chat_refs import parse_refs
        result = parse_refs("See @commit:abc1234 for details")
        assert result == ["@commit:abc1234"]

    def test_parse_branch_ref(self):
        from src.core.services.chat.chat_refs import parse_refs
        result = parse_refs("Merged from @branch:feature/login")
        assert result == ["@branch:feature/login"]

    def test_parse_audit_ref(self):
        from src.core.services.chat.chat_refs import parse_refs
        result = parse_refs("Related to @audit:op_12345")
        assert result == ["@audit:op_12345"]

    def test_parse_code_ref(self):
        from src.core.services.chat.chat_refs import parse_refs
        result = parse_refs("Changed @code:src/main.py")
        assert result == ["@code:src/main.py"]

    def test_parse_code_ref_with_path(self):
        from src.core.services.chat.chat_refs import parse_refs
        result = parse_refs("See @code:src/core/services/chat/chat_refs.py")
        assert result == ["@code:src/core/services/chat/chat_refs.py"]

    def test_parse_mixed_old_and_new_refs(self):
        from src.core.services.chat.chat_refs import parse_refs
        result = parse_refs("@run:run_1 changed @code:src/main.py on @branch:main")
        assert result == ["@run:run_1", "@code:src/main.py", "@branch:main"]

    def test_type_completion_all_8(self, tmp_path: Path):
        """@-prefix should now suggest all 8 types."""
        from src.core.services.chat.chat_refs import autocomplete
        repo = _init_test_repo(tmp_path / "repo")
        result = autocomplete("@", repo)
        assert len(result) == 8  # run, thread, trace, user, commit, branch, audit, code

    def test_resolve_commit_exists(self, tmp_path: Path):
        """Resolve a commit that exists."""
        import subprocess
        from src.core.services.chat.chat_refs import resolve_ref
        repo = _init_test_repo(tmp_path / "repo")

        # Get the actual HEAD short hash
        r = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True,
        )
        short_hash = r.stdout.strip()

        result = resolve_ref(f"@commit:{short_hash}", repo)
        assert result is not None
        assert result["type"] == "commit"
        assert result["exists"] is True
        assert result["message"] == "initial"

    def test_resolve_commit_not_found(self, tmp_path: Path):
        from src.core.services.chat.chat_refs import resolve_ref
        repo = _init_test_repo(tmp_path / "repo")

        result = resolve_ref("@commit:deadbeef99", repo)
        assert result is not None
        assert result["exists"] is False

    def test_resolve_branch_exists(self, tmp_path: Path):
        """main branch should resolve."""
        import subprocess
        from src.core.services.chat.chat_refs import resolve_ref
        repo = _init_test_repo(tmp_path / "repo")

        # Get current branch name
        r = subprocess.run(
            ["git", "-C", str(repo), "branch", "--show-current"],
            capture_output=True, text=True,
        )
        branch = r.stdout.strip()

        result = resolve_ref(f"@branch:{branch}", repo)
        assert result is not None
        assert result["type"] == "branch"
        assert result["exists"] is True
        assert "sha" in result

    def test_resolve_branch_not_found(self, tmp_path: Path):
        from src.core.services.chat.chat_refs import resolve_ref
        repo = _init_test_repo(tmp_path / "repo")

        result = resolve_ref("@branch:nonexistent-branch-xyz", repo)
        assert result is not None
        assert result["exists"] is False

    def test_resolve_audit_exists(self, tmp_path: Path):
        """Resolve an audit entry that exists."""
        from src.core.persistence.audit import AuditEntry, AuditWriter
        from src.core.services.chat.chat_refs import resolve_ref
        repo = _init_test_repo(tmp_path / "repo")

        # Write an audit entry
        writer = AuditWriter(project_root=repo)
        entry = AuditEntry(
            operation_id="op_test_123",
            operation_type="detect",
            status="ok",
            automation="stack_detect",
        )
        writer.write(entry)

        result = resolve_ref("@audit:op_test_123", repo)
        assert result is not None
        assert result["type"] == "audit"
        assert result["exists"] is True
        assert result["operation_type"] == "detect"
        assert result["status"] == "ok"

    def test_resolve_audit_not_found(self, tmp_path: Path):
        from src.core.services.chat.chat_refs import resolve_ref
        repo = _init_test_repo(tmp_path / "repo")

        result = resolve_ref("@audit:nonexistent_op", repo)
        assert result is not None
        assert result["exists"] is False

    def test_resolve_code_exists(self, tmp_path: Path):
        """Resolve a code file that exists."""
        from src.core.services.chat.chat_refs import resolve_ref
        repo = _init_test_repo(tmp_path / "repo")

        result = resolve_ref("@code:README.md", repo)
        assert result is not None
        assert result["type"] == "code"
        assert result["exists"] is True
        assert result["size_bytes"] > 0

    def test_resolve_code_not_found(self, tmp_path: Path):
        from src.core.services.chat.chat_refs import resolve_ref
        repo = _init_test_repo(tmp_path / "repo")

        result = resolve_ref("@code:nonexistent_file.py", repo)
        assert result is not None
        assert result["exists"] is False

    def test_autocomplete_commits(self, tmp_path: Path):
        from src.core.services.chat.chat_refs import autocomplete
        repo = _init_test_repo(tmp_path / "repo")

        result = autocomplete("@commit:", repo)
        assert len(result) >= 1  # At least the "initial" commit
        assert all(r.startswith("@commit:") for r in result)

    def test_autocomplete_branches(self, tmp_path: Path):
        from src.core.services.chat.chat_refs import autocomplete
        repo = _init_test_repo(tmp_path / "repo")

        result = autocomplete("@branch:", repo)
        assert len(result) >= 1
        assert all(r.startswith("@branch:") for r in result)

    def test_autocomplete_audits(self, tmp_path: Path):
        from src.core.persistence.audit import AuditEntry, AuditWriter
        from src.core.services.chat.chat_refs import autocomplete
        repo = _init_test_repo(tmp_path / "repo")

        writer = AuditWriter(project_root=repo)
        writer.write(AuditEntry(operation_id="op_auto_1", operation_type="detect"))
        writer.write(AuditEntry(operation_id="op_auto_2", operation_type="scaffold"))

        result = autocomplete("@audit:", repo)
        assert len(result) >= 2
        assert "@audit:op_auto_1" in result
        assert "@audit:op_auto_2" in result


