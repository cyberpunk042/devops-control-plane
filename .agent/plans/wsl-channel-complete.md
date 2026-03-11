# WSL↔Windows Channel — Complete Solution Plan

## Status: DRAFT — Awaiting Review

---

## Goal

Make WSL2 and Windows TALK. Create an interactive system where:
1. The system **detects** the current WSL↔Windows channel state
2. The user **sees** their current operability level and ALL available upgrade options
3. The user **chooses** which remediation to apply (multiple choices per layer)
4. The system **executes** the chosen remediation
5. The system **validates** the result end-to-end

This is NOT just detection or notifications. This is building the actual
network channel and giving the user control over HOW it gets built.

---

## Current State (What Exists)

| What | Status | Where |
|------|--------|-------|
| WSL detection | ✅ Works | `detection.py:is_wsl()`, `l0_hw_detectors.py:_detect_wsl_interop()` |
| Hostname resolution detection | ✅ Works | `l0_hw_detectors.py` — DNS resolve test |
| curl.exe detection | ✅ Works | `detection.py:get_curl_exe()` |
| .wslconfig parsing | ✅ Works | `l0_hw_detectors.py:_parse_wslconfig()` |
| Operability level computation | ⚠️ Partial | Computed but based on DNS only, not actual connectivity |
| Notifications (backend) | ⚠️ Exists | Created in `_check_wsl_interop_notifications()` but missing key types |
| Notifications (frontend) | ⚠️ Exists | Icons + click action registered but no useful flow |
| **Network tunnel** | ❌ Missing | No tunnel exists — no way to forward traffic |
| **Interactive remediation UI** | ❌ Missing | No choices, no buttons, no setup flow |
| **Firewall rule creation** | ⚠️ Endpoint exists | `POST /tab-mesh/wsl-fix-firewall` but no UI to trigger it |
| **curl.exe install** | ⚠️ Endpoint exists | `POST /tab-mesh/wsl-install-curl` but no UI |
| **Tunnel management** | ❌ Missing | No socat, no netsh, no Python proxy, nothing |
| **Validation** | ⚠️ Endpoint exists | `POST /tab-mesh/wsl-validate` but no UI |

---

## Architecture: 5 Layers × Multiple Choices

### Layer 1: Network Channel (THE TUNNEL)

**What:** How does traffic get from WSL Python to Windows Chrome on port 9222?

**Current state:** ❌ No tunnel. Uses curl.exe subprocess as a workaround.

**Choices (user picks one):**

| # | Choice | How It Works | Prerequisites | Speed | Risk |
|---|--------|-------------|---------------|-------|------|
| 1A | **Python TCP Proxy** | Background thread in Flask app. Listens on WSL localhost:9222, forwards to Windows host IP:9222 | hostname.local resolves OR gateway IP known + firewall rule | ~5ms | None — runs in-process |
| 1B | **socat tunnel** | `socat TCP-LISTEN:9222,fork TCP:$(hostname).local:9222` as background process | socat installed + hostname resolves + firewall rule | ~5ms | Needs socat package |
| 1C | **netsh portproxy** | `netsh interface portproxy add v4tov4 listenport=9222 listenaddress=0.0.0.0 connectport=9222 connectaddress=127.0.0.1` on Windows | Elevated PowerShell + firewall rule | ~3ms | Persistent Windows config |
| 1D | **SSH tunnel** | `ssh -L 9222:localhost:9222 user@$(hostname).local` | OpenSSH on Windows + SSH key/password | ~10ms | Needs SSH server running |
| 1E | **curl.exe bridge** (current) | Subprocess call to Windows curl.exe for each request | curl.exe on PATH | ~2000ms | Slow, spawns process per call |
| 1F | **Mirrored networking** | Set `networkingMode=mirrored` in .wslconfig → localhost works natively | .wslconfig edit + WSL restart | ~1ms | ⚠️ May break VS Code, IDE networking |

**Recommended:** 1A (Python TCP Proxy) — zero external dependencies, runs in-process, fast.
**Fallback:** 1E (curl.exe bridge) — always works if curl.exe exists.
**Risky alternative:** 1F (mirrored) — fastest but can break other tools.

### Layer 2: Hostname Resolution (How to find Windows from WSL)

