# Channel Resilience — Investigation & Analysis

**Created:** 2026-03-11
**Status:** Investigation in progress — findings from code reading
**Context:** Bug fix session revealed fundamental infrastructure gaps

---

## Finding 1: The False Positive — `direct` Works by Accident

The `direct` channel on this system works at ~6ms because **netsh portproxy
rules (9222-9232) were manually set up** at some previous point. These are
Windows-side persistent rules that forward `172.17.128.1:<port>` to
`127.0.0.1:<port>`.

**On a clean system, these rules don't exist.** The `direct` channel would
fail — `172.17.128.1:9222` would either get connection refused or hang.

Evidence from logs:
```
Transport probe port 9222: direct=6ms, curl=276ms
```

The system is fast. But it's an accident, not by design.

---

## Finding 2: `needs_tunnel()` Has a Logic Bug

**File:** `router.py:189-196`
```python
def needs_tunnel(self) -> bool:
    if not self._env.wsl2:
        return False
    if self._mirrored:
        return False
    return not self._host_ip
```

This returns True only if `resolve_host_ip()` returned None.

**The bug:** Having a host IP does NOT mean portproxy rules exist.
`resolve_host_ip()` resolves `HOSTNAME.local` via mDNS (DNS resolution).
Portproxy is a separate TCP forwarding layer. On a clean system:

- `resolve_host_ip()` → `172.17.128.1` ✅ (mDNS works)
- `needs_tunnel()` → `False` (host IP exists)
- But `direct` probe → FAILS (no portproxy rules, nothing listening)
- Tunnel never starts
- System falls to `curl` only (~300ms)

**What it should check:** Whether the `direct` probe actually succeeded,
not whether host IP resolved. The decision to start a tunnel should be
based on **probe results**, not DNS.

---

## Finding 3: Launcher Bypasses the Router

**File:** `launcher.py:172-280`

All three functions bypass the router entirely:

### _port_in_use (line 172)
```python
if is_wsl():
    host_ip = resolve_host_ip()
    if host_ip:
        urllib.request.urlopen(f"http://{host_ip}:{port}/json/version", timeout=0.05)
    else:
        curl_get(...)  # fallback
```

### _cdp_responding (line 212)
Same pattern: host_ip → urllib at 50ms → else curl_get

### _get_browser_id (line 242)
Same pattern: host_ip → urllib at 50ms → else curl_get

**The problem:** These functions have their own transport logic instead
of using the router. The 50ms timeouts are correct for `direct` but:

1. On clean system: `host_ip` resolves → uses urllib to host_ip at 50ms →
   no portproxy → TIMES OUT → returns False/None → Chrome never detected
2. The `else` branch (curl_get at 1.0s) only runs if `host_ip` is None
3. There is NO path that says "host_ip resolves but direct fails, try curl"

**Specifically:** If `resolve_host_ip()` returns an IP but portproxy isn't
set up, all three functions will ALWAYS fail at 50ms. The curl fallback
never runs because it's gated on `if not host_ip`.

---

## Finding 4: The warm() Function Partly Handles This

**File:** `cdp_client.py:349-409`

```python
def warm(port):
    router = get_router()
    probe_results = router.probe(port)

    if router.needs_tunnel():          # ← Bug from Finding 2
        backend = router.select_tunnel_backend()
        start_tunnel(...)
        probe_results = router.probe(port)  # re-probe

    if not router.has_fast_channel(port):
        warm_bridge()                  # PS bridge as last resort
```

On a clean system with mDNS working:
1. `probe(9222)` → `direct` FAILS (no portproxy), `curl` OK (~200ms)
2. `needs_tunnel()` → `False` (host_ip exists — Finding 2 bug)
3. `has_fast_channel(9222)` → `False` (only `curl` in rankings)
4. Falls to `warm_bridge()` (PS bridge)
5. But launcher still bypasses router with 50ms timeouts (Finding 3)

---

## Finding 5: Router Probe Timeout — 150ms

**File:** `router.py:362`
```python
with urllib.request.urlopen(req, timeout=0.15) as resp:
```

This applies to ALL channel probes (native, tunnel, direct). On a clean
system, probing `direct` at `http://172.17.128.1:9222` with no portproxy:
- If connection refused: fast fail, OK
- If packets dropped (firewall): hangs 150ms, then timeout, OK

150ms probe timeout is fine for discovery. The issue is what happens AFTER
discovery — the launcher ignores the discovery results.

---

## Finding 6: The 5 Tunnel Backends — Current Real Status

Investigated from `tunnel_backends.py` and `is_available()` classmethods:

| Backend | is_available() check | This system | Clean system |
|---------|---------------------|-------------|-------------|
| python_proxy (WslTunnel) | Always True | ✅ | ✅ |
| socat (SocatTunnel) | `shutil.which("socat")` | ❓ Need to check | ❌ Not default |
| netsh (NetshTunnel) | `shutil.which("powershell.exe")` | ✅ PS exists | ✅ PS exists |
| ssh (SshTunnel) | `shutil.which("ssh")` + PS | ❓ Need to check | ❓ Depends |
| mirrored (MirroredConfig) | `is_mirrored()` network check | ❌ Not mirrored | ❌ Not mirrored |

