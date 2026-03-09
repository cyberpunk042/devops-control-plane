"""
CDP recorder injection — injects and manages the recorder script
in the foreign page.

Handles:
- Initial injection via evaluate_js()
- Re-injection on page navigation (watcher thread)
- Pause/resume via JS flag manipulation
- Recorder removal on stop
"""

from __future__ import annotations

import json
import logging
import string
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to the recorder JS template
_RECORDER_JS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cdp_recorder.js"


# ── Recorder JS loading ───────────────────────────────────────


def _load_recorder_js(
    session_id: str,
    dcp_host: str,
    dcp_port: int,
) -> str:
    """Load and parameterize the recorder JS template.

    Replaces template variables:
        ${SESSION_ID}  → session UUID
        ${DCP_HOST}    → DCP server host
        ${DCP_PORT}    → DCP server port
    """
    raw = _RECORDER_JS_PATH.read_text(encoding="utf-8")

    # Use string.Template for safe substitution ($ prefix)
    tmpl = string.Template(raw)
    return tmpl.safe_substitute(
        SESSION_ID=session_id,
        DCP_HOST=dcp_host,
        DCP_PORT=str(dcp_port),
    )


# ── Injection ──────────────────────────────────────────────────


def inject_recorder(
    target_ws_url: str,
    session_id: str,
    dcp_host: str,
    dcp_port: int,
) -> bool:
    """Inject the recorder script into a Chrome tab.

    Args:
        target_ws_url: WebSocket debugger URL for the target tab
        session_id: Recording session UUID
        dcp_host: DCP server host (for callback URL)
        dcp_port: DCP server port (for callback URL)

    Returns:
        True if injection succeeded.
    """
    from src.ui.web import cdp_client

    js = _load_recorder_js(session_id, dcp_host, dcp_port)
    result = cdp_client.evaluate_js(target_ws_url, js, timeout=5.0)

    if result is None:
        logger.warning("CDP recorder injection failed — no response")
        return False

    # Log full response for diagnosis
    logger.debug("CDP recorder inject response: %s", result)

    # CDP returns: {"id":1, "result": {"result": {"type":"string","value":"injected"}}}
    # But sometimes the structure varies — try multiple paths
    inner = result.get("result", {})
    value = inner.get("result", {}).get("value")

    # Fallback: some CDP responses have exceptionDetails instead of result
    if value is None and "exceptionDetails" in inner:
        exc_text = inner["exceptionDetails"].get("text", "")
        logger.warning("CDP recorder injection threw: %s", exc_text)
        return False

    if value is None:
        # Last resort: log the full response for investigation
        logger.warning(
            "CDP recorder injection unexpected result (value=None): %s",
            json.dumps(result, default=str)[:500],
        )
        return False

    if value == "injected":
        logger.info("CDP recorder injected: fresh")
        return True

    if value == "already_active":
        # Recorder from a previous session is still running —
        # update its session_id so events match the NEW session
        update_js = f"(function(){{ window.__dcp_session_id = '{session_id}'; return 'session_updated'; }})()"
        upd = cdp_client.evaluate_js(target_ws_url, update_js, timeout=3.0)
        upd_val = (upd or {}).get("result", {}).get("result", {}).get("value")
        logger.info(
            "CDP recorder already_active — session_id updated: %s", upd_val,
        )
        return True

    logger.warning("CDP recorder injection returned: %s", value)
    return False


def remove_recorder(target_ws_url: str) -> bool:
    """Remove the recorder from a Chrome tab.

    Calls the cleanup function injected by the recorder script.
    """
    from src.ui.web import cdp_client

    js = """
    (function() {
        if (window.__dcp_recorder_cleanup) {
            window.__dcp_recorder_cleanup();
            return 'removed';
        }
        return 'not_found';
    })()
    """
    result = cdp_client.evaluate_js(target_ws_url, js, timeout=3.0)
    if result:
        value = result.get("result", {}).get("result", {}).get("value")
        logger.info("CDP recorder removal: %s", value)
        return value == "removed"
    return False


def check_recorder_alive(target_ws_url: str) -> bool:
    """Check if the recorder is still active in the tab."""
    from src.ui.web import cdp_client

    js = "(function() { return !!window.__dcp_recorder_active; })()"
    result = cdp_client.evaluate_js(target_ws_url, js, timeout=5.0)
    if result:
        value = result.get("result", {}).get("result", {}).get("value")
        return value is True
    return False


