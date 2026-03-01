"""Infra environment — .env management endpoints."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services.env import ops as env_ops
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import project_root as _project_root

from . import infra_bp


@infra_bp.route("/infra/status")
def infra_status():  # type: ignore[no-untyped-def]
    """Combined environment and IaC status."""
    return jsonify(env_ops.infra_status(_project_root()))


@infra_bp.route("/infra/env/status")
def env_status():  # type: ignore[no-untyped-def]
    """Detected .env files and their state."""
    return jsonify(env_ops.env_status(_project_root()))


@infra_bp.route("/infra/env/vars")
def env_vars():  # type: ignore[no-untyped-def]
    """Variables in a .env file."""
    file = request.args.get("file", ".env")
    redact = request.args.get("redact", "true").lower() != "false"
    result = env_ops.env_vars(_project_root(), file=file, redact=redact)

    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@infra_bp.route("/infra/env/diff")
def env_diff():  # type: ignore[no-untyped-def]
    """Compare two .env files."""
    source = request.args.get("source", ".env.example")
    target = request.args.get("target", ".env")
    result = env_ops.env_diff(_project_root(), source=source, target=target)

    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@infra_bp.route("/infra/env/validate")
def env_validate():  # type: ignore[no-untyped-def]
    """Validate a .env file."""
    file = request.args.get("file", ".env")
    result = env_ops.env_validate(_project_root(), file=file)

    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@infra_bp.route("/infra/env/generate-example", methods=["POST"])
@run_tracked("generate", "generate:env_example")
def env_generate_example():  # type: ignore[no-untyped-def]
    """Generate .env.example from .env."""
    result = env_ops.generate_env_example(_project_root())

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@infra_bp.route("/infra/env/generate-env", methods=["POST"])
@run_tracked("generate", "generate:env")
def env_generate_env():  # type: ignore[no-untyped-def]
    """Generate .env from .env.example."""
    result = env_ops.generate_env_from_example(_project_root())

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)
