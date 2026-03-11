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

    Environment-aware: delegates to ChromeLauncher.kill_all() which
    uses taskkill.exe on WSL or pkill on native Linux.

    Returns::

        { "killed": true/false, "message": "..." }
    """
    from src.core.services.chrome.launcher import get_launcher
    try:
        killed = get_launcher().kill_all()
        return jsonify({
            "killed": killed,
            "message": (
                "All Chrome processes terminated."
                if killed
                else "Chrome was not running."
            ),
        })
    except Exception as exc:
        return jsonify({"killed": False, "message": str(exc)}), 500


@tab_mesh_bp.route("/tab-mesh/chrome-status")
def chrome_status():
    """Check Chrome availability and create a notification if missing.

    Returns the output of ``require_chrome()``. If Chrome is not
    available, also creates a deduplicated ``chrome_missing``
    notification with installation guidance.

    Returns::

        {
            "available": true/false,
            "binary": "...",
            "version": "...",
            "environment": "wsl" | "linux",
            "install_plan": { ... }  // only when available=False
        }
    """
    from src.core.services.chrome.launcher import require_chrome

    status = require_chrome()

    if not status["available"]:
        # Create a notification with remediation guidance
        from flask import current_app
        from src.core.services.notifications import create_notification

        project_root = Path(current_app.config["PROJECT_ROOT"])
        install_plan = status.get("install_plan", {})
        steps = install_plan.get("steps", [])
        step_text = steps[0].get("command", "") if steps else ""

        create_notification(
            project_root,
            notif_type="chrome_missing",
            title="Chrome Not Installed",
            message=(
                "Chrome is required for CDP-based tab management, "
                "test recording, and browser automation. "
                f"Install it via: {step_text}"
                if step_text
                else "Chrome is required but not installed. "
                "Use the Audit → Tool Install panel to set it up."
            ),
            meta={
                "action_tab": "audit",
                "action_hash": "#audit",
                "install_plan": install_plan,
            },
            dedup=True,
        )

    return jsonify(status)


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


# ── WSL interop notification check ───────────────────────────


def _check_wsl_interop_notifications() -> None:
    """Check WSL interop layers and create notifications for gaps.

    Safe to call repeatedly — all notifications use dedup=True.
    Only runs on WSL systems; returns immediately on native Linux.
    """
    from src.core.services.chrome.detection import is_wsl
    if not is_wsl():
        return

    from flask import current_app
    from src.core.services.notifications import create_notification
    from src.core.services.audit.l0_hw_detectors import _detect_wsl_interop
    from src.core.services.chrome.wsl_tunnel import get_active_tunnel

    try:
        project_root = Path(current_app.config["PROJECT_ROOT"])
    except RuntimeError:
        return  # No app context (e.g. background thread)

    # If a tunnel is already active and running at Level 2+,
    # skip upgrade and firewall notifications — they're resolved.
    tunnel = get_active_tunnel()
    tunnel_active = tunnel is not None and tunnel.is_running if tunnel else False

    interop = _detect_wsl_interop()
    channel_level = interop.get("cdp_channel_level", 0)
    hostname = interop.get("hostname")
    hostname_resolves = interop.get("hostname_local_resolves", False)
    curl_available = interop.get("curl_exe_available", False)

    # ── hostname.local not resolving (Layer 2) ────────────────
    if hostname and not hostname_resolves:
        create_notification(
            project_root,
            notif_type="wsl_hostname_resolution",
            title="hostname.local Not Resolving",
            message=(
                f'"{hostname}.local" could not be resolved via mDNS. '
                "This is the recommended way for WSL2 to reach Windows "
                "services (like Chrome CDP) without workarounds. "
                "mDNS is usually enabled on modern Windows — check "
                "that the Bonjour/mDNS service is running."
            ),
            meta={
                "layer": 2,
                "hostname": hostname,
                "action_tab": "wsl-channel",
                "action_hash": "#wsl-channel",
            },
            dedup=True,
        )

    # ── curl.exe missing (Layer 5 — fallback) ─────────────────
    if not curl_available:
        if channel_level < 2:
            create_notification(
                project_root,
                notif_type="wsl_curl_exe_missing",
                title="CDP Bridge Unavailable",
                message=(
                    "curl.exe is not found on Windows and no direct "
                    "channel (hostname.local) is available. CDP "
                    "communication with Chrome is currently impossible. "
                    "Run the WSL Interop Setup to fix this."
                ),
                meta={
                    "layer": 5,
                    "priority": "imminent",
                    "action_tab": "wsl-channel",
                    "action_hash": "#wsl-channel",
                },
                dedup=True,
            )
        else:
            create_notification(
                project_root,
                notif_type="wsl_curl_exe_missing",
                title="curl.exe Not Found (Optional)",
                message=(
                    "curl.exe is not found on Windows. The direct "
                    "channel via hostname.local is working, so CDP "
                    "functions normally. curl.exe is only needed as a "
                    "fallback. You can install it for redundancy."
                ),
                meta={
                    "layer": 5,
                    "priority": "normal",
                    "action_tab": "wsl-channel",
                    "action_hash": "#wsl-channel",
                },
                dedup=True,
            )

    # ── Firewall rule missing (Layer 3) ───────────────────────
    # When hostname.local resolves but the firewall rule for CDP
    # port access doesn't exist, the direct channel won't work.
    # This is a separate concern from hostname resolution.
    if hostname_resolves and not tunnel_active:
        fw_status = check_wsl_firewall_status()
        firewall_ok = fw_status.get("port_reachable") or fw_status.get("rule_exists")
        if not firewall_ok:
            create_notification(
                project_root,
                notif_type="wsl_firewall_rule",
                title="Windows Firewall Blocking CDP",
                message=(
                    f"{hostname}.local resolves correctly but the "
                    "Windows firewall may be blocking CDP connections "
                    "from WSL2. A firewall rule is needed to allow "
                    "inbound TCP on the vEthernet (WSL) interface. "
                    "Open Tab Mesh → Setup to create the rule."
                ),
                meta={
                    "layer": 3,
                    "hostname": hostname,
                    "hostname_ip": interop.get("hostname_local_ip"),
                    "action_tab": "wsl-channel",
                    "action_hash": "#wsl-channel",
                    "remediation": "Create WSL_CDP_Access firewall rule",
                },
                dedup=True,
            )

    # ── Channel upgrade opportunity (Level 1 → Level 2) ───────
    # When system works at Level 1 (curl.exe bridge, ~100ms/call)
    # but could be at Level 2 (direct channel, ~5ms/call).
    if channel_level == 1 and not tunnel_active:
        upgrade_steps = []
        if hostname and not hostname_resolves:
            upgrade_steps.append(
                "hostname.local mDNS resolution is not working — "
                "check that Bonjour/mDNS is running on Windows"
            )
        if not curl_available:
            upgrade_steps.append(
                "curl.exe is missing — install it as a fallback"
            )

        create_notification(
            project_root,
            notif_type="wsl_channel_upgrade",
            title="CDP Channel: Upgrade Available",
            message=(
                "CDP is working via curl.exe bridge (~2000ms per call). "
                "You can upgrade to the Direct Channel (~5ms per call) "
                "by configuring hostname.local resolution and a "
                "Windows firewall rule. "
                "Open Tab Mesh → Setup to configure."
            ),
            meta={
                "current_level": 1,
                "current_level_name": "curl.exe Bridge",
                "recommended_level": 2,
                "recommended_level_name": "Direct Channel",
                "upgrade_steps": upgrade_steps,
                "action_tab": "wsl-channel",
                "action_hash": "#wsl-channel",
            },
            dedup=True,
        )


def check_wsl_firewall_status(port: int = 9222) -> dict:
    """Comprehensive firewall status check.

    Checks both the named rule AND actual TCP reachability, because
    a user may have opened the port with a different rule name.

    Returns::

        {
            "rule_exists": True/False,
            "rule_enabled": True/False,
            "rule_port": 9222,
            "port_reachable": True/False,
            "hostname_ip": "172.17.128.1" | None,
            "needs_rule": True/False,
        }
    """
    import socket as _socket

    result = {
        "rule_exists": False,
        "rule_enabled": False,
        "rule_port": port,
        "port_reachable": False,
        "hostname_ip": None,
        "needs_rule": True,
    }

    # ── Check named rule ──────────────────────────────────────
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "Get-NetFirewallRule -DisplayName 'WSL_CDP_Access' "
             "-ErrorAction SilentlyContinue "
             "| Select-Object -ExpandProperty Enabled"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            result["rule_exists"] = True
            result["rule_enabled"] = r.stdout.strip().lower() == "true"
    except Exception:
        pass

    # ── Resolve hostname.local for TCP test ────────────────────
    host_ip = None
    try:
        hostname_r = subprocess.run(
            ["hostname"],
            capture_output=True, text=True, timeout=3,
        )
        hostname = hostname_r.stdout.strip()
        if hostname:
            fqdn = f"{hostname}.local"
            try:
                infos = _socket.getaddrinfo(
                    fqdn, None, _socket.AF_INET, _socket.SOCK_STREAM,
                )
                if infos:
                    host_ip = infos[0][4][0]
            except (_socket.gaierror, OSError):
                pass
    except Exception:
        pass

    result["hostname_ip"] = host_ip

    # ── TCP reachability test ─────────────────────────────────
    if host_ip:
        try:
            sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect((host_ip, port))
            sock.close()
            result["port_reachable"] = True
        except (ConnectionRefusedError, OSError):
            pass

    # ── needs_rule: True if port not reachable and no rule ────
    result["needs_rule"] = (
        not result["port_reachable"]
        and not (result["rule_exists"] and result["rule_enabled"])
    )

    return result


def _check_wsl_firewall_rule() -> bool:
    """Legacy wrapper — returns True if firewall is OK."""
    status = check_wsl_firewall_status()
    return status["port_reachable"] or (
        status["rule_exists"] and status["rule_enabled"]
    )


@tab_mesh_bp.route("/tab-mesh/cdp-status")
def cdp_status():
    """Check if Chrome DevTools Protocol is available.

    Also triggers WSL interop gap notifications (deduped) so users
    see remediation guidance on first page load without needing to
    open the CDP setup wizard.

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

    # Fire WSL interop gap notifications (deduped — safe to call repeatedly)
    _check_wsl_interop_notifications()

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

    # ── WSL interop channel details ───────────────────────────
    # Enriched detection: networking mode, hostname.local, curl.exe,
    # operability level. These are independent concerns for the UI.
    from src.core.services.audit.l0_hw_detectors import _detect_wsl_interop
    interop = _detect_wsl_interop()
    result["wsl_interop"] = {
        "networking_mode": interop.get("networking_mode", "unknown"),
        "wslconfig_parsed": interop.get("wslconfig_parsed"),
        "hostname": interop.get("hostname"),
        "hostname_local_resolves": interop.get(
            "hostname_local_resolves", False,
        ),
        "hostname_local_ip": interop.get("hostname_local_ip"),
        "curl_exe_available": interop.get("curl_exe_available", False),
        "curl_exe_path": interop.get("curl_exe_path"),
        "cdp_channel_level": interop.get("cdp_channel_level", 0),
    }
    # Fire WSL interop gap notifications (shared with cdp_status)
    _check_wsl_interop_notifications()

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


