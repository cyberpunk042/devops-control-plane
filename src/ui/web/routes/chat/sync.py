"""Chat sync — push/pull and combined polling."""

from __future__ import annotations

import logging

from flask import jsonify, request

from src.core.services.chat import (
    list_messages,
    list_threads,
    pull_chat,
    push_chat,
)
from src.ui.web.helpers import project_root as _project_root, requires_git_auth
from src.ui.web.routes.integrations.gh_helpers import requires_gh_auth

from . import chat_bp

logger = logging.getLogger(__name__)


@chat_bp.route("/chat/poll", methods=["POST"])
@requires_gh_auth
@requires_git_auth
def chat_poll():
    """Single poll endpoint: pull remote, return threads + messages.

    Body (JSON):
        thread_id — thread to read messages from (required)
        n         — max messages (default 100)
    """
    try:
        root = _project_root()
        body = request.get_json(silent=True) or {}
        thread_id = body.get("thread_id", "")
        n = body.get("n", 100)

        # 1. Pull from remote (non-fatal)
        pulled = False
        try:
            pulled = pull_chat(root)
        except Exception:
            pass

        # 2. Read threads with message_count
        threads = list_threads(root)
        thread_data = []
        for t in threads:
            td = t.model_dump(mode="json")
            try:
                from src.core.services.chat.chat_ops import _thread_dir
                msg_file = _thread_dir(root, t.thread_id) / "messages.jsonl"
                if msg_file.is_file():
                    td["message_count"] = sum(
                        1 for _ in msg_file.open("r", encoding="utf-8")
                    )
                else:
                    td["message_count"] = 0
            except Exception:
                td["message_count"] = 0
            thread_data.append(td)

        # 3. Read messages for the requested thread
        messages = []
        if thread_id:
            msgs = list_messages(root, thread_id=thread_id, n=n)
            for m in msgs:
                d = m.model_dump(mode="json")
                if d.get("trace_id") and d.get("source") == "trace":
                    from src.core.services.trace import get_trace
                    t = get_trace(root, d["trace_id"])
                    d["trace_shared"] = t.shared if t else False
                messages.append(d)

        return jsonify({
            "pulled": pulled,
            "threads": thread_data,
            "messages": messages,
        })
    except Exception as e:
        logger.exception("Failed to poll chat")
        return jsonify({"error": str(e)}), 500


@chat_bp.route("/chat/sync", methods=["POST"])
@requires_gh_auth
@requires_git_auth
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
