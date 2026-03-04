"""
Server lifecycle management — status, restart signals, PID tracking.

Channel-independent: no Flask or HTTP dependency.

Provides the infrastructure for graceful server restarts,
including folder rename + CWD change scenarios.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Process metadata ────────────────────────────────────────────

_start_time: float = time.time()


def server_status(project_root: Path, *, host: str = "", port: int = 0) -> dict:
    """Return current server process metadata.

    Returns::

        {
            "pid": 12345,
            "uptime_s": 3600,
            "cwd": "/home/user/project",
            "host": "127.0.0.1",
            "port": 8000,
            "python": "/home/user/.venv/bin/python",
        }
    """
    uptime = time.time() - _start_time
    return {
        "pid": os.getpid(),
        "uptime_s": round(uptime, 1),
        "cwd": str(project_root),
        "host": host,
        "port": port,
        "python": sys.executable,
    }


# ── Restart signal ──────────────────────────────────────────────

_RESTART_EXIT_CODE = 42
_RESTART_SIGNAL_FILE = ".restart-signal"


def request_restart(project_root: Path, *, new_cwd: str | None = None) -> dict:
    """Request a graceful server restart.

    Writes a ``.restart-signal`` file (optionally with a new CWD)
    and exits the process with code 42.  The ``manage.sh`` wrapper
    catches this exit code and re-launches the server.

    If ``new_cwd`` is a different directory, this function attempts
    to ``os.rename()`` the project folder before exiting.

    Args:
        project_root: Current project root directory.
        new_cwd: Optional new CWD to restart into (e.g. after folder rename).

    Returns:
        This function never returns — it calls ``os._exit(42)``.
        The dict return type is for error responses only.
    """
    signal_path = project_root / _RESTART_SIGNAL_FILE
    current_cwd = str(project_root)
    rename_folder = False

    # Determine if a folder rename is needed
    if new_cwd and new_cwd.strip() and new_cwd.strip() != current_cwd:
        new_cwd = new_cwd.strip()
        rename_folder = True
    else:
        new_cwd = None

    # Write signal file FIRST (before rename, since manage.sh reads from old CWD)
    try:
        content = new_cwd or ""
        signal_path.write_text(content, encoding="utf-8")
        logger.info(
            "Restart signal written to %s (new_cwd=%s)",
            signal_path, new_cwd or "<same>",
        )
    except OSError as exc:
        return {"error": f"Failed to write restart signal: {exc}"}

    # Publish SSE event before exiting (if event bus is available)
    try:
        from src.core.services.event_bus import bus
        bus.publish("server:restarting", data={
            "new_cwd": new_cwd,
            "message": "Server restarting...",
        })
        # Small delay to let SSE flush to clients
        time.sleep(0.3)
    except Exception:
        pass  # Best-effort — SSE may not be available

    # Rename the folder if needed
    if rename_folder and new_cwd:
        new_path = Path(new_cwd)
        if new_path.exists():
            # Clean up signal file if rename would fail
            signal_path.unlink(missing_ok=True)
            return {"error": f"Target path already exists: {new_cwd}"}

        try:
            os.rename(current_cwd, new_cwd)
            logger.info("Folder renamed: %s → %s", current_cwd, new_cwd)
        except OSError as exc:
            # Clean up signal file on failure
            signal_path.unlink(missing_ok=True)
            return {"error": f"Failed to rename folder: {exc}"}

    logger.info("Exiting with code %d for restart", _RESTART_EXIT_CODE)
    os._exit(_RESTART_EXIT_CODE)  # noqa: SLF001 — bypass Flask's exception handling


# ── Signal handlers ─────────────────────────────────────────────

def install_signal_handlers() -> None:
    """Register SIGTERM and SIGINT handlers for graceful shutdown.

    Should be called once during ``run_server()`` setup.
    Ensures vault auto-lock, SSE cleanup, and event bus flush
    happen before the process exits.
    """
    def _graceful_shutdown(signum: int, frame: object) -> None:
        sig_name = signal.Signals(signum).name
        logger.info("Received %s — initiating graceful shutdown", sig_name)

        # 1. Try to lock vault (preserve auto-lock guarantee)
        try:
            from src.core.services import vault
            if hasattr(vault, "lock_vault") and vault._session_passphrase:
                vault.lock_vault(vault._project_root, vault._session_passphrase)
                logger.info("Vault locked on shutdown")
        except Exception:
            pass  # Best-effort

        # 2. Flush event bus
        try:
            from src.core.services.event_bus import bus
            bus.publish("sys:shutdown", data={"signal": sig_name})
        except Exception:
            pass

        logger.info("Graceful shutdown complete — exiting")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT, _graceful_shutdown)
    logger.debug("Signal handlers installed (SIGTERM, SIGINT)")
