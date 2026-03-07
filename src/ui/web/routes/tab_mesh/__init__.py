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


# ── Helpers ───────────────────────────────────────────────────


def _is_wsl() -> bool:
    """Quick check: are we running under WSL?"""
    try:
        with open("/proc/version", encoding="utf-8") as f:
            v = f.read().lower()
        return "microsoft" in v or "wsl" in v
    except (FileNotFoundError, OSError):
        return False


def _get_windows_user() -> str | None:
    """Detect the Windows username from WSL."""
    if not shutil.which("cmd.exe"):
        return None
    try:
        r = subprocess.run(
            ["cmd.exe", "/c", "echo", "%USERNAME%"],
            capture_output=True, text=True, timeout=5,
        )
        username = r.stdout.strip()
        if username and username != "%USERNAME%":
            return username
    except Exception:
        pass
    return None


def _chrome_data_dir(windows_user: str) -> str:
    """Return the WSL path to Chrome's default User Data directory."""
    return f"/mnt/c/Users/{windows_user}/AppData/Local/Google/Chrome/User Data"


def _chrome_data_dir_win(windows_user: str) -> str:
    """Return the Windows path to Chrome's default User Data directory."""
    return f"C:\\Users\\{windows_user}\\AppData\\Local\\Google\\Chrome\\User Data"


def _chrome_debug_data_dir_win(windows_user: str) -> str:
    """Return a SEPARATE user-data-dir for Chrome remote debugging.

    Chrome 136+ silently ignores --remote-debugging-port when
    --user-data-dir points to the DEFAULT User Data directory.
    We must use a different directory. Chrome will create a fresh
    profile there on first launch.
    """
    return f"C:\\Users\\{windows_user}\\AppData\\Local\\Google\\ChromeDebug"


def _read_chrome_profiles(data_dir: str) -> list[dict]:
    """Read Chrome profiles from the Local State file.

    Returns a list of dicts with keys: dir, name, email.
    """
    local_state = Path(data_dir) / "Local State"
    if not local_state.exists():
        return []

    try:
        with open(local_state, encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    info_cache = state.get("profile", {}).get("info_cache", {})
    profiles = []
    for dir_name, info in sorted(info_cache.items()):
        profiles.append({
            "dir": dir_name,
            "name": info.get("name", dir_name),
            "email": info.get("user_name", ""),
        })
    return profiles


def _shortcut_locations(windows_user: str) -> dict[str, str]:
    """Return all known Chrome shortcut paths (WSL paths)."""
    return {
        "taskbar": (
            f"/mnt/c/Users/{windows_user}/AppData/Roaming"
            f"/Microsoft/Internet Explorer/Quick Launch"
            f"/User Pinned/TaskBar/Google Chrome.lnk"
        ),
        "desktop": f"/mnt/c/Users/{windows_user}/Desktop/Google Chrome.lnk",
        "start_menu_global": (
            "/mnt/c/ProgramData/Microsoft/Windows"
            "/Start Menu/Programs/Google Chrome.lnk"
        ),
        "start_menu_user": (
            f"/mnt/c/Users/{windows_user}/AppData/Roaming"
            f"/Microsoft/Windows/Start Menu/Programs/Google Chrome.lnk"
        ),
    }


def _wsl_to_win_path(wsl_path: str) -> str:
    """Convert a WSL /mnt/c/... path to Windows C:\\... path."""
    if wsl_path.startswith("/mnt/c/"):
        return "C:\\" + wsl_path[7:].replace("/", "\\")
    return wsl_path


def _read_shortcut(wsl_path: str) -> dict | None:
    """Read a .lnk shortcut's target and arguments via PowerShell.

    Returns dict with keys: target, args — or None if unreadable.
    """
    if not os.path.exists(wsl_path):
        return None
    if not shutil.which("powershell.exe"):
        return None

    win_path = _wsl_to_win_path(wsl_path)
    ps_cmd = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$lnk = $shell.CreateShortcut('{win_path}'); "
        "Write-Host '::TARGET::' $lnk.TargetPath; "
        "Write-Host '::ARGS::' $lnk.Arguments"
    )
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10,
        )
        target = ""
        args = ""
        for line in r.stdout.splitlines():
            if "::TARGET::" in line:
                target = line.split("::TARGET::", 1)[1].strip()
            elif "::ARGS::" in line:
                args = line.split("::ARGS::", 1)[1].strip()
        return {"target": target, "args": args}
    except Exception as exc:
        logger.warning("Failed to read shortcut %s: %s", win_path, exc)
        return None


