# Phase 4: Interactive Setup UI

## Status: ANALYSIS — Awaiting Review

## Implementation Priority: 2 of 7

---

## What This Phase Delivers

The user-facing UI where they see their current WSL↔Windows channel state,
see ALL available choices, and pick which remediation to apply. This is
the CENTER of the entire solution — everything else feeds into it.

---

## Where It Lives

### Existing Structure

The Tab Mesh system already has a **setup wizard** in `_tab_mesh_panel.html`:

```
_tab_mesh_panel.html
├── _meshShowSetup()           — entry point, fetches diag data
├── _meshRenderSetupWizard()   — renders Chrome shortcut setup
├── _meshApplyRemediation()    — applies shortcut changes
├── _meshRenderPostApply()     — post-apply Chrome restart
├── _meshRestartChrome()       — kills + relaunches Chrome
├── _meshVerifyCDP()           — verifies CDP works after restart
└── _meshTriggerSignin()       — Chrome sign-in via CDP
```

This wizard handles **Chrome shortcut setup** (debug flags, icon, backup).
The WSL Channel section is a **separate concern** — it's about the
NETWORK PATH, not the Chrome configuration.

### Where the WSL Channel Section Goes

**Option A: Inside the existing setup wizard** — Add a new step after
the shortcut setup. When all shortcut diagnostics pass but CDP
still doesn't work (because of the WSL network gap), show the
WSL Channel section.

**Option B: Separate panel section** — A new section in the mesh panel
that's always accessible, not gated behind the shortcut wizard.

**Recommended: Option A with B as fallback.**

- If coming from the wizard flow: show after shortcut setup
- If coming from a notification click: show directly (skip wizard)
- Both paths render the same `_meshRenderWslChannel()` function

---

## Data Source: Backend Endpoint

### NEW: `GET /tab-mesh/wsl-channel-status`

Returns everything the UI needs to render the channel section:

```python
@tab_mesh_bp.route("/tab-mesh/wsl-channel-status")
def wsl_channel_status():
    """Full WSL channel diagnostic for the setup UI."""
    return jsonify({
        # Current state
        "is_wsl": True,
        "networking_mode": "nat",
        "channel_level": 1,
        "channel_level_name": "curl.exe Bridge",
        
        # Layer 2: Hostname resolution
        "hostname": "DESKTOP-ABC123",
        "hostname_local_resolves": True,
        "hostname_local_ip": "172.17.128.1",
        
        # Layer 3: Firewall
        "firewall_rule_exists": False,
        "firewall_port_reachable": False,
        
        # Layer 5: curl.exe
        "curl_exe_available": True,
        "curl_exe_path": "C:\\Windows\\System32\\curl.exe",
        
        # Tunnel state
        "tunnel_active": False,
        "tunnel_method": None,
        "tunnel_stats": None,
        
        # Chrome state
        "chrome_running": True,
        "cdp_port": 9222,
        "cdp_reachable": True,  # via curl.exe bridge
        
        # Available choices (filtered by prerequisites)
        "choices": [
            {
                "id": "python_proxy",
                "label": "Python TCP Proxy",
                "description": "In-app tunnel. Zero dependencies.",
                "speed": "~5ms",
                "recommended": True,
                "available": True,  # all prerequisites met
                "prerequisites": [
                    {"name": "hostname", "ok": True, "detail": "172.17.128.1"},
                    {"name": "firewall", "ok": False, "detail": "WSL_CDP_Access rule missing"},
                ],
            },
            {
                "id": "socat",
                "label": "socat tunnel",
                "description": "WSL-side port forward.",
                "speed": "~5ms",
                "recommended": False,
                "available": False,
                "prerequisites": [
                    {"name": "socat", "ok": False, "detail": "not installed"},
                    {"name": "hostname", "ok": True},
                    {"name": "firewall", "ok": False},
                ],
            },
            {
                "id": "netsh",
                "label": "netsh portproxy",
                "description": "Windows-side, persistent across reboots.",
                "speed": "~3ms",
                "recommended": False,
                "available": True,
                "prerequisites": [
                    {"name": "admin", "ok": True, "detail": "UAC required"},
                    {"name": "firewall", "ok": False},
                ],
            },
            {
                "id": "ssh",
                "label": "SSH tunnel",
                "description": "Encrypted. Needs OpenSSH on Windows.",
                "speed": "~10ms",
                "recommended": False,
                "available": False,
                "prerequisites": [
                    {"name": "openssh", "ok": False, "detail": "server not detected"},
                ],
            },
            {
                "id": "mirrored",
                "label": "Mirrored networking",
                "description": "Changes WSL network mode. localhost works natively.",
                "speed": "<1ms",
                "recommended": False,
                "risky": True,
                "risk_detail": "May break VS Code and other IDE networking.",
                "available": True,
                "prerequisites": [],
            },
        ],
    })
```

