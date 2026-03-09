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


# ── WSL2 detection ────────────────────────────────────────────

_is_wsl2: bool | None = None
_curl_exe_path: str | None = None
_curl_exe_resolved: bool = False
_win_temp_dir: str | None = None
_win_temp_dir_resolved: bool = False


def _detect_wsl2() -> bool:
    """Check if we're running under WSL2."""
    global _is_wsl2
    if _is_wsl2 is not None:
        return _is_wsl2
    try:
        with open("/proc/version", encoding="utf-8") as f:
            _is_wsl2 = "microsoft" in f.read().lower()
    except OSError:
        _is_wsl2 = False
    return _is_wsl2


def _get_curl_exe() -> str | None:
    """Cached lookup for curl.exe path."""
    global _curl_exe_path, _curl_exe_resolved
    if _curl_exe_resolved:
        return _curl_exe_path
    import shutil
    _curl_exe_path = shutil.which("curl.exe")
    _curl_exe_resolved = True
    return _curl_exe_path


# ── Low-level HTTP ────────────────────────────────────────────


def _curl_exe_get(url: str, timeout: float = 2.0) -> str | None:
    """Use Windows curl.exe to make an HTTP request from WSL2.

    WSL2 runs in a separate network namespace from Windows.
    Chrome binds its debug port to 127.0.0.1 on the WINDOWS side,
    which is unreachable from WSL2's localhost.

    curl.exe runs in the Windows network namespace, so it CAN
    reach Chrome's localhost. This is a zero-config bridge.
    """
    import subprocess

    curl_exe = _get_curl_exe()
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


def _curl_exe_put(url: str, timeout: float = 2.0) -> str | None:
    """PUT request via Windows curl.exe (same bridge as _curl_exe_get)."""
    import subprocess

    curl_exe = _get_curl_exe()
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


