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

import logging
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import git_ops

logger = logging.getLogger(__name__)

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