---

## UI Rendering

### Function: `_meshRenderWslChannel(container, status)`

Renders the complete WSL Channel setup section.

### Section 1: Current State Banner

```html
<!-- Level indicator -->
<div class="wsl-channel-level">
    <div class="level-badge level-1">Level 1</div>
    <div class="level-name">curl.exe Bridge</div>
    <div class="level-speed">~2000ms per CDP call</div>
</div>
```

Styled with color coding:
- Level 0: Red badge — "No CDP"
- Level 1: Yellow badge — "curl.exe Bridge" 
- Level 2: Green badge — "Direct Channel" ✅
- Level 3: Blue badge — "Native localhost" (mirrored)

### Section 2: Detection Results

```html
<div class="wsl-detection-grid">
    <div class="detection-item ok">✅ WSL2 NAT mode</div>
    <div class="detection-item ok">✅ hostname.local → 172.17.128.1</div>
    <div class="detection-item fail">❌ Firewall rule missing</div>
    <div class="detection-item ok">✅ curl.exe available</div>
    <div class="detection-item fail">❌ Network tunnel not running</div>
</div>
```

### Section 3: Tunnel Choices (Cards)

```html
<div class="wsl-channel-choices">
    <!-- Recommended -->
    <div class="choice-card recommended">
        <div class="choice-header">
            <input type="radio" name="tunnel-method" value="python_proxy" checked>
            <span class="choice-label">Python TCP Proxy</span>
            <span class="choice-badge recommended">Recommended</span>
        </div>
        <div class="choice-desc">In-app tunnel. Zero dependencies. ~5ms</div>
        <div class="choice-prereqs">
            <span class="prereq ok">✅ hostname</span>
            <span class="prereq fail">❌ firewall <button onclick="_wslFixPrereq('firewall')">[Fix]</button></span>
        </div>
        <button class="btn btn-primary btn-sm" onclick="_wslStartTunnel('python_proxy')"
                disabled>Set Up</button>
    </div>

    <!-- Alternatives -->
    <div class="choice-card">...</div>

    <!-- Risky -->
    <div class="choice-card risky">
        <div class="choice-header">
            <input type="radio" name="tunnel-method" value="mirrored">
            <span class="choice-label">⚠️ Mirrored networking</span>
        </div>
        <div class="choice-desc">May break VS Code and IDE networking</div>
        <button class="btn btn-warning btn-sm" onclick="_wslStartTunnel('mirrored')">
            Set Up (Risky)
        </button>
    </div>
</div>
```

### Section 4: Inline Prerequisite Fix

When user clicks [Fix] next to a failed prerequisite:

```html
<div class="prereq-fix-inline" id="fix-firewall">
    <div class="fix-title">🛡️ Create Firewall Rule</div>
    <div class="fix-options">
        <label>
            <input type="radio" name="fw-scope" value="single" checked>
            Port 9222 only (minimal)
        </label>
        <label>
            <input type="radio" name="fw-scope" value="range">
            Ports 9222-9232 (multiple instances)
        </label>
    </div>
    <div class="fix-warning">⚠️ Windows will ask for admin permission (UAC)</div>
    <button class="btn btn-primary btn-sm" onclick="_wslCreateFirewallRule()">
        Create Rule
    </button>
    <div class="fix-status" id="fw-status"></div>
</div>
```

