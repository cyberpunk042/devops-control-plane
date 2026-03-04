"""GitHub repo management — create, visibility, default branch."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import git_ops
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import project_root as _project_root
from src.ui.web.routes.integrations.gh_helpers import requires_gh_auth

from . import integrations_bp


@integrations_bp.route("/gh/repo/create", methods=["POST"])
@run_tracked("setup", "setup:gh_repo")
@requires_gh_auth
def gh_repo_create():  # type: ignore[no-untyped-def]
    """Create a new GitHub repository."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Repository name is required"}), 400

    result = git_ops.gh_repo_create(
        _project_root(),
        name,
        private=data.get("private", True),
        description=data.get("description", ""),
        add_remote=data.get("add_remote", True),
    )
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/gh/repo/visibility", methods=["POST"])
@run_tracked("setup", "setup:gh_visibility")
@requires_gh_auth
def gh_repo_set_visibility():  # type: ignore[no-untyped-def]
    """Change repository visibility (public/private)."""
    data = request.get_json(silent=True) or {}
    visibility = data.get("visibility", "").strip()
    if not visibility:
        return jsonify({"error": "Missing 'visibility' field"}), 400

    result = git_ops.gh_repo_set_visibility(_project_root(), visibility)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/gh/repo/default-branch", methods=["POST"])
@run_tracked("setup", "setup:gh_default_branch")
@requires_gh_auth
def gh_repo_set_default_branch():  # type: ignore[no-untyped-def]
    """Change the default branch on GitHub."""
    data = request.get_json(silent=True) or {}
    branch = data.get("branch", "").strip()
    if not branch:
        return jsonify({"error": "Missing 'branch' field"}), 400
    result = git_ops.gh_repo_set_default_branch(_project_root(), branch)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/gh/repo/rename", methods=["POST"])
@run_tracked("setup", "setup:gh_repo_rename")
@requires_gh_auth
def gh_repo_rename():  # type: ignore[no-untyped-def]
    """Rename the GitHub repository.

    JSON body:
        new_name: new repository name (required)
    """
    data = request.get_json(silent=True) or {}
    new_name = data.get("new_name", "").strip()
    if not new_name:
        return jsonify({"error": "Missing 'new_name' field"}), 400

    result = git_ops.gh_repo_rename(_project_root(), new_name)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)
