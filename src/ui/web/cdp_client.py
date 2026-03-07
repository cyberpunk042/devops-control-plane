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


def evaluate_js(ws_url: str, expression: str, timeout: float = 5.0) -> dict | None:
    """Execute JavaScript on a Chrome tab via CDP WebSocket.

    WSL2 cannot reach Chrome's WebSocket at localhost:9222 directly,
    so we use PowerShell as a bridge — it runs on the Windows side
    where localhost:9222 IS reachable.

    Args:
        ws_url: WebSocket debugger URL from target's
                ``webSocketDebuggerUrl`` field.
        expression: JavaScript expression to evaluate.
        timeout: Max seconds to wait.

    Returns:
        The CDP response dict, or None on failure.
    """
    import subprocess
    import shutil

    # Escape the JS expression for embedding in PowerShell
    # Replace single quotes with double-single for PS, and backslashes
    ps_expr = expression.replace("'", "''")

    ps_script = f"""
$ws = New-Object System.Net.WebSockets.ClientWebSocket
$cts = New-Object System.Threading.CancellationTokenSource
$cts.CancelAfter({int(timeout * 1000)})
try {{
    $ws.ConnectAsync([Uri]'{ws_url}', $cts.Token).Wait()
    $cmd = '{{"id":1,"method":"Runtime.evaluate","params":{{"expression":"{ps_expr}"}}}}'
    $bytes = [Text.Encoding]::UTF8.GetBytes($cmd)
    $segment = New-Object System.ArraySegment[byte](,$bytes)
    $ws.SendAsync($segment, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $cts.Token).Wait()
    $buf = New-Object byte[] 65536
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
