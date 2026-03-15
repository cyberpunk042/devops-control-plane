"""
Execution Plan CRUD endpoints.

Routes registered on ``plans_bp`` from the parent package.

Endpoints:
    GET    /plans                       — list all plans (summaries)
    GET    /plans/<plan_id>             — full plan with steps
    POST   /plans                       — create a plan
    PUT    /plans/<plan_id>             — update a plan
    DELETE /plans/<plan_id>             — delete a plan
    POST   /plans/<plan_id>/duplicate   — clone a plan

    POST   /plans/add-to-git            — add plan to ledger
    POST   /plans/sync-to-git           — sync local changes to ledger
    POST   /plans/remove-from-git       — remove plan from ledger
"""

from __future__ import annotations

import logging

from flask import jsonify, request

from src.core.services.events.tracked import tracked
from src.ui.web.helpers import project_root as _project_root

from . import plans_bp

logger = logging.getLogger(__name__)


# ── List plans ─────────────────────────────────────────────────


@plans_bp.route("/plans")
def plans_list():
    """List all execution plans (summary — no step details)."""
    from src.core.services.scripts.plan_storage import list_plans

    root = _project_root()
    plans = list_plans(root)
    return jsonify({"ok": True, "plans": plans, "total": len(plans)})


# ── Get plan ───────────────────────────────────────────────────


@plans_bp.route("/plans/<plan_id>")
def plans_get(plan_id: str):
    """Get full plan with all steps."""
    from src.core.services.scripts.plan_storage import get_plan

    root = _project_root()
    plan = get_plan(root, plan_id)
    if plan is None:
        return jsonify({"ok": False, "error": f"Plan '{plan_id}' not found"}), 404
    return jsonify({"ok": True, "plan": plan.to_dict()})


# ── Create plan ────────────────────────────────────────────────


@plans_bp.route("/plans", methods=["POST"])
@tracked("plan.created")
def plans_create():
    """Create a new execution plan.

    Body (JSON): ExecutionPlan fields (name, steps, mode, browser_config, etc.)
    The ``id`` field is auto-generated if not provided.
    """
    from src.core.services.scripts.plans import ExecutionPlan
    from src.core.services.scripts.plan_storage import save_plan

    root = _project_root()
    data = request.get_json(silent=True) or {}

    if not data.get("name"):
        return jsonify({"ok": False, "error": "name is required"}), 400

    plan = ExecutionPlan.from_dict(data)
    save_plan(root, plan)

    logger.info("Created plan %s (%s)", plan.id, plan.name)
    return jsonify({"ok": True, "plan_id": plan.id}), 201


# ── Update plan ────────────────────────────────────────────────


@plans_bp.route("/plans/<plan_id>", methods=["PUT"])
@tracked("plan.updated")
def plans_update(plan_id: str):
    """Update an existing execution plan.

    Body (JSON): fields to update.  Steps can be replaced entirely.
    """
    from src.core.services.scripts.plans import (
        BrowserConfig,
        PlanStep,
        _now_iso,
    )
    from src.core.services.scripts.plan_storage import get_plan, save_plan

    root = _project_root()
    plan = get_plan(root, plan_id)
    if plan is None:
        return jsonify({"ok": False, "error": f"Plan '{plan_id}' not found"}), 404

    data = request.get_json(silent=True) or {}

    # Update simple fields
    for field_name in ("name", "description", "mode", "variables"):
        if field_name in data:
            setattr(plan, field_name, data[field_name])

    # Update steps if provided (full replacement)
    if "steps" in data:
        plan.steps = [PlanStep.from_dict(s) for s in data["steps"]]

    # Update browser_config if provided
    if "browser_config" in data:
        bc = data["browser_config"]
        plan.browser_config = BrowserConfig.from_dict(bc) if bc else None

    plan.updated_at = _now_iso()
    save_plan(root, plan)

    return jsonify({"ok": True})


# ── Delete plan ────────────────────────────────────────────────


@plans_bp.route("/plans/<plan_id>", methods=["DELETE"])
@tracked("plan.deleted")
def plans_delete(plan_id: str):
    """Delete an execution plan."""
    from src.core.services.scripts.plan_storage import delete_plan

    root = _project_root()
    deleted = delete_plan(root, plan_id)
    if not deleted:
        return jsonify({"ok": False, "error": f"Plan '{plan_id}' not found"}), 404
    return jsonify({"ok": True})


# ── Duplicate plan ─────────────────────────────────────────────