### Section 5: Validation

```html
<div class="wsl-channel-actions">
    <button class="btn btn-sm" onclick="_wslValidateChannel()">
        ▶ Validate Channel
    </button>
    <button class="btn btn-sm btn-ghost" onclick="_wslRescan()">
        🔄 Re-scan
    </button>
</div>

<div class="wsl-validation-result" id="wsl-validation" style="display:none">
    <!-- Populated after validation -->
</div>
```

---

## JavaScript Functions

### Entry Points

```javascript
function _meshRenderWslChannel(container, status) {
    // Renders the full WSL Channel section
    // Called from:
    //   1. _meshRenderSetupWizard() — after shortcut section
    //   2. Notification click → _activateTab('debugging') → this
}

function _meshShowWslChannel() {
    // Standalone entry: fetch status + render
    // Called when notification navigates here
    fetch('/tab-mesh/wsl-channel-status')
        .then(r => r.json())
        .then(status => {
            var container = document.getElementById('mesh-panel-body');
            _meshRenderWslChannel(container, status);
        });
}
```

### Actions

```javascript
function _wslStartTunnel(method) {
    // POST /tab-mesh/wsl-start-tunnel { method: "python_proxy" }
    // On success: re-render with updated status
    // On failure: show error inline
}

function _wslStopTunnel() {
    // POST /tab-mesh/wsl-stop-tunnel
}

function _wslFixPrereq(prereqName) {
    // Show inline fix UI for the given prerequisite
    // prereqName: "firewall", "socat", "curl_exe"
    // Expand the fix section, call the appropriate endpoint
}

function _wslCreateFirewallRule() {
    // POST /tab-mesh/wsl-fix-firewall { scope: "single" | "range" }
    // Show spinner, handle UAC wait, show result
    // On success: refresh detection status, re-enable tunnel button
}

function _wslValidateChannel() {
    // POST /tab-mesh/wsl-validate
    // Show latency test results, Chrome version, etc.
}

function _wslRescan() {
    // GET /tab-mesh/wsl-channel-status (fresh)
    // Re-render the whole section
}
```

---

## Backend Endpoints (New)

| Method | Path | Action | Phase |
|--------|------|--------|-------|
| GET | `/tab-mesh/wsl-channel-status` | Full diagnostic status | Phase 4 |
| POST | `/tab-mesh/wsl-start-tunnel` | Start tunnel (method param) | Phase 1+2 |
| POST | `/tab-mesh/wsl-stop-tunnel` | Stop active tunnel | Phase 1+2 |
| GET | `/tab-mesh/wsl-firewall-status` | Firewall check | Phase 3 |
| POST | `/tab-mesh/wsl-fix-firewall` | Create rule | Phase 3 (exists) |
| POST | `/tab-mesh/wsl-remove-firewall` | Remove rule | Phase 3 |
| POST | `/tab-mesh/wsl-validate` | End-to-end validation | Phase 7 (exists) |
| POST | `/tab-mesh/wsl-install-curl` | Install curl.exe | Phase 6 (exists) |

All WSL channel endpoints are prefixed with `/tab-mesh/wsl-*`.

---

## CSS Styling

The WSL Channel section uses the existing design system variables:

