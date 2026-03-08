"""
CDP Port Injector — injects a DCP notification banner into
Chrome tabs pointing at a port occupied by a foreign process.

Only active during fallback mode.  Only targets non-DCP processes
(DCP instances are handled by PID takeover in server_lifecycle.py).

Chrome renders everything as a page — HTML apps, JSON API responses,
error pages all have ``document.body``.  CDP can inject into all
of them via ``evaluate_js()``.

Lifecycle:
    - Started by ``run_server()`` when fallback mode is detected
    - Runs as a daemon thread (dies with the server process)
    - Polls every ``POLL_INTERVAL`` seconds for new tabs
    - One-shot per Chrome target ID (won't re-inject after dismiss)
    - Backs off after consecutive CDP failures
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

# ── Tunables ──────────────────────────────────────────────────

POLL_INTERVAL = 10      # seconds between scans
MAX_CDP_FAILURES = 5    # consecutive failures before backoff
BACKOFF_INTERVAL = 60   # seconds between scans in backoff mode

# ── Thread state ──────────────────────────────────────────────

_stop_event: threading.Event | None = None
_thread: threading.Thread | None = None

# ── Injection JS template ────────────────────────────────────

_JS_TEMPLATE = r"""(function() {
    if (document.getElementById('__dcp_port_banner')) return 'already_injected';
    if (!document.body) return 'no_body';

    var banner = document.createElement('div');
    banner.id = '__dcp_port_banner';
    banner.style.cssText = [
        'position:fixed',
        'top:0',
        'left:0',
        'right:0',
        'z-index:2147483647',
        'background:linear-gradient(135deg, #1e1b4b 0%, #312e81 100%)',
        'color:#e0e7ff',
        'font-family:system-ui,-apple-system,sans-serif',
        'font-size:13px',
        'padding:10px 16px',
        'display:flex',
        'align-items:center',
        'justify-content:space-between',
        'gap:12px',
        'box-shadow:0 2px 12px rgba(0,0,0,0.4)',
        'border-bottom:2px solid rgba(129,140,248,0.4)',
    ].join(';');

    banner.innerHTML =
        '<div style="display:flex;align-items:center;gap:10px">' +
            '<span style="font-size:18px">\u26a1</span>' +
            '<div>' +
                '<div style="font-weight:600;font-size:13px">' +
                    'DevOps Control Plane' +
                '</div>' +
                '<div style="font-size:12px;opacity:0.85;margin-top:2px">' +
                    'Admin panel is running on ' +
                    '<a href="http://${HOST}:${PORT}" ' +
                       'style="color:#a5b4fc;text-decoration:underline;' +
                       'font-weight:600">' +
                        'localhost:${PORT}' +
                    '</a>' +
                '</div>' +
            '</div>' +
        '</div>' +
        '<button onclick="this.parentElement.remove()" ' +
            'style="background:rgba(255,255,255,0.1);border:1px solid ' +
            'rgba(255,255,255,0.2);color:#c7d2fe;cursor:pointer;' +
            'font-size:12px;padding:4px 10px;border-radius:4px">' +
            'Dismiss' +
        '</button>';

    document.body.insertBefore(banner, document.body.firstChild);
    return 'injected';
})()"""


# ── Core logic ────────────────────────────────────────────────


def _build_injection_js(host: str, port: int) -> str:
    """Build the JS payload with actual host:port values."""
    return (
        _JS_TEMPLATE
        .replace("${HOST}", host)
        .replace("${PORT}", str(port))
    )


def _injector_loop(
    host: str,
    preferred_port: int,
    actual_port: int,
    stop_event: threading.Event,
) -> None:
    """Background loop: find tabs on preferred port, inject banner."""
    consecutive_failures = 0
    injected_targets: set[str] = set()

    while not stop_event.is_set():
        interval = (
            BACKOFF_INTERVAL
            if consecutive_failures >= MAX_CDP_FAILURES
            else POLL_INTERVAL
        )

        try:
            from src.ui.web import cdp_client

            if not cdp_client.is_available():
                consecutive_failures += 1
                stop_event.wait(interval)
                continue

            targets = cdp_client.get_targets()
            port_pattern = f"localhost:{preferred_port}"

            # Find page-type tabs pointing at the preferred port
            candidates = [
                t for t in targets
                if t.get("type") == "page"
                and port_pattern in (t.get("url") or "")
                and t["id"] not in injected_targets
            ]

            for target in candidates:
                ws_url = target.get("webSocketDebuggerUrl")
                if not ws_url:
                    continue

                js = _build_injection_js(host, actual_port)
                result = cdp_client.evaluate_js(ws_url, js, timeout=3.0)

                if result:
                    value = (
                        result.get("result", {})
                        .get("result", {})
                        .get("value")
                    )
                    if value in ("injected", "already_injected"):
                        injected_targets.add(target["id"])
                        logger.info(
                            "CDP: injected DCP banner → %s",
                            target.get("url", "?")[:80],
                        )

            consecutive_failures = 0

            # Prune closed tabs from tracking set
            current_ids = {t["id"] for t in targets}
            injected_targets &= current_ids

        except Exception as exc:
            consecutive_failures += 1
            logger.debug("CDP injector error: %s", exc)

        stop_event.wait(interval)


# ── Public API ────────────────────────────────────────────────


def start_injector(
    host: str,
    preferred_port: int,
    actual_port: int,
) -> None:
    """Start the CDP port injector as a daemon thread.

    Safe to call even if CDP is not available — the thread
    will back off and retry periodically.
    """
    global _stop_event, _thread

    if _thread and _thread.is_alive():
        logger.debug("CDP injector already running")
        return

    _stop_event = threading.Event()
    _thread = threading.Thread(
        target=_injector_loop,
        args=(host, preferred_port, actual_port, _stop_event),
        daemon=True,
        name="cdp-port-injector",
    )
    _thread.start()
    logger.info(
        "CDP port injector started (watching tabs on :%d, "
        "redirecting to :%d)",
        preferred_port,
        actual_port,
    )


def stop_injector() -> None:
    """Stop the injector thread (if running)."""
    global _stop_event
    if _stop_event:
        _stop_event.set()
        logger.debug("CDP port injector stop requested")
