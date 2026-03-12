"""PowerShell bridge — warm persistent process + one-shot fallback.

Manages a long-running powershell.exe subprocess for WebSocket
operations across the WSL2↔Windows boundary.

The warm bridge keeps one PowerShell process alive across calls.
Protocol: READY → CONNECT ws_url → CONNECTED → commands →
          DISCONNECT → DISCONNECTED → CONNECT again ...

First boot costs ~3s (PS startup).  Subsequent connects: ~100ms.

This module does NOT know about CDP. It relays arbitrary string
commands over WebSocket and returns the string responses.
``CdpSession`` adds CDP framing on top.
"""

from __future__ import annotations

import json
import logging
import os
import queue as _queue
import subprocess
import tempfile
import threading as _threading

from .environment import get_environment

logger = logging.getLogger(__name__)


# ── Module state ──────────────────────────────────────────────

_bridge_lock = _threading.Lock()
_bridge_process = None
_bridge_script_path: str | None = None
_bridge_ready = False
_bridge_queue: "_queue.Queue[str | None]" = _queue.Queue()
_bridge_reader_thread: _threading.Thread | None = None
_stale_bridge_cleaned = False
_bridge_warming = False  # True while a warm-up thread is active


# ── Stale cleanup ─────────────────────────────────────────────


def cleanup_stale_bridge() -> None:
    """Kill any orphaned PowerShell bridge processes from previous runs.

    Called once at startup.  Runs in a background thread to avoid
    blocking server launch.  Cleans up temp cdp_bridge_*.ps1 files
    from C:\\Windows\\Temp as an indicator of stale processes.
    """
    global _stale_bridge_cleaned
    if _stale_bridge_cleaned:
        return
    _stale_bridge_cleaned = True

    env = get_environment()
    if not env.wsl2:
        return

    import glob

    # Clean up stale cdp_bridge_*.ps1 temp files
    stale_scripts = glob.glob("/mnt/c/Windows/Temp/cdp_bridge_*.ps1")
    for script in stale_scripts:
        try:
            os.remove(script)
            logger.debug("Removed stale bridge script: %s", script)
        except OSError:
            pass


# ── Reader thread ─────────────────────────────────────────────


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


# ── PowerShell script ─────────────────────────────────────────

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


# ── Bridge lifecycle ──────────────────────────────────────────


