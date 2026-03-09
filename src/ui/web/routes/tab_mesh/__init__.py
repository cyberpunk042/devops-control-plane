"""
Tab Mesh CDP routes — tab focus, diagnostics, and remediation.

Provides API endpoints for:
- Checking Chrome DevTools Protocol availability
- Focusing a browser tab via CDP
- Diagnosing the user's Chrome/WSL setup
- Remediating Chrome shortcuts to enable remote debugging
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from flask import Blueprint, jsonify, request

tab_mesh_bp = Blueprint("tab_mesh", __name__)
logger = logging.getLogger(__name__)


# ── Chrome domain imports ─────────────────────────────────────
# Detection functions extracted to src.core.services.chrome.detection

from src.core.services.chrome.detection import (
    is_wsl as _is_wsl,
    get_windows_user as _get_windows_user,
    get_chrome_version as _get_chrome_version,
)
from src.core.services.chrome.profiles import (
    chrome_data_dir as _chrome_data_dir,
    chrome_data_dir_win as _chrome_data_dir_win,
    chrome_debug_data_dir_win as _chrome_debug_data_dir_win,
    read_chrome_profiles as _read_chrome_profiles,
    clone_profile_to_debug_dir as _clone_profile_to_debug_dir,
)
from src.core.services.chrome.shortcuts import (
    CHROME_ICON_DEBUG,
    CHROME_ICON_NORMAL,
    shortcut_locations as _shortcut_locations,
    backup_shortcut_locations as _backup_shortcut_locations,
    wsl_to_win_path as _wsl_to_win_path,
    read_shortcut as _read_shortcut,
    modify_shortcut as _modify_shortcut,
    modify_shortcut_elevated as _modify_shortcut_elevated,
    clone_shortcut as _clone_shortcut,
)


# ── Helpers ───────────────────────────────────────────────────


# Profile functions extracted to src.core.services.chrome.profiles
# (see Chrome domain imports at top of file)


# Shortcut functions extracted to src.core.services.chrome.shortcuts
# (see Chrome domain imports at top of file)


# ── Routes ────────────────────────────────────────────────────


# _clone_profile_to_debug_dir is now imported from src.core.services.chrome.profiles
# (see Chrome domain imports at top of file)


@tab_mesh_bp.route("/tab-mesh/kill-chrome", methods=["POST"])
def kill_chrome():
    """Force-kill all Chrome processes.

    Returns::

        { "killed": true/false, "message": "..." }
    """
    if not _is_wsl():
        return jsonify({"killed": False, "message": "Not running under WSL"}), 400

    try:
        r = subprocess.run(
            ["taskkill.exe", "/F", "/IM", "chrome.exe"],
            capture_output=True, text=True, timeout=10,
        )
        killed = r.returncode == 0 or "not found" in r.stderr.lower()
        return jsonify({
            "killed": killed,
            "message": (
                "All Chrome processes terminated."
                if r.returncode == 0
                else "Chrome was not running."
            ),
        })
    except Exception as exc:
        return jsonify({"killed": False, "message": str(exc)}), 500


@tab_mesh_bp.route("/tab-mesh/restart-chrome", methods=["POST"])
def restart_chrome():
    """Orchestrated Chrome restart for CDP activation.

    1. Reads the user's email from the selected Chrome profile
    2. Schedules a background PS1 script: wait 2s, kill Chrome, relaunch
    3. Returns immediately with the email so the frontend can guide sign-in

    Chrome opens with a fresh debug profile + the admin panel URL.
    The user signs in with their Google account to restore sync data.
    """
    if not _is_wsl():
        return jsonify({"success": False, "error": "Not running under WSL"}), 400

    data = request.get_json(silent=True) or {}
    profile_dir = data.get("profile_dir", "Default")
    return_url = data.get("return_url", "http://127.0.0.1:8000")
    port = data.get("port", 9222)

    windows_user = _get_windows_user()
    if not windows_user:
        return jsonify({"success": False, "error": "Could not detect Windows user"}), 500

    # Read email from the selected profile BEFORE killing Chrome
    data_dir = _chrome_data_dir(windows_user)
    profiles = _read_chrome_profiles(data_dir)
    email = ""
    for p in profiles:
        if p["dir"] == profile_dir:
            email = p.get("email", "")
            break

    debug_dir = _chrome_debug_data_dir_win(windows_user)
    chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

    # Build a landing URL that includes the sign-in hash.
    # The admin panel detects #chrome-signin on load and
    # auto-triggers the CDP-based email pre-fill flow.
    from urllib.parse import quote
    if email:
        landing_url = (
            f"{return_url}#chrome-signin&email={quote(email)}"
        )
    else:
        landing_url = return_url

    ps_content = (
        "Start-Sleep -Seconds 2\n"
        "taskkill /F /IM chrome.exe 2>$null\n"
        "Start-Sleep -Seconds 2\n"
        f'Start-Process "{chrome_exe}" -ArgumentList '
        f'"--remote-debugging-port={port}",'
        f'"--user-data-dir={debug_dir}",'
        f'"--no-first-run",'
        f'"{landing_url}"\n'
    )

    launch_scheduled = False
    try:
        import tempfile
        script_path = os.path.join(tempfile.gettempdir(), "chrome_restart.ps1")
        script_path_win = subprocess.run(
            ["wslpath", "-w", script_path],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()

        with open(script_path, "w") as f:
            f.write(ps_content)

        subprocess.Popen(
            [
                "powershell.exe", "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", script_path_win,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        launch_scheduled = True
        logger.info("Chrome restart script scheduled: %s", script_path_win)
    except Exception as exc:
        logger.warning("Failed to schedule Chrome restart: %s", exc)

    return jsonify({
        "success": launch_scheduled,
        "launch_scheduled": launch_scheduled,
        "email": email,
    })




@tab_mesh_bp.route("/tab-mesh/cdp-status")
def cdp_status():
    """Check if Chrome DevTools Protocol is available.

    Returns::

        {
            "available": true/false,
            "chrome_version": "138.0.6423.82" | null,
            "endpoint": "http://localhost:9222"
        }
    """
    from src.ui.web import cdp_client

    # Try discovery if not yet available
    cdp_client.try_discover_endpoint()
    available = cdp_client.is_available()

    version_info = cdp_client.get_version() if available else None
    browser = version_info.get("Browser", "") if version_info else None

    return jsonify({
        "available": available,
        "chrome_version": browser,
        "endpoint": cdp_client._base_url(),
    })


@tab_mesh_bp.route("/tab-mesh/focus", methods=["POST"])
def focus_tab():
    """Focus a browser tab via CDP.

    Accepts EITHER a direct Chrome target ID (preferred, exact) or
    a URL pattern fallback::

        { "targetId": "CHROME-TARGET-ID" }          # exact
        { "urlPattern": "/pages/site/docs/", ... }   # fallback

    Returns::

        { "success": true, "url": "...", "targetId": "..." }
    """
    from src.ui.web import cdp_client

    data = request.get_json(silent=True) or {}
    direct_target_id = data.get("targetId")

    # ── Direct target ID path (preferred) ───────────────────────
    if direct_target_id:
        result = cdp_client.activate_target(direct_target_id)
        return jsonify({
            "success": result,
            "targetId": direct_target_id,
        })

    # ── URL pattern fallback ────────────────────────────────────
    url_pattern = data.get("urlPattern", "/")
    exclude_url = data.get("excludeUrl")

    targets = cdp_client.get_targets()
    if not targets:
        return jsonify({
            "success": False,
            "reason": "cdp_unavailable",
        }), 503

    match = cdp_client.find_target_by_url(
        targets, url_pattern, exclude_url=exclude_url,
    )
    if not match:
        return jsonify({
            "success": False,
            "reason": "not_found",
            "targets": len(targets),
        })

    result = cdp_client.activate_target(match["id"])
    return jsonify({
        "success": result,
        "url": match.get("url"),
        "targetId": match.get("id"),
    })


@tab_mesh_bp.route("/tab-mesh/discover-target", methods=["POST"])
def discover_target():
    """Discover a tab's Chrome target ID by matching its mesh tab ID.

    The requesting tab must set ``window.__meshTabId`` before calling.
    The backend evaluates that expression on candidate CDP targets
    to find the exact match.

    Request body::

        { "meshTabId": "abc-123", "url": "http://localhost:8000/" }

    Returns::

        { "chromeTargetId": "CHROME-TARGET-ID" }
        { "chromeTargetId": null, "reason": "..." }
    """
    from src.ui.web import cdp_client

    data = request.get_json(silent=True) or {}
    mesh_tab_id = data.get("meshTabId")
    tab_url = data.get("url", "")

    if not mesh_tab_id:
        return jsonify({"chromeTargetId": None, "reason": "missing meshTabId"}), 400

    targets = cdp_client.get_targets()
    if not targets:
        return jsonify({"chromeTargetId": None, "reason": "cdp_unavailable"})

    # Narrow candidates by URL prefix (same origin) to minimise JS evals
    # Extract origin from the tab's URL for filtering
    from urllib.parse import urlparse
    parsed = urlparse(tab_url)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme else ""

    candidates = []
    for t in targets:
        if t.get("type") != "page":
            continue
        t_url = t.get("url", "")
        if t_url.startswith("devtools://") or t_url.startswith("chrome-devtools://"):
            continue
        # Only check tabs from the same origin
        if origin and not t_url.startswith(origin):
            continue
        # Must have a WebSocket URL for JS evaluation
        if not t.get("webSocketDebuggerUrl"):
            continue
        candidates.append(t)

    if not candidates:
        return jsonify({"chromeTargetId": None, "reason": "no_candidates"})

    # Evaluate window.__meshTabId on each candidate
    for candidate in candidates:
        ws_url = candidate["webSocketDebuggerUrl"]
        result = cdp_client.evaluate_js(ws_url, "window.__meshTabId || null")
        if result is None:
            continue
        # CDP returns: {"id":1, "result": {"result": {"type":"string","value":"abc-123"}}}
        try:
            value = result["result"]["result"]["value"]
        except (KeyError, TypeError):
            continue
        if value == mesh_tab_id:
            return jsonify({"chromeTargetId": candidate["id"]})

    return jsonify({"chromeTargetId": None, "reason": "not_found"})


@tab_mesh_bp.route("/tab-mesh/cdp-diagnose")
def cdp_diagnose():
    """Diagnose Chrome/WSL setup for CDP remediation.

    Detects: Windows user, Chrome version, profiles, shortcuts,
    current shortcut args, and whether CDP is already active.

    Returns a comprehensive diagnostic dict for the setup wizard.
    """
    from src.ui.web import cdp_client

    result: dict = {
        "wsl": _is_wsl(),
        "windows_user": None,
        "chrome_exe_found": False,
        "chrome_version": None,
        "requires_user_data_dir": True,
        "chrome_data_dir": None,
        "profiles": [],
        "shortcuts": {},
        "cdp_active": False,
        "powershell_available": shutil.which("powershell.exe") is not None,
    }

    if not result["wsl"]:
        return jsonify(result)

    # Windows user
    windows_user = _get_windows_user()
    result["windows_user"] = windows_user
    if not windows_user:
        return jsonify(result)

    # Chrome exe
    chrome_exe = "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
    result["chrome_exe_found"] = os.path.exists(chrome_exe)

    # Chrome version
    version = _get_chrome_version()
    result["chrome_version"] = version
    if version:
        major = cdp_client.parse_chrome_major_version(version)
        result["requires_user_data_dir"] = (major or 999) >= 136

    # Chrome data dir + profiles (from the DEFAULT location)
    data_dir = _chrome_data_dir(windows_user)
    debug_dir_win = _chrome_debug_data_dir_win(windows_user)
    result["chrome_data_dir"] = debug_dir_win  # This is what we'll SET

    if os.path.isdir(data_dir):
        result["profiles"] = _read_chrome_profiles(data_dir)

    # Shortcuts — check if they have the CORRECT flags
    # CRITICAL: has_debug_port is only "truly configured" if the
    # user-data-dir points to our separate debug directory, NOT
    # the default User Data path (Chrome 136+ silently ignores that).
    default_data_dir_win = _chrome_data_dir_win(windows_user)
    shortcut_paths = _shortcut_locations(windows_user)
    backup_paths = _backup_shortcut_locations(windows_user)

    for key, wsl_path in shortcut_paths.items():
        found = os.path.exists(wsl_path)
        shortcut_info: dict = {"found": found}
        if found:
            details = _read_shortcut(wsl_path)
            if details:
                shortcut_info["target"] = details["target"]
                shortcut_info["args"] = details["args"]
                shortcut_info["icon"] = details.get("icon", "")
                has_port = "--remote-debugging-port=" in details["args"]
                has_data_dir = "--user-data-dir=" in details["args"]
                # Check if it's using the DEFAULT dir (won't work)
                uses_default = (
                    has_data_dir
                    and default_data_dir_win.lower() in details["args"].lower()
                )
                shortcut_info["has_debug_port"] = (
                    has_port and has_data_dir and not uses_default
                )
                shortcut_info["has_user_data_dir"] = has_data_dir
                shortcut_info["uses_default_dir"] = uses_default
                # Check if the icon matches the expected debug icon
                shortcut_info["has_debug_icon"] = (
                    CHROME_ICON_DEBUG.lower()
                    in details.get("icon", "").lower()
                )

        # Scan the backup shortcut ("Chrome - OLD") at this location
        backup_wsl = backup_paths.get(key, "")
        backup_found = os.path.exists(backup_wsl) if backup_wsl else False
        backup_info: dict = {"found": backup_found}
        if backup_found:
            backup_details = _read_shortcut(backup_wsl)
            if backup_details:
                backup_info["target"] = backup_details["target"]
                backup_info["args"] = backup_details["args"]
                backup_info["icon"] = backup_details.get("icon", "")
                backup_info["has_debug_args"] = (
                    "--remote-debugging-port=" in backup_details["args"]
                )
        shortcut_info["backup"] = backup_info

        # Compute per-location status
        debug_ok = shortcut_info.get("has_debug_port", False)
        icon_ok = shortcut_info.get("has_debug_icon", False)
        if debug_ok and icon_ok and backup_found:
            shortcut_info["status"] = "ok"
        elif debug_ok and icon_ok and not backup_found:
            shortcut_info["status"] = "needs_backup"
        elif debug_ok and not icon_ok:
            shortcut_info["status"] = "needs_icon_fix"
        else:
            shortcut_info["status"] = "needs_setup"

        result["shortcuts"][key] = shortcut_info

    # CDP active?
    cdp_client.try_discover_endpoint()
    result["cdp_active"] = cdp_client.is_available()

    return jsonify(result)


@tab_mesh_bp.route("/tab-mesh/cdp-remediate", methods=["POST"])
def cdp_remediate():
    """Apply Chrome debugging flags to selected shortcuts.

    For each shortcut:
    1. If ``keep_backup`` is true (default), clones the original to
       ``Chrome - OLD.lnk`` with clean args and normal icon (chrome.exe,4)
       — unless a backup already exists.
    2. Modifies the main shortcut: adds debug args + sets dev icon
       (chrome.exe,8).

    Request body::

        {
            "shortcuts": ["taskbar", "desktop", "start_menu_global"],
            "profile_dir": "Default",
            "port": 9222,
            "keep_backup": true
        }

    Returns::

        {
            "results": {
                "taskbar": {
                    "shortcut_ok": true,
                    "backup_ok": true,
                    "backup_skipped": false
                },
                ...
            },
            "requires_restart": true
        }
    """
    from src.ui.web import cdp_client

    data = request.get_json(silent=True) or {}
    shortcut_keys = data.get("shortcuts", [])
    profile_dir = data.get("profile_dir", "Default")
    port = data.get("port", 9222)
    keep_backup = data.get("keep_backup", True)

    if not _is_wsl():
        return jsonify({"error": "Not running under WSL"}), 400

    windows_user = _get_windows_user()
    if not windows_user:
        return jsonify({"error": "Could not detect Windows user"}), 500

    # Determine user-data-dir value
    # CRITICAL: Chrome 136+ silently ignores --remote-debugging-port
    # when --user-data-dir points to the DEFAULT User Data directory.
    # We must use a SEPARATE directory for debugging to work.
    chrome_version = _get_chrome_version()
    needs_data_dir = True  # Default to safe assumption
    if chrome_version:
        major = cdp_client.parse_chrome_major_version(chrome_version)
        needs_data_dir = (major or 999) >= 136

    user_data_dir: str | None = None
    if needs_data_dir:
        user_data_dir = _chrome_debug_data_dir_win(windows_user)

    all_shortcuts = _shortcut_locations(windows_user)
    all_backups = _backup_shortcut_locations(windows_user)
    results: dict = {}

    for key in shortcut_keys:
        wsl_path = all_shortcuts.get(key)
        if not wsl_path:
            results[key] = {
                "shortcut_ok": False,
                "reason": "unknown_shortcut",
            }
            continue
        if not os.path.exists(wsl_path):
            results[key] = {
                "shortcut_ok": False,
                "reason": "not_found",
            }
            continue

        entry: dict = {}

        # Step 1: Create backup if requested and not already existing
        backup_wsl = all_backups.get(key, "")
        if keep_backup and backup_wsl:
            if os.path.exists(backup_wsl):
                entry["backup_ok"] = True
                entry["backup_skipped"] = True  # Already existed
            else:
                backup_ok = _clone_shortcut(
                    wsl_path, backup_wsl,
                    clear_args=True,
                    icon_location=CHROME_ICON_NORMAL,
                )
                entry["backup_ok"] = backup_ok
                entry["backup_skipped"] = False
        else:
            entry["backup_ok"] = None  # Not requested
            entry["backup_skipped"] = True

        # Step 2: Modify the main shortcut — add debug args + dev icon
        ok = _modify_shortcut(
            wsl_path, port, user_data_dir,
            icon_location=CHROME_ICON_DEBUG,
        )
        entry["shortcut_ok"] = ok

        results[key] = entry

    return jsonify({
        "results": results,
        "requires_restart": True,
        "message": (
            "Close Chrome completely (check system tray) "
            "and reopen from any of your shortcuts."
        ),
    })


@tab_mesh_bp.route("/tab-mesh/trigger-chrome-signin", methods=["POST"])
def trigger_chrome_signin():
    """Trigger Chrome sync sign-in and pre-fill email via CDP.

    1. Opens chrome://settings/syncSetup to initiate Chrome's sign-in flow
    2. Polls for the Google sign-in tab to appear
    3. Uses CDP WebSocket to fill the email input field

    Request JSON::

        { "email": "user@example.com" }

    Returns::

        { "success": true/false, "message": "...", "step": "..." }
    """
    from src.ui.web import cdp_client
    import time

    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    if not email:
        return jsonify({"success": False, "message": "No email provided"}), 400

    if not cdp_client.is_available():
        return jsonify({
            "success": False,
            "message": "CDP not available — Chrome may not be running with debugging",
        }), 503

    # Open Google sign-in for Chrome sync directly — no chrome://settings
    tab = cdp_client.create_tab(
        "https://accounts.google.com/AccountChooser?service=chromiumsync"
    )
    if not tab:
        return jsonify({
            "success": False,
            "message": "Failed to open sign-in tab",
            "step": "create_tab",
        }), 500

    ws_url = tab.get("webSocketDebuggerUrl", "")
    if not ws_url:
        return jsonify({
            "success": False,
            "message": "Sign-in tab has no WebSocket URL",
            "step": "no_ws_url",
        }), 500

    # Fill using stable selector — getElementById('identifierId')
    # Poll aggressively until the input appears (page may still be loading)
    fill_js = (
        "var el = document.getElementById('identifierId'); "
        "if (el) { "
        "  el.value = '" + email.replace("'", "\\'") + "'; "
        "  el.dispatchEvent(new Event('input', {bubbles: true})); "
        "  'filled' "
        "} else { 'no_input_found' }"
    )

    for attempt in range(6):
        time.sleep(0.5)
        result = cdp_client.evaluate_js(ws_url, fill_js, timeout=5.0)
        if result:
            value = (result.get("result", {})
                     .get("result", {})
                     .get("value", ""))
            if value == "filled":
                return jsonify({
                    "success": True,
                    "message": f"Email filled: {email}. Enter your password to sign in.",
                    "step": "email_filled",
                })

    return jsonify({
        "success": False,
        "message": "Email input not found after polling — page may not have loaded",
        "step": "input_not_found",
    }), 500


@tab_mesh_bp.route("/tab-mesh/suggest-cdp", methods=["POST"])
def suggest_cdp():
    """Create a one-time notification suggesting CDP setup.

    Called by the frontend when cross-tab navigation falls back
    because CDP is unavailable.  Uses notification dedup so
    only one active suggestion exists at a time.

    Returns::

        { "created": true/false }
    """
    from flask import current_app
    from src.core.services.notifications import create_notification

    project_root = Path(current_app.config["PROJECT_ROOT"])

    result = create_notification(
        project_root,
        notif_type="cdp_suggestion",
        title="Enable Tab Focus",
        message=(
            "Cross-tab navigation is working, but tabs can't be "
            "brought to the front without Chrome DevTools Protocol. "
            "Open the Tab Mesh panel → Setup to enable CDP."
        ),
        meta={"action_tab": "debugging", "action_hash": "#debugging"},
        dedup=True,
    )

    return jsonify({"created": result is not None})

