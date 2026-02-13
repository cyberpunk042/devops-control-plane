"""
Integration routes — Git, GitHub, and CI/CD endpoints.

Blueprint: integrations_bp
Prefix: /api

Thin HTTP wrappers over ``src.core.services.git_ops``.

Endpoints:
    GET  /git/status          — branch, dirty state, ahead/behind
    GET  /git/log             — recent commit history
    POST /git/commit          — stage + commit
    POST /git/pull            — pull from remote
    POST /git/push            — push to remote
    GET  /gh/pulls            — open pull requests
    GET  /gh/actions/runs     — recent workflow runs
    POST /gh/actions/dispatch — trigger a workflow
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import git_ops

integrations_bp = Blueprint("integrations", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


# ── Git Status ──────────────────────────────────────────────────────


@integrations_bp.route("/git/status")
def git_status():  # type: ignore[no-untyped-def]
    """Git repository status: branch, dirty files, ahead/behind tracking."""
    return jsonify(git_ops.git_status(_project_root()))


# ── Git Log ─────────────────────────────────────────────────────────


@integrations_bp.route("/git/log")
def git_log():  # type: ignore[no-untyped-def]
    """Recent commit history."""
    n = request.args.get("n", 10, type=int)
    return jsonify(git_ops.git_log(_project_root(), n=n))


# ── Git Commit ──────────────────────────────────────────────────────


@integrations_bp.route("/git/commit", methods=["POST"])
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


# ── Git Pull ────────────────────────────────────────────────────────


@integrations_bp.route("/git/pull", methods=["POST"])
def git_pull():  # type: ignore[no-untyped-def]
    """Pull from remote."""
    data = request.get_json(silent=True) or {}
    rebase = data.get("rebase", False)

    result = git_ops.git_pull(_project_root(), rebase=rebase)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── Git Push ────────────────────────────────────────────────────────


@integrations_bp.route("/git/push", methods=["POST"])
def git_push():  # type: ignore[no-untyped-def]
    """Push to remote."""
    data = request.get_json(silent=True) or {}
    force = data.get("force", False)

    result = git_ops.git_push(_project_root(), force=force)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── GitHub: Status ──────────────────────────────────────────────────


@integrations_bp.route("/integrations/gh/status")
def gh_status_extended():  # type: ignore[no-untyped-def]
    """Extended GitHub status — version, repo, auth details."""
    return jsonify(git_ops.gh_status(_project_root()))


# ── GitHub: Pull Requests ───────────────────────────────────────────


@integrations_bp.route("/gh/pulls")
def gh_pulls():  # type: ignore[no-untyped-def]
    """List open pull requests."""
    return jsonify(git_ops.gh_pulls(_project_root()))


# ── GitHub: Actions ─────────────────────────────────────────────────


@integrations_bp.route("/gh/actions/runs")
def gh_actions_runs():  # type: ignore[no-untyped-def]
    """Recent workflow run history."""
    n = request.args.get("n", 10, type=int)
    return jsonify(git_ops.gh_actions_runs(_project_root(), n=n))


@integrations_bp.route("/gh/actions/dispatch", methods=["POST"])
def gh_actions_dispatch():  # type: ignore[no-untyped-def]
    """Trigger a workflow via repository dispatch."""
    data = request.get_json(silent=True) or {}
    workflow = data.get("workflow", "")
    if not workflow:
        return jsonify({"error": "Missing 'workflow' field"}), 400

    ref = data.get("ref")
    result = git_ops.gh_actions_dispatch(_project_root(), workflow, ref=ref)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── GitHub: Workflows list ──────────────────────────────────────────


@integrations_bp.route("/gh/actions/workflows")
def gh_actions_workflows():  # type: ignore[no-untyped-def]
    """List available workflows."""
    return jsonify(git_ops.gh_actions_workflows(_project_root()))


# ── GitHub: User ────────────────────────────────────────────────────


@integrations_bp.route("/gh/user")
def gh_user():  # type: ignore[no-untyped-def]
    """Currently authenticated GitHub user."""
    return jsonify(git_ops.gh_user(_project_root()))


# ── GitHub: Repo Info ───────────────────────────────────────────────


@integrations_bp.route("/gh/repo/info")
def gh_repo_info():  # type: ignore[no-untyped-def]
    """Detailed repository information (visibility, description, etc)."""
    return jsonify(git_ops.gh_repo_info(_project_root()))


# ── GitHub: Auth Logout ─────────────────────────────────────────────


@integrations_bp.route("/gh/auth/logout", methods=["POST"])
def gh_auth_logout():  # type: ignore[no-untyped-def]
    """Logout from GitHub CLI."""
    result = git_ops.gh_auth_logout(_project_root())
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── GitHub: Create Repository ───────────────────────────────────────


@integrations_bp.route("/gh/repo/create", methods=["POST"])
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


# ── GitHub: Set Visibility ──────────────────────────────────────────


@integrations_bp.route("/gh/repo/visibility", methods=["POST"])
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


# ── Git: Remotes Management ─────────────────────────────────────────


@integrations_bp.route("/git/remotes")
def git_remotes():  # type: ignore[no-untyped-def]
    """List all git remotes with their URLs."""
    return jsonify(git_ops.git_remotes(_project_root()))


@integrations_bp.route("/git/remote/add", methods=["POST"])
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
def git_remote_remove():  # type: ignore[no-untyped-def]
    """Remove a git remote by name (defaults to origin)."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "origin").strip()
    result = git_ops.git_remote_remove(_project_root(), name)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/remote/rename", methods=["POST"])
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


# ── GitHub: Default Branch ──────────────────────────────────────────


@integrations_bp.route("/gh/repo/default-branch", methods=["POST"])
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

