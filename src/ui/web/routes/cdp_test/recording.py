"""
CDP Test recording control endpoints.

Routes registered on ``cdp_test_bp`` from the parent package.

Endpoints:
    POST /cdp-test/record/start     — start recording (inject recorder)
    POST /cdp-test/record/stop      — stop recording (remove recorder)
    POST /cdp-test/record/pause     — pause recording
    POST /cdp-test/record/resume    — resume recording
    POST /cdp-test/record/restart   — clear steps, re-inject
    POST /cdp-test/record/event     — receive event from recorder JS
    GET  /cdp-test/record/status    — current session status + steps
    GET  /cdp-test/targets          — list browser tabs available for recording
"""

from __future__ import annotations

import logging

from flask import jsonify, request

from . import cdp_test_bp

logger = logging.getLogger(__name__)


# ── Private Network Access headers ────────────────────────────
# Chrome blocks requests from public origins (e.g. github.io)
# to private networks (localhost) unless these headers are present.

def _add_pna_cors(resp):
    """Add CORS + Private Network Access headers to a response."""
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Private-Network"] = "true"
    return resp


# ── Start recording ────────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/record/start", methods=["POST"])
def cdp_test_record_start():
    """Start a recording session.

    Body (JSON):
        {
            "target_url": "http://localhost:3000"  // URL pattern to find tab
        }

    Finds a matching Chrome tab, injects the recorder script,
    and starts capturing events.
    """
    from src.ui.web import cdp_client
    from src.core.services.cdp_test.session import create_session
    from src.core.services.cdp_test.recorder import inject_recorder, start_watcher
    from src.core.services.event_bus import bus

    data = request.get_json(silent=True) or {}
    target_url = data.get("target_url", "")
    if not target_url:
        return jsonify({"ok": False, "error": "target_url is required"}), 400

    # Check CDP availability
    if not cdp_client.is_available():
        return jsonify({
            "ok": False,
            "error": "Chrome DevTools Protocol not available. "
                     "Launch Chrome with --remote-debugging-port=9222",
        }), 503

    # Find matching tab
    targets = cdp_client.get_targets()
    target = cdp_client.find_target_by_url(targets, target_url)

    if target is None:
        # Try creating a new tab
        target = cdp_client.create_tab(target_url)
        if target is None:
            return jsonify({
                "ok": False,
                "error": f"No browser tab found matching '{target_url}' "
                         "and could not create one",
            }), 404

    target_id = target.get("id", "")
    ws_url = target.get("webSocketDebuggerUrl", "")
    if not ws_url:
        return jsonify({
            "ok": False,
            "error": "Target tab has no WebSocket debugger URL",
        }), 500

    # Determine DCP callback address
    # Use the request's host so Chrome can reach us back
    dcp_host = request.host.split(":")[0]  # e.g. "localhost"
    dcp_port = int(request.host.split(":")[-1]) if ":" in request.host else 80

    # Create session
    session = create_session(target_url, target_id, ws_url)

    # Inject recorder
    ok = inject_recorder(ws_url, session.id, dcp_host, dcp_port)
    if not ok:
        from src.core.services.cdp_test.session import end_session
        end_session()
        return jsonify({
            "ok": False,
            "error": "Failed to inject recorder into target tab",
        }), 500

    # Start navigation watcher (re-injects on page navigation)
    start_watcher(session.id, target_id, dcp_host, dcp_port)

    # Publish event
    bus.publish(
        "cdp_test:record_start",
        key=session.id,
        data={
            "session_id": session.id,
            "target_url": target_url,
            "target_title": target.get("title", ""),
        },
    )

    logger.info("Recording started: %s → %s", session.id, target_url)
    return jsonify({
        "ok": True,
        "session_id": session.id,
        "target": {
            "id": target_id,
            "url": target.get("url", ""),
            "title": target.get("title", ""),
        },
    })


