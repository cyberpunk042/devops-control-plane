# Phase D2 — State Override Engine

> **Status:** Planning
> **Created:** 2026-02-25
> **Parent:** Stage Debugger feature
> **Depends on:** D0 (identity gate), D1 (debugger drawer exists)

---

## Objective

Build the **persistent override layer** that alters what the UI
believes about the system, without changing the system itself. This
enables testing of install flows, remediation options, and dashboard
states for systems and tool states that don't exist locally.

Unlike D1's scenario launcher (which opens a one-shot modal with
synthetic data), D2 creates **active overrides** that affect all
subsequent UI rendering and API calls until the developer clears them.

---

## Problem Statement

### D1 vs D2 distinction

D1 answers: "What does the remediation modal look like for failure X?"
→ One-shot modal, synthetic data, no side effects.

D2 answers: "What does the whole dashboard look like on Fedora?"
and "What happens if I try to install ruff when pipx is missing?"
→ Persistent state changes that ripple through the entire UI.

### What D2 overrides

| Override type | What it changes | Where it takes effect |
|--------------|----------------|----------------------|
| System profile | distro family, package manager, capabilities | Plan resolution, availability computation |
| Tool state | installed/missing per tool | Dashboard toolchain card, install flow |
| Failure injection | Force next install to fail with specific error | SSE execution, remediation trigger |
| Available methods | Which install methods appear available | Plan resolution choices |

---

## Architecture

### Override storage

All overrides live in `sessionStorage` under a single key.
They are automatically cleared when the browser tab closes.

```javascript
// Key: 'dcp_dev_overrides'
// Shape:
{
    // ── System profile override ──────────────────────────────
    system_profile: null | {
        preset_id: "fedora_39",     // which preset is active
        profile: { ... },           // full system_profile dict
    },
    
    // ── Tool state overrides ─────────────────────────────────
    tool_overrides: {
        // tool_id → override state
        // "ruff": "missing",       // force show as not installed
        // "trivy": "installed",    // force show as installed
    },
    
    // ── Failure injection ────────────────────────────────────
    inject_failure: null | {
        scenario_id: "pep668_debian",
        trigger: "next_install",    // when to trigger
        // "next_install" = next install attempt fails with this
        // "tool:ruff" = only when installing ruff
        // "any" = every install fails with this
    },
    
    // ── Method overrides ─────────────────────────────────────
    method_overrides: {
        // tool_id → forced method
        // "terraform": "snap",     // force snap even if apt available
    },
}
```

### Override lifecycle

```
Developer opens debugger drawer
  → Tab 2: "State Overrides"
  → Sets system = Fedora
  → sessionStorage updated
  
Developer navigates dashboard
  → loadToolsStatus() reads overrides
  → API call includes X-Dev-System header (or query param)
  → Backend uses override profile instead of _detect_os()
  → Dashboard renders as if on Fedora
  
Developer clicks install on a tool
  → Plan resolution uses Fedora profile
  → Availability computed for Fedora
  → Modal shows Fedora-specific options
  
Developer clears overrides
  → sessionStorage cleared
  → Next navigation shows real state
```

---

## System Profile Override

### How it works end-to-end

#### Frontend (request side)

```javascript
function _getDevOverrides() {
    if (!window._devModeStatus || !window._devModeStatus.dev_mode) return null;
    try {
        return JSON.parse(sessionStorage.getItem('dcp_dev_overrides'));
    } catch (_) { return null; }
}

function _getDevSystemProfile() {
    const overrides = _getDevOverrides();
    return overrides?.system_profile?.profile || null;
}

// For API calls that need system profile:
function _apiHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    const devProfile = _getDevSystemProfile();
    if (devProfile) {
        headers['X-Dev-System-Override'] = JSON.stringify({
            preset_id: _getDevOverrides()?.system_profile?.preset_id
        });
    }
    return headers;
}
```

#### Backend (receive side)

