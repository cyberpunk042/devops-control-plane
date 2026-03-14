# Phase 7: End-to-End Validation

## Status: ANALYSIS — Awaiting Review

## Implementation Priority: 5 of 7

---

## What This Phase Delivers

The [Validate Channel] button in the Phase 4 UI. Tests every layer
independently, measures latency, and shows the user a clear pass/fail
report. Also re-computes the operability level after any change.

---

## What Already Exists — MOSTLY COMPLETE

### POST /tab-mesh/wsl-validate ✅

Full per-layer validation at `tab_mesh/__init__.py:1068-1139`:

- **Layer 0:** WSL environment (powershell, binfmt, windows_user)
- **Layer 1:** Networking mode (NAT vs mirrored)
- **Layer 2:** hostname.local resolution (resolves, IP)
- **Layer 5:** curl.exe bridge (path)
- **CDP test:** `try_discover_endpoint()` + `is_available()`

### POST /tab-mesh/wsl-test-hostname ✅

Granular hostname test at `tab_mesh/__init__.py:968-1065`:

- **Step 1:** Resolve hostname → `hostname.local`
- **Step 2:** DNS resolve → IP address
- **Step 3:** TCP connect to IP:port
- **Step 4:** HTTP GET `/json/version`
- Returns per-step ok/error + overall pass/fail

---

## What's Missing

### 7.1: Tunnel Layer in Validation

The existing validation checks layers 0, 1, 2, 5 and CDP overall.
It does NOT check:

- **Layer 3:** Firewall rule status
- **Layer 4:** Chrome binding / tunnel state
- **Tunnel:** Whether the active tunnel is working

**Fix:** Add tunnel and firewall layers to `wsl_validate()`:

```python
# Add after existing layers dict:

# Layer 3: Firewall
firewall_ok = _check_wsl_firewall_rule()
layers["layer_3_firewall"] = {
    "name": "Windows Firewall",
    "ok": firewall_ok,
    "detail": {
        "rule_name": "WSL_CDP_Access",
        "rule_exists": firewall_ok,
    },
}

# Tunnel state
from src.core.services.chrome.wsl_tunnel import get_active_tunnel
tunnel = get_active_tunnel()
layers["tunnel"] = {
    "name": "Network Tunnel",
    "ok": tunnel is not None and tunnel.is_running,
    "detail": {
        "method": tunnel.__class__.__name__ if tunnel else None,
        "stats": tunnel.stats if tunnel and tunnel.is_running else None,
    },
}
```

### 7.2: Latency Measurement

The most important metric. User wants to SEE the speed difference.

```python
# Add to wsl_validate():
import time

latency = {}

# Measure curl.exe bridge latency
if interop.get("curl_exe_available"):
    start = time.monotonic()
    curl_ok = _curl_exe_get("http://localhost:9222/json/version")
    latency["curl_exe_ms"] = round((time.monotonic() - start) * 1000, 1)
    latency["curl_exe_ok"] = curl_ok is not None

# Measure tunnel/direct latency
if tunnel and tunnel.is_running:
    validation = tunnel.validate()
    latency["tunnel_ms"] = validation.get("latency_ms")
    latency["tunnel_ok"] = validation.get("ok")

# Measure direct (hostname.local) latency
host_ip = interop.get("hostname_local_ip")
if host_ip:
    start = time.monotonic()
    try:
        req = urllib.request.Request(f"http://{host_ip}:9222/json/version")
        with urllib.request.urlopen(req, timeout=3) as resp:
            resp.read()
        latency["direct_ms"] = round((time.monotonic() - start) * 1000, 1)
        latency["direct_ok"] = True
    except Exception:
        latency["direct_ms"] = None
        latency["direct_ok"] = False

result["latency"] = latency
```

### 7.3: Level Re-computation

After any remediation, the operability level needs to be re-computed
based on ACTUAL state, not just detection:

```python
def _compute_actual_level(interop: dict, tunnel_active: bool, cdp_ok: bool) -> dict:
    """Compute the actual operability level based on live state.
    
    Returns:
        {
            "level": 2,
            "level_name": "Direct Channel",
            "method": "python_proxy",
            "latency_ms": 4.2,
        }
    """
    if interop.get("networking_mode") == "mirrored" and cdp_ok:
        return {"level": 3, "level_name": "Native localhost", "method": "mirrored"}
    
    if tunnel_active and cdp_ok:
        return {"level": 2, "level_name": "Direct Channel", "method": "tunnel"}
    
    if interop.get("curl_exe_available") and cdp_ok:
        return {"level": 1, "level_name": "curl.exe Bridge", "method": "curl_exe"}
    
    return {"level": 0, "level_name": "No CDP", "method": None}
```

This replaces the detection-only `cdp_channel_level` from `_detect_wsl_interop()`.

### 7.4: UI Rendering of Validation Results

In Phase 4's `_wslValidateChannel()`:

