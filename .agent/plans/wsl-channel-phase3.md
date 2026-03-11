# Phase 3: Firewall Rule Management

## Status: ANALYSIS — Awaiting Review

## Implementation Priority: 3 of 7

---

## What This Phase Delivers

Complete firewall rule lifecycle: **detect** → **create** → **verify** → **remove**.
Multiple choices for the user (specific rule, broad rule, skip).
Backend endpoints already exist — this phase adds the missing pieces.

---

## What Already Exists

### Detection: `_check_wsl_firewall_rule()` ✅

```python
# tab_mesh/__init__.py line 404-420
# Checks if WSL_CDP_Access rule exists and is enabled
# Uses: powershell.exe Get-NetFirewallRule -DisplayName 'WSL_CDP_Access'
# Returns: bool
```

**Problem:** Only checks for ONE specific rule name. Doesn't detect:
- Rules with different names that serve the same purpose
- Port range rules (3B)
- Whether the rule actually covers the right port

### Creation: `POST /tab-mesh/wsl-fix-firewall` ✅

```python
# tab_mesh/__init__.py line 1172-1274
# Creates WSL_CDP_Access inbound rule
# Uses elevated PowerShell (UAC prompt)
# Handles: already exists, creation, UAC cancel, timeout
```

**Problem:** 
- Only creates specific port rule (3A). No broad rule option (3B).
- No UI to trigger it — endpoint exists but no button calls it.
- No post-creation validation (doesn't verify rule actually works).

### Notification: `wsl_firewall_rule` ✅

Created in `_check_wsl_interop_notifications()` when hostname resolves
but firewall rule is missing. Frontend renders with 🛡️ icon and
"Click to open setup →" action.

---

## What Needs to Be Added

### 3.1: Enhanced Detection

The current detection only checks for one rule name. Enhance to also
test actual TCP connectivity — because a rule might exist under a
different name, or the user might have already opened the port.

```python
def check_wsl_firewall_status(port: int = 9222) -> dict:
    """Comprehensive firewall status check.
    
    Returns:
        {
            "rule_exists": True/False,      # WSL_CDP_Access rule found
            "rule_enabled": True/False,      # rule is enabled
            "rule_port": 9222,               # port the rule covers
            "port_reachable": True/False,     # actual TCP test through firewall
            "hostname_ip": "172.17.128.1",   # target IP used for test
            "alternative_rule": str | None,  # if another rule covers this port
        }
    """
```

**TCP reachability test:** After checking the rule, also do a raw socket
connect from WSL to `hostname.local:port`. If this succeeds, the
firewall is open regardless of which rule did it.

### 3.2: Broad Rule Option (3B)

Add support for creating a port RANGE rule (9222-9232) to cover
multiple Chrome instances:

```python
# In wsl_fix_firewall() — accept a "scope" parameter
scope = request.json.get("scope", "single")  # "single" or "range"

if scope == "range":
    port_spec = "9222-9232"
    description = f"Allow WSL2 CDP access on ports 9222-9232"
else:
    port_spec = str(port)
    description = f"Allow WSL2 CDP access on port {port}"
```

### 3.3: Rule Removal

Add endpoint to remove the firewall rule (for cleanup/reset):

```python
@tab_mesh_bp.route("/tab-mesh/wsl-remove-firewall", methods=["POST"])
def wsl_remove_firewall():
    """Remove the WSL_CDP_Access firewall rule."""
    # Uses elevated PowerShell:
    # Remove-NetFirewallRule -DisplayName 'WSL_CDP_Access'
```

### 3.4: Post-Creation Validation

After creating the rule, immediately test TCP connectivity to confirm
it actually works:

```python
# In wsl_fix_firewall(), after successful creation:
import socket
host_ip = _resolve_hostname_local()
if host_ip:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((host_ip, port))
        sock.close()
        validated = True
    except (ConnectionRefusedError, OSError):
        # Rule created but still can't connect
        # This means Chrome isn't listening on this interface
        validated = False
```

---

## Integration with Phase 1 (Tunnel)

The tunnel's `start()` method needs to reach `hostname.local:port`.
If the firewall blocks this, the tunnel's remote connection will fail:

```
Python TCP Proxy → connects to hostname.local:9222 → BLOCKED by firewall
```

**Flow:**
1. User clicks [Start Tunnel] in Phase 4 UI
2. Tunnel tries to connect → fails
3. System detects: "Firewall rule missing"
4. UI shows: "Firewall rule needed. [Create Rule]"
5. User clicks → UAC prompt → rule created
6. System retries tunnel → succeeds

This means Phase 3 must be callable from Phase 4 UI inline — not
as a separate workflow. The firewall check is a **prerequisite gate**
in the tunnel setup flow.

### Prerequisite Gate Pattern

```python
def check_tunnel_prerequisites(target_host: str, port: int) -> dict:
    """Check all prerequisites before starting a tunnel.
    
    Returns:
        {
            "hostname_resolves": True/False,
            "firewall_ok": True/False,     # ← Phase 3
            "port_available": True/False,   # local port free
            "chrome_running": True/False,
            "all_ok": True/False,
            "missing": ["firewall", ...]   # what needs fixing
        }
    """
```

This function is called by Phase 4 UI before starting any tunnel.
If `firewall_ok` is False, the UI shows the inline fix button.

---

## Integration with Phase 2 (Alternative Backends)

| Backend | Needs Firewall Rule? | Why |
|---------|---------------------|-----|
| Python TCP Proxy (1A) | **Yes** | Connects from WSL to hostname.local:port |
| socat (1B) | **Yes** | Same — connects to hostname.local:port |
| netsh portproxy (1C) | **Yes** | Opens NEW listener on 0.0.0.0 — firewall must allow |
| SSH tunnel (1D) | **No** | SSH handles its own auth/encryption |
| curl.exe bridge (1E) | **No** | Runs on Windows side — no firewall crossing |
| Mirrored (1F) | **No** | localhost works, no cross-network traffic |

---

## Choices Presented to User (Phase 4 UI)

```
┌─ Firewall ───────────────────────────────────┐
│                                               │
│  Status: ❌ No rule found                     │
│                                               │
│  ○ Create specific rule (port 9222 only)      │
│    Recommended — minimal attack surface       │
│    [Create Rule]                              │
│                                               │
│  ○ Create broad rule (ports 9222-9232)        │
│    For multiple Chrome instances              │
│    [Create Rule]                              │
│                                               │
│  ○ Skip (not needed for my setup)             │
│    If using SSH tunnel or mirrored mode       │
│                                               │
│  ⚠️ Requires Admin elevation (UAC prompt)     │
│                                               │
└───────────────────────────────────────────────┘
```

---

## API Endpoints (Final Shape)

| Method | Path | Action | Exists? |
|--------|------|--------|---------|
| GET | `/tab-mesh/wsl-firewall-status` | Check rule + reachability | **NEW** |
| POST | `/tab-mesh/wsl-fix-firewall` | Create rule (single or range) | ✅ Enhance |
| POST | `/tab-mesh/wsl-remove-firewall` | Remove rule | **NEW** |

### GET /tab-mesh/wsl-firewall-status

```json
{
    "rule_exists": false,
    "rule_enabled": false,
    "port_reachable": false,
    "hostname_ip": "172.17.128.1",
    "needs_rule": true,
    "recommendation": "Create specific rule for port 9222"
}
```

### POST /tab-mesh/wsl-fix-firewall (enhanced)

Request: `{ "port": 9222, "scope": "single" | "range" }`

Response: `{ "ok": true, "action": "created", "validated": true }`

### POST /tab-mesh/wsl-remove-firewall

Response: `{ "ok": true, "action": "removed" }`

---

## Files Modified

| File | Action | What |
|------|--------|------|
| `src/ui/web/routes/tab_mesh/__init__.py` | **MODIFY** | Enhance `wsl_fix_firewall()` with scope param, add `wsl_firewall_status()`, add `wsl_remove_firewall()` |
| `src/ui/web/routes/tab_mesh/__init__.py` | **MODIFY** | Enhance `_check_wsl_firewall_rule()` → `check_wsl_firewall_status()` |

No new files — all firewall logic stays in the existing tab_mesh routes.

---

## Testing Plan

| # | Test | What It Verifies |
|---|------|-----------------|
| 1 | `test_firewall_status_no_rule` | Status endpoint returns rule_exists=False |
| 2 | `test_firewall_status_rule_exists` | Status endpoint returns rule_exists=True |
| 3 | `test_firewall_create_single` | Creates specific port rule |
| 4 | `test_firewall_create_range` | Creates port range rule |
| 5 | `test_firewall_already_exists` | Returns ok=True with action=already_exists |
| 6 | `test_firewall_uac_cancel` | Returns ok=False when UAC is cancelled |
| 7 | `test_firewall_remove` | Removes the rule |
| 8 | `test_firewall_post_validation` | After creation, tests TCP reachability |
| 9 | `test_prerequisite_gate` | `check_tunnel_prerequisites()` reports firewall status |

**Note:** Tests 3-7 require PowerShell and admin elevation — these are
integration tests that run manually on the user's WSL2 system. Unit tests
mock the PowerShell subprocess calls.

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| UAC prompt scares user | Clear warning in UI: "Windows will ask for admin permission" |
| Rule creation succeeds but port still blocked | Post-creation TCP validation catches this |
| vEthernet (WSL) interface name varies | Check with `Get-NetAdapter *WSL*` first, fall back to exact name |
| Multiple rules conflict | Detection checks actual TCP connectivity, not just rule existence |
| User disables firewall entirely | Detect with `Get-NetFirewallProfile`, warn if disabled |