def _get_chrome_version() -> str | None:
    """Get Chrome version string from the executable."""
    chrome_exe = "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
    if not os.path.exists(chrome_exe):
        return None

    # Read version from the chrome.exe directory's version file
    chrome_dir = Path(chrome_exe).parent
    try:
        # Chrome stores version in a subdirectory name like "138.0.6423.82"
        for child in chrome_dir.iterdir():
            if child.is_dir() and re.match(r"\d+\.\d+\.\d+\.\d+", child.name):
                return child.name
    except OSError:
        pass

    return None


def _modify_shortcut(
    wsl_path: str,
    add_port: int,
    user_data_dir: str | None,
) -> bool:
    """Modify a .lnk shortcut to add Chrome debugging flags.

    Reads current arguments, appends missing flags, writes back.
    If the write fails (e.g. system directory), retries with UAC
    elevation which pops a Windows confirmation dialog.
    """
    if not shutil.which("powershell.exe"):
        return False

    current = _read_shortcut(wsl_path)
    if current is None:
        return False

    existing_args = current["args"]

    # Build new args — replace or add flags as needed
    new_args = existing_args
    if f"--remote-debugging-port={add_port}" not in existing_args:
        new_args = f"{new_args} --remote-debugging-port={add_port}".strip()

    if user_data_dir:
        target_arg = f'--user-data-dir="{user_data_dir}"'
        if "--user-data-dir=" not in existing_args:
            # No user-data-dir set — add it
            new_args = f'{new_args} {target_arg}'.strip()
        elif target_arg not in existing_args:
            # Remove the old --user-data-dir=... (with or without quotes)
            new_args = re.sub(
                r'--user-data-dir="[^"]*"',
                lambda _: target_arg,
                new_args,
            )
            # Also handle unquoted form
            if target_arg not in new_args:
                new_args = re.sub(
                    r'--user-data-dir=\S+',
                    lambda _: target_arg,
                    new_args,
                )

    if new_args == existing_args:
        logger.info("Shortcut already has required flags: %s", wsl_path)
        return True  # Already configured

    win_path = _wsl_to_win_path(wsl_path)
    # Escape single quotes in the arguments for PowerShell
    safe_args = new_args.replace("'", "''")
    ps_cmd = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$lnk = $shell.CreateShortcut('{win_path}'); "
        f"$lnk.Arguments = '{safe_args}'; "
        "$lnk.Save()"
    )
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            logger.info("Updated shortcut: %s → args: %s", win_path, new_args)
            return True

        # Check if it's a permissions issue — retry with UAC elevation
        if "UnauthorizedAccessException" in r.stderr:
            logger.info(
                "Permission denied for %s, retrying with elevation...",
                win_path,
            )
            return _modify_shortcut_elevated(win_path, safe_args)

        logger.warning(
            "PowerShell shortcut update failed (rc=%d): %s",
            r.returncode, r.stderr.strip(),
        )
        return False
    except Exception as exc:
        logger.warning("Failed to modify shortcut %s: %s", win_path, exc)
        return False


def _modify_shortcut_elevated(win_path: str, safe_args: str) -> bool:
    """Modify a shortcut using UAC-elevated PowerShell.

    Writes the modification script to a temp .ps1 file, then
    launches an elevated PowerShell process to execute it.
    This avoids all quoting issues with paths containing spaces.
    """
    import tempfile

    # Write the PS1 script to a temp file on the Windows filesystem
    # (elevated PowerShell needs to read it, so it must be on C:\)
    inner_script = (
        "$shell = New-Object -ComObject WScript.Shell\n"
        f"$lnk = $shell.CreateShortcut('{win_path}')\n"
        f"$lnk.Arguments = '{safe_args}'\n"
        "$lnk.Save()\n"
    )
    try:
        # Write to Windows temp dir so the elevated process can access it
        tmp_dir = "/mnt/c/Windows/Temp"
        script_path_wsl = f"{tmp_dir}/cdp_shortcut_fix.ps1"
        script_path_win = "C:\\Windows\\Temp\\cdp_shortcut_fix.ps1"

        with open(script_path_wsl, "w", encoding="utf-8") as f:
            f.write(inner_script)

        # Run the script elevated — triggers UAC prompt
        elevated_cmd = (
            "Start-Process powershell -Verb RunAs -Wait "
            f"-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass',"
            f"'-File','{script_path_win}'"
        )
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", elevated_cmd],
            capture_output=True, text=True, timeout=30,
        )

        # Clean up temp file
        try:
            os.remove(script_path_wsl)
        except OSError:
            pass

        if r.returncode == 0:
            logger.info("Elevated update succeeded: %s", win_path)
            return True
        logger.warning(
            "Elevated update failed (rc=%d): %s",
            r.returncode, r.stderr.strip(),
        )
        return False
    except Exception as exc:
        logger.warning("Elevated shortcut update failed: %s", exc)
        return False


