# Channel Resilience Implementation Plan

**Source:** `.agent/plans/channel-resilience-analysis.md` (12 findings)
**Date:** 2026-03-11
**Status:** In Progress

**Completed:**
- ✅ Chunk 1: Router Foundation (needs_tunnel fix + timeout profiles)
- ✅ Chunk 2: Channel Level Detector (real TCP probe)
- ✅ Chunk 4: Warm-up Notification (notify, don't auto-install)

**Remaining:**
- ✅ Chunk 3: Launcher Delegation (router-delegated, 15s stall killed)
- ⬜ Chunk 5: Notification System verification
- ⬜ Chunk 6: Dead Code Cleanup

---

## Goal

Make WSL transport channels resilient on ANY system — clean install
or pre-configured. The system must:

1. Work at whatever speed is available (even curl at 260ms)
2. Detect the gap and auto-provision fast channels when possible
3. Notify the user when manual action is needed
4. Never stall on dead connections (adaptive timeouts)
5. Never conflate DNS resolution with actual connectivity

---

## Current State (What's Broken)

```
CLEAN SYSTEM (no portproxy rules):

  warm() fires
    → router.probe(9222): only curl=260ms works
    → needs_tunnel()? host_ip resolves → False        ← BUG
    → no tunnel started                                ← WRONG
    → has_fast_channel()? → False
    → warms PS bridge                                  ← SLOW FALLBACK
    
  launcher tries to use Chrome:
    → _cdp_responding: urllib to host_ip:9222 at 50ms
    → no portproxy → 15 second stall                   ← CATASTROPHIC
    → eventually falls back to PS bridge at ~800ms
    
  notification check:
    → cdp_channel_level: hostname resolves → level 2   ← BUG
    → upgrade notification: level != 1 → skipped       ← SILENT FAILURE
```

---

## Target State (What It Should Do)

```
CLEAN SYSTEM (no portproxy rules):

  warm() fires
    → router.probe(9222): only curl=260ms works
    → needs_tunnel()? no fast channel in probe → True  ← FIXED
    → creates imminent notification: "Port Forwarding Needed"
    → does NOT auto-install (no surprise UAC prompts)
    → has_fast_channel()? → False
    → warms PS bridge (slow but works)
    
  user sees notification:
    → toast: "CDP Channel: Port Forwarding Needed"
    → clicks → WSL Channel Setup modal opens
    → picks "Port Forwarding" → UAC prompt (consented)
    → netsh rules created → fast channel works
    
  launcher uses router (after Chunk 3):
    → router.is_reachable(9222) at channel-aware timeout
    → no 15s stall even on curl-only
    
  notification check:
    → cdp_channel_level: actual TCP probe → level 1   ← ACCURATE
    → upgrade notification fires correctly ✅

AFTER USER SETS UP PORT FORWARDING:
    → warm() re-probes: direct=6ms, curl=260ms
    → has_fast_channel() → True ✅
    → PS bridge NOT needed
    → notification dismissed
```

---

## Architecture Principle

```
┌─────────────────────────────────────────────────────────────┐
│  SINGLE SOURCE OF TRUTH: TransportRouter                    │
│                                                             │
│  Everything asks the router. Nothing goes around it.        │
│                                                             │
│  The router knows:                                          │
│  • Which channels are alive (from probe results)            │
│  • How fast each channel is (from probe timings)            │
│  • What timeout to use for the active channel               │
│  • Whether a tunnel is needed (from probe, not DNS)         │
│                                                             │
│  Consumers:                                                 │
│  • warm() asks router → decides tunnel start                │
│  • launcher asks router → port check, CDP detection         │
│  • cdp_client asks router → HTTP/WS transport               │
│  • detector asks router → channel level for notifications   │
│                                                             │
│  Nobody does their own urllib/socket with hardcoded timeout. │
└─────────────────────────────────────────────────────────────┘
```

---
---

# IMPLEMENTATION CHUNKS

Each chunk is independently verifiable. Each chunk leaves the system
in a working state. Foundation first, then infrastructure, then features.

---

## Chunk 1: Router Foundation — `needs_tunnel()` Fix + Timeout Profiles

**Files:** `wsl_transport/router.py`
**Fixes:** Finding 2 (needs_tunnel bug), Finding 11 (adaptive timeouts)
**Dependencies:** None (foundation)

### What to change

**1a. Fix `needs_tunnel()` to use probe results:**

Current (BROKEN):
```python
def needs_tunnel(self) -> bool:
    if not self._env.wsl2:
        return False
    if self._mirrored:
        return False
    return not self._host_ip     # ← checks DNS, not probe
```

Fixed:
```python
def needs_tunnel(self, port: int = 9222) -> bool:
    """Whether a tunnel should be started.
    
    Returns True when:
    - Running on WSL2
    - Not mirrored networking
    - No fast channel (native/direct/tunnel) found for this port
    
    This checks ACTUAL PROBE RESULTS, not just DNS resolution.
    DNS can resolve (mDNS works) but the direct channel can still
    be dead (no portproxy rules).
    """
    if not self._env.wsl2:
        return False
    if self._mirrored:
        return False
    return not self.has_fast_channel(port)
```

**1b. Add timeout profile to router:**

```python
# Channel timeout profiles (multiplier of ~3-5x expected latency)
_TIMEOUT_PROFILES = {
    "native":  {"port_check": 0.010, "http_get": 0.050, "ws_connect": 0.100},
    "tunnel":  {"port_check": 0.050, "http_get": 0.100, "ws_connect": 0.200},
    "direct":  {"port_check": 0.050, "http_get": 0.100, "ws_connect": 0.200},
    "curl":    {"port_check": 0.500, "http_get": 1.000, "ws_connect": None},
    "bridge":  {"port_check": None,  "http_get": None,  "ws_connect": 0.500},
}
# Fallback when no channel is probed yet
_FALLBACK_PROFILE = {"port_check": 0.500, "http_get": 1.000, "ws_connect": 1.000}

def get_timeout(self, operation: str, port: int = 9222) -> float:
    """Get the appropriate timeout for the given operation.
    
    Uses the fastest known channel for this port to determine
    the timeout. Falls back to conservative timeouts if no
    channel has been probed.
    
    Args:
        operation: "port_check", "http_get", or "ws_connect"
        port: CDP port (default 9222)
    
    Returns:
        Timeout in seconds.
    """
    rankings = self._rankings.get(port)
    if rankings:
        fastest_channel = rankings[0][0]  # (channel_name, latency)
        profile = self._TIMEOUT_PROFILES.get(
            fastest_channel, self._FALLBACK_PROFILE
        )
    else:
        profile = self._FALLBACK_PROFILE
    
    timeout = profile.get(operation)
    if timeout is None:
        # Operation not supported on this channel
        return self._FALLBACK_PROFILE[operation] or 1.0
    return timeout
```

### How to verify

```bash
# 1. Remove portproxy rules (already done)
# 2. Restart server
# 3. Check logs:
#    - probe should show: curl=260ms (no direct, no tunnel)
#    - needs_tunnel() should return True (before: returned False)
#    - get_timeout("port_check") should return 0.500 (before: hardcoded 0.050)
```

**Key test:** `needs_tunnel()` with portproxy removed:
- Before fix: returns False (DNS resolves → thinks direct works)
- After fix: returns True (no fast channel in probe)

### What NOT to change yet

- Do NOT change the launcher yet (Chunk 3)
- Do NOT change warm() yet (Chunk 4)
- Do NOT change the detector yet (Chunk 2)
- Only change router.py

---

## Chunk 2: Channel Level Detector — Real Probe

**Files:** `core/services/audit/l0_hw_detectors.py`
**Fixes:** Finding 8 (cdp_channel_level conflates DNS with portproxy)
**Dependencies:** Chunk 1 (router needs probe-based needs_tunnel)

### What to change

**2a. Fix `cdp_channel_level` to use actual connectivity test:**

Current (BROKEN):
```python
if result["networking_mode"] == "mirrored":
    result["cdp_channel_level"] = 3
elif result["hostname_local_resolves"]:
    result["cdp_channel_level"] = 2       # ← assumes direct works
elif result["curl_exe_available"]:
    result["cdp_channel_level"] = 1
```

Fixed — add a real TCP probe after DNS resolution:
```python
if result["networking_mode"] == "mirrored":
    result["cdp_channel_level"] = 3
elif result["hostname_local_resolves"]:
    # DNS resolves, but is something actually LISTENING?
    # Quick TCP probe to host_ip:9222 (the default CDP port)
    if _tcp_reachable(result["hostname_local_ip"], 9222, timeout=0.2):
        result["cdp_channel_level"] = 2   # Direct channel works
    elif result["curl_exe_available"]:
        result["cdp_channel_level"] = 1   # DNS works but no portproxy
    else:
        result["cdp_channel_level"] = 0   # DNS works but nothing else
elif result["curl_exe_available"]:
    result["cdp_channel_level"] = 1
```

Add helper:
```python
def _tcp_reachable(host: str, port: int, timeout: float = 0.2) -> bool:
    """Quick TCP connect test — does something answer?"""
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False
```

### How to verify

```bash
# With portproxy removed:
# - hostname.local resolves → True
# - _tcp_reachable(172.17.128.1, 9222) → False (no portproxy)
# - cdp_channel_level → 1 (curl only)
# Before fix: cdp_channel_level was 2 (wrong)
```

### What NOT to change yet

- Do NOT change the notification logic (that's downstream — it will
  automatically fire correctly once channel_level is accurate)
- Do NOT change the UI

---

## Chunk 3: Launcher Delegation — Use Router, Not Direct urllib

**Files:** `core/services/chrome/launcher.py`
**Fixes:** Finding 3, 6, 10 (launcher bypass, 15s stall)
**Dependencies:** Chunk 1 (router has get_timeout + probe-based decisions)

### What to change

**3a. `_port_in_use()` — delegate to router:**

Current (BROKEN):
```python
def _port_in_use(port):
    host_ip = _resolve_host_ip()
    if host_ip:
        # urllib to host_ip:port with 50ms timeout
        ...
    else:
        # curl.exe fallback
        ...
```

Fixed — ask the router:
```python
def _port_in_use(port):
    """Check if something is listening on the CDP port.
    
    Delegates to the TransportRouter which knows the best channel
    and appropriate timeout for the current system state.
    """
    from src.core.services.wsl_transport.router import get_router
    try:
        router = get_router()
        return router.is_reachable(port)
    except Exception:
        return False
```

**3b. `_cdp_responding()` — delegate to router:**

Current (BROKEN):
```python
def _cdp_responding(port, timeout):
    host_ip = _resolve_host_ip()
    if host_ip:
        # urllib to host_ip:port/json/version with 50ms timeout
        # Retry loop for 15 seconds
        ...
```

Fixed:
```python
def _cdp_responding(port, timeout=15):
    """Wait for CDP to become responsive on the given port.
    
    Uses the TransportRouter to check via the best available channel
    with appropriate timeouts.
    """
    from src.core.services.wsl_transport.router import get_router
    import time
    
    router = get_router()
    deadline = time.monotonic() + timeout
    check_interval = 0.5  # check every 500ms, not every 50ms
    
    while time.monotonic() < deadline:
        try:
            resp = router.http_get(port, "/json/version")
            if resp is not None:
                return True
        except Exception:
            pass
        time.sleep(check_interval)
    
    return False
```

**3c. `_get_browser_id()` — delegate to router:**

Same pattern — use `router.http_get(port, "/json/version")` instead
of raw urllib with hardcoded timeout.

### How to verify

```bash
# With portproxy removed:
# 1. Launch a plan
# 2. Check that Chrome launch does NOT stall for 15 seconds
# 3. _cdp_responding should poll at 500ms intervals via router
#    using curl channel at appropriate timeout
# 4. Total wait should be proportional to curl latency, not 15s stall
#
# Expected log:
#   Chrome launched directly (wsl-pid=XXXX port=9222)
#   Chrome launched (pid=XXXX port=9222) CDP responding after ~2-3s
#   (not 15s)
```

### What NOT to change yet

- Do NOT change warm() auto-provisioning (Chunk 4)
- Do NOT remove _resolve_host_ip() yet — other code may use it

---

## Chunk 4: Warm-up Notification (DESIGN CHANGED) ✅ DONE

**Files:** `ui/web/cdp_client.py`, `_notifications.html`
**Fixes:** Finding 2 chain — but via notification, NOT auto-install
**Dependencies:** Chunk 1 (needs_tunnel now works correctly)

### Design Decision

Original plan: warm() auto-calls `start_tunnel()` → UAC prompt.
**User rejected this** — too aggressive. Auto-triggering UAC without
consent is bad UX.

New design: warm() creates an **imminent notification** instead.
The notification:
- Uses `dedup=True` → only one exists at a time
- Has `priority: "imminent"` → auto-shows error-level toast
- Has `action_tab: "wsl-channel"` → click opens WSL Channel Setup modal
- User chooses when (and whether) to act

### What was changed

```python
# BEFORE: auto-install (removed)
if router.needs_tunnel():
    start_tunnel(python_proxy)  # → UAC prompt without consent

# AFTER: notify (implemented)
if router.needs_tunnel(port):
    create_notification(
        notif_type="wsl_channel_setup",
        title="CDP Channel: Port Forwarding Needed",
        message="No fast channel... Set up port forwarding...",
        meta={"priority": "imminent", "action_tab": "wsl-channel"},
        dedup=True,
    )
```

Also added `⚡` icon for `wsl_channel_setup` in `_notifications.html`.

### Verified

- Import OK
- Server starts without error
- Notification creation path is exercised when needs_tunnel() = True

---

## Chunk 5: Notification System — Accurate Gap Detection

**Files:** `ui/web/routes/tab_mesh/__init__.py`
**Fixes:** Finding 5 (upgrade notification skipped)
**Dependencies:** Chunk 2 (detector now returns accurate channel_level)

### What to change

With Chunk 2, `cdp_channel_level` is now accurate:
- Clean system with no portproxy → level 1 (not level 2)
- The existing notification code at line 375:
  ```python
  if channel_level == 1 and not tunnel_active:
      # Create "CDP Channel: Upgrade Available" notification
  ```
  This should now fire correctly because channel_level IS 1.

**Verify the notification flow works end-to-end:**
1. Server starts on clean system
2. warm() fires but UAC is cancelled (no portproxy created)
3. System stays on curl
4. Tab mesh panel or CDP status endpoint is hit
5. `_check_wsl_interop_notifications()` runs
6. `cdp_channel_level = 1` (accurate now)
7. Upgrade notification fires ✅

**If needed:** Adjust the notification text to be clearer about what
"upgrade" means — it should say "Set up Port Forwarding" not just
"configure hostname.local resolution."

### How to verify

```bash
# With portproxy removed AND warm's auto-provision blocked:
# 1. Start server
# 2. Check notification badge
# 3. Should see: "CDP Channel: Upgrade Available"
# 4. Message should explain: curl.exe bridge is slow, set up
#    port forwarding via Tab Mesh → Setup
```

---

## Chunk 6: Dead Code Cleanup

**Files:** `wsl_transport/tunnel_backends.py`, `chrome/wsl_tunnel.py`
**Fixes:** Finding 9 (maybe_start_tunnel dead code)
**Dependencies:** Chunk 4 (warm() is the official auto-provision path)

### What to change

**6a. Remove or deprecate `maybe_start_tunnel()`:**

Since warm() is now the official auto-provisioning path (Chunk 4),
`maybe_start_tunnel()` is confirmed dead code. Options:
- Remove it entirely from tunnel_backends.py
- Remove it from the chrome/wsl_tunnel.py re-export stub
- Or mark it deprecated with a log warning if called

**6b. Review NetshTunnel vs WslTunnel overlap:**

Now that we understand WslTunnel creates netsh rules as a side effect:
- NetshTunnel creates ONE rule for ONE port
- WslTunnel creates rules for 9222-9232 range + TCP proxy

Decision needed: keep both (for manual single-port use) or consolidate.
Recommendation: keep both but document the relationship clearly.

### How to verify

```bash
# grep for maybe_start_tunnel — should have no callers
# Run full test suite to verify nothing breaks
```

---
---

# EXECUTION ORDER

```
✅ Chunk 1: Router Foundation ──────────────── FOUNDATION (DONE)
   │     needs_tunnel() uses probe results + get_timeout()
   │
   ├──✅ Chunk 2: Channel Level Detector ────── INFRASTRUCTURE (DONE)
   │     _tcp_reachable() instead of DNS-as-proof
   │
   ├──✅ Chunk 4: Warm-up Notification ─────── FEATURE (DONE)
   │     notify instead of auto-install (design changed)
   │
   ├──✅ Chunk 3: Launcher Delegation ─────── INFRASTRUCTURE (DONE)
   │     use router, kill 15s stall
   │     Files: launcher.py + router.py (_ensure_probed)
   │
   ├──⬜ Chunk 5: Notification System ─────── FEATURE
   │     verify end-to-end with accurate channel_level
   │     Files: tab_mesh/__init__.py
   │
   └──⬜ Chunk 6: Dead Code Cleanup ───────── CLEANUP
         remove maybe_start_tunnel, document overlap
         Files: tunnel_backends.py, wsl_tunnel.py
```

---

# VERIFICATION MATRIX

Each chunk has a before/after verification:

| Chunk | Test Scenario | Before Fix | After Fix |
|-------|---------------|------------|-----------|
| 1 | `needs_tunnel()` on clean system | Returns False | Returns True |
| 1 | `get_timeout("port_check")` on curl-only | N/A (50ms hardcoded) | 500ms |
| 2 | `cdp_channel_level` on clean system | 2 (wrong) | 1 (correct) |
| 3 | Chrome launch on clean system | 15s stall | ~2-3s via router |
| 3 | `_port_in_use` on clean system | 50ms timeout, fail | 500ms via curl |
| 4 | warm() on clean system | Skips tunnel | Creates imminent notification |
| 4 | Notification type | N/A | `wsl_channel_setup` (deduped) |
| 5 | Notification on clean system | Silent (level 2) | "Upgrade Available" |
| 6 | `maybe_start_tunnel` callers | 0 (dead code) | Removed |

---

# RISK MITIGATION

**Before ANY chunk:** Verify the system still works WITH portproxy.
Each chunk must not break the existing fast path.

**Rollback plan per chunk:**
- Chunk 1: Revert router.py only
- Chunk 2: Revert l0_hw_detectors.py only
- Chunk 3: Revert launcher.py only
- Chunk 4: Verify warm() path, maybe no code changes needed
- Chunk 5: Revert tab_mesh/__init__.py notification text only
- Chunk 6: Git revert dead code removal

**Test both states after each chunk:**
1. WITH portproxy rules → everything still fast
2. WITHOUT portproxy rules → improved behavior per chunk

---

# CONTEXT RECOVERY

If context is lost, the AI should:

1. Read THIS document first
2. Read the analysis: `.agent/plans/channel-resilience-analysis.md`
3. Check which chunks are done (look at git log)
4. Resume from the next incomplete chunk
5. NEVER skip ahead — chunks must be done in order

Key files to understand the system:
- `src/core/services/wsl_transport/router.py` — transport router
- `src/core/services/chrome/launcher.py` — Chrome launcher
- `src/ui/web/cdp_client.py` — CDP client + warm()
- `src/core/services/wsl_transport/tunnel_backends.py` — tunnel backends
- `src/core/services/audit/l0_hw_detectors.py` — WSL interop detector
- `src/ui/web/routes/tab_mesh/__init__.py` — notification logic
