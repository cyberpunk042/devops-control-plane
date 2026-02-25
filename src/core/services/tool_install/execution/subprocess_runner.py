"""
L4 Execution — Core subprocess runner.

The SINGLE PLACE where ``subprocess.run`` is called for
install operations. All security, logging, and error handling
is centralised here.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)


def _run_subprocess(
    cmd: list[str],
    *,
    needs_sudo: bool = False,
    sudo_password: str = "",
    timeout: int = 120,
    env_overrides: dict[str, str] | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Run a subprocess command with sudo and env support.

    This is the SINGLE PLACE where subprocess.run is called for
    install operations.  All security, logging, and error handling
    is centralised here.

    Security invariants (from domain-sudo-security):
    - Password piped via stdin only (``sudo -S``)
    - ``-k`` invalidates cached credentials every time
    - Password never logged, never written to disk
    - Password never appears in command args

    Args:
        cmd: Command list for ``subprocess.run()``.
        needs_sudo: Whether the command requires root.
        sudo_password: Sudo password (piped to stdin).
        timeout: Seconds before ``TimeoutExpired``.
        env_overrides: Extra env vars (e.g. PATH from ``post_env``).

        cwd: Working directory for the command (Phase 5 builds).

    Returns:
        ``{"ok": True, "stdout": "...", "elapsed_ms": N}`` on success,
        ``{"ok": False, "error": "...", ...}`` on failure.
    """
    # ── Sudo handling ──
    if needs_sudo:
        if os.geteuid() == 0:
            # Already root — no sudo prefix needed
            pass
        elif not sudo_password:
            return {
                "ok": False,
                "needs_sudo": True,
                "error": "This step requires sudo. Please enter your password.",
            }
        else:
            cmd = ["sudo", "-S", "-k"] + cmd

    # ── Environment ──
    env = os.environ.copy()
    if env_overrides:
        for key, value in env_overrides.items():
            env[key] = os.path.expandvars(value)

    # ── Execute ──
    start = time.monotonic()
    try:
        stdin_data = (
            (sudo_password + "\n")
            if (needs_sudo and sudo_password and os.geteuid() != 0)
            else None
        )
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=stdin_data,
            env=env,
            cwd=cwd,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if result.returncode == 0:
            return {
                "ok": True,
                "stdout": result.stdout[-2000:] if result.stdout else "",
                "elapsed_ms": elapsed_ms,
            }

        stderr = result.stderr[-2000:] if result.stderr else ""

        # Wrong password?
        if needs_sudo and (
            "incorrect password" in stderr.lower()
            or "sorry" in stderr.lower()
        ):
            return {
                "ok": False,
                "needs_sudo": True,
                "error": "Wrong password. Try again.",
            }

        return {
            "ok": False,
            "error": f"Command failed (exit {result.returncode})",
            "stderr": stderr,
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "elapsed_ms": elapsed_ms,
        }

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Command timed out ({timeout}s)"}
    except Exception as e:
        logger.exception("Subprocess error: %s", cmd)
        return {"ok": False, "error": str(e)}