# ═══════════════════════════════════════════════════════════════════
#  WSL Interop — Diagnostic & Remediation Endpoints
# ═══════════════════════════════════════════════════════════════════


@tab_mesh_bp.route("/tab-mesh/wsl-test-hostname", methods=["POST"])
def wsl_test_hostname():
    """Test hostname.local mDNS resolution and TCP connectivity.

    Tests:
      1. Resolve $(hostname).local via mDNS → IP address
      2. TCP connect to that IP on the target port (default 9222)
      3. HTTP GET to http://hostname.local:port/json/version

    Returns a detailed per-step result dict.
    """
    import socket
    import urllib.request
    import urllib.error

    port = request.json.get("port", 9222) if request.is_json else 9222

    result: dict = {
        "hostname": None,
        "hostname_local": None,
        "steps": {
            "dns_resolve": {"ok": False, "ip": None, "error": None},
            "tcp_connect": {"ok": False, "error": None},
            "http_get": {"ok": False, "response": None, "error": None},
        },
        "overall": False,
    }

    # Step 1: Get hostname
    try:
        r = subprocess.run(
            ["hostname"],
            capture_output=True, text=True, timeout=3,
        )
        hostname = r.stdout.strip()
        if not hostname:
            result["steps"]["dns_resolve"]["error"] = "hostname command returned empty"
            return jsonify(result)
        result["hostname"] = hostname
        result["hostname_local"] = f"{hostname}.local"
    except Exception as exc:
        result["steps"]["dns_resolve"]["error"] = str(exc)[:100]
        return jsonify(result)

    # Step 2: DNS resolution
    fqdn = f"{hostname}.local"
    try:
        infos = socket.getaddrinfo(
            fqdn, None, socket.AF_INET, socket.SOCK_STREAM,
        )
        if infos:
            resolved_ip = infos[0][4][0]
            result["steps"]["dns_resolve"]["ok"] = True
            result["steps"]["dns_resolve"]["ip"] = resolved_ip
        else:
            result["steps"]["dns_resolve"]["error"] = "no results from getaddrinfo"
            return jsonify(result)
    except (socket.gaierror, OSError) as exc:
        result["steps"]["dns_resolve"]["error"] = str(exc)[:100]
        return jsonify(result)

    # Step 3: TCP connect
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            err = s.connect_ex((resolved_ip, int(port)))
            if err == 0:
                result["steps"]["tcp_connect"]["ok"] = True
            else:
                result["steps"]["tcp_connect"]["error"] = (
                    f"connect_ex returned {err} — port {port} may be "
                    "blocked by Windows firewall or Chrome is not running"
                )
                return jsonify(result)
    except (socket.timeout, OSError) as exc:
        result["steps"]["tcp_connect"]["error"] = str(exc)[:100]
        return jsonify(result)

    # Step 4: HTTP GET to CDP version endpoint
    url = f"http://{fqdn}:{port}/json/version"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            result["steps"]["http_get"]["ok"] = True
            result["steps"]["http_get"]["response"] = body[:500]
    except urllib.error.URLError as exc:
        result["steps"]["http_get"]["error"] = str(exc.reason)[:100]
    except Exception as exc:
        result["steps"]["http_get"]["error"] = str(exc)[:100]

    # Overall: all 3 steps must pass
    steps = result["steps"]
    result["overall"] = all(
        steps[k]["ok"] for k in ("dns_resolve", "tcp_connect", "http_get")
    )

    return jsonify(result)


