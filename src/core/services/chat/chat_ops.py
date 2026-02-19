"""
Chat operations — send, list, thread CRUD, push/pull.

Uses two storage backends:
  - Git notes (``refs/notes/scp-chat``) for run-attached messages
  - Ledger branch files (``.scp-ledger/chat/threads/``) for thread messages

Uses ``chat_crypto.py`` for encryption/decryption.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.core.services.chat.chat_crypto import decrypt_text, encrypt_text, is_encrypted
from src.core.services.chat.chat_refs import parse_refs
from src.core.services.chat.models import ChatMessage, MessageFlags, Thread
from src.core.services.ledger.worktree import (
    TAG_PREFIX,
    _run_main_git,
    current_user,
    ensure_worktree,
    ledger_add_and_commit,
    notes_append,
    notes_show,
    worktree_path,
)

try:
    from src.core.services.event_bus import bus as _bus
except Exception:  # pragma: no cover
    _bus = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

NOTES_REF = "refs/notes/scp-chat"
GENERAL_THREAD_ID = "general"


# ═══════════════════════════════════════════════════════════════════════
#  Internal helpers
# ═══════════════════════════════════════════════════════════════════════


def _tag_object_sha(project_root: Path, run_id: str) -> str | None:
    """Get the object SHA of an annotated tag (needed for notes target).

    We need the tag object itself, not the commit it points to.
    ``git rev-parse scp/run/<run_id>`` returns the tag object SHA for
    annotated tags when the ref is the full tag name.
    """
    tag_name = f"{TAG_PREFIX}{run_id}"
    r = _run_main_git("rev-parse", tag_name, project_root=project_root)
    if r.returncode != 0:
        logger.warning("Tag %s not found: %s", tag_name, r.stderr.strip())
        return None
    return r.stdout.strip()


def _threads_dir(project_root: Path) -> Path:
    """Return the threads directory on the ledger branch."""
    return worktree_path(project_root) / "chat" / "threads"


def _thread_dir(project_root: Path, thread_id: str) -> Path:
    """Return a specific thread's directory."""
    return _threads_dir(project_root) / thread_id


def _read_thread_messages(thread_dir: Path) -> list[ChatMessage]:
    """Read messages from a thread's messages.jsonl file."""
    messages_file = thread_dir / "messages.jsonl"
    if not messages_file.is_file():
        return []

    messages: list[ChatMessage] = []
    try:
        for line in messages_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(ChatMessage.from_jsonl(line))
            except Exception as e:
                logger.warning("Skipping corrupt message: %s", e)
    except OSError as e:
        logger.error("Failed to read thread messages: %s", e)

    return messages


def _append_thread_message(project_root: Path, thread_id: str, msg: ChatMessage) -> None:
    """Append a message to a thread's messages.jsonl file and commit."""
    td = _thread_dir(project_root, thread_id)
    td.mkdir(parents=True, exist_ok=True)

    messages_file = td / "messages.jsonl"
    with messages_file.open("a", encoding="utf-8") as f:
        f.write(msg.to_jsonl() + "\n")

    # Commit to ledger branch
    rel_path = f"chat/threads/{thread_id}/messages.jsonl"
    ledger_add_and_commit(
        project_root,
        paths=[rel_path],
        message=f"chat: message in {thread_id}",
    )


def _parse_notes_messages(notes_content: str) -> list[ChatMessage]:
    """Parse ChatMessage list from git notes JSONL content."""
    messages: list[ChatMessage] = []
    for line in notes_content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            messages.append(ChatMessage.from_jsonl(line))
        except Exception as e:
            logger.warning("Skipping corrupt note line: %s", e)
    return messages


def _try_decrypt_messages(messages: list[ChatMessage], project_root: Path) -> list[ChatMessage]:
    """Attempt to decrypt encrypted messages in-place.

    If the key is unavailable, replaces text with '[encrypted]'.
    """
    for msg in messages:
        if msg.flags.encrypted and is_encrypted(msg.text):
            try:
                msg.text = decrypt_text(msg.text, project_root)
            except ValueError:
                msg.text = "[encrypted]"
    return messages


