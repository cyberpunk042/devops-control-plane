"""
Chrome profile management — path helpers, profile reading, profile cloning.

Extracted from ``src.ui.web.routes.tab_mesh`` to serve as shared
infrastructure for both Tab Mesh and the Scripts System execution plans.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def chrome_data_dir(windows_user: str) -> str:
    """Return the WSL path to Chrome's default User Data directory."""
    return f"/mnt/c/Users/{windows_user}/AppData/Local/Google/Chrome/User Data"


def chrome_data_dir_win(windows_user: str) -> str:
    """Return the Windows path to Chrome's default User Data directory."""
    return f"C:\\Users\\{windows_user}\\AppData\\Local\\Google\\Chrome\\User Data"


def chrome_debug_data_dir_win(windows_user: str) -> str:
    """Return a SEPARATE user-data-dir for Chrome remote debugging.

    Chrome 136+ silently ignores --remote-debugging-port when
    --user-data-dir points to the DEFAULT User Data directory.
    We must use a different directory. Chrome will create a fresh
    profile there on first launch.
    """
    return f"C:\\Users\\{windows_user}\\AppData\\Local\\Google\\ChromeDebug"


def create_temp_profile_dir(port: int) -> str:
    """Create a temporary Chrome profile directory for Linux.

    Creates ``/tmp/chrome-debug-{port}/`` with a ``First Run``
    sentinel file and default ``Preferences`` to suppress
    first-run dialogs and default-browser checks.

    Each port gets its own directory to avoid profile locking
    conflicts between simultaneous Chrome instances.

    Args:
        port: The debug port, used to namespace the directory.

    Returns:
        Absolute path to the created profile directory.
    """
    profile_dir = f"/tmp/chrome-debug-{port}"
    os.makedirs(profile_dir, exist_ok=True)

    # Write the "First Run" sentinel so Chrome skips the welcome flow
    first_run = os.path.join(profile_dir, "First Run")
    if not os.path.exists(first_run):
        with open(first_run, "w") as f:
            f.write("")

    # Write minimal Preferences to suppress default-browser check
    # and restore-pages prompt
    prefs_path = os.path.join(profile_dir, "Default", "Preferences")
    prefs_dir = os.path.dirname(prefs_path)
    os.makedirs(prefs_dir, exist_ok=True)
    if not os.path.exists(prefs_path):
        prefs = {
            "browser": {
                "check_default_browser": False,
            },
            "session": {
                "restore_on_startup": 4,  # 4 = open blank page
            },
        }
        with open(prefs_path, "w", encoding="utf-8") as f:
            json.dump(prefs, f)

    logger.info("Temp profile dir ready: %s", profile_dir)
    return profile_dir


def read_chrome_profiles(data_dir: str) -> list[dict]:
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


def clone_profile_to_debug_dir(
    windows_user: str,
    profile_dir: str = "Default",
) -> dict:
    """Clone essential Chrome profile files to the debug data directory.

    Copies bookmarks, login data, preferences, extensions,
    and other essentials so the debug Chrome instance feels like home.
    Returns a status dict with what was copied.
    """
    src_root = Path(chrome_data_dir(windows_user))
    debug_dir_win = chrome_debug_data_dir_win(windows_user)
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
