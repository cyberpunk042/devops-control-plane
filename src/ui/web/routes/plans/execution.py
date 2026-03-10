"""
Execution Plan execution control endpoints.

Routes registered on ``plans_bp`` from the parent package.

Endpoints:
    POST   /plans/<plan_id>/execute         — start plan execution
    POST   /plans/run/<run_id>/cancel       — cancel running plan
    POST   /plans/run/<run_id>/resume       — resume from pause
    POST   /plans/run/<run_id>/skip         — skip current step
    GET    /plans/run/active                — get active plan run info
    GET    /plans/results                   — list past results
    GET    /plans/results/<run_id>          — get specific result
"""

from __future__ import annotations

import logging

from flask import jsonify, request

from src.ui.web.helpers import project_root as _project_root

from . import plans_bp

logger = logging.getLogger(__name__)


# ── Execute plan ───────────────────────────────────────────────


@plans_bp.route("/plans/<plan_id>/execute", methods=["POST"])
def plans_execute(plan_id: str):
    """Start execution of an execution plan.

    Body (JSON, optional):
        - ``mode``: Override execution mode (fully_automated/semi_automated/interactive)
        - ``variables``: Override initial variables
        - ``browser_config``: Override browser configuration

    Returns ``run_id`` if started, or error if another plan is running.
    """
    from src.core.services.scripts.plans import (
        BrowserConfig,
        PlanRunResult,
    )
    from src.core.services.scripts.plan_executor import start_plan
    from src.core.services.scripts.plan_storage import get_plan
    from src.core.services.event_bus import bus

    root = _project_root()
    plan = get_plan(root, plan_id)
    if plan is None:
        return jsonify({"ok": False, "error": f"Plan '{plan_id}' not found"}), 404

    # Apply runtime overrides
    data = request.get_json(silent=True) or {}

    if "mode" in data:
        plan.mode = data["mode"]

    if "variables" in data:
        plan.variables.update(data["variables"])

    if "browser_config" in data:
        bc = data["browser_config"]
        plan.browser_config = BrowserConfig.from_dict(bc) if bc else None

    # Create callback that publishes to the event bus
    def _bus_callback(event_type: str, event_data: dict):
        """Publish plan events to the global SSE bus."""
        bus.publish(
            event_type,
            key=event_data.get("run_id", ""),
            data=event_data,
        )

    # Start the plan
    result = start_plan(root, plan, _bus_callback)

    if isinstance(result, PlanRunResult):
        # Startup error
        return jsonify({
            "ok": False,
            "error": result.error or "Failed to start plan",
        }), 409

    # result is the run_id string
    run_id = result
    logger.info(
        "Plan started: run=%s, plan=%s (%s), mode=%s",
        run_id, plan.id, plan.name, plan.mode,
    )

    return jsonify({
        "ok": True,
        "run_id": run_id,
        "plan_id": plan.id,
        "plan_name": plan.name,
        "total_steps": len(plan.steps),
        "mode": plan.mode,
    })


# ── Cancel plan ────────────────────────────────────────────────


@plans_bp.route("/plans/run/<run_id>/cancel", methods=["POST"])
def plans_cancel(run_id: str):
    """Cancel the active plan run."""
    from src.core.services.scripts.plan_executor import (
        cancel_active_plan,
        get_active_plan_run,
    )

    active = get_active_plan_run()
    if active is None or active.run_id != run_id:
        return jsonify({
            "ok": False,
            "error": "No active plan matches this run_id",
        }), 404

    cancelled = cancel_active_plan()
    return jsonify({"ok": cancelled})


# ── Resume plan ────────────────────────────────────────────────


@plans_bp.route("/plans/run/<run_id>/resume", methods=["POST"])
def plans_resume(run_id: str):
    """Resume a paused plan execution.

    Optionally accepts JSON body with ``variables`` dict to merge
    into the running namespace before continuing.
    """
    from src.core.services.scripts.plan_executor import resume_plan

    body = request.get_json(silent=True) or {}
    var_updates = body.get("variables") if isinstance(body, dict) else None

    resumed = resume_plan(run_id, variable_updates=var_updates)
    if not resumed:
        return jsonify({
            "ok": False,
            "error": "Plan is not paused or run_id doesn't match",
        }), 404
    return jsonify({"ok": True})


# ── Skip step ──────────────────────────────────────────────────


@plans_bp.route("/plans/run/<run_id>/skip", methods=["POST"])
def plans_skip(run_id: str):
    """Skip the current step in a paused interactive plan."""
    from src.core.services.scripts.plan_executor import skip_step

    skipped = skip_step(run_id)
    if not skipped:
        return jsonify({
            "ok": False,
            "error": "Plan is not paused or run_id doesn't match",
        }), 404
    return jsonify({"ok": True})


# ── Active plan info ───────────────────────────────────────────


@plans_bp.route("/plans/run/active")
def plans_active():
    """Get info about the currently running plan, if any."""
    from src.core.services.scripts.plan_executor import get_active_plan_run

    active = get_active_plan_run()
    if active is None:
        return jsonify({"ok": True, "active": False})

    return jsonify({
        "ok": True,
        "active": True,
        "run_id": active.run_id,
        "plan_id": active.plan_id,
        "paused": active.paused,
        "current_step": active.current_step_sequence,
    })


# ── List results ───────────────────────────────────────────────


@plans_bp.route("/plans/results")
def plans_list_results():
    """List plan run results (newest first).

    Query params:
        ?plan_id=...  — filter by plan
        ?last=20      — number of results (default 20)
    """
    from src.core.services.scripts.plan_storage import list_results

    root = _project_root()
    plan_id = request.args.get("plan_id")
    last = request.args.get("last", 20, type=int)

    results = list_results(root, plan_id=plan_id, last=last)
    return jsonify({"ok": True, "results": results, "total": len(results)})


# ── Get result ─────────────────────────────────────────────────


@plans_bp.route("/plans/results/<run_id>")
def plans_get_result(run_id: str):
    """Get detail for a single plan run result."""
    from src.core.services.scripts.plan_storage import get_result

    root = _project_root()
    result = get_result(root, run_id)
    if result is None:
        return jsonify({"ok": False, "error": f"Result '{run_id}' not found"}), 404
    return jsonify({"ok": True, "result": result.to_dict()})
