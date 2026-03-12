# CDP Bridge Refactor — Architecture Analysis & Milestone Plan

**Created:** 2026-03-11
**Status:** Analysis phase — do NOT implement until plan is agreed
**Goal:** Restructure the CDP communication layer for adaptivity, robustness, and performance — zero feature loss, zero regression

---

## 1. The Core Problem

The CDP layer does not adapt. Every operation independently discovers its
communication path through a cascade of fallback strategies. There is no
shared understanding of "what works right now" — each function re-probes
from scratch.

A WebSocket is a tunnel. Once established, it is the fastest and most
streamlined path. But the current system treats every WS connection as
disposable — open, use once, close. The HTTP layer (`_get_json`) doesn't
use WS at all. The `evaluate_js` function spawns a fresh PowerShell
process per call. Nothing shares anything.

The result: we have the highway built (direct channel, 5ms connections)
but every car takes the service road because nobody remembers the highway
exists.

---

## 2. Current Architecture — Full Map

### 2.1 Files Involved

| File | Role | Lines |
|------|------|-------|
| `src/ui/web/cdp_client.py` | HTTP API, WS bridge, CdpSession, evaluate_js | ~1700 |
| `src/core/services/chrome/launcher.py` | Launch, kill, port-check, host resolution | ~1140 |
| `src/core/services/chrome/wsl_tunnel.py` | TCP proxy backends (4 implementations) | ~1400 |
| `src/core/services/cdp_test/replayer.py` | Test execution — main consumer of CDP | ~2800 |
| `src/core/services/cdp_test/recorder.py` | Recording — uses evaluate_js | ~200 |
| `src/core/services/cdp_port_injector.py` | Injects JS into pages — uses evaluate_js | ~200 |
| `src/ui/web/routes/tab_mesh/__init__.py` | Tab focus — uses evaluate_js | ~1000 |
| `src/ui/web/routes/cdp_test/replay.py` | Warm endpoint — calls warm_bridge + start_tunnel | ~360 |
| `src/ui/web/routes/cdp_test/recording.py` | Recording routes — uses evaluate_js | ~1000 |

### 2.2 Communication Channels (what exists today)

There are two conceptual layers: **transport** (how bytes reach Chrome)
and **protocol** (HTTP vs WebSocket). The router must understand both.

