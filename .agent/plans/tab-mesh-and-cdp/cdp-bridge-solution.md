# CDP Bridge Refactor — Solution Design (v2)

**Created:** 2026-03-11
**Status:** Design phase — no code until agreed
**Depends on:** `.agent/plans/cdp-bridge-refactor.md` (analysis)

---

## 1. Vision

Three layers. Three domains. Clean separation.

The problem "how do I reach a TCP port on Windows from WSL2" is **not
a Chrome problem**. It's a networking problem. Chrome is just the first
consumer. Tomorrow it could be a Windows-side API server, a database,
or anything else listening on the Windows host.

The problem "how do I send CDP commands to Chrome" is **not a transport
problem**. It's a protocol problem. CDP doesn't care how the bytes
travel — direct socket, tunnel, PowerShell bridge — it just needs a
connected WebSocket.

Mixing these two concerns in a single 1700-line file is why the system
doesn't adapt. Each function reinvents the transport layer because
there's no transport layer to call.

---

## 2. The Three Layers

```
    ┌─────────────────────────────────────────────────────────────┐
    │  LAYER 3: CONSUMERS                                         │
    │                                                             │
    │  replayer.py     recorder.py    tab_mesh/     cdp_port_     │
    │                                 __init__.py   injector.py   │
    │                                                             │
    │  These call CDP. They don't know how bytes reach Chrome.    │
    ├─────────────────────────────────────────────────────────────┤
    │  LAYER 2: CDP PROTOCOL                                      │
    │                                                             │
    │  cdp_client.py                                              │
    │    CdpSession        — persistent WS session to a target    │
    │    evaluate_js()     — evaluate JS in a tab                 │
    │    get_targets()     — list open tabs                       │
    │    activate_target() — bring tab to front                   │
    │    is_available()    — check if Chrome is reachable          │
    │    session pool      — reuse connections                     │
    │                                                             │
    │  Speaks CDP. Asks Layer 1 for connectivity.                 │
    ├─────────────────────────────────────────────────────────────┤
    │  LAYER 1: WSL TRANSPORT                                     │
    │                                                             │
    │  src/core/services/wsl_transport/                            │
    │    TransportRouter   — knows what works, adapts              │
    │    host resolution   — hostname.local → IP                   │
    │    tunnel backends   — python_proxy, socat, netsh, ssh       │
    │    bridge backends   — curl.exe, powershell                  │
    │    environment       — WSL2? mirrored? native?               │
    │                                                             │
    │  Solves: "give me an HTTP/WS connection to host:port"       │
    │  Doesn't know what CDP is. Doesn't know what Chrome is.     │
    ├─────────────────────────────────────────────────────────────┤
    │  INFRASTRUCTURE                                             │
    │                                                             │
    │  src/core/services/chrome/                                   │
    │    launcher.py       — launch/kill Chrome instances          │
    │    detection.py      — find Chrome binary                    │
    │    profiles.py       — manage Chrome profiles                │
    │    shortcuts.py      — desktop shortcuts                     │
    │                                                             │
    │  Manages Chrome. Uses Layer 1 for port checks.              │
    └─────────────────────────────────────────────────────────────┘
```

### Why This Separation Matters

| Concern | Where it lives | Who calls it |
|---------|---------------|-------------|
| "Is localhost:9222 reachable from WSL2?" | Transport | Chrome, CDP, anyone |
| "Which tunnel backend should I use?" | Transport | Transport (internal) |
| "What IP does hostname.local resolve to?" | Transport | Transport (internal) |
| "Send a CDP command to evaluate JS" | CDP | Consumers |
| "Pool and reuse WebSocket sessions" | CDP | CDP (internal) |
| "Launch Chrome with debug flags" | Chrome | UI routes |
| "Kill a Chrome instance gracefully" | Chrome | UI routes, uses CDP |

---

## 3. Layer 1: wsl_transport — The Transport Service

### 3.1 Package Structure

```
src/core/services/wsl_transport/
    __init__.py              — public API exports
    environment.py           — system capability detection (WSL2? tools?)
    network.py               — host resolution, mirrored detection, reachability
    router.py                — TransportRouter (the brain)
    websocket.py             — _PyWebSocket (raw WS client, protocol-agnostic)
    tunnel_backends.py       — moved from chrome/wsl_tunnel.py (all 5 backends)
    curl_bridge.py           — curl.exe HTTP bridge (~50 lines)
    ps_bridge.py             — PowerShell bridge: warm process, one-shot,
                                script generation, temp file mgmt (~300+ lines)
```

**Why this split (compared to v1 of this document):**