# ── Stop recording ─────────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/record/stop", methods=["POST"])
def cdp_test_record_stop():
    """Stop the active recording session.

    Removes the recorder from the tab, stops the watcher,
    and returns the recorded steps as a suite draft.
    """
    from src.core.services.cdp_test.session import get_active_session, end_session
    from src.core.services.cdp_test.recorder import remove_recorder, stop_watcher
    from src.core.services.event_bus import bus

    session = get_active_session()
    if session is None:
        return jsonify({"ok": False, "error": "No active recording session"}), 404

    # Remove recorder from the page
    remove_recorder(session.target_ws_url)

    # Stop the navigation watcher
    stop_watcher()

    # End the session
    steps = session.get_steps()
    session_id = session.id
    target_url = session.target_url
    end_session()

    # Publish event
    bus.publish(
        "cdp_test:record_stop",
        key=session_id,
        data={
            "session_id": session_id,
            "step_count": len(steps),
        },
    )

    logger.info("Recording stopped: %s (%d steps)", session_id, len(steps))
    return jsonify({
        "ok": True,
        "session_id": session_id,
        "steps_count": len(steps),
        "steps": steps,
        "suite_draft": {
            "name": "",
            "target_url": target_url,
            "steps": steps,
            "variables": {},
        },
    })


# ── Pause recording ───────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/record/pause", methods=["POST"])
def cdp_test_record_pause():
    """Pause the active recording (events still flow but are ignored)."""
    from src.core.services.cdp_test.session import get_active_session
    from src.core.services.cdp_test.recorder import pause_recorder
    from src.core.services.event_bus import bus

    session = get_active_session()
    if session is None:
        return jsonify({"ok": False, "error": "No active recording session"}), 404

    ok = pause_recorder(session.target_ws_url)
    if ok:
        session.status = "paused"
        bus.publish(
            "cdp_test:record_paused",
            key=session.id,
            data={"session_id": session.id},
        )
    return jsonify({"ok": ok})


# ── Resume recording ──────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/record/resume", methods=["POST"])
def cdp_test_record_resume():
    """Resume a paused recording."""
    from src.core.services.cdp_test.session import get_active_session
    from src.core.services.cdp_test.recorder import resume_recorder
    from src.core.services.event_bus import bus

    session = get_active_session()
    if session is None:
        return jsonify({"ok": False, "error": "No active recording session"}), 404

    ok = resume_recorder(session.target_ws_url)
    if ok:
        session.status = "recording"
        bus.publish(
            "cdp_test:record_resumed",
            key=session.id,
            data={"session_id": session.id},
        )
    return jsonify({"ok": ok})


# ── Restart recording ─────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/record/restart", methods=["POST"])
def cdp_test_record_restart():
    """Clear recorded steps and restart (re-inject recorder)."""
    from src.core.services.cdp_test.session import get_active_session
    from src.core.services.cdp_test.recorder import (
        remove_recorder, inject_recorder,
    )

    session = get_active_session()
    if session is None:
        return jsonify({"ok": False, "error": "No active recording session"}), 404

    # Determine DCP callback address
    dcp_host = request.host.split(":")[0]
    dcp_port = int(request.host.split(":")[-1]) if ":" in request.host else 80

    # Remove old recorder, clear steps, re-inject
    remove_recorder(session.target_ws_url)
    session.clear_steps()
    session.status = "recording"

    ok = inject_recorder(
        session.target_ws_url, session.id, dcp_host, dcp_port,
    )
    return jsonify({"ok": ok, "session_id": session.id})


# ── Receive event from recorder JS ────────────────────────────