def _get_json(
    path: str,
    timeout: float = 1.0,
    *,
    port: int | None = None,
) -> dict | list | None:
    """GET a Chrome JSON API endpoint.  Returns parsed JSON or None.

    Args:
        port: When provided, target ``http://localhost:{port}`` instead
              of the global endpoint.  Used for multi-instance support.
    """
    base = f"http://localhost:{port}" if port is not None else _base_url()
    url = f"{base}{path}"

    # WSL2: skip direct HTTP (always fails), go straight to curl.exe
    if _detect_wsl2():
        raw = _curl_exe_get(url, timeout=timeout)
        if raw:
            try:
                return json.loads(raw)
            except (ValueError, json.JSONDecodeError):
                pass
        return None

    # Native Linux / direct access
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def _get_raw(
    path: str,
    timeout: float = 1.0,
    *,
    port: int | None = None,
) -> str | None:
    """GET a Chrome debugging endpoint, return raw text or None.

    Args:
        port: When provided, target ``http://localhost:{port}`` instead
              of the global endpoint.
    """
    base = f"http://localhost:{port}" if port is not None else _base_url()
    url = f"{base}{path}"

    # WSL2: skip direct HTTP (always fails), go straight to curl.exe
    if _detect_wsl2():
        return _curl_exe_get(url, timeout=timeout)

    # Native Linux / direct access
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except (urllib.error.URLError, OSError):
        return None


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

    Args:
        port: Target a specific Chrome instance instead of the global one.

    Returns:
        The target dict for the new tab, or None on failure.
    """
    from urllib.parse import quote
    path = f"/json/new?{quote(url, safe='/:?=&%')}"
    base = f"http://localhost:{port}" if port is not None else _base_url()
    full_url = f"{base}{path}"

    # Try direct PUT first
    try:
        req = urllib.request.Request(full_url, method="PUT")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        pass

    # WSL2 fallback via curl.exe
    if _detect_wsl2():
        raw = _curl_exe_put(full_url, timeout=2.0)
        if raw:
            try:
                return json.loads(raw)
            except (ValueError, json.JSONDecodeError):
                pass

    return None


def evaluate_js(
    ws_url: str,
    expression: str,
    timeout: float = 5.0,
    *,
    await_promise: bool = False,
) -> dict | None:
    """Execute JavaScript on a Chrome tab via CDP WebSocket.

    WSL2 cannot reach Chrome's WebSocket at localhost:9222 directly,
    so we use PowerShell as a bridge — it runs on the Windows side
    where localhost:9222 IS reachable.

    The CDP command JSON is written to a temp file to avoid escaping
    issues with large or complex JS expressions — embedding them
    inline in a PowerShell string breaks on $, {}, quotes, etc.

    Args:
        ws_url: WebSocket debugger URL from target's
                ``webSocketDebuggerUrl`` field.
        expression: JavaScript expression to evaluate.
        timeout: Max seconds to wait.
        await_promise: If True, CDP will await the Promise returned
                       by the expression before returning the value.
                       Required for ``async function()`` IIFEs.

    Returns:
        The CDP response dict, or None on failure.
    """
    import subprocess
    import shutil
    import tempfile
    import os

    # Build the CDP command as a JSON file — no inline escaping needed
    params = {"expression": expression}
    if await_promise:
        params["awaitPromise"] = True
    cdp_cmd = json.dumps({
        "id": 1,
        "method": "Runtime.evaluate",
        "params": params,
    })

    # Write temp file to the WINDOWS filesystem so PowerShell can read it.
    # WSL paths (\\wsl.localhost\...) don't work reliably from PS.
    # The Windows temp dir is cached to avoid calling cmd.exe every time.
    global _win_temp_dir, _win_temp_dir_resolved
    if _detect_wsl2() and not _win_temp_dir_resolved:
        try:
            win_user = subprocess.run(
                ["cmd.exe", "/C", "echo", "%USERNAME%"],
                capture_output=True, text=True, timeout=3,
            ).stdout.strip()
            candidate = f"/mnt/c/Users/{win_user}/AppData/Local/Temp"
            if os.path.isdir(candidate):
                _win_temp_dir = candidate
                logger.debug("CDP evaluate_js: Windows temp dir = %s", candidate)
        except (subprocess.TimeoutExpired, OSError):
            pass
        _win_temp_dir_resolved = True
    win_temp_dir = _win_temp_dir if _detect_wsl2() else None

    tmp_fd, tmp_path = tempfile.mkstemp(
        suffix=".json", prefix="cdp_cmd_",
        dir=win_temp_dir,  # None falls back to system default
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(cdp_cmd)

        # Convert to Windows path for PowerShell
        if _detect_wsl2():
            try:
                win_path = subprocess.run(
                    ["wslpath", "-w", tmp_path],
                    capture_output=True, text=True, timeout=3,
                ).stdout.strip()
            except (subprocess.TimeoutExpired, OSError):
                win_path = tmp_path
        else:
            win_path = tmp_path

        # Escape backslashes for embedding in PS single-quoted string
        win_path_escaped = win_path.replace("'", "''")

        ps_script = f"""
