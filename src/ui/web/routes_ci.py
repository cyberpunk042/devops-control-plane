"""
CI/CD routes — workflow analysis and generation endpoints.

Blueprint: ci_bp
Prefix: /api

Thin HTTP wrappers over ``src.core.services.ci_ops``.

Endpoints:
    GET  /ci/status              — detected CI providers
    GET  /ci/workflows           — parsed workflow files with analysis
    GET  /ci/coverage            — module CI coverage analysis
    POST /ci/generate/ci         — generate CI workflow
    POST /ci/generate/lint       — generate lint workflow
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import ci_ops, devops_cache

ci_bp = Blueprint("ci", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


def _get_modules() -> list[dict]:
    """Load and detect modules for coverage analysis."""
    from src.core.config.loader import load_project
    from src.core.config.stack_loader import discover_stacks
    from src.core.services.detection import detect_modules

    root = _project_root()
    project = load_project(root / "project.yml")
    stacks = discover_stacks(root / "stacks")
    detection = detect_modules(project, root, stacks)
    return [m.model_dump() for m in detection.modules]


def _get_stack_names() -> list[str]:
    """Get unique stack names from detected modules."""
    modules = _get_modules()
    seen: set[str] = set()
    names: list[str] = []
    for m in modules:
        stack = m.get("effective_stack", m.get("stack_name", ""))
        if stack and stack not in seen:
            names.append(stack)
            seen.add(stack)
    return names


# ── Detect ──────────────────────────────────────────────────────────


@ci_bp.route("/ci/status")
def ci_status():  # type: ignore[no-untyped-def]
    """CI/CD availability: detected providers, workflow count."""
    return jsonify(ci_ops.ci_status(_project_root()))


# ── Observe ─────────────────────────────────────────────────────────


@ci_bp.route("/ci/workflows")
def ci_workflows():  # type: ignore[no-untyped-def]
    """Parsed workflow files with structural analysis."""
    return jsonify(ci_ops.ci_workflows(_project_root()))


@ci_bp.route("/ci/coverage")
def ci_coverage():  # type: ignore[no-untyped-def]
    """Module CI coverage analysis."""
    modules = _get_modules()
    return jsonify(ci_ops.ci_coverage(_project_root(), modules))


# ── Facilitate (generate) ───────────────────────────────────────────


@ci_bp.route("/ci/generate/ci", methods=["POST"])
def generate_ci():  # type: ignore[no-untyped-def]
    """Generate a CI workflow from detected stacks."""
    from src.core.config.loader import load_project

    root = _project_root()
    stack_names = _get_stack_names()
    project = load_project(root / "project.yml")

    result = ci_ops.generate_ci_workflow(root, stack_names, project_name=project.name)

    if "error" in result:
        return jsonify(result), 400

    devops_cache.record_event(
        root,
        label="⚙️ CI Workflow Generated",
        summary=f"CI workflow generated ({len(stack_names)} stack(s))",
        detail={"stacks": stack_names, "project": project.name},
        card="ci",
        action="generated",
        target="ci-workflow",
    )
    return jsonify(result)


@ci_bp.route("/ci/generate/lint", methods=["POST"])
def generate_lint():  # type: ignore[no-untyped-def]
    """Generate a lint workflow from detected stacks."""
    stack_names = _get_stack_names()
    root = _project_root()
    result = ci_ops.generate_lint_workflow(root, stack_names)

    if "error" in result:
        return jsonify(result), 400

    devops_cache.record_event(
        root,
        label="⚙️ Lint Workflow Generated",
        summary=f"Lint workflow generated ({len(stack_names)} stack(s))",
        detail={"stacks": stack_names},
        card="ci",
        action="generated",
        target="lint-workflow",
    )
    return jsonify(result)
