# Phase 1: Python TCP Proxy — The Tunnel

## Status: ANALYSIS COMPLETE — Awaiting Approval

---

## What This Phase Delivers

A TCP proxy that runs **inside the Flask process** as a background thread.
It listens on WSL's `localhost:<port>` and forwards ALL TCP traffic
to `<windows_host_ip>:<port>`. This makes Chrome's debug port
(bound to 127.0.0.1 on Windows) reachable from WSL Python via localhost.

After this phase:
- `_get_json()` uses Python urllib to localhost → proxy → Chrome (no curl.exe)
  **This is the HIGH-FREQUENCY path** — called on every page load, tab list, activation
- `_port_in_use()` and `_cdp_responding()` use localhost → proxy → Chrome
- **curl.exe bridge becomes unnecessary for HTTP calls**
- `CdpSession` (WebSocket) — only used in 2 places (replayer + recording) —
  also benefits but is NOT the primary motivation

---

## Analysis: Current Code Paths

### How CDP HTTP requests work today (WSL2)

```
cdp_client._get_json("/json/version")
    → detects WSL2 → calls _curl_exe_get("http://localhost:9222/json/version")
        → subprocess.run(["curl.exe", "-s", url])
            → curl.exe runs on Windows → reaches Chrome localhost:9222
            → returns JSON stdout
        → parsed into dict
```

**Cost:** ~2000ms per call (subprocess spawn + Windows process creation + stdout pipe)
This is called on EVERY page load (`cdp_status`), every tab list, every activation.

### How CDP WebSocket works today (WSL2)

Only used in **2 places**: `replayer.py` (test streaming) and `recording.py` (screenshots).

```
CdpSession(ws_url)
    → detects WSL2 → _BridgeWebSocket (PowerShell bridge)
        → powershell.exe stays alive as persistent process
        → sends CONNECT ws://localhost:9222/devtools/page/XXX
        → PowerShell creates System.Net.WebSockets.ClientWebSocket
        → all JSON messages piped through stdin/stdout
```

**Cost:** ~4000ms first connect (PS startup), ~6ms subsequent (pre-warmed)
This is a SECONDARY concern — the PowerShell bridge already handles
subsequent connections well once warmed up.

### How it would work WITH the tunnel

```
Tunnel thread: listening on localhost:9222
    → accepts TCP connection from Python
    → opens TCP connection to hostname.local:9222 (Windows Chrome)
    → bidirectional byte forwarding

cdp_client._get_json("/json/version")  ← THE BIG WIN
    → NOT WSL2 path (tunnel makes localhost work!)
    → urllib GET http://localhost:9222/json/version
    → TCP → tunnel → Chrome
    → returns JSON

CdpSession(ws_url)  [secondary benefit]
    → _PyWebSocket connects to localhost:9222
    → TCP → tunnel → Chrome WebSocket
    → works but less critical (only 2 call sites)
```

**Cost:** ~5ms per HTTP call (down from ~2000ms — 400x improvement)

---

## Design

### File: `src/core/services/chrome/wsl_tunnel.py`

