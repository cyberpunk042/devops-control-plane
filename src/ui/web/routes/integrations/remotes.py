"""Git remote management — list, add, remove, rename, set-url."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import git_ops
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import project_root as _project_root

from . import integrations_bp


@integrations_bp.route("/git/remotes")
def git_remotes():  # type: ignore[no-untyped-def]
    """List all git remotes with their URLs."""
    return jsonify(git_ops.git_remotes(_project_root()))


@integrations_bp.route("/git/remote/add", methods=["POST"])
@run_tracked("setup", "setup:git_remote")
def git_remote_add():  # type: ignore[no-untyped-def]
    """Add a new git remote."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    url = data.get("url", "").strip()
    if not name or not url:
        return jsonify({"error": "Both 'name' and 'url' are required"}), 400
    result = git_ops.git_remote_add(_project_root(), name, url)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/remote/remove", methods=["POST"])
@run_tracked("destroy", "destroy:git_remote")
def git_remote_remove():  # type: ignore[no-untyped-def]
    """Remove a git remote by name (defaults to origin)."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "origin").strip()
    result = git_ops.git_remote_remove(_project_root(), name)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/remote/rename", methods=["POST"])
@run_tracked("setup", "setup:git_remote_rename")
def git_remote_rename():  # type: ignore[no-untyped-def]
    """Rename a git remote."""
    data = request.get_json(silent=True) or {}
    old = data.get("old_name", "").strip()
    new = data.get("new_name", "").strip()
    if not old or not new:
        return jsonify({"error": "Both 'old_name' and 'new_name' are required"}), 400
    result = git_ops.git_remote_rename(_project_root(), old, new)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/remote/set-url", methods=["POST"])
@run_tracked("setup", "setup:git_remote_url")
def git_remote_set_url():  # type: ignore[no-untyped-def]
    """Change the URL of a git remote."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    url = data.get("url", "").strip()
    if not name or not url:
        return jsonify({"error": "Both 'name' and 'url' are required"}), 400
    result = git_ops.git_remote_set_url(_project_root(), name, url)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)