**What:** What IP address does WSL use to reach the Windows host?

**Current state:** ⚠️ Detection exists but not used for tunnel targets.

**Choices:**

| # | Choice | How It Works | Prerequisites | Reliability |
|---|--------|-------------|---------------|-------------|
| 2A | **hostname.local (mDNS)** | `socket.getaddrinfo("HOSTNAME.local", None)` | mDNS/Bonjour on Windows (default on Win10/11) | High — survives IP changes |
| 2B | **/etc/resolv.conf nameserver** | Parse nameserver from WSL-generated resolv.conf | WSL generates the file (default) | Medium — IP may change |
| 2C | **Default gateway** | `ip route show default` → gateway IP | Standard WSL2 NAT setup | Medium — IP may change |
| 2D | **Manual IP** | User provides the Windows host IP | None | Low — breaks on IP change |
| 2E | **Auto-detect** (try all) | Try 2A → 2B → 2C in order, use first that works | None | High — cascading fallback |

**Recommended:** 2E (Auto-detect) with 2A as primary.
**Detection already exists** for 2A, 2B, 2C in `cdp_client.py:try_discover_endpoint()`.

### Layer 3: Windows Firewall (Allow WSL traffic through)

**What:** Windows firewall blocks inbound connections from WSL2 vEthernet by default.

**Current state:** ⚠️ Backend endpoint exists but no UI, no detection of rule status.

**Choices:**

| # | Choice | How It Works | Prerequisites | Scope |
|---|--------|-------------|---------------|-------|
| 3A | **Create inbound rule** | `New-NetFirewallRule -DisplayName "WSL_CDP_Access" -Direction Inbound -InterfaceAlias "vEthernet (WSL)" -Action Allow -Protocol TCP -LocalPort 9222` | Elevated PowerShell | Specific port + interface |
| 3B | **Create broad rule** | Same but for port range (9222-9232) to cover multiple instances | Elevated PowerShell | Port range |
| 3C | **Temporary disable** | `Set-NetFirewallProfile -Profile Private -Enabled False` | Elevated PowerShell | ⚠️ Disables ALL firewall |
| 3D | **Skip (not needed)** | If using netsh portproxy (1C) or mirrored (1F), firewall rule may not be needed | Depends on tunnel choice | — |

**Recommended:** 3A (specific rule) — minimal surface, targeted.
**Detection:** `powershell.exe Get-NetFirewallRule -DisplayName 'WSL_CDP_Access'`

### Layer 4: Chrome Accessibility (Is Chrome reachable on the target interface?)

**What:** Chrome binds to 127.0.0.1 by default. If the tunnel target is a different interface,
Chrome must be configured to listen there.

**Current state:** ❌ Not handled.

**Choices:**

| # | Choice | How It Works | Prerequisites | Impact |
|---|--------|-------------|---------------|--------|
| 4A | **Use tunnel** | Tunnel (1A/1B/1C/1D) handles the translation — Chrome stays on 127.0.0.1 | Tunnel running | None — Chrome untouched |
| 4B | **Modify Chrome shortcut** | Add `--remote-debugging-address=0.0.0.0` to Chrome launch args | Shortcut modification | Chrome binds to all interfaces |
| 4C | **netsh portproxy** | Windows-side proxy from 0.0.0.0:9222 → 127.0.0.1:9222 | netsh (built-in) + admin | Same as 1C |
| 4D | **Not needed** | If using mirrored networking (1F), localhost works natively | mirrored mode | — |

**Recommended:** 4A (use tunnel) — no Chrome modification needed.
**Note:** 4B is what the plan originally said (`--remote-debugging-address=0.0.0.0`). It IS a real
Chromium flag but has security implications (exposes debug port to network).

### Layer 5: curl.exe Availability (Fallback Bridge)

**What:** curl.exe is the last-resort bridge. If everything else fails, curl.exe still works.

**Current state:** ⚠️ Detection exists, install endpoint exists, no UI.

**Choices (fallback chain — try in order):**

