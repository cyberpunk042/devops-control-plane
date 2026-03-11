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
from typing import Any

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

# ── PID file management ────────────────────────────────────────

_PID_FILENAME = "server.pid"
_STATE_DIR = ".state"


def _pid_path(project_root: Path) -> Path:
    """Return the PID file path inside ``.state/``."""
    return project_root / _STATE_DIR / _PID_FILENAME


def write_pid_file(project_root: Path, port: int) -> None:
    """Write a PID file recording this process and the bound port.

    Format: ``PID:PORT`` on a single line.
    Stored in ``.state/server.pid`` (gitignored runtime directory).
    """
    path = _pid_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"{os.getpid()}:{port}"
    try:
        path.write_text(content, encoding="utf-8")
        logger.debug("PID file written: %s (%s)", path, content)
    except OSError as exc:
        logger.warning("Failed to write PID file: %s", exc)


def read_pid_file(project_root: Path) -> tuple[int, int] | None:
    """Read the PID file, returning ``(pid, port)`` or None.

    Returns None if the file doesn't exist, is malformed, or
    cannot be read.
    """
    path = _pid_path(project_root)
    if not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8").strip()
        pid_str, port_str = content.split(":")
        return int(pid_str), int(port_str)
    except (OSError, ValueError):
        return None


def clear_pid_file(project_root: Path) -> None:
    """Remove the PID file (on clean shutdown)."""
    path = _pid_path(project_root)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    try:
        os.kill(pid, 0)  # Signal 0 = existence check, no signal sent
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Process exists but owned by another user


def _is_port_free(host: str, port: int) -> bool:
    """Check if a TCP port is available for binding.

    Uses SO_REUSEADDR to match Flask's socket options — a port
    in TIME_WAIT (from a recently stopped server) is still
    considered free, because Flask can bind to it.
    """
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(0.5)
    try:
        sock.bind((host, port))
        sock.close()
        return True
    except OSError:
        return False


def _probe_our_server(host: str, port: int, project_root: Path) -> bool:
    """HTTP probe to check if a running server on host:port is ours.

    Hits ``/api/server/status`` and checks if the response CWD
    matches our project root.  Returns False on any error.
    """
    import urllib.request
    import json as _json

    url = f"http://{host}:{port}/api/server/status"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = _json.loads(resp.read())
            remote_cwd = data.get("cwd", "")
            return str(project_root) == remote_cwd
    except Exception:
        return False


# ── Port occupant identification ───────────────────────────────


def identify_port_occupant(host: str, port: int) -> dict[str, Any]:
    """Identify what process is holding a TCP port.

    Uses ``ss -tlnp`` (no root needed for own-user processes)
    with fallback to ``lsof -i``.  Reads ``/proc/{pid}/cmdline``
    for the full command line when PID is available.

    Returns::

        {
            "pid": 4521,                    # or None
            "name": "node",                 # or None
            "cmdline": "node ./server.js",  # or None
        }

    All fields may be None if detection fails — the port is still
    occupied, we just can't identify who.
    """
    import re
    import subprocess

    result: dict[str, Any] = {"pid": None, "name": None, "cmdline": None}

    # ── Try ss first (available on most Linux) ──
    try:
        out = subprocess.run(
            ["ss", "-tlnp", f"sport = :{port}"],
            capture_output=True, text=True, timeout=3,
        )
        # Parse: users:(("node",pid=4521,fd=19))
        match = re.search(
            r'users:\(\("([^"]+)",pid=(\d+)',
            out.stdout,
        )
        if match:
            result["name"] = match.group(1)
            result["pid"] = int(match.group(2))
    except Exception:
        pass

    # ── Fallback to lsof ──
    if result["pid"] is None:
        try:
            out = subprocess.run(
                ["lsof", "-i", f":{port}", "-sTCP:LISTEN", "-t"],
                capture_output=True, text=True, timeout=3,
            )
            pid_str = out.stdout.strip().split("\n")[0]
            if pid_str.isdigit():
                result["pid"] = int(pid_str)
        except Exception:
            pass

    # ── Read cmdline from /proc if we have PID ──
    if result["pid"]:
        try:
            raw = Path(f"/proc/{result['pid']}/cmdline").read_bytes()
            result["cmdline"] = (
                raw.replace(b"\x00", b" ")
                .decode("utf-8", errors="replace")
                .strip()
            )
            if not result["name"]:
                result["name"] = (
                    result["cmdline"].split()[0].rsplit("/", 1)[-1]
                )
        except Exception:
            pass

    return result