```
    ┌─────────────────────────────────────────────────────────────┐
    │                     WSL2 Python Process                      │
    │                                                             │
    │  ═══════════════ TRANSPORT LAYER ═══════════════════════    │
    │                                                             │
    │  ┌─ Transport A: Direct Socket ────────────────────────┐    │
    │  │  Python socket → hostname.local:PORT → Chrome        │    │
    │  │  Requires: netsh portproxy + firewall rule            │    │
    │  │  Speed: ~5ms connect, instant send/recv               │    │
    │  │  Supports: HTTP and WebSocket                         │    │
    │  │  Port-aware: YES — any port                           │    │
    │  │  Status: PRIMARY — works for all ports today          │    │
    │  └──────────────────────────────────────────────────────┘    │
    │                                                             │
    │  ┌─ Transport B: Tunnel (localhost proxy) ─────────────┐    │
    │  │  Python → localhost:PORT → tunnel backend             │    │
    │  │          → hostname.local:PORT → Chrome               │    │
    │  │  Supports: HTTP and WebSocket (transparent TCP)       │    │
    │  │  Port-aware: per-port listener required               │    │
    │  │  Status: ACTIVE — only port 9222 today                │    │
    │  │                                                       │    │
    │  │  Backend implementations (see §2.6):                  │    │
    │  │    python_proxy  ~5ms   ← CURRENT (only one tested)   │    │
    │  │    socat         ~5ms   ← available, not tested       │    │
    │  │    netsh         ~3ms   ← available, not tested       │    │
    │  │    ssh           ~10ms  ← available, not tested       │    │
    │  │    mirrored      <1ms   ← RISKY, not tested           │    │
    │  └──────────────────────────────────────────────────────┘    │
    │                                                             │
    │  ┌─ Transport C: PowerShell WS Bridge ─────────────────┐    │
    │  │  Python stdin → powershell.exe → .NET WebSocket       │    │
    │  │          → localhost:PORT → Chrome                     │    │
    │  │  Speed: ~3s cold start, ~100ms per command warm        │    │
    │  │  Supports: WebSocket only                              │    │
    │  │  Port-aware: YES — URL passed per command              │    │
    │  │  Status: FALLBACK — used when A+B unavailable          │    │
    │  └──────────────────────────────────────────────────────┘    │
    │                                                             │
    │  ┌─ Transport D: PowerShell One-Shot ──────────────────┐    │
    │  │  Python → subprocess.run(powershell.exe) per call      │    │
    │  │          → .NET WebSocket → Chrome                     │    │
    │  │  Speed: ~2-3s per call (PS startup each time)          │    │
    │  │  Supports: WebSocket only                              │    │
    │  │  Port-aware: YES — URL passed per call                 │    │
    │  │  Status: LAST RESORT — used by evaluate_js today       │    │
    │  └──────────────────────────────────────────────────────┘    │
    │                                                             │
    │  ┌─ Transport E: curl.exe HTTP Bridge ─────────────────┐    │
    │  │  Python → subprocess.run(curl.exe) → Chrome HTTP       │    │
    │  │  Speed: ~50-200ms per call                             │    │
    │  │  Supports: HTTP only                                   │    │
    │  │  Port-aware: YES — URL passed per call                 │    │
    │  │  Status: HTTP FALLBACK — when A+B fail for HTTP        │    │
    │  └──────────────────────────────────────────────────────┘    │
    │                                                             │
    │  ┌─ Transport F: Native localhost ─────────────────────┐    │
    │  │  Python socket → localhost:PORT → Chrome              │    │
    │  │  Speed: <1ms                                          │    │
    │  │  Supports: HTTP and WebSocket                         │    │
    │  │  Status: NON-WSL only (or WSL mirrored networking)    │    │
    │  └──────────────────────────────────────────────────────┘    │
    │                                                             │
    │  ═══════════════ PROTOCOL LAYER ═══════════════════════     │
    │                                                             │
    │  HTTP operations: _get_json, _get_raw, activate_target      │
    │    Can use: A, B, E, F                                      │
    │                                                             │
    │  WebSocket operations: evaluate, send_command, Browser.close │
    │    Can use: A, B, C, D, F                                   │
    │    Persistent session: A, B, C, F                            │
    │    One-shot only: D                                          │
    │                                                             │
    └─────────────────────────────────────────────────────────────┘
```

### 2.6 Tunnel Backend Registry (wsl_tunnel.py)

The tunnel system (`wsl_tunnel.py`) already has a plugin-style registry
(`TUNNEL_METHODS`) with 5 implementations sharing a common interface:
`start()`, `stop()`, `is_running`, `validate()`, `stats`.

Only `python_proxy` has been tested in production. The others are
implemented but untested. The router must treat the tunnel backend as
**interchangeable** — any of them makes `localhost:PORT` work.

| Key | Backend | Speed | Prerequisites | Risk | Tested |
|-----|---------|-------|---------------|------|--------|
| `python_proxy` | WslTunnel | ~5ms | None (pure Python) | None | ✅ Production |
| `socat` | SocatTunnel | ~5ms | `apt install socat` | None | ❌ Not tested |
| `netsh` | NetshTunnel | ~3ms | UAC elevation (one-time), persists across reboots | None | ❌ Not tested |
| `ssh` | SshTunnel | ~10ms | OpenSSH client + server on Windows | None | ❌ Not tested |
| `mirrored` | MirroredConfig | <1ms | Edits `.wslconfig`, WSL restart required | ⚠️ **HIGH** — can break VS Code, Docker Desktop, IDE networking | ❌ Not tested |

**Key design constraint:** The router MUST NOT hardcode `python_proxy`.
It should:
1. Check which backends are available (prerequisites met)
2. Let the user configure preference (or auto-select best available)
3. Switch to a different backend if the active one fails