```python
# In routes_dev.py or a middleware helper:

def _resolve_system_profile(project_root: Path) -> tuple[dict, bool]:
    """Resolve system profile, respecting dev overrides.
    
    Returns:
        (profile_dict, is_override)
    """
    # Check request header for dev override
    override_header = request.headers.get("X-Dev-System-Override")
    if override_header:
        try:
            override = json.loads(override_header)
            preset_id = override.get("preset_id")
            if preset_id and preset_id in SYSTEM_PRESETS:
                return SYSTEM_PRESETS[preset_id], True
        except (json.JSONDecodeError, KeyError):
            pass
    
    # No override — use real detection
    from src.core.services.audit.l0_detection import _detect_os
    return _detect_os(), False
```

This function replaces direct `_detect_os()` calls in:
- `routes_audit.py` — plan resolution
- `orchestrator.py` — execute_plan

#### Safety guard

The override is ONLY respected when the request also passes the
dev mode check:

```python
def _resolve_system_profile(project_root: Path) -> tuple[dict, bool]:
    override_header = request.headers.get("X-Dev-System-Override")
    if override_header:
        # SAFETY: verify dev mode is actually active
        from src.core.services.identity import is_owner
        if not is_owner(project_root):
            # Non-owner tried to inject a system override → ignore
            logger.warning("System override from non-owner, ignoring")
            override_header = None
    # ... proceed
```

This prevents a non-owner from injecting system overrides even if they
craft the request manually.

### System indicator in the UI

When a system override is active, the dashboard shows a clear banner:

```
┌─────────────────────────────────────────────────────────────────┐
│ 🔧 System Override Active: Fedora 39 (dnf)     [✕ Clear]      │
│    Real system: Debian 12 (apt) — dashboard shows Fedora view  │
└─────────────────────────────────────────────────────────────────┘
```

**Why important:** Without this, the developer forgets an override is
active and thinks the dashboard is broken. The banner is always visible
when `system_profile` override is set.

---

## Tool State Override

### How it works

In `loadToolsStatus()` (in `_dashboard.html`), after receiving tool
data from the API:

```javascript
async function loadToolsStatus() {
    // ... existing fetch logic ...
    const data = cached || await api('/tools/status');
    
    // ── Apply dev overrides ──────────────────────────────────
    const overrides = _getDevOverrides();
    if (overrides?.tool_overrides) {
        const tools = data.tools || [];
        for (const t of tools) {
            const override = overrides.tool_overrides[t.id];
            if (override === 'missing') {
                t.available = false;
                t._dev_override = 'forced_missing';
            } else if (override === 'installed') {
                t.available = true;
                t._dev_override = 'forced_installed';
            }
        }
        // Recompute counts
        data.available = tools.filter(t => t.available).length;
        data.missing_count = tools.length - data.available;
    }
    // ... rest of rendering ...
}
```

The `_dev_override` marker allows the rendering code to show a visual
indicator that the tool state is synthetic:

```javascript
// In the tool rendering loop:
if (t._dev_override) {
    actionHtml += `<span style="font-size:0.55rem;color:hsl(280,70%,60%)"
        title="Dev override: ${t._dev_override}">🔧</span>`;
}
```

### Tool override UI

In the debugger drawer (Tab 2), a grid of tools with toggle switches:

```
┌─────────────────────────────────────────────────┐
│ Tool State Overrides                            │
│ ────────────────────────────────────────────── │
│ python3    ✅ real    [real] [missing] [inst]   │
│ pip        ✅ real    [real] [missing] [inst]   │
│ ruff       ✅ real    [real] [missing] [inst]   │
│ trivy      ❌ real    [real] [missing] [inst]   │
│ docker     ✅ real    [real] [missing] [inst]   │
│ kubectl    ❌ real    [real] [missing] [inst]   │
│ terraform  ❌ real    [real] [missing] [inst]   │
│ ...                                             │
│                              [Clear All]         │
└─────────────────────────────────────────────────┘
```

Each tool shows:
- Current real state (✅/❌)
- Three buttons: `real` (use actual state), `missing` (force missing),
  `inst` (force installed)