| # | Choice | How It Works | Prerequisites | Elevation |
|---|--------|-------------|---------------|-----------|
| 5A | **Already installed** | `curl.exe` at `C:\Windows\System32\curl.exe` (Win10 17063+) | Modern Windows | None |
| 5B | **winget install** | `winget install --id curl.curl --accept-source-agreements` | winget available | None |
| 5C | **scoop install** | `scoop install curl` (install scoop first if needed: `irm get.scoop.sh \| iex`) | PowerShell exec policy | None |
| 5D | **choco install** | `choco install curl -y` | Chocolatey installed | Admin |
| 5E | **Direct download** | Download from `curl.se/windows/`, extract to `%LOCALAPPDATA%\curl`, add to user PATH | Internet access | None |
| 5F | **Manual** | Guide user to download and install manually | Internet access | None |

**Recommended:** 5A check first → 5B → 5C → 5D → 5E → 5F.
**Detection:** `shutil.which("curl.exe")` — already exists.

---

## Operability Levels (What the user sees)

| Level | Name | What Works | How User Gets Here |
|-------|------|-----------|-------------------|
| 0 | **No CDP** | Nothing — no Chrome, no debug flags, no bridge | Default unconfigured state |
| 1 | **curl.exe Bridge** | CDP via curl.exe subprocess (~2000ms/call) | Chrome + debug shortcut + curl.exe |
| 2 | **Direct Channel** ✅ | CDP via tunnel/direct socket (~5ms/call) | Tunnel + hostname resolution + firewall |
| 3 | **Native localhost** ⚠️ | CDP via localhost (< 1ms) | mirrored networking (risky) |

**The notification says:** "CDP works at Level 1 (curl.exe bridge, ~2000ms/call).
Upgrade to Level 2 (Direct Channel, ~5ms/call) available. Click to set up."

When user clicks → goes to the **interactive setup UI** with all the choices.

---

## Interactive Setup UI

### Where It Lives

Tab Mesh → Setup → **WSL Channel** section (new section in existing setup flow).

### What It Shows

```
┌─────────────────────────────────────────────────────┐
│  WSL↔Windows Channel Setup                          │
│                                                     │
│  Current Level: ● Level 1 — curl.exe Bridge         │
│  Speed: ~2000ms per CDP call                       │
│  ─────────────────────────────────────────────────   │
│                                                     │
│  🔬 Detection Results                               │
│  ├─ WSL2 NAT mode                          ✅       │
│  ├─ hostname.local resolves (172.17.128.1) ✅       │
│  ├─ Firewall rule (WSL_CDP_Access)         ❌       │
│  ├─ Chrome on 0.0.0.0                      ❌       │
│  ├─ curl.exe available                     ✅       │
│  └─ Network tunnel                         ❌       │
│                                                     │
│  🚀 Upgrade to Level 2 — Direct Channel             │
│  Choose a tunnel method:                            │
│                                                     │
│  ┌─ Recommended ──────────────────────────────────┐ │
│  │ ○ Python TCP Proxy (in-app, zero dependencies) │ │
│  │   Starts a background thread. No install needed │ │
│  │   [Set Up] [Learn More]                         │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─ Alternatives ─────────────────────────────────┐ │
│  │ ○ socat tunnel (WSL-side port forward)         │ │
│  │   Needs: socat package                          │ │
│  │   [Set Up] [Install socat]                      │ │
│  │                                                 │ │
│  │ ○ netsh portproxy (Windows-side, persistent)   │ │
│  │   Needs: elevated PowerShell                    │ │
│  │   [Set Up]                                      │ │
│  │                                                 │ │
│  │ ○ SSH tunnel (encrypted)                       │ │
│  │   Needs: OpenSSH server on Windows              │ │
│  │   [Set Up]                                      │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─ ⚠️ Risky Alternative ────────────────────────┐  │
│  │ ○ Mirrored networking                          │ │
│  │   WARNING: May break VS Code, IDE networking   │ │
│  │   [Set Up] [Read Warnings]                      │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  ─────────────────────────────────────────────────   │
│  Prerequisites (auto-detected):                     │
│                                                     │
│  Firewall Rule:  ❌ Missing                         │
│  [Create Rule] (needs elevated PowerShell)          │
│                                                     │
│  curl.exe:  ✅ Found at C:\Windows\System32         │
│                                                     │
│  ─────────────────────────────────────────────────   │
│  [▶ Validate Channel]  [🔄 Re-scan]                │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### User Flow

1. User sees notification: "CDP Level 1. Upgrade available."
2. Clicks → Tab Mesh → WSL Channel section
3. Sees detection results (what works, what doesn't)
4. Sees tunnel choices (recommended + alternatives)
5. Picks a tunnel method → clicks [Set Up]
6. System checks prerequisites (firewall? hostname? Chrome?)
   - If prerequisite missing → offers to fix it inline
7. System creates the tunnel
8. System validates end-to-end
9. Success → level updates to 2, notification dismissed

### When Non-Optimal

If the user already set up curl.exe (Level 1) and hostname.local resolves:
- The setup UI shows: "Level 1 active. Level 2 available."
- Shows the tunnel choices that would upgrade them
- Doesn't force anything — user decides

---

## Implementation Phases

### Phase 1: Python TCP Proxy (The Tunnel)

**The core missing piece.** A background thread in the Flask app that:
1. Listens on WSL localhost:PORT
2. Forwards TCP to the Windows host IP:PORT
3. Chrome stays on 127.0.0.1 (no modification needed)

```python
# src/core/services/chrome/wsl_tunnel.py

