"""Git history & maintenance — gc, repack, history reset, filter-repo."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import git_ops
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import requires_git_auth, project_root as _project_root

from . import integrations_bp


@integrations_bp.route("/git/gc", methods=["POST"])
@run_tracked("git", "git:gc")
def git_gc_route():  # type: ignore[no-untyped-def]
    """Run git gc to optimise the repository.

    JSON body:
        aggressive: optional bool (default false)
    """
    data = request.get_json(silent=True) or {}
    aggressive = bool(data.get("aggressive", False))

    result = git_ops.git_gc(_project_root(), aggressive=aggressive)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/history-reset", methods=["POST"])
@requires_git_auth
@run_tracked("git", "git:history-reset")
def git_history_reset_route():  # type: ignore[no-untyped-def]
    """Reset git history to a single commit (orphan branch).

    This is destructive and irreversible.

    JSON body:
        message: optional commit message (default: "Initial commit (history reset)")
    """
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()

    result = git_ops.git_history_reset(
        _project_root(),
        **({"message": message} if message else {}),
    )
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/filter-repo", methods=["POST"])
@requires_git_auth
@run_tracked("git", "git:filter-repo")
def git_filter_repo_route():  # type: ignore[no-untyped-def]
    """Scrub specific files/paths from entire git history.

    Requires git-filter-repo to be installed (via tool install system).

    JSON body:
        paths: list of file paths to remove from history (required)
        force: optional bool (default false)
    """
    data = request.get_json(silent=True) or {}
    paths = data.get("paths", [])
    if not paths or not isinstance(paths, list):
        return jsonify({"error": "A non-empty 'paths' list is required"}), 400

    force = bool(data.get("force", False))

    result = git_ops.git_filter_repo(
        _project_root(), paths=paths, force=force,
    )
    if "error" in result:
        # If tool is missing, return 424 (Failed Dependency) with install hint
        status = 424 if result.get("tool_name") else 400
        return jsonify(result), status
    return jsonify(result)
