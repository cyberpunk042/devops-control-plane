"""HTTP requests via Windows curl.exe subprocess.

Stateless bridge. Each call spawns a curl.exe subprocess that runs
in the Windows network namespace, able to reach Chrome's localhost.

This is the simplest cross-boundary HTTP mechanism — zero config,
works on any WSL2 system with curl.exe (pre-installed on Windows 10+).

Performance: ~50ms warm, ~2000ms cold (first call loads curl.exe).
"""

from __future__ import annotations

import logging
import subprocess

from .environment import get_environment

logger = logging.getLogger(__name__)


def curl_get(url: str, timeout: float = 2.0) -> str | None:
    """Use Windows curl.exe to make an HTTP GET request from WSL2.

    WSL2 runs in a separate network namespace from Windows.
    Chrome binds its debug port to 127.0.0.1 on the WINDOWS side,
    which is unreachable from WSL2's localhost.

    curl.exe runs in the Windows network namespace, so it CAN
    reach Chrome's localhost. This is a zero-config bridge.
    """
    curl_exe = get_environment().curl_exe
    if not curl_exe:
        return None
    try:
        r = subprocess.run(
            [curl_exe, "-s", "--connect-timeout", str(max(1, int(timeout))), url],
            capture_output=True, text=True,
            timeout=timeout + 2,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
        return None
    except (subprocess.TimeoutExpired, OSError):
        return None


def curl_put(url: str, timeout: float = 2.0) -> str | None:
    """PUT request via Windows curl.exe (same bridge as curl_get)."""
    curl_exe = get_environment().curl_exe
    if not curl_exe:
        return None
    try:
        r = subprocess.run(
            [curl_exe, "-s", "-X", "PUT",
             "--connect-timeout", str(max(1, int(timeout))), url],
            capture_output=True, text=True,
            timeout=timeout + 2,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
        return None
    except (subprocess.TimeoutExpired, OSError):
        return None
