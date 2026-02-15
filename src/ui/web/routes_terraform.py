"""
Terraform routes — IaC status, validation, plan, state, generation.

Blueprint: terraform_bp
Prefix: /api

Endpoints:
    GET  /terraform/status            — Terraform config analysis
    POST /terraform/validate          — validate configuration
    POST /terraform/plan              — dry-run plan
    GET  /terraform/state             — list state resources
    GET  /terraform/workspaces        — list workspaces
    POST /terraform/generate          — generate scaffolding
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import terraform_ops

terraform_bp = Blueprint("terraform", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


@terraform_bp.route("/terraform/status")
def tf_status():  # type: ignore[no-untyped-def]
    """Terraform configuration analysis."""
    from src.core.services.devops_cache import get_cached

    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "terraform",
        lambda: terraform_ops.terraform_status(root),
        force=force,
    ))


@terraform_bp.route("/terraform/validate", methods=["POST"])
def tf_validate():  # type: ignore[no-untyped-def]
    """Validate Terraform configuration."""
    result = terraform_ops.terraform_validate(_project_root())
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@terraform_bp.route("/terraform/plan", methods=["POST"])
def tf_plan():  # type: ignore[no-untyped-def]
    """Run terraform plan."""
    root = _project_root()
    result = terraform_ops.terraform_plan(root)
    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@terraform_bp.route("/terraform/state")
def tf_state():  # type: ignore[no-untyped-def]
    """List resources in terraform state."""
    return jsonify(terraform_ops.terraform_state(_project_root()))


@terraform_bp.route("/terraform/workspaces")
def tf_workspaces():  # type: ignore[no-untyped-def]
    """List terraform workspaces."""
    return jsonify(terraform_ops.terraform_workspaces(_project_root()))


@terraform_bp.route("/terraform/generate", methods=["POST"])
def tf_generate():  # type: ignore[no-untyped-def]
    """Generate Terraform scaffolding."""
    data = request.get_json(silent=True) or {}
    root = _project_root()
    provider = data.get("provider", "aws")
    backend = data.get("backend", "local")

    result = terraform_ops.generate_terraform(
        root, provider,
        backend=backend,
        project_name=data.get("project_name", ""),
    )
    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


# ── Extended operations ─────────────────────────────────────────────


@terraform_bp.route("/terraform/init", methods=["POST"])
def tf_init():  # type: ignore[no-untyped-def]
    """Initialize Terraform."""
    data = request.get_json(silent=True) or {}
    upgrade = data.get("upgrade", False)
    root = _project_root()
    result = terraform_ops.terraform_init(root, upgrade=upgrade)
    if not result.get("ok"):
        return jsonify(result), 400

    return jsonify(result)


@terraform_bp.route("/terraform/apply", methods=["POST"])
def tf_apply():  # type: ignore[no-untyped-def]
    """Apply Terraform plan."""
    root = _project_root()
    result = terraform_ops.terraform_apply(root)
    if not result.get("ok"):
        return jsonify(result), 400

    return jsonify(result)


@terraform_bp.route("/terraform/output")
def tf_output():  # type: ignore[no-untyped-def]
    """Get Terraform outputs."""
    result = terraform_ops.terraform_output(_project_root())
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)


@terraform_bp.route("/terraform/destroy", methods=["POST"])
def tf_destroy():  # type: ignore[no-untyped-def]
    """Destroy Terraform resources."""
    root = _project_root()
    result = terraform_ops.terraform_destroy(root)
    if not result.get("ok"):
        return jsonify(result), 400

    return jsonify(result)


@terraform_bp.route("/terraform/workspace/select", methods=["POST"])
def tf_workspace_select():  # type: ignore[no-untyped-def]
    """Switch Terraform workspace."""
    data = request.get_json(silent=True) or {}
    workspace = data.get("workspace", "")
    if not workspace:
        return jsonify({"error": "Missing 'workspace' field"}), 400
    root = _project_root()
    result = terraform_ops.terraform_workspace_select(root, workspace)
    if not result.get("ok"):
        return jsonify(result), 400

    return jsonify(result)


@terraform_bp.route("/terraform/fmt", methods=["POST"])
def tf_fmt():  # type: ignore[no-untyped-def]
    """Format Terraform files."""
    root = _project_root()
    result = terraform_ops.terraform_fmt(root)
    if not result.get("ok"):
        return jsonify(result), 400

    return jsonify(result)
