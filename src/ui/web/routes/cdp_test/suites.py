"""
CDP Test suite CRUD endpoints.

Routes registered on ``cdp_test_bp`` from the parent package.

Endpoints:
    GET    /cdp-test/suites                       — list all suites (summaries)
    GET    /cdp-test/suites/<suite_id>             — full suite with steps
    POST   /cdp-test/suites                       — create a suite
    PUT    /cdp-test/suites/<suite_id>             — update a suite
    DELETE /cdp-test/suites/<suite_id>             — delete a suite
    POST   /cdp-test/suites/<suite_id>/duplicate   — clone a suite

    POST   /cdp-test/suites/add-to-git             — add suite to ledger
    POST   /cdp-test/suites/sync-to-git            — sync local changes to ledger
    POST   /cdp-test/suites/remove-from-git        — remove suite from ledger

    GET    /cdp-test/results                       — list run results
    GET    /cdp-test/results/<run_id>              — single result detail
"""

from __future__ import annotations

import logging

from flask import jsonify, request

from src.core.services.events.tracked import tracked
from src.ui.web.helpers import project_root as _project_root

from . import cdp_test_bp

logger = logging.getLogger(__name__)


# ── List suites ────────────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/suites")
def cdp_test_list_suites():
    """List all test suites (summary — no step details)."""
    from src.core.services.cdp_test.storage import list_suites

    root = _project_root()
    suites = list_suites(root)
    return jsonify({"ok": True, "suites": suites, "total": len(suites)})


# ── Get suite ──────────────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/suites/<suite_id>")
def cdp_test_get_suite(suite_id: str):
    """Get full test suite with all steps."""
    from src.core.services.cdp_test.storage import get_suite

    root = _project_root()
    suite = get_suite(root, suite_id)
    if suite is None:
        return jsonify({"ok": False, "error": f"Suite '{suite_id}' not found"}), 404
    return jsonify({"ok": True, "suite": suite.to_dict()})


# ── Create suite ───────────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/suites", methods=["POST"])
@tracked("cdp_test.suite.created")
def cdp_test_create_suite():
    """Create a new test suite.

    Body (JSON): TestSuite fields (name, target_url, steps, etc.)
    The ``id`` field is auto-generated if not provided.
    """
    from src.core.services.cdp_test.models import TestSuite
    from src.core.services.cdp_test.storage import save_suite

    root = _project_root()
    data = request.get_json(silent=True) or {}

    if not data.get("name"):
        return jsonify({"ok": False, "error": "name is required"}), 400

    suite = TestSuite.from_dict(data)
    save_suite(root, suite)

    logger.info("Created suite %s (%s)", suite.id, suite.name)
    return jsonify({"ok": True, "suite_id": suite.id}), 201


# ── Update suite ───────────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/suites/<suite_id>", methods=["PUT"])
@tracked("cdp_test.suite.updated")
def cdp_test_update_suite(suite_id: str):
    """Update an existing test suite.

    Body (JSON): fields to update.  Steps can be replaced entirely
    or individual fields can be patched.
    """
    from src.core.services.cdp_test.models import TestStep, _now_iso
    from src.core.services.cdp_test.storage import get_suite, save_suite

    root = _project_root()
    suite = get_suite(root, suite_id)
    if suite is None:
        return jsonify({"ok": False, "error": f"Suite '{suite_id}' not found"}), 404

    data = request.get_json(silent=True) or {}

    # Update simple fields
    for field_name in (
        "name", "description", "target_url", "target_description",
        "category", "tags", "variables",
        "default_timeout_ms", "navigate_wait_ms", "replay_speed",
        "stop_on_failure", "take_screenshots",
    ):
        if field_name in data:
            setattr(suite, field_name, data[field_name])

    # Update steps if provided (full replacement)
    if "steps" in data:
        suite.steps = [TestStep.from_dict(s) for s in data["steps"]]

    # Update outputs if provided
    if "outputs" in data:
        suite.outputs = data["outputs"]

    suite.updated_at = _now_iso()
    save_suite(root, suite)

    return jsonify({"ok": True})


# ── Delete suite ───────────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/suites/<suite_id>", methods=["DELETE"])
@tracked("cdp_test.suite.deleted")
def cdp_test_delete_suite(suite_id: str):
    """Delete a test suite."""
    from src.core.services.cdp_test.storage import delete_suite

    root = _project_root()
    deleted = delete_suite(root, suite_id)
    if not deleted:
        return jsonify({"ok": False, "error": f"Suite '{suite_id}' not found"}), 404
    return jsonify({"ok": True})


