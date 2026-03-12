"""System capability detection for WSL2↔Windows transport.

Answers: "what kind of system is this?" and "what tools do we have?"

Does NOT probe network. Does NOT connect to anything.
All checks read files or call ``shutil.which`` — no TCP, no subprocess
calls that could hang.

The ``WslEnvironment`` dataclass is an immutable snapshot detected once
at first use and cached for the process lifetime.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ── Immutable environment snapshot ────────────────────────────


@dataclass(frozen=True)
class WslEnvironment:
    """Immutable snapshot of system capabilities.

    Detected once at first use.  Cached for process lifetime.
    These checks read files and call ``which`` — no network.
    """

    wsl2: bool
    """Running inside WSL2?"""

    curl_exe: str | None
    """Full path to ``curl.exe`` (None if not found)."""

    powershell_exe: str | None
    """Full path to ``powershell.exe`` (None if not found)."""

    win_temp_dir: str | None
    """Windows ``%TEMP%`` directory path accessible from WSL.

    Resolved via ``/mnt/c/Users/<user>/AppData/Local/Temp``.
    Used by PowerShell bridge to write temp scripts.
    None if not on WSL2 or if the path doesn't exist.
    """


# ── Singleton ─────────────────────────────────────────────────

_env: WslEnvironment | None = None


def get_environment() -> WslEnvironment:
    """Return cached environment.  Detect on first call.

    Thread-safe: worst case two threads detect simultaneously and
    both arrive at the same result (all checks are idempotent).
    """
    global _env
    if _env is not None:
        return _env

    wsl2 = _detect_wsl2()
    curl_exe = shutil.which("curl.exe") if wsl2 else None
    powershell_exe = shutil.which("powershell.exe") if wsl2 else None
    win_temp_dir = _resolve_win_temp() if wsl2 else None

    _env = WslEnvironment(
        wsl2=wsl2,
        curl_exe=curl_exe,
        powershell_exe=powershell_exe,
        win_temp_dir=win_temp_dir,
    )

    logger.info(
        "WSL environment detected: wsl2=%s, curl_exe=%s, ps_exe=%s, "
        "win_temp=%s",
        _env.wsl2,
        "yes" if _env.curl_exe else "no",
        "yes" if _env.powershell_exe else "no",
        "yes" if _env.win_temp_dir else "no",
    )

    return _env


# ── Quick accessors ───────────────────────────────────────────


def is_wsl2() -> bool:
    """Quick cached check: are we running under WSL2?

    This is safe to call very early — it only reads ``/proc/version``.
    """
    return get_environment().wsl2


# ── Internal detection helpers ────────────────────────────────


def _detect_wsl2() -> bool:
    """Check ``/proc/version`` for Microsoft kernel signature.

    Returns True if the kernel version string contains 'microsoft',
    which indicates WSL2 (WSL1 uses a real Windows kernel and would
    not have this file).
    """
    try:
        with open("/proc/version", encoding="utf-8") as f:
            content = f.read().lower()
        return "microsoft" in content
    except OSError:
        return False


def _resolve_win_temp() -> str | None:
    """Find the Windows ``%TEMP%`` directory accessible from WSL.

    Looks for ``/mnt/c/Users/<user>/AppData/Local/Temp`` where
    ``<user>`` is detected via ``cmd.exe /c echo %USERNAME%``.

    Returns the path if it exists, else None.
    """
    import subprocess

    try:
        r = subprocess.run(
            ["cmd.exe", "/c", "echo", "%TEMP%"],
            capture_output=True, text=True, timeout=5,
        )
        win_path = r.stdout.strip()
        if not win_path or win_path == "%TEMP%":
            return None

        # Convert Windows path to WSL path: C:\Users\... → /mnt/c/Users/...
        if ":" in win_path:
            drive = win_path[0].lower()
            rest = win_path[2:].replace("\\", "/")
            wsl_path = f"/mnt/{drive}{rest}"
        else:
            wsl_path = win_path

        if os.path.isdir(wsl_path):
            return wsl_path
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        pass

    return None
