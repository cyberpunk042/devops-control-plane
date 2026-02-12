"""
Environment & IaC routes — env var management and IaC detection endpoints.

Blueprint: infra_bp
Prefix: /api

Thin HTTP wrappers over ``src.core.services.env_ops``.

Endpoints:
    GET  /infra/status              — combined env + IaC status
    GET  /infra/env/status          — detected .env files
    GET  /infra/env/vars            — variables in a .env file
    GET  /infra/env/diff            — compare two .env files
    GET  /infra/env/validate        — validate a .env file
    POST /infra/env/generate-example — generate .env.example
    POST /infra/env/generate-env    — generate .env from example
    GET  /infra/iac/status          — detected IaC providers
    GET  /infra/iac/resources       — IaC resource inventory
    GET  /env/card-status           — aggregated env card data
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import env_ops

infra_bp = Blueprint("infra", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


# ── Combined ────────────────────────────────────────────────────────


@infra_bp.route("/infra/status")
def infra_status():  # type: ignore[no-untyped-def]
    """Combined environment and IaC status."""
    return jsonify(env_ops.infra_status(_project_root()))


# ── Environment ─────────────────────────────────────────────────────


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
def env_generate_example():  # type: ignore[no-untyped-def]
    """Generate .env.example from .env."""
    result = env_ops.generate_env_example(_project_root())

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@infra_bp.route("/infra/env/generate-env", methods=["POST"])
def env_generate_env():  # type: ignore[no-untyped-def]
    """Generate .env from .env.example."""
    result = env_ops.generate_env_from_example(_project_root())

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── IaC ─────────────────────────────────────────────────────────────


@infra_bp.route("/infra/iac/status")
def iac_status():  # type: ignore[no-untyped-def]
    """Detected IaC providers and configs."""
    return jsonify(env_ops.iac_status(_project_root()))


@infra_bp.route("/infra/iac/resources")
def iac_resources():  # type: ignore[no-untyped-def]
    """IaC resource inventory."""
    return jsonify(env_ops.iac_resources(_project_root()))


# ── Aggregated environment card data ────────────────────────────


@infra_bp.route("/env/card-status")
def env_card_status():  # type: ignore[no-untyped-def]
    """Aggregated environment data for the DevOps dashboard card."""
    from src.core.services.devops_cache import get_cached

    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "env",
        lambda: env_ops.env_card_status(root),
        force=force,
    ))
