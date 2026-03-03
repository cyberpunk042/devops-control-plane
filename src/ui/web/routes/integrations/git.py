"""Git operations — status, log, commit, pull, push."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import git_ops
from src.core.services.devops.cache import get_cached
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import requires_git_auth, project_root as _project_root

from . import integrations_bp


@integrations_bp.route("/git/status")
def git_status():  # type: ignore[no-untyped-def]
    """Git repository status: branch, dirty files, ahead/behind tracking."""
    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "git",
        lambda: git_ops.git_status(root),
        force=force,
    ))


@integrations_bp.route("/git/log")
def git_log():  # type: ignore[no-untyped-def]
    """Recent commit history."""
    n = request.args.get("n", 10, type=int)
    return jsonify(git_ops.git_log(_project_root(), n=n))


@integrations_bp.route("/git/commit", methods=["POST"])
@run_tracked("git", "git:commit")
def git_commit():  # type: ignore[no-untyped-def]
    """Stage and commit changes.

    JSON body:
        message: commit message (required)
        files: optional list of files to stage (default: all)
    """
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "Commit message is required"}), 400

    files = data.get("files")
    result = git_ops.git_commit(_project_root(), message, files=files)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/pull", methods=["POST"])
@requires_git_auth
@run_tracked("git", "git:pull")
def git_pull():  # type: ignore[no-untyped-def]
    """Pull from remote."""
    data = request.get_json(silent=True) or {}
    rebase = data.get("rebase", False)

    result = git_ops.git_pull(_project_root(), rebase=rebase)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/push", methods=["POST"])
@requires_git_auth
@run_tracked("git", "git:push")
def git_push():  # type: ignore[no-untyped-def]
    """Push to remote."""
    data = request.get_json(silent=True) or {}
    force = data.get("force", False)

    result = git_ops.git_push(_project_root(), force=force)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/ledger/resolve-conflict", methods=["POST"])
def ledger_resolve_conflict_route():  # type: ignore[no-untyped-def]
    """Resolve a ledger rebase conflict.

    JSON body:
        action: "retry" | "skip" | "reset" | "content_merge" | "force_push"
    """
    data = request.get_json(silent=True) or {}
    action = data.get("action", "").strip()
    valid = ("retry", "skip", "reset", "content_merge", "force_push")
    if action not in valid:
        return jsonify({"ok": False, "error": f"action must be one of {valid}"}), 400

    from src.core.services.ledger.worktree import ledger_resolve_conflict
    result = ledger_resolve_conflict(_project_root(), action)
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@integrations_bp.route("/ledger/sync-status")
def ledger_sync_status_route():  # type: ignore[no-untyped-def]
    """Inspect ledger branch divergence between local and remote.

    Returns commit-level and message-level diff so the user can see
    exactly what would be lost with each resolution option.
    """
    from src.core.services.ledger.worktree import ledger_sync_status
    return jsonify(ledger_sync_status(_project_root()))