- `environment.py` was conflating **system capabilities** ("am I on WSL2?",
  "is powershell.exe available?") with **network topology** ("what IP is
  hostname.local?", "is mirrored networking active?"). These are different
  concerns — you detect WSL2 by reading `/proc/version`, but you detect
  network topology by probing TCP connections. Split into `environment.py`
  + `network.py`.

- `bridges.py` was conflating **curl.exe** (stateless HTTP, ~50 lines) with
  **PowerShell bridge** (stateful process with lifecycle, stdin/stdout
  protocol, script template generation, locking, ~300+ lines). They share
  nothing except "subprocess call to a Windows binary." Split into
  `curl_bridge.py` + `ps_bridge.py`.

- `_PyWebSocket` was listed as "stays in cdp_client.py" but `router.connect_ws()`
  calls it — meaning transport would depend on CDP. That's a **layering violation**.
  `_PyWebSocket` is a raw WS client. It doesn't speak CDP. It belongs in
  transport as `websocket.py`.

### 3.2 environment.py — System Capability Detection

Answers: "what kind of system is this?" and "what tools do we have?"
Does NOT probe network. Does NOT connect to anything.

```
class WslEnvironment:
    """Immutable snapshot of system capabilities.

    Detected once at first use. Cached for process lifetime.
    These checks read files and call `which` — no network.
    """

    wsl2: bool              # Running inside WSL2?
    curl_exe: str | None    # Path to curl.exe (None if not found)
    powershell_exe: str | None  # Path to powershell.exe
    win_temp_dir: str | None    # Windows %TEMP% path

# Module-level singleton
_env: WslEnvironment | None = None

def get_environment() -> WslEnvironment:
    """Return cached environment. Detect on first call."""

def is_wsl2() -> bool:
    """Quick check. Cached."""
```

**Replaces:**
- `_detect_wsl2()` in cdp_client.py
- `_get_curl_exe()` in cdp_client.py
- `_get_win_temp()` in cdp_client.py
- `is_wsl()` in launcher.py

### 3.3 network.py — Network Topology Discovery

Answers: "how can we reach the Windows host?" and "what network
mode are we in?" These checks probe actual TCP connections.

```
def resolve_host_ip() -> str | None:
    """Resolve hostname.local → IP via mDNS. Cached."""

def is_mirrored() -> bool:
    """Check if WSL2 mirrored networking is active.
    
    True if localhost connects directly to a Windows-side port.
    Cached after first check.
    """

def direct_http_reachable(host_ip: str, port: int, timeout: float) -> bool:
    """Can we reach host_ip:port via direct Python HTTP?"""

def localhost_reachable(port: int, timeout: float) -> bool:
    """Can we reach localhost:port? (tunnel or mirrored)"""
```

**Replaces:**
- `_get_windows_host_ip()` in cdp_client.py
- `_resolve_wsl_host()` in launcher.py
- `_direct_http_reachable()` in cdp_client.py
- `_port_in_use()` network probing logic in launcher.py

### 3.4 websocket.py — Raw WebSocket Client

The `_PyWebSocket` class extracted from cdp_client.py. This is a
**protocol-agnostic** WebSocket client. It knows how to:
- Perform WS handshake over a TCP socket
- Send/receive WS frames
- Handle masking, fragmentation, ping/pong

It does NOT know CDP. It does NOT know Chrome. It's pure transport.

```
class PyWebSocket:
    """Minimal WebSocket client over a raw TCP socket."""

    def __init__(self, url: str, timeout: float = 10.0):
        """Connect to ws_url, perform upgrade handshake."""

    def send(self, data: str) -> None:
        """Send a text frame."""

    def recv(self, timeout: float) -> str:
        """Receive the next text frame."""

    def close(self) -> None:
        """Send close frame and shut down socket."""

    @property
    def connected(self) -> bool:
        """True if socket is alive."""
```

**Why it moves here:**

In v1 of this document, `_PyWebSocket` was listed as "stays in
cdp_client.py." But `router.connect_ws()` needs to construct one —
that means transport importing from CDP. Layering violation.

`_PyWebSocket` is a TCP transport primitive. CdpSession wraps it to
add CDP framing. The right ownership:

```
Transport layer: PyWebSocket     → "I can send/recv WS frames"
CDP layer:       CdpSession      → "I use a PyWebSocket to speak CDP"
```

### 3.5 tunnel_backends.py — All Tunnel Implementations

This is `wsl_tunnel.py` **moved** from `chrome/` to `wsl_transport/`.

The file stays structurally the same — it already has the right
abstraction (`TUNNEL_METHODS` registry, shared interface). The move
is about domain ownership: tunnels are a transport concern, not a
Chrome concern.

```
# Content from current wsl_tunnel.py, unchanged:

class WslTunnel:        # python_proxy
class SocatTunnel:      # socat
class NetshTunnel:      # netsh portproxy
class SshTunnel:        # ssh
class MirroredConfig:   # mirrored networking

TUNNEL_METHODS: dict[str, dict]  # registry

# NEW: is_available() classmethod added to each backend

def start_tunnel(local_port, target_host, target_port, method)
def stop_tunnel()
def get_active_tunnel()
def maybe_start_tunnel()
```

### 3.6 curl_bridge.py — HTTP via curl.exe

Stateless. Subprocess per call. ~50 lines.

```
def curl_get(url: str, timeout: float) -> bytes | None:
    """HTTP GET via curl.exe subprocess.

    Uses the curl_exe path from WslEnvironment.
    Returns raw response body or None on failure.
    """

def curl_put(url: str, timeout: float) -> bytes | None:
    """HTTP PUT via curl.exe subprocess."""
```

**Replaces:** `_curl_exe_get()`, `_curl_exe_put()` in cdp_client.py

### 3.7 ps_bridge.py — PowerShell Bridge (warm + one-shot)

Stateful. Manages a long-running powershell.exe process for WS
operations. Has its own lifecycle, locking, script generation,
temp file management. ~300+ lines.

This is a significant module — it manages:
- A persistent powershell.exe subprocess (`_bridge_process`)
- stdin/stdout communication protocol (JSON commands/responses)
- Script template generation (.NET WebSocket code)
- Temp file writes to Windows %TEMP%
- Thread safety via `_bridge_lock`
- Health monitoring (process alive? responsive?)

```
# Warm bridge (persistent process)
def warm_bridge() -> None:
    """Pre-start a powershell.exe process for WS operations.
    
    Spawns the process in background. Subsequent bridge_send()
    calls use this warm process instead of cold-starting each time.
    """

def bridge_send(command: str, timeout: float) -> dict | None:
    """Send a JSON-encoded WS command through the warm bridge.
    
    The bridge process handles:
    1. Connect to WebSocket URL
    2. Send the command
    3. Wait for response
    4. Return result as JSON
    """

def bridge_status() -> dict:
    """Return bridge health: process alive, response time, age."""

def bridge_stop() -> None:
    """Kill the bridge process gracefully."""

# One-shot (fresh subprocess per call)
def ps_evaluate(ws_url: str, expression: str, timeout: float,
                *, await_promise: bool = False) -> dict | None:
    """Evaluate JS via a one-shot powershell.exe subprocess.
    
    Last resort. Spawns a fresh PS process, generates a .NET
    WebSocket script, writes it to temp file, executes, parses
    output. ~2-3 seconds per call.
    """

def ps_send_command(ws_url: str, method: str, params: dict,
                    timeout: float) -> dict | None:
    """Send a raw CDP command via one-shot PS. Same mechanism
    as ps_evaluate but for arbitrary CDP methods."""
```

**Replaces:**
- `warm_bridge()`, `_bridge_send()`, `_bridge_process`, `_bridge_lock` in cdp_client.py
- PS one-shot logic from `evaluate_js()` in cdp_client.py
- PS script generation code in cdp_client.py
- `_evaluate_fresh_ps()` in CdpSession

### 3.8 router.py — The Brain

The router uses `environment.py`, `network.py`, `tunnel_backends.py`,
`curl_bridge.py`, `ps_bridge.py`, and `websocket.py`. It is the only
module in the package that imports from siblings — all others are
independent.

```
class TransportRouter:
    """Adaptive transport layer for WSL2↔Windows communication.

    Discovers the runtime environment, probes available channels,
    ranks them by speed, and provides the fastest path to any
    host:port on the Windows side.

    Does NOT know about CDP, Chrome, or any specific protocol.
    It just provides connectivity.
    """

    ─── State ───

    _env: WslEnvironment             # from environment.py
    _host_ip: str | None             # from network.py
    _mirrored: bool                  # from network.py
    _rankings: dict[int, dict]       # port → {channel: latency_ms}
    _preferred: dict[int, str]       # port → best channel name
    _health: dict[str, ChannelHealth]  # channel → health status

    ─── Public API ───

    def http_get(port: int, path: str, timeout: float) -> bytes | None:
        """HTTP GET to Windows host:port/path via fastest channel."""

    def http_put(port: int, path: str, timeout: float) -> bytes | None:
        """HTTP PUT to Windows host:port/path via fastest channel."""

    def connect_ws(ws_url: str, timeout: float) -> PyWebSocket | None:
        """Open a WebSocket via fastest channel.

        Rewrites the URL hostname based on preferred channel:
          direct → ws://hostname.local:port/path
          tunnel → ws://localhost:port/path
          native → ws://localhost:port/path

        Returns a connected PyWebSocket or None.
        The caller (CdpSession) wraps this for CDP framing.
        """

    def rewrite_url(url: str, port: int) -> str:
        """Rewrite a URL to use the preferred channel for this port."""

    def probe(port: int) -> dict:
        """Probe all channels for a port. Return {channel: latency_ms}."""

    def is_reachable(port: int) -> bool:
        """Can we reach anything on this port via any channel?"""

    def evict(port: int) -> None:
        """Forget rankings for a port (e.g., after killing a process)."""

    def status() -> dict:
        """Full router status for observability."""

    @property
    def environment(self) -> WslEnvironment:
        """Read-only access to detected environment."""

    def select_tunnel_backend(self) -> str:
        """Pick best available tunnel backend from TUNNEL_METHODS."""

    def needs_tunnel(self) -> bool:
        """True if no fast direct channel is available."""

    def has_fast_channel(self, port: int = 9222) -> bool:
        """True if direct or tunnel is working for this port."""

    ─── Internal ───

    def _ensure_probed(port: int) -> None:
        """Lazy probe on first use per port."""

    def _ranked_channels(port: int) -> list[str]:
        """Channels sorted by latency for this port."""

    def _record_success(channel: str, latency: float) -> None
    def _record_failure(channel: str) -> None
    def _maybe_recover(channel: str) -> None:
        """Background re-probe if a channel was degraded."""


class ChannelHealth:
    ok: bool
    last_success: float | None
    last_failure: float | None
    latency_ms: float | None
    consecutive_failures: int
```

### 3.6 __init__.py — Clean Public API

```python
"""WSL Transport — adaptive networking for WSL2↔Windows communication.

Provides a unified, environment-aware transport layer that automatically
discovers the fastest available path to reach TCP ports on the Windows
host from within WSL2.

Supports multiple backends: direct socket, TCP tunnel (python_proxy,
socat, netsh, ssh), mirrored networking, curl.exe bridge, and
PowerShell bridge.

Usage:
    from src.core.services.wsl_transport import get_router

    router = get_router()
    data = router.http_get(9222, "/json/version")
    ws = router.connect_ws("ws://...:9222/devtools/page/ABC")
"""

from .environment import (
    get_environment,
    resolve_host_ip,
    is_wsl2,
    is_mirrored,
    WslEnvironment,
)
from .router import get_router, TransportRouter
from .tunnel_backends import (
    TUNNEL_METHODS,
    start_tunnel,
    stop_tunnel,
    get_active_tunnel,
    maybe_start_tunnel,
)
from .bridges import (
    warm_bridge,
    bridge_send,
    bridge_status,
    curl_get,
    curl_put,
    ps_evaluate,
)
```

---

## 4. Layer 2: CDP Protocol (cdp_client.py, simplified)

### 4.1 What cdp_client.py Becomes

After extracting transport concerns to Layer 1, cdp_client.py shrinks
significantly and focuses purely on **CDP protocol operations**.

```
cdp_client.py — AFTER refactor

    REMOVED (moved to wsl_transport):
      × _detect_wsl2()               → wsl_transport.environment
      × _get_windows_host_ip()       → wsl_transport.network
      × _get_curl_exe()              → wsl_transport.environment
      × _get_win_temp()              → wsl_transport.environment
      × _curl_exe_get/_curl_exe_put  → wsl_transport.curl_bridge
      × _bridge_* functions          → wsl_transport.ps_bridge
      × warm_bridge()                → wsl_transport.ps_bridge
      × _PyWebSocket class           → wsl_transport.websocket
      × URL rewriting logic          → wsl_transport.router
      × Strategy cascades            → wsl_transport.router

    KEPT (CDP protocol):
      ✓ CdpSession class (wraps PyWebSocket for CDP framing)
      ✓ evaluate_js() (public API, rewired through pool + router)
      ✓ get_targets() / activate_target() / is_available()
      ✓ set_endpoint()

    NEW (protocol-level orchestration):
      + _SessionPool (manages persistent CdpSession instances)
      + warm() replaces warm_bridge() (delegates to transport)
```

### 4.2 How cdp_client.py Uses Transport

```python
from src.core.services.wsl_transport import get_router

def _get_json(path, timeout=1.0, *, port=None):
    """Fetch JSON from Chrome's CDP HTTP endpoint."""
    p = port or _DEFAULT_PORT
    data = get_router().http_get(p, path, timeout)
    if data:
        return json.loads(data)
    return None

def evaluate_js(ws_url, expression, timeout=5.0, *, await_promise=False):
    """Evaluate JS in a Chrome tab via CDP."""
    # Try session pool first (0ms overhead if pooled)
    pool = _get_session_pool()
    session = pool.get(ws_url)
    if session and session.connected:
        return session.evaluate(expression, timeout=timeout,
                                await_promise=await_promise)

    # Create new session via transport
    session = CdpSession(ws_url, connect_timeout=timeout)
    if session.connected:
        pool.put(ws_url, session)
        return session.evaluate(expression, timeout=timeout,
                                await_promise=await_promise)

    # All fast paths failed — PS one-shot fallback
    from src.core.services.wsl_transport.ps_bridge import ps_evaluate
    return ps_evaluate(ws_url, expression, timeout,
                       await_promise=await_promise)
```

### 4.3 CdpSession — Simplified Constructor

```python
class CdpSession:
    def __init__(self, ws_url: str, connect_timeout: float = 10.0):
        from src.core.services.wsl_transport import get_router
        from src.core.services.wsl_transport.ps_bridge import bridge_send

        router = get_router()

        # Primary: let the transport router connect via fastest channel
        self._ws = router.connect_ws(ws_url, timeout=connect_timeout)
        if self._ws:
            self._mode = "transport"
            self._connected = True
            return

        # Fallback 1: PowerShell warm bridge
        # (bridge_send handles its own WS connection internally)
        self._mode = "bridge"
        self._connected = True  # optimistic — bridge_send checks liveness
        self._ws = None  # no PyWebSocket — commands go through bridge_send
        return

        # Note: fresh_ps mode is handled at the evaluate_js level,
        # not inside CdpSession. If both transport and bridge fail,
        # evaluate_js falls back to ps_evaluate() directly.
```

The key insight: CdpSession no longer needs 5 mode strings (python,
direct, tunnel, bridge, fresh_ps). It has two modes:
- `"transport"` — the transport router connected a PyWebSocket
- `"bridge"` — no direct WS, commands go through `bridge_send()`

The `evaluate` and `send_command` methods simplify correspondingly —
just two branches instead of five.

### 4.4 Session Pool

```python
class _SessionPool:
    """Thread-safe pool of persistent CdpSession instances.

    Keyed by (ws_url, thread_id). Each thread gets its own
    session to the same target. No cross-thread sharing.
    """

    _pool: dict[tuple[str, int], _PoolEntry]
    _lock: threading.Lock
    MAX_IDLE = 60  # seconds

    def get(ws_url: str) -> CdpSession | None:
        """Get a pooled session for this URL + current thread."""

    def put(ws_url: str, session: CdpSession) -> None:
        """Pool a session for reuse."""

    def evict_port(port: int) -> None:
        """Evict all sessions for a port (e.g., Chrome killed)."""

    def _reap_stale() -> None:
        """Remove sessions idle > MAX_IDLE."""
```

### 4.5 warm() — The New Boot Function

```python
def warm():
    """Warm the CDP infrastructure.

    Called at server startup. Delegates to transport for
    networking setup, then optionally pools a session.
    """
    from src.core.services.wsl_transport import get_router, warm_bridge

    router = get_router()  # triggers environment detection

    # Let transport decide what to warm
    env = router.environment
    if env.wsl2 and not env.mirrored:
        if not router.has_fast_channel():
            # No direct or tunnel — need PS bridge
            warm_bridge()
        # else: direct/tunnel available, no PS needed

    # Probe in background (Chrome may not be up yet)
    threading.Thread(
        target=_probe_when_ready,
        args=(router,),
        daemon=True,
    ).start()
```

---

## 5. Layer Interactions — Full Flow Diagrams

### 5.1 Boot Sequence

```
Server starts
  │
  ├─ UI calls POST /api/cdp-test/warm
  │    │
  │    └─ cdp_client.warm()                          [LAYER 2]
  │         │
  │         ├─ get_router()                          [LAYER 1]
  │         │    ├─ WslEnvironment detected:
  │         │    │    wsl2=True, mirrored=False,
  │         │    │    host_ip=172.17.128.1
  │         │    └─ Router created (no probing yet)
  │         │
  │         ├─ router.has_fast_channel()?
  │         │    ├─ host_ip exists → YES
  │         │    └─ Skip warm_bridge() (no PS process!)
  │         │
  │         └─ Background: _probe_when_ready()
  │              │
  │              ├─ router.probe(9222)               [LAYER 1]
  │              │    ├─ direct: http_get → 4ms ✓
  │              │    ├─ tunnel: not active
  │              │    ├─ curl: http_get → 180ms ✓
  │              │    └─ preferred[9222] = "direct"
  │              │
  │              └─ Log: "Transport: port 9222 preferred=direct (4ms)"
```

### 5.2 evaluate_js Call (recorder, tab_mesh, etc.)

```
recorder.py calls evaluate_js(ws_url, script)    [LAYER 3]
  │
  └─ cdp_client.evaluate_js()                     [LAYER 2]
       │
       ├─ pool.get(ws_url)?
       │    └─ Miss (first call)
       │
       ├─ CdpSession(ws_url)
       │    │
       │    └─ router.connect_ws(ws_url)            [LAYER 1]
       │         ├─ preferred[9222] = "direct"
       │         ├─ Rewrite: ws://172.17.128.1:9222/devtools/page/XYZ
       │         ├─ _PyWebSocket connects (5ms)
       │         └─ Return connected WS
       │
       ├─ session.evaluate(script) → result (8ms)
       │
       ├─ pool.put(ws_url, session)                [LAYER 2]
       │
       └─ Return result
           TOTAL: ~13ms (was ~2500ms via PS one-shot)
```

### 5.3 Replay Flow

```
replayer.py creates CdpSession(ws_url_9223)       [LAYER 3]
  │
  └─ CdpSession.__init__(ws_url)                   [LAYER 2]
       │
       └─ router.connect_ws(ws_url)                 [LAYER 1]
            ├─ Port 9223 not probed → quick probe
            ├─ direct: 5ms ✓
            ├─ preferred[9223] = "direct"
            ├─ Rewrite URL, connect
            └─ Return WS (5ms total)

replayer.py calls session.evaluate() × N steps     [LAYER 3 → 2]
  │
  └─ All go through session._ws directly
     No transport overhead per step (WS already open)

Plan done → kill_instance(9223)
  │
  ├─ cdp_client.browser_close(9223)                [LAYER 2]
  │    ├─ router.http_get(9223, "/json/version")    [LAYER 1]
  │    ├─ Get browser WS URL
  │    ├─ CdpSession → Browser.close
  │    └─ pool.evict_port(9223)                     [LAYER 2]
  │
  └─ router.evict(9223)                            [LAYER 1]
       └─ Clear rankings for this port
```

### 5.4 Fallback — No Direct Channel

```
User without netsh portproxy configured:

Boot:
  environment.py → host_ip = None (hostname.local didn't resolve)

  warm()
    router.has_fast_channel()? NO
    → Start tunnel: maybe_start_tunnel()           [LAYER 1]
    → Also: warm_bridge() (PS bridge as backup)    [LAYER 1]

  probe(9222):
    direct: FAIL (no host_ip)
    tunnel: 6ms ✓ (python_proxy started)
    curl: 180ms ✓
    → preferred[9222] = "tunnel"

  evaluate_js(ws_url, ...):
    → router.connect_ws(ws_url):
        Rewrite → ws://localhost:9222/devtools/page/XYZ
        _PyWebSocket connects via tunnel (6ms)
    → session.evaluate() (8ms)
    → TOTAL: ~14ms (still fast, tunnel works)

If tunnel ALSO fails:
    → router.connect_ws() returns None
    → CdpSession fallback → bridge (PS warm, ~100ms)
    → If bridge fails → fresh_ps (~2-3s)
    → evaluate_js PS one-shot fallback
    → Still works. Slower. But works.
```

---

## 6. What Moves Where

### 6.1 From cdp_client.py → wsl_transport/environment.py

| Function | Lines | Notes |
|----------|-------|-------|
| `_detect_wsl2()` | 56-68 | Becomes `is_wsl2()` |
| `_get_windows_host_ip()` | 69-100 | Becomes `resolve_host_ip()` |
| `_get_curl_exe()` | 102-127 | Becomes part of `WslEnvironment` |
| `_get_win_temp()` | 129-151 | Becomes part of `WslEnvironment` |
| Cache globals (`_is_wsl2`, `_curl_exe_path`, etc.) | 47-53 | Encapsulated in `WslEnvironment` |

### 6.2 From cdp_client.py → wsl_transport/bridges.py

| Function | Lines | Notes |
|----------|-------|-------|
| `_curl_exe_get()` | ~153-190 | Becomes `curl_get()` |
| `_curl_exe_put()` | ~192-220 | Becomes `curl_put()` |
| `warm_bridge()` | ~1017-1047 | Same name, new home |
| `_bridge_send()` | ~1050-1100 | Becomes `bridge_send()` |
| `_bridge_process` global | ~1010-1015 | Encapsulated in module |
| `_bridge_lock` | ~1013 | Encapsulated in module |
| PS one-shot logic from `evaluate_js()` | ~1105-1170 | Becomes `ps_evaluate()` |
| PS script generation | ~1170-1250 | Stays with `ps_evaluate()` |

### 6.3 From chrome/wsl_tunnel.py → wsl_transport/tunnel_backends.py

| Item | Notes |
|------|-------|
| Entire file | Moved with minimal changes |
| `TUNNEL_METHODS` registry | Unchanged |
| 5 backend classes | Add `is_available()` classmethod |
| Module-level API | Unchanged |

### 6.4 From launcher.py — Removed (imports from transport)

| Function | Replacement |
|----------|------------|
| `_resolve_wsl_host()` | `from wsl_transport import resolve_host_ip` |
| `is_wsl()` | `from wsl_transport import is_wsl2` |
| `_port_in_use()` | Uses `get_router().is_reachable(port)` |
| `_cdp_responding()` | Uses `get_router().is_reachable(port)` |

### 6.5 Stays in cdp_client.py (CDP protocol)

| Item | Notes |
|------|-------|
| `CdpSession` | CDP session wrapper (wraps PyWebSocket) |
| `evaluate_js()` | Public API (rewired through pool + transport) |
| `get_targets()` | Lists Chrome tabs via CDP |
| `activate_target()` | Focus a tab via CDP |
| `is_available()` | Check if CDP is reachable |
| `set_endpoint()` | Override CDP endpoint |
| `_SessionPool` | NEW — connection pooling |
| `warm()` | NEW — replaces warm_bridge() |

Note: `_PyWebSocket` moves OUT to `wsl_transport/websocket.py`.

---

## 7. Dependency Flow

```
    wsl_transport/                     ← depends on NOTHING (stdlib only)
      environment.py                      (reads /proc/version, calls shutil.which)
      network.py                          (socket, urllib — probes TCP)
      websocket.py                        (socket — raw WS client)
      tunnel_backends.py                  (socket, subprocess, threading)
      curl_bridge.py                      (subprocess)
      ps_bridge.py                        (subprocess, threading, tempfile)
      router.py                           (← all siblings above)

    chrome/                            ← depends on wsl_transport
      launcher.py                         (← wsl_transport.router.is_reachable,
                                              wsl_transport.network.resolve_host_ip,
                                              wsl_transport.environment.is_wsl2)

    ui/web/
      cdp_client.py                    ← depends on wsl_transport
                                          (← wsl_transport.router.get_router,
                                             wsl_transport.router.connect_ws,
                                             wsl_transport.ps_bridge.ps_evaluate,
                                             wsl_transport.ps_bridge.warm_bridge,
                                             wsl_transport.websocket.PyWebSocket)

    consumers (replayer, recorder,     ← depends on cdp_client only
               tab_mesh, etc.)            (no transport imports)
```

No circular dependencies. Clean unidirectional flow.

---

## 7b. Error Contract Between Layers

Layers need clear contracts for how failures propagate.

### Transport → CDP

| Transport method | Returns on success | Returns on failure | Raises |
|-----------------|-------------------|-------------------|--------|
| `router.http_get()` | `bytes` | `None` | Never |
| `router.http_put()` | `bytes` | `None` | Never |
| `router.connect_ws()` | `PyWebSocket` | `None` | Never |
| `router.is_reachable()` | `True` | `False` | Never |

The transport layer **never raises** to the CDP layer. It tries all
channels internally and returns `None` when everything has failed.
Health tracking and logging happen inside the router.

The CDP layer interprets `None` as "fall back to PS bridge."

### CDP → Consumers

| CDP method | Returns on success | Returns on failure | Raises |
|-----------|-------------------|-------------------|--------|
| `evaluate_js()` | `dict` | `None` | Never |
| `CdpSession.evaluate()` | `dict` | `None` | Never |
| `CdpSession.send_command()` | `dict` | `None` | Never |
| `get_targets()` | `list[dict]` | `[]` | Never |
| `is_available()` | `True` | `False` | Never |

Same pattern. Consumers never need try/except for CDP operations.
This is already the current contract — we preserve it.

---

## 7c. Cross-Layer Event Propagation

Some events must propagate across layers. The key ones:

### Chrome Killed → Pool + Transport

```
launcher.kill_instance(instance)                     [CHROME]
  │
  ├─ cdp_client.browser_close(port)                  [CDP]
  │    └─ Sends Browser.close via session
  │
  ├─ cdp_client.evict_port(port)                     [CDP]
  │    └─ _session_pool.evict_port(port)
  │       Closes and removes all sessions for this port
  │
  └─ wsl_transport.get_router().evict(port)           [TRANSPORT]
       └─ Clear rankings for this port
           (next request to this port will re-probe)
```

### Channel Degraded → Background Recovery

```
router.http_get fails 3x on "direct"                   [TRANSPORT]
  │
  ├─ router._record_failure("direct")
  │    └─ consecutive_failures = 3 → mark degraded
  │
  ├─ router re-ranks: preferred[9222] = "tunnel"
  │    └─ Log WARNING: "Direct channel degraded"
  │
  └─ router starts recovery thread (if not running)    [TRANSPORT]
       └─ Every 60s: try direct → if success:
            ├─ Mark recovered
            ├─ Re-probe to re-rank
            └─ Log INFO: "Direct channel recovered"

  CDP layer and consumers are UNAWARE. They just see
  http_get/connect_ws succeeding (via the new preferred channel).
```

### Tunnel Backend Fails → Fallback Selection

```
Tunnel backend (python_proxy) crashes                  [TRANSPORT]
  │
  ├─ tunnel_backends: is_running → False
  │
  ├─ router detects on next probe or connect attempt
  │    └─ "tunnel" channel fails → falls back to next
  │
  └─ If router.needs_tunnel() and no tunnel alive:
       ├─ Select next available backend
       │    (python_proxy failed → try socat → try netsh)
       ├─ Start new tunnel
       └─ Re-probe

  This is entirely within the transport layer.
  CDP and consumers see nothing.
```

---

## 8. TransportRouter — Internal Architecture

### 8.1 Channel Types

The router knows about these channel types. It doesn't know they're
used for Chrome — they're just "ways to reach a port":

| Channel | Transport | Supports | Speed |
|---------|-----------|----------|-------|
| `native` | Python socket → localhost | HTTP + WS | <1ms |
| `direct` | Python socket → hostname.local | HTTP + WS | ~5ms |
| `tunnel` | Python socket → localhost (via tunnel backend) | HTTP + WS | ~5-10ms |
| `curl` | subprocess curl.exe → localhost | HTTP only | ~180ms |
| `bridge` | subprocess powershell.exe (warm) | WS only | ~100ms |
| `fresh_ps` | subprocess powershell.exe (cold) | WS only | ~2-3s |

### 8.2 connect_ws() Logic

```
def connect_ws(ws_url: str, timeout: float) -> WebSocket | None:
    """Connect a WebSocket via the fastest available transport."""

    port = _extract_port(ws_url)
    self._ensure_probed(port)

    for channel in self._ranked_channels(port):
        if channel in ("native", "tunnel"):
            rewritten = _rewrite_ws_host(ws_url, "localhost")
        elif channel == "direct":
            rewritten = _rewrite_ws_host(ws_url, self._env.host_ip)
        else:
            continue  # curl/bridge/fresh_ps can't do raw WS connect

        try:
            ws = _PyWebSocket(rewritten, timeout=timeout)
            self._record_success(channel, ...)
            return ws
        except Exception:
            self._record_failure(channel)
            continue

    return None  # All WS-capable channels failed
```

Note: `connect_ws` returns a raw WebSocket object. It does NOT return
a CdpSession. CdpSession wraps it. This keeps transport and protocol
cleanly separated.

### 8.3 http_get() Logic

```
def http_get(port: int, path: str, timeout: float) -> bytes | None:
    """HTTP GET via the fastest available transport."""

    self._ensure_probed(port)

    for channel in self._ranked_channels(port):
        if channel in ("native", "tunnel"):
            url = f"http://localhost:{port}{path}"
        elif channel == "direct":
            url = f"http://{self._env.host_ip}:{port}{path}"
        elif channel == "curl":
            return curl_get(f"http://localhost:{port}{path}", timeout)
        else:
            continue  # bridge/fresh_ps can't do HTTP

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            self._record_success(channel, ...)
            return data
        except Exception:
            self._record_failure(channel)
            continue

    return None
```

### 8.4 Failure & Recovery

```
3 consecutive failures on a channel:
    → Mark degraded (ok=False)
    → Remove from rankings
    → Log WARNING
    → Start background recovery thread

Recovery thread (runs every 60s when something is degraded):
    → Try degraded channel with a simple HTTP GET
    → If success:
        → Mark recovered (ok=True)
        → Re-probe all channels (might want to re-rank)
        → Log INFO: "Channel X recovered"
```

---

## 9. Tunnel Backend Integration in Transport

### 9.1 Backend Selection (in router.py)

```
def _select_tunnel_backend() -> str:
    """Auto-select best available tunnel backend."""
    from .tunnel_backends import TUNNEL_METHODS

    priority = ["netsh", "python_proxy", "socat", "ssh"]
    # "mirrored" excluded — too risky for auto-selection

    for key in priority:
        method = TUNNEL_METHODS.get(key)
        if not method:
            continue
        cls = method["class"]
        if hasattr(cls, "is_available") and cls.is_available():
            return key

    return "python_proxy"  # always available
```

### 9.2 When Does the Tunnel Start?

The tunnel is started by the **CDP layer** (via `warm()`), not by the
transport layer itself. The transport layer provides the capability;
the consumer decides when to use it.

```
cdp_client.warm():                                [LAYER 2]
    router = get_router()                          [LAYER 1]
    if router.needs_tunnel():
        from wsl_transport import start_tunnel, resolve_host_ip
        backend = router.select_tunnel_backend()
        start_tunnel(9222, resolve_host_ip(), method=backend)
```

Why not auto-start in the transport layer? Because:
1. The transport layer doesn't know which ports matter
2. Starting a tunnel has side effects (threads, processes)
3. The consumer (CDP layer) knows it needs port 9222

---

## 10. What We Preserve — Everything

| Feature | Layer | Status |
|---------|-------|--------|
| Direct socket (hostname.local) | Transport | primary |
| TCP tunnel (python_proxy) | Transport | fallback |
| Socat tunnel | Transport | available, selectable |
| Netsh portproxy | Transport | available, auto-detected |
| SSH tunnel | Transport | available, manual |
| Mirrored networking | Transport | auto-detected |
| PowerShell bridge (warm) | Transport | fallback for WS |
| PowerShell one-shot | Transport | last resort |
| curl.exe HTTP bridge | Transport | HTTP fallback |
| Native Linux localhost | Transport | non-WSL primary |
| CdpSession | CDP | unchanged API |
| evaluate_js() | CDP | unchanged API, faster |
| get_targets() | CDP | unchanged API, faster |
| activate_target() | CDP | unchanged API, faster |
| Session pooling | CDP | new, transparent |
| Chrome launcher | Chrome | uses transport for port checks |
| Chrome kill (Browser.close) | CDP+Chrome | uses transport |
| All 5 tunnel backends | Transport | kept, is_available() added |

---

## 11. Migration Phases

### Phase 1: Create wsl_transport/environment.py
- Extract `_detect_wsl2`, `_get_windows_host_ip`, `_get_curl_exe`, `_get_win_temp`
- cdp_client.py imports from `wsl_transport.environment`
- launcher.py imports from `wsl_transport.environment`
- Old functions become thin wrappers temporarily
- **Verify:** Zero behavior change, all imports resolve

### Phase 2: Create wsl_transport/bridges.py
- Extract `_curl_exe_get`, `_curl_exe_put`, bridge functions, PS logic
- cdp_client.py imports from `wsl_transport.bridges`
- **Verify:** evaluate_js still works, warm_bridge still works

### Phase 3: Move wsl_tunnel.py → wsl_transport/tunnel_backends.py
- Move file, update all import paths
- Add `is_available()` to each backend class
- **Verify:** Tunnel still starts, all existing behavior

### Phase 4: Create wsl_transport/router.py
- TransportRouter with `http_get`, `connect_ws`, probing, health
- Uses environment, tunnel_backends, bridges internally
- **Verify:** Router can probe, can connect, can fallback

### Phase 5: Wire cdp_client.py through TransportRouter
- `_get_json` → `router.http_get()`
- CdpSession constructor → `router.connect_ws()`
- **Verify:** All CDP operations still work

### Phase 6: Add _SessionPool to cdp_client.py
- evaluate_js goes through pool
- Pool keyed by (ws_url, thread_id)
- **Verify:** evaluate_js ~100x faster, fallback still works

### Phase 7: Replace warm_bridge() with warm()
- New warm() function in cdp_client.py
- Delegates to transport as needed
- **Verify:** Boot sequence, no unnecessary PS processes

### Phase 8: Simplify launcher.py
- `_port_in_use` → `router.is_reachable()`
- `_cdp_responding` → `router.is_reachable()`
- Remove `_resolve_wsl_host()`, `is_wsl()`
- **Verify:** Chrome launch, kill, port detection all work

### Phase 9: Cleanup
- Remove old thin wrappers in cdp_client.py
- Remove dead code
- Update docstrings
- Package README for wsl_transport/
- **Verify:** Full end-to-end all scenarios

---

## 12. Open Design Decisions

| # | Question | Leaning | Notes |
|---|----------|---------|-------|
| 1 | Session pool: per-thread or shared? | Per-thread | No hot-path locking |
| 2 | Pool eviction: time + event | Both | 60s idle + evict on kill |
| 3 | TransportRouter: singleton or instance? | Singleton | One per process |
| 4 | Where wsl_tunnel.py moves physically | `wsl_transport/tunnel_backends.py` | Clean name |
| 5 | `_PyWebSocket` location | `wsl_transport/websocket.py` | Resolved: it's a transport primitive |
| 6 | `bridges.py` split | `curl_bridge.py` + `ps_bridge.py` | Resolved: different complexity, different concerns |
| 7 | `environment.py` split | `environment.py` + `network.py` | Resolved: capabilities ≠ topology |
| 8 | Transport router status on `/api/cdp-test/warm`? | Yes | Observability |
| 9 | Should recorder/tab_mesh eventually get their own session? | Yes, via pool | Phase 6 handles it |
| 10 | Tunnel auto-restart on crash? | Yes, in router | Transport handles internally |
| 11 | `chrome/wsl_tunnel.py` — leave a re-export stub? | Yes, for 1 release | Gradual migration |

---

## 13. Success Criteria

- [ ] `wsl_transport/` has ZERO imports from `cdp_client` or `chrome/`
- [ ] `cdp_client.py` has ZERO transport logic (no URL rewriting, no strategy cascades)
- [ ] `chrome/launcher.py` has ZERO host resolution or port-check logic of its own
- [ ] All evaluate_js callers get ~100x speedup with zero changes
- [ ] Every existing feature works unchanged
- [ ] Graceful degradation through all failure scenarios
- [ ] All 5 tunnel backends selectable and auto-ranked
- [ ] Mirrored networking auto-detected, skips all machinery
- [ ] Full observability via status endpoint
- [ ] Transport layer never raises to CDP layer (None contract)
- [ ] Cross-layer events (kill, degrade, recover) propagate correctly
- [ ] Each module in wsl_transport/ has a single, clear responsibility