- Active override highlighted

---

## Failure Injection

### Purpose

The developer wants to test: "What happens when I install ruff and
it fails with PEP 668?" Without actually causing a PEP 668 error.

### Mechanism

1. Developer sets a failure injection in the debugger drawer
2. On next install attempt (via SSE), the backend checks for injection
3. If injection is active → skip the real command, return the synthetic error
4. The rest of the pipeline (remediation analysis, modal display) runs normally

### Frontend → Backend flow

```javascript
// In debugger drawer:
function _injectFailure(scenarioId) {
    const overrides = _getDevOverrides() || {};
    overrides.inject_failure = {
        scenario_id: scenarioId,
        trigger: 'next_install',
    };
    _saveDevOverrides(overrides);
    showToast(`🔧 Next install will fail with: ${scenarioId}`, 'info');
}
```

When the install SSE stream starts:
```javascript
// In the install execution code:
const devOverrides = _getDevOverrides();
if (devOverrides?.inject_failure) {
    // Add header to the SSE request
    headers['X-Dev-Inject-Failure'] = JSON.stringify(devOverrides.inject_failure);
    
    // Clear the injection (one-shot)
    if (devOverrides.inject_failure.trigger === 'next_install') {
        devOverrides.inject_failure = null;
        _saveDevOverrides(devOverrides);
    }
}
```

Backend:
```python
# In routes_audit.py SSE generation, before running the actual command:
inject = request.headers.get("X-Dev-Inject-Failure")
if inject and is_owner(project_root):
    injection = json.loads(inject)
    # Import the scenario
    from src.core.services.dev_scenarios import get_scenario_by_id
    scenario = get_scenario_by_id(injection["scenario_id"])
    if scenario:
        # Simulate the failure without running anything
        yield _sse({"type": "step_start", "step": 0, "label": step_label, "total": 1})
        yield _sse({"type": "log", "text": "[DEV] Injected failure: " + injection["scenario_id"]})
        yield _sse({"type": "step_failed", "step": 0, "error": "Injected failure"})
        done_event = {
            "type": "done", "ok": False,
            "plan_id": plan_id,
            "error": "Injected failure: " + injection["scenario_id"],
            "remediation": scenario["remediation"],
        }
        yield _sse(done_event)
        return
```

### Important: this is NOT a mock

The injected failure goes through the REAL UI pipeline:
- Real SSE events (step_start → log → step_failed → done)
- Real remediation modal rendering
- Real option display with real availability computation
- Only the actual command execution is skipped

This tests the full stack, not just the UI.

---

## Debugger Drawer Tab 2 Layout

```
┌─────────────────────────────────────────────┐
│ [Scenarios] [Overrides] [...]               │
│ ─────────────────────────────────────────── │
│                                              │
│ 🖥️ System Profile                           │
│ Currently: Debian 12 (real)                  │
│ Override: [dropdown: real|debian|fedora|...] │
│                                              │
│ 🔧 Tool State                               │
│ ┌──────────────────────────────────────────┐│
│ │ Quick: [Force All Missing] [Reset All]   ││
│ │                                          ││
│ │ python3  ✅  ○real ○missing ○installed   ││
│ │ pip      ✅  ○real ○missing ○installed   ││
│ │ ruff     ✅  ○real ○missing ○installed   ││
│ │ docker   ✅  ○real ○missing ○installed   ││
│ │ kubectl  ❌  ○real ○missing ○installed   ││
│ │ ...                                      ││
│ └──────────────────────────────────────────┘│
│                                              │
│ 💥 Failure Injection                         │
│ Next install fails with:                     │
│ [dropdown: none | pep668 | rustc | ...]     │
│ Scope: [next_install | any | tool:___]       │
│                                              │
│ Active: PEP 668 (Debian) ← next install     │
│ [Clear Injection]                            │
│                                              │
│ ─────────────────────────────────────────── │
│ 🚿 Override Hygiene                          │
│ Active overrides: 3                          │
│ [Clear All Overrides]                        │
└─────────────────────────────────────────────┘
```

