"""
Scripts history endpoints — run history queries.

Routes registered on ``scripts_bp`` from the parent package.

Endpoints:
    GET /scripts/history            — list recent script runs
    GET /scripts/history/<run_id>   — detail for one run
"""

from __future__ import annotations

import logging

from flask import jsonify, request

from src.ui.web.helpers import project_root as _project_root

from . import scripts_bp

logger = logging.getLogger(__name__)


# ── List recent runs ───────────────────────────────────────────


@scripts_bp.route("/scripts/history")
def scripts_history():
    """List recent script runs.

    Query params:
        ?script_id=generators/class_diagrams  — filter by script
        ?last=10                              — number of runs (default 10)
    """
    from src.core.services.run_tracker import load_runs

    root = _project_root()
    count = request.args.get("last", 10, type=int)
    script_id = request.args.get("script_id")

    all_runs = load_runs(root, n=200)

    # Filter to script runs only
    script_runs = [r for r in all_runs if r.get("type") == "script"]

    # Filter by script ID if specified
    if script_id:
        script_runs = [
            r for r in script_runs
            if r.get("metadata", {}).get("script_id") == script_id
        ]

    script_runs = script_runs[:count]

    return jsonify({
        "ok": True,
        "runs": script_runs,
        "total": len(script_runs),
    })


# ── Single run detail ─────────────────────────────────────────


@scripts_bp.route("/scripts/history/<run_id>")
def scripts_history_detail(run_id: str):
    """Detail for a single run."""
    from src.core.services.run_tracker import get_run_local

    root = _project_root()
    run = get_run_local(root, run_id)

    if run is None:
        return jsonify({"ok": False, "error": f"Run '{run_id}' not found"}), 404

    return jsonify({
        "ok": True,
        "run": run,
    })