```python
"""
TCP tunnel from WSL localhost to Windows host.

Listens on 127.0.0.1:<port> in WSL and forwards all TCP connections
to <target_host>:<port>. Bidirectional byte forwarding using select().

This is a Layer 4 transport proxy — it forwards raw TCP bytes.
Both HTTP and WebSocket traffic pass through transparently.
No protocol awareness needed.
"""

class WslTunnel:
    def __init__(self, local_port: int, target_host: str, target_port: int | None = None):
        """
        Args:
            local_port: Port to listen on (e.g. 9222)
            target_host: Windows host IP (from hostname.local or gateway)
            target_port: Port on Windows side (defaults to local_port)
        """
    
    def start(self) -> bool:
        """Start the tunnel listener in a background thread.
        
        Returns True if started, False if port already in use.
        Creates a non-blocking server socket, then spawns a daemon 
        thread to accept connections and forward bytes.
        """
    
    def stop(self) -> None:
        """Stop the tunnel. Closes all active connections and the 
        listener socket. Thread-safe."""
    
    @property
    def is_running(self) -> bool:
        """Is the tunnel actively listening?"""
    
    def validate(self) -> dict:
        """Test end-to-end: connect through the tunnel, 
        hit /json/version on Chrome.
        
        Returns:
            {
                "ok": True/False,
                "latency_ms": 4.2,
                "chrome_version": "Chrome/138.0.6423.82",
                "tunnel_port": 9222,
                "target_host": "172.17.128.1",
                "error": None or "connection refused"
            }
        """
    
    @property
    def stats(self) -> dict:
        """Return tunnel statistics.
        
        Returns:
            {
                "started_at": "2026-03-11T08:50:00",
                "connections_total": 42,
                "connections_active": 1,
                "bytes_forwarded": 123456,
            }
        """
```

### Connection Forwarding Logic

For each accepted connection:
1. Open a new TCP connection to `target_host:target_port`
2. Spawn two forwarding loops:
   - client → remote: read from client socket, write to remote socket
   - remote → client: read from remote socket, write to client socket
3. Use `select.select()` for non-blocking I/O (no asyncio dependency)
4. When either side closes → close both sockets

```python
def _handle_connection(self, client_sock, client_addr):
    """Handle a single proxied connection."""
    remote_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    remote_sock.settimeout(5)
    try:
        remote_sock.connect((self._target_host, self._target_port))
    except (ConnectionRefusedError, OSError) as e:
        logger.warning("Tunnel: cannot reach %s:%s — %s",
                       self._target_host, self._target_port, e)
        client_sock.close()
        return
    
    # Bidirectional forwarding
    remote_sock.setblocking(False)
    client_sock.setblocking(False)
    sockets = [client_sock, remote_sock]
    
    try:
        while self._running:
            readable, _, errored = select.select(sockets, [], sockets, 1.0)
            
            if errored:
                break
            
            for sock in readable:
                data = sock.recv(65536)
                if not data:
                    raise ConnectionError("closed")
                
                target = remote_sock if sock is client_sock else client_sock
                target.sendall(data)
    except (ConnectionError, OSError):
        pass
    finally:
        client_sock.close()
        remote_sock.close()
```

### When sock.recv() returns empty → both sockets close and the thread exits.
### This handles HTTP (short-lived) and WebSocket (long-lived) connections equally.

---

## Integration Points

### 1. `cdp_client._get_json()` (line 130)

**Current:** On WSL2, always uses `_curl_exe_get()` (subprocess bridge).

**With tunnel:** If tunnel is running, WSL2 detection still returns True, BUT
localhost IS reachable → the "Native Linux / direct access" path works.

**Change needed:** Check if tunnel is active BEFORE the WSL2 branch:

```python
def _get_json(path, timeout=1.0, *, port=None):
    base = f"http://localhost:{port}" if port is not None else _base_url()
    url = f"{base}{path}"

    # If WSL tunnel is active, localhost works — skip curl.exe
    if _detect_wsl2() and not _is_tunnel_active(port):
        raw = _curl_exe_get(url, timeout=timeout)
        if raw:
            try:
                return json.loads(raw)
            except (ValueError, json.JSONDecodeError):
                pass
        return None

    # Native Linux / direct access / tunnel active
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None
```

### 2. `cdp_client._get_raw()` (line 164)

Same pattern as `_get_json()` — add tunnel check.

### 3. `CdpSession.__init__()` — WebSocket connection

**Current:** On WSL2, uses `_BridgeWebSocket` (PowerShell process).

**With tunnel:** If tunnel is running, `_PyWebSocket` works directly.

**Change needed:** Check tunnel before choosing bridge:

