"""Testing actions — run tests, coverage, generate template."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services.testing import ops as testing_ops
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import project_root as _project_root

from . import testing_bp


@testing_bp.route("/testing/run", methods=["POST"])
@run_tracked("test", "test:run")
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

    return jsonify(result)


@testing_bp.route("/testing/coverage", methods=["POST"])
@run_tracked("test", "test:coverage")
def testing_coverage():  # type: ignore[no-untyped-def]
    """Run tests with coverage."""
    root = _project_root()
    result = testing_ops.test_coverage(root)
    return jsonify(result)


@testing_bp.route("/testing/generate/template", methods=["POST"])
@run_tracked("generate", "generate:test_template")
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

    return jsonify(result)