---

## Integration Points — What Gets Modified

### API calls that need system profile awareness

These are the backend functions that call `_detect_os()` and would
need to respect the override:

| Function | File | Currently calls | Override needed |
|----------|------|----------------|-----------------|
| `execute_plan()` | orchestrator.py | receives system_profile param | Already parameterized ✅ |
| `install_tool()` | orchestrator.py | `_detect_os()` | Replace with `_resolve_system_profile()` |
| SSE `generate()` | routes_audit.py | `_detect_os()` | Replace with `_resolve_system_profile()` |
| SSE `generate_dag()` | routes_audit.py | `_detect_os()` | Replace with `_resolve_system_profile()` |
| Plan resolution endpoints | routes_audit.py | `_detect_os()` | Replace with `_resolve_system_profile()` |

**Key insight:** `execute_plan()` is already parameterized with
`system_profile=`. The override only needs to happen at the entry
points that create the profile. There are exactly 3-4 call sites.

### Frontend API calls that need override headers

| Function | File | Currently calls | Change |
|----------|------|----------------|--------|
| `installWithPlan()` | _globals.html | POST /audit/install-plan/execute | Add X-Dev headers |
| Plan resolution | _globals.html | POST /audit/install-plan | Add X-Dev headers |
| `loadToolsStatus()` | _dashboard.html | GET /tools/status | Client-side override only |

**Key insight for tool status:** The tool status endpoint returns
real `shutil.which()` results. For tool overrides, we DON'T need
to change the backend — we modify the response client-side after
receiving it. This is simpler and more honest (the override is
clearly a UI layer concern, not a system detection concern).

---

## Touch Point Inventory

### Files to create

| File | Purpose | Est. lines |
|------|---------|-----------|
| `src/core/services/dev_overrides.py` | `_resolve_system_profile()` helper | ~50 |

### Files to modify

| File | Change | Est. lines changed |
|------|--------|-------------------|
| `src/ui/web/templates/scripts/_stage_debugger.html` | Tab 2: overrides UI | +200 |
| `src/ui/web/templates/scripts/_dashboard.html` | Tool override patching in loadToolsStatus | +25 |
| `src/ui/web/templates/scripts/_globals.html` | Override headers in API calls + override banner | +30 |
| `src/ui/web/routes_audit.py` | Replace `_detect_os()` with helper at entry points | +15 |
| `src/ui/web/routes_dev.py` | System override validation endpoint | +20 |
| `src/ui/web/static/css/admin.css` | Override indicator styles | +30 |

### Files NOT modified

| File | Why not |
|------|---------|
| `orchestrator.py` | Already parameterized with `system_profile=` |
| `identity.py` | D0 concern, unchanged |
| `remediation_handlers.py` | D1 concern, unchanged |
| `handler_matching.py` | Takes system_profile as input |
| `remediation_planning.py` | Takes system_profile as input |

---

## Implementation Order

```
D2.1  Create src/core/services/dev_overrides.py
      └─ _resolve_system_profile() function
      └─ Reads X-Dev-System-Override header
      └─ Verifies dev mode + owner identity
      └─ Falls back to real _detect_os()
      └─ Test: with/without header, with/without owner

D2.2  Update entry points in routes_audit.py
      └─ Depends on: D2.1
      └─ Replace _detect_os() calls with _resolve_system_profile()
      └─ Only 3-4 call sites
      └─ Test: normal requests unchanged, override header respected

D2.3  Frontend: override storage helpers
      └─ _getDevOverrides(), _saveDevOverrides()
      └─ sessionStorage read/write
      └─ _apiHeaders() adds override headers when active
      └─ Test: set/get/clear overrides

D2.4  Frontend: system profile picker (Tab 2 top section)
      └─ Depends on: D2.3 (storage helpers)
      └─ Dropdown with system presets
      └─ Override banner appears when active
      └─ Test: select Fedora → banner shows → API calls include header

D2.5  Frontend: tool state overrides (Tab 2 middle section)
      └─ Depends on: D2.3 (storage helpers)
      └─ Per-tool radio buttons: real / missing / installed
      └─ Modify loadToolsStatus() to apply client-side patches
      └─ Test: force ruff missing → dashboard shows ruff as ❌

D2.6  Frontend: failure injection (Tab 2 bottom section)
      └─ Depends on: D2.3 (storage helpers) + D1.2 (scenarios)
      └─ Dropdown of scenarios to inject
      └─ Inject mechanism in SSE request headers
      └─ Backend intercept in routes_audit.py SSE handler
      └─ Test: set injection → install any tool → injected failure appears

D2.7  CSS: override indicators + banner styles
      └─ Can be done in parallel with D2.4-D2.6
```