```css
/* Added to the existing Tab Mesh panel CSS */

.wsl-channel-level {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px;
    border-radius: var(--radius-sm);
    background: var(--bg-tertiary);
    margin-bottom: 12px;
}

.level-badge {
    padding: 3px 8px;
    border-radius: var(--radius-sm);
    font-size: 0.64rem;
    font-weight: 700;
    text-transform: uppercase;
}
.level-badge.level-0 { background: rgba(248,113,113,0.15); color: var(--danger); }
.level-badge.level-1 { background: rgba(251,191,36,0.15); color: var(--warning); }
.level-badge.level-2 { background: rgba(52,211,153,0.15); color: var(--success); }
.level-badge.level-3 { background: rgba(96,165,250,0.15); color: var(--info); }

.choice-card {
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    margin-bottom: 8px;
    transition: border-color 0.15s;
}
.choice-card:hover { border-color: var(--border-hover); }
.choice-card.recommended { border-color: var(--success); }
.choice-card.risky { border-color: var(--warning); }

.choice-prereqs { font-size: 0.62rem; margin-top: 6px; }
.prereq.ok { color: var(--success); }
.prereq.fail { color: var(--danger); }
```

---

## Interconnection with All Phases

| Phase | How Phase 4 Uses It |
|-------|--------------------|
| Phase 1 | [Set Up] button calls `POST /wsl-start-tunnel { method: "python_proxy" }` |
| Phase 2 | Same button for each backend: socat, netsh, SSH, mirrored |
| Phase 3 | [Fix] button inline calls `POST /wsl-fix-firewall` |
| Phase 5 | Notification click navigates HERE → `_meshShowWslChannel()` |
| Phase 6 | [Install curl.exe] button calls `POST /wsl-install-curl` |
| Phase 7 | [Validate] button calls `POST /wsl-validate`, shows results |

**Phase 4 is the HUB. All other phases provide the data and actions.
Phase 4 is the interface that ties them together.**

---

## User Flow (Complete)

### Flow A: From Notification
1. User loads page → `cdp_status()` fires → detects Level 1
2. `_check_wsl_interop_notifications()` creates "Upgrade Available" notification
3. User sees 🚀 notification toast
4. Clicks notification → `navigate-tab` handler → `_meshShowWslChannel()`
5. UI loads, shows current state + choices
6. User picks "Python TCP Proxy" → sees ❌ Firewall → clicks [Fix]
7. Inline firewall fix → UAC → rule created → ✅
8. [Set Up] button enables → Click → tunnel starts
9. [Validate] → shows ~5ms latency → Level 2 ✅
10. Notification auto-dismissed

### Flow B: From Setup Wizard
1. User opens mesh panel → clicks ⚙️ Setup
2. Wizard runs → shortcut diagnostics → all pass
3. CDP test: "CDP works via curl.exe bridge (slow)"
4. Shows WSL Channel section below shortcut section
5. Same flow as steps 5-10 above

### Flow C: Direct Access
1. User navigates to `#debugging` or Tab Mesh panel
2. WSL Channel section always visible if `is_wsl` is true
3. Shows current state, available upgrades
4. User acts when ready

---

## Files Modified/Created

| File | Action | What |
|------|--------|------|
| `src/ui/web/templates/scripts/_tab_mesh_panel.html` | **MODIFY** | Add `_meshRenderWslChannel()`, `_meshShowWslChannel()`, action functions |
| `src/ui/web/routes/tab_mesh/__init__.py` | **MODIFY** | Add `GET /wsl-channel-status`, `POST /wsl-start-tunnel`, `POST /wsl-stop-tunnel` |
| `src/ui/web/static/css/index.css` | **MODIFY** | Add WSL channel card styles |

---

## Testing Plan

| # | Test | What It Verifies |
|---|------|-----------------|
| 1 | `test_channel_status_endpoint` | Returns correct JSON shape |
| 2 | `test_channel_status_choices` | Choices filtered by prerequisites |
| 3 | `test_start_tunnel_endpoint` | POST starts the tunnel, returns ok |
| 4 | `test_stop_tunnel_endpoint` | POST stops the tunnel |
| 5 | Manual: notification → UI | Clicking notification lands on channel section |
| 6 | Manual: wizard → channel | Setup wizard shows channel section after shortcuts |
| 7 | Manual: fix prereq inline | [Fix] firewall works inline without navigation |
| 8 | Manual: full flow | Pick method → fix prereqs → start → validate |