$ws = New-Object System.Net.WebSockets.ClientWebSocket
$cts = New-Object System.Threading.CancellationTokenSource
$cts.CancelAfter({int(timeout * 1000)})
try {{
    $ws.ConnectAsync([Uri]'{ws_url}', $cts.Token).Wait()
    $cmd = [IO.File]::ReadAllText('{win_path_escaped}')
    $bytes = [Text.Encoding]::UTF8.GetBytes($cmd)
    $segment = New-Object System.ArraySegment[byte](,$bytes)
    $ws.SendAsync($segment, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $cts.Token).Wait()
    $buf = New-Object byte[] 262144
    $seg = New-Object System.ArraySegment[byte](,$buf)
    $result = $ws.ReceiveAsync($seg, $cts.Token).Result
    $response = [Text.Encoding]::UTF8.GetString($buf, 0, $result.Count)
    Write-Output $response
    $ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, '', $cts.Token).Wait()
}} catch {{
    Write-Error $_.Exception.Message
}}
"""

        try:
            r = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_script],
                capture_output=True, text=True,
                timeout=timeout + 5,
            )
            if r.returncode == 0 and r.stdout.strip():
                return json.loads(r.stdout.strip())
            if r.stderr.strip():
                logger.warning("CDP evaluate_js error: %s", r.stderr.strip()[:200])
            return None
        except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as exc:
            logger.warning("CDP evaluate_js failed: %s", exc)
            return None
    finally:
        # Always clean up the temp file
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── Persistent CDP session ────────────────────────────────────


class _PyWebSocket:
    """Minimal Python-native WebSocket client (text-only, for CDP).

    Implements RFC 6455 just enough for CDP: text frames,
    client masking, multi-frame receive, close/ping handling.
    No external dependencies — uses only Python's ``socket`` module.
    """

    __slots__ = ("_sock",)

    def __init__(self, ws_url: str, timeout: float = 5.0):
        import socket
        import base64
        import os
        from urllib.parse import urlparse

        parsed = urlparse(ws_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 80
        path = parsed.path or "/"

        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._sock.settimeout(timeout)

        # WebSocket upgrade handshake
        key = base64.b64encode(os.urandom(16)).decode()
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        )
        self._sock.sendall(handshake.encode())

        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("WS handshake: connection closed")
            resp += chunk

        status_line = resp.split(b"\r\n")[0]
        if b"101" not in status_line:
            raise ConnectionError(
                f"WS upgrade failed: {status_line.decode(errors='replace')}"
            )

    def send(self, text: str) -> None:
        """Send a text frame (client-masked per RFC 6455)."""
        import os

        data = text.encode("utf-8")
        mask = os.urandom(4)
        header = bytearray()
        header.append(0x81)  # FIN + TEXT opcode

        length = len(data)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(length.to_bytes(2, "big"))
        else:
            header.append(0x80 | 127)
            header.extend(length.to_bytes(8, "big"))

        header.extend(mask)
        masked = bytearray(length)
        for i in range(length):
            masked[i] = data[i] ^ mask[i % 4]
        self._sock.sendall(bytes(header) + bytes(masked))

    def recv(self) -> str:
        """Receive a complete text message (handles continuation frames)."""
        fragments = []
        while True:
            hdr = self._recv_exact(2)
            fin = hdr[0] & 0x80
            opcode = hdr[0] & 0x0F
            has_mask = hdr[1] & 0x80
            length = hdr[1] & 0x7F

            if length == 126:
                length = int.from_bytes(self._recv_exact(2), "big")
            elif length == 127:
                length = int.from_bytes(self._recv_exact(8), "big")

            mask_key = self._recv_exact(4) if has_mask else None
            payload = self._recv_exact(length)

            if mask_key:
                payload = bytearray(payload)
                for i in range(len(payload)):
                    payload[i] ^= mask_key[i % 4]
                payload = bytes(payload)

            if opcode == 0x08:
                raise ConnectionError("WS peer sent close frame")
            if opcode == 0x09:
                self._send_pong(payload)
                continue
            if opcode == 0x0A:
                continue

            fragments.append(payload)
            if fin:
                break

        return b"".join(fragments).decode("utf-8")

    def _recv_exact(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("WS connection lost")
            buf.extend(chunk)
        return bytes(buf)

    def _send_pong(self, payload: bytes) -> None:
        import os
        mask = os.urandom(4)
        header = bytearray([0x8A])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        else:
            header.append(0x80 | 126)
            header.extend(length.to_bytes(2, "big"))
        header.extend(mask)
        masked = bytearray(length)
        for i in range(length):
            masked[i] = payload[i] ^ mask[i % 4]
        self._sock.sendall(bytes(header) + bytes(masked))

    def close(self) -> None:
        try:
            self._sock.sendall(b"\x88\x80" + b"\x00\x00\x00\x00")
        except Exception:
            pass
        try:
            self._sock.close()
        except Exception:
            pass


# ── Pre-warmed PowerShell bridge ──────────────────────────────
#
# One PowerShell process stays alive across replays.
# Protocol: READY → CONNECT ws_url → CONNECTED → commands →
#           DISCONNECT → DISCONNECTED → CONNECT again ...
#
# First boot costs ~3s (PS startup).  Subsequent connects: ~100ms.

import threading as _threading
import queue as _queue

_bridge_lock = _threading.Lock()
_bridge_process = None
_bridge_script_path: str | None = None
_bridge_ready = False
_bridge_queue: "_queue.Queue[str | None]" = _queue.Queue()
_bridge_reader_thread: _threading.Thread | None = None


def _bridge_reader_loop() -> None:
    """Persistent reader: pumps stdout lines into _bridge_queue."""
    global _bridge_process
    while _bridge_process and _bridge_process.poll() is None:
        try:
            line = _bridge_process.stdout.readline()
            if not line:
                break
            _bridge_queue.put(line.strip())
        except Exception:
            break
    _bridge_queue.put(None)  # Sentinel: process died


def _bridge_read(timeout: float = 10.0) -> str | None:
    """Read the next line from the bridge (via queue). Thread-safe."""
    try:
        val = _bridge_queue.get(timeout=timeout)
        return val
    except _queue.Empty:
        return None

_BRIDGE_PS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::Out.WriteLine('READY')
[Console]::Out.Flush()

while ($true) {
    $cmd = [Console]::In.ReadLine()
    if ($cmd -eq $null -or $cmd -eq 'EXIT') { break }

    if ($cmd.StartsWith('CONNECT ')) {
        $wsUrl = $cmd.Substring(8)
        $ws = $null
        try {
            $ws = New-Object System.Net.WebSockets.ClientWebSocket
            $cts = New-Object System.Threading.CancellationTokenSource
            $ws.ConnectAsync([Uri]$wsUrl, $cts.Token).Wait()
            [Console]::Out.WriteLine('CONNECTED')
            [Console]::Out.Flush()

            while ($true) {
                $line = [Console]::In.ReadLine()
                if ($line -eq $null -or $line -eq 'EXIT') {
                    try { $ws.CloseAsync(
                        [System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure,
                        '', $cts.Token).Wait() } catch {}
                    $ws.Dispose()
                    exit
                }
                if ($line -eq 'DISCONNECT') {
                    try { $ws.CloseAsync(
                        [System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure,
                        '', $cts.Token).Wait() } catch {}
                    $ws.Dispose()
                    [Console]::Out.WriteLine('DISCONNECTED')
                    [Console]::Out.Flush()
                    break
                }

                $bytes = [Text.Encoding]::UTF8.GetBytes($line)
                $seg = New-Object System.ArraySegment[byte](,$bytes)
                $ws.SendAsync($seg,
                    [System.Net.WebSockets.WebSocketMessageType]::Text,
                    $true, $cts.Token).Wait()

                $all = New-Object System.Collections.Generic.List[byte]
                do {
                    $buf = New-Object byte[] 1048576
                    $rseg = New-Object System.ArraySegment[byte](,$buf)
                    $r = $ws.ReceiveAsync($rseg, $cts.Token).Result
                    for ($i = 0; $i -lt $r.Count; $i++) { $all.Add($buf[$i]) }
                } while (-not $r.EndOfMessage)

                $resp = [Text.Encoding]::UTF8.GetString($all.ToArray())
                [Console]::Out.WriteLine($resp)
                [Console]::Out.Flush()
            }
        } catch {
            if ($ws) { try { $ws.Dispose() } catch {} }
            [Console]::Out.WriteLine('ERROR:' + $_.Exception.Message)
            [Console]::Out.Flush()
        }
    }
}
"""