**Parallelizable:** D2.4 + D2.5 + D2.6 are independent (different sections
of the same tab). D2.7 can be done alongside any of them.
**Critical path:** D2.1 → D2.2 → D2.3 → D2.4

---

## Safety & Isolation

### Override scope

| Override | Scope | Persistence | Leak risk |
|----------|-------|-------------|-----------|
| System profile | Per-tab sessionStorage + request header | Tab close clears | Low — header only sent when dev mode |
| Tool state | Per-tab sessionStorage + client-side patch | Tab close clears | None — client-side only |
| Failure injection | Per-tab sessionStorage + request header | One-shot or tab close | Low — validated on backend |

### What prevents override leaking

1. **sessionStorage** — automatically cleared when tab closes
2. **Override banner** — visual indicator always visible when active
3. **Owner check** — backend validates identity before accepting overrides
4. **One-shot injection** — `next_install` trigger auto-clears after use
5. **Clear All button** — prominent, always visible in the overrides tab

### What happens if override is set but dev mode is disabled

The override header is only sent when `window._devModeStatus.dev_mode`
is true. If the user disables dev mode in Settings:
- Frontend stops sending override headers
- Backend ignores orphaned sessionStorage values
- Next API call uses real system profile
- Banner disappears

---

## Data Flow: System Override

```
Debugger Drawer Tab 2                Backend
────────────────────                ──────────

Select "Fedora 39"                   
  │                                  
  ▼                                  
sessionStorage                       
  dcp_dev_overrides.system_profile   
  = { preset_id: "fedora_39", ... }  
  │                                  
  │  (any subsequent API call)       
  ▼                                  
fetch('/audit/install-plan', {       
  headers: {                         
    'X-Dev-System-Override':         
    '{"preset_id":"fedora_39"}'      
  }                                  
})                                   
                                     ▼
                                     _resolve_system_profile()
                                       │ reads header
                                       │ validates owner
                                       │ returns SYSTEM_PRESETS["fedora_39"]
                                       ▼
                                     resolve_install_plan(tool, profile)
                                       │ uses Fedora profile
                                       │ selects dnf method
                                       ▼
                                     Response: plan with Fedora steps
  ▼                                  
UI renders plan                      
  (shows dnf commands instead of apt)
```

---

## Data Flow: Tool Override

```
Debugger Drawer Tab 2                 Dashboard
────────────────────                 ──────────

Toggle "ruff" → "missing"            
  │                                   
  ▼                                   
sessionStorage                       
  dcp_dev_overrides.tool_overrides   
  = { "ruff": "missing" }            
  │                                   
  │  (dashboard loads or refreshes)   
  ▼                                   
loadToolsStatus()                     
  │ fetch('/tools/status')            
  │ → receives real data              
  │ → tools[].ruff.available = true   
  │                                   
  │ Apply overrides:                  
  │ ruff.available = false ← override 
  │ ruff._dev_override = "forced_miss"
  │ Recompute counts                  
  ▼                                   
Render dashboard                      
  ruff shows as ❌ with 🔧 marker    
  Install button appears              
```

---

## Interaction With Existing Features

### Install flow with system override

When a system override is active and the user clicks Install:
1. Plan resolution uses the override profile
2. Plan shows Fedora-specific steps (e.g., `dnf install` instead of `apt-get install`)
3. **Execution would fail** because we're actually on Debian