**Future opportunity:** `netsh` is the fastest (~3ms) and persists across
reboots — zero runtime overhead. If the user has already granted UAC
elevation via the existing `_ensure_windows_routing()` flow, netsh
portproxy is already active. The router should detect this and skip
starting a tunnel entirely (it's already there).

**Mirrored networking note:** If mirrored mode is active (detectable via
`/proc/sys/net/ipv4/conf/eth0/` or checking if localhost connects
directly), ALL tunnel machinery is unnecessary. Native localhost works.
The router should detect this and use Transport F directly.

### 2.3 Host Resolution (duplicated)

| Function | Location | Mechanism | Cache |
|----------|----------|-----------|-------|
| `_resolve_wsl_host()` | launcher.py:177 | `hostname` → socket.getaddrinfo | Module-level globals |
| `_get_windows_host_ip()` | cdp_client.py:69 | `hostname` → socket.getaddrinfo | Module-level globals |

Both do **the same thing** independently with separate caches.

### 2.4 Strategy Cascades (every function re-discovers)

Each function that talks to Chrome has its own strategy cascade:

| Function | Strategies (in order) |
|----------|----------------------|
| `_get_json()` | tunnel → direct → curl.exe |
| `_get_raw()` | tunnel → direct → curl.exe |
| `_port_in_use()` | direct/json → curl.exe → socket |
| `_cdp_responding()` | direct → curl.exe → urllib |
| `CdpSession.__init__()` | tunnel → direct → python → bridge → fresh_ps |
| `evaluate_js()` | PowerShell one-shot only (no adaptation) |
| `kill_instance()` | /json/version HTTP → CdpSession → taskkill |
| `activate_target()` | calls `_get_raw()` which cascades |

**Every call re-probes.** If the direct channel worked 1ms ago, the next
function call doesn't know that — it starts from tunnel again.

### 2.5 Call Site Inventory — evaluate_js

These are the places that still use the slow PowerShell one-shot path
instead of a persistent session:

| File | Call Count | Context |
|------|------------|---------|
| `recorder.py` | 6 | Recording sessions — inject, update, stop, get events |
| `recording.py` (routes) | 2 | Start/stop recording |
| `tab_mesh/__init__.py` | 2 | Read __meshTabId, fill JS |
| `cdp_port_injector.py` | 1 | Inject port into pages |
| `replayer.py` | 1 | Fallback when session is down |

Each of these pays ~2-3s per call via PowerShell subprocess.

---

## 3. What the Refactored System Should Look Like

### 3.1 Design Principles

1. **Discover once, remember forever** — probe available channels at boot,
   cache the result, re-probe only on failure
2. **Prefer persistent connections** — a WS connection that's already open
   is always faster than opening a new one
3. **No feature removal** — every channel (A-F) stays available as fallback
4. **Adaptive degradation** — if the fast channel fails, fall back
   transparently and log a warning
5. **Single source of truth for host IP** — one resolution function, one cache
6. **Port-aware** — the system must work for port 9222 (user Chrome) AND
   9223+ (plan-launched Chrome)

### 3.2 Proposed Architecture: The Channel Router

The router is the single brain that knows what works. Everything else
asks it. It manages three concerns:
- **Environment detection** (WSL2? mirrored? native Linux?)
- **Transport selection** (which channel to use for this port)
- **Session lifecycle** (connection pooling, health, eviction)

```
    ┌──────────────────────────────────────────────────────────────┐
    │                     CdpChannelRouter                         │
    │                                                              │
    │  ┌─ Environment (discovered once) ───────────────────────┐   │
    │  │  wsl2 = True                                           │   │
    │  │  mirrored = False  (if True → use Transport F, done)   │   │
    │  │  host_ip = "172.17.128.1"  (resolved once)             │   │
    │  └────────────────────────────────────────────────────────┘   │
    │                                                              │
    │  ┌─ Transport Ranking (probed per port) ─────────────────┐   │
    │  │  Port 9222: [direct 4ms, tunnel 6ms, curl 180ms]       │   │
    │  │  Port 9223: [direct 5ms, curl 200ms]  (no tunnel)      │   │
    │  │  Preferred: fastest that succeeded                      │   │
    │  │  Re-probe: on sustained failure only                    │   │
    │  └────────────────────────────────────────────────────────┘   │
    │                                                              │
    │  ┌─ Tunnel Backend (one active at a time) ───────────────┐   │
    │  │  Uses TUNNEL_METHODS registry from wsl_tunnel.py        │   │
    │  │  Selected by: availability check + user preference      │   │
    │  │  Current: python_proxy (tested)                         │   │
    │  │  Available: socat, netsh, ssh, mirrored                 │   │
    │  │  Interface: start(), stop(), is_running, validate()     │   │
    │  └────────────────────────────────────────────────────────┘   │
    │                                                              │
    │  ┌─ Public API ──────────────────────────────────────────┐   │
    │  │                                                        │   │
    │  │  http_get(port, path) → dict | None                    │   │
    │  │    Uses preferred transport for HTTP                    │   │
    │  │    Fallback chain: direct → tunnel → curl.exe           │   │
    │  │                                                        │   │
    │  │  get_session(ws_url) → CdpSession                      │   │
    │  │    Returns pooled session or creates new one            │   │
    │  │    Uses preferred transport for WS connect              │   │
    │  │    Fallback: bridge → fresh_ps                          │   │
    │  │                                                        │   │
    │  │  evaluate(ws_url, js, **kw) → dict | None              │   │
    │  │    Session pool → session.evaluate(js)                  │   │
    │  │    Fallback: PS one-shot                                │   │
    │  │                                                        │   │
    │  │  browser_close(port) → bool                            │   │
    │  │    Session to browser WS → Browser.close                │   │
    │  │    Fallback: taskkill.exe                               │   │
    │  │                                                        │   │
    │  └────────────────────────────────────────────────────────┘   │
    │                                                              │
    │  ┌─ Health Tracking ─────────────────────────────────────┐   │
    │  │  direct:  ok=True   last_success=17:05:49  latency=5ms │   │
    │  │  tunnel:  ok=True   last_success=17:05:36  latency=6ms │   │
    │  │  bridge:  ok=True   last_success=never     latency=N/A │   │
    │  │  curl:    ok=True   last_success=never     latency=N/A │   │
    │  │  native:  ok=False  (WSL2, not mirrored)               │   │
    │  │                                                        │   │
    │  │  On failure: mark degraded → try next → log warning     │   │
    │  │  On recovery: re-probe after backoff → upgrade path     │   │
    │  └────────────────────────────────────────────────────────┘   │
    │                                                              │
    └──────────────────────────────────────────────────────────────┘
```

### 3.3 Key Concept: Session Pool

Instead of creating a new CdpSession per replay run or per evaluate_js
call, the router maintains a pool of sessions keyed by `ws_url`:

```
    _session_pool = {
        "ws://172.17.128.1:9222/devtools/page/ABC123": CdpSession(connected, direct, 5s old),
        "ws://172.17.128.1:9223/devtools/page/DEF456": CdpSession(connected, direct, 2s old),
        "ws://172.17.128.1:9223/devtools/browser/...": CdpSession(connected, direct, 10s old),
    }
```

When `evaluate(ws_url, js)` is called:
1. Check pool for existing session to this ws_url
2. If connected → use it (0ms overhead)
3. If stale/dead → remove, create new session via preferred channel
4. If all channels fail → fall back to evaluate_js one-shot (PS)

This eliminates the 5-20ms CdpSession connect overhead per step in replay,
and completely eliminates the ~2-3s PowerShell overhead for evaluate_js callers.

### 3.4 Key Concept: Environment & Channel Probe

At server startup (or on first CDP operation):

```python
def _probe_environment():
    """Detect the runtime environment once."""
    env = {
        "wsl2": _detect_wsl2(),
        "mirrored": False,
        "host_ip": None,
    }

    if not env["wsl2"]:
        # Native Linux — localhost works directly
        return env

    # Check for mirrored networking (localhost works natively)
    # If localhost:9222 connects AND hostname.local resolves to 127.0.0.1,
    # we're likely in mirrored mode.
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        sock.connect(("localhost", 9222))
        sock.close()
        env["mirrored"] = True  # localhost works — no tunneling needed
        return env
    except (ConnectionRefusedError, OSError):
        pass

    # Standard WSL2 — resolve host IP
    env["host_ip"] = resolve_wsl_host_ip()  # single shared function
    return env


def _probe_channels(port: int = 9222):
    """Probe all available transports and rank by speed."""
    results = {}
    env = _probe_environment()

    # Mirrored networking — native localhost, fastest possible
    if env["mirrored"]:
        t0 = time.monotonic()
        try:
            urllib.request.urlopen(
                f"http://localhost:{port}/json/version", timeout=1)
            results["native"] = time.monotonic() - t0
        except: pass
        if results:
            return "native", results

    # Direct (hostname.local via netsh portproxy)
    if env["host_ip"]:
        t0 = time.monotonic()
        try:
            urllib.request.urlopen(
                f"http://{env['host_ip']}:{port}/json/version", timeout=1)
            results["direct"] = time.monotonic() - t0
        except: pass

    # Tunnel (localhost via active tunnel backend)
    if is_tunnel_active(port):
        t0 = time.monotonic()
        try:
            urllib.request.urlopen(
                f"http://localhost:{port}/json/version", timeout=1)
            results["tunnel"] = time.monotonic() - t0
        except: pass

    # curl.exe (subprocess bridge — always available on WSL2)
    curl = get_curl_exe()
    if curl:
        t0 = time.monotonic()
        try:
            r = subprocess.run(
                [curl, "-s", "--connect-timeout", "1",
                 f"http://localhost:{port}/json/version"],
                capture_output=True, timeout=3)
            if r.returncode == 0:
                results["curl"] = time.monotonic() - t0
        except: pass

    # Rank by speed — fastest wins
    preferred = min(results, key=results.get) if results else "curl"
    return preferred, results
```

The result is stored and reused. Re-probe only on sustained failure.

### 3.5 Key Concept: Tunnel Backend Selection

The router does not hardcode which tunnel backend to use. It queries
the `TUNNEL_METHODS` registry and selects based on availability:

```python
def _select_tunnel_backend():
    """Pick the best available tunnel backend."""
    from src.core.services.chrome.wsl_tunnel import TUNNEL_METHODS

    # Priority order (configurable in future)
    priority = ["netsh", "python_proxy", "socat", "ssh"]
    # "mirrored" excluded from auto-selection (too risky)

    for key in priority:
        method = TUNNEL_METHODS.get(key)
        if not method:
            continue
        cls = method["class"]
        # Check prerequisites (each backend knows its own)
        if hasattr(cls, "is_available") and not cls.is_available():
            continue
        return key

    return "python_proxy"  # always available (pure Python)
```

**Note:** `is_available()` is a class method that checks prerequisites:
- socat: `shutil.which("socat")` is not None
- netsh: check if portproxy rule already exists (no UAC needed if so)
- ssh: `shutil.which("ssh")` and OpenSSH on Windows
- python_proxy: always True

This will need to be added to each backend class (currently missing).

---

## 4. Detailed Change Map

### 4.1 Host Resolution — Unify

- **Delete** `_resolve_wsl_host()` from launcher.py
- **Delete** `_get_windows_host_ip()` from cdp_client.py
- **Create** a single `resolve_wsl_host_ip()` in a shared location
  (either cdp_client.py or a new `src/core/services/chrome/host_resolution.py`)
- All callers import from one place

### 4.2 Channel Router — New Module

Create `src/core/services/chrome/cdp_router.py` (or integrate into cdp_client.py):

```
class CdpRouter:
    """Adaptive CDP communication router.

    Discovers the fastest available channel at boot and routes all
    CDP traffic through it. Maintains a session pool for persistent
    WebSocket connections. Falls back transparently on failure.
    """

    def http_get(port, path) -> dict | None
    def http_put(port, path) -> str | None
    def get_session(ws_url) -> CdpSession
    def evaluate(ws_url, js, **kw) -> dict | None
    def browser_close(port) -> bool
    def probe_channels(port) -> dict
```

### 4.3 _get_json / _get_raw — Simplify

Replace the inline 3-strategy cascade with:
```python
def _get_json(path, timeout=1.0, *, port=None):
    return _router.http_get(port or _DEFAULT_PORT, path)
```

The router handles the cascade internally.

### 4.4 evaluate_js — Keep but Wire Through Router

`evaluate_js()` function signature stays the same (backward compatible).
Internal implementation changes from "always PS one-shot" to:

```python
def evaluate_js(ws_url, expression, timeout=5.0, *, await_promise=False):
    # Try persistent session first (0ms overhead if pooled)
    result = _router.evaluate(ws_url, expression, timeout=timeout,
                              await_promise=await_promise)
    if result is not None:
        return result

    # Fallback: original PS one-shot (preserved for robustness)
    return _evaluate_js_powershell(ws_url, expression, timeout,
                                   await_promise=await_promise)
```

All 10+ callers get faster without any code changes.

### 4.5 CdpSession — Simplify Constructor

The current constructor has 5 strategies inline. Move strategy selection
to the router:

```python
class CdpSession:
    def __init__(self, ws_url, connect_timeout=10.0):
        # Let the router decide the best channel
        self._ws = _router.connect_ws(ws_url, timeout=connect_timeout)
        self._mode = _router.preferred_channel
        self._connected = self._ws is not None
```

The router's `connect_ws` method tries channels in order of preference.

### 4.6 warm_bridge — Becomes Conditional

The bridge warmup only runs if the probe determines that the bridge is
needed (i.e., direct and tunnel channels both failed):

```python
def warm():
    preferred, results = probe_channels()
    if preferred in ("direct", "tunnel"):
        # No bridge needed — skip PS startup
        return
    # Bridge or curl is the best we have — pre-warm
    warm_bridge()
```

### 4.7 Tunnel — Port-Aware & Backend-Aware

The current tunnel only covers port 9222. Plan-launched Chrome uses
9223+. This needs a two-part solution:

**Part 1: Multi-port support**

**Option A:** Start additional tunnels for plan ports (simple, one
thread per port). Router calls `start_tunnel(port)` when a plan
browser launches.

**Option B:** Make the tunnel dynamic — when a connection comes in
for an unknown port, start a new listener (more complex).

**Option C:** Don't tunnel plan ports — use direct channel only
(simplest, works today). Tunnel remains for port 9222 where it
serves as the fallback when direct is unavailable.

**Recommendation:** Option C for now. Direct channel is the primary
path and works for all ports. Tunnel is the safety net for port 9222.
Revisit if direct proves unreliable.

**Part 2: Backend selection**

The router should integrate with `TUNNEL_METHODS` so that:
- At boot, it checks which backends have their prerequisites met
- It auto-selects the fastest available backend
- The user can override via configuration (future: UI setting)
- If the active backend fails, it can switch to another

Decision tree for tunnel backend:
```
    Is mirrored networking active?
    └─ YES → No tunnel needed. Use native localhost.
    └─ NO  → Is netsh portproxy already configured?
             └─ YES → No tunnel needed. Direct channel works.
             └─ NO  → Is socat installed?
                      └─ YES → Use socat (fast, external process)
                      └─ NO  → Use python_proxy (zero deps, built-in)
    
    (SSH is available as manual override for encrypted scenarios)
    (Mirrored is available as manual override, with risk warning)
```

### 4.8 kill_instance — Simplify

```python
def kill_instance(self, instance):
    if is_wsl():
        # Use the router to send Browser.close
        killed = _router.browser_close(instance.port)
        if not killed:
            # Fallback: taskkill with stored PID
            subprocess.run(["taskkill.exe", "/F", "/T", "/PID", ...])
    else:
        os.kill(instance.pid, signal.SIGTERM)
```

### 4.9 Port Check — Simplify

```python
def _port_in_use(port):
    return _router.http_get(port, "/json/version") is not None

def _cdp_responding(port):
    return _router.http_get(port, "/json/version") is not None
```

These become trivial because the router handles the channel selection.

---

## 5. Session Lifecycle — How Persistent WS Works

### 5.1 The Flow Today (per replay)

```
replay_suite() called
  → CdpSession(ws_url) — connect WS (5-20ms)
  → session.evaluate(js) × N steps
  → session falls out of scope → GC closes WS
```

Each replay creates and destroys a session. This is fine for replay
(5ms overhead amortized over seconds of steps). But evaluate_js callers
(recorder, tab_mesh) create a SUBPROCESS per call.

### 5.2 The Flow After Refactor

```
evaluate_js(ws_url, js) called
  → router.evaluate(ws_url, js)
    → check pool for existing session to this ws_url
    → if live session: session.evaluate(js) — 0ms overhead
    → if no session: create CdpSession, pool it, evaluate
    → if session dead: remove from pool, create new, retry
    → if all WS fail: fall back to PS one-shot
```

The session pool automatically manages lifecycle:
- Sessions are created on demand
- Sessions are reused across calls (same target)
- Sessions are evicted when the target goes away
- Sessions are evicted after a max idle time (e.g., 60s)
- Pool is cleared when Chrome instance is killed

### 5.3 Thread Safety

The session pool must be thread-safe because:
- Replay runs in a background thread
- Recording runs in a background thread
- Tab mesh runs in request threads
- Port injector can run from SSE thread

Use a `threading.Lock` around pool operations. Individual sessions
are not shared across threads — each thread gets its own session
to a given target.

---

## 6. What We Preserve

| Feature | Preserved? | Notes |
|---------|-----------|-------|
| Direct socket channel (hostname.local) | ✅ | Becomes primary |
| TCP tunnel (python_proxy) | ✅ | Stays as fallback for port 9222 |
| Socat tunnel backend | ✅ | Available via TUNNEL_METHODS, selectable |
| Netsh portproxy backend | ✅ | Available via TUNNEL_METHODS, auto-detected |
| SSH tunnel backend | ✅ | Available via TUNNEL_METHODS, manual select |
| Mirrored networking detection | ✅ | Auto-detected, skips all tunnel machinery |
| PowerShell bridge (warm) | ✅ | Only starts if direct+tunnel fail |
| PowerShell one-shot | ✅ | Last resort fallback in evaluate |
| curl.exe HTTP bridge | ✅ | Last resort for HTTP operations |
| Native Linux path | ✅ | Direct socket, no WSL shenanigans |
| Multi-port support (9222, 9223+) | ✅ | Router is port-aware |
| Browser.close kill | ✅ | Via router.browser_close |
| taskkill fallback | ✅ | When Browser.close fails |

---

## 7. Migration Steps (Ordered)

### Phase 1: Unify Host Resolution
- Single `resolve_wsl_host_ip()` function
- All callers reference the same cache
- Zero behavioral change

### Phase 2: Create CdpRouter
- New class with `http_get`, `connect_ws`, `evaluate`
- Wraps existing functions — doesn't replace them yet
- Channel probing at first use
- Internal session pool

### Phase 3: Wire evaluate_js Through Router
- evaluate_js internals change to try session pool first
- All 10+ callers get faster with zero changes
- PS one-shot remains as fallback
- Verify: recorder, tab_mesh, port_injector all still work

### Phase 4: Wire _get_json/_get_raw Through Router
- Replace inline cascade with router.http_get
- Verify: all HTTP API calls still work
- _port_in_use and _cdp_responding simplify

### Phase 5: Conditional Bridge Warmup
- warm_bridge() only runs when needed
- Saves ~3s boot time when direct channel works

### Phase 6: CdpSession Constructor Simplification
- Move strategy cascade into router.connect_ws
- CdpSession constructor becomes thin
- Verify: replay, recording, kill all still work

### Phase 7: Cleanup
- Remove duplicated code
- Update docstrings
- Remove debug logging added during this investigation
- Verify full system end-to-end

---

## 8. Risk Assessment

| Risk | Mitigation |
|------|------------|
| Session pool returns stale session | Health check before reuse (try small command) |
| Thread contention on pool lock | Lock is held briefly (dict lookup/insert) |
| Channel probe wrong at boot (Chrome not running yet) | Re-probe on first failure |
| Direct channel stops working mid-session | Catch error, mark degraded, fallback |
| Regression in evaluate_js callers | Phase 3 preserves exact same API |
| Recorder needs different ws_url per target | Pool is keyed by ws_url — handles naturally |

---

## 9. Open Questions

1. **Where does CdpRouter live?**
   - Option A: In `cdp_client.py` (keep everything together)
   - Option B: In new `src/core/services/chrome/cdp_router.py` (clean separation)
   - Leaning toward A because cdp_client.py already has all the building blocks

2. **Session pool eviction policy?**
   - Time-based (60s idle)?
   - Event-based (Chrome instance killed → flush pool)?
   - Both?

3. **Should tunnel cover plan ports (9223+)?**
   - Current: tunnel only covers 9222
   - Proposed: no change — direct channel handles 9223+
   - Revisit if direct channel proves unreliable for plan ports

4. **Naming: evaluate_js → evaluate?**
   - Keep `evaluate_js` as the public API (backward compatible)
   - Internal implementation routed through pool
   - Or deprecate and add `cdp_evaluate` as the new name?

---

## 10. Success Criteria

After refactor is complete:

- [ ] `evaluate_js` calls complete in <50ms instead of ~2-3s
- [ ] CdpSession connects in <10ms for any port
- [ ] Browser.close works reliably on first attempt
- [ ] No PowerShell process spawned at boot when direct channel works
- [ ] All existing tests and replays pass unchanged
- [ ] Graceful fallback when direct channel is unavailable
- [ ] Single host resolution cache shared by all code
- [ ] Log output clearly shows which channel is being used
- [ ] Tunnel backend is auto-selected based on available prerequisites
- [ ] Mirrored networking is detected and uses native localhost
- [ ] Router re-probes and recovers when a channel degrades
- [ ] All 5 tunnel backends remain functional and selectable