```python
# In CdpSession.__init__
if _detect_wsl2() and not _is_tunnel_active(port):
    # Fall back to PowerShell bridge
    self._ws = _BridgeWebSocket(ws_url, timeout=timeout)
else:
    # Direct Python WebSocket (works natively or through tunnel)
    self._ws = _PyWebSocket(ws_url, timeout=timeout)
```

### 4. `launcher._port_in_use()` (line 211)

**With tunnel:** If tunnel on this port is running, localhost works directly.
No change needed — the Python socket fallback (line 258) will succeed.

### 5. `launcher._cdp_responding()` (line 270)

Same — urllib to localhost will work through the tunnel.

### 6. `cdp_client.try_discover_endpoint()` (line 1325)

Step 1 (`is_available()` on localhost) will SUCCEED because the tunnel
is listening. No changes needed — it just works.

---

## Tunnel Lifecycle

### When does the tunnel start?

**Option A (Recommended):** Lazy start — when `cdp_client.try_discover_endpoint()` 
discovers that localhost doesn't work but hostname.local resolves.

```python
# In try_discover_endpoint(), after step 2 (hostname.local success):
if is_wsl2 and host_ip:
    from src.core.services.chrome.wsl_tunnel import get_tunnel, start_tunnel
    tunnel = start_tunnel(port=_DEFAULT_PORT, target_host=host_ip)
    if tunnel and tunnel.validate()["ok"]:
        # Reset endpoint to localhost — tunnel handles forwarding
        global _endpoint
        _endpoint = None  # back to localhost default
        return True
```

**Option B:** Explicit start via UI — user clicks [Start Tunnel] in the setup flow.

**Option C:** App startup — start tunnel during Flask app initialization.

I recommend **Option A** for Phase 1 (just works, no UI needed) and **Option B** 
for Phase 4 (interactive setup UI).

### When does the tunnel stop?

- Server shutdown (`server_lifecycle.py` cleanup)
- Chrome process killed (no point tunneling to nothing)
- User explicitly stops it via UI
- Tunnel target becomes unreachable (auto-restart with backoff)

### Port conflict handling

If port 9222 is already in use ON THE WSL SIDE (e.g. another tunnel or service):
1. Detect with `socket.bind()` — if EADDRINUSE, port is taken
2. Try next port in range (9222-9232)
3. Update cdp_client endpoint to match

---

## Testing Plan

### Unit Tests: `tests/unit/test_wsl_tunnel.py`

| # | Test | What It Verifies |
|---|------|-----------------|
| 1 | `test_tunnel_binds_port` | Tunnel starts and listens on the specified port |
| 2 | `test_tunnel_stop` | Tunnel stops cleanly, port is released |
| 3 | `test_tunnel_refuses_when_port_taken` | Returns False if port already in use |
| 4 | `test_tunnel_forwards_http` | HTTP request through tunnel reaches mock server |
| 5 | `test_tunnel_forwards_websocket` | WebSocket upgrade through tunnel works |
| 6 | `test_tunnel_bidirectional` | Data flows both directions through the tunnel |
| 7 | `test_tunnel_handles_target_down` | Client gets connection error if target unreachable |
| 8 | `test_tunnel_concurrent_connections` | Multiple simultaneous connections work |
| 9 | `test_tunnel_large_payload` | Large data (>64KB) transfers correctly |
| 10 | `test_tunnel_stats` | Connection count and bytes are tracked |
| 11 | `test_tunnel_validate_success` | `validate()` returns ok=True with mock Chrome |
| 12 | `test_tunnel_validate_failure` | `validate()` returns ok=False when target is down |

### Integration Tests: `tests/integration/test_wsl_tunnel_cdp.py`

These tests require Chrome running on Windows. Run manually on a WSL2 system.

| # | Test | What It Verifies |
|---|------|-----------------|
| 13 | `test_cdp_json_via_tunnel` | `_get_json("/json/version")` returns Chrome info |
| 14 | `test_cdp_targets_via_tunnel` | `get_targets()` returns tab list |
| 15 | `test_cdp_websocket_via_tunnel` | `CdpSession` connects and sends commands |
| 16 | `test_tunnel_latency_vs_curl` | Measure tunnel vs curl.exe — tunnel should be <20ms |