# ── Duplicate suite ────────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/suites/<suite_id>/duplicate", methods=["POST"])
@tracked("cdp_test.suite.duplicated")
def cdp_test_duplicate_suite(suite_id: str):
    """Clone a test suite with a new ID.

    Optionally pass ``{"name": "New Name"}`` in the body.
    """
    import uuid

    from src.core.services.cdp_test.models import _now_iso
    from src.core.services.cdp_test.storage import get_suite, save_suite

    root = _project_root()
    original = get_suite(root, suite_id)
    if original is None:
        return jsonify({"ok": False, "error": f"Suite '{suite_id}' not found"}), 404

    data = request.get_json(silent=True) or {}

    # Create clone with new ID
    original.id = str(uuid.uuid4())
    original.name = data.get("name", f"{original.name} (copy)")
    original.created_at = _now_iso()
    original.updated_at = _now_iso()
    original.last_run_at = ""
    original.last_run_status = ""
    original.run_count = 0
    original.in_git = False
    original.git_updated_at = ""

    # Give each step a new ID too
    for step in original.steps:
        step.id = str(uuid.uuid4())

    save_suite(root, original)

    logger.info("Duplicated suite %s → %s", suite_id, original.id)
    return jsonify({"ok": True, "suite_id": original.id}), 201


# ── Git operations ─────────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/suites/add-to-git", methods=["POST"])
@tracked("cdp_test.git.added")
def cdp_test_add_suite_to_git():
    """Add a test suite to the ledger (git) branch.

    Body (JSON): ``{"suite_id": "..."}``
    """
    import threading

    from src.core.services.cdp_test.storage import add_suite_to_git
    from src.core.services.git_auth import is_auth_ok
    from src.core.services.ledger.worktree import push_ledger_branch

    root = _project_root()
    data = request.get_json(silent=True) or {}
    suite_id = data.get("suite_id", "")
    if not suite_id:
        return jsonify({"ok": False, "error": "suite_id is required"}), 400

    ok = add_suite_to_git(root, suite_id)
    if not ok:
        return jsonify({"ok": False, "error": "Suite not found"}), 404

    # Background push if auth is available
    if is_auth_ok():
        threading.Thread(
            target=push_ledger_branch, args=(root,), daemon=True,
        ).start()

    return jsonify({"ok": True, "suite_id": suite_id, "in_git": True})


@cdp_test_bp.route("/cdp-test/suites/sync-to-git", methods=["POST"])
@tracked("cdp_test.git.synced")
def cdp_test_sync_suite_to_git():
    """Sync local suite changes to the ledger (git) branch.

    Body (JSON): ``{"suite_id": "..."}``
    """
    import threading

    from src.core.services.cdp_test.storage import sync_suite_to_git
    from src.core.services.git_auth import is_auth_ok
    from src.core.services.ledger.worktree import push_ledger_branch

    root = _project_root()
    data = request.get_json(silent=True) or {}
    suite_id = data.get("suite_id", "")
    if not suite_id:
        return jsonify({"ok": False, "error": "suite_id is required"}), 400

    ok = sync_suite_to_git(root, suite_id)
    if not ok:
        return jsonify({
            "ok": False,
            "error": "Suite not found or not in git",
        }), 404

    # Background push if auth is available
    if is_auth_ok():
        threading.Thread(
            target=push_ledger_branch, args=(root,), daemon=True,
        ).start()

    return jsonify({
        "ok": True, "suite_id": suite_id,
        "in_git": True, "git_dirty": False,
    })


@cdp_test_bp.route("/cdp-test/suites/remove-from-git", methods=["POST"])
@tracked("cdp_test.git.removed")
def cdp_test_remove_suite_from_git():
    """Remove a test suite from the ledger (git) branch.

    The suite remains in local storage.
    Body (JSON): ``{"suite_id": "..."}``
    """
    import threading

    from src.core.services.cdp_test.storage import remove_suite_from_git
    from src.core.services.git_auth import is_auth_ok
    from src.core.services.ledger.worktree import push_ledger_branch

    root = _project_root()
    data = request.get_json(silent=True) or {}
    suite_id = data.get("suite_id", "")
    if not suite_id:
        return jsonify({"ok": False, "error": "suite_id is required"}), 400

    ok = remove_suite_from_git(root, suite_id)
    if not ok:
        return jsonify({"ok": False, "error": "Suite not found"}), 404

    # Background push if auth is available
    if is_auth_ok():
        threading.Thread(
            target=push_ledger_branch, args=(root,), daemon=True,
        ).start()

    return jsonify({"ok": True, "suite_id": suite_id, "in_git": False})


