"""
Chrome instance launcher — port allocation, lifecycle management, PID tracking.

Manages Chrome instances across environments:
- WSL→Windows: PowerShell interop (Start-Process) with curl.exe CDP bridge
- Native Linux: direct subprocess launch with Python socket/urllib checks

Handles launching Chrome, port allocation to avoid collisions, PID capture
for targeted kill, and CDP ready-state polling.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field

from src.core.services.chrome.detection import (
    find_chrome_linux,
    get_curl_exe,
    get_windows_user,
    has_display,
    is_docker,
    is_wsl,
)

logger = logging.getLogger(__name__)


# ── Exceptions ───────────────────────────────────────────────


class ChromeLaunchError(RuntimeError):
    """Base error for Chrome launch failures."""

    def __init__(self, message: str, *, remediation: dict | None = None):
        super().__init__(message)
        self.remediation = remediation or {}


class ChromeNotInstalled(ChromeLaunchError):
    """Chrome binary not found on this system."""

    def __init__(self, *, install_plan: dict | None = None):
        super().__init__(
            "Chrome is not installed. Install Google Chrome or Chromium.",
            remediation={
                "type": "tool_missing",
                "tool": "google-chrome",
                "install_plan": install_plan,
                "suggestion": (
                    "Install via: sudo apt install google-chrome-stable "
                    "or use the Audit → Tool Install panel."
                ),
            },
        )
        self.install_plan = install_plan


class ChromeNoDisplay(ChromeLaunchError):
    """No graphical display available for headed Chrome."""

    def __init__(self) -> None:
        super().__init__(
            "No display available. Use headless=True or configure a display.",
            remediation={
                "type": "missing_resource",
                "resource": "display",
                "suggestions": [
                    "Use headless mode (config.headless=True)",
                    "Install xvfb: sudo apt install xvfb",
                    "Run with: xvfb-run <command>",
                    "Set DISPLAY environment variable",
                ],
            },
        )


class ChromeStartupFailed(ChromeLaunchError):
    """Chrome process started but exited or CDP never responded."""

    def __init__(
        self, message: str, *, stderr: str = "", exit_code: int = 0,
    ):
        super().__init__(message)
        self.stderr = stderr
        self.exit_code = exit_code


# ── Data Models ──────────────────────────────────────────────


@dataclass
class ChromeLaunchConfig:
    """Configuration for launching a Chrome instance."""

    port: int = 0
    # 0 = auto-allocate via find_free_debug_port()
    # >0 = use this specific port (fail if busy)

    profile_type: str = "temp"
    # "temp" = fresh debug dir, no sign-in (GoogleAccountless)
    # "email" = fresh debug dir, but read user's email for sign-in auto-fill

    email: str = ""
    # When profile_type="email", the email to pre-fill in the sign-in flow.
    # If empty and profile_type="email", caller must provide it
    # (from read_chrome_profiles + user selection).

    headless: bool = False
    # True = add --headless flag. Required when WSL has no X11/display.

    kill_existing: bool = False
    # True = taskkill /F /IM chrome.exe before launching (restart mode).
    # False = launch alongside existing Chrome (multi-instance mode).

    landing_url: str = ""
    # URL to open on launch. When email is provided, the launcher appends
    # #chrome-signin&email=<email> for auto-fill.
    # When empty, Chrome opens its default new tab page.

    no_first_run: bool = True
    # True = add --no-first-run flag (skip Chrome welcome wizard).

    chrome_exe: str = ""
    # Override Chrome executable path. Empty = default:
    # "C:\Program Files\Google\Chrome\Application\chrome.exe"


@dataclass
class ChromeInstance:
    """A running Chrome instance managed by the launcher."""

    pid: int = 0
    # Windows PID of the Chrome browser process.
    # Used for targeted kill (taskkill /F /PID <pid>).

    port: int = 0
    # Debug port this instance is listening on.

    profile_dir: str = ""
    # Windows path to the --user-data-dir used.
    # e.g. "C:\Users\Jean\AppData\Local\Google\ChromeDebug-9223"

    headless: bool = False
    # Whether this instance was launched in headless mode.

    endpoint: str = ""
    # Full CDP endpoint URL, e.g. "http://localhost:9223"
    # This is what callers use to construct ws:// URLs for CdpSession.

    email: str = ""
    # The email used for sign-in auto-fill, if applicable.
    # Empty for temp/GoogleAccountless instances.

    started_at: str = ""
    # ISO timestamp of launch.

    ready: bool = False
    # True when CDP endpoint responded to /json/version.
    # Set by _wait_for_ready().


# ── Port Checking ────────────────────────────────────────────



def _port_in_use(port: int) -> bool:
    """Check if Chrome is listening on a TCP port.

    In WSL2, the ``netsh portproxy`` rules forward 9222-9232 on
    the host IP to Windows localhost.  The proxy accepts TCP on
    ALL forwarded ports, but only Chrome actually responds to HTTP.
    Chrome responds in ~10-20ms; free ports hang until timeout.
    A 100ms timeout catches every real Chrome while failing fast
    on free ports.
    """
    import urllib.request

    from src.core.services.chrome.detection import is_wsl
    if is_wsl():
        from src.core.services.wsl_transport.network import resolve_host_ip
        host_ip = resolve_host_ip()
        if not host_ip:
            from src.core.services.wsl_transport.curl_bridge import curl_get
            return curl_get(
                f"http://localhost:{port}/json/version", timeout=1.0,
            ) is not None
        try:
            urllib.request.urlopen(
                f"http://{host_ip}:{port}/json/version",
                timeout=0.05,  # Chrome responds in ~5-20ms via portproxy
            )
            return True
        except Exception:
            return False
    else:
        try:
            urllib.request.urlopen(
                f"http://localhost:{port}/json/version",
                timeout=0.5,
            )
            return True
        except Exception:
            return False


def _cdp_responding(port: int) -> bool:
    """Check if a CDP endpoint is responding on the given port.

    Uses the host IP direct channel (~10-20ms via portproxy).
    Falls back to curl.exe if host IP is unavailable.
    """
    from src.core.services.chrome.detection import is_wsl
    if is_wsl():
        from src.core.services.wsl_transport.network import resolve_host_ip
        host_ip = resolve_host_ip()
        if host_ip:
            import urllib.request
            try:
                urllib.request.urlopen(
                    f"http://{host_ip}:{port}/json/version",
                    timeout=0.05,
                )
                return True
            except Exception:
                return False
        # Fallback
        from src.core.services.wsl_transport.curl_bridge import curl_get
        return curl_get(
            f"http://localhost:{port}/json/version", timeout=1.0,
        ) is not None
    else:
        from src.ui.web.cdp_client import is_available
        return is_available(port=port)


def _get_browser_id(port: int) -> str | None:
    """Get the unique browser identity on a port.

    Returns the ``webSocketDebuggerUrl`` from ``/json/version``
    which contains a UUID unique to each Chrome instance.
    Uses host IP direct channel (~10-20ms). Returns None if
    nothing responds.
    """
    import json as _json
    from src.core.services.chrome.detection import is_wsl

    if is_wsl():
        from src.core.services.wsl_transport.network import resolve_host_ip
        host_ip = resolve_host_ip()
        if host_ip:
            import urllib.request
            try:
                r = urllib.request.urlopen(
                    f"http://{host_ip}:{port}/json/version",
                    timeout=0.05,
                )
                data = _json.loads(r.read().decode())
                return data.get("webSocketDebuggerUrl", "")
            except Exception:
                return None
        # Fallback to curl
        from src.core.services.wsl_transport.curl_bridge import curl_get
        raw = curl_get(
            f"http://localhost:{port}/json/version", timeout=1.0,
        )
        if raw:
            try:
                data = _json.loads(raw)
                return data.get("webSocketDebuggerUrl", "")
            except (ValueError, AttributeError):
                return raw[:80]
        return None
    else:
        from src.ui.web.cdp_client import get_version
        info = get_version(port=port)
        if info:
            return info.get("webSocketDebuggerUrl", "")
        return None


# ── Chrome Launcher ──────────────────────────────────────────


_DEFAULT_CHROME_EXE_WIN = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe"
)

_PORT_RANGE_START = 9222 # 9222 = user's main browser, never for plans TODO: Fix, but test for now
_PORT_RANGE_SIZE = 10
_READY_TIMEOUT = 15       # seconds to wait for CDP after launch
_READY_POLL_INTERVAL = 0.2  # 200ms poll (Chrome starts in <1s)


class ChromeLauncher:
    """Manages Chrome instances in WSL→Windows environment.

    Thread-safe. Tracks all launched instances. Handles port allocation,
    PID capture, CDP ready-state polling, and targeted/bulk kill.
    """

    def __init__(self) -> None:
        self._instances: dict[int, ChromeInstance] = {}  # port → instance
        self._reserved_ports: set[int] = set()
        self._lock = threading.Lock()

    # ── Port Allocation ──────────────────────────────────────

    def find_free_debug_port(
        self,
        start: int = _PORT_RANGE_START,
        max_tries: int = _PORT_RANGE_SIZE,
    ) -> int:
        """Find and reserve a free TCP port for Chrome debugging.

        Scans ports starting from ``start``. Checks against:
        1. Already-reserved ports (claimed but not yet launched)
        2. Already-tracked instances
        3. Actual TCP listeners (via curl.exe in WSL2)

        Returns the port number. The port is reserved until
        ``launch()`` registers the instance (or ``_release_port()``
        is called on failure).

        Raises RuntimeError if no port is free in the range.
        """
        with self._lock:
            for port in range(start, start + max_tries):
                if port in self._reserved_ports:
                    continue
                if port in self._instances:
                    continue
                if _port_in_use(port):
                    continue
                self._reserved_ports.add(port)
                return port
        raise RuntimeError(
            f"No free debug port in range {start}–{start + max_tries - 1}"
        )

    def _release_port(self, port: int) -> None:
        """Release a reserved port (called on launch failure)."""
        with self._lock:
            self._reserved_ports.discard(port)

    # ── Launch ───────────────────────────────────────────────

    def launch(self, config: ChromeLaunchConfig) -> ChromeInstance:
        """Launch a Chrome instance.

        Environment-aware:
        - WSL: PowerShell interop (Start-Process) with PID capture via stdout
        - Native Linux: direct subprocess.Popen with PID from Popen.pid

        Flow:
        1. Allocates a debug port (or uses the one specified)
        2. Optionally kills all existing Chrome (restart mode)
        3. Launches Chrome (env-specific method)
        4. Captures the Chrome PID
        5. Polls until CDP endpoint responds
        6. Returns the tracked ChromeInstance

        Raises:
            ChromeNotInstalled: Chrome binary not found.
            ChromeNoDisplay: No display and headless not set.
            ChromeStartupFailed: Chrome launched but crashed or CDP timeout.
            RuntimeError: Other launch failures.
        """
        # ── Step 1: Port ──
        if config.port > 0:
            # Explicit port — verify it's free
            with self._lock:
                if config.port in self._instances:
                    raise RuntimeError(
                        f"Port {config.port} already has a managed instance"
                    )
                if _port_in_use(config.port):
                    raise RuntimeError(
                        f"Port {config.port} is already in use"
                    )
                self._reserved_ports.add(config.port)
            port = config.port
        else:
            port = self.find_free_debug_port()

        try:
            # ── Step 2: Kill existing (restart mode) ──
            if config.kill_existing:
                self.kill_all()
                time.sleep(2)

            # ── Step 2b: Capture existing browser ID (hijack guard) ──
            # If something is already on this port, record its identity.
            # After launch, we verify the identity CHANGED — proving
            # our new Chrome actually bound the debug port.
            existing_browser_id = _get_browser_id(port)
            logger.info(
                "Hijack guard: existing_browser_id on port %d = %s",
                port, existing_browser_id,
            )

            # ── Step 3: Route to environment-specific launch ──
            if is_wsl():
                instance = self._launch_wsl(config, port)
            else:
                instance = self._launch_linux(config, port)

            # ── Step 4: Wait for CDP ready ──
            if self._wait_for_ready(instance):
                # ── Step 4b: Verify it's OUR Chrome, not an existing one ──
                if existing_browser_id:
                    new_browser_id = _get_browser_id(port)
                    logger.info(
                        "Hijack guard: new_browser_id on port %d = %s",
                        port, new_browser_id,
                    )
                    if new_browser_id == existing_browser_id:
                        raise ChromeStartupFailed(
                            f"Port {port} still has the same browser "
                            f"(id={existing_browser_id[:40]}…). "
                            f"New Chrome failed to bind the debug port. "
                            f"An existing Chrome is already using it."
                        )
                logger.info(
                    "Chrome instance ready: port=%d pid=%d endpoint=%s",
                    port, instance.pid, instance.endpoint,
                )
            else:
                logger.warning(
                    "Chrome launched (pid=%d port=%d) but CDP not responding "
                    "after %ds. Instance tracked but not ready.",
                    instance.pid, port, _READY_TIMEOUT,
                )

            # ── Step 5: Register ──
            with self._lock:
                self._reserved_ports.discard(port)
                self._instances[port] = instance

            return instance

        except Exception:
            self._release_port(port)
            raise

    # ── WSL→Windows Launch Path ──────────────────────────────

    def _launch_wsl(
        self, config: ChromeLaunchConfig, port: int,
    ) -> ChromeInstance:
        """Launch Chrome on Windows from WSL.

        Primary: direct .exe invocation via WSL interop (~50ms)
        Fallback: powershell.exe Start-Process (~3-4s cold start)
        """
        windows_user = get_windows_user()
        if not windows_user:
            raise RuntimeError("ChromeLauncher: could not detect Windows user")

        # Profile dir (Windows path)
        profile_dir = _make_instance_debug_dir_win(windows_user, port)

        # Landing URL
        landing_url = config.landing_url
        if config.email and landing_url:
            from urllib.parse import quote
            landing_url = (
                f"{landing_url}#chrome-signin&email={quote(config.email)}"
            )

        chrome_exe = config.chrome_exe or _DEFAULT_CHROME_EXE_WIN
        chrome_args = [
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
        ]
        if config.no_first_run:
            chrome_args.append("--no-first-run")
        if config.headless:
            chrome_args.append("--headless")
        if landing_url:
            chrome_args.append(landing_url)

        pid = 0

        # ── Primary: direct .exe via WSL interop (fast) ──
        # WSL can run Windows .exe files directly.  Convert the
        # Windows path to a WSL /mnt/c path and use Popen.
        wsl_chrome_path = chrome_exe.replace("\\", "/")
        if wsl_chrome_path[1] == ":":
            # C:\… → /mnt/c/…
            drive = wsl_chrome_path[0].lower()
            wsl_chrome_path = f"/mnt/{drive}{wsl_chrome_path[2:]}"

        if os.path.isfile(wsl_chrome_path):
            try:
                proc = subprocess.Popen(
                    [wsl_chrome_path] + chrome_args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                # The Popen PID is the WSL-side wrapper PID.
                # We need the Windows PID for kill management.
                # Query it via tasklist after a brief wait.
                time.sleep(0.3)
                try:
                    # Use wmic to find the chrome.exe with our specific
                    # debug port in its command line — this gives us the
                    # correct main browser PID, not a random subprocess.
                    r = subprocess.run(
                        [
                            "cmd.exe", "/C",
                            "wmic", "process", "where",
                            f"Name='chrome.exe' and CommandLine like '%--remote-debugging-port={port}%'",
                            "get", "ProcessId", "/FORMAT:LIST",
                        ],
                        capture_output=True, text=True, timeout=5,
                    )
                    for line in r.stdout.splitlines():
                        line = line.strip()
                        if line.startswith("ProcessId="):
                            try:
                                candidate = int(line.split("=", 1)[1])
                                if candidate > 0:
                                    pid = candidate
                                    break  # Take the first match
                            except (ValueError, IndexError):
                                pass
                except (subprocess.TimeoutExpired, OSError):
                    pass

                if pid > 0:
                    logger.info(
                        "Chrome launched directly (pid=%d port=%d)",
                        pid, port,
                    )
                else:
                    # Use the WSL wrapper PID as fallback
                    pid = proc.pid
                    logger.info(
                        "Chrome launched directly (wsl-pid=%d port=%d)",
                        pid, port,
                    )
            except (OSError, subprocess.SubprocessError) as exc:
                logger.debug(
                    "Direct exe launch failed: %s, falling back to PS", exc,
                )

        # ── Fallback: PowerShell (slow but reliable) ──
        if pid == 0:
            args_ps = ",".join(f"'{a}'" for a in chrome_args)
            ps_content = (
                f'$ErrorActionPreference = "Stop"\n'
                f'try {{\n'
                f'    $proc = Start-Process "{chrome_exe}" '
                f"-ArgumentList {args_ps} -PassThru\n"
                f'    Write-Host "PID:$($proc.Id)"\n'
                f'}} catch {{\n'
                f'    Write-Error $_.Exception.Message\n'
                f'    exit 1\n'
                f'}}\n'
            )

            tmp_dir = "/mnt/c/Windows/Temp"
            script_name = f"chrome_launch_{port}.ps1"
            script_path_wsl = f"{tmp_dir}/{script_name}"
            script_path_win = f"C:\\Windows\\Temp\\{script_name}"

            with open(script_path_wsl, "w", encoding="utf-8") as f:
                f.write(ps_content)

            r = subprocess.run(
                [
                    "powershell.exe", "-NoProfile",
                    "-ExecutionPolicy", "Bypass",
                    "-File", script_path_win,
                ],
                capture_output=True, text=True, timeout=15,
            )

            try:
                os.remove(script_path_wsl)
            except OSError:
                pass

            for line in r.stdout.splitlines():
                if line.startswith("PID:"):
                    try:
                        pid = int(line[4:].strip())
                    except ValueError:
                        pass
                    break

            if r.returncode != 0:
                raise ChromeStartupFailed(
                    f"PS1 launch failed (rc={r.returncode}): "
                    f"{r.stderr.strip()}",
                    stderr=r.stderr,
                    exit_code=r.returncode,
                )

        if pid == 0:
            logger.warning(
                "Chrome launched but PID not captured."
            )

        # Build instance
        from datetime import datetime, timezone
        return ChromeInstance(
            pid=pid,
            port=port,
            profile_dir=profile_dir,
            headless=config.headless,
            email=config.email,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

    # ── Native Linux Launch Path ─────────────────────────────

    def _launch_linux(
        self, config: ChromeLaunchConfig, port: int,
    ) -> ChromeInstance:
        """Launch Chrome directly on native Linux via subprocess.Popen.

        Detects Chrome binary, checks display availability, adds
        ``--no-sandbox`` in Docker, and captures PID from Popen.pid.

        Raises:
            ChromeNotInstalled: Chrome binary not found.
            ChromeNoDisplay: No display and headless not set.
            ChromeStartupFailed: Chrome process exited immediately.
        """
        # Find Chrome binary
        chrome_path = config.chrome_exe or find_chrome_linux()
        if not chrome_path:
            raise ChromeNotInstalled()

        # Display check (skip for headless)
        if not config.headless and not has_display():
            raise ChromeNoDisplay()

        # Profile dir (Linux path — use /tmp for isolation)
        from src.core.services.chrome.profiles import create_temp_profile_dir
        profile_dir = create_temp_profile_dir(port)

        # Chrome arguments
        chrome_args = [
            chrome_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
        ]
        if config.no_first_run:
            chrome_args.append("--no-first-run")
        if config.headless:
            chrome_args.append("--headless")
        if is_docker():
            # Chrome in Docker needs --no-sandbox due to seccomp
            chrome_args.append("--no-sandbox")
        if config.landing_url:
            landing_url = config.landing_url
            if config.email:
                from urllib.parse import quote
                landing_url = (
                    f"{landing_url}#chrome-signin&email={quote(config.email)}"
                )
            chrome_args.append(landing_url)

        # Launch Chrome — Popen (non-blocking, Chrome runs independently)
        try:
            proc = subprocess.Popen(
                chrome_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True,  # detach from parent process group
            )
        except FileNotFoundError:
            raise ChromeNotInstalled()
        except OSError as exc:
            raise ChromeStartupFailed(
                f"Failed to start Chrome: {exc}",
                exit_code=1,
            )

        # Give Chrome a moment to start (or crash)
        time.sleep(1)

        # Check if Chrome crashed immediately
        exit_code = proc.poll()
        if exit_code is not None:
            stderr = ""
            try:
                stderr = proc.stderr.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise ChromeStartupFailed(
                f"Chrome exited immediately (code={exit_code})",
                stderr=stderr,
                exit_code=exit_code,
            )

        pid = proc.pid
        logger.info(
            "Chrome launched on Linux: pid=%d port=%d binary=%s",
            pid, port, chrome_path,
        )

        # Build instance
        from datetime import datetime, timezone
        return ChromeInstance(
            pid=pid,
            port=port,
            profile_dir=profile_dir,
            headless=config.headless,
            email=config.email,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

    # ── Ready-State Polling ──────────────────────────────────

    def _wait_for_ready(
        self,
        instance: ChromeInstance,
        timeout: float = _READY_TIMEOUT,
        poll_interval: float = _READY_POLL_INTERVAL,
    ) -> bool:
        """Poll until CDP responds on the instance's port.

        Sets ``instance.endpoint`` and ``instance.ready`` on success.
        Returns True if ready, False if timeout.
        """
        deadline = time.time() + timeout

        while time.time() < deadline:
            if _cdp_responding(instance.port):
                instance.endpoint = f"http://localhost:{instance.port}"
                instance.ready = True
                return True
            time.sleep(poll_interval)

        return False

    # ── Kill ─────────────────────────────────────────────────

    def kill_instance(self, instance: ChromeInstance) -> bool:
        """Kill a specific Chrome instance by its PID.

        Environment-aware:
        - WSL: finds the chrome.exe by ``--remote-debugging-port``
          in command line (wmic), then ``taskkill.exe /F /T``.
          Falls back to stored PID.
        - Native Linux: ``os.kill(pid, SIGTERM)`` → ``SIGKILL`` fallback

        Removes the instance from tracking on success.
        """
        if not instance.pid:
            logger.warning("Cannot kill instance on port %d: no PID", instance.port)
            return False
        try:
            if is_wsl():
                # wmic can't see Chrome command lines (all empty),
                # so PID-based lookup doesn't work.  Use CDP
                # Browser.close to shut down the instance cleanly.
                killed = False
                try:
                    from src.ui.web.cdp_client import get_version, CdpSession

                    # Get browser WS URL via transport router
                    version = get_version(port=instance.port)
                    ws_url = (
                        version.get("webSocketDebuggerUrl", "")
                        if version else ""
                    )

                    if ws_url:
                        # Connect to browser WS and send Browser.close.
                        # Browser.close causes Chrome to drop the WS
                        # immediately, so send_command's recv() would
                        # throw.  Fire-and-forget via raw ws.send().
                        logger.info(
                            "Attempting CdpSession to browser WS: %s",
                            ws_url,
                        )
                        session = CdpSession(ws_url, connect_timeout=3)
                        if session.connected:
                            logger.info("Sending Browser.close...")
                            # Browser.close drops the WS immediately,
                            # so send_command's recv may fail — that's OK,
                            # the close command is delivered before the drop.
                            try:
                                session.send_command(
                                    "Browser.close", {},
                                )
                            except Exception:
                                pass  # expected — connection drops
                            logger.info("Browser.close sent OK")
                            killed = True
                            logger.info(
                                "Chrome closed via CDP Browser.close "
                                "on port %d",
                                instance.port,
                            )
                    else:
                        logger.warning(
                            "No webSocketDebuggerUrl in /json/version "
                            "on port %d", instance.port,
                        )
                except Exception as exc:
                    logger.warning(
                        "CDP Browser.close failed on port %d: %s",
                        instance.port, exc,
                    )

                # Fallback: taskkill with stored PID
                if not killed:
                    r = subprocess.run(
                        ["taskkill.exe", "/F", "/T", "/PID",
                         str(instance.pid)],
                        capture_output=True, text=True, timeout=10,
                    )
                    killed = r.returncode == 0
            else:
                # Native Linux: SIGTERM first, SIGKILL fallback
                try:
                    os.kill(instance.pid, signal.SIGTERM)
                    # Give it a moment to exit gracefully
                    time.sleep(0.5)
                    # Check if still running
                    os.kill(instance.pid, 0)
                    # Still alive — force kill
                    os.kill(instance.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # Already dead — success
                killed = True

            if killed:
                with self._lock:
                    self._instances.pop(instance.port, None)
                # Evict pooled CDP sessions for this port
                try:
                    from src.ui.web.cdp_client import evict_port
                    evict_port(instance.port)
                except Exception:
                    pass  # Non-critical cleanup
                logger.info(
                    "Killed Chrome instance PID %d on port %d",
                    instance.pid, instance.port,
                )
            else:
                logger.warning(
                    "Kill PID %d failed on port %d",
                    instance.pid, instance.port,
                )
            return killed
        except Exception as exc:
            logger.warning(
                "Failed to kill Chrome PID %d: %s", instance.pid, exc,
            )
            return False

    def kill_all(self) -> bool:
        """Kill ALL Chrome processes.

        Environment-aware:
        - WSL: ``taskkill.exe /F /IM chrome.exe``
        - Native Linux: ``pkill -9 -f`` for each known Chrome binary name

        Clears all tracked instances and reserved ports.
        """
        try:
            if is_wsl():
                r = subprocess.run(
                    ["taskkill.exe", "/F", "/IM", "chrome.exe"],
                    capture_output=True, text=True, timeout=10,
                )
                killed = r.returncode == 0 or "not found" in r.stderr.lower()
            else:
                # Native Linux: try pkill for each known Chrome name
                killed = False
                for name in ("google-chrome-stable", "google-chrome",
                             "chromium-browser", "chromium"):
                    r = subprocess.run(
                        ["pkill", "-9", "-f", name],
                        capture_output=True, text=True, timeout=10,
                    )
                    if r.returncode == 0:
                        killed = True

            with self._lock:
                self._instances.clear()
                self._reserved_ports.clear()
            if killed:
                logger.info("All Chrome processes terminated")
            return killed
        except Exception as exc:
            logger.warning("Failed to kill all Chrome: %s", exc)
            return False

    # ── Query ────────────────────────────────────────────────

    def list_instances(self) -> list[ChromeInstance]:
        """Return all tracked Chrome instances."""
        with self._lock:
            return list(self._instances.values())

    def get_instance(self, port: int) -> ChromeInstance | None:
        """Return the instance on a given port, or None."""
        with self._lock:
            return self._instances.get(port)

    # ── Cleanup ──────────────────────────────────────────────

    def cleanup(self) -> None:
        """Kill all managed instances. Call on server shutdown."""
        instances = self.list_instances()
        for inst in instances:
            self.kill_instance(inst)
        with self._lock:
            self._instances.clear()
            self._reserved_ports.clear()
        logger.info("ChromeLauncher cleanup complete")


# ── Helpers ──────────────────────────────────────────────────


def _make_instance_debug_dir_win(windows_user: str, port: int) -> str:
    """Return a per-instance debug dir path (Windows format).

    Each port gets its own directory to avoid profile locking conflicts
    between simultaneous Chrome instances.
    """
    return (
        f"C:\\Users\\{windows_user}\\AppData\\Local\\Google"
        f"\\ChromeDebug-{port}"
    )


# ── Availability Gate ────────────────────────────────────────


def require_chrome() -> dict:
    """Check if Chrome is available in the current environment.

    Returns a structured dict that callers can use for:
    - Gating features that need Chrome
    - Building notifications with install guidance
    - Passing install_plan to the tool install system

    Returns::

        # Chrome found:
        {
            "available": True,
            "binary": "/usr/bin/google-chrome-stable",
            "version": "145.0.7632.109",       # or None
            "environment": "linux",             # or "wsl"
        }

        # Chrome NOT found:
        {
            "available": False,
            "binary": None,
            "version": None,
            "environment": "linux",
            "install_plan": {
                "tool": "google-chrome",
                "steps": [...],
                "can_auto_install": True,
            },
        }
    """
    from src.core.services.chrome.detection import (
        find_chrome_linux,
        get_chrome_version_linux,
        is_wsl,
    )

    if is_wsl():
        # In WSL, Chrome runs on Windows — check for chrome.exe
        import shutil
        chrome_exe = shutil.which("chrome.exe")
        if chrome_exe:
            return {
                "available": True,
                "binary": chrome_exe,
                "version": None,  # version detection is Windows-side
                "environment": "wsl",
            }
        # Fallback: check the default Windows path
        import os
        default_win = "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
        if os.path.exists(default_win):
            return {
                "available": True,
                "binary": default_win,
                "version": None,
                "environment": "wsl",
            }
        return {
            "available": False,
            "binary": None,
            "version": None,
            "environment": "wsl",
            "install_plan": {
                "tool": "google-chrome",
                "steps": [
                    {
                        "label": "Install Google Chrome on Windows",
                        "command": "Download from https://www.google.com/chrome/",
                        "type": "manual",
                    },
                ],
                "can_auto_install": False,
            },
        }

    # Native Linux
    chrome_path = find_chrome_linux()
    if chrome_path:
        version = get_chrome_version_linux(chrome_path)
        return {
            "available": True,
            "binary": chrome_path,
            "version": version,
            "environment": "linux",
        }

    # Not found — build install_plan from recipe
    install_plan = _build_chrome_install_plan()
    return {
        "available": False,
        "binary": None,
        "version": None,
        "environment": "linux",
        "install_plan": install_plan,
    }


def _build_chrome_install_plan() -> dict:
    """Build an install_plan dict for Chrome on Linux.

    Tries to look up the recipe from the tool_install data layer.
    Falls back to a hardcoded plan if the recipe is unavailable.
    """
    try:
        from src.core.services.tool_install.data.recipes import TOOL_RECIPES
        recipe = TOOL_RECIPES.get("google-chrome", {})
        if recipe:
            # Detect which package manager is available
            import shutil
            available_methods = []
            for method in recipe.get("prefer", []):
                if shutil.which(method):
                    available_methods.append(method)

            # Pick the best method
            if available_methods:
                method = available_methods[0]
                install_cmd = recipe["install"].get(method, [])
            else:
                install_cmd = recipe["install"].get("_default", [])
                method = "_default"

            return {
                "tool": "google-chrome",
                "steps": [
                    {
                        "label": f"Install Google Chrome via {method}",
                        "command": " ".join(install_cmd) if isinstance(install_cmd, list) else str(install_cmd),
                        "type": method,
                        "needs_sudo": recipe.get("needs_sudo", {}).get(method, True),
                    },
                ],
                "can_auto_install": True,
            }
    except ImportError:
        pass

    # Fallback
    return {
        "tool": "google-chrome",
        "steps": [
            {
                "label": "Install Google Chrome",
                "command": (
                    "wget -q -O /tmp/gc.deb "
                    "https://dl.google.com/linux/direct/"
                    "google-chrome-stable_current_amd64.deb "
                    "&& sudo dpkg -i /tmp/gc.deb "
                    "&& sudo apt-get -f install -y"
                ),
                "type": "manual",
            },
        ],
        "can_auto_install": False,
    }


# ── Module-level Singleton ───────────────────────────────────


_launcher: ChromeLauncher | None = None


def get_launcher() -> ChromeLauncher:
    """Get or create the module-level launcher singleton."""
    global _launcher
    if _launcher is None:
        _launcher = ChromeLauncher()
    return _launcher
