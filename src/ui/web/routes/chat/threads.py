"""Chat thread management — list, create, delete."""

from __future__ import annotations

import logging
import threading

from flask import jsonify, request

from src.core.services.chat import (
    create_thread,
    delete_thread,
    list_threads,
    push_chat,
)
from src.core.services.git_auth import is_auth_ok
from src.core.services.ledger.worktree import GitIdentityError
from src.ui.web.helpers import project_root as _project_root, requires_git_auth
from src.ui.web.routes.integrations.gh_helpers import requires_gh_auth

from . import chat_bp

logger = logging.getLogger(__name__)


@chat_bp.route("/chat/threads")
def chat_threads():
    """List all chat threads, newest-first."""
    try:
        root = _project_root()
        threads = list_threads(root)

        # Enrich with message_count and last_message_at for UI
        result = []
        for t in threads:
            td = t.model_dump(mode="json")
            try:
                from src.core.services.chat.chat_ops import _thread_dir
                msg_file = _thread_dir(root, t.thread_id) / "messages.jsonl"
                if msg_file.is_file():
                    lines = msg_file.read_text(encoding="utf-8").strip().splitlines()
                    td["message_count"] = len(lines)
                    # Last message timestamp
                    if lines:
                        import json as _json
                        try:
                            last_msg = _json.loads(lines[-1])
                            td["last_message_at"] = last_msg.get("ts", td["created_at"])
                        except Exception:
                            td["last_message_at"] = td["created_at"]
                    else:
                        td["last_message_at"] = td["created_at"]
                else:
                    td["message_count"] = 0
                    td["last_message_at"] = td["created_at"]
            except Exception:
                td["message_count"] = 0
                td["last_message_at"] = td.get("created_at", "")
            result.append(td)

        # Sort by last activity (most recent first)
        result.sort(key=lambda d: d.get("last_message_at", ""), reverse=True)

        return jsonify({"threads": result})
    except Exception as e:
        logger.exception("Failed to list threads")
        return jsonify({"error": str(e)}), 500


@chat_bp.route("/chat/threads/create", methods=["POST"])
@requires_gh_auth
@requires_git_auth
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

        # Auto-push to origin in background so other systems see the thread
        if is_auth_ok():
            def _bg_push(r):
                try:
                    push_chat(r)
                except Exception:
                    pass
            threading.Thread(target=_bg_push, args=(root,), daemon=True).start()

        return jsonify(thread.model_dump(mode="json"))
    except GitIdentityError as e:
        return jsonify({
            "ok": False,
            "needs": "git_identity",
            "error": str(e),
        }), 400
    except Exception as e:
        logger.exception("Failed to create thread")
        return jsonify({"error": str(e)}), 500


@chat_bp.route("/chat/delete-thread", methods=["POST"])
@requires_gh_auth
@requires_git_auth
def chat_delete_thread():
    """Delete an entire thread and all its messages.

    Body (JSON):
        thread_id — thread to delete (required)
    """
    try:
        root = _project_root()
        body = request.get_json(silent=True) or {}

        thread_id = body.get("thread_id", "").strip()
        if not thread_id:
            return jsonify({"error": "thread_id is required"}), 400

        deleted = delete_thread(
            root,
            thread_id=thread_id,
        )

        if not deleted:
            return jsonify({"error": "Thread not found"}), 404

        return jsonify({"deleted": True, "thread_id": thread_id})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Failed to delete thread")
        return jsonify({"error": str(e)}), 500