@cdp_test_bp.route("/cdp-test/suites/recover", methods=["POST"])
@tracked("cdp_test.suite.recovered")
def cdp_test_recover_suite():
    """Recover a deleted suite from ledger git history.

    Body (JSON): ``{"suite_id": "..."}``
    """
    from src.core.services.cdp_test.storage import recover_suite_from_history

    root = _project_root()
    data = request.get_json(silent=True) or {}
    suite_id = data.get("suite_id", "")
    if not suite_id:
        return jsonify({"ok": False, "error": "suite_id is required"}), 400

    suite = recover_suite_from_history(root, suite_id)
    if suite is None:
        return jsonify({
            "ok": False,
            "error": "Suite not found in git history",
        }), 404

    return jsonify({
        "ok": True,
        "suite_id": suite_id,
        "suite": suite.to_dict(),
    })


@cdp_test_bp.route("/cdp-test/suites/<suite_id>/check-history")
def cdp_test_check_suite_history(suite_id: str):
    """Check if a deleted suite can be recovered from git history."""
    from src.core.services.cdp_test.storage import check_suite_in_history

    root = _project_root()
    recoverable = check_suite_in_history(root, suite_id)
    return jsonify({"ok": True, "recoverable": recoverable, "suite_id": suite_id})


# ── Dependency checks ─────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/suites/<suite_id>/git-dependents")
def cdp_test_suite_git_dependents(suite_id: str):
    """Check which in-git plans reference this suite.

    Returns a list of ``{plan_id, plan_name}`` for plans that are
    in git and have cdp_test steps pointing at this suite.
    Used by the frontend before remove-from-git to warn about
    breaking dependencies.
    """
    from src.core.services.scripts.plan_storage import find_plans_referencing_suite

    root = _project_root()
    dependents = find_plans_referencing_suite(root, suite_id)
    return jsonify({"ok": True, "dependents": dependents})


# ── List results ───────────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/results")
def cdp_test_list_results():
    """List test run results (newest first).

    Query params:
        ?suite_id=...  — filter by suite
        ?last=20       — number of results (default 20)
    """
    from src.core.services.cdp_test.storage import list_results

    root = _project_root()
    suite_id = request.args.get("suite_id")
    last = request.args.get("last", 20, type=int)

    results = list_results(root, suite_id=suite_id, last=last)
    return jsonify({"ok": True, "results": results, "total": len(results)})


# ── Get result ─────────────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/results/<run_id>")
def cdp_test_get_result(run_id: str):
    """Get detail for a single run result."""
    from src.core.services.cdp_test.storage import get_result

    root = _project_root()
    result = get_result(root, run_id)
    if result is None:
        return jsonify({"ok": False, "error": f"Result '{run_id}' not found"}), 404
    return jsonify({"ok": True, "result": result.to_dict()})


# ── Serve screenshot images ───────────────────────────────────


@cdp_test_bp.route("/cdp-test/screenshots/<filename>")
def cdp_test_screenshot(filename: str):
    """Serve a captured screenshot image.

    Screenshots are stored in ``.state/cdp-tests/screenshots/``.
    Only serves .png files from that directory (no path traversal).
    """
    import os
    from pathlib import Path

    from flask import send_file

    # Block path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        return jsonify({"ok": False, "error": "Invalid filename"}), 400

    root = _project_root()
    screenshot_dir = Path(root) / ".state" / "cdp-tests" / "screenshots"
    filepath = screenshot_dir / filename

    if not filepath.exists() or not filepath.is_file():
        return jsonify({"ok": False, "error": "Screenshot not found"}), 404

    # Verify it's actually inside the screenshots dir (belt + suspenders)
    try:
        filepath.resolve().relative_to(screenshot_dir.resolve())
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid path"}), 400

    return send_file(str(filepath), mimetype="image/png")