# ═══════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════


def send_message(
    project_root: Path,
    text: str,
    *,
    user: str = "",
    thread_id: str | None = None,
    run_id: str | None = None,
    trace_id: str | None = None,
    publish: bool = False,
    encrypt: bool = False,
    source: str = "manual",
) -> ChatMessage:
    """Send a message.

    Routing:
      - If ``run_id`` is set → writes JSONL line to git notes on the run's tag
      - If ``thread_id`` is set → appends to thread's messages.jsonl
      - If both set → writes to both locations
      - If neither → creates/uses the 'general' thread

    Args:
        project_root: Repository root.
        text: Message text.
        user: Author (defaults to git config user.name).
        thread_id: Thread to post in (None for run-only or general).
        run_id: Run to attach this message to (None for thread-only).
        publish: Mark as eligible for public rendering.
        encrypt: Encrypt the text field using CONTENT_VAULT_ENC_KEY.
        source: Message source: "manual", "trace", or "system".

    Returns:
        The created ChatMessage.

    Raises:
        ValueError: If encrypt=True and CONTENT_VAULT_ENC_KEY is not set.
    """
    # Ensure ledger worktree
    ensure_worktree(project_root)

    # Resolve user
    if not user:
        user = current_user(project_root)

    # Encrypt if requested (before creating message — encrypts the text)
    actual_text = text
    encrypted = False
    if encrypt:
        actual_text = encrypt_text(text, project_root)  # raises ValueError if no key
        encrypted = True

    # Parse @-references from original text (before encryption)
    refs = parse_refs(text)

    # Build message
    import socket
    msg = ChatMessage(
        user=user,
        hostname=socket.gethostname(),
        text=actual_text,
        thread_id=thread_id,
        run_id=run_id,
        trace_id=trace_id,
        refs=refs,
        source=source,
        flags=MessageFlags(publish=publish, encrypted=encrypted),
    )
    msg.ensure_id()

    # Route: neither run_id nor thread_id → use general thread
    effective_thread_id = thread_id
    if not run_id and not thread_id:
        effective_thread_id = GENERAL_THREAD_ID
        msg.thread_id = GENERAL_THREAD_ID
        # Ensure general thread exists
        _ensure_general_thread(project_root, user)

    # Write to git notes (run-attached)
    if run_id:
        tag_sha = _tag_object_sha(project_root, run_id)
        if tag_sha:
            notes_append(
                project_root,
                ref=NOTES_REF,
                target=tag_sha,
                content=msg.to_jsonl(),
            )
            logger.debug("Message %s written to notes on %s", msg.id, run_id)
        else:
            logger.warning(
                "Run tag for %s not found — message %s not attached to run notes",
                run_id, msg.id,
            )

    # Write to thread file
    if effective_thread_id:
        _append_thread_message(project_root, effective_thread_id, msg)
        logger.debug("Message %s written to thread %s", msg.id, effective_thread_id)

    # Publish to event bus
    if _bus is not None:
        try:
            _bus.publish(
                "chat:message",
                key=msg.id,
                data={
                    "user": msg.user,
                    "thread_id": msg.thread_id,
                    "run_id": msg.run_id,
                    "source": msg.source,
                    "encrypted": msg.flags.encrypted,
                    "preview": text[:80] if not encrypt else "[encrypted]",
                },
            )
        except Exception:
            pass  # bus failure must never break chat

    logger.info("Message sent: %s (run=%s, thread=%s)", msg.id, run_id, effective_thread_id)
    return msg


