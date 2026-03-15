"""
CDP Test browser management endpoints.

Routes registered on ``cdp_test_bp`` from the parent package.

Endpoints:
    POST /cdp-test/launch-browser   — launch a separate Chrome instance
    POST /cdp-test/kill-browser     — kill a previously launched instance
    GET  /cdp-test/browser-status   — check status of a launched instance
"""

from __future__ import annotations

import logging

from flask import jsonify, request

from src.core.services.events.tracked import tracked

from . import cdp_test_bp

logger = logging.getLogger(__name__)


# ── Launch browser ─────────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/launch-browser", methods=["POST"])
@tracked("cdp_test.browser.launched")
def cdp_test_launch_browser():
    """Launch a separate Chrome instance for isolated test replay.

    Body (JSON)::

        {
            "headless": false,           // optional, default false
            "url": "http://example.com", // optional — opens this URL
        }

    Returns::

        {
            "ok": true,
            "port": 9223,
            "pid": 12345,
            "endpoint": "http://localhost:9223",
        }

    Error responses::

        503 — Chrome is not installed (includes install_plan)
        500 — Launch failed (includes error details)
    """
    from src.core.services.chrome.launcher import (
        ChromeLaunchConfig,
        ChromeNotInstalled,
        ChromeNoDisplay,
        ChromeStartupFailed,
        get_launcher,
        require_chrome,
    )

    data = request.get_json(silent=True) or {}

    # Pre-check: is Chrome available?
    status = require_chrome()
    if not status["available"]:
        return jsonify({
            "ok": False,
            "error": "Chrome is not installed",
            "install_plan": status.get("install_plan"),
        }), 503

    # Build launch config
    config = ChromeLaunchConfig(
        headless=bool(data.get("headless", False)),
        landing_url=data.get("url", ""),
        no_first_run=True,
    )

    launcher = get_launcher()

    try:
        instance = launcher.launch(config)
    except ChromeNotInstalled:
        return jsonify({
            "ok": False,
            "error": "Chrome binary not found",
            "install_plan": status.get("install_plan"),
        }), 503
    except ChromeNoDisplay:
        return jsonify({
            "ok": False,
            "error": (
                "No display available. Use headless mode or configure "
                "a display (DISPLAY env var)."
            ),
        }), 503
    except ChromeStartupFailed as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
            "stderr": getattr(exc, "stderr", ""),
        }), 500
    except Exception as exc:
        logger.exception("Unexpected error launching Chrome")
        return jsonify({
            "ok": False,
            "error": f"Unexpected launch error: {exc}",
        }), 500

    logger.info(
        "Launched test browser: port=%d pid=%d",
        instance.port, instance.pid,
    )

    return jsonify({
        "ok": True,
        "port": instance.port,
        "pid": instance.pid,
        "endpoint": instance.endpoint,
    })


# ── Kill browser ───────────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/kill-browser", methods=["POST"])
@tracked("cdp_test.browser.killed")
def cdp_test_kill_browser():
    """Kill a previously launched test Chrome instance.

    Body (JSON)::

        { "port": 9223 }

    Returns::

        { "ok": true, "killed": true }

    Error responses::

        400 — port is required
        404 — no instance found on that port
    """
    from src.core.services.chrome.launcher import get_launcher

    data = request.get_json(silent=True) or {}
    port = data.get("port")
    if port is None:
        return jsonify({"ok": False, "error": "port is required"}), 400
    port = int(port)

    launcher = get_launcher()

    # Find the instance by port
    instance = launcher.get_instance(port)

    if instance is None:
        return jsonify({
            "ok": False,
            "error": f"No launched instance found on port {port}",
        }), 404

    try:
        launcher.kill_instance(instance)
    except Exception as exc:
        logger.warning("Error killing instance on port %d: %s", port, exc)
        return jsonify({
            "ok": False,
            "error": f"Failed to kill instance: {exc}",
        }), 500

    logger.info("Killed test browser on port %d", port)
    return jsonify({"ok": True, "killed": True})


# ── Browser status ─────────────────────────────────────────────


@cdp_test_bp.route("/cdp-test/browser-status")
def cdp_test_browser_status():
    """Check status of launched Chrome instances.

    Returns::

        {
            "ok": true,
            "instances": [
                {
                    "port": 9223,
                    "pid": 12345,
                    "endpoint": "http://localhost:9223",
                    "ready": true,
                }
            ]
        }
    """
    from src.core.services.chrome.launcher import get_launcher
    from src.ui.web import cdp_client

    launcher = get_launcher()
    instances = []
    for inst in launcher.list_instances():
        ready = cdp_client.is_available(port=inst.port)
        instances.append({
            "port": inst.port,
            "pid": inst.pid,
            "endpoint": inst.endpoint,
            "ready": ready,
        })

    return jsonify({"ok": True, "instances": instances})