@tab_mesh_bp.route("/tab-mesh/wsl-validate", methods=["POST"])
def wsl_validate():
    """End-to-end validation of all WSL interop layers.

    Runs detection for each independent layer and reports status.
    This is a comprehensive check — slower than cdp_diagnose but
    tests actual connectivity, not just detection.

    Returns per-layer status with actionable info.
    """
    from src.core.services.audit.l0_hw_detectors import _detect_wsl_interop
    from src.ui.web import cdp_client

    interop = _detect_wsl_interop()

    layers: dict = {
        "layer_0_wsl": {
            "name": "WSL Environment",
            "ok": interop.get("available", False),
            "detail": {
                "powershell": interop.get("available", False),
                "binfmt": interop.get("binfmt_registered", False),
                "windows_user": interop.get("windows_user"),
            },
        },
        "layer_1_networking": {
            "name": "Networking Mode",
            "mode": interop.get("networking_mode", "unknown"),
            "ok": True,  # Informational — NAT is fine
            "detail": {
                "wslconfig_parsed": interop.get("wslconfig_parsed"),
                "note": (
                    "mirrored mode active — localhost works natively"
                    if interop.get("networking_mode") == "mirrored"
                    else "NAT mode (default) — hostname.local or curl.exe needed"
                ),
            },
        },
        "layer_2_hostname": {
            "name": "hostname.local Resolution",
            "ok": interop.get("hostname_local_resolves", False),
            "recommended": True,
            "detail": {
                "hostname": interop.get("hostname"),
                "resolves": interop.get("hostname_local_resolves", False),
                "ip": interop.get("hostname_local_ip"),
            },
        },
        "layer_5_curl_exe": {
            "name": "curl.exe Bridge (Fallback)",
            "ok": interop.get("curl_exe_available", False),
            "detail": {
                "path": interop.get("curl_exe_path"),
            },
        },
    }

    # ── Layer 3: Firewall ──────────────────────────────────────
    fw = check_wsl_firewall_status()
    firewall_ok = fw.get("port_reachable") or (
        fw.get("rule_exists") and fw.get("rule_enabled")
    )
    layers["layer_3_firewall"] = {
        "name": "Windows Firewall",
        "ok": firewall_ok,
        "detail": {
            "rule_name": "WSL_CDP_Access",
            "rule_exists": fw.get("rule_exists", False),
            "rule_enabled": fw.get("rule_enabled", False),
            "port_reachable": fw.get("port_reachable", False),
        },
    }

    # ── Tunnel state ───────────────────────────────────────────
    from src.core.services.chrome.wsl_tunnel import get_active_tunnel

    tunnel = get_active_tunnel()
    tunnel_running = (
        tunnel is not None and tunnel.is_running if tunnel else False
    )
    layers["tunnel"] = {
        "name": "Network Tunnel",
        "ok": tunnel_running,
        "detail": {
            "method": (
                tunnel.stats.get("method") if tunnel_running else None
            ),
            "stats": tunnel.stats if tunnel_running else None,
        },
    }

    # CDP end-to-end test
    cdp_client.try_discover_endpoint()
    cdp_ok = cdp_client.is_available()

    # ── Latency measurement ────────────────────────────────────
    import time as _time
    import urllib.request
    import urllib.error

    latency: dict = {}

    # curl.exe bridge latency
    if interop.get("curl_exe_available"):
        try:
            start = _time.monotonic()
            r = subprocess.run(
                [interop["curl_exe_path"], "-s", "--max-time", "5",
                 "http://localhost:9222/json/version"],
                capture_output=True, text=True, timeout=6,
            )
            elapsed = (_time.monotonic() - start) * 1000
            latency["curl_exe_ms"] = round(elapsed, 1)
            latency["curl_exe_ok"] = r.returncode == 0 and bool(r.stdout)
        except Exception:
            latency["curl_exe_ms"] = None
            latency["curl_exe_ok"] = False

    # Tunnel latency (uses tunnel.validate() which measures internally)
    if tunnel_running:
        try:
            tv = tunnel.validate()
            latency["tunnel_ms"] = tv.get("latency_ms")
            latency["tunnel_ok"] = tv.get("ok", False)
        except Exception:
            latency["tunnel_ms"] = None
            latency["tunnel_ok"] = False

    # Direct (hostname.local) latency
    host_ip = interop.get("hostname_local_ip")
    if host_ip:
        try:
            start = _time.monotonic()
            req = urllib.request.Request(
                f"http://{host_ip}:9222/json/version",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                resp.read()
            latency["direct_ms"] = round(
                (_time.monotonic() - start) * 1000, 1,
            )
            latency["direct_ok"] = True
        except Exception:
            latency["direct_ms"] = None
            latency["direct_ok"] = False

    # ── Actual level ───────────────────────────────────────────
    actual_level = _compute_actual_level(interop, tunnel_running, cdp_ok)

    result = {
        "layers": layers,
        "latency": latency,
        "actual_level": actual_level,
        "cdp_channel_level": interop.get("cdp_channel_level", 0),
        "cdp_active": cdp_ok,
        "cdp_endpoint": cdp_client._base_url() if cdp_ok else None,
        "summary": _build_validation_summary(
            interop, cdp_ok,
        ),
    }

    return jsonify(result)


def _compute_actual_level(
    interop: dict,
    tunnel_active: bool,
    cdp_ok: bool,
) -> dict:
    """Compute the actual operability level based on live state.

    Unlike ``_detect_wsl_interop()`` which uses detection heuristics,
    this checks what is ACTUALLY working right now.

    Returns::

        {
            "level": 2,
            "level_name": "Direct Channel",
            "method": "python_proxy",
        }
    """
    if interop.get("networking_mode") == "mirrored" and cdp_ok:
        return {
            "level": 3,
            "level_name": "Native localhost",
            "method": "mirrored",
        }

    if tunnel_active and cdp_ok:
        return {
            "level": 2,
            "level_name": "Direct Channel",
            "method": "tunnel",
        }

    if interop.get("curl_exe_available") and cdp_ok:
        return {
            "level": 1,
            "level_name": "curl.exe Bridge",
            "method": "curl_exe",
        }

    return {
        "level": 0,
        "level_name": "No CDP",
        "method": None,
    }


def _build_validation_summary(
    interop: dict,
    cdp_ok: bool,
) -> dict:
    """Build a human-readable validation summary."""
    level = interop.get("cdp_channel_level", 0)
    level_names = {
        0: "No CDP channel",
        1: "curl.exe bridge (fallback)",
        2: "Direct channel via hostname.local (recommended)",
        3: "Mirrored networking (native localhost)",
    }

    issues: list[str] = []
    if not interop.get("hostname_local_resolves"):
        issues.append("hostname.local does not resolve — recommended fix")
    if not interop.get("curl_exe_available"):
        issues.append("curl.exe not found on Windows — fallback unavailable")
    if not cdp_ok:
        issues.append("CDP endpoint not reachable — is Chrome running with debug flags?")

    return {
        "level": level,
        "level_name": level_names.get(level, "Unknown"),
        "cdp_working": cdp_ok,
        "issues": issues,
        "issue_count": len(issues),
    }


@tab_mesh_bp.route("/tab-mesh/wsl-firewall-status")
def wsl_firewall_status():
    """Check firewall rule status and TCP reachability.

    Returns comprehensive firewall status including named rule check
    and actual TCP port reachability test.
    """
    port = request.args.get("port", 9222, type=int)
    status = check_wsl_firewall_status(port)
    return jsonify(status)


@tab_mesh_bp.route("/tab-mesh/wsl-fix-firewall", methods=["POST"])
def wsl_fix_firewall():
    """Create a Windows firewall rule to allow WSL→Windows CDP traffic.

    Creates an inbound TCP rule on the vEthernet (WSL) interface.
    Supports both single-port and port-range rules.  Requires UAC
    elevation — the user will see a UAC prompt.

    Request JSON::

        {
            "port": 9222,
            "scope": "single" | "range"
        }

    ``scope="single"`` creates a rule for the exact port.
    ``scope="range"`` creates a rule for ports 9222-9232 (multi-instance).
    """
    port = 9222
    scope = "single"
    if request.is_json:
        port = request.json.get("port", 9222)
        scope = request.json.get("scope", "single")

    rule_name = "WSL_CDP_Access"

    # ── Step 1: Check if rule already exists ───────────────────
    check_cmd = (
        f"Get-NetFirewallRule -DisplayName '{rule_name}' "
        "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty Enabled"
    )
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", check_cmd],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip().lower() == "true":
            # Validate TCP even though rule exists
            fw = check_wsl_firewall_status(port)
            return jsonify({
                "ok": True,
                "action": "already_exists",
                "message": f"Firewall rule '{rule_name}' already exists and is enabled.",
                "validated": fw.get("port_reachable", False),
            })
    except Exception:
        pass  # If check fails, try to create anyway

    # ── Step 2: Build port spec based on scope ─────────────────
    if scope == "range":
        port_spec = "9222-9232"
        description = "Allow WSL2 CDP access on ports 9222-9232"
    else:
        port_spec = str(port)
        description = f"Allow WSL2 to access Chrome CDP on port {port}"

    # ── Step 3: Create the rule via elevated PowerShell ────────
    script_content = (
        f"New-NetFirewallRule "
        f"-DisplayName '{rule_name}' "
        f"-Direction Inbound "
        f"-InterfaceAlias 'vEthernet (WSL)' "
        f"-Action Allow "
        f"-Protocol TCP "
        f"-LocalPort {port_spec} "
        f"-Description '{description}'\n"
    )

    try:
        script_path_wsl = "/mnt/c/Windows/Temp/wsl_cdp_firewall.ps1"
        script_path_win = "C:\\Windows\\Temp\\wsl_cdp_firewall.ps1"

        with open(script_path_wsl, "w", encoding="utf-8") as f:
            f.write(script_content)

        elevated_cmd = (
            "Start-Process powershell -Verb RunAs -Wait "
            "-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass',"
            f"'-File','{script_path_win}'"
        )
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", elevated_cmd],
            capture_output=True, text=True, timeout=30,
        )

        # Clean up
        try:
            os.remove(script_path_wsl)
        except OSError:
            pass

        if r.returncode == 0:
            # ── Step 4: Post-creation validation ───────────────
            import time
            time.sleep(0.5)  # brief pause for rule to take effect
            fw = check_wsl_firewall_status(port)
            validated = fw.get("port_reachable", False)

            return jsonify({
                "ok": True,
                "action": "created",
                "scope": scope,
                "port_spec": port_spec,
                "validated": validated,
                "message": (
                    f"Firewall rule '{rule_name}' created ({port_spec}). "
                    + ("TCP connection verified ✓" if validated
                       else "Rule created but TCP test failed — "
                            "Chrome may not be running or bound to this interface.")
                ),
            })
        else:
            return jsonify({
                "ok": False,
                "action": "failed",
                "message": (
                    f"Failed to create firewall rule (exit code {r.returncode}). "
                    "The UAC prompt may have been cancelled."
                ),
                "stderr": r.stderr.strip()[:500],
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({
            "ok": False,
            "action": "timeout",
            "message": "Timed out waiting for UAC or PowerShell.",
        }), 504
    except Exception as exc:
        return jsonify({
            "ok": False,
            "action": "error",
            "message": str(exc)[:200],
        }), 500


@tab_mesh_bp.route("/tab-mesh/wsl-remove-firewall", methods=["POST"])
def wsl_remove_firewall():
    """Remove the WSL_CDP_Access firewall rule.

    Uses elevated PowerShell (UAC prompt) to remove the rule.
    """
    rule_name = "WSL_CDP_Access"

    # Check if rule exists first
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             f"Get-NetFirewallRule -DisplayName '{rule_name}' "
             "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty Enabled"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return jsonify({
                "ok": True,
                "action": "not_found",
                "message": f"Firewall rule '{rule_name}' does not exist.",
            })
    except Exception:
        pass

    # Remove via elevated PowerShell
    script_content = (
        f"Remove-NetFirewallRule -DisplayName '{rule_name}' "
        "-ErrorAction SilentlyContinue\n"
    )

    try:
        script_path_wsl = "/mnt/c/Windows/Temp/wsl_cdp_firewall_del.ps1"
        script_path_win = "C:\\Windows\\Temp\\wsl_cdp_firewall_del.ps1"

        with open(script_path_wsl, "w", encoding="utf-8") as f:
            f.write(script_content)

        elevated_cmd = (
            "Start-Process powershell -Verb RunAs -Wait "
            "-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass',"
            f"'-File','{script_path_win}'"
        )
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", elevated_cmd],
            capture_output=True, text=True, timeout=30,
        )

        try:
            os.remove(script_path_wsl)
        except OSError:
            pass

        if r.returncode == 0:
            return jsonify({
                "ok": True,
                "action": "removed",
                "message": f"Firewall rule '{rule_name}' removed.",
            })
        else:
            return jsonify({
                "ok": False,
                "action": "failed",
                "message": (
                    f"Failed to remove firewall rule (exit code {r.returncode}). "
                    "The UAC prompt may have been cancelled."
                ),
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({
            "ok": False,
            "action": "timeout",
            "message": "Timed out waiting for UAC or PowerShell.",
        }), 504
    except Exception as exc:
        return jsonify({
            "ok": False,
            "action": "error",
            "message": str(exc)[:200],
        }), 500


def check_tunnel_prerequisites(
    target_host: str | None = None,
    port: int = 9222,
) -> dict:
    """Check all prerequisites before starting a tunnel.

    Called by Phase 4 UI to determine what needs fixing before
    a tunnel can be started.

    Args:
        target_host: Windows host IP.  If None, resolves hostname.local.
        port: CDP port to check.

    Returns::

        {
            "hostname_resolves": True/False,
            "hostname_ip": "172.17.128.1" | None,
            "firewall_ok": True/False,
            "port_available": True/False,
            "chrome_reachable": True/False,
            "all_ok": True/False,
            "missing": ["firewall", "hostname", ...]
        }
    """
    import socket as _socket

    result = {
        "hostname_resolves": False,
        "hostname_ip": target_host,
        "firewall_ok": False,
        "port_available": False,
        "chrome_reachable": False,
        "all_ok": False,
        "missing": [],
    }

    # ── Check hostname resolution ──────────────────────────────
    if target_host is None:
        try:
            hostname_r = subprocess.run(
                ["hostname"],
                capture_output=True, text=True, timeout=3,
            )
            hostname = hostname_r.stdout.strip()
            if hostname:
                fqdn = f"{hostname}.local"
                try:
                    infos = _socket.getaddrinfo(
                        fqdn, None, _socket.AF_INET, _socket.SOCK_STREAM,
                    )
                    if infos:
                        target_host = infos[0][4][0]
                        result["hostname_resolves"] = True
                        result["hostname_ip"] = target_host
                except (_socket.gaierror, OSError):
                    pass
        except Exception:
            pass
    else:
        result["hostname_resolves"] = True

    if not result["hostname_resolves"]:
        result["missing"].append("hostname")

    # ── Check local port availability ──────────────────────────
    try:
        test_sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        test_sock.settimeout(0.5)
        test_sock.bind(("127.0.0.1", port))
        test_sock.close()
        result["port_available"] = True
    except OSError:
        # Port in use — might be our own tunnel (which is fine)
        from src.core.services.chrome.wsl_tunnel import get_active_tunnel
        tunnel = get_active_tunnel()
        if tunnel and tunnel.is_running and tunnel.local_port == port:
            result["port_available"] = True  # our tunnel has it
        else:
            result["missing"].append("port_in_use")

    # ── Check firewall ─────────────────────────────────────────
    if target_host:
        fw = check_wsl_firewall_status(port)
        result["firewall_ok"] = (
            fw.get("port_reachable", False)
            or (fw.get("rule_exists", False) and fw.get("rule_enabled", False))
        )
        if not result["firewall_ok"]:
            result["missing"].append("firewall")

        # ── Check Chrome reachability (TCP test) ───────────────
        result["chrome_reachable"] = fw.get("port_reachable", False)
    else:
        result["missing"].append("firewall")

    # ── Summary ────────────────────────────────────────────────
    result["all_ok"] = len(result["missing"]) == 0

    return result


@tab_mesh_bp.route("/tab-mesh/wsl-channel-status")
def wsl_channel_status():
    """Full WSL channel diagnostic for the setup UI.

    Combines detection, firewall, tunnel state, and available
    choices into a single response that the frontend can render.
    """
    import socket as _socket

    from src.core.services.chrome.detection import is_wsl
    from src.core.services.audit.l0_hw_detectors import _detect_wsl_interop
    from src.core.services.chrome.wsl_tunnel import (
        TUNNEL_METHODS, get_active_tunnel,
    )

    if not is_wsl():
        return jsonify({"is_wsl": False})

    interop = _detect_wsl_interop()
    channel_level = interop.get("cdp_channel_level", 0)
    hostname = interop.get("hostname")
    hostname_resolves = interop.get("hostname_local_resolves", False)
    hostname_ip = interop.get("hostname_local_ip")

    # Firewall status
    fw = check_wsl_firewall_status()

    # Tunnel state
    tunnel = get_active_tunnel()
    tunnel_active = tunnel is not None and tunnel.is_running if tunnel else False
    tunnel_method = None
    tunnel_stats = None
    if tunnel_active:
        tunnel_stats = tunnel.stats
        tunnel_method = tunnel_stats.get("method")

    # socat availability
    socat_available = shutil.which("socat") is not None

    # SSH availability (check if OpenSSH on Windows responds)
    ssh_available = shutil.which("ssh") is not None

    # Build choices with prerequisites
    choices = []
    for method_id, info in TUNNEL_METHODS.items():
        choice = {
            "id": method_id,
            "label": info["label"],
            "description": info["description"],
            "speed": info.get("speed", ""),
            "recommended": info.get("recommended", False),
            "risky": info.get("risky", False),
            "risk_detail": info.get("risk_detail", ""),
            "prerequisites": [],
            "available": True,
        }

        # Build prerequisite list per method
        if method_id == "python_proxy":
            choice["prerequisites"].append({
                "name": "hostname",
                "ok": hostname_resolves,
                "detail": hostname_ip or "not resolved",
            })
            # The Python proxy auto-configures netsh portproxy + firewall
            # on start, so this is always "ok" — it's handled automatically.
            fw_ok = fw.get("port_reachable") or (
                fw.get("rule_exists") and fw.get("rule_enabled")
            )
            choice["prerequisites"].append({
                "name": "firewall",
                "ok": True,  # auto-configured on start
                "detail": (
                    "port reachable" if fw.get("port_reachable")
                    else "rule exists" if fw.get("rule_exists")
                    else "auto-configured on start"
                ),
            })
        elif method_id == "socat":
            choice["prerequisites"].append({
                "name": "socat",
                "ok": socat_available,
                "detail": "installed" if socat_available else "not installed (apt install socat)",
            })
            choice["prerequisites"].append({
                "name": "hostname",
                "ok": hostname_resolves,
                "detail": hostname_ip or "not resolved",
            })
            choice["prerequisites"].append({
                "name": "firewall",
                "ok": fw.get("port_reachable") or (
                    fw.get("rule_exists") and fw.get("rule_enabled")
                ),
                "detail": "ok" if fw.get("port_reachable") else "needed",
            })
        elif method_id == "netsh":
            choice["prerequisites"].append({
                "name": "admin",
                "ok": True,
                "detail": "UAC required",
            })
            choice["prerequisites"].append({
                "name": "firewall",
                "ok": fw.get("port_reachable") or (
                    fw.get("rule_exists") and fw.get("rule_enabled")
                ),
                "detail": "ok" if fw.get("port_reachable") else "needed",
            })
        elif method_id == "ssh":
            choice["prerequisites"].append({
                "name": "ssh",
                "ok": ssh_available,
                "detail": "found" if ssh_available else "not found",
            })
            choice["prerequisites"].append({
                "name": "hostname",
                "ok": hostname_resolves,
                "detail": hostname_ip or "not resolved",
            })
        elif method_id == "mirrored":
            # No prerequisites — but risky
            pass

        # available = all prerequisites OK
        choice["available"] = all(
            p["ok"] for p in choice["prerequisites"]
        )
        choices.append(choice)

    return jsonify({
        # Current state
        "is_wsl": True,
        "networking_mode": interop.get("networking_mode", "nat"),
        "channel_level": channel_level,
        "channel_level_name": interop.get("cdp_channel_label", "Unknown"),

        # Layer 2: Hostname
        "hostname": hostname,
        "hostname_local_resolves": hostname_resolves,
        "hostname_local_ip": hostname_ip,

        # Layer 3: Firewall
        "firewall_rule_exists": fw.get("rule_exists", False),
        "firewall_rule_enabled": fw.get("rule_enabled", False),
        "firewall_port_reachable": fw.get("port_reachable", False),

        # Layer 5: curl.exe
        "curl_exe_available": interop.get("curl_exe_available", False),
        "curl_exe_path": interop.get("curl_exe_path"),

        # Tunnel state
        "tunnel_active": tunnel_active,
        "tunnel_method": tunnel_method,
        "tunnel_stats": tunnel_stats,

        # Chrome
        "cdp_port": 9222,

        # Choices
        "choices": choices,
    })


@tab_mesh_bp.route("/tab-mesh/wsl-start-tunnel", methods=["POST"])
def wsl_start_tunnel():
    """Start a WSL tunnel using the specified method.

    Request JSON::

        { "method": "python_proxy", "port": 9222 }
    """
    data = request.get_json(force=True, silent=True) or {}
    method = data.get("method", "python_proxy")
    port = data.get("port", 9222)

    from src.core.services.chrome.wsl_tunnel import (
        TUNNEL_METHODS, start_tunnel,
    )

    if method not in TUNNEL_METHODS:
        return jsonify({
            "ok": False,
            "error": f"Unknown tunnel method: {method}",
            "available_methods": list(TUNNEL_METHODS.keys()),
        }), 400

    # Resolve target host
    import socket as _socket
    target_host = None
    try:
        hostname_r = subprocess.run(
            ["hostname"],
            capture_output=True, text=True, timeout=3,
        )
        hostname = hostname_r.stdout.strip()
        if hostname:
            fqdn = f"{hostname}.local"
            try:
                infos = _socket.getaddrinfo(
                    fqdn, None, _socket.AF_INET, _socket.SOCK_STREAM,
                )
                if infos:
                    target_host = infos[0][4][0]
            except (_socket.gaierror, OSError):
                pass
    except Exception:
        pass

    if not target_host and method not in ("mirrored",):
        return jsonify({
            "ok": False,
            "error": "Cannot resolve hostname.local — target host unknown.",
        }), 400

    tunnel = start_tunnel(
        local_port=port,
        target_host=target_host or "127.0.0.1",
        method=method,
    )

    if tunnel:
        # Dismiss stale gap notifications now that tunnel is active
        try:
            from flask import current_app
            from src.core.services.notifications import (
                create_notification, dismiss_notification_by_type,
            )
            project_root = Path(current_app.config["PROJECT_ROOT"])
            dismiss_notification_by_type(project_root, "wsl_channel_upgrade")
            dismiss_notification_by_type(project_root, "wsl_firewall_rule")

            method_name = TUNNEL_METHODS[method]["label"]
            create_notification(
                project_root,
                notif_type="wsl_channel_active",
                title="CDP Channel: Level 2 Active ✅",
                message=(
                    f"Direct Channel via {method_name} is running. "
                    "CDP latency improved from ~2000ms to ~5ms."
                ),
                meta={"level": 2, "method": method},
                dedup=True,
            )
        except Exception:
            pass  # Notifications must never break tunnel start

        return jsonify({
            "ok": True,
            "method": method,
            "stats": tunnel.stats,
            "message": f"Tunnel started: {TUNNEL_METHODS[method]['label']}",
        })
    else:
        return jsonify({
            "ok": False,
            "method": method,
            "error": f"Failed to start {TUNNEL_METHODS[method]['label']}.",
        }), 500


@tab_mesh_bp.route("/tab-mesh/wsl-stop-tunnel", methods=["POST"])
def wsl_stop_tunnel():
    """Stop the active WSL tunnel."""
    from src.core.services.chrome.wsl_tunnel import (
        get_active_tunnel, stop_tunnel,
    )

    tunnel = get_active_tunnel()
    if not tunnel or not tunnel.is_running:
        return jsonify({
            "ok": True,
            "action": "not_running",
            "message": "No tunnel is currently active.",
        })

    method = tunnel.stats.get("method", "unknown")
    stop_tunnel()

    return jsonify({
        "ok": True,
        "action": "stopped",
        "method": method,
        "message": f"Tunnel stopped ({method}).",
    })


@tab_mesh_bp.route("/tab-mesh/wsl-install-curl", methods=["POST"])
def wsl_install_curl():
    """Install curl.exe on Windows with robust multi-fallback chain.

    Tries each method in order of preference, skipping those whose
    prerequisites are not available:

      1. Verify it's not already installed (PowerShell alias check)
      2. winget install (built into modern Windows)
      3. scoop install (no elevation needed)
      4. chocolatey install (needs elevation)
      5. Direct download from curl.se (always available)

    Returns the method used and validation result.
    """
    # ── Step 0: Check if curl.exe already exists ──────────────
    existing = shutil.which("curl.exe")
    if existing:
        # Validate it works
        try:
            r = subprocess.run(
                [existing, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return jsonify({
                "ok": True,
                "action": "already_installed",
                "path": existing,
                "version": r.stdout.strip().splitlines()[0] if r.stdout else None,
            })
        except Exception:
            pass  # If validation fails, try reinstall

    # ── Build the fallback chain ──────────────────────────────
    # Each entry: (id, label, detect_cmd, install_cmd, needs_elevation)
    chain = _build_curl_install_chain()

    attempted: list[dict] = []
    for step in chain:
        step_result: dict = {
            "id": step["id"],
            "label": step["label"],
            "available": False,
            "attempted": False,
            "success": False,
            "error": None,
        }

        # Check if this method's prerequisite is available
        if step.get("detect_cmd"):
            try:
                r = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command",
                     step["detect_cmd"]],
                    capture_output=True, text=True, timeout=10,
                )
                step_result["available"] = (r.returncode == 0
                                            and r.stdout.strip())
            except Exception:
                step_result["available"] = False
        else:
            # No detection needed (e.g. direct download — always available)
            step_result["available"] = True

        if not step_result["available"]:
            attempted.append(step_result)
            continue

        # Attempt the install
        step_result["attempted"] = True
        try:
            if step.get("needs_elevation"):
                ok = _run_elevated_ps1(step["install_script"])
            else:
                r = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-ExecutionPolicy",
                     "Bypass", "-Command", step["install_cmd"]],
                    capture_output=True, text=True, timeout=120,
                )
                ok = r.returncode == 0
                if not ok:
                    step_result["error"] = r.stderr.strip()[:300]

            if ok:
                # Validate
                curl_path = shutil.which("curl.exe")
                if curl_path:
                    step_result["success"] = True
                    attempted.append(step_result)
                    return jsonify({
                        "ok": True,
                        "action": "installed",
                        "method": step["id"],
                        "path": curl_path,
                        "attempts": attempted,
                    })
                else:
                    step_result["error"] = (
                        "Install appeared to succeed but curl.exe "
                        "not found on PATH — may need WSL restart"
                    )
        except subprocess.TimeoutExpired:
            step_result["error"] = "timed out"
        except Exception as exc:
            step_result["error"] = str(exc)[:200]

        attempted.append(step_result)

    # All methods exhausted
    return jsonify({
        "ok": False,
        "action": "all_failed",
        "message": (
            "All automated installation methods failed. "
            "Please install curl manually from https://curl.se/windows/ "
            "and ensure it is on your Windows PATH."
        ),
        "attempts": attempted,
    }), 500


def _build_curl_install_chain() -> list[dict]:
    """Build the ordered curl.exe installation fallback chain."""
    return [
        {
            "id": "winget",
            "label": "Install via winget (recommended)",
            "detect_cmd": (
                "Get-Command winget -ErrorAction SilentlyContinue "
                "| Select-Object -ExpandProperty Source"
            ),
            "install_cmd": (
                "winget install --id curl.curl "
                "--accept-source-agreements "
                "--accept-package-agreements"
            ),
            "needs_elevation": False,
        },
        {
            "id": "scoop",
            "label": "Install via scoop (no elevation needed)",
            "detect_cmd": (
                "Get-Command scoop -ErrorAction SilentlyContinue "
                "| Select-Object -ExpandProperty Source"
            ),
            "install_cmd": "scoop install curl",
            "needs_elevation": False,
        },
        {
            "id": "choco",
            "label": "Install via Chocolatey",
            "detect_cmd": (
                "Get-Command choco -ErrorAction SilentlyContinue "
                "| Select-Object -ExpandProperty Source"
            ),
            "install_script": "choco install curl -y\n",
            "install_cmd": "",  # unused — elevated path
            "needs_elevation": True,
        },
        {
            "id": "direct_download",
            "label": "Download binary from curl.se",
            "detect_cmd": None,  # Always available
            "install_cmd": (
                "$url = 'https://curl.se/windows/latest.cgi?p=win64-mingw.zip'; "
                "$zip = \"$env:TEMP\\curl_download.zip\"; "
                "$dest = \"$env:LOCALAPPDATA\\curl\"; "
                "Invoke-WebRequest -Uri $url -OutFile $zip; "
                "Expand-Archive -Path $zip -DestinationPath $dest -Force; "
                "$binDir = Get-ChildItem $dest -Directory | "
                "Select-Object -First 1 -ExpandProperty FullName; "
                "$binPath = Join-Path $binDir 'bin'; "
                "$userPath = [Environment]::GetEnvironmentVariable('Path','User'); "
                "if ($userPath -notlike \"*$binPath*\") { "
                "[Environment]::SetEnvironmentVariable("
                "'Path', \"$userPath;$binPath\", 'User') }"
            ),
            "needs_elevation": False,
        },
    ]


def _run_elevated_ps1(script_content: str) -> bool:
    """Run a PowerShell script with UAC elevation.

    Writes the script to a temp .ps1 file on the Windows filesystem,
    then launches it via ``Start-Process -Verb RunAs``.
    """
    script_path_wsl = "/mnt/c/Windows/Temp/wsl_curl_install.ps1"
    script_path_win = "C:\\Windows\\Temp\\wsl_curl_install.ps1"

    try:
        with open(script_path_wsl, "w", encoding="utf-8") as f:
            f.write(script_content)

        elevated_cmd = (
            "Start-Process powershell -Verb RunAs -Wait "
            "-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass',"
            f"'-File','{script_path_win}'"
        )
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", elevated_cmd],
            capture_output=True, text=True, timeout=120,
        )

        try:
            os.remove(script_path_wsl)
        except OSError:
            pass

        return r.returncode == 0

    except Exception:
        return False
