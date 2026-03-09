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


# ── Live capture helpers ──────────────────────────────────────


def _capture_screenshot_live(session, step: dict) -> None:
    """Take a screenshot NOW during recording and attach to step.

    Uses a temporary CdpSession to call Page.captureScreenshot.
    The resulting PNG is saved to .state/cdp-tests/screenshots/
    and the step dict is updated with screenshot_path.

    For element screenshots: uses the pre-captured element_rect
    (from when the user right-clicked, BEFORE the modal opened)
    so the clip is accurate even if the element changed state
    (e.g. textarea lost focus and collapsed).

    For full-page screenshots (capture_screenshot_full): no clip.
    """
    import base64
    from pathlib import Path

    from src.ui.web import cdp_client
    from src.ui.web.helpers import project_root as _project_root

    action = step.get("action", "")
    is_full_page = action == "capture_screenshot_full"

    try:
        with cdp_client.CdpSession(session.target_ws_url, connect_timeout=5.0) as cdp:
            if not cdp.connected:
                logger.warning("Live screenshot: CDP not connected")
                return

            clip = None
            # captureBeyondViewport causes Chrome to temporarily resize the
            # page layout (triggers media queries, reflows) — only use it
            # for full-page captures. Element screenshots use viewport-
            # relative coordinates with captureBeyondViewport=false.
            capture_beyond = is_full_page

            if not is_full_page:
                # ── Element screenshot: use pre-captured rect ─────
                # element_rect was captured at right-click time (via
                # getBoundingClientRect) — VIEWPORT-relative.
                # CDP clip needs PAGE coordinates, so add scroll offsets.
                # Keep captureBeyondViewport=false to avoid Chrome
                # resizing/reflowing the page (element is visible).
                pre_rect = step.get("element_rect", {})
                if (pre_rect
                        and pre_rect.get("width", 0) > 0
                        and pre_rect.get("height", 0) > 0):
                    # Get scroll offset + devicePixelRatio
                    scroll_js = "(function(){ return JSON.stringify({ sx: window.scrollX, sy: window.scrollY, dpr: window.devicePixelRatio || 1 }); })()"
                    scroll_result = cdp.evaluate(scroll_js, timeout=2.0)
                    import json as _json
                    scroll_val = (
                        scroll_result.get("result", {}).get("result", {}).get("value", "{}")
                        if scroll_result else "{}"
                    )
                    scroll = _json.loads(scroll_val) if scroll_val else {}
                    sx = scroll.get("sx", 0)
                    sy = scroll.get("sy", 0)
                    dpr = scroll.get("dpr", 1)

                    # Convert viewport-relative → page coordinates
                    clip = {
                        "x": max(pre_rect["x"] + sx, 0),
                        "y": max(pre_rect["y"] + sy, 0),
                        "width": max(pre_rect["width"], 1),
                        "height": max(pre_rect["height"], 1),
                        "scale": dpr,
                    }
                    logger.debug(
                        "Live screenshot: page clip %s (viewport %s, scroll %d,%d)",
                        clip, pre_rect, sx, sy,
                    )
                else:
                    # Fallback: try to query the DOM (element may have changed)
                    selector = step.get("selector", "")
                    if selector:
                        find_js = f"""(function() {{
                            var el = document.querySelector('{selector.replace("'", "\\\\'")}');
                            if (!el) return JSON.stringify({{ ok: false }});
                            var r = el.getBoundingClientRect();
                            return JSON.stringify({{
                                ok: true,
                                x: Math.max(r.x + window.scrollX, 0),
                                y: Math.max(r.y + window.scrollY, 0),
                                width: r.width, height: r.height,
                                dpr: window.devicePixelRatio || 1
                            }});
                        }})()"""
                        rect_result = cdp.evaluate(find_js, timeout=3.0)
                        rect_val = (
                            rect_result.get("result", {}).get("result", {}).get("value", "{}")
                            if rect_result else "{}"
                        )
                        import json as _json
                        rect = _json.loads(rect_val) if rect_val else {}
                        if rect.get("ok"):
                            clip = {
                                "x": rect["x"], "y": rect["y"],
                                "width": max(rect["width"], 1),
                                "height": max(rect["height"], 1),
                                "scale": rect.get("dpr", 1),
                            }

            params = {"format": "png", "captureBeyondViewport": capture_beyond}
            if clip:
                params["clip"] = clip

            result = cdp.send_command("Page.captureScreenshot", params, timeout=10.0)
            if not result:
                logger.warning("Live screenshot: no CDP response")
                return

            b64_data = result.get("result", {}).get("data", "")
            if not b64_data:
                logger.warning("Live screenshot: no image data")
                return

            # Save to disk
            root = _project_root()
            ss_dir = Path(root) / ".state" / "cdp-tests" / "screenshots"
            ss_dir.mkdir(parents=True, exist_ok=True)

            prefix = "full" if is_full_page else "elem"
            filename = f"rec_{prefix}_{session.id[:8]}_{step['id'][:8]}.png"
            filepath = ss_dir / filename
            filepath.write_bytes(base64.b64decode(b64_data))

            # Update step dict so SSE broadcast includes the path
            step["screenshot_path"] = str(filepath)
            logger.info("Live screenshot saved: %s (%s)", filename,
                        "full page" if is_full_page else f"clip {clip}")

    except Exception as exc:
        logger.warning("Live screenshot failed: %s", exc)


