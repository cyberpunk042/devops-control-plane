"""Testing status — detected frameworks, inventory."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services.testing import ops as testing_ops
from src.ui.web.helpers import project_root as _project_root

from . import testing_bp


@testing_bp.route("/testing/status")
def testing_status():  # type: ignore[no-untyped-def]
    """Detected test frameworks and stats."""
    from src.core.services.devops.cache import get_cached

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
