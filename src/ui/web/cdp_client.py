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


def _get_json(path: str, timeout: float = 1.0) -> dict | list | None:
    """GET a Chrome JSON API endpoint.  Returns parsed JSON or None."""
    url = f"{_base_url()}{path}"

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


def _get_raw(path: str, timeout: float = 1.0) -> str | None:
    """GET a Chrome debugging endpoint, return raw text or None."""
    url = f"{_base_url()}{path}"

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


def is_available() -> bool:
    """Check if Chrome's debugging endpoint is reachable."""
    version = _get_json("/json/version", timeout=0.5)
    return version is not None


def get_version() -> dict | None:
    """Return Chrome version info, or None if unreachable.

    Example response::

        {
            "Browser": "Chrome/138.0.6423.82",
            "Protocol-Version": "1.3",
            "User-Agent": "...",
            "V8-Version": "...",
            "WebKit-Version": "..."
        }
    """
    return _get_json("/json/version")


def get_targets() -> list[dict]:
    """Return all open browser targets (tabs, extensions, etc).

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
    result = _get_json("/json")
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


def activate_target(target_id: str) -> bool:
    """Bring a tab to the foreground by its target ID.

    Uses Chrome's ``/json/activate/{id}`` endpoint.

    Returns:
        True if activation succeeded, False otherwise.
    """
    raw = _get_raw(f"/json/activate/{target_id}", timeout=1.0)
    if raw is not None:
        logger.info("CDP activated target: %s", target_id)
        return True
    logger.warning("CDP failed to activate target: %s", target_id)
    return False


def create_tab(url: str) -> dict | None:
    """Open a new browser tab via CDP.

    Uses the ``PUT /json/new?url`` endpoint (PUT required by Chrome).

    Returns:
        The target dict for the new tab, or None on failure.
    """
    from urllib.parse import quote
    path = f"/json/new?{quote(url, safe='/:?=&%')}"
    full_url = f"{_base_url()}{path}"

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

        # Read response (must be 101 Switching Protocols)
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
            header.append(0x80 | length)  # MASK bit set
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(length.to_bytes(2, "big"))
        else:
            header.append(0x80 | 127)
            header.extend(length.to_bytes(8, "big"))

        header.extend(mask)

        # Mask the payload
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

            if opcode == 0x08:  # Close
                raise ConnectionError("WS peer sent close frame")
            if opcode == 0x09:  # Ping → send pong
                self._send_pong(payload)
                continue
            if opcode == 0x0A:  # Pong — ignore
                continue

            fragments.append(payload)
            if fin:
                break

        return b"".join(fragments).decode("utf-8")

    def _recv_exact(self, n: int) -> bytes:
        """Read exactly *n* bytes from the socket."""
        buf = bytearray()
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("WS connection lost")
            buf.extend(chunk)
        return bytes(buf)

    def _send_pong(self, payload: bytes) -> None:
        """Send a pong frame."""
        import os

        mask = os.urandom(4)
        header = bytearray([0x8A])  # FIN + PONG
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
        """Send a close frame and shut down the socket."""
        try:
            # Send close frame (opcode 0x08, masked, zero-length)
            self._sock.sendall(b"\x88\x80" + b"\x00\x00\x00\x00")
        except Exception:
            pass
        try:
            self._sock.close()
        except Exception:
            pass


class CdpSession:
    """Persistent CDP WebSocket session — one connection, many commands.

    Primary strategy: Python-native socket WebSocket (~50ms connect).
    Fallback: PowerShell .NET WebSocket (for old WSL2 without localhost
    forwarding — ~3s connect).

    Usage::

        with CdpSession(ws_url) as session:
            if session.connected:
                result = session.evaluate("document.title")
    """

    __slots__ = (
        "_ws", "_process", "_connected", "_cmd_id",
        "_ws_url", "_script_path", "_mode",
    )

    def __init__(self, ws_url: str, connect_timeout: float = 10.0):
        self._ws = None
        self._process = None
        self._connected = False
        self._cmd_id = 0
        self._ws_url = ws_url
        self._script_path = None
        self._mode = ""

        # ── Strategy 1: Python-native WebSocket (instant) ─────
        try:
            self._ws = _PyWebSocket(ws_url, timeout=connect_timeout)
            self._mode = "python"
            self._connected = True
            logger.info(
                "CdpSession connected via Python socket to %s", ws_url,
            )
            return
        except Exception as exc:
            logger.debug(
                "Python WS failed (%s), trying PowerShell", exc,
            )

        # ── Strategy 2: PowerShell (WSL2 fallback) ────────────
        self._init_powershell(ws_url, connect_timeout)

    def _init_powershell(
        self, ws_url: str, connect_timeout: float,
    ) -> None:
        """Fall back to PowerShell .NET WebSocket for old WSL2."""
        import subprocess
        import tempfile
        import os
        import threading

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

        ws_url_safe = ws_url.replace("'", "''")
        ps_script = (
            "$ErrorActionPreference = 'Stop'\n"
            "$ws = New-Object System.Net.WebSockets.ClientWebSocket\n"
            "$cts = New-Object System.Threading.CancellationTokenSource\n"
            "try {\n"
            f"    $ws.ConnectAsync([Uri]'{ws_url_safe}', $cts.Token).Wait()\n"
            "    [Console]::Out.WriteLine('CONNECTED')\n"
            "    [Console]::Out.Flush()\n"
            "    while ($true) {\n"
            "        $line = [Console]::In.ReadLine()\n"
            "        if ($line -eq $null -or $line -eq 'EXIT') { break }\n"
            "        $bytes = [Text.Encoding]::UTF8.GetBytes($line)\n"
            "        $seg = New-Object System.ArraySegment[byte](,$bytes)\n"
            "        $ws.SendAsync($seg, "
            "[System.Net.WebSockets.WebSocketMessageType]::Text, "
            "$true, $cts.Token).Wait()\n"
            "        $all = New-Object System.Collections.Generic.List[byte]\n"
            "        do {\n"
            "            $buf = New-Object byte[] 1048576\n"
            "            $rseg = New-Object System.ArraySegment[byte](,$buf)\n"
            "            $r = $ws.ReceiveAsync($rseg, $cts.Token).Result\n"
            "            for ($i = 0; $i -lt $r.Count; $i++) "
            "{ $all.Add($buf[$i]) }\n"
            "        } while (-not $r.EndOfMessage)\n"
            "        $resp = [Text.Encoding]::UTF8.GetString($all.ToArray())\n"
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
            self._process = subprocess.Popen(
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
                    line = self._process.stdout.readline().strip()
                    connected[0] = (line == "CONNECTED")
                except Exception:
                    pass

            t = threading.Thread(target=_wait, daemon=True)
            t.start()
            t.join(timeout=connect_timeout)

            self._connected = connected[0]
            self._mode = "powershell"
            if self._connected:
                logger.info(
                    "CdpSession connected via PowerShell to %s", ws_url,
                )
            else:
                logger.warning(
                    "CdpSession PS: failed to connect within %ss",
                    connect_timeout,
                )
                self.close()

        except Exception as exc:
            logger.warning("CdpSession PS startup failed: %s", exc)
            self.close()

    @property
    def connected(self) -> bool:
        """True if the session is alive."""
        if not self._connected:
            return False
        if self._mode == "python":
            return self._ws is not None
        if self._mode == "powershell":
            return (
                self._process is not None
                and self._process.poll() is None
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
        return self._evaluate_ps(cmd, timeout)

    def _evaluate_python(self, cmd: str, timeout: float) -> dict | None:
        """Send/receive via Python socket WebSocket."""
        old_timeout = self._ws._sock.gettimeout()
        self._ws._sock.settimeout(timeout)
        try:
            self._ws.send(cmd)
            resp = self._ws.recv()
            return json.loads(resp)
        except Exception as exc:
            logger.warning("CdpSession Python evaluate failed: %s", exc)
            self._connected = False
            return None
        finally:
            try:
                self._ws._sock.settimeout(old_timeout)
            except Exception:
                pass

    def _evaluate_ps(self, cmd: str, timeout: float) -> dict | None:
        """Send/receive via PowerShell stdin/stdout."""
        import threading

        try:
            self._process.stdin.write(cmd + "\n")
            self._process.stdin.flush()

            result_holder: list[dict | None] = [None]

            def _read():
                try:
                    line = self._process.stdout.readline().strip()
                    if line:
                        result_holder[0] = json.loads(line)
                except Exception:
                    pass

            reader = threading.Thread(target=_read, daemon=True)
            reader.start()
            reader.join(timeout=timeout)

            if result_holder[0] is None:
                logger.warning(
                    "CdpSession PS: no response within %ss (cmd %d)",
                    timeout, self._cmd_id,
                )
                return None

            return result_holder[0]

        except Exception as exc:
            logger.warning("CdpSession PS evaluate failed: %s", exc)
            self._connected = False
            return None

    def close(self):
        """Shut down the session and clean up."""
        import os

        if self._mode == "python" and self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

        if self._mode == "powershell" and self._process:
            if self._process.poll() is None:
                try:
                    self._process.stdin.write("EXIT\n")
                    self._process.stdin.flush()
                    self._process.wait(timeout=3.0)
                except Exception:
                    try:
                        self._process.kill()
                    except Exception:
                        pass
            self._process = None

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
