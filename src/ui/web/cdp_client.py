"""
Chrome DevTools Protocol (CDP) client for tab focus.

Minimal client that talks to Chrome's JSON debugging API to list
and activate browser tabs.  Used by the Tab Mesh system to bring
a target tab to the foreground — something that browser-page JS
cannot do due to focus-stealing restrictions.

Chrome must be launched with ``--remote-debugging-port=9222`` and
(on Chrome 136+) ``--user-data-dir=...`` for the endpoint to be
available.

All functions are safe to call when CDP is unreachable — they
return ``None`` or empty results without raising.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
import urllib.error
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Default endpoint ──────────────────────────────────────────

_DEFAULT_PORT = 9222
_endpoint: str | None = None


def _base_url() -> str:
    """Return the current CDP base URL."""
    return _endpoint or f"http://localhost:{_DEFAULT_PORT}"


def set_endpoint(host: str, port: int = _DEFAULT_PORT) -> None:
    """Override the CDP endpoint (e.g. when Windows host IP differs)."""
    global _endpoint
    _endpoint = f"http://{host}:{port}"
    logger.info("CDP endpoint set to %s", _endpoint)



# ── Low-level HTTP ────────────────────────────────────────────

def _get_json(
    path: str,
    timeout: float = 1.0,
    *,
    port: int | None = None,
) -> dict | list | None:
    """GET a Chrome JSON API endpoint.  Returns parsed JSON or None.

    Delegates to the transport router which handles channel ranking
    and fallback (tunnel → direct → curl) automatically.

    Args:
        port: When provided, target ``http://localhost:{port}`` instead
              of the global endpoint.  Used for multi-instance support.
    """
    from src.core.services.wsl_transport.router import get_router

    target_port = port if port is not None else _DEFAULT_PORT
    raw = get_router().http_get(target_port, path, timeout)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return None


def _get_raw(
    path: str,
    timeout: float = 1.0,
    *,
    port: int | None = None,
) -> str | None:
    """GET a Chrome debugging endpoint, return raw text or None.

    Delegates to the transport router which handles channel ranking
    and fallback automatically.

    Args:
        port: When provided, target ``http://localhost:{port}`` instead
              of the global endpoint.
    """
    from src.core.services.wsl_transport.router import get_router

    target_port = port if port is not None else _DEFAULT_PORT
    return get_router().http_get(target_port, path, timeout)


# ── Public API ────────────────────────────────────────────────


def is_available(*, port: int | None = None) -> bool:
    """Check if Chrome's debugging endpoint is reachable.

    Args:
        port: Target a specific Chrome instance instead of the global one.
    """
    version = _get_json("/json/version", timeout=0.5, port=port)
    return version is not None


def get_version(*, port: int | None = None) -> dict | None:
    """Return Chrome version info, or None if unreachable.

    Args:
        port: Target a specific Chrome instance instead of the global one.

    Example response::

        {
            "Browser": "Chrome/138.0.6423.82",
            "Protocol-Version": "1.3",
            "User-Agent": "...",
            "V8-Version": "...",
            "WebKit-Version": "..."
        }
    """
    return _get_json("/json/version", port=port)


def get_targets(*, port: int | None = None) -> list[dict]:
    """Return all open browser targets (tabs, extensions, etc).

    Args:
        port: Target a specific Chrome instance instead of the global one.

    Each target is a dict with at least::

        {
            "id": "ABC123...",
            "type": "page",
            "title": "DevOps Control Plane",
            "url": "http://localhost:8000/#content",
            "description": "",
            "devtoolsFrontendUrl": "...",
            "webSocketDebuggerUrl": "ws://..."
        }

    Returns an empty list if CDP is unreachable.
    """
    result = _get_json("/json", port=port)
    if isinstance(result, list):
        return result
    return []


def find_target_by_url(
    targets: list[dict],
    url_pattern: str,
    *,
    exclude_url: str | None = None,
) -> dict | None:
    """Find a target whose URL contains *url_pattern*.

    Args:
        targets: List from :func:`get_targets`.
        url_pattern: Substring to match in the target URL.
        exclude_url: Optional URL to exclude (e.g. the requesting tab).

    Returns:
        The first matching target dict, or None.
    """
    for target in targets:
        if target.get("type") != "page":
            continue
        url = target.get("url", "")
        # Skip DevTools windows — they show as type "page" but are not real tabs
        if url.startswith("devtools://") or url.startswith("chrome-devtools://"):
            continue
        if url_pattern not in url:
            continue
        if exclude_url and exclude_url in url:
            continue
        return target
    return None


def activate_target(target_id: str, *, port: int | None = None) -> bool:
    """Bring a tab to the foreground by its target ID.

    Uses Chrome's ``/json/activate/{id}`` endpoint.

    Args:
        port: Target a specific Chrome instance instead of the global one.

    Returns:
        True if activation succeeded, False otherwise.
    """
    raw = _get_raw(f"/json/activate/{target_id}", timeout=1.0, port=port)
    if raw is not None:
        logger.info("CDP activated target: %s", target_id)
        return True
    logger.warning("CDP failed to activate target: %s", target_id)
    return False


def create_tab(url: str, *, port: int | None = None) -> dict | None:
    """Open a new browser tab via CDP.

    Uses the ``PUT /json/new?url`` endpoint (PUT required by Chrome).
    Delegates to the transport router for channel selection.

    Args:
        port: Target a specific Chrome instance instead of the global one.

    Returns:
        The target dict for the new tab, or None on failure.
    """
    from urllib.parse import quote
    from src.core.services.wsl_transport.router import get_router

    target_port = port if port is not None else _DEFAULT_PORT
    path = f"/json/new?{quote(url, safe='/:?=&%')}"
    raw = get_router().http_put(target_port, path, timeout=2.0)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return None

# ── Session Pool ──────────────────────────────────────────────


import threading as _threading
import time as _time


class _PoolEntry:
    """Wrapper tracking last-used time for a pooled CdpSession."""

    __slots__ = ("session", "last_used")

    def __init__(self, session: "CdpSession") -> None:
        self.session = session
        self.last_used = _time.monotonic()

    def touch(self) -> None:
        self.last_used = _time.monotonic()


class _SessionPool:
    """Thread-safe pool of persistent CdpSession instances.

    Keyed by ``(ws_url, thread_id)``.  Each thread gets its own
    session to the same target — no cross-thread sharing of
    WebSocket state.

    Idle sessions (> ``MAX_IDLE`` seconds) are reaped automatically
    on ``get()`` calls.
    """

    MAX_IDLE = 60  # seconds

    def __init__(self) -> None:
        self._pool: dict[tuple[str, int], _PoolEntry] = {}
        self._lock = _threading.Lock()

    def get(self, ws_url: str) -> "CdpSession | None":
        """Return a pooled session for this URL + current thread.

        Returns None if no pooled session exists or if it's no longer
        connected.  Reaps stale sessions opportunistically.
        """
        key = (ws_url, _threading.get_ident())
        with self._lock:
            self._reap_stale_locked()
            entry = self._pool.get(key)
            if entry is None:
                return None
            if not entry.session.connected:
                # Dead session — remove it
                del self._pool[key]
                return None
            entry.touch()
            return entry.session

    def put(self, ws_url: str, session: "CdpSession") -> None:
        """Pool a connected session for reuse."""
        key = (ws_url, _threading.get_ident())
        with self._lock:
            # Close any existing session for this slot
            old = self._pool.get(key)
            if old is not None and old.session is not session:
                try:
                    old.session.close()
                except Exception:
                    pass
            self._pool[key] = _PoolEntry(session)

    def evict_port(self, port: int) -> None:
        """Close and remove all sessions whose URL contains ``:port/``.

        Called when Chrome is killed on that port — all sessions are
        now dead.
        """
        port_fragment = f":{port}/"
        with self._lock:
            to_remove = [
                key for key in self._pool
                if port_fragment in key[0]
            ]
            for key in to_remove:
                entry = self._pool.pop(key)
                try:
                    entry.session.close()
                except Exception:
                    pass

    def _reap_stale_locked(self) -> None:
        """Remove sessions idle > MAX_IDLE (caller holds lock)."""
        now = _time.monotonic()
        stale = [
            key for key, entry in self._pool.items()
            if (now - entry.last_used) > self.MAX_IDLE
        ]
        for key in stale:
            entry = self._pool.pop(key)
            try:
                entry.session.close()
            except Exception:
                pass


# Module-level singleton
_session_pool = _SessionPool()


def evict_port(port: int) -> None:
    """Evict all pooled sessions for a port and reset router state.

    Call this when Chrome is killed on that port.
    """
    _session_pool.evict_port(port)
    from src.core.services.wsl_transport.router import get_router
    get_router().evict(port)


# ── Boot / warm ───────────────────────────────────────────────


def warm(port: int = _DEFAULT_PORT) -> dict:
    """Warm the CDP infrastructure.

    Called at server startup or when the user opens the CDP test
    panel.  Performs adaptive setup based on the detected environment:

    1. Initializes the transport router (environment detection).
    2. Probes all channels for ``port`` (native, tunnel, direct, curl).
    3. Checks saved channel state for auto-restart or IP change.
    4. If WSL2 NAT mode and no fast channel → creates notification.
    5. Only warms the PS bridge if no fast WS-capable channel
       is available after probing.

    Returns:
        Status dict suitable for JSON response to the frontend.
    """
    from src.core.services.wsl_transport.router import get_router

    router = get_router()

    # Probe channels for this port
    probe_results = router.probe(port)

    # ── Channel lifecycle: auto-restart proxy / detect IP change ──
    try:
        from flask import current_app
        project_root = Path(current_app.config["PROJECT_ROOT"])
        _warm_channel_lifecycle(router, port, project_root)
    except Exception as exc:
        logger.debug("Channel lifecycle check failed: %s", exc)

    # If WSL2 NAT mode and no fast channel, notify the user
    if router.needs_tunnel(port):
        logger.info(
            "No fast channel for port %d — creating setup notification",
            port,
        )
        try:
            from flask import current_app
            from src.core.services.notifications import create_notification
            project_root = Path(current_app.config["PROJECT_ROOT"])
            create_notification(
                project_root,
                notif_type="wsl_channel_setup",
                title="CDP Channel: Port Forwarding Needed",
                message=(
                    "No fast channel to Chrome detected. The system is "
                    "using the curl.exe fallback (~260ms/call). Set up "
                    "port forwarding for fast direct access (~5ms)."
                ),
                meta={
                    "action_tab": "wsl-channel",
                    "action_hash": "#wsl-channel",
                },
                dedup=True,
            )
        except Exception as exc:
            logger.debug("Could not create setup notification: %s", exc)

    # Only warm PS bridge if we still have no fast WS channel
    bridge_st = bridge_status()
    if not router.has_fast_channel(port):
        logger.info("No fast WS channel — warming PS bridge")
        warm_bridge()
        bridge_st = bridge_status()
    else:
        logger.info("Fast channel available — skipping PS bridge warm")
        bridge_st = {"needed": False, "ready": False, "warming": False}

    return {
        "ok": True,
        **router.status(),
        "bridge": bridge_st,
        "pool_size": len(_session_pool._pool),
    }


def _warm_channel_lifecycle(
    router, port: int, project_root: Path,
) -> None:
    """Handle channel auto-restart and IP change detection.

    Reads ``.state/wsl_channel.json`` (saved by ``wsl_start_tunnel``
    route) and:

    1. If stored IP ≠ current IP → netsh rules are orphaned →
       create notification for user to re-run setup.
    2. If stored method is ``python_proxy`` and TCP proxy is dead
       but direct channel works (same IP, rules persist) →
       auto-restart the proxy silently for resilience.
    """
    import json as _json
    from src.core.services.wsl_transport.network import resolve_host_ip

    state_file = project_root / ".state" / "wsl_channel.json"
    if not state_file.exists():
        return

    try:
        state = _json.loads(state_file.read_text())
    except (ValueError, OSError):
        return

    stored_method = state.get("method")
    stored_host = state.get("target_host")
    stored_port = state.get("port", 9222)

    if not stored_host:
        return

    current_ip = resolve_host_ip()
    if not current_ip:
        return

    # ── IP changed → netsh rules are orphaned ──
    if stored_host != current_ip:
        logger.warning(
            "WSL host IP changed: %s → %s — netsh portproxy rules are orphaned",
            stored_host, current_ip,
        )
        from src.core.services.notifications import create_notification
        create_notification(
            project_root,
            notif_type="wsl_ip_changed",
            title="CDP Channel: Host IP Changed",
            message=(
                f"WSL host IP changed from {stored_host} to {current_ip}. "
                "Port forwarding rules need updating."
            ),
            meta={
                "action_tab": "wsl-channel",
                "action_hash": "#wsl-channel",
                "old_ip": stored_host,
                "new_ip": current_ip,
            },
            dedup=True,
        )
        # Update stored IP so we don't re-notify every warm()
        try:
            state["target_host"] = current_ip
            state_file.write_text(_json.dumps(state, indent=2))
        except OSError:
            pass
        return

    # ── Same IP, auto-restart ephemeral tunnel if needed ──
    # All of python_proxy, socat, ssh are ephemeral (die with app).
    # netsh creates persistent OS-level rules and needs no restart.
    _EPHEMERAL_METHODS = {"python_proxy", "socat", "ssh"}

    if stored_method in _EPHEMERAL_METHODS:
        from src.core.services.wsl_transport.tunnel_backends import (
            get_active_tunnel, start_tunnel,
        )
        tunnel = get_active_tunnel()
        if tunnel and tunnel.is_running:
            return  # tunnel is alive, nothing to do

        logger.info(
            "Auto-restarting %s tunnel (was dead after app restart)",
            stored_method,
        )
        new_tunnel = start_tunnel(
            local_port=stored_port,
            target_host=stored_host,
            method=stored_method,
        )
        if new_tunnel:
            logger.info(
                "%s tunnel auto-restarted on port %d",
                stored_method, stored_port,
            )
            # Re-probe to get updated rankings with tunnel channel
            router.evict(port)
            router.probe(port)
        else:
            logger.warning("%s tunnel auto-restart failed", stored_method)


# ── evaluate_js (pooled) ──────────────────────────────────────


def evaluate_js(
    ws_url: str,
    expression: str,
    timeout: float = 5.0,
    *,
    await_promise: bool = False,
) -> dict | None:
    """Execute JavaScript on a Chrome tab via CDP WebSocket.

    Connection strategy (in order of preference):

    1. **Pooled session** — reuse an existing CdpSession for this
       ws_url + thread.  Near-zero overhead (~5ms).

    2. **New CdpSession** — create via transport router (tunnel,
       direct, or native PyWebSocket).  Pools it for subsequent
       calls (~15ms first time).

    3. **PS one-shot fallback** — ``ps_evaluate()`` via PowerShell
       subprocess.  Always works on WSL2 (~200ms).

    Args:
        ws_url: WebSocket debugger URL from target's
                ``webSocketDebuggerUrl`` field.
        expression: JavaScript expression to evaluate.
        timeout: Max seconds to wait.
        await_promise: If True, CDP will await the Promise returned
                       by the expression before returning the value.

    Returns:
        The CDP response dict, or None on failure.
    """
    # 1. Try pooled session
    session = _session_pool.get(ws_url)
    if session is not None:
        result = session.evaluate(
            expression, timeout=timeout, await_promise=await_promise,
        )
        if result is not None:
            return result
        # Session died mid-use — fall through to create a new one

    # 2. Create new CdpSession (uses router for fast WS connect)
    session = CdpSession(ws_url, connect_timeout=min(timeout, 5.0))
    if session.connected:
        _session_pool.put(ws_url, session)
        return session.evaluate(
            expression, timeout=timeout, await_promise=await_promise,
        )

    # 3. Fallback: PS one-shot (always works on WSL2)
    from src.core.services.wsl_transport.ps_bridge import ps_evaluate
    return ps_evaluate(ws_url, expression, timeout, await_promise=await_promise)


# ── Persistent CDP session ────────────────────────────────────



# _PyWebSocket has moved to wsl_transport.websocket.PyWebSocket.
# This alias keeps all in-file callers working without change.
from src.core.services.wsl_transport.websocket import PyWebSocket as _PyWebSocket


# ── Pre-warmed PowerShell bridge (delegates to wsl_transport.ps_bridge) ──

# Bridge management has moved to wsl_transport.ps_bridge.
# These thin wrappers preserve the internal call sites.

from src.core.services.wsl_transport.ps_bridge import (
    warm_bridge,
    bridge_status,
    bridge_connect as _bridge_connect,
    bridge_disconnect as _bridge_disconnect,
    bridge_send as _bridge_send,
    cleanup_stale_bridge,
)



# ── CdpSession ─────────────────────────────────────────────────


class CdpSession:
    """Persistent CDP WebSocket session — one connection, many commands.

    Connection strategies (in order of preference):

    1. **Python socket** — instant (~50ms).  Works when Python can
       reach Chrome's debug port directly.

    2. **Pre-warmed PS bridge** — fast (~100ms).  A shared PowerShell
       process kept alive across sessions.  The ~3s PS startup cost
       is paid once at app boot, not per-replay.

    3. **Fresh PowerShell** — slow (~3s).  Last resort fallback when
       the bridge isn't available.

    Usage::

        with CdpSession(ws_url) as session:
            if session.connected:
                result = session.evaluate("document.title")
    """

    __slots__ = (
        "_ws", "_fresh_process", "_connected", "_cmd_id",
        "_ws_url", "_mode", "_script_path",
    )

    def __init__(self, ws_url: str, connect_timeout: float = 10.0):
        self._ws = None
        self._fresh_process = None
        self._connected = False
        self._cmd_id = 0
        self._ws_url = ws_url
        self._mode = ""
        self._script_path = None

        import time as _t
        _t0 = _t.monotonic()

        # ── Phase 1: Transport router (tunnel/direct/native) ───
        # The router probes all WS-capable channels, ranks them by
        # latency, and returns a connected PyWebSocket via the
        # fastest path.  Covers old strategies 0, 0b, and 1.
        from src.core.services.wsl_transport.router import get_router
        _t1 = _t.monotonic()
        ws = get_router().connect_ws(ws_url, timeout=connect_timeout)
        if ws:
            self._ws = ws
            self._mode = "python"
            self._connected = True
            logger.info(
                "CdpSession connected via router to %s (%.0fms)",
                ws_url, (_t.monotonic() - _t1) * 1000,
            )
            return

        logger.debug(
            "Router WS connect failed in %.0fms, trying bridge",
            (_t.monotonic() - _t1) * 1000,
        )

        # ── Phase 2: Pre-warmed bridge (fast) ─────────────────
        # PowerShell subprocess protocol — different interface than
        # PyWebSocket.  Uses stdin/stdout to send CDP commands.
        _t2 = _t.monotonic()
        if _bridge_connect(ws_url, timeout=connect_timeout):
            self._mode = "bridge"
            self._connected = True
            logger.info(
                "CdpSession connected via bridge to %s (%.0fms, total %.0fms)",
                ws_url, (_t.monotonic() - _t2) * 1000,
                (_t.monotonic() - _t0) * 1000,
            )
            return

        logger.debug(
            "Bridge connect failed in %.0fms",
            (_t.monotonic() - _t2) * 1000,
        )

        # ── Phase 3: Fresh PowerShell (slow, last resort) ─────
        _t3 = _t.monotonic()
        logger.debug("Bridge unavailable, trying fresh PowerShell")
        self._init_fresh_ps(ws_url, connect_timeout)
        logger.info(
            "CdpSession fresh PS connect took %.0fms (total %.0fms)",
            (_t.monotonic() - _t3) * 1000,
            (_t.monotonic() - _t0) * 1000,
        )

    def _init_fresh_ps(
        self, ws_url: str, connect_timeout: float,
    ) -> None:
        """Last resort: start a fresh PowerShell process (~3s)."""
        import subprocess
        import tempfile
        import os

        ws_url_safe = ws_url.replace("'", "''")
        ps_script = (
            "$ErrorActionPreference = 'Stop'\n"
            "$ws = New-Object System.Net.WebSockets.ClientWebSocket\n"
            "$cts = New-Object System.Threading.CancellationTokenSource\n"
            "try {\n"
            f"    $ws.ConnectAsync([Uri]'{ws_url_safe}', $cts.Token)"
            ".Wait()\n"
            "    [Console]::Out.WriteLine('CONNECTED')\n"
            "    [Console]::Out.Flush()\n"
            "    while ($true) {\n"
            "        $line = [Console]::In.ReadLine()\n"
            "        if ($line -eq $null -or $line -eq 'EXIT')"
            " { break }\n"
            "        $bytes = [Text.Encoding]::UTF8.GetBytes($line)\n"
            "        $seg = New-Object "
            "System.ArraySegment[byte](,$bytes)\n"
            "        $ws.SendAsync($seg, "
            "[System.Net.WebSockets.WebSocketMessageType]::Text, "
            "$true, $cts.Token).Wait()\n"
            "        $all = New-Object "
            "System.Collections.Generic.List[byte]\n"
            "        do {\n"
            "            $buf = New-Object byte[] 1048576\n"
            "            $rseg = New-Object "
            "System.ArraySegment[byte](,$buf)\n"
            "            $r = $ws.ReceiveAsync($rseg, $cts.Token)"
            ".Result\n"
            "            for ($i = 0; $i -lt $r.Count; $i++) "
            "{ $all.Add($buf[$i]) }\n"
            "        } while (-not $r.EndOfMessage)\n"
            "        $resp = [Text.Encoding]::UTF8.GetString("
            "$all.ToArray())\n"
            "        [Console]::Out.WriteLine($resp)\n"
            "        [Console]::Out.Flush()\n"
            "    }\n"
            "} catch {\n"
            "    [Console]::Error.WriteLine("
            "'SESSION_ERROR:' + $_.Exception.Message)\n"
            "} finally {\n"
            "    if ($ws.State -eq 'Open') {\n"
            "        try { $ws.CloseAsync("
            "[System.Net.WebSockets.WebSocketCloseStatus]"
            "::NormalClosure, '', $cts.Token).Wait() } catch {}\n"
            "    }\n"
            "    $ws.Dispose()\n"
            "}\n"
        )

        from src.core.services.wsl_transport.environment import get_environment
        _env = get_environment()
        win_temp = _env.win_temp_dir if _env.wsl2 else None
        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix=".ps1", prefix="cdp_sess_", dir=win_temp,
        )
        self._script_path = tmp_path
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(ps_script)

        if _env.wsl2:
            try:
                win_path = subprocess.run(
                    ["wslpath", "-w", tmp_path],
                    capture_output=True, text=True, timeout=3,
                ).stdout.strip()
            except (subprocess.TimeoutExpired, OSError):
                win_path = tmp_path
        else:
            win_path = tmp_path

        try:
            self._fresh_process = subprocess.Popen(
                [
                    "powershell.exe", "-NoProfile",
                    "-ExecutionPolicy", "Bypass",
                    "-File", win_path,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            connected = [False]

            def _wait():
                try:
                    line = self._fresh_process.stdout.readline().strip()
                    connected[0] = (line == "CONNECTED")
                except Exception:
                    pass

            t = _threading.Thread(target=_wait, daemon=True)
            t.start()
            t.join(timeout=connect_timeout)

            if connected[0]:
                self._mode = "fresh_ps"
                self._connected = True
                logger.info(
                    "CdpSession connected via fresh PS to %s", ws_url,
                )
            else:
                logger.warning("Fresh PS session failed to connect")
                self._fresh_process = None

        except Exception as exc:
            logger.warning("Fresh PS startup failed: %s", exc)
            self._fresh_process = None

    @property
    def connected(self) -> bool:
        """True if the session is alive."""
        if not self._connected:
            return False
        if self._mode == "python":
            return self._ws is not None
        if self._mode == "bridge":
            bs = bridge_status()
            return bs.get("ready", False)
        if self._mode == "fresh_ps":
            return (
                self._fresh_process is not None
                and self._fresh_process.poll() is None
            )
        return False

    def evaluate(
        self,
        expression: str,
        *,
        await_promise: bool = False,
        timeout: float = 10.0,
    ) -> dict | None:
        """Send a JS expression and get the CDP response."""
        if not self.connected:
            return None

        self._cmd_id += 1
        params: dict = {"expression": expression}
        if await_promise:
            params["awaitPromise"] = True

        cmd = json.dumps({
            "id": self._cmd_id,
            "method": "Runtime.evaluate",
            "params": params,
        })

        if self._mode == "python":
            return self._evaluate_python(cmd, timeout)
        if self._mode == "bridge":
            return _bridge_send(cmd, timeout)
        return self._evaluate_fresh_ps(cmd, timeout)

    def send_command(
        self,
        method: str,
        params: dict | None = None,
        *,
        timeout: float = 10.0,
    ) -> dict | None:
        """Send an arbitrary CDP command and return the response.

        Unlike :meth:`evaluate` (which hardcodes ``Runtime.evaluate``),
        this accepts any CDP domain method — e.g.
        ``Emulation.setFocusEmulationEnabled``,
        ``Page.setWebLifecycleState``.
        """
        if not self.connected:
            return None

        self._cmd_id += 1
        cmd = json.dumps({
            "id": self._cmd_id,
            "method": method,
            "params": params or {},
        })

        if self._mode == "python":
            return self._evaluate_python(cmd, timeout)
        if self._mode == "bridge":
            return _bridge_send(cmd, timeout)
        return self._evaluate_fresh_ps(cmd, timeout)

    def _evaluate_python(self, cmd: str, timeout: float) -> dict | None:
        """Send/receive via Python socket WebSocket."""
        old_timeout = self._ws._sock.gettimeout()
        self._ws._sock.settimeout(timeout)
        try:
            self._ws.send(cmd)
            resp = self._ws.recv()
            return json.loads(resp)
        except Exception as exc:
            logger.warning("CdpSession Python eval failed: %s", exc)
            self._connected = False
            return None
        finally:
            try:
                self._ws._sock.settimeout(old_timeout)
            except Exception:
                pass

    def _evaluate_fresh_ps(
        self, cmd: str, timeout: float,
    ) -> dict | None:
        """Send/receive via a fresh PowerShell process."""
        proc = self._fresh_process
        if not proc or proc.poll() is not None:
            return None

        try:
            proc.stdin.write(cmd + "\n")
            proc.stdin.flush()

            result_holder: list[dict | None] = [None]

            def _read():
                try:
                    line = proc.stdout.readline().strip()
                    if line:
                        result_holder[0] = json.loads(line)
                except Exception:
                    pass

            reader = _threading.Thread(target=_read, daemon=True)
            reader.start()
            reader.join(timeout=timeout)

            return result_holder[0]

        except Exception as exc:
            logger.warning("CdpSession fresh PS eval failed: %s", exc)
            self._connected = False
            return None

    def close(self):
        """Shut down the session."""
        import os

        if self._mode == "python" and self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

        if self._mode == "bridge":
            _bridge_disconnect()

        if self._mode == "fresh_ps" and self._fresh_process:
            if self._fresh_process.poll() is None:
                try:
                    self._fresh_process.stdin.write("EXIT\n")
                    self._fresh_process.stdin.flush()
                    self._fresh_process.wait(timeout=3.0)
                except Exception:
                    try:
                        self._fresh_process.kill()
                    except Exception:
                        pass
            self._fresh_process = None

        self._connected = False

        if self._script_path:
            try:
                os.unlink(self._script_path)
            except OSError:
                pass
            self._script_path = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        try:
            self.close()
        except (ImportError, TypeError):
            pass  # Python interpreter shutting down



# ── Auto-discovery for WSL ────────────────────────────────────


def try_discover_endpoint() -> bool:
    """Try to find a working CDP endpoint.

    Attempts multiple discovery methods in order of preference:
    1. localhost (works for native Linux / WSL2 mirrored networking)
    2. hostname.local via mDNS (recommended WSL2 direct channel)
    3. resolv.conf nameserver (works when WSL generates it)
    4. Default gateway IP (WSL2 NAT mode — most reliable fallback)

    Sets the endpoint internally if found.

    Returns:
        True if a working endpoint was discovered.
    """
    import subprocess

    # 1. Try localhost (works for WSL2 mirrored networking + native)
    if is_available():
        logger.info("CDP available at %s", _base_url())
        return True

    # 2. Try hostname.local via mDNS (recommended WSL2 direct channel)
    # This resolves the Windows host by name — faster and more stable
    # than IP-based methods. Requires Bonjour/mDNS on Windows.
    try:
        import socket
        r = subprocess.run(
            ["hostname"],
            capture_output=True, text=True, timeout=3,
        )
        hostname = r.stdout.strip()
        if hostname:
            fqdn = f"{hostname}.local"
            try:
                infos = socket.getaddrinfo(
                    fqdn, None, socket.AF_INET, socket.SOCK_STREAM,
                )
                if infos:
                    host_ip = infos[0][4][0]
                    set_endpoint(host_ip, _DEFAULT_PORT)
                    if is_available():
                        logger.info(
                            "CDP available at %s (%s):%s",
                            fqdn, host_ip, _DEFAULT_PORT,
                        )
                        return True
            except (socket.gaierror, OSError):
                pass
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass

    # 3. Try Windows host IP via /etc/resolv.conf (WSL2 generated)
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("nameserver"):
                    host_ip = line.strip().split()[1]
                    # Skip external DNS servers (e.g. 8.8.8.8)
                    if not host_ip.startswith(("10.", "172.", "192.168.")):
                        continue
                    set_endpoint(host_ip, _DEFAULT_PORT)
                    if is_available():
                        logger.info(
                            "CDP available at Windows host %s:%s",
                            host_ip, _DEFAULT_PORT,
                        )
                        return True
                    break
    except (FileNotFoundError, OSError, IndexError):
        pass

    # 4. Try WSL2 default gateway (= Windows host in NAT mode)
    try:
        r = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0:
            parts = r.stdout.strip().split()
            if "via" in parts:
                gw_ip = parts[parts.index("via") + 1]
                set_endpoint(gw_ip, _DEFAULT_PORT)
                if is_available():
                    logger.info(
                        "CDP available at WSL2 gateway %s:%s",
                        gw_ip, _DEFAULT_PORT,
                    )
                    return True
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass

    # Not found — reset to default
    global _endpoint
    _endpoint = None
    logger.debug("CDP not available on any known endpoint")
    return False


# ── Chrome version parsing ────────────────────────────────────


def parse_chrome_major_version(version_string: str) -> int | None:
    """Extract the major version number from a Chrome version string.

    Args:
        version_string: e.g. "Google Chrome 138.0.6423.82" or
                        "Chrome/138.0.6423.82"

    Returns:
        Major version as int (e.g. 138) or None.
    """
    m = re.search(r"(\d+)\.\d+\.\d+\.\d+", version_string)
    return int(m.group(1)) if m else None


def requires_user_data_dir() -> bool:
    """Check if the detected Chrome version requires --user-data-dir.

    Chrome 136+ ignores ``--remote-debugging-port`` when using the
    default profile directory. A ``--user-data-dir`` must be
    explicitly specified.

    Returns True if Chrome >= 136, False otherwise, None if version
    cannot be determined.
    """
    version_info = get_version()
    if not version_info:
        return True  # Assume yes for safety
    browser = version_info.get("Browser", "")
    major = parse_chrome_major_version(browser)
    if major is None:
        return True
    return major >= 136