class WslTunnel:
    """TCP tunnel from WSL localhost to Windows host.
    
    Listens on localhost:<port> in WSL and forwards all TCP
    traffic to <windows_host>:<port>. This makes Chrome's
    debug port (bound to 127.0.0.1 on Windows) accessible
    from WSL Python via localhost.
    """
    
    def __init__(self, port: int, target_host: str):
        self.port = port
        self.target_host = target_host  # hostname.local IP or gateway
        self._server = None
        self._thread = None
    
    def start(self) -> bool:
        """Start the tunnel in a background thread."""
        ...
    
    def stop(self):
        """Stop the tunnel."""
        ...
    
    def is_running(self) -> bool:
        """Check if tunnel is active."""
        ...
    
    def validate(self) -> dict:
        """Test end-to-end: connect through tunnel, hit /json/version."""
        ...
```

**Files:**
- NEW: `src/core/services/chrome/wsl_tunnel.py`
- MODIFY: `src/core/services/chrome/launcher.py` — use tunnel when available

### Phase 2: Alternative Tunnel Backends

Add alternative tunnel implementations behind the same interface:

```python
# Each implements the same start/stop/validate interface

class SocatTunnel:      # 1B — shells out to socat
class NetshTunnel:      # 1C — configures netsh portproxy via PowerShell  
class SshTunnel:        # 1D — starts ssh -L tunnel
class MirroredConfig:   # 1F — modifies .wslconfig (with warnings)
```

### Phase 3: Firewall Rule Management

**Files:**
- EXISTING: `POST /tab-mesh/wsl-fix-firewall` endpoint (enhance)
- NEW: Firewall rule detection in `_check_wsl_firewall_rule()`
- NEW: UI button in setup flow

### Phase 4: Interactive Setup UI

**Files:**
- MODIFY: `src/ui/web/templates/scripts/_tab_mesh.html` — add WSL Channel section
- New section in Tab Mesh setup that shows:
  - Current detection results
  - Current operability level
  - Tunnel choices (radio buttons or cards)
  - [Set Up] buttons per choice
  - [Validate] button
  - Prerequisite status with inline fix buttons

### Phase 5: Notifications (Entry Point)

**Files:**
- MODIFY: `_check_wsl_interop_notifications()` — fire when below Level 2
- MODIFY: `_notifications.html` — WSL notifications navigate to setup UI
- The notification is just the DOOR to the interactive setup

### Phase 6: curl.exe Install Plan (Fallback Chain)

**Files:**
- EXISTING: `POST /tab-mesh/wsl-install-curl` endpoint (enhance with full chain)
- UI: Install button in setup flow with progress feedback
- Chain: winget → scoop → choco → direct download → manual

### Phase 7: End-to-End Validation

**Files:**
- EXISTING: `POST /tab-mesh/wsl-validate` endpoint (enhance)
- Tests each layer independently
- Reports which layers pass/fail
- Updates operability level in real-time

---

## Choice Dependencies

Some tunnel choices need prerequisites. The UI grays out unavailable options:

| Tunnel Choice | Needs hostname? | Needs firewall? | Needs Chrome binding? | Needs install? |
|---------------|----------------|-----------------|----------------------|----------------|
| 1A Python Proxy | Yes (any method) | Yes | No (proxy handles it) | No |
| 1B socat | Yes (hostname.local) | Yes | No | socat package |
| 1C netsh portproxy | No | Yes | No (netsh handles it) | No (built-in) |
| 1D SSH tunnel | Yes (hostname.local) | No (SSH bypasses) | No | OpenSSH server |
| 1E curl.exe | No | No | No | curl.exe |
| 1F Mirrored | No | No | No | No |

---

## Notification Strategy

| When | Notification | Type | Action |
|------|-------------|------|--------|
| Level 0 (no CDP) | "CDP unavailable — no Chrome or no debug flags" | Imminent | → Chrome setup |
| Level 1 (curl.exe) | "CDP Level 1 — Upgrade to Direct Channel available" | Normal | → WSL Channel setup |
| Level 2 (direct) | None — this is the recommended state | — | — |
| curl.exe missing + no tunnel | "CDP Bridge Unavailable — no way to reach Chrome" | Imminent | → WSL Channel setup |
| Firewall rule missing + tunnel needs it | "Firewall rule needed for direct channel" | Normal | → inline fix |

Each notification has `dedup=True` — fires once, not on every page load.
Each notification is clickable → navigates to Tab Mesh → WSL Channel setup.

---

## What Gets Reverted / Cleaned Up

The previous session added detection and notification code that's partially wrong.
Before implementing this plan:

1. **Keep:** `_detect_wsl_interop()` enrichment (hostname, curl.exe, .wslconfig parsing)
2. **Keep:** `try_discover_endpoint()` hostname.local step
3. **Keep:** `_port_in_use()` / `_cdp_responding()` hostname.local fallthrough fix
4. **Rework:** `_check_wsl_interop_notifications()` — align with this plan's notification strategy
5. **Rework:** `cdp_channel_level` computation — Level 2 should mean tunnel is active, not just DNS
6. **Remove:** `_check_wsl_firewall_rule()` from notification flow — move to setup UI detection
7. **Keep:** Frontend notification icons + click action (navigate-tab)

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Python TCP proxy thread crashes | Restart logic + fallback to curl.exe |
| socat not installed | Offer install or suggest Python proxy |
| Firewall rule needs elevation | UAC prompt via existing elevated PS pattern |
| Mirrored networking breaks IDE | Warning label, NOT recommended, user explicitly opts in |
| Tunnel port conflict | Check if port is already in use before binding |
| Chrome not running when tunnel starts | Tunnel waits/retries, validates on-demand |
| Multiple tunnel methods active | Only one active at a time, UI shows which |
| hostname.local IP changes | Tunnel re-resolves on reconnect |

---

## Priority Order

1. **Phase 1: Python TCP Proxy** — THE tunnel. Makes Level 2 possible.
2. **Phase 4: Interactive Setup UI** — User sees choices and picks.
3. **Phase 3: Firewall Rule** — Prerequisite for most tunnel options.
4. **Phase 5: Notifications** — Entry point to the setup UI.
5. **Phase 7: Validation** — Confirm it works end-to-end.
6. **Phase 2: Alternative tunnels** — More choices (socat, netsh, SSH).
7. **Phase 6: curl.exe install** — Fallback chain for Level 1.

---

## Future Notes

### PowerShell Bridge Worker — Cold Start in Plan Execution

The PowerShell bridge (`_BridgeWebSocket`) currently starts COLD when
plan execution launches a new Chrome instance. This is because the bridge
is not pre-warmed when the plan executor spins up — it's not integrated
into the plan exec modal flow.

**Impact:** First CdpSession connect during plan execution: ~4000ms.
**When to address:** After Phase 1 (tunnel), the bridge becomes secondary.
If the tunnel is active, the pre-warmed bridge is no longer needed for
most operations. But for plan execution on separate Chrome instances
(different ports), the bridge may still be used.

**TODO:** When implementing Phase 4 (Interactive Setup UI), evaluate
whether the tunnel covers plan execution's needs or if the bridge
worker should be pre-warmed during plan modal initialization.

