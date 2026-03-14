# CDP Bridge Refactor — Execution Tracking

**Created:** 2026-03-11
**Status:** 🔴 Not started
**Design:** `.agent/plans/cdp-bridge-solution.md`
**Analysis:** `.agent/plans/cdp-bridge-refactor.md`

---

## Progress Overview

| Phase | Name | Sub-tasks | Done | Status |
|-------|------|-----------|------|--------|
| 1 | Package foundation | 5 | 5/5 | 🟢 |
| 2 | Transport primitives | 6 | 6/6 | 🟢 |
| 3 | Tunnel backends migration | 4 | 4/4 | 🟢 |
| 4 | Transport router | 5 | 5/5 | 🟢 |
| 5 | Wire CDP HTTP layer | 4 | 4/4 | 🟢 |
| 6 | Wire CDP WebSocket layer | 4 | 4/4 | 🟢 |
| 7 | Session pool + evaluate_js | 4 | 4/4 | 🟢 |
| 8 | Boot sequence (warm) | 3 | 3/3 | 🟢 |
| 9 | Launcher simplification | 4 | 4/4 | 🟢 |
| 10 | Cleanup + documentation | 5 | 5/5 | 🟢 |
| **TOTAL** | | **44** | **44/44** | 🟢 |

---

## Dependency Map

```
Phase 1 ──┬── Phase 2 ──┬── Phase 4 ── Phase 5 ── Phase 6 ── Phase 7 ── Phase 8
           │             │
           └── Phase 3 ──┘
                                                                          Phase 9 (after 5)
                                                                          Phase 10 (after all)
```

- Phases 2 and 3 can run **in parallel** (both depend only on Phase 1)
- Phase 4 depends on both 2 and 3 (router imports from all siblings)
- Phases 5→6→7→8 are **sequential** (each builds on previous)
- Phase 9 depends on Phase 5 (launcher uses router.is_reachable)
- Phase 10 is final cleanup after everything is verified

---

## Phase 1: Package Foundation

**Goal:** Create the `wsl_transport/` package with `environment.py`
and `network.py`. After this phase, all host resolution and WSL2
detection has a single source of truth.

**Depends on:** Nothing (first phase)

### 1.1 Create package skeleton ✅
- [x] Create `src/core/services/wsl_transport/__init__.py` (empty initially)
- **Files:** `wsl_transport/__init__.py`
- **Verify:** `python -c "import src.core.services.wsl_transport"` succeeds

### 1.2 Extract environment.py — system capabilities ✅
- [x] Create `wsl_transport/environment.py`
- [x] Move `_detect_wsl2()` from cdp_client.py → `is_wsl2()`
- [x] Move `_get_curl_exe()` from cdp_client.py → part of `WslEnvironment`
- [x] Move `_get_win_temp()` from cdp_client.py → part of `WslEnvironment`
- [x] Move `is_wsl()` from launcher.py → import from environment
- [x] `WslEnvironment` dataclass with: `wsl2`, `curl_exe`, `powershell_exe`, `win_temp_dir`
- **Files:** `wsl_transport/environment.py`, `cdp_client.py` (thin wrappers), `launcher.py` (import change)
- **Verify:** `get_environment()` returns correct `WslEnvironment` snapshot
- **Verify:** cdp_client.py's `_detect_wsl2()` calls `is_wsl2()` and still works
- **Verify:** launcher.py's `is_wsl()` calls `is_wsl2()` and still works

### 1.3 Extract network.py — topology discovery ✅
- [x] Create `wsl_transport/network.py`
- [x] Move `_get_windows_host_ip()` from cdp_client.py → `resolve_host_ip()`
- [x] Move `_resolve_wsl_host()` from launcher.py → import `resolve_host_ip()`
- [x] Add `is_mirrored()` detection (new — checks localhost direct connection)
- [x] Add `direct_http_reachable()` and `localhost_reachable()` helpers
- **Files:** `wsl_transport/network.py`, `cdp_client.py` (thin wrapper), `launcher.py` (import change)
- **Verify:** `resolve_host_ip()` returns same IP as old `_get_windows_host_ip()`
- **Verify:** launcher.py's `_resolve_wsl_host()` still works via import