**Note:** NetshTunnel `is_available()` checks if powershell.exe exists, NOT
if netsh portproxy rules are set up. These are different questions:
- "Can we CREATE rules?" (PS available) vs "DO rules exist?" (need to query)

---

## Finding 7: The Two Different Problems

There are actually TWO problems mixed together:

### Problem A: The existing netsh portproxy rules (what makes `direct` work)
These are Windows-side forwarding rules that already exist on this system.
The `direct` channel uses them. The router probes them. This is the FAST path.

### Problem B: The NetshTunnel backend (in tunnel_backends.py)
This is code that CAN CREATE netsh portproxy rules. It's a tunnel backend
alongside python_proxy, socat, etc. But it hasn't been tested.

The confusion: the `direct` channel and the `netsh` tunnel backend both
use netsh portproxy. But `direct` is "someone already set up the rules" and
`netsh` backend is "the app sets up the rules."

If the netsh backend works, it could be the recommended AUTO-SETUP path:
app detects no portproxy → creates rules → `direct` channel works from
then on (persistent across reboots).

---

## Finding 8: Channel Level Detector Conflates DNS with Portproxy

**File:** `l0_hw_detectors.py:406-421`

```python
# Level 2: Direct channel via hostname.local (recommended, ~5ms)
if result["networking_mode"] == "mirrored":
    result["cdp_channel_level"] = 3
elif result["hostname_local_resolves"]:
    result["cdp_channel_level"] = 2       # ← BUG: assumes direct works
elif result["curl_exe_available"]:
    result["cdp_channel_level"] = 1
else:
    result["cdp_channel_level"] = 0
```

**The bug:** `hostname_local_resolves` (mDNS DNS resolution) is used as
proof that the direct channel works. But DNS resolution and netsh portproxy
are completely separate:

- `hostname.local` resolves → mDNS works → IP `172.17.128.1` known ✅
- But nothing is LISTENING at `172.17.128.1:9222` without portproxy ❌

**Impact:** The notification system gets a `cdp_channel_level = 2` and
skips the upgrade notification (which only fires at `channel_level == 1`).
So when portproxy rules are missing but hostname resolves, the user gets
NO notification that something is wrong. The system silently degrades
to curl at 260ms with no prompt.

**Same root cause as Finding 2:** The system conflates DNS resolution
with direct channel availability. This bug appears in THREE places:
1. `needs_tunnel()` in router.py (Finding 2)
2. launcher.py if/else branching (Finding 3)
3. `cdp_channel_level` computation (this finding)

**Confirmed by live test:** After removing netsh portproxy rules:
- hostname.local still resolves → detector says level 2
- But direct channel is dead → system stuck on curl at 260ms
- No notification fires to tell user to fix it

---

## Finding 9: `maybe_start_tunnel()` — Dead Code

**File:** `tunnel_backends.py:1346-1424`

This function was designed to auto-start the Python TCP Proxy tunnel
at server boot if conditions are met. It:
1. Checks `is_wsl()`
2. Resolves hostname.local
3. Calls `start_tunnel(method="python_proxy")`

**But it is NEVER CALLED anywhere.** It's exported from the module
and re-exported from `chrome/wsl_tunnel.py` but no code calls it.

This was probably the original auto-boot mechanism that got disconnected
during the refactor to the `warm()` approach. The intent was the same:
auto-provision the transport on startup.

---

## Finding 10: Live Evidence — 15-Second Stall

**Observed** after removing netsh portproxy rules (clean system test):

```
21:41:00 Chrome launched directly (wsl-pid=236897 port=9222)
21:41:15 Chrome launched (pid=236897 port=9222) but CDP not responding after 15s.
```

**15 seconds** of dead waiting. The launcher's `_cdp_responding` function
is in a retry loop calling:
```python
urllib.request.urlopen(f"http://172.17.128.1:9222/json/version", timeout=0.05)
```

Each attempt times out at 50ms (no portproxy → nothing listening).
The curl fallback never runs (gated on `if not host_ip`).
So it hammers a dead connection **~300 times** (15s ÷ 50ms) before giving up.

Then the plan executor continues anyway via PS bridge:
```
21:41:15 Plan browser launched: port=9222 pid=236897
21:41:17 CdpSession connected via fresh PS ... 804ms
21:41:22 Replay finished: 4/4 passed (6525ms)
```

**Impact:**
- Plan total: **28 seconds** instead of ~5s with portproxy
- 15s wasted on dead port checking
- ~800ms per CdpSession connect instead of ~5ms
- Tests still pass — but painfully slow

This is the clearest symptom of the launcher bypassing the router.
The router ALREADY KNOWS only curl works — but the launcher ignores that.

---

## Finding 11: Timeouts Must Be Channel-Adaptive

**Current state:** All timeouts are hardcoded:
- Launcher: 50ms (tuned for direct)
- Router probe: 150ms
- curl: 1000ms subprocess timeout

**The problem:** When the system is in slow mode (curl only), those
50ms timeouts cause guaranteed failures. When the system is in fast
mode (direct/tunnel), the timeouts are fine.