# ── Port resolution ────────────────────────────────────────────


class PortResolutionError(Exception):
    """All candidate ports are occupied by other processes."""


def resolve_port(
    project_root: Path,
    *,
    preferred_port: int = 8000,
    fallback_ports: list[int] | None = None,
    host: str = "127.0.0.1",
    cli_port_override: int | None = None,
) -> int:
    """Resolve which port to bind the admin panel to.

    Resolution order:

    1. If ``cli_port_override`` is given (user passed ``--port``),
       try that port only — no fallback.
    2. Try ``preferred_port`` (from project.yml ``web.port``).
    3. If ``preferred_port`` is occupied:
       a. Check PID file — if it's our old process, signal it to
          stop and claim the port.
       b. If it's a stranger, try each ``fallback_port`` in order.
    4. If all ports exhausted, raise ``PortResolutionError``.

    On success, writes a PID file recording the chosen port.

    Args:
        project_root: Project root directory.
        preferred_port: Default port from config (default 8000).
        fallback_ports: Fallback list from config.
        host: Bind address.
        cli_port_override: User-specified port from CLI (no fallback).

    Returns:
        The resolved port number.

    Raises:
        PortResolutionError: If no port is available.
    """
    if fallback_ports is None:
        fallback_ports = [8001, 8002, 8080, 8888, 9000]

    # ── CLI override: user explicitly chose a port ──
    if cli_port_override is not None:
        port = cli_port_override
        if _is_port_free(host, port):
            logger.info("Port %d is free (CLI override)", port)
            write_pid_file(project_root, port)
            return port

        # Port is busy — check if it's us
        if _try_takeover(project_root, host, port):
            write_pid_file(project_root, port)
            return port

        raise PortResolutionError(
            f"Port {port} is occupied by another process. "
            f"Stop the other process or choose a different port."
        )

    # ── Normal resolution: preferred → fallbacks ──
    candidates = [preferred_port] + [
        p for p in fallback_ports if p != preferred_port
    ]

    for port in candidates:
        if _is_port_free(host, port):
            if port != preferred_port:
                logger.info(
                    "Preferred port %d busy, using fallback port %d",
                    preferred_port, port,
                )
            else:
                logger.info("Port %d is free", port)
            write_pid_file(project_root, port)
            return port

        # Port is busy — check if it's our old process
        if _try_takeover(project_root, host, port):
            write_pid_file(project_root, port)
            return port

        logger.debug("Port %d occupied by another process, trying next", port)

    # All exhausted
    tried = ", ".join(str(p) for p in candidates)
    raise PortResolutionError(
        f"All candidate ports are occupied: {tried}. "
        f"Either stop the conflicting processes, or set a custom port "
        f"in project.yml under web.port / web.fallback_ports."
    )


