"""GitHub observation — status, pulls, actions, workflows, user, repo info."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import git_ops
from src.core.services.events.tracked import tracked
from src.ui.web.helpers import project_root as _project_root
from src.ui.web.routes.integrations.gh_helpers import requires_gh_auth

from . import integrations_bp


@integrations_bp.route("/integrations/gh/status")
def gh_status_extended():  # type: ignore[no-untyped-def]
    """Extended GitHub status — version, repo, auth details."""
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("devops.github", force=force)
    return jsonify(result["data"])


@integrations_bp.route("/gh/pulls")
@requires_gh_auth
def gh_pulls():  # type: ignore[no-untyped-def]
    """List open pull requests."""
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("github.pulls", force=force)
    return jsonify(result["data"])


@integrations_bp.route("/gh/actions/runs")
@requires_gh_auth
def gh_actions_runs():  # type: ignore[no-untyped-def]
    """Recent workflow run history."""
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("github.runs", force=force)
    return jsonify(result["data"])


@integrations_bp.route("/gh/actions/dispatch", methods=["POST"])
@tracked("ci.workflow.dispatched")
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
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("github.workflows", force=force)
    return jsonify(result["data"])


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