**Future vision:** The active channel defines the timeout profile.
The system needs critical timeouts (can't wait forever), but it also
needs to support slow channels without breaking.

```
┌─────────────────────────────────────────────────────────────┐
│              ADAPTIVE TIMEOUT PROFILES                      │
│                                                             │
│  Channel         │ Port check │ HTTP GET │ WS connect      │
│  ─────────────── │ ────────── │ ──────── │ ──────────       │
│  native (<1ms)   │    10ms    │   50ms   │   100ms         │
│  direct (~6ms)   │    50ms    │  100ms   │   200ms         │
│  tunnel (~5ms)   │    50ms    │  100ms   │   200ms         │
│  curl (~260ms)   │   500ms    │ 1000ms   │   N/A (no WS)   │
│  bridge (~100ms) │    N/A     │   N/A    │   500ms         │
│                                                             │
│  The router knows which channel is active.                  │
│  The launcher should ASK the router for the timeout         │
│  instead of hardcoding 50ms.                                │
│                                                             │
│  Key principle:                                             │
│  timeout = channel_latency × safety_multiplier              │
│  (e.g. 3x-5x the expected latency)                         │
│                                                             │
│  This way:                                                  │
│  • Fast channels keep tight timeouts (no wasted time)       │
│  • Slow channels get realistic timeouts (no false fails)    │
│  • System stays responsive regardless of channel mode       │
└─────────────────────────────────────────────────────────────┘
```

---

## Summary of Gaps Found

| # | Gap | Severity | Where |
|---|-----|----------|-------|
| 1 | `needs_tunnel()` checks DNS, not probe results | 🔴 Critical | router.py:189 |
| 2 | Launcher bypasses router, hardcoded 50ms | 🔴 Critical | launcher.py:172-280 |
| 3 | No curl fallback when host_ip resolves but direct fails | 🔴 Critical | launcher.py |
| 4 | `cdp_channel_level` conflates DNS with portproxy | 🔴 Critical | l0_hw_detectors.py:416 |
| 5 | Upgrade notification skipped when channel_level=2 but direct is dead | 🔴 Critical | tab_mesh/__init__.py:375 |
| 6 | 15-second stall on clean system (launcher hammers dead connection) | 🔴 Critical | launcher.py |
| 7 | Hardcoded timeouts don't adapt to channel speed | 🔴 Critical | launcher.py |
| 8 | `maybe_start_tunnel()` is dead code, never called | 🟡 Medium | tunnel_backends.py:1346 |
| 9 | Tunnel backends untested with automated tests | 🟡 Medium | tunnel_backends.py |
| 10 | NetshTunnel is_available ≠ rules exist | 🟡 Medium | tunnel_backends.py |
| 11 | No automated test for router failover | 🟡 Medium | router.py |
| 12 | No clean-system validation | 🟡 Medium | — |

---

## Open Questions for Discussion

1. Should `needs_tunnel()` check probe results instead of DNS?
2. Should the launcher functions delegate to the router?
3. Should the netsh backend auto-create rules on first boot?
4. What's the right timeout multiplier per channel?
5. How do we test this without breaking the current working system?
6. Should the router expose a `get_timeout(operation)` method
   that the launcher and cdp_client can call?

---

*Investigation ongoing. Findings updated as code is read.*

---

## The 5 Channel Methods — Detailed Code Investigation

### 1. Python TCP Proxy (`WslTunnel`) — tunnel_backends.py:53-500

**What it does:** Binds a server socket on `127.0.0.1:<port>` in WSL,
accepts TCP connections, opens a TCP connection to `<target_host>:<target_port>`
on Windows, and forwards bytes in both directions using `select.select()`.
Each connection handled in its own background thread.

**What `start()` does:** (line 245-299)
1. Calls `_ensure_windows_routing()` — this auto-creates netsh portproxy
   rules + firewall rules via elevated PowerShell if the target host isn't
   reachable. YES — the Python TCP Proxy already embeds netsh setup!
2. Binds `127.0.0.1:<port>`, starts accept loop in daemon thread.

**What `_ensure_windows_routing()` does:** (line 125-243)
1. Tests if `target_host:target_port` is reachable via TCP connect.
2. If not → writes a PS1 script that creates netsh portproxy rules for
   ports 9222-9232, listening on the host IP (NOT 0.0.0.0).
3. Runs the script via elevated PowerShell (UAC prompt).
4. Re-tests reachability after.

**is_available:** Always `True` (pure Python, zero deps).

**Key finding:** This backend is NOT just a TCP proxy — it's a TCP proxy
that auto-provisions netsh portproxy as part of its startup. So if this
backend runs, it also sets up the persistent Windows-side routing. After
that, the `direct` channel would ALSO work (because the portproxy rules
now exist).

**Gap:** `WslTunnel.start()` binds `127.0.0.1:<port>`. But if Chrome on
Windows is also accessible at that port via localhostForwarding, the bind
might conflict. Need to investigate.

---

### 2. socat Tunnel (`SocatTunnel`) — tunnel_backends.py:539-656

**What it does:** Spawns `socat TCP-LISTEN:<port>,fork,reuseaddr TCP:<host>:<port>`
as a background subprocess.

**is_available:** `shutil.which("socat") is not None` — needs socat installed.

**Key finding:** Simple subprocess wrapper. Depends on socat being installed.
No auto-provisioning. Straightforward but adds an apt dependency.

---

### 3. netsh portproxy (`NetshTunnel`) — tunnel_backends.py:659-881

**What it does:** Creates a single netsh portproxy rule via elevated PowerShell.
`listen on <host_ip>:<port> → connect to 127.0.0.1:<port>`.

**What `start()` does:** (line 707-769)
1. If `is_running` already → return True.
2. Writes netsh command to a temp PS1 file.
3. Runs via elevated PowerShell (UAC prompt).
4. Verifies rule was created via `is_running`.

**What `is_running` does:** (line 808-830)
Runs `netsh interface portproxy show v4tov4`, parses output, checks if
our port number is in the listing.

**`validate()` connects via host IP** (line 832-870) — NOT localhost.
Because netsh portproxy is Windows-side. WSL reaches it via `hostname.local`.

**Key finding:** This creates ONE rule for ONE port. Compare to WslTunnel's
`_ensure_windows_routing()` which creates rules for 9222-9232 (range).
NetshTunnel is more surgical but needs to be called per port.

**Key finding 2:** The log message on line 759 says "0.0.0.0" but the actual
listen_addr uses `self._target_host`. Minor bug in log message.

---

### 4. SSH Tunnel (`SshTunnel`) — tunnel_backends.py:884-1039

**What it does:** Spawns `ssh -N -L <port>:localhost:<port> <user>@<host>`
as a background subprocess.

**is_available:** `shutil.which("ssh")` AND `shutil.which("powershell.exe")`.
Needs SSH client in WSL + OpenSSH server running on Windows.

**Key finding:** Most complex prerequisites. Encrypted channel. Useful for
remote scenarios but overkill for local WSL↔Windows.

---

### 5. Mirrored Networking (`MirroredConfig`) — tunnel_backends.py:1042-1228

**What it does:** Edits `.wslconfig` on the Windows side to set
`networkingMode=mirrored`. After WSL restart, localhost in WSL reaches
Windows localhost natively.

**is_available:** Delegates to `network.is_mirrored()` — checks if port 135
(Windows RPC) is reachable on localhost from WSL. Only True if ALREADY mirrored.

**Key finding:** NOT a runtime tunnel. It's a configuration change that
requires WSL restart. The `start()` edits .wslconfig, `stop()` removes it.
But neither restarts WSL — user must do that manually.

**Key finding 2:** `is_available()` returns True only if already enabled.
Can't be auto-enabled without user consent + WSL restart. This is an
opt-in-only option.

---

## How Backends Map to Router Channels

| Backend | Creates this router channel | How WSL connects |
|---------|---------------------------|-------------------|
| python_proxy | `tunnel` (via localhost) | WSL → `127.0.0.1:<port>` → TCP proxy → host_ip → Chrome |
| socat | `tunnel` (via localhost) | WSL → `127.0.0.1:<port>` → socat → host_ip → Chrome |
| netsh | `direct` (via host IP) | WSL → `host_ip:<port>` → netsh portproxy → Chrome |
| ssh | `tunnel` (via localhost) | WSL → `127.0.0.1:<port>` → ssh → Windows → Chrome |
| mirrored | `native` (via localhost) | WSL → `127.0.0.1:<port>` → directly Chrome |

---

## Critical Finding: WslTunnel Auto-Provisions netsh

`WslTunnel.start()` at line 261 calls `_ensure_windows_routing()` which
creates netsh portproxy rules for ports 9222-9232 via elevated PowerShell.

This means: if the Python TCP Proxy backend is started, it:
1. Creates persistent netsh portproxy rules (survive reboots)
2. Then ALSO starts its own in-process TCP forwarder on localhost

After this runs once:
- `tunnel` channel works via the python proxy (localhost:9222)
- `direct` channel ALSO works via netsh portproxy (host_ip:9222)
- Next boot: python proxy is gone, but direct still works

The Python TCP Proxy is really a **"first-boot provisioner + temporary bridge."**

---

## Timeout Sensitivity by Channel

Hardcoded timeouts today:
- Launcher functions: 50ms (tuned for direct @ 5-20ms)
- Router probe: 150ms
- curl_get in probe: 1000ms
- curl_get in launcher fallback: 1000ms

If direct is dead and only curl works:
- Launcher 50ms → FAILS (curl needs 120ms+)
- Router probe 150ms → curl has its own 1000ms timeout via subprocess
- No adaptive logic exists

| Channel | Chrome response time | Minimum safe timeout |
|---------|---------------------|---------------------|
| `native` | <1ms | 10ms |
| `direct` (portproxy) | 5-20ms | 50ms |
| `tunnel` (python_proxy) | ~5ms | 50ms |
| `curl` | 120-300ms | 500ms |
| `bridge` | ~100ms | 300ms |

---

## Mystery Solved: Why `direct` Works Today

**The user clicked "Python TCP Proxy" once in the UI.**

That triggered this chain:
```
UI: "Python TCP Proxy" button
  → POST /tab-mesh/wsl-start-tunnel {method: "python_proxy"}
    → start_tunnel(method="python_proxy")
      → WslTunnel(9222, "172.17.128.1").start()
        → _ensure_windows_routing()
          → Tests if 172.17.128.1:9222 is reachable → NO
          → Writes PS1 script: netsh portproxy add rules for 9222-9232
          → Runs via elevated PowerShell (UAC prompt)
          → Rules created ✅ (persist across reboots)
        → Binds 127.0.0.1:9222, starts TCP proxy thread ✅
```

After this:
- `tunnel` channel works (via python proxy on localhost)
- `direct` channel ALSO works (via netsh portproxy on host IP)
- **App restarts** → python proxy thread dies → `tunnel` channel dead
- **But netsh rules survive** → `direct` channel still works at 6ms
- This is the state of the system TODAY

The Python TCP Proxy is really a **one-time Windows provisioner** that
ALSO runs a temporary TCP proxy. The permanent effect is the netsh rules.

---

## How warm() Fits In — Full Boot Flow

### Current boot sequence (this system, with portproxy rules):
```
Server starts
  → User opens CDP test panel (or plan modal)
    → Frontend calls POST /cdp-test/warm
      → cdp_client.warm(port=9222)
        → router = get_router()
          → Detects: WSL2=True, host_ip=172.17.128.1, mirrored=False
        → router.probe(9222)
          → Probe native: SKIP (WSL2 + not mirrored)
          → Probe tunnel: SKIP (no active tunnel)
          → Probe direct: http://172.17.128.1:9222 → 6ms ✅
          → Probe curl: curl.exe localhost:9222 → 276ms ✅
          → Rankings: [direct=6ms, curl=276ms]
        → router.needs_tunnel()?
          → WSL2=True, mirrored=False, host_ip exists → False
          → SKIP tunnel start
        → router.has_fast_channel(9222)?
          → direct is in rankings → True
          → SKIP PS bridge warm
        → Return status: {direct=6ms, curl=276ms, bridge=not needed}
```

### What SHOULD happen on clean system (no portproxy rules):
```
Server starts
  → User opens CDP test panel
    → POST /cdp-test/warm
      → cdp_client.warm(port=9222)
        → router.probe(9222)
          → Probe native: SKIP (WSL2)
          → Probe tunnel: SKIP (no active tunnel)
          → Probe direct: http://172.17.128.1:9222 → TIMEOUT 150ms ❌
          → Probe curl: curl.exe localhost:9222 → 276ms ✅
          → Rankings: [curl=276ms]
        → router.needs_tunnel()?
          → host_ip exists (DNS works) → False    ← BUG (Finding 2)
          → SKIP tunnel start                     ← WRONG
        → router.has_fast_channel(9222)?
          → only curl → False
          → Warms PS bridge (WS fallback)
        → Return status: {curl=276ms, bridge=warmed}
        
        NOW THE LAUNCHER TRIES TO USE CHROME:
        → _port_in_use(9222)
          → host_ip = 172.17.128.1 (resolves)
          → urllib to host_ip:9222, timeout=50ms
          → No portproxy → TIMEOUT → returns False  ← BROKEN
        → Chrome thinks port is free, tries to launch
        → OR: _cdp_responding fails → Chrome never detected as ready
```

### What SHOULD happen on clean system (FIXED):
```
Server starts
  → User opens CDP test panel
    → POST /cdp-test/warm
      → cdp_client.warm(port=9222)
        → router.probe(9222)
          → Probe direct: TIMEOUT ❌
          → Probe curl: 276ms ✅
          → Rankings: [curl=276ms]
        → router.needs_tunnel()?
          → Checks probe results: no fast channel → True  ← FIXED
          → Selects python_proxy backend
          → start_tunnel(python_proxy)
            → WslTunnel.start()
              → _ensure_windows_routing()
                → Creates netsh portproxy rules ✅ (persistent!)
              → Starts TCP proxy on localhost:9222 ✅
          → Re-probe:
            → tunnel=5ms ✅, direct=6ms ✅ (netsh just created!), curl=276ms ✅
        → has_fast_channel? → True (tunnel + direct)
        → SKIP PS bridge
        → Return status: {tunnel=5ms, direct=6ms, curl=276ms}
        
        LAUNCHER NOW WORKS:
        → _port_in_use(9222) via router → uses direct at 6ms ✅
        → Everything fast from now on
        → Next reboot: netsh rules persist, direct works immediately
```

---

## `maybe_start_tunnel()` — Dead Code

`tunnel_backends.py:1346` defines `maybe_start_tunnel()` which was
supposed to auto-start the tunnel at server boot. It:
1. Resolves hostname.local
2. Calls `start_tunnel(method="python_proxy")`

**But it is NEVER CALLED anywhere.** It's exported from the module
and re-exported from `chrome/wsl_tunnel.py` but no caller exists.

This was probably the original auto-boot mechanism before the
`warm()` function was created. It got disconnected during the refactor.

---

## The Overlap Problem

The Python TCP Proxy and netsh portproxy options overlap:

```
Python TCP Proxy (WslTunnel):
  1. Creates netsh portproxy rules (via _ensure_windows_routing)
  2. ALSO starts in-process TCP forwarder
  
  Side effects: creates BOTH tunnel + direct channels
  Permanent: netsh rules survive reboots
  Ephemeral: TCP proxy dies with app

netsh portproxy (NetshTunnel):
  1. Creates netsh portproxy rules only
  
  Side effects: creates direct channel only
  Permanent: netsh rules survive reboots
```

They both create netsh portproxy rules. The difference:
- Python TCP Proxy creates rules for 9222-9232 (range) + TCP proxy
- NetshTunnel creates a rule for ONE port only
- Python TCP Proxy's rules use the specific host IP
- NetshTunnel's rules also use the specific host IP

---
---

# PART 2: System Layers & Architecture Visualization

---

## The Full Stack — Who Calls What

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONSUMERS (Layer 1)                          │
│                                                                 │
│   replayer.py    recorder.py    plan_executor.py    tab_mesh    │
│       │              │               │                  │       │
│       └──────────────┴───────────────┴──────────────────┘       │
│                          │                                      │
│                    evaluate_js()                                 │
│                    get_targets()                                 │
│                    create_tab()                                  │
├─────────────────────────────────────────────────────────────────┤
│                    CDP PROTOCOL (Layer 2)                        │
│                    cdp_client.py                                 │
│                                                                 │
│   ┌──────────┐  ┌───────────────┐  ┌────────────────┐          │
│   │ warm()   │  │ evaluate_js() │  │ SessionPool    │          │
│   │          │  │               │  │                │          │
│   │ Probes   │  │ Pool lookup   │  │ get(ws_url)    │          │
│   │ channels │  │ → CdpSession  │  │ put(ws_url)    │          │
│   │ Starts   │  │ → evaluate    │  │ evict(port)    │          │
│   │ tunnels  │  │ → pool it     │  │ reap stale     │          │
│   └────┬─────┘  └──────┬────────┘  └────────────────┘          │
│        │               │                                        │
│        ▼               ▼                                        │
├─────────────────────────────────────────────────────────────────┤
│                TRANSPORT ROUTER (Layer 3)                       │
│                wsl_transport/router.py                          │
│                                                                 │
│   get_router() → singleton TransportRouter                      │
│                                                                 │
│   ┌─────────────────────────────────────────────────────┐      │
│   │ probe(port)        → test all channels, rank them   │      │
│   │ http_get(port,path)→ iterate ranked, return first   │      │
│   │ http_put(port,path)→ same                           │      │
│   │ connect_ws(ws_url) → iterate WS-capable channels    │      │
│   │ is_reachable(port) → any channel works?             │      │
│   │ has_fast_channel() → native/direct/tunnel working?  │      │
│   │ needs_tunnel()     → ⚠️ BUG: checks DNS not probe  │      │
│   └─────────┬───────────────────────────────────────────┘      │
│             │                                                   │
│             ▼                                                   │
├─────────────────────────────────────────────────────────────────┤
│                   CHANNELS (Layer 4)                            │
│          How bytes actually travel from WSL to Windows          │
│                                                                 │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐         │
│   │ native   │ │ tunnel   │ │ direct   │ │ curl     │         │
│   │          │ │          │ │          │ │          │         │
│   │ Python   │ │ Python   │ │ Python   │ │curl.exe  │         │
│   │ socket → │ │ socket → │ │ socket → │ │subprocess│         │
│   │localhost │ │localhost │ │ host IP  │ │→localhost│         │
│   │          │ │ (proxy)  │ │(portprxy)│ │          │         │
│   │ HTTP+WS  │ │ HTTP+WS  │ │ HTTP+WS  │ │ HTTP only│         │
│   │ <1ms     │ │ ~5ms     │ │ ~6ms     │ │~120-300ms│         │
│   └──────────┘ └──────────┘ └──────────┘ └──────────┘         │
│                                                                 │
│   When works:   When works:   When works:   When works:         │
│   - Mirrored    - Tunnel      - netsh       - Always            │
│     networking    backend       portproxy    (if curl.exe        │
│     enabled       running       rules set     exists)           │
│                                 up                              │
├─────────────────────────────────────────────────────────────────┤
│                TUNNEL BACKENDS (Layer 5)                        │
│          wsl_transport/tunnel_backends.py                       │
│          What creates / enables the channels above              │
│                                                                 │
│   ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  │
│   │ WslTunnel      │  │ SshTunnel      │  │ MirroredConfig │  │
│   │ (python_proxy) │  │                │  │                │  │
│   │                │  │ ssh -N -L      │  │ Edits          │  │
│   │ 1. netsh setup │  │ port:localhost  │  │ .wslconfig     │  │
│   │ 2. TCP proxy   │  │ :port user@host│  │ networkingMode │  │
│   │                │  │                │  │ =mirrored      │  │
│   │ Enables:       │  │ Enables:       │  │ Enables:       │  │
│   │ • tunnel ch.   │  │ • tunnel ch.   │  │ • native ch.   │  │
│   │ • direct ch.   │  │                │  │                │  │
│   │   (permanent)  │  │ Encrypted      │  │ Needs WSL      │  │
│   │                │  │ Needs OpenSSH  │  │ restart        │  │
│   │ Also includes: │  │ on Windows     │  │ May break IDE  │  │
│   │ NetshTunnel    │  │                │  │ networking     │  │
│   │ SocatTunnel    │  │                │  │                │  │
│   └────────────────┘  └────────────────┘  └────────────────┘  │
│         ▲                                                       │
│         │                                                       │
│   ┌─────┴──────────────────────────────────────────────┐       │
│   │ Sub-backends (part of the Port Forwarding family): │       │
│   │                                                    │       │
│   │ • WslTunnel: TCP proxy + netsh auto-setup          │       │
│   │ • NetshTunnel: netsh portproxy rules only          │       │
│   │ • SocatTunnel: socat subprocess (needs apt)        │       │
│   └────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Where warm() Fits

```
                          SERVER BOOT
                              │
                              ▼
                    ┌─────────────────┐
                    │  User opens     │
                    │  CDP test panel │
                    │  or Plan modal  │
                    └────────┬────────┘
                             │
                    POST /cdp-test/warm
                             │
                             ▼
              ┌──────────────────────────────┐
              │         warm(port)           │
              │      cdp_client.py:349       │
              ├──────────────────────────────┤
              │                              │
              │  1. get_router()             │
              │     └→ environment detection │
              │     └→ host IP resolution    │
              │     └→ mirrored check        │
              │                              │
              │  2. router.probe(port)       │
              │     └→ try native  → ?ms     │
              │     └→ try tunnel  → ?ms     │
              │     └→ try direct  → ?ms     │
              │     └→ try curl    → ?ms     │
              │     └→ rank by speed         │
              │                              │
              │  3. needs_tunnel()?           │
              │     ├→ YES: start tunnel     │──→ WslTunnel.start()
              │     │       re-probe         │       │
              │     │                        │       ├→ _ensure_windows_routing()
              │     └→ NO: skip              │       │    └→ netsh portproxy setup
              │                              │       │
              │  4. has_fast_channel()?       │       └→ TCP proxy thread
              │     ├→ YES: skip PS bridge   │
              │     └→ NO: warm_bridge()     │──→ PowerShell warm process
              │                              │
              │  5. Return status JSON       │
              └──────────────────────────────┘
                             │
                             ▼
                    Launcher can now use
                    the fastest channel
                    for port checks
```

---

## The 3 Real Options — Properly Named

The 5 tunnel backends are really **3 strategies** with sub-variants:

### Option 1: Port Forwarding (Recommended)
**What's under this umbrella:** WslTunnel + NetshTunnel + SocatTunnel

```
┌─────────────────────────────────────────────────────────────┐
│              OPTION 1: PORT FORWARDING                      │
│              "Set it up once, works forever"                 │
│                                                             │
│  What it does:                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1. Creates netsh portproxy rules on Windows         │   │
│  │    (WSL host IP:9222-9232 → 127.0.0.1:9222-9232)   │   │
│  │    ═══════════════════════════════════════════       │   │
│  │    These are PERMANENT. Survive reboots.            │   │
│  │    One UAC prompt. Never needed again.              │   │
│  │                                                     │   │
│  │ 2. Starts a temporary TCP proxy in the app          │   │
│  │    (127.0.0.1:9222 → host_ip:9222)                  │   │
│  │    ─────────────────────────────────────             │   │
│  │    For immediate use while netsh takes effect.       │   │
│  │    Dies with app. Not needed after first boot.      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Result:                                                    │
│  ┌────────────────┐  ┌────────────────┐                    │
│  │ tunnel channel │  │ direct channel │                    │
│  │ ~5ms           │  │ ~6ms           │                    │
│  │ (ephemeral)    │  │ (permanent)    │                    │
│  └────────────────┘  └────────────────┘                    │
│                                                             │
│  After first boot:                                          │
│  • App restarts → only direct channel remains (~6ms)        │
│  • netsh rules persist → no re-setup needed                 │
│  • TCP proxy not needed anymore                             │
│                                                             │
│  Sub-variants (same family):                                │
│  • SocatTunnel: uses socat instead of Python TCP proxy      │
│    (same netsh setup, different localhost forwarder)         │
│    Needs: apt install socat                                 │
│  • NetshTunnel: creates netsh rules without TCP proxy       │
│    (one port at a time, no temporary forwarder)             │
│                                                             │
│  Dependencies: None (pure Python + PowerShell)              │
│  Admin needed: Once (UAC for netsh setup)                   │
│  Speed: ~3-6ms                                              │
└─────────────────────────────────────────────────────────────┘
```

### Option 2: SSH Tunnel
**What's under this umbrella:** SshTunnel only

```
┌─────────────────────────────────────────────────────────────┐
│              OPTION 2: SSH TUNNEL                            │
│              "Encrypted, needs OpenSSH on Windows"          │
│                                                             │
│  What it does:                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Spawns: ssh -N -L 9222:localhost:9222 user@host     │   │
│  │                                                     │   │
│  │ Creates a local SSH port forward.                   │   │
│  │ Traffic goes through encrypted SSH channel.         │   │
│  │ NO netsh rules created. NO permanent changes.       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Result:                                                    │
│  ┌────────────────┐                                        │
│  │ tunnel channel │  (no direct channel)                   │
│  │ ~10ms          │                                        │
│  │ (ephemeral)    │                                        │
│  └────────────────┘                                        │
│                                                             │
│  After app restart: tunnel gone. Must re-establish.         │
│  No permanent changes to the system.                        │
│                                                             │
│  Dependencies: ssh client (WSL) + OpenSSH server (Windows)  │
│  Admin needed: No (but OpenSSH setup on Windows is manual)  │
│  Speed: ~10ms                                               │
│  Encryption: Yes                                            │
└─────────────────────────────────────────────────────────────┘
```

### Option 3: Mirrored Networking
**What's under this umbrella:** MirroredConfig only

```
┌─────────────────────────────────────────────────────────────┐
│              OPTION 3: MIRRORED NETWORKING                   │
│              "Fastest, but risky"                            │
│                                                             │
│  What it does:                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Edits ~/.wslconfig:                                 │   │
│  │   [wsl2]                                            │   │
│  │   networkingMode=mirrored                           │   │
│  │                                                     │   │
│  │ WSL shares Windows network stack.                   │   │
│  │ localhost in WSL = localhost in Windows.             │   │
│  │ No tunnels. No proxies. No port forwarding.         │   │
│  │ Just works™.                                        │   │
│  │                                                     │   │
│  │ ⚠️  REQUIRES WSL RESTART (wsl --shutdown)           │   │
│  │ ⚠️  May break: VS Code Remote, Docker Desktop,     │   │
│  │     IDE networking, port bindings                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Result:                                                    │
│  ┌────────────────┐                                        │
│  │ native channel │  (the gold standard)                   │
│  │ <1ms           │                                        │
│  │ (permanent)    │                                        │
│  └────────────────┘                                        │
│                                                             │
│  After WSL restart: always works. No app dependency.        │
│  But: may break other tools that rely on WSL networking.    │
│                                                             │
│  Dependencies: None                                         │
│  Admin needed: No (but WSL restart needed)                  │
│  Speed: <1ms                                                │
│  Risk: HIGH — can break IDE/Docker networking               │
└─────────────────────────────────────────────────────────────┘
```

---

## The Complete Data Flow — Per Option

### Option 1: Port Forwarding (after setup)

```
WSL (Linux)                          Windows
─────────────────────────────────    ────────────────────────────
                                    
 App (Python)                        Chrome (127.0.0.1:9222)
   │                                       ▲
   │ urllib/socket                          │
   │                                       │
   ▼                                       │
 172.17.128.1:9222  ──── netsh ────→ 127.0.0.1:9222
                         portproxy
                         (Windows kernel-level
                          TCP forwarding)
                          
 Speed: ~3-6ms
 Permanent: YES (survives reboots)
 App dependency: NONE after setup
```

### Option 2: SSH Tunnel (while running)

```
WSL (Linux)                          Windows
─────────────────────────────────    ────────────────────────────

 App (Python)                        Chrome (127.0.0.1:9222)
   │                                       ▲
   │ socket to localhost                   │
   │                                       │
   ▼                                       │
 127.0.0.1:9222 ──→ ssh process ──→ sshd ──→ 127.0.0.1:9222
                    (encrypted)     (OpenSSH
                                     server)
                                     
 Speed: ~10ms
 Permanent: NO (dies with app/ssh process)
 Encryption: YES
```

### Option 3: Mirrored Networking

```
WSL (Linux) ════════ SHARED NETWORK STACK ════════ Windows
─────────────────────────────────────────────────────────────

 App (Python)                        Chrome (127.0.0.1:9222)
   │                                       ▲
   │ socket to localhost                   │
   │                                       │
   └───────────── localhost ───────────────┘
                 (same machine, same network)
                 
 Speed: <1ms
 Permanent: YES (until .wslconfig changed)
 Risk: May break VS Code, Docker, etc.
```

---

## Fallback Stack — Always Available

```
┌───────────────────────────────────────────────────┐
│ Regardless of which option is active, these       │
│ fallbacks are ALWAYS available:                   │
│                                                   │
│  ┌─────────────────────────────────────────────┐ │
│  │ curl.exe (HTTP only, ~120-300ms)            │ │
│  │ Always works. No setup. Slow but reliable.  │ │
│  │ Can reach Chrome via Windows localhost.      │ │
│  └─────────────────────────────────────────────┘ │
│                                                   │
│  ┌─────────────────────────────────────────────┐ │
│  │ PowerShell Bridge (WS only, ~100ms)         │ │
│  │ Warm PS process. Can send CDP commands.     │ │
│  │ Last resort for WebSocket when no fast      │ │
│  │ channel exists.                             │ │
│  └─────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────┘
```
