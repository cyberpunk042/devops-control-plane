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

        # Enrich with message_count for UI (seen/unseen badges)
        result = []
        for t in threads:
            td = t.model_dump(mode="json")
            try:
                from src.core.services.chat.chat_ops import _thread_dir
                msg_file = _thread_dir(root, t.thread_id) / "messages.jsonl"
                if msg_file.is_file():
                    td["message_count"] = sum(1 for _ in msg_file.open("r", encoding="utf-8"))
                else:
                    td["message_count"] = 0
            except Exception:
                td["message_count"] = 0
            result.append(td)

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