@cdp_test_bp.route("/cdp-test/record/event", methods=["POST"])
def cdp_test_record_event():
    """Receive a captured event from the injected recorder.

    This endpoint is called by the recorder JS in the foreign page
    via navigator.sendBeacon() or fetch().

    Body (JSON): event data including action, selector, value, etc.

    CORS headers are set to allow cross-origin requests from the
    recorded page.
    """
    from flask import make_response
    from src.core.services.cdp_test.session import get_active_session
    from src.core.services.event_bus import bus

    # Handle CORS preflight (shouldn't reach here — OPTIONS route below)
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        return _add_pna_cors(resp)

    session = get_active_session()
    if session is None:
        resp = jsonify({"ok": False, "error": "No active session"})
        _add_pna_cors(resp)
        return resp, 404

    data = request.get_json(silent=True) or {}

    # Validate session ID — old recorder scripts from previous sessions
    # may still be running in the page; ignore their events gracefully.
    if data.get("session_id") != session.id:
        logger.debug(
            "Ignoring event from stale session %s (active: %s)",
            data.get("session_id", "?"), session.id,
        )
        resp = jsonify({"ok": True, "ignored": True})
        return resp

    # Skip if paused
    if session.status == "paused":
        resp = jsonify({"ok": True, "skipped": True})
        _add_pna_cors(resp)
        return resp

    # Skip internal recorder actions (ping, etc.) — not user interactions
    if data.get("action") in ("ping",):
        resp = jsonify({"ok": True, "ignored": True})
        _add_pna_cors(resp)
        return resp

    # Add step to session
    step_data = {
        "action": data.get("action", ""),
        "selector": data.get("selector", ""),
        "xpath": data.get("xpath", ""),
        "selector_alternatives": data.get("selector_alternatives", []),
        "value": data.get("value", ""),
        "page_url": data.get("page_url", ""),
        "element_tag": data.get("element_tag", ""),
        "element_text": data.get("element_text", ""),
        "element_rect": data.get("element_rect", {}),
        "timestamp_ms": data.get("timestamp_ms", 0),
    }

    # Flatten assertion config into replayer-compatible step fields
    ac = data.get("assert_config")
    if ac:
        step_data["assertion_type"] = ac.get("check_type", "exists")
        step_data["assertion_expected"] = ac.get("expected", "")
        step_data["assertion_attribute"] = ac.get("attribute_name", "")
        step_data["case_sensitive"] = ac.get("case_sensitive", True)
        on_fail = ac.get("on_fail", {})
        if on_fail:
            step_data["on_fail"] = on_fail

    step = session.add_step(step_data)

    # Broadcast to admin panel via event bus
    bus.publish(
        "cdp_test:step_captured",
        key=session.id,
        data={
            "session_id": session.id,
            "step": step,
        },
    )

    resp = jsonify({
        "ok": True,
        "step_id": step["id"],
        "sequence": step["sequence"],
    })
    _add_pna_cors(resp)
    return resp


# ── CORS preflight for /record/event ──────────────────────────


@cdp_test_bp.route("/cdp-test/record/event", methods=["OPTIONS"])
def cdp_test_record_event_options():
    """Handle CORS preflight for the event endpoint.

    Must include Access-Control-Allow-Private-Network for Chrome's
    Private Network Access checks (public origin → localhost).
    """
    from flask import make_response

    resp = make_response("", 204)
    return _add_pna_cors(resp)


# ── Add step (admin panel — insert assertion/capture/diag) ─────