def _ensure_bridge() -> bool:
    """Ensure the pre-warmed PowerShell bridge process is running.

    Returns True if the bridge is ready.  Thread-safe.
    """
    global _bridge_process, _bridge_script_path, _bridge_ready
    global _bridge_reader_thread, _bridge_queue
    import subprocess
    import tempfile
    import os

    with _bridge_lock:
        # Already alive?
        if (
            _bridge_ready
            and _bridge_process is not None
            and _bridge_process.poll() is None
        ):
            return True

        # Clean up previous
        _bridge_ready = False
        if _bridge_process and _bridge_process.poll() is None:
            try:
                _bridge_process.kill()
            except Exception:
                pass
        if _bridge_script_path:
            try:
                os.unlink(_bridge_script_path)
            except OSError:
                pass

        # Drain old queue
        _bridge_queue = _queue.Queue()

        # Resolve Windows temp dir (once)
        global _win_temp_dir, _win_temp_dir_resolved
        if _detect_wsl2() and not _win_temp_dir_resolved:
            try:
                win_user = subprocess.run(
                    ["cmd.exe", "/C", "echo", "%USERNAME%"],
                    capture_output=True, text=True, timeout=3,
                ).stdout.strip()
                candidate = f"/mnt/c/Users/{win_user}/AppData/Local/Temp"
                if os.path.isdir(candidate):
                    _win_temp_dir = candidate
            except (subprocess.TimeoutExpired, OSError):
                pass
            _win_temp_dir_resolved = True

        # Write script
        win_temp = _win_temp_dir if _detect_wsl2() else None
        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix=".ps1", prefix="cdp_bridge_", dir=win_temp,
        )
        _bridge_script_path = tmp_path
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(_BRIDGE_PS_SCRIPT)

        # Convert path for WSL2
        if _detect_wsl2():
            try:
                win_path = subprocess.run(
                    ["wslpath", "-w", tmp_path],
                    capture_output=True, text=True, timeout=3,
                ).stdout.strip()
            except (subprocess.TimeoutExpired, OSError):
                win_path = tmp_path
        else:
            win_path = tmp_path

        # Start PowerShell
        try:
            _bridge_process = subprocess.Popen(
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

            # Start persistent reader thread
            _bridge_reader_thread = _threading.Thread(
                target=_bridge_reader_loop,
                name="cdp-bridge-reader",
                daemon=True,
            )
            _bridge_reader_thread.start()

            # Wait for READY signal via queue
            line = _bridge_read(timeout=10.0)
            _bridge_ready = (line == "READY")

            if _bridge_ready:
                logger.info(
                    "CDP bridge process ready (PID %d)",
                    _bridge_process.pid,
                )
            else:
                logger.warning("CDP bridge failed to start (got: %s)", line)
                try:
                    _bridge_process.kill()
                except Exception:
                    pass
                _bridge_process = None

        except Exception as exc:
            logger.warning("CDP bridge startup failed: %s", exc)
            _bridge_process = None
            _bridge_ready = False

    return _bridge_ready


def warm_bridge() -> None:
    """Pre-start the PowerShell bridge in a background thread.

    Call this at app startup so the ~3s PowerShell boot happens
    before the user clicks "Replay".
    """
    if not _detect_wsl2():
        return
    _threading.Thread(
        target=_ensure_bridge,
        name="cdp-bridge-warmup",
        daemon=True,
    ).start()


def bridge_status() -> dict:
    """Return the current bridge status for the UI.

    Returns:
        dict with keys:
            needed (bool): True if WSL2 requires the bridge
            ready (bool): True if the bridge is warmed and ready
            warming (bool): True if currently starting up
    """
    needed = _detect_wsl2()
    if not needed:
        return {"needed": False, "ready": True, "warming": False}

    ready = (
        _bridge_ready
        and _bridge_process is not None
        and _bridge_process.poll() is None
    )
    # "warming" = we know it's needed but it's not ready yet
    warming = needed and not ready
    return {"needed": True, "ready": ready, "warming": warming}


def _bridge_connect(ws_url: str, timeout: float = 10.0) -> bool:
    """Send CONNECT to the pre-warmed bridge.  Returns True on success."""
    if not _ensure_bridge():
        return False

    try:
        _bridge_process.stdin.write(f"CONNECT {ws_url}\n")
        _bridge_process.stdin.flush()

        line = _bridge_read(timeout=timeout)

        if line == "CONNECTED":
            return True

        if line and line.startswith("ERROR:"):
            logger.warning("CDP bridge connect error: %s", line)
        else:
            logger.warning(
                "CDP bridge: unexpected response: %s", line,
            )
        return False

    except Exception as exc:
        logger.warning("CDP bridge connect failed: %s", exc)
        return False


def _bridge_disconnect() -> None:
    """Send DISCONNECT to the bridge (returns it to idle state)."""
    if _bridge_process and _bridge_process.poll() is None:
        try:
            _bridge_process.stdin.write("DISCONNECT\n")
            _bridge_process.stdin.flush()

            line = _bridge_read(timeout=5.0)
            if line == "DISCONNECTED":
                logger.debug("CDP bridge disconnected cleanly")
            else:
                logger.warning(
                    "CDP bridge disconnect: unexpected response: %s", line,
                )
        except Exception:
            pass


def _bridge_send(cmd: str, timeout: float = 10.0) -> dict | None:
    """Send a CDP command via the bridge and return parsed response."""
    if not _bridge_process or _bridge_process.poll() is not None:
        return None

    try:
        _bridge_process.stdin.write(cmd + "\n")
        _bridge_process.stdin.flush()

        line = _bridge_read(timeout=timeout)
        if line:
            return json.loads(line)
        return None

    except Exception as exc:
        logger.warning("CDP bridge send failed: %s", exc)
        return None


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

        # ── Strategy 1: Python-native WebSocket (instant) ─────
        _t1 = _t.monotonic()
        try:
            self._ws = _PyWebSocket(ws_url, timeout=connect_timeout)
            self._mode = "python"
            self._connected = True
            logger.info(
                "CdpSession connected via Python socket to %s (%.0fms)",
                ws_url, (_t.monotonic() - _t1) * 1000,
            )
            return
        except Exception as exc:
            logger.debug(
                "Python WS failed in %.0fms (%s), trying bridge",
                (_t.monotonic() - _t1) * 1000, exc,
            )

        # ── Strategy 2: Pre-warmed bridge (fast) ──────────────
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

        # ── Strategy 3: Fresh PowerShell (slow, last resort) ──
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

        win_temp = _win_temp_dir if _detect_wsl2() else None
        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix=".ps1", prefix="cdp_sess_", dir=win_temp,
        )
        self._script_path = tmp_path
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(ps_script)

        if _detect_wsl2():
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
            return (
                _bridge_process is not None
                and _bridge_process.poll() is None
            )
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
        self.close()



# ── Auto-discovery for WSL ────────────────────────────────────


def try_discover_endpoint() -> bool:
    """Try to find a working CDP endpoint.

    Attempts localhost first, then the Windows host IP (for WSL2).
    WSL2 uses a separate network namespace, so Chrome's 127.0.0.1:9222
    is NOT reachable from WSL's localhost. We try:
    1. localhost (works for native Linux / WSL2 mirrored networking)
    2. resolv.conf nameserver (works when WSL generates it)
    3. Default gateway IP (WSL2 NAT mode — most reliable)

    Sets the endpoint internally if found.

    Returns:
        True if a working endpoint was discovered.
    """
    import subprocess

    # 1. Try localhost (works for WSL2 mirrored networking + native)
    if is_available():
        logger.info("CDP available at %s", _base_url())
        return True

    # 2. Try Windows host IP via /etc/resolv.conf (WSL2 generated)
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

    # 3. Try WSL2 default gateway (= Windows host in NAT mode)
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