def _ensure_bridge() -> bool:
    """Ensure the pre-warmed PowerShell bridge process is running.

    Returns True if the bridge is ready.  Thread-safe.
    """
    global _bridge_process, _bridge_script_path, _bridge_ready
    global _bridge_reader_thread, _bridge_queue

    env = get_environment()

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

        # Write script to Windows temp dir (or system default)
        win_temp = env.win_temp_dir if env.wsl2 else None
        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix=".ps1", prefix="cdp_bridge_", dir=win_temp,
        )
        _bridge_script_path = tmp_path
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(_BRIDGE_PS_SCRIPT)

        # Convert path for WSL2
        if env.wsl2:
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
        ps_exe = env.powershell_exe or "powershell.exe"
        try:
            _bridge_process = subprocess.Popen(
                [
                    ps_exe, "-NoProfile",
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


# ── Public API ────────────────────────────────────────────────


def warm_bridge() -> None:
    """Pre-start the PowerShell bridge in a background thread.

    Call this at app startup so the ~3s PowerShell boot happens
    before the user clicks "Replay".

    Safe to call repeatedly — will not spawn duplicate threads.
    """
    global _bridge_warming
    env = get_environment()
    if not env.wsl2:
        return
    cleanup_stale_bridge()
    # Already ready or already starting — nothing to do
    if _bridge_ready and _bridge_process is not None and _bridge_process.poll() is None:
        return
    if _bridge_warming:
        return
    _bridge_warming = True

    def _do_warm():
        global _bridge_warming
        try:
            _ensure_bridge()
        finally:
            _bridge_warming = False

    _threading.Thread(
        target=_do_warm,
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
    env = get_environment()
    needed = env.wsl2
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


def bridge_connect(ws_url: str, timeout: float = 10.0) -> bool:
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


def bridge_disconnect() -> None:
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


def bridge_send(cmd: str, timeout: float = 10.0) -> dict | None:
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


def bridge_stop() -> None:
    """Kill the bridge process gracefully."""
    global _bridge_process, _bridge_ready, _bridge_script_path

    with _bridge_lock:
        _bridge_ready = False
        if _bridge_process and _bridge_process.poll() is None:
            try:
                _bridge_process.stdin.write("EXIT\n")
                _bridge_process.stdin.flush()
                _bridge_process.wait(timeout=3)
            except Exception:
                try:
                    _bridge_process.kill()
                except Exception:
                    pass
            _bridge_process = None

        if _bridge_script_path:
            try:
                os.unlink(_bridge_script_path)
            except OSError:
                pass
            _bridge_script_path = None


# ── One-shot PS fallback ──────────────────────────────────────
#
# These spawn a fresh powershell.exe per call.  Slow (~2-3s) but
# reliable.  Used when the warm bridge isn't available and Python
# can't reach Chrome's WS directly.


def _wsl_path_to_win(path: str) -> str:
    """Convert a WSL filesystem path to a Windows path via wslpath."""
    try:
        r = subprocess.run(
            ["wslpath", "-w", path],
            capture_output=True, text=True, timeout=3,
        )
        return r.stdout.strip() or path
    except (subprocess.TimeoutExpired, OSError):
        return path


def ps_send_command(
    ws_url: str,
    method: str,
    params: dict,
    timeout: float = 5.0,
) -> dict | None:
    """Send a raw CDP command via a one-shot powershell.exe subprocess.

    Spawns a fresh PS process, generates a .NET WebSocket script,
    writes the command to a temp file, executes, parses output.
    ~2-3 seconds per call.

    Args:
        ws_url: WebSocket debugger URL.
        method: CDP method name (e.g. "Runtime.evaluate").
        params: CDP method params dict.
        timeout: Max seconds to wait.

    Returns:
        The CDP response dict, or None on failure.
    """
    env = get_environment()

    # Build CDP command JSON
    cdp_cmd = json.dumps({
        "id": 1,
        "method": method,
        "params": params,
    })

    # Write temp file to Windows filesystem for PS to read
    win_temp = env.win_temp_dir if env.wsl2 else None
    tmp_fd, tmp_path = tempfile.mkstemp(
        suffix=".json", prefix="cdp_cmd_",
        dir=win_temp,
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(cdp_cmd)

        # Convert to Windows path for PowerShell
        win_path = _wsl_path_to_win(tmp_path) if env.wsl2 else tmp_path

        # Escape for PS single-quoted string
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

        ps_exe = env.powershell_exe or "powershell.exe"
        try:
            r = subprocess.run(
                [ps_exe, "-NoProfile", "-Command", ps_script],
                capture_output=True, text=True,
                timeout=timeout + 5,
            )
            if r.returncode == 0 and r.stdout.strip():
                return json.loads(r.stdout.strip())
            if r.stderr.strip():
                logger.warning("PS one-shot error: %s", r.stderr.strip()[:200])
            return None
        except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as exc:
            logger.warning("PS one-shot failed: %s", exc)
            return None
    finally:
        # Always clean up the temp file
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def ps_evaluate(
    ws_url: str,
    expression: str,
    timeout: float = 5.0,
    *,
    await_promise: bool = False,
) -> dict | None:
    """Evaluate JavaScript via a one-shot powershell.exe subprocess.

    Convenience wrapper around ``ps_send_command`` for
    ``Runtime.evaluate``.

    Args:
        ws_url: WebSocket debugger URL.
        expression: JavaScript expression to evaluate.
        timeout: Max seconds to wait.
        await_promise: If True, CDP awaits the returned Promise.

    Returns:
        The CDP response dict, or None on failure.
    """
    params = {"expression": expression}
    if await_promise:
        params["awaitPromise"] = True
    return ps_send_command(ws_url, "Runtime.evaluate", params, timeout)

