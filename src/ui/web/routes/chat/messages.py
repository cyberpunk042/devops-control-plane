"""Chat message operations — list, send, delete, update flags, move."""

from __future__ import annotations

import logging
import threading

from flask import jsonify, request

from src.core.services.chat import (
    delete_message,
    list_messages,
    pull_chat,
    push_chat,
    send_message,
    update_message_flags,
)
from src.core.services.git_auth import is_auth_ok
from src.ui.web.helpers import project_root as _project_root, requires_git_auth
from src.ui.web.routes.integrations.gh_helpers import requires_gh_auth

from . import chat_bp

logger = logging.getLogger(__name__)


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
        if is_auth_ok():
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
        msgs_out = []
        for m in messages:
            d = m.model_dump(mode="json")
            if d.get("trace_id") and d.get("source") == "trace":
                from src.core.services.trace import get_trace
                t = get_trace(root, d["trace_id"])
                d["trace_shared"] = t.shared if t else False
            msgs_out.append(d)
        return jsonify({
            "messages": msgs_out,
        })
    except Exception as e:
        logger.exception("Failed to list messages")
        return jsonify({"error": str(e)}), 500


@chat_bp.route("/chat/send", methods=["POST"])
@requires_gh_auth
@requires_git_auth
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
        if is_auth_ok():
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


@chat_bp.route("/chat/delete-message", methods=["POST"])
@requires_gh_auth
@requires_git_auth
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


@chat_bp.route("/chat/update-message", methods=["POST"])
@requires_gh_auth
@requires_git_auth
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


@chat_bp.route("/chat/move-message", methods=["POST"])
@requires_gh_auth
@requires_git_auth
def chat_move_message():
    """Move or copy a message to a different thread.

    Body (JSON):
        source_thread_id — thread the message is in now (required)
        message_id       — the message ID to move/copy (required)
        target_thread_id — thread to post to (required)
        delete_source    — if true, delete from source (move); else copy (default true)
    """
    try:
        root = _project_root()
        body = request.get_json(silent=True) or {}
        src_thread = body.get("source_thread_id", "")
        msg_id = body.get("message_id", "")
        tgt_thread = body.get("target_thread_id", "")
        delete_src = body.get("delete_source", True)

        if not src_thread or not msg_id or not tgt_thread:
            return jsonify({"error": "source_thread_id, message_id, and target_thread_id are required"}), 400

        if src_thread == tgt_thread:
            return jsonify({"error": "Source and target thread cannot be the same"}), 400

        # Find the source message
        msgs = list_messages(root, thread_id=src_thread, n=9999)
        source_msg = None
        for m in msgs:
            if m.id == msg_id:
                source_msg = m
                break

        if not source_msg:
            return jsonify({"error": f"Message {msg_id} not found in thread {src_thread}"}), 404

        # Post as a new message in the target thread (fresh timestamp)
        new_msg = send_message(
            root,
            source_msg.text,
            user=source_msg.user,
            thread_id=tgt_thread,
            trace_id=source_msg.trace_id,
            source=source_msg.source,
            publish=source_msg.flags.publish if source_msg.flags else False,
            encrypt=False,  # Don't re-encrypt — text is already encrypted if it was
        )

        # Delete from source if requested (move)
        deleted = False
        if delete_src:
            deleted = delete_message(root, thread_id=src_thread, message_id=msg_id)

        # Push in background
        if is_auth_ok():
            from src.core.services.ledger.worktree import push_ledger_branch
            threading.Thread(target=push_ledger_branch, args=(root,), daemon=True).start()

        return jsonify({
            "new_message_id": new_msg.id,
            "deleted_source": deleted,
            "target_thread_id": tgt_thread,
        })
    except Exception as e:
        logger.exception("Failed to move/copy message")
        return jsonify({"error": str(e)}), 500
