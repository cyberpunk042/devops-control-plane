"""
Chat API routes — serve chat data for the Content Vault Chat sub-tab.

Blueprint: chat_bp
Prefix: /api (applied by server.py)

Endpoints:
    /api/chat/threads            — list all threads
    /api/chat/threads/create     — create a new thread
    /api/chat/messages           — list messages by thread/run
    /api/chat/send               — send a message
    /api/chat/delete-message     — delete a message
    /api/chat/refs/resolve       — resolve an @-reference
    /api/chat/refs/autocomplete  — autocomplete @-reference prefix
    /api/chat/sync               — push/pull chat data
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services.chat import (
    autocomplete,
    create_thread,
    delete_message,
    list_messages,
    list_threads,
    pull_chat,
    push_chat,
    resolve_ref,
    send_message,
    update_message_flags,
)

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


# ── List threads ───────────────────────────────────────────────────

@chat_bp.route("/chat/threads")
def chat_threads():
    """List all chat threads, newest-first."""
    try:
        root = _project_root()
        threads = list_threads(root)
        return jsonify({
            "threads": [t.model_dump(mode="json") for t in threads],
        })
    except Exception as e:
        logger.exception("Failed to list threads")
        return jsonify({"error": str(e)}), 500


# ── Create thread ──────────────────────────────────────────────────

@chat_bp.route("/chat/threads/create", methods=["POST"])
def chat_thread_create():
    """Create a new chat thread."""
    try:
        root = _project_root()
        body = request.get_json(silent=True) or {}

        title = body.get("title", "").strip()
        if not title:
            return jsonify({"error": "Title is required"}), 400

        thread = create_thread(
            root,
            title=title,
            user=body.get("user", ""),
            anchor_run=body.get("anchor_run") or None,
            tags=body.get("tags") or [],
        )
        return jsonify(thread.model_dump(mode="json"))
    except Exception as e:
        logger.exception("Failed to create thread")
        return jsonify({"error": str(e)}), 500


# ── List messages ──────────────────────────────────────────────────

@chat_bp.route("/chat/messages")
def chat_messages():
    """List messages for a thread or run.

    Query params:
        thread_id — thread to read from
        run_id    — run to read notes from
        n         — max messages to return (default 50)
    """
    try:
        root = _project_root()
        thread_id = request.args.get("thread_id") or None
        run_id = request.args.get("run_id") or None
        n = request.args.get("n", 50, type=int)

        # Auto-pull latest from origin in background (non-blocking).
        # Messages load instantly from local; pull results appear on next load.
        # Only attempt if auth is verified — avoids hanging on SSH passphrase.
        from src.core.services.git_auth import is_auth_ok as _auth_ok
        if _auth_ok():
            def _bg_pull(r):
                try:
                    pull_chat(r)
                except Exception:
                    pass
            threading.Thread(target=_bg_pull, args=(root,), daemon=True).start()

        messages = list_messages(
            root,
            thread_id=thread_id,
            run_id=run_id,
            n=n,
        )
        return jsonify({
            "messages": [m.model_dump(mode="json") for m in messages],
        })
    except Exception as e:
        logger.exception("Failed to list messages")
        return jsonify({"error": str(e)}), 500


# ── Send message ───────────────────────────────────────────────────

@chat_bp.route("/chat/send", methods=["POST"])
def chat_send():
    """Send a chat message.

    Body (JSON):
        text       — message text (required)
        thread_id  — thread to post in (optional)
        run_id     — run to attach to (optional)
        encrypt    — encrypt the message (optional, default false)
        source     — "manual", "trace", or "system" (optional, default "manual")
    """
    try:
        root = _project_root()
        body = request.get_json(silent=True) or {}

        text = body.get("text", "").strip()
        if not text:
            return jsonify({"error": "Message text is required"}), 400

        msg = send_message(
            root,
            text=text,
            thread_id=body.get("thread_id") or None,
            run_id=body.get("run_id") or None,
            encrypt=body.get("encrypt", False),
            publish=body.get("publish", False),
            source=body.get("source", "manual"),
        )
        # Return decrypted text to the client for immediate rendering.
        # The stored version stays encrypted on disk.
        result = msg.model_dump(mode="json")
        if msg.flags.encrypted and msg.text.startswith("ENC:"):
            try:
                from src.core.services.chat.chat_crypto import decrypt_text
                result["text"] = decrypt_text(msg.text, root)
            except Exception:
                pass  # fall back to encrypted text if key unavailable

        # Auto-push to origin in background (don't block the response)
        # Only attempt if auth is verified.
        from src.core.services.git_auth import is_auth_ok as _auth_ok2
        if _auth_ok2():
            def _bg_push(r):
                try:
                    push_chat(r)
                except Exception:
                    pass
            threading.Thread(target=_bg_push, args=(root,), daemon=True).start()

        return jsonify(result)
    except ValueError as e:
        # ValueError raised when encrypt=True but no key configured
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Failed to send message")
        return jsonify({"error": str(e)}), 500


# ── Delete message ──────────────────────────────────────────────────────

@chat_bp.route("/chat/delete-message", methods=["POST"])
def chat_delete_message():
    """Delete a chat message by ID.

    Body (JSON):
        thread_id  — thread containing the message (required)
        message_id — message ID to delete (required)
    """
    try:
        root = _project_root()
        body = request.get_json(silent=True) or {}

        thread_id = body.get("thread_id", "").strip()
        message_id = body.get("message_id", "").strip()

        if not thread_id:
            return jsonify({"error": "thread_id is required"}), 400
        if not message_id:
            return jsonify({"error": "message_id is required"}), 400

        deleted = delete_message(
            root,
            thread_id=thread_id,
            message_id=message_id,
        )

        if not deleted:
            return jsonify({"error": "Message not found"}), 404

        return jsonify({"deleted": True, "message_id": message_id})
    except Exception as e:
        logger.exception("Failed to delete message")
        return jsonify({"error": str(e)}), 500


# ── Update message flags ──────────────────────────────────────────────

@chat_bp.route("/chat/update-message", methods=["POST"])
def chat_update_message():
    """Update flags on an existing chat message.

    Body (JSON):
        thread_id  — thread containing the message (required)
        message_id — message ID to update (required)
        publish    — new publish flag (optional, bool)
        encrypt    — new encrypt flag (optional, bool)
    """
    try:
        root = _project_root()
        body = request.get_json(silent=True) or {}

        thread_id = body.get("thread_id", "").strip()
        message_id = body.get("message_id", "").strip()

        if not thread_id:
            return jsonify({"error": "thread_id is required"}), 400
        if not message_id:
            return jsonify({"error": "message_id is required"}), 400

        publish = body.get("publish")  # None if absent
        encrypt = body.get("encrypt")  # None if absent

        msg = update_message_flags(
            root,
            thread_id=thread_id,
            message_id=message_id,
            publish=publish,
            encrypt=encrypt,
        )

        if not msg:
            return jsonify({"error": "Message not found"}), 404

        # Return decrypted text for display
        result = msg.model_dump(mode="json")
        if msg.flags.encrypted and msg.text.startswith("ENC:"):
            try:
                from src.core.services.chat.chat_crypto import decrypt_text
                result["text"] = decrypt_text(msg.text, root)
            except Exception:
                pass
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Failed to update message")
        return jsonify({"error": str(e)}), 500


# ── Resolve @-reference ────────────────────────────────────────────

@chat_bp.route("/chat/refs/resolve")
def chat_resolve_ref():
    """Resolve an @-reference to entity metadata.

    Query params:
        ref — reference string, e.g. "@run:run_20260217_detect_a1b2"
    """
    try:
        root = _project_root()
        ref = request.args.get("ref", "")
        if not ref:
            return jsonify({"error": "ref parameter is required"}), 400

        result = resolve_ref(ref, root)
        if result is None:
            return jsonify({"error": "not_found", "ref": ref}), 404

        return jsonify(result)
    except Exception as e:
        logger.exception("Failed to resolve ref")
        return jsonify({"error": str(e)}), 500


# ── Autocomplete @-reference ──────────────────────────────────────

@chat_bp.route("/chat/refs/autocomplete")
def chat_autocomplete():
    """Autocomplete @-reference prefix.

    Query params:
        prefix — partial reference, e.g. "@run:", "@run:run_2026"
    """
    try:
        root = _project_root()
        prefix = request.args.get("prefix", "")
        if not prefix:
            return jsonify({"suggestions": []})

        results = autocomplete(prefix, root)
        return jsonify({"suggestions": results})
    except Exception as e:
        logger.exception("Failed to autocomplete ref")
        return jsonify({"error": str(e), "suggestions": []}), 500


# ── Sync (push/pull) ──────────────────────────────────────────────

@chat_bp.route("/chat/sync", methods=["POST"])
def chat_sync():
    """Push and/or pull chat data to/from origin.

    Body (JSON):
        action — "push", "pull", or "both" (default "both")
    """
    try:
        root = _project_root()
        body = request.get_json(silent=True) or {}
        action = body.get("action", "both")

        pushed = False
        pulled = False

        if action in ("push", "both"):
            pushed = push_chat(root)
        if action in ("pull", "both"):
            pulled = pull_chat(root)

        return jsonify({"pushed": pushed, "pulled": pulled})
    except Exception as e:
        logger.exception("Failed to sync chat")
        return jsonify({"error": str(e)}), 500