def _try_takeover(project_root: Path, host: str, port: int) -> bool:
    """Attempt to take over a port occupied by our own old process.

    1. Check PID file — if the PID matches and is alive, send SIGTERM
    2. HTTP-probe /api/server/status to confirm it's really us
    3. Wait for port to become free

    Returns True if takeover succeeded, False otherwise.
    """
    pid_info = read_pid_file(project_root)

    # If PID file exists and matches this port
    if pid_info is not None:
        old_pid, old_port = pid_info
        if old_port == port and _is_pid_alive(old_pid):
            # Confirm via HTTP that it's really our server
            if _probe_our_server(host, port, project_root):
                logger.info(
                    "Port %d held by our old process (PID %d) — "
                    "sending SIGTERM for takeover",
                    port, old_pid,
                )
                try:
                    os.kill(old_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass  # Already gone

                # Wait for port to free up (up to 5 seconds)
                for _ in range(50):
                    time.sleep(0.1)
                    if _is_port_free(host, port):
                        logger.info("Port %d freed after takeover", port)
                        return True

                logger.warning(
                    "Port %d still occupied after SIGTERM to PID %d",
                    port, old_pid,
                )
                return False

        # PID file exists but PID is dead — stale file
        if not _is_pid_alive(old_pid):
            logger.debug("Stale PID file (PID %d dead), clearing", old_pid)
            clear_pid_file(project_root)

    # No PID file, but maybe there's a server we can probe
    if _probe_our_server(host, port, project_root):
        logger.info(
            "Port %d held by our server (no PID file) — cannot takeover safely",
            port,
        )
        # We can detect it's ours but don't have the PID to kill.
        # Don't take over blindly — fall to next port.

    return False




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

    logger.info("Scheduling restart (exit code %d)", _RESTART_EXIT_CODE)

    # Set the restart flag so the signal handler knows to exit with 42
    global _restart_requested
    _restart_requested = True

    # Schedule a SIGTERM to ourselves — this triggers the graceful
    # shutdown handler which will exit with code 42 (not 0).
    # The delay gives Flask time to send the HTTP response.
    import threading

    def _delayed_signal() -> None:
        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)

    t = threading.Thread(target=_delayed_signal, daemon=True)
    t.start()

    # Return a dict so the route can send a proper HTTP response
    return {"ok": True, "message": "Restarting..."}


# ── Signal handlers ─────────────────────────────────────────────

# Module-level flag: True when a restart has been requested via API
_restart_requested = False


def install_signal_handlers() -> None:
    """Register SIGTERM and SIGINT handlers for graceful shutdown.

    Should be called once during ``run_server()`` setup.
    Ensures vault auto-lock, SSE cleanup, and event bus flush
    happen before the process exits.

    If ``_restart_requested`` is set, exits with code 42 instead of 0
    so that ``manage.sh`` catches it and re-launches the server.
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

        # 3. Kill CDP bridge process (prevents zombie PowerShell on Windows)
        try:
            from src.ui.web import cdp_client
            if (
                hasattr(cdp_client, '_bridge_process')
                and cdp_client._bridge_process is not None
                and cdp_client._bridge_process.poll() is None
            ):
                cdp_client._bridge_process.kill()
                cdp_client._bridge_process = None
                cdp_client._bridge_ready = False
                logger.debug("CDP bridge killed on shutdown")
        except Exception:
            pass

        # 4. Stop WSL tunnel (prevents orphaned proxy on Windows)
        try:
            from src.core.services.chrome.wsl_tunnel import get_active_tunnel
            tunnel = get_active_tunnel()
            if tunnel and tunnel.is_running:
                tunnel.stop()
                logger.debug("WSL tunnel stopped on shutdown")
        except Exception:
            pass

        # 5. Clean up PID file
        try:
            from src.core.context import get_project_root as _get_root
            _root = _get_root()
            if _root:
                clear_pid_file(_root)
                logger.debug("PID file cleared on shutdown")
        except Exception:
            pass

        # Exit with 42 if restart was requested, 0 otherwise
        exit_code = _RESTART_EXIT_CODE if _restart_requested else 0
        logger.info(
            "Graceful shutdown complete — exiting with code %d%s",
            exit_code,
            " (restart)" if _restart_requested else "",
        )
        os._exit(exit_code)  # noqa: SLF001 — must bypass Flask's SystemExit catch

    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT, _graceful_shutdown)
    logger.debug("Signal handlers installed (SIGTERM, SIGINT)")