**This is intentional.** The developer can:
- See the plan without executing it
- Execute with failure injection to test the remediation flow
- Execute for real to see what actually happens (will fail, which
  triggers real remediation — also useful for testing)

### Tool override + install flow

When a tool is overridden to "missing" and the user clicks Install:
1. Dashboard shows the install button
2. User clicks Install
3. Plan resolves normally (the tool IS actually installed)
4. Plan says `already_installed: true`

**Problem:** The override only affects the dashboard rendering, not
the plan resolution. Should it?

**Decision: NO.** The override is a UI-level concern only. Plan
resolution checks `shutil.which()` which reports the real state.
If the developer wants to test the full install flow for an installed
tool, they use failure injection (D2.6), not tool overrides.

This keeps the layers clean:
- Tool override = dashboard testing
- Failure injection = flow testing
- System override = plan resolution testing

---

## Testing Strategy

### Manual tests

1. **System override:**
   - Select Fedora → banner appears
   - Load dashboard → tools card unchanged (tool states are real)
   - Click Install on a tool → plan shows dnf commands
   - Clear override → plan shows apt commands

2. **Tool override:**
   - Force ruff missing → dashboard shows ruff as ❌
   - Click Install → plan says already_installed (real state)
   - Force docker installed → dashboard shows docker as ✅
   - Clear all → dashboard shows real state

3. **Failure injection:**
   - Set injection to PEP 668
   - Install ruff → injected failure, remediation modal appears
   - Modal shows real §6 options with correct availability
   - Injection auto-clears (one-shot)
   - Install ruff again → real execution (no injection)

4. **Override persistence:**
   - Set overrides → reload page → overrides still active
   - Close tab → open new tab → overrides cleared
   - Set override → disable dev mode → override ignored

### Integration test

```python
# Test _resolve_system_profile with override header
from src.core.services.dev_overrides import _resolve_system_profile

# Simulated request with override header
# Should return Fedora profile when owner, real profile when not
```

---

## Estimated Effort

| Step | New lines | Changed lines | Files |
|------|-----------|--------------|-------|
| D2.1 dev_overrides.py | 50 | 0 | 1 new |
| D2.2 routes_audit entry points | 15 | 0 | 1 modified |
| D2.3 FE storage helpers | 40 | 0 | 1 modified |
| D2.4 System picker UI | 60 | 0 | 1 modified |
| D2.5 Tool state UI | 80 | 25 | 2 modified |
| D2.6 Failure injection | 80 | 15 | 2 modified |
| D2.7 CSS | 30 | 0 | 1 modified |
| **Total** | **~355** | **~40** | **1 new + 6 modified** |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Override leaks to production API calls | Low | High | sessionStorage + owner check + banner |
| System override causes confusing plan failures | Medium | Low | Banner clearly shows override is active |
| Tool override contradicts real install result | Medium | Low | Documented as UI-only override |
| Performance: extra header parsing per request | Low | Low | Only parsed when header present |
| Failure injection skips real execution | Low | Low | Intentional — documented behavior |

---

## Traceability

| Requirement | Source | Implementation |
|------------|--------|---------------|
| Show other system presets | User request ("show even another system preset") | System profile override with preset picker |
| Show disabled/impossible in relevant cases | User request ("offer it to you disabled in relevant cases") | Override + real availability computation |
| Deps install options | User request ("deps install options in other cases") | Override produces different availability |
| Debug tools/deps for testing | User request ("add debug tools/deps") | Tool state override + failure injection |
| Development & QA | User request ("development & qa testing feature") | Full override engine with session isolation |

---

## What D2 Does NOT Include

- Assistant content inspection → D3
- Live SSE event injection (beyond failure inject) → D3
- Recipe browser → D3
- Multiple simultaneous system profiles (split-screen) → future
- Override sharing between tabs → out of scope (sessionStorage is per-tab)
- Override presets ("QA Profile: Minimal Alpine") → future
