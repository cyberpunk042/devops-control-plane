"""Secrets status — gh status, auto-detect, environments, secrets list."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import secrets_ops
from src.ui.web.helpers import project_root as _project_root

from . import secrets_bp


def _env_name() -> str:
    """Extract optional env name from query params."""
    return request.args.get("env", "").strip().lower()


@secrets_bp.route("/gh/status")
def api_gh_status():
    """Get gh CLI status (installed, authenticated)."""
    return jsonify(secrets_ops.gh_status())


@secrets_bp.route("/gh/auto")
def api_gh_auto():
    """Get GitHub token from gh CLI and detect repo from git remote."""
    return jsonify(secrets_ops.gh_auto_detect(_project_root()))


@secrets_bp.route("/gh/environments")
def api_gh_environments():
    """List GitHub deployment environments for the current repo."""
    return jsonify(secrets_ops.list_environments(_project_root()))


@secrets_bp.route("/gh/secrets")
def api_gh_secrets():
    """Get list of secrets AND variables set in GitHub."""
    result = secrets_ops.list_gh_secrets(_project_root(), env_name=_env_name())
    return jsonify(result)
