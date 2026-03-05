"""Secrets actions — set/remove, push, create env, cleanup, seed, key generation."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import secrets_ops
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import project_root as _project_root

from . import secrets_bp


def _env_name() -> str:
    """Extract optional env name from query params."""
    return request.args.get("env", "").strip().lower()


@secrets_bp.route("/keys/generate", methods=["POST"])
@run_tracked("generate", "generate:key")
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


@secrets_bp.route("/gh/environment/create", methods=["POST"])
@run_tracked("setup", "setup:gh_environment")
def api_gh_environment_create():
    """Create a deployment environment on GitHub."""
    data = request.json or {}

    root = _project_root()
    env_name = data.get("name", "").strip()

    result = secrets_ops.create_environment(root, env_name)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@secrets_bp.route("/env/cleanup", methods=["POST"])
@run_tracked("destroy", "destroy:environment")
def api_env_cleanup():
    """Clean up an environment: delete local .env files and optionally GitHub env."""
    data = request.json or {}

    root = _project_root()
    env_name = data.get("name", "").strip().lower()

    result = secrets_ops.cleanup_environment(
        root, env_name,
        delete_files=data.get("delete_files", True),
        delete_github=data.get("delete_github", False),
    )

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@secrets_bp.route("/env/seed", methods=["POST"])
@run_tracked("setup", "setup:env_seed")
def api_env_seed():
    """Seed environment files when transitioning from single-env to multi-env."""
    data = request.json or {}

    root = _project_root()
    envs = data.get("environments", [])

    result = secrets_ops.seed_environments(
        root, envs,
        default=data.get("default", ""),
    )

    return jsonify(result)


@secrets_bp.route("/secret/set", methods=["POST"])
@run_tracked("setup", "setup:secret_set")
def api_secret_set():
    """Set a single secret to .env and/or GitHub."""
    data = request.json or {}

    root = _project_root()
    name = data.get("name", "")

    result = secrets_ops.set_secret(
        root, name,
        data.get("value", ""),
        target=data.get("target", "both"),
        env_name=_env_name(),
    )

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@secrets_bp.route("/secret/remove", methods=["POST"])
@run_tracked("destroy", "destroy:secret")
def api_secret_remove():
    """Remove a secret/variable from .env and/or GitHub."""
    data = request.json or {}

    root = _project_root()
    name = data.get("name", "")

    result = secrets_ops.remove_secret(
        root, name,
        target=data.get("target", "both"),
        kind=data.get("kind", "secret"),
        env_name=_env_name(),
    )

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@secrets_bp.route("/secrets/push", methods=["POST"])
@run_tracked("deploy", "deploy:secrets_push")
def api_push_secrets():
    """Push secrets/variables to GitHub AND save to .env file."""
    data = request.json or {}

    root = _project_root()

    result = secrets_ops.push_secrets(
        root,
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
