"""GitHub observation — status, pulls, actions, workflows, user, repo info."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import git_ops
from src.core.services.devops.cache import get_cached
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import project_root as _project_root
from src.ui.web.routes.integrations.gh_helpers import requires_gh_auth

from . import integrations_bp


@integrations_bp.route("/integrations/gh/status")
def gh_status_extended():  # type: ignore[no-untyped-def]
    """Extended GitHub status — version, repo, auth details."""
    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "github",
        lambda: git_ops.gh_status(root),
        force=force,
    ))


@integrations_bp.route("/gh/pulls")
@requires_gh_auth
def gh_pulls():  # type: ignore[no-untyped-def]
    """List open pull requests."""
    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "gh-pulls",
        lambda: git_ops.gh_pulls(root),
        force=force,
    ))


@integrations_bp.route("/gh/actions/runs")
@requires_gh_auth
def gh_actions_runs():  # type: ignore[no-untyped-def]
    """Recent workflow run history."""
    root = _project_root()
    n = request.args.get("n", 10, type=int)
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "gh-runs",
        lambda: git_ops.gh_actions_runs(root, n=n),
        force=force,
    ))


@integrations_bp.route("/gh/actions/dispatch", methods=["POST"])
@run_tracked("ci", "ci:gh_dispatch")
@requires_gh_auth
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


@integrations_bp.route("/gh/actions/workflows")
@requires_gh_auth
def gh_actions_workflows():  # type: ignore[no-untyped-def]
    """List available workflows."""
    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "gh-workflows",
        lambda: git_ops.gh_actions_workflows(root),
        force=force,
    ))


@integrations_bp.route("/gh/user")
@requires_gh_auth
def gh_user():  # type: ignore[no-untyped-def]
    """Currently authenticated GitHub user."""
    return jsonify(git_ops.gh_user(_project_root()))


@integrations_bp.route("/gh/repo/info")
@requires_gh_auth
def gh_repo_info():  # type: ignore[no-untyped-def]
    """Detailed repository information (visibility, description, etc)."""
    return jsonify(git_ops.gh_repo_info(_project_root()))


@integrations_bp.route("/github/status")
def github_operational_status():  # type: ignore[no-untyped-def]
    """GitHub operational status from githubstatus.com.

    No auth required — queries public status API.
    """
    from src.core.services.git.gh_api import check_github_status
    return jsonify(check_github_status())