def pause_recorder(target_ws_url: str) -> bool:
    """Tell the recorder to stop capturing (but stay injected)."""
    from src.ui.web import cdp_client

    js = """
    (function() {
        if (window.__dcp_recorder_active) {
            window.__dcp_recorder_paused = true;
            var ind = document.getElementById('__dcp_recorder_indicator');
            if (ind) {
                ind.style.background = 'rgba(100,100,100,0.9)';
                ind.querySelector('span:last-child').textContent = 'DCP Paused';
            }
            return 'paused';
        }
        return 'not_active';
    })()
    """
    result = cdp_client.evaluate_js(target_ws_url, js, timeout=2.0)
    if result:
        value = result.get("result", {}).get("result", {}).get("value")
        return value == "paused"
    return False


def resume_recorder(target_ws_url: str) -> bool:
    """Tell the recorder to resume capturing."""
    from src.ui.web import cdp_client

    js = """
    (function() {
        if (window.__dcp_recorder_active) {
            window.__dcp_recorder_paused = false;
            var ind = document.getElementById('__dcp_recorder_indicator');
            if (ind) {
                ind.style.background = 'rgba(220,38,38,0.9)';
                ind.querySelector('span:last-child').textContent = 'DCP Recording';
            }
            return 'resumed';
        }
        return 'not_active';
    })()
    """
    result = cdp_client.evaluate_js(target_ws_url, js, timeout=2.0)
    if result:
        value = result.get("result", {}).get("result", {}).get("value")
        return value == "resumed"
    return False


# ── Navigation Watcher ─────────────────────────────────────────


_watcher_thread: threading.Thread | None = None
_watcher_stop = threading.Event()


def start_watcher(
    session_id: str,
    target_id: str,
    dcp_host: str,
    dcp_port: int,
) -> None:
    """Start a background thread that re-injects the recorder on navigation.

    Traditional page navigations destroy the recorder (new DOM context).
    This watcher polls the target tab and re-injects when needed.
    """
    global _watcher_thread
    stop_watcher()  # Stop any existing watcher

    _watcher_stop.clear()

    def _watch_loop() -> None:
        from src.ui.web import cdp_client

        consecutive_failures = 0
        while not _watcher_stop.is_set():
            _watcher_stop.wait(5.0)  # Check every 5 seconds
            if _watcher_stop.is_set():
                break

            from src.core.services.cdp_test.session import get_active_session

            session = get_active_session()
            if session is None or session.id != session_id:
                logger.debug("Watcher: session ended, stopping")
                break

            if session.status != "recording":
                continue  # Don't re-inject while paused

            try:
                targets = cdp_client.get_targets()
                target = None
                for t in targets:
                    if t.get("id") == target_id:
                        target = t
                        break

                if target is None:
                    # Tab was closed
                    consecutive_failures += 1
                    if consecutive_failures >= 5:
                        logger.warning("Watcher: target tab closed, stopping")
                        from src.core.services.event_bus import bus
                        bus.publish(
                            "cdp_test:recorder_lost",
                            key=session_id,
                            data={"reason": "tab_closed"},
                        )
                        break
                    continue

                # Tab exists — check if recorder is alive
                ws_url = target.get("webSocketDebuggerUrl", "")
                if not ws_url:
                    continue

                # Update session's ws_url (it can change after navigation)
                session.target_ws_url = ws_url

                alive = check_recorder_alive(ws_url)
                if not alive:
                    # Recorder died (page navigated) — re-inject
                    logger.info("Watcher: recorder lost, re-injecting...")
                    ok = inject_recorder(ws_url, session_id, dcp_host, dcp_port)
                    if ok:
                        from src.core.services.event_bus import bus
                        bus.publish(
                            "cdp_test:recorder_injected",
                            key=session_id,
                            data={"target_url": target.get("url", "")},
                        )

                consecutive_failures = 0

            except Exception as exc:
                consecutive_failures += 1
                logger.debug("Watcher error: %s", exc)
                if consecutive_failures >= 10:
                    logger.warning("Watcher: too many failures, stopping")
                    break

    _watcher_thread = threading.Thread(
        target=_watch_loop,
        name="cdp-recorder-watcher",
        daemon=True,
    )
    _watcher_thread.start()
    logger.info("Recorder watcher started for session %s", session_id)


def stop_watcher() -> None:
    """Stop the navigation watcher thread."""
    global _watcher_thread
    _watcher_stop.set()
    if _watcher_thread is not None:
        _watcher_thread.join(timeout=5.0)
        _watcher_thread = None
    _watcher_stop.clear()
