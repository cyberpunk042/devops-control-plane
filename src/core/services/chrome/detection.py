"""
Chrome environment detection — WSL, Windows user, Chrome version.

Extracted from ``src.ui.web.routes.tab_mesh`` to serve as shared
infrastructure for both Tab Mesh and the Scripts System execution plans.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


def is_wsl() -> bool:
    """Quick check: are we running under WSL?"""
    try:
        with open("/proc/version", encoding="utf-8") as f:
            v = f.read().lower()
        return "microsoft" in v or "wsl" in v
    except (FileNotFoundError, OSError):
        return False


def get_windows_user() -> str | None:
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


def get_chrome_version() -> str | None:
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
