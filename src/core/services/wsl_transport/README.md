# wsl_transport

Adaptive networking layer for WSL2↔Windows communication.

## Purpose

In WSL2 (non-mirrored/NAT mode), processes running inside Linux cannot
directly reach `localhost` on the Windows host.  Chrome's DevTools
Protocol (CDP) listens on `127.0.0.1` in Windows, making it unreachable
from WSL2 without special transport handling.

This package provides a **unified, environment-aware transport layer**
that automatically discovers and selects the fastest available path to
reach TCP ports on the Windows host.

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Layer 3: Consumers                             │
│  (recorder, replayer, tab_mesh, plan_executor)  │
│                                                 │
│  → evaluate_js(), CdpSession(), get_targets()   │
├─────────────────────────────────────────────────┤
│  Layer 2: CDP Protocol (cdp_client.py)          │
│                                                 │
│  → Session pool, warm(), evict_port()           │
│  → Delegates ALL networking to Layer 1          │
├─────────────────────────────────────────────────┤
│  Layer 1: WSL Transport (this package)          │
│                                                 │
│  → TransportRouter: channel discovery, ranking  │
│  → HTTP: router.http_get(), router.http_put()   │
│  → WS:  router.connect_ws()                     │
│  → Env:  WSL2 detection, tool discovery         │
│  → Net:  host resolution, mirrored detection    │
└─────────────────────────────────────────────────┘
```

## Modules

### `environment.py`
System capability detection.  Answers: Are we in WSL2?  Is
`curl.exe` available?  Is `powershell.exe` available?  Where is the
Windows temp directory?

- `WslEnvironment` — frozen dataclass with all detection results
- `get_environment()` — cached singleton
- `is_wsl2()` — quick boolean check

### `network.py`
Host resolution and reachability.

- `resolve_host_ip()` — resolves `HOSTNAME.local` via mDNS (cached)
- `is_mirrored()` — detects WSL2 mirrored networking mode
- `direct_http_reachable()` — TCP probe to verify connectivity

### `websocket.py`
Minimal WebSocket client implementing RFC 6455.  Protocol-agnostic —
used by the router and CDP sessions for raw WS connections.

- `PyWebSocket` — send/recv/close over a raw TCP socket
- Handles upgrade handshake, framing, masking, close frames

### `curl_bridge.py`
HTTP requests via `curl.exe` subprocess.  Reaches Windows-side
`localhost` from WSL2 by running in the Windows namespace.

- `curl_get()` — HTTP GET via curl.exe
- `curl_put()` — HTTP PUT via curl.exe

### `ps_bridge.py`
PowerShell bridge for WebSocket communication.  Provides two modes:

1. **Warm bridge** — persistent PowerShell process with pre-loaded
   WebSocket classes.  ~3s cold start, then <50ms per command.
2. **One-shot** — `ps_evaluate()` for standalone JS evaluation.

- `warm_bridge()` — start the background PS process
- `bridge_send()` — send a CDP command via the warm process
- `bridge_status()` — health check
- `ps_evaluate()` — one-shot JS evaluation

### `tunnel_backends.py`
TCP tunnel implementations for forwarding ports from WSL2 to Windows.

- `start_tunnel()` — factory function selecting the best backend
- Backends: `python_proxy`, `socat`, `netsh`, `ssh`
- `get_active_tunnel()` — check for running tunnel

### `router.py`
The **TransportRouter** — the central intelligence of the package.

- `get_router()` — cached singleton
- `probe(port)` — test all channels, rank by latency
- `http_get(port, path)` — HTTP GET via fastest channel
- `http_put(port, path)` — HTTP PUT via fastest channel
- `connect_ws(ws_url)` — WebSocket via fastest channel
- `has_fast_channel(port)` — check if a <100ms channel exists
- `needs_tunnel()` — true if WSL2 NAT mode with no fast channel
- `status()` — full status dict for observability

#### Channel Priority (by latency)

| Channel | Mechanism | Typical Latency |
|---------|-----------|-----------------|
| native | Python socket to localhost | <1ms |
| tunnel | Python socket through TCP proxy | ~2ms |
| direct | Python socket to hostname.local | ~5-20ms |
| curl | curl.exe subprocess | ~150-300ms |

## Public API

```python
from src.core.services.wsl_transport import get_router

router = get_router()

# HTTP
data = router.http_get(9222, "/json/version")
result = router.http_put(9222, "/json/new?http://example.com")

# WebSocket
ws = router.connect_ws("ws://localhost:9222/devtools/page/ABC")
ws.send('{"id":1,"method":"Runtime.evaluate","params":{"expression":"1+1"}}')
response = ws.recv()

# Status
status = router.status()
# → { environment: {...}, network: {...}, rankings: {...}, health: {...} }
```

## Design Decisions

1. **No upward imports** — this package NEVER imports from `cdp_client`,
   `launcher`, or any UI layer.  It is a pure transport layer.

2. **Lazy initialization** — the router singleton is created on first
   use.  Environment detection and channel probing happen once.

3. **Latency-ranked channels** — every channel is probed and ranked.
   The fastest channel is always tried first, with automatic fallback.

4. **Health tracking** — channels track consecutive failures and are
   temporarily demoted to avoid repeated timeout penalties.

5. **Thread-safe** — the router and all its channels are safe to use
   from multiple threads concurrently.