### Smoke Test: Manual on user's system

```bash
# 1. Start the tunnel manually
python -c "
from src.core.services.chrome.wsl_tunnel import WslTunnel
t = WslTunnel(9222, '$(hostname).local')
t.start()
print(t.validate())
input('Press Enter to stop...')
t.stop()
"

# 2. While tunnel runs, test CDP
python -c "
from src.ui.web.cdp_client import _get_json
print(_get_json('/json/version'))
"
```

---

## Files Created/Modified

| File | Action | What |
|------|--------|------|
| `src/core/services/chrome/wsl_tunnel.py` | **NEW** | TCP proxy tunnel implementation |
| `src/ui/web/cdp_client.py` | **MODIFY** | Add `_is_tunnel_active()`, update `_get_json`, `_get_raw`, `CdpSession` to use tunnel |
| `src/core/services/chrome/launcher.py` | **MODIFY** | No changes needed — localhost fallback works through tunnel |
| `tests/unit/test_wsl_tunnel.py` | **NEW** | Unit tests with mock servers |
| `tests/integration/test_wsl_tunnel_cdp.py` | **NEW** | Integration tests (manual, requires Chrome) |

---

## Prerequisites for This Phase

Before the tunnel can work, the Windows host must be reachable from WSL:

1. **hostname.local must resolve** — Already detected, already works on user's system ✅
2. **Firewall must allow the connection** — The tunnel connects to `hostname.local:9222`. 
   If the firewall blocks this, the tunnel's remote connection will fail with 
   `ConnectionRefusedError`. The tunnel's `validate()` will report this.
   - **This means Phase 3 (Firewall Rule) may need to be done BEFORE Phase 1 works end-to-end.**
   - **However, the tunnel CODE can be built and tested with mocks regardless.**

### The chicken-and-egg problem:

- Tunnel needs firewall rule to reach Chrome
- Firewall rule endpoint already exists (`POST /tab-mesh/wsl-fix-firewall`)
- But no UI to trigger it yet (Phase 4)

**Resolution:** Phase 1 builds the tunnel code + tests with mocks. 
The user can manually create the firewall rule to test end-to-end:
```powershell
New-NetFirewallRule -DisplayName "WSL_CDP_Access" -Direction Inbound `
    -InterfaceAlias "vEthernet (WSL)" -Action Allow -Protocol TCP `
    -LocalPort 9222
```

Or we add a quick CLI command to our `manage.sh` for convenience.

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Tunnel thread crashes | Catch all exceptions, log, auto-restart with 1s backoff |
| Port already in use | Detect at bind time, report error, try next port |
| Target IP changes (WSL restarts) | Re-resolve hostname.local on reconnect failure |
| select() not available | Standard Python stdlib — always available |
| Tunnel + curl.exe both active | Tunnel takes priority; curl.exe becomes dead code path |
| Multiple Chrome instances (different ports) | One tunnel per port, managed by a registry dict |
| WebSocket lifetime (hours) | select() loop with keepalive, no timeout |
| Chrome not running yet | Tunnel starts anyway — connections fail until Chrome is up |

---

## Estimated Effort

| Task | Time |
|------|------|
| `wsl_tunnel.py` implementation | 30 min |
| `cdp_client.py` integration (3 functions) | 15 min |
| Unit tests (12 tests) | 30 min |
| Integration tests (4 tests) | 15 min |
| Manual smoke test | 10 min |
| **Total** | **~1.5 hours** |

---

## Approval Checklist

Before implementation:
- [ ] User approves this design
- [ ] User confirms hostname.local resolves on their system
- [ ] User confirms Phase 3 (firewall) can be done manually for testing
- [ ] User approves the file locations and naming