def _ensure_general_thread(project_root: Path, user: str) -> None:
    """Ensure the 'general' thread exists (idempotent)."""
    td = _thread_dir(project_root, GENERAL_THREAD_ID)
    thread_file = td / "thread.json"
    if thread_file.is_file():
        return

    thread = Thread(
        thread_id=GENERAL_THREAD_ID,
        title="General",
        created_by=user,
    )
    td.mkdir(parents=True, exist_ok=True)
    thread_file.write_text(
        json.dumps(thread.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    ledger_add_and_commit(
        project_root,
        paths=[f"chat/threads/{GENERAL_THREAD_ID}/thread.json"],
        message="chat: create general thread",
    )


def list_messages(
    project_root: Path,
    *,
    run_id: str | None = None,
    thread_id: str | None = None,
    n: int = 50,
) -> list[ChatMessage]:
    """List messages, newest-first.

    If ``run_id`` is set, reads from git notes.
    If ``thread_id`` is set, reads from thread files.
    If both set, merges and deduplicates by id.

    Auto-decrypts if CONTENT_VAULT_ENC_KEY is available.
    """
    messages: list[ChatMessage] = []
    seen_ids: set[str] = set()

    # Read from git notes (run-attached)
    if run_id:
        tag_sha = _tag_object_sha(project_root, run_id)
        if tag_sha:
            content = notes_show(project_root, ref=NOTES_REF, target=tag_sha)
            if content:
                for msg in _parse_notes_messages(content):
                    if msg.id not in seen_ids:
                        messages.append(msg)
                        seen_ids.add(msg.id)

    # Read from thread files
    if thread_id:
        td = _thread_dir(project_root, thread_id)
        for msg in _read_thread_messages(td):
            if msg.id not in seen_ids:
                messages.append(msg)
                seen_ids.add(msg.id)

    # Sort newest-first by timestamp
    messages.sort(key=lambda m: m.ts, reverse=True)

    # Limit
    messages = messages[:n]

    # Auto-decrypt
    _try_decrypt_messages(messages, project_root)

    return messages


def delete_message(
    project_root: Path,
    *,
    thread_id: str,
    message_id: str,
) -> bool:
    """Delete a message from a thread by its ID.

    Rewrites the thread's ``messages.jsonl`` without the target line
    and commits the change to the ledger branch.

    Args:
        project_root: Repository root.
        thread_id: Thread containing the message.
        message_id: The message ``id`` field to remove.

    Returns:
        True if the message was found and deleted, False if not found.
    """
    ensure_worktree(project_root)

    td = _thread_dir(project_root, thread_id)
    messages_file = td / "messages.jsonl"

    if not messages_file.is_file():
        return False

    lines = messages_file.read_text(encoding="utf-8").splitlines()
    kept: list[str] = []
    found = False

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        try:
            msg = ChatMessage.from_jsonl(line_stripped)
            if msg.id == message_id:
                found = True
                continue  # skip this message
        except Exception:
            pass  # keep corrupt lines to avoid data loss
        kept.append(line_stripped)

    if not found:
        return False

    # Rewrite the file
    messages_file.write_text(
        "\n".join(kept) + ("\n" if kept else ""),
        encoding="utf-8",
    )

    # Commit to ledger branch
    rel_path = f"chat/threads/{thread_id}/messages.jsonl"
    ledger_add_and_commit(
        project_root,
        paths=[rel_path],
        message=f"chat: deleted message {message_id} from {thread_id}",
    )

    # Emit event
    if _bus:
        _bus.publish("chat:message_deleted", data={
            "thread_id": thread_id,
            "message_id": message_id,
        })

    logger.info("Deleted message %s from thread %s", message_id, thread_id)
    return True


def delete_thread(
    project_root: Path,
    *,
    thread_id: str,
) -> bool:
    """Delete an entire thread and all its messages.

    Removes the thread directory from the ledger worktree and commits
    the change.

    Args:
        project_root: Repository root.
        thread_id: Thread to delete.

    Returns:
        True if the thread was found and deleted, False if not found.

    Raises:
        ValueError: If attempting to delete the general thread.
    """
    if thread_id == GENERAL_THREAD_ID:
        raise ValueError("Cannot delete the general thread")

    ensure_worktree(project_root)

    td = _thread_dir(project_root, thread_id)
    if not td.is_dir():
        return False

    # Remove the directory from git tracking first
    import shutil
    rel_path = f"chat/threads/{thread_id}"
    from src.core.services.ledger.worktree import _run_ledger_git
    _run_ledger_git("rm", "-rf", rel_path, project_root=project_root)

    # Also remove from filesystem (in case git rm didn't catch untracked files)
    if td.is_dir():
        shutil.rmtree(td)

    # Commit
    ledger_add_and_commit(
        project_root,
        paths=[],  # git rm already staged
        message=f"chat: deleted thread {thread_id}",
    )

    # Emit event
    if _bus:
        _bus.publish("chat:thread_deleted", data={
            "thread_id": thread_id,
        })

    # Push to remote so other systems see the deletion
    import threading
    def _bg_push():
        try:
            push_chat(project_root)
        except Exception as exc:
            logger.warning("Background push after thread delete failed: %s", exc)
    t = threading.Thread(target=_bg_push, daemon=True)
    t.start()

    logger.info("Deleted thread %s", thread_id)
    return True


def update_message_flags(
    project_root: Path,
    *,
    thread_id: str,
    message_id: str,
    publish: bool | None = None,
    encrypt: bool | None = None,
) -> ChatMessage | None:
    """Update flags on an existing message.

    Supports toggling ``publish`` and ``encrypt`` flags.
    When toggling encrypt:
      - encrypt=True  → encrypts the text field (if not already encrypted).
      - encrypt=False → decrypts the text field (if currently encrypted).

    Args:
        project_root: Repository root.
        thread_id: Thread containing the message.
        message_id: The message ``id`` field to update.
        publish: New publish flag (None = no change).
        encrypt: New encrypt flag (None = no change).

    Returns:
        The updated ChatMessage, or None if not found.

    Raises:
        ValueError: If encrypt=True and no key configured, or decrypt fails.
    """
    ensure_worktree(project_root)

    td = _thread_dir(project_root, thread_id)
    messages_file = td / "messages.jsonl"

    if not messages_file.is_file():
        return None

    lines = messages_file.read_text(encoding="utf-8").splitlines()
    updated_lines: list[str] = []
    updated_msg: ChatMessage | None = None

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        try:
            msg = ChatMessage.from_jsonl(line_stripped)
        except Exception:
            updated_lines.append(line_stripped)
            continue

        if msg.id == message_id:
            # Toggle publish
            if publish is not None:
                msg.flags.publish = publish

            # Toggle encrypt
            if encrypt is not None:
                if encrypt and not msg.flags.encrypted:
                    # Encrypt the text
                    msg.text = encrypt_text(msg.text, project_root)
                    msg.flags.encrypted = True
                elif not encrypt and msg.flags.encrypted:
                    # Decrypt the text
                    if is_encrypted(msg.text):
                        msg.text = decrypt_text(msg.text, project_root)
                    msg.flags.encrypted = False

            updated_msg = msg
            updated_lines.append(msg.to_jsonl())
        else:
            updated_lines.append(line_stripped)

    if not updated_msg:
        return None

    # Rewrite the file
    messages_file.write_text(
        "\n".join(updated_lines) + ("\n" if updated_lines else ""),
        encoding="utf-8",
    )

    # Commit to ledger branch
    rel_path = f"chat/threads/{thread_id}/messages.jsonl"
    action_parts = []
    if publish is not None:
        action_parts.append(f"publish={'on' if publish else 'off'}")
    if encrypt is not None:
        action_parts.append(f"encrypt={'on' if encrypt else 'off'}")
    ledger_add_and_commit(
        project_root,
        paths=[rel_path],
        message=f"chat: updated {message_id} ({', '.join(action_parts)})",
    )

    # Emit event
    if _bus:
        _bus.publish("chat:message_updated", data={
            "thread_id": thread_id,
            "message_id": message_id,
            "flags": {"publish": updated_msg.flags.publish, "encrypted": updated_msg.flags.encrypted},
        })

    logger.info("Updated message %s flags: %s", message_id, ", ".join(action_parts))
    return updated_msg

def create_thread(
    project_root: Path,
    title: str,
    *,
    user: str = "",
    anchor_run: str | None = None,
    tags: list[str] | None = None,
) -> Thread:
    """Create a new thread. Writes thread.json to the ledger branch.

    Args:
        project_root: Repository root.
        title: Thread title.
        user: Creator (defaults to git config user.name).
        anchor_run: Optional run_id to anchor the thread to.
        tags: Optional classification tags.

    Returns:
        The created Thread.
    """
    ensure_worktree(project_root)

    if not user:
        user = current_user(project_root)

    thread = Thread(
        title=title,
        created_by=user,
        anchor_run=anchor_run,
        tags=tags or [],
    )
    thread.ensure_id()

    # Write thread.json
    td = _thread_dir(project_root, thread.thread_id)
    td.mkdir(parents=True, exist_ok=True)
    thread_file = td / "thread.json"
    thread_file.write_text(
        json.dumps(thread.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )

    # Commit
    rel_path = f"chat/threads/{thread.thread_id}/thread.json"
    ledger_add_and_commit(
        project_root,
        paths=[rel_path],
        message=f"chat: create thread '{title}'",
    )

    logger.info("Thread created: %s (%s)", thread.thread_id, title)
    return thread


def list_threads(project_root: Path) -> list[Thread]:
    """List all threads from .scp-ledger/chat/threads/*/thread.json.

    Returns newest-first by created_at.
    """
    threads_root = _threads_dir(project_root)
    if not threads_root.is_dir():
        return []

    threads: list[Thread] = []
    try:
        for td in sorted(threads_root.iterdir()):
            if not td.is_dir():
                continue
            thread_file = td / "thread.json"
            if not thread_file.is_file():
                continue
            try:
                data = json.loads(thread_file.read_text(encoding="utf-8"))
                threads.append(Thread.model_validate(data))
            except Exception as e:
                logger.warning("Skipping corrupt thread %s: %s", td.name, e)
    except OSError as e:
        logger.error("Failed to list threads: %s", e)

    # Newest first
    threads.sort(key=lambda t: t.created_at, reverse=True)
    return threads


# ═══════════════════════════════════════════════════════════════════════
#  Push / Pull
# ═══════════════════════════════════════════════════════════════════════


def push_chat(project_root: Path) -> bool:
    """Push chat data to origin.

    Pushes:
      1. ``refs/notes/scp-chat`` (run-attached messages)
      2. Ledger branch (which contains thread files)

    The ledger branch push is handled by the ledger push mechanism.
    This function handles only the notes ref.
    """
    from src.core.services.ledger.ledger_ops import push_ledger

    # Push notes ref
    r = _run_main_git(
        "push", "origin", NOTES_REF,
        project_root=project_root,
        timeout=30,
    )
    notes_ok = r.returncode == 0
    if not notes_ok:
        stderr = r.stderr.strip()
        # "everything up-to-date" or "remote rejected" for nonexistent ref are OK
        if "up-to-date" in stderr.lower() or "everything" in stderr.lower():
            notes_ok = True
        else:
            logger.warning("Chat notes push issue: %s", stderr)

    # Push ledger branch (includes thread files)
    ledger_ok = push_ledger(project_root)

    return notes_ok and ledger_ok


def pull_chat(project_root: Path) -> bool:
    """Pull chat data from origin.

    Pulls:
      1. ``refs/notes/scp-chat`` (run-attached messages)
      2. Ledger branch (which contains thread files)
    """
    from src.core.services.ledger.ledger_ops import pull_ledger

    # Fetch notes ref
    r = _run_main_git(
        "fetch", "origin",
        f"{NOTES_REF}:{NOTES_REF}",
        project_root=project_root,
        timeout=30,
    )
    notes_ok = r.returncode == 0
    if not notes_ok:
        stderr = r.stderr.strip()
        if "couldn't find remote" in stderr.lower() or "no match" in stderr.lower():
            notes_ok = True  # Notes don't exist on remote yet — fine
        else:
            logger.warning("Chat notes fetch issue: %s", stderr)

    # Pull ledger branch (includes thread files)
    ledger_ok = pull_ledger(project_root)

    return notes_ok and ledger_ok