@cdp_test_bp.route("/cdp-test/record/add-step", methods=["POST"])
def cdp_test_record_add_step():
    """Insert a step into the recording at a specific position.

    Used by the admin panel modals to add assertion, capture,
    or diagnostic steps after a given step.

    Body (JSON):
        {
            "action": "assert" | "capture_*" | "inject_js" | ...,
            "selector": "...",
            "after_step_id": "uuid",   // insert after this step
            "assert_config": { ... },  // for assertions
            "diagnostic_steps": [...], // for assertions
            "value": "...",            // for capture/inject_js
        }
    """
    from src.core.services.cdp_test.session import get_active_session
    from src.core.services.event_bus import bus

    session = get_active_session()
    if session is None:
        return jsonify({"ok": False, "error": "No active recording session"}), 404

    data = request.get_json(silent=True) or {}
    after_step_id = data.pop("after_step_id", "")

    # Build step data from payload
    step_data = {
        "action": data.get("action", ""),
        "selector": data.get("selector", ""),
        "value": data.get("value", ""),
        "page_url": data.get("page_url", ""),
        "timestamp_ms": data.get("timestamp_ms", 0),
    }

    # Flatten assertion config into replayer-compatible step fields
    ac = data.get("assert_config")
    if ac:
        step_data["assertion_type"] = ac.get("check_type", "exists")
        step_data["assertion_expected"] = ac.get("expected", "")
        step_data["assertion_attribute"] = ac.get("attribute_name", "")
        step_data["case_sensitive"] = ac.get("case_sensitive", True)
        # Preserve on_fail config for branching during replay
        on_fail = ac.get("on_fail", {})
        if on_fail:
            step_data["on_fail"] = on_fail

    # Pass through diagnostic steps if present
    if data.get("diagnostic_steps"):
        step_data["diagnostic_steps"] = data["diagnostic_steps"]

    step = session.insert_step_after(after_step_id, step_data)

    # Broadcast update to admin panel
    bus.publish(
        "cdp_test:step_captured",
        key=session.id,
        data={
            "session_id": session.id,
            "step": step,
            "inserted": True,
        },
    )

    logger.info("Step inserted after %s: %s", after_step_id, step["action"])
    return jsonify({
        "ok": True,
        "step_id": step["id"],
        "sequence": step["sequence"],
    })


# ── Eval JS in target page (admin panel live preview) ──────────


@cdp_test_bp.route("/cdp-test/record/eval", methods=["POST"])
def cdp_test_record_eval():
    """Evaluate JavaScript in the recording target page.

    Used by the admin panel to fetch live element values
    for assertion preview.

    Body (JSON):
        {
            "js": "document.querySelector('#foo').textContent"
        }

    Returns:
        { "ok": true, "value": "the result" }
    """
    from src.ui.web import cdp_client
    from src.core.services.cdp_test.session import get_active_session

    session = get_active_session()
    if session is None:
        return jsonify({"ok": False, "error": "No active recording session"}), 404

    data = request.get_json(silent=True) or {}
    js = data.get("js", "")
    if not js:
        return jsonify({"ok": False, "error": "js is required"}), 400

    try:
        cdp_response = cdp_client.evaluate_js(session.target_ws_url, js)
        if cdp_response is None:
            return jsonify({"ok": False, "error": "CDP evaluation returned no result"}), 500

        # CDP Runtime.evaluate response structure:
        # { "id": 1, "result": { "result": { "type": "string", "value": "..." } } }
        result_obj = cdp_response.get("result", {}).get("result", {})
        value = result_obj.get("value", result_obj.get("description", ""))

        return jsonify({"ok": True, "value": value})
    except Exception as e:
        logger.warning("Eval failed: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Recording status ───────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/record/status")
def cdp_test_record_status():
    """Get current recording session status and steps."""
    from src.core.services.cdp_test.session import get_active_session

    session = get_active_session()
    if session is None:
        return jsonify({
            "ok": True,
            "active": False,
            "session": None,
        })

    return jsonify({
        "ok": True,
        "active": True,
        "session": {
            "id": session.id,
            "target_url": session.target_url,
            "target_id": session.target_id,
            "status": session.status,
            "step_count": session.step_count,
            "steps": session.get_steps(),
            "started_at": session.started_at,
        },
    })


# ── List available targets ─────────────────────────────────────


@cdp_test_bp.route("/cdp-test/targets")
def cdp_test_list_targets():
    """List browser tabs available for recording."""
    from src.ui.web import cdp_client

    if not cdp_client.is_available():
        return jsonify({
            "ok": False,
            "error": "Chrome DevTools Protocol not available",
            "targets": [],
        }), 503

    targets = cdp_client.get_targets()
    pages = [
        {
            "id": t.get("id", ""),
            "url": t.get("url", ""),
            "title": t.get("title", ""),
        }
        for t in targets
        if t.get("type") == "page"
        and not (t.get("url", "").startswith("devtools://"))
        and not (t.get("url", "").startswith("chrome-devtools://"))
        and not (t.get("url", "").startswith("chrome://"))
    ]

    return jsonify({"ok": True, "targets": pages})