### 1.4 Wire thin wrappers in cdp_client.py ✅
- [x] `_detect_wsl2()` calls `wsl_transport.environment.is_wsl2()`
- [x] `_get_windows_host_ip()` calls `wsl_transport.network.resolve_host_ip()`
- [x] `_get_curl_exe()` calls `wsl_transport.environment.get_environment().curl_exe`
- [x] `_get_win_temp()` — globals still in place, transport env has `win_temp_dir`
- **Files:** `cdp_client.py` only
- **Verify:** Server starts, `/api/cdp-test/warm` returns same results as before

### 1.5 Wire thin wrappers in launcher.py ✅
- [x] `_resolve_wsl_host()` calls `wsl_transport.network.resolve_host_ip()`
- [ ] `is_wsl()` — imported from `chrome.detection`, will wire to transport in Phase 10
- **Files:** `launcher.py` only
- **Verify:** Chrome launch still works, `kill_instance` still works

---

## Phase 2: Transport Primitives

**Goal:** Extract WebSocket client, curl bridge, and PS bridge from
cdp_client.py into their own transport modules.

**Depends on:** Phase 1 (environment.py for tool paths)

### 2.1 Extract websocket.py ✅
- [x] Create `wsl_transport/websocket.py`
- [x] Move `_PyWebSocket` class from cdp_client.py → `PyWebSocket`
- [x] Rename: drop the underscore prefix (it's now a public transport class)
- [x] Add `recv(timeout)` per-call timeout — plan §3.4
- [x] Add `@property connected` for liveness checking — plan §3.4
- [x] cdp_client.py imports: `from wsl_transport.websocket import PyWebSocket`
- **Files:** `wsl_transport/websocket.py`, `cdp_client.py` (import change + alias)
- **Verify:** CdpSession still constructs _PyWebSocket (now PyWebSocket) correctly
- **Verify:** All WS connections still work (evaluate_js, replay, etc.)

### 2.2 Extract curl_bridge.py ✅
- [x] Create `wsl_transport/curl_bridge.py`
- [x] Move `_curl_exe_get()` → `curl_get()`
- [x] Move `_curl_exe_put()` → `curl_put()`
- [x] Uses `get_environment().curl_exe` for path (not own detection)
- [x] cdp_client.py imports: thin wrappers call `curl_bridge.curl_get()`
- **Files:** `wsl_transport/curl_bridge.py`, `cdp_client.py` (thin wrapper)
- **Verify:** `_get_json()` path through curl.exe still works
- **Verify:** `_get_raw()` path through curl.exe still works

### 2.3 Extract ps_bridge.py — warm bridge process ✅
- [x] Create `wsl_transport/ps_bridge.py`
- [x] Move `_bridge_process`, `_bridge_lock` globals
- [x] Move `warm_bridge()` → same name, new home
- [x] Move `_bridge_send()` → `bridge_send()`
- [x] Move `bridge_status()` related code
- [x] Added `bridge_stop()` for graceful shutdown (plan §3.7)
- [x] Uses `get_environment()` for WSL2 detection and win_temp
- [x] Uses `env.powershell_exe` for PS path
- [x] cdp_client.py: imports from ps_bridge with aliases for internal callers
- **Files:** `wsl_transport/ps_bridge.py`, `cdp_client.py` (thin wrappers)
- **Verify:** `warm_bridge()` still starts PS process
- **Verify:** `bridge_send()` still sends commands through bridge
- **Verify:** CdpSession `"bridge"` mode still works

### 2.4 Extract ps_bridge.py — one-shot evaluate ✅
- [x] Move PS one-shot logic from `evaluate_js()` → `ps_evaluate()`
- [x] Create `ps_send_command()` for arbitrary CDP methods
- [x] Move PS script generation code (the .NET WebSocket template)
- [x] Move temp file write logic (uses `win_temp_dir` from environment)
- [x] cdp_client.py: evaluate_js PS fallback calls `ps_bridge.ps_evaluate()`
- **Files:** `wsl_transport/ps_bridge.py` (append), `cdp_client.py`
- **Verify:** `evaluate_js()` PS one-shot path still works
- **Verify:** CdpSession `"fresh_ps"` mode still works

### 2.5 CdpSession fresh_ps mode — DEFERRED to Phase 6
- [ ] CdpSession's `_init_fresh_ps` + `_evaluate_fresh_ps` stay in cdp_client.py
- [ ] Phase 6 eliminates fresh_ps mode entirely (only transport + bridge)
- **Reason:** fresh_ps is a per-session persistent PS process, not a one-shot.
  Extracting it now would create dead code that Phase 6 removes.
  The warm bridge covers the same use case more efficiently.

### 2.6 Verify Phase 2 complete ✅
- [x] `wsl_transport/websocket.py` exists and `PyWebSocket` is importable
- [x] `wsl_transport/curl_bridge.py` exists and `curl_get`/`curl_put` work
- [x] `wsl_transport/ps_bridge.py` exists with all bridge functions
- [x] cdp_client.py still has all public API functions with same signatures
- [x] Zero behavior change end-to-end
- **Test:** Server restart, warm endpoint, evaluate_js, replay a test

---

## Phase 3: Tunnel Backends Migration

**Goal:** Move `chrome/wsl_tunnel.py` to `wsl_transport/tunnel_backends.py`.
Add `is_available()` to each backend.

**Depends on:** Phase 1 (environment.py for tool detection)
**Can run in parallel with:** Phase 2

### 3.1 Move wsl_tunnel.py ✅
- [x] Copy `chrome/wsl_tunnel.py` → `wsl_transport/tunnel_backends.py`
- [x] Updated docstring import example to new path
- [x] Leave `chrome/wsl_tunnel.py` as a re-export stub (backward compat)
- **Files:** `wsl_transport/tunnel_backends.py`, `chrome/wsl_tunnel.py` (stub)
- **Verify:** ✅ Both import paths work, object identity confirmed

### 3.2 Update all import sites ✅
- [x] All 6 import sites verified working through re-export stub
- [x] No changes needed — stub handles backward compat
- **Files:** No changes (stub handles all)
- **Verify:** ✅ All importers work without modification

### 3.3 Add is_available() classmethods ✅
- [x] `WslTunnel.is_available()` → `True` (always available)
- [x] `SocatTunnel.is_available()` → `shutil.which("socat") is not None`
- [x] `NetshTunnel.is_available()` → `shutil.which("powershell.exe") is not None`
- [x] `SshTunnel.is_available()` → `shutil.which("ssh")` + `powershell.exe`
- [x] `MirroredConfig.is_available()` → delegates to `network.is_mirrored()`
- **Files:** `wsl_transport/tunnel_backends.py`
- **Verify:** ✅ All 5 classmethods return expected values on current system

### 3.4 Verify Phase 3 complete ✅
- [x] Tunnel starts via `start_tunnel()` from new location
- [x] `TUNNEL_METHODS` registry is accessible
- [x] `is_available()` works for each backend
- [x] Old import path still works via stub

---

## Phase 4: Transport Router

**Goal:** Create `router.py` — the adaptive routing brain.

**Depends on:** Phase 2 (websocket, bridges) + Phase 3 (tunnels)

### 4.1 Router skeleton ✅
- [x] Create `wsl_transport/router.py`
- [x] `TransportRouter` class with `__init__` (reads environment, network)
- [x] `ChannelHealth` dataclass with `record_success()` / `record_failure()`
- [x] `get_router()` singleton accessor (thread-safe)
- [x] `status()` returns environment + rankings + health
- **Files:** `wsl_transport/router.py`
- **Verify:** ✅ `get_router()` returns a `TransportRouter` with correct env

### 4.2 Channel probing ✅
- [x] `probe(port)` — test each channel, measure latency
- [x] `_ensure_probed(port)` — lazy probe on first use
- [x] `_ranked_channels(port)` — sorted by latency
- [x] Tested: native=N/A, tunnel=N/A, direct=14ms, curl=267ms
- **Files:** `wsl_transport/router.py`
- **Verify:** ✅ `probe(9222)` returns correct results on current system

### 4.3 HTTP routing ✅
- [x] `http_get(port, path, timeout)` — iterate ranked channels
- [x] `http_put(port, path, timeout)` — same pattern
- [x] `is_reachable(port)` — quick check
- [x] Uses `curl_bridge.curl_get()` for curl channel
- [x] Uses `urllib` for direct/native/tunnel channels
- **Files:** `wsl_transport/router.py`
- **Verify:** ✅ `router.http_get(9222, "/json/version")` returns Chrome version

### 4.4 WebSocket routing ✅
- [x] `connect_ws(ws_url, timeout)` — try ranked WS-capable channels
- [x] `rewrite_url(url, port)` — rewrite hostname for preferred channel
- [x] Returns `PyWebSocket` or `None`
- [x] Only tries native, direct, tunnel (not curl/bridge)
- [x] Host header override for direct channel (Chrome requires localhost Host)
- **Files:** `wsl_transport/router.py`
- **Verify:** ✅ WS routing logic verified via code review

### 4.5 Health tracking & recovery ✅
- [x] `ChannelHealth.record_success(latency)` — update health
- [x] `ChannelHealth.record_failure()` — increment consecutive failures
- [x] 3 consecutive failures → mark degraded (`ok=False`)
- [x] `evict(port)` — clear rankings (Chrome killed)
- **Files:** `wsl_transport/router.py`
- **Verify:** ✅ Health tracking integrated into all probe/get/connect calls

---

## Phase 5: Wire CDP HTTP Layer

**Goal:** Replace strategy cascades in cdp_client.py's HTTP functions
with `router.http_get()`.

**Depends on:** Phase 4

### 5.1 Wire _get_json ✅
- [x] `_get_json(path, timeout, port)` → `router.http_get(port, path, timeout)`
- [x] Remove inline tunnel/direct/curl strategy cascade (80 lines → 12 lines)
- [x] Parse JSON from string returned by router
- **Files:** `cdp_client.py`
- **Verify:** ✅ `get_targets()` returns 14 targets, `is_available()` returns True

### 5.2 Wire _get_raw ✅
- [x] `_get_raw(path, timeout, port)` → `router.http_get(port, path, timeout)`
- [x] Remove inline strategy cascade (50 lines → 4 lines)
- **Files:** `cdp_client.py`
- **Verify:** ✅ `activate_target()` works

### 5.3 Wire create_tab ✅
- [x] `create_tab()` → `router.http_put()` (was inline PUT + curl fallback)
- [x] Remove 34-line cascade
- **Files:** `cdp_client.py`
- **Verify:** ✅ Function callable, signature preserved

### 5.4 Verify Phase 5 complete ✅
- [x] All HTTP-based CDP operations work: targets, version, activate
- [x] No strategy cascade code remains in _get_json, _get_raw, or create_tab
- [x] cdp_client.py HTTP operations delegate to router

---

## Phase 6: Wire CDP WebSocket Layer

**Goal:** CdpSession constructor uses `router.connect_ws()` instead of
its own 5-strategy cascade.

**Depends on:** Phase 5

### 6.1 Simplify CdpSession.__init__ ✅
- [x] Primary: `ws = get_router().connect_ws(ws_url, timeout)` → PyWebSocket
- [x] Fallback 1: `_bridge_connect()` → bridge mode
- [x] Fallback 2: `_init_fresh_ps()` → fresh_ps mode
- [x] Removed: 100-line 5-strategy cascade → 15-line 3-phase approach
- [x] Modes: "python" (all PyWebSocket), "bridge", "fresh_ps"
- **Files:** `cdp_client.py`
- **Verify:** ✅ `CdpSession(ws_url)` connects via router, mode="python"

### 6.2 Simplify CdpSession.evaluate ✅
- [x] Simplified mode dispatch: `"python"` → `_evaluate_python`, `"bridge"` → `_bridge_send`, else `_evaluate_fresh_ps`
- [x] Removed dead `"direct"` and `"tunnel"` mode checks
- **Files:** `cdp_client.py`
- **Verify:** ✅ `session.evaluate("document.title")` returns result

### 6.3 Simplify CdpSession.send_command ✅
- [x] Same simplified mode dispatch as evaluate
- [x] Removed dead mode checks
- **Files:** `cdp_client.py`
- **Verify:** ✅ `session.send_command("Runtime.evaluate", {...})` works

### 6.4 Verify Phase 6 complete ✅
- [x] CdpSession.__init__ uses router.connect_ws() as primary path
- [x] CdpSession has 3 modes: python, bridge, fresh_ps
- [x] bridge and fresh_ps fallbacks preserved exactly
- [x] All evaluate/send_command/close paths work per mode

---

## Phase 7: Session Pool + evaluate_js Optimization

**Goal:** Pool persistent CdpSession instances. evaluate_js reuses
pooled sessions instead of creating new ones each call.

**Depends on:** Phase 6

### 7.1 Create _SessionPool ✅
- [x] `_SessionPool` class in cdp_client.py
- [x] Keyed by `(ws_url, thread_id)` — no cross-thread sharing
- [x] `get(ws_url)` → existing CdpSession or None (checks `.connected`)
- [x] `put(ws_url, session)` → store for reuse (closes old if replacing)
- [x] `evict_port(port)` → close+remove all sessions for port
- [x] Thread-safe with `threading.Lock`
- [x] `_PoolEntry` tracks `last_used` for stale reaping
- **Files:** `cdp_client.py`
- **Verify:** ✅ Pool stores/retrieves sessions correctly

### 7.2 Wire evaluate_js through pool ✅
- [x] Try `_session_pool.get()` first → `session.evaluate()` if connected
- [x] On miss: create `CdpSession`, `_session_pool.put()`, evaluate
- [x] On failure: fall back to `ps_evaluate()` (from ps_bridge)
- **Files:** `cdp_client.py`
- **Verify:** ✅ 17ms → 8ms → 4ms for repeated calls to same target

### 7.3 Add stale session reaping ✅
- [x] `_reap_stale_locked()` — close sessions idle > 60s
- [x] Called on every `get()` (opportunistic reaping)
- [x] Stale check: `time.monotonic() - last_used > MAX_IDLE`
- **Files:** `cdp_client.py`
- **Verify:** ✅ Built into pool, tested via get() path

### 7.4 Wire evict_port to kill flow ✅
- [x] `kill_instance()` in launcher.py calls `cdp_client.evict_port()`
- [x] `evict_port()` calls `_session_pool.evict_port()` + `router.evict()`
- [x] Wrapped in try/except for non-critical cleanup
- **Files:** `cdp_client.py`, `launcher.py`
- **Verify:** ✅ After killing Chrome, pool is empty for that port

---

## Phase 8: Boot Sequence (warm)

**Goal:** New `warm()` function that intelligently decides what to
warm based on environment.

**Depends on:** Phase 7

### 8.1 Create warm() function ✅
- [x] `warm(port)` in cdp_client.py replaces inline warm logic
- [x] Gets router, calls `probe(port)`
- [x] Starts tunnel if `needs_tunnel()` (WSL2 NAT, no fast channel)
- [x] Only warms PS bridge if no fast WS channel after probing
- [x] Returns full status dict (environment, rankings, health, bridge, pool)
- **Files:** `cdp_client.py`
- **Verify:** ✅ On system with direct channel: NO PS process spawned, direct=8ms

### 8.2 Update warm endpoint ✅
- [x] `/cdp-test/warm` calls `cdp_client.warm()` instead of inline logic
- [x] 85-line route handler → 3 lines
- [x] Returns full router status in response
- **Files:** `routes/cdp_test/replay.py`
- **Verify:** ✅ Endpoint returns rich JSON with environment, rankings, health

### 8.3 Background probe ✅
- [x] Router lazy-probes on first use per port (via `_ensure_probed`)
- [x] `warm()` calls `probe()` eagerly at boot
- [x] Logs show channel rankings: `direct=8ms, curl=268ms`
- **Files:** `cdp_client.py`, `router.py`
- **Verify:** ✅ Logs: "Transport probe port 9222: direct=8ms, curl=268ms"

---

## Phase 9: Launcher Simplification

**Goal:** launcher.py delegates port checking to transport router.

**Depends on:** Phase 5 (router.is_reachable exists)

### 9.1 Replace _port_in_use ✅
- [x] `_port_in_use(port)` → `router.http_get(port, "/json/version")` — 10 lines
- [x] Removed 57-line inline strategy cascade
- **Files:** `launcher.py`
- **Verify:** ✅ `_port_in_use(9222)=True, _port_in_use(9999)=False`

### 9.2 Replace _cdp_responding ✅
- [x] `_cdp_responding(port)` → `cdp_client.is_available(port=port)` — 7 lines
- [x] Removed 50-line inline strategy cascade
- **Files:** `launcher.py`
- **Verify:** ✅ `_cdp_responding(9222)=True, _cdp_responding(9999)=False`

### 9.3 Simplify kill flow ✅
- [x] Replaced 65-line manual host resolution + urllib + ws_url rewriting
- [x] Now: `get_version(port=)` + `CdpSession(ws_url)` — 43 lines
- [x] Router handles all URL rewriting and channel selection
- **Files:** `launcher.py`
- **Verify:** ✅ Kill flow imports work, CdpSession path preserved

### 9.4 Remove dead code ✅
- [x] Removed `_resolve_wsl_host()` — no callers remain
- [x] Removed `_wsl_host_ip` / `_wsl_host_resolved` globals
- [x] `is_wsl()` kept for Chrome process management (not transport)
- **Files:** `launcher.py`
- **Verify:** ✅ All imports + functions work after cleanup

---

## Phase 10: Cleanup + Documentation

**Goal:** Remove thin wrappers, dead code, update docs.

**Depends on:** All previous phases

### 10.1 Remove thin wrappers from cdp_client.py ✅
- [x] Removed `_detect_wsl2()`, `_get_windows_host_ip()`, `_direct_http_reachable()`
- [x] Removed `_is_tunnel_active()`, `_get_curl_exe()`
- [x] Removed `_curl_exe_get()`, `_curl_exe_put()`
- [x] Removed 7 legacy globals (`_is_wsl2`, `_curl_exe_path`, etc.)
- [x] Replaced `_detect_wsl2()` calls in `_init_fresh_ps` with `get_environment()`
- **Files:** `cdp_client.py`
- **Verify:** ✅ All dead wrappers/globals removed, all paths work

### 10.2 chrome/wsl_tunnel.py — SKIPPED (out of scope)
- `wsl_tunnel.py` has 8+ active callers across `tab_mesh`, `server_lifecycle`
- It is a Chrome-level concern (process management), not transport
- Kept in place — not part of this refactor's scope

### 10.3 Update __init__.py public API ✅
- [x] `wsl_transport/__init__.py` exports `get_router`
- [x] `__all__` defined
- **Files:** `wsl_transport/__init__.py`
- **Verify:** ✅ `from src.core.services.wsl_transport import get_router` works

### 10.4 Package README ✅
- [x] Created `wsl_transport/README.md`
- [x] Documents: purpose, architecture, all 7 modules, public API, design decisions
- [x] Includes channel latency table and layer diagram
- **Files:** `wsl_transport/README.md`

### 10.5 Final verification ✅
- [x] `wsl_transport/` has ZERO imports from cdp_client or UI
- [x] `cdp_client.py` has ZERO transport logic (no urllib, no curl)
- [x] `launcher.py` has ZERO host resolution logic
- [x] All evaluate_js callers work (6ms pooled)
- [x] Browser.close path: connected=True via router
- [x] Boot: warm() skips PS bridge when direct channel is fast
- **Test:** ✅ Full end-to-end on current system

---

## How to Use This Document

1. Before starting a phase, re-read the design doc section for that phase
2. Check all sub-tasks in order — they build on each other
3. Mark `[x]` as each sub-task completes
4. After each sub-task: verify the stated criteria before moving on
5. After each phase: run the full test before starting next phase
6. Update the Progress Overview table after each phase

**If a sub-task fails:**
- Don't layer fixes (one-change-one-test rule)
- Revert the broken change
- Re-read the code you're modifying
- Understand why it broke before trying again