def _capture_console_live(session, step: dict) -> None:
    """Read accumulated console buffer from the target page.

    The recorder JS monkey-patches console methods from the moment
    it's injected, buffering everything into window.__cdp_console_buffer.
    This function reads that buffer and attaches it to the step.
    """
    from src.ui.web import cdp_client

    try:
        # Read the buffer — don't clear it (user may want to capture again)
        read_js = """(function() {
            var entries = window.__cdp_console_buffer || [];
            return JSON.stringify(entries);
        })()"""

        result = cdp_client.evaluate_js(
            session.target_ws_url, read_js, timeout=5.0,
        )
        if not result:
            logger.warning("Live console capture: no CDP response")
            return

        raw = (
            result.get("result", {}).get("result", {}).get("value", "[]")
        )
        if not raw or raw == "[]":
            logger.info("Live console capture: no entries")
            return

        import json as _json
        entries = _json.loads(raw)
        if isinstance(entries, list) and entries:
            step["console_log"] = entries
            logger.info("Live console capture: %d entries", len(entries))

    except Exception as exc:
        logger.warning("Live console capture failed: %s", exc)


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

    # ── Live capture during recording ─────────────────────────
    # Take screenshots/console NOW so results are visible immediately
    action = step_data.get("action", "")

    if action in ("capture_screenshot", "capture_screenshot_full") and session.target_ws_url:
        _capture_screenshot_live(session, step)

    if (action == "capture_console"
            and step_data.get("value") == "stop"
            and session.target_ws_url):
        _capture_console_live(session, step)

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
        # Preserve on_fail config (mode + diagnostics) for replay
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

# ── Recorder diagnostic log ───────────────────────────────────


@cdp_test_bp.route("/cdp-test/record/log", methods=["POST", "OPTIONS"])
def cdp_test_record_log():
    """Receive diagnostic log messages from the injected recorder.

    This endpoint gives visibility into what happens inside the
    target page — modal opens, sendEvent calls, errors, etc.

    Body (JSON):
        {
            "level": "info" | "warn" | "error",
            "msg": "description of what happened",
            "data": { ... }   // optional extra context
        }
    """
    if request.method == "OPTIONS":
        resp = jsonify({"ok": True})
        _add_pna_cors(resp)
        return resp

    data = request.get_json(silent=True) or {}
    level = data.get("level", "info")
    msg = data.get("msg", "")
    extra = data.get("data", {})

    prefix = "[CDP recorder]"
    log_msg = f"{prefix} {msg}"
    if extra:
        log_msg += f" | {extra}"

    if level == "error":
        logger.error(log_msg)
    elif level == "warn":
        logger.warning(log_msg)
    else:
        logger.info(log_msg)

    resp = jsonify({"ok": True})
    _add_pna_cors(resp)
    return resp


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