```javascript
function _wslValidateChannel() {
    var container = document.getElementById('wsl-validation');
    container.style.display = '';
    container.innerHTML = '<div class="spinner-sm"></div> Validating...';
    
    fetch('/tab-mesh/wsl-validate', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            var html = '';
            
            // Level badge
            var lv = data.actual_level;
            html += '<div class="validation-level">' +
                '<span class="level-badge level-' + lv.level + '">' +
                'Level ' + lv.level + '</span> ' +
                lv.level_name + '</div>';
            
            // Per-layer results
            var layers = data.layers;
            for (var key in layers) {
                var l = layers[key];
                var icon = l.ok ? '✅' : '❌';
                html += '<div class="validation-layer">' +
                    icon + ' ' + l.name + '</div>';
            }
            
            // Latency comparison
            if (data.latency) {
                html += '<div class="validation-latency">';
                html += '<div class="latency-title">⚡ Latency Comparison</div>';
                if (data.latency.curl_exe_ms != null) {
                    html += '<div>curl.exe bridge: <strong>' + 
                        data.latency.curl_exe_ms + 'ms</strong></div>';
                }
                if (data.latency.tunnel_ms != null) {
                    html += '<div>Tunnel: <strong>' + 
                        data.latency.tunnel_ms + 'ms</strong></div>';
                }
                if (data.latency.direct_ms != null) {
                    html += '<div>Direct (hostname.local): <strong>' + 
                        data.latency.direct_ms + 'ms</strong></div>';
                }
                html += '</div>';
            }
            
            // CDP status
            html += '<div class="validation-cdp">' +
                (data.cdp_active ? '✅' : '❌') +
                ' CDP: ' + (data.cdp_endpoint || 'not reachable') +
                '</div>';
            
            container.innerHTML = html;
        });
}
```

---

## Validation Response Shape (Final)

```json
{
    "layers": {
        "layer_0_wsl": { "name": "WSL Environment", "ok": true, "detail": {...} },
        "layer_1_networking": { "name": "Networking Mode", "ok": true, "detail": {...} },
        "layer_2_hostname": { "name": "hostname.local", "ok": true, "detail": {...} },
        "layer_3_firewall": { "name": "Windows Firewall", "ok": false, "detail": {...} },
        "layer_5_curl_exe": { "name": "curl.exe Bridge", "ok": true, "detail": {...} },
        "tunnel": { "name": "Network Tunnel", "ok": true, "detail": {...} }
    },
    "latency": {
        "curl_exe_ms": 1842.3,
        "curl_exe_ok": true,
        "tunnel_ms": 4.2,
        "tunnel_ok": true,
        "direct_ms": 5.1,
        "direct_ok": true
    },
    "actual_level": {
        "level": 2,
        "level_name": "Direct Channel",
        "method": "python_proxy",
        "latency_ms": 4.2
    },
    "cdp_active": true,
    "cdp_endpoint": "http://localhost:9222",
    "summary": "All layers operational. CDP at Level 2 via tunnel (4.2ms)."
}
```

---

## Interconnection with All Phases

| Phase | How Phase 7 Uses It |
|-------|--------------------|
| Phase 1 | Checks `get_active_tunnel().is_running` + `tunnel.validate()` |
| Phase 2 | Same — all tunnel backends expose `validate()` |
| Phase 3 | Checks `_check_wsl_firewall_rule()` for Layer 3 |
| Phase 4 | [Validate] button renders results in the UI |
| Phase 5 | After successful validation, dismiss gap notifications |
| Phase 6 | Checks `curl_exe_available` for fallback status |

**Validation is called:**
1. User clicks [Validate] in Phase 4 UI
2. After tunnel start (Phase 1) — auto-validation
3. After firewall rule creation (Phase 3) — auto-validation
4. After curl.exe install (Phase 6) — auto-validation

---

## Files Modified

| File | Action | What |
|------|--------|------|
| `src/ui/web/routes/tab_mesh/__init__.py` | **MODIFY** | Add firewall + tunnel layers to `wsl_validate()`, add latency measurement, add `_compute_actual_level()` |
| `src/ui/web/templates/scripts/_tab_mesh_panel.html` | **MODIFY** | `_wslValidateChannel()` rendering (part of Phase 4 code) |

---

## Testing Plan

| # | Test | What It Verifies |
|---|------|-----------------|
| 1 | `test_validate_all_layers` | Response includes all 6 layers |
| 2 | `test_validate_latency_curl` | curl.exe latency is measured |
| 3 | `test_validate_latency_tunnel` | Tunnel latency is measured |
| 4 | `test_validate_actual_level` | Level computed from live state, not detection |
| 5 | `test_compute_level_tunnel` | Tunnel active → Level 2 |
| 6 | `test_compute_level_curl` | Only curl.exe → Level 1 |
| 7 | `test_compute_level_mirrored` | Mirrored networking → Level 3 |
| 8 | `test_compute_level_none` | Nothing works → Level 0 |
| 9 | Manual: validate button | Click [Validate] → shows latency comparison |
| 10 | Manual: before/after tunnel | Validate at Level 1, start tunnel, validate at Level 2 |

---

## The Payoff

After Phase 7, the user clicks [Validate] and sees:

```
Level 2 — Direct Channel ✅

✅ WSL Environment
✅ Networking Mode (NAT)
✅ hostname.local → 172.17.128.1
✅ Windows Firewall (WSL_CDP_Access)
✅ curl.exe (fallback)
✅ Network Tunnel (Python TCP Proxy)

⚡ Latency Comparison
   curl.exe bridge:  1842.3ms
   Tunnel:              4.2ms   ← 439x faster

✅ CDP: http://localhost:9222
```

That's the proof it works. That's the whole point.
