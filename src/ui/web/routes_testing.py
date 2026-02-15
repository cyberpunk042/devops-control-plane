"""
Testing routes — test status, inventory, run, coverage.

Blueprint: testing_bp
Prefix: /api

Endpoints:
    GET  /testing/status           — detected frameworks and stats
    GET  /testing/inventory        — test file listing
    POST /testing/run              — run tests
    POST /testing/coverage         — run tests with coverage
    POST /testing/generate/template — generate test template
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import testing_ops, devops_cache

testing_bp = Blueprint("testing", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


@testing_bp.route("/testing/status")
def testing_status():  # type: ignore[no-untyped-def]
    """Detected test frameworks and stats."""
    from src.core.services.devops_cache import get_cached

    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "testing",
        lambda: testing_ops.testing_status(root),
        force=force,
    ))


@testing_bp.route("/testing/inventory")
def testing_inventory():  # type: ignore[no-untyped-def]
    """Test file listing with function counts."""
    return jsonify(testing_ops.test_inventory(_project_root()))


@testing_bp.route("/testing/run", methods=["POST"])
def testing_run():  # type: ignore[no-untyped-def]
    """Run tests."""
    data = request.get_json(silent=True) or {}
    root = _project_root()
    result = testing_ops.run_tests(
        root,
        verbose=data.get("verbose", False),
        file_path=data.get("file"),
        keyword=data.get("keyword"),
    )
    if "error" in result:
        return jsonify(result), 400

    devops_cache.record_event(
        root,
        label="🧪 Tests Run",
        summary="Tests executed" + (f" ({data.get('file')})" if data.get("file") else ""),
        detail={"file": data.get("file"), "keyword": data.get("keyword"), "verbose": data.get("verbose", False)},
        card="testing",
        action="executed",
        target=data.get("file") or "all",
    )
    return jsonify(result)


@testing_bp.route("/testing/coverage", methods=["POST"])
def testing_coverage():  # type: ignore[no-untyped-def]
    """Run tests with coverage."""
    root = _project_root()
    result = testing_ops.test_coverage(root)

    devops_cache.record_event(
        root,
        label="📊 Coverage Run",
        summary="Coverage analysis completed",
        detail={},
        card="testing",
        action="executed",
        target="coverage",
    )
    return jsonify(result)


@testing_bp.route("/testing/generate/template", methods=["POST"])
def testing_generate_template():  # type: ignore[no-untyped-def]
    """Generate test template."""
    data = request.get_json(silent=True) or {}
    module = data.get("module", "")
    if not module:
        return jsonify({"error": "Missing 'module' field"}), 400

    root = _project_root()
    result = testing_ops.generate_test_template(
        root, module,
        stack=data.get("stack", "python"),
    )
    if "error" in result:
        return jsonify(result), 400

    devops_cache.record_event(
        root,
        label="📝 Test Template Generated",
        summary=f"Test template generated for module '{module}'",
        detail={"module": module, "stack": data.get("stack", "python")},
        card="testing",
        action="generated",
        target=module,
    )
    return jsonify(result)
