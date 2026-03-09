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


# ── Native Linux Chrome detection ────────────────────────────

_CHROME_LINUX_NAMES = (
    "google-chrome-stable",   # Google Chrome official (Debian/Ubuntu)
    "google-chrome",          # Some distros use this name
    "chromium-browser",       # Ubuntu/Debian Chromium
    "chromium",               # Fedora/Arch Chromium
)


def find_chrome_linux() -> str | None:
    """Find Chrome or Chromium binary on native Linux.

    Search order (highest priority first):
    1. google-chrome-stable  (Google Chrome official)
    2. google-chrome         (some distros use this name)
    3. chromium-browser      (Ubuntu/Debian Chromium)
    4. chromium              (Fedora/Arch Chromium)

    Returns the full path to the first found binary, or None.
    """
    for name in _CHROME_LINUX_NAMES:
        path = shutil.which(name)
        if path:
            return path
    return None


def get_chrome_version_linux(chrome_path: str) -> str | None:
    """Get Chrome/Chromium version by running ``<binary> --version``.

    Handles output like:
    - ``Google Chrome 145.0.7632.109``
    - ``Chromium 128.0.6613.84 built on Debian ...``

    Returns the version string (e.g. ``"145.0.7632.109"``), or None.
    """
    try:
        r = subprocess.run(
            [chrome_path, "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return None
        # Parse: "Google Chrome 145.0.7632.109" or "Chromium 128.0.6613.84 ..."
        match = re.search(r"(\d+\.\d+\.\d+\.\d+)", r.stdout)
        if match:
            return match.group(1)
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


# ── Environment capability checks ────────────────────────────


def has_display() -> bool:
    """Check if a graphical display is available.

    Checks DISPLAY (X11), WAYLAND_DISPLAY (Wayland), and
    MIR_SOCKET (Mir) environment variables.

    Returns False in headless/Docker/CI environments.
    """
    return bool(
        os.environ.get("DISPLAY")
        or os.environ.get("WAYLAND_DISPLAY")
        or os.environ.get("MIR_SOCKET")
    )


def is_docker() -> bool:
    """Check if running inside a Docker container.

    Chrome in Docker often needs ``--no-sandbox`` in addition to
    ``--headless`` due to seccomp restrictions.
    """
    # Method 1: /.dockerenv exists
    if os.path.exists("/.dockerenv"):
        return True
    # Method 2: /proc/1/cgroup contains "docker" or "containerd"
    try:
        with open("/proc/1/cgroup", encoding="utf-8") as f:
            cgroup = f.read().lower()
        if "docker" in cgroup or "containerd" in cgroup:
            return True
    except (FileNotFoundError, OSError):
        pass
    return False


# ── curl.exe bridge (WSL2) ───────────────────────────────────

_curl_exe_path: str | None = None
_curl_exe_resolved: bool = False


def get_curl_exe() -> str | None:
    """Cached lookup for curl.exe path."""
    global _curl_exe_path, _curl_exe_resolved
    if _curl_exe_resolved:
        return _curl_exe_path
    _curl_exe_path = shutil.which("curl.exe")
    _curl_exe_resolved = True
    return _curl_exe_path
