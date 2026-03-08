"""
CDP Test replay endpoints.

Routes registered on ``cdp_test_bp`` from the parent package.

Endpoints:
    POST /cdp-test/replay/start     — start replaying a suite
    POST /cdp-test/replay/cancel    — cancel the active replay
    GET  /cdp-test/replay/status    — current replay status
"""

from __future__ import annotations

import logging

from flask import jsonify, request

from src.ui.web.helpers import project_root as _project_root

from . import cdp_test_bp

logger = logging.getLogger(__name__)


# ── Start replay ───────────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/replay/start", methods=["POST"])
def cdp_test_replay_start():
    """Start replaying a saved test suite.

    Body (JSON)::

        {
            "suite_id": "abc-123",
            "target_id": "CHROME-TARGET-ID",      // optional — auto-detect from suite URL
            "variables": { "PASSWORD": "secret" }, // optional overrides
        }

    Returns::

        {
            "ok": true,
            "run_id": "run-uuid",
            "suite_id": "abc-123",
            "suite_name": "Login Flow",
            "total_steps": 10,
        }

    The replay progress is streamed via the global SSE bus
    (/api/events) with event types:

        cdp_test:replay_start   — replay begins
        cdp_test:step_start     — step about to execute
        cdp_test:step_passed    — step succeeded
        cdp_test:step_failed    — step failed
        cdp_test:replay_done    — replay finished
        cdp_test:replay_error   — replay-level error
    """
    from src.core.services.cdp_test.models import TestRunResult
    from src.core.services.cdp_test.replayer import start_replay
    from src.core.services.cdp_test.storage import get_suite
    from src.core.services.event_bus import bus
    from src.ui.web import cdp_client

    data = request.get_json(silent=True) or {}
    suite_id = data.get("suite_id")
    if not suite_id:
        return jsonify({"ok": False, "error": "suite_id is required"}), 400

    root = _project_root()
    suite = get_suite(root, suite_id)
    if suite is None:
        return jsonify({"ok": False, "error": f"Suite '{suite_id}' not found"}), 404

    # ── Resolve target tab ────────────────────────────────────
    target_id = data.get("target_id")
    targets = None  # Fetched on demand, reused to avoid extra curl.exe calls

    if not target_id:
        # Auto-detect: find a tab matching the suite's target_url
        if not suite.target_url:
            return jsonify({
                "ok": False,
                "error": "No target_id provided and suite has no target_url",
            }), 400

        targets = cdp_client.get_targets()
        if not targets:
            return jsonify({
                "ok": False,
                "error": "CDP unavailable — cannot discover browser tabs",
            }), 503

        # Extract the hostname/path for matching
        import re
        url_pattern = suite.target_url
        # Strip protocol for more flexible matching
        url_pattern = re.sub(r"^https?://", "", url_pattern)

        match = cdp_client.find_target_by_url(targets, url_pattern)
        if not match:
            # Also try matching just the domain
            domain = url_pattern.split("/")[0]
            match = cdp_client.find_target_by_url(targets, domain)

        if not match:
            # No matching tab — auto-create one with the suite's URL
            logger.info(
                "No tab matches '%s', creating one via CDP",
                suite.target_url,
            )
            new_tab = cdp_client.create_tab(suite.target_url)
            if not new_tab or "id" not in new_tab:
                return jsonify({
                    "ok": False,
                    "error": (
                        f"No tab matching '{suite.target_url}' and "
                        f"failed to create one via CDP."
                    ),
                }), 503
            target_id = new_tab["id"]
            # Give the new tab time to load the page
            import time
            time.sleep(3.0)
        else:
            target_id = match["id"]

    # ── Verify target tab exists & extract ws_url ─────────────
    # Reuse the targets list we already fetched (avoid extra curl.exe call)
    if not targets:
        targets = cdp_client.get_targets()
    tab_entry = None
    for t in (targets or []):
        if t.get("id") == target_id:
            tab_entry = t
            break
    if not tab_entry:
        return jsonify({
            "ok": False,
            "error": f"Target tab '{target_id}' not found — was it closed?",
        }), 404
    ws_url = tab_entry.get("webSocketDebuggerUrl", "")

    # Find DCP admin tab (for re-activating after replay)
    dcp_match = cdp_client.find_target_by_url(targets, "localhost:8000")
    dcp_tab_id = dcp_match.get("id") if dcp_match else None

    # ── Merge variables ───────────────────────────────────────
    variables = data.get("variables") or {}

    # ── Create callback that publishes to the event bus ────────
    def _bus_callback(event_type: str, event_data: dict):
        """Publish replay events to the global SSE bus."""
        bus.publish(
            event_type,
            key=event_data.get("run_id", ""),
            data=event_data,
        )

    # ── Start the replay ──────────────────────────────────────
    result = start_replay(
        suite=suite,
        target_id=target_id,
        variables=variables,
        callback=_bus_callback,
        ws_url=ws_url,
        dcp_tab_id=dcp_tab_id,
    )

    if isinstance(result, TestRunResult):
        # Startup error — returned a result immediately
        return jsonify({
            "ok": False,
            "error": result.error or "Failed to start replay",
        }), 409

    # result is the run_id string
    run_id = result
    logger.info(
        "Replay started: run=%s, suite=%s (%s), target=%s",
        run_id, suite.id, suite.name, target_id,
    )

    return jsonify({
        "ok": True,
        "run_id": run_id,
        "suite_id": suite.id,
        "suite_name": suite.name,
        "total_steps": len(suite.steps),
        "target_id": target_id,
    })


# ── Cancel replay ──────────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/replay/cancel", methods=["POST"])
def cdp_test_replay_cancel():
    """Cancel the active replay.

    No body required.

    Returns::

        { "ok": true }   — if a replay was running and is now cancelled
        { "ok": false }  — if no replay was running
    """
    from src.core.services.cdp_test.replayer import cancel_active_run

    cancelled = cancel_active_run()
    if not cancelled:
        return jsonify({"ok": False, "error": "No active replay to cancel"}), 404

    logger.info("Replay cancelled by user")
    return jsonify({"ok": True})


# ── Replay status ──────────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/replay/status")
def cdp_test_replay_status():
    """Get the status of the active replay.

    Returns::

        {
            "ok": true,
            "active": true,
            "run_id": "...",
            "suite_id": "...",
        }
    """
    from src.core.services.cdp_test.replayer import get_active_run

    run = get_active_run()
    if run is None:
        return jsonify({"ok": True, "active": False})

    return jsonify({
        "ok": True,
        "active": True,
        "run_id": run.run_id,
        "suite_id": run.suite_id,
    })