# ── Routes ────────────────────────────────────────────────────


def _clone_profile_to_debug_dir(
    windows_user: str,
    profile_dir: str = "Default",
) -> dict:
    """Clone essential Chrome profile files to the debug data directory.

    Copies bookmarks, login data, preferences, extensions,
    and other essentials so the debug Chrome instance feels like home.
    Returns a status dict with what was copied.
    """
    src_root = Path(_chrome_data_dir(windows_user))
    debug_dir_win = _chrome_debug_data_dir_win(windows_user)
    # Convert win path to WSL path for file operations
    dst_root = Path(
        "/mnt/c/"
        + debug_dir_win[3:].replace("\\", "/")
    )

    status: dict = {"copied": [], "skipped": [], "errors": []}

    # Create the debug dir structure
    dst_profile = dst_root / profile_dir
    dst_profile.mkdir(parents=True, exist_ok=True)

    # Copy Local State (profile metadata, at the root level)
    local_state = src_root / "Local State"
    if local_state.exists():
        try:
            shutil.copy2(local_state, dst_root / "Local State")
            status["copied"].append("Local State")
        except Exception as exc:
            status["errors"].append(f"Local State: {exc}")

    # Essential profile files to copy
    essentials = [
        "Bookmarks",
        "Preferences",
        "Secure Preferences",
        "Login Data",
        "Login Data-journal",
        "Web Data",
        "Web Data-journal",
        "Favicons",
        "Favicons-journal",
        "Cookies",
        "Cookies-journal",
        "Top Sites",
        "History",
    ]

    src_profile = src_root / profile_dir
    if not src_profile.is_dir():
        status["errors"].append(f"Profile dir not found: {profile_dir}")
        return status

    for fname in essentials:
        src_file = src_profile / fname
        if src_file.exists():
            try:
                shutil.copy2(src_file, dst_profile / fname)
                status["copied"].append(fname)
            except Exception as exc:
                status["errors"].append(f"{fname}: {exc}")
        else:
            status["skipped"].append(fname)

    # Copy Extensions directory (can be large but essential for UX)
    ext_src = src_profile / "Extensions"
    ext_dst = dst_profile / "Extensions"
    if ext_src.is_dir() and not ext_dst.exists():
        try:
            shutil.copytree(ext_src, ext_dst, dirs_exist_ok=True)
            status["copied"].append("Extensions/")
        except Exception as exc:
            status["errors"].append(f"Extensions: {exc}")

    logger.info(
        "Profile clone: %d copied, %d skipped, %d errors",
        len(status["copied"]),
        len(status["skipped"]),
        len(status["errors"]),
    )
    return status


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

    Request body::

        { "urlPattern": "/", "excludeUrl": "..." }

    Returns::

        { "success": true, "url": "...", "targetId": "..." }
    """
    from src.ui.web import cdp_client

    data = request.get_json(silent=True) or {}
    url_pattern = data.get("urlPattern", "/")
    exclude_url = data.get("excludeUrl")

    # get_targets returns [] if CDP unreachable — no need for is_available()
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
    for key, wsl_path in shortcut_paths.items():
        found = os.path.exists(wsl_path)
        shortcut_info: dict = {"found": found}
        if found:
            details = _read_shortcut(wsl_path)
            if details:
                shortcut_info["target"] = details["target"]
                shortcut_info["args"] = details["args"]
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
        result["shortcuts"][key] = shortcut_info

    # CDP active?
    cdp_client.try_discover_endpoint()
    result["cdp_active"] = cdp_client.is_available()

    return jsonify(result)


@tab_mesh_bp.route("/tab-mesh/cdp-remediate", methods=["POST"])
def cdp_remediate():
    """Apply Chrome debugging flags to selected shortcuts.

    Request body::

        {
            "shortcuts": ["taskbar", "desktop", "start_menu_global"],
            "profile_dir": "Default",
            "port": 9222
        }

    Returns::

        {
            "results": {
                "taskbar": { "success": true },
                "desktop": { "success": true },
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
    results: dict = {}

    for key in shortcut_keys:
        wsl_path = all_shortcuts.get(key)
        if not wsl_path:
            results[key] = {"success": False, "reason": "unknown_shortcut"}
            continue
        if not os.path.exists(wsl_path):
            results[key] = {"success": False, "reason": "not_found"}
            continue

        ok = _modify_shortcut(wsl_path, port, user_data_dir)
        results[key] = {"success": ok}

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