@plans_bp.route("/plans/<plan_id>/duplicate", methods=["POST"])
@tracked("plan.duplicated")
def plans_duplicate(plan_id: str):
    """Clone a plan with a new ID.

    Optionally pass ``{"name": "New Name"}`` in the body.
    """
    import uuid

    from src.core.services.scripts.plans import _now_iso
    from src.core.services.scripts.plan_storage import get_plan, save_plan

    root = _project_root()
    original = get_plan(root, plan_id)
    if original is None:
        return jsonify({"ok": False, "error": f"Plan '{plan_id}' not found"}), 404

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

    save_plan(root, original)

    logger.info("Duplicated plan %s → %s", plan_id, original.id)
    return jsonify({"ok": True, "plan_id": original.id}), 201


# ── Git operations ─────────────────────────────────────────────


@plans_bp.route("/plans/add-to-git", methods=["POST"])
@tracked("plan.git.added")
def plans_add_to_git():
    """Add an execution plan to the ledger (git) branch.

    Body (JSON): ``{"plan_id": "..."}``
    """
    import threading

    from src.core.services.git_auth import is_auth_ok
    from src.core.services.ledger.worktree import push_ledger_branch
    from src.core.services.scripts.plan_storage import add_plan_to_git

    root = _project_root()
    data = request.get_json(silent=True) or {}
    plan_id = data.get("plan_id", "")
    if not plan_id:
        return jsonify({"ok": False, "error": "plan_id is required"}), 400

    ok = add_plan_to_git(root, plan_id)
    if not ok:
        return jsonify({"ok": False, "error": "Plan not found"}), 404

    # Background push if auth is available
    if is_auth_ok():
        threading.Thread(
            target=push_ledger_branch, args=(root,), daemon=True,
        ).start()

    return jsonify({"ok": True, "plan_id": plan_id, "in_git": True})


@plans_bp.route("/plans/sync-to-git", methods=["POST"])
@tracked("plan.git.synced")
def plans_sync_to_git():
    """Sync local plan changes to the ledger (git) branch.

    Body (JSON): ``{"plan_id": "..."}``
    """
    import threading

    from src.core.services.git_auth import is_auth_ok
    from src.core.services.ledger.worktree import push_ledger_branch
    from src.core.services.scripts.plan_storage import sync_plan_to_git

    root = _project_root()
    data = request.get_json(silent=True) or {}
    plan_id = data.get("plan_id", "")
    if not plan_id:
        return jsonify({"ok": False, "error": "plan_id is required"}), 400

    ok = sync_plan_to_git(root, plan_id)
    if not ok:
        return jsonify({
            "ok": False,
            "error": "Plan not found or not in git",
        }), 404

    # Background push if auth is available
    if is_auth_ok():
        threading.Thread(
            target=push_ledger_branch, args=(root,), daemon=True,
        ).start()

    return jsonify({
        "ok": True, "plan_id": plan_id,
        "in_git": True, "git_dirty": False,
    })


@plans_bp.route("/plans/remove-from-git", methods=["POST"])
@tracked("plan.git.removed")
def plans_remove_from_git():
    """Remove a plan from the ledger (git) branch.

    The plan remains in local storage.
    Body (JSON): ``{"plan_id": "..."}``
    """
    import threading

    from src.core.services.git_auth import is_auth_ok
    from src.core.services.ledger.worktree import push_ledger_branch
    from src.core.services.scripts.plan_storage import remove_plan_from_git

    root = _project_root()
    data = request.get_json(silent=True) or {}
    plan_id = data.get("plan_id", "")
    if not plan_id:
        return jsonify({"ok": False, "error": "plan_id is required"}), 400

    ok = remove_plan_from_git(root, plan_id)
    if not ok:
        return jsonify({"ok": False, "error": "Plan not found"}), 404

    # Background push if auth is available
    if is_auth_ok():
        threading.Thread(
            target=push_ledger_branch, args=(root,), daemon=True,
        ).start()

    return jsonify({"ok": True, "plan_id": plan_id, "in_git": False})


# ── Dependency checks ─────────────────────────────────────────


@plans_bp.route("/plans/<plan_id>/git-check")
def plans_git_check(plan_id: str):
    """Check git status of suites referenced by this plan.

    Returns which referenced suites are not in git (``not_in_git``)
    and which are in git but have local changes (``dirty``).
    Used by the frontend before add-to-git / sync-to-git.
    """
    from src.core.services.scripts.plan_storage import check_plan_suite_deps

    root = _project_root()
    deps = check_plan_suite_deps(root, plan_id)
    return jsonify({"ok": True, **deps})
