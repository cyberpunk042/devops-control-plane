"""
Admin API — GitHub CLI and secrets management endpoints.

Thin HTTP wrappers over ``src.core.services.secrets_ops``.

Blueprint: secrets_bp
Prefix: /api
Routes:
    /api/gh/status
    /api/gh/auto
    /api/gh/secrets          (?env= for environment-scoped)
    /api/gh/environments
    /api/gh/environment/create
    /api/env/cleanup
    /api/env/seed
    /api/secret/set
    /api/secret/remove       (?env= for environment-scoped)
    /api/secrets/push        (?env= for environment-scoped)
    /api/keys/generate
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import secrets_ops

logger = logging.getLogger(__name__)

secrets_bp = Blueprint("secrets", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"]).resolve()


def _env_name() -> str:
    """Extract optional env name from query params."""
    return request.args.get("env", "").strip().lower()


# ── gh CLI status ────────────────────────────────────────────────────


@secrets_bp.route("/gh/status")
def api_gh_status():
    """Get gh CLI status (installed, authenticated)."""
    return jsonify(secrets_ops.gh_status())


# ── gh auto-detect token & repo ──────────────────────────────────────


@secrets_bp.route("/gh/auto")
def api_gh_auto():
    """Get GitHub token from gh CLI and detect repo from git remote."""
    return jsonify(secrets_ops.gh_auto_detect(_project_root()))


# ── List GitHub environments ─────────────────────────────────────────


@secrets_bp.route("/gh/environments")
def api_gh_environments():
    """List GitHub deployment environments for the current repo."""
    return jsonify(secrets_ops.list_environments(_project_root()))


# ── Key generators ───────────────────────────────────────────────────


@secrets_bp.route("/keys/generate", methods=["POST"])
def api_keys_generate():
    """Generate a secret value (password, token, SSH key, certificate)."""
    data = request.json or {}

    result = secrets_ops.generate_key(
        gen_type=data.get("type", "password").strip().lower(),
        length=data.get("length", 32),
        cn=data.get("cn", "localhost"),
    )

    if "error" in result:
        return jsonify(result), 500 if "failed" in result["error"] else 400
    return jsonify(result)


# ── Create GitHub environment ────────────────────────────────────────


@secrets_bp.route("/gh/environment/create", methods=["POST"])
def api_gh_environment_create():
    """Create a deployment environment on GitHub."""
    data = request.json or {}

    result = secrets_ops.create_environment(
        _project_root(),
        data.get("name", "").strip(),
    )

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@secrets_bp.route("/env/cleanup", methods=["POST"])
def api_env_cleanup():
    """Clean up an environment: delete local .env files and optionally GitHub env."""
    data = request.json or {}

    result = secrets_ops.cleanup_environment(
        _project_root(),
        data.get("name", "").strip().lower(),
        delete_files=data.get("delete_files", True),
        delete_github=data.get("delete_github", False),
    )

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@secrets_bp.route("/env/seed", methods=["POST"])
def api_env_seed():
    """Seed environment files when transitioning from single-env to multi-env."""
    data = request.json or {}

    result = secrets_ops.seed_environments(
        _project_root(),
        data.get("environments", []),
        default=data.get("default", ""),
    )

    return jsonify(result)


# ── List GitHub secrets & variables ──────────────────────────────────


@secrets_bp.route("/gh/secrets")
def api_gh_secrets():
    """Get list of secrets AND variables set in GitHub."""
    result = secrets_ops.list_gh_secrets(_project_root(), env_name=_env_name())
    return jsonify(result)


# ── Set a single secret ─────────────────────────────────────────────


@secrets_bp.route("/secret/set", methods=["POST"])
def api_secret_set():
    """Set a single secret to .env and/or GitHub."""
    data = request.json or {}

    result = secrets_ops.set_secret(
        _project_root(),
        data.get("name", ""),
        data.get("value", ""),
        target=data.get("target", "both"),
        env_name=_env_name(),
    )

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── Remove a single secret ──────────────────────────────────────────


@secrets_bp.route("/secret/remove", methods=["POST"])
def api_secret_remove():
    """Remove a secret/variable from .env and/or GitHub."""
    data = request.json or {}

    result = secrets_ops.remove_secret(
        _project_root(),
        data.get("name", ""),
        target=data.get("target", "both"),
        kind=data.get("kind", "secret"),
        env_name=_env_name(),
    )

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── Bulk push secrets/variables to GitHub + save to .env ─────────────


@secrets_bp.route("/secrets/push", methods=["POST"])
def api_push_secrets():
    """Push secrets/variables to GitHub AND save to .env file."""
    data = request.json or {}

    result = secrets_ops.push_secrets(
        _project_root(),
        secrets_dict=data.get("secrets", {}),
        variables=data.get("variables", {}),
        env_values=data.get("env_values", {}),
        deletions=data.get("deletions", []),
        sync_keys=data.get("sync_keys", []),
        push_to_github=data.get("push_to_github", True),
        save_to_env=data.get("save_to_env", True),
        exclude_from_github=set(data.get("exclude_from_github", [])),
        env_name=_env_name(),
    )

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)
