# Phase D1 — Scenario Library & Modal Tester

> **Status:** Planning
> **Created:** 2026-02-25
> **Parent:** Stage Debugger feature
> **Depends on:** D0 (identity gate — `window._devModeStatus.dev_mode`)

---

## Objective

Build the scenario library (curated failure presets) and the first tab
of the stage debugger drawer: the **Modal Tester**. This gives the
developer the ability to open any remediation modal with synthetic
§6-shaped data, without running an actual install, without causing a
real failure, and without needing the target tool or system state.

---

## Problem Statement

### Why this is needed

The remediation model (R1-R7) introduces complex UI with:
- 3 availability states (ready, locked, impossible)
- Risk badges (low, medium, high)
- Breadcrumb chains at varying depths (0, 1, 2+)
- Lock reasons and unlock hints
- Step count estimates
- Strategy-based execution dispatch (10+ strategies)

Testing all combinations requires triggering real failures:
- PEP 668 on pip (needs an externally-managed Python)
- rustc version mismatch (needs an old compiler)
- GCC build bug (needs a specific Cargo build to fail)
- npm EACCES (needs specific permission state)
- Disk full (needs... a full disk)
- OOM (needs to exhaust memory)

This is impractical for iterative UI development. We need to
**synthesize** these states on demand.

### What the tester does

1. Developer opens the stage debugger drawer (🔧 icon)
2. Clicks the "Scenarios" tab
3. Sees a grid of preset failure scenarios
4. Clicks one → the real `_showRemediationModal()` opens with
   synthetic §6 data
5. Can interact with the modal exactly as if a real failure occurred
6. Can test option clicks, strategy dispatch, availability rendering
7. No backend calls during modal rendering (data is pre-built)

---

## Scenario Design

### What makes a good test scenario?

A scenario exercises a specific **combination** of UI states:

| Dimension | Possible values |
|-----------|----------------|
| Availability mix | all-ready, mixed, all-locked, has-impossible |
| Risk levels | all-low, has-medium, has-high |
| Chain depth | 0, 1, 2, 3 |
| Option count | 1, 2-3, 4+ |
| Strategies | retry, switch, install_dep, manual, env_fix, cleanup |
| Lock reasons | short text, long text with packages list |
| Step counts | 1, 3, 5+ |
| System deps | none, has missing_packages, all satisfied |

### Preset Scenarios

Each scenario is a named configuration that produces a complete §6
response shape when rendered.

#### Group 1: Method-Family Failures (most common)

```
Scenario ID          | Failure                    | Avail Mix         | Options  | Risk
─────────────────────┼────────────────────────────┼───────────────────┼──────────┼──────
pep668_debian        | PEP 668 (pip, Debian)      | 3 ready, 1 locked | 4        | low
pep668_fedora        | PEP 668 (pip, Fedora)      | 2 ready, 2 locked | 4        | low
cargo_rustc_old      | rustc version mismatch     | 1 ready, 2 locked | 3        | medium
cargo_gcc_bug        | GCC/binutils crash         | 2 ready, 1 imp    | 3        | high
cargo_missing_lib    | Missing C library          | 1 ready, 1 locked | 2        | low
npm_eacces           | npm EACCES                 | 2 ready           | 2        | low
npm_missing          | npm not found              | 1 ready, 1 locked | 2        | low
apt_stale_index      | apt index out of date      | 1 ready            | 1        | low
apt_locked           | dpkg lock held             | 1 ready, 1 manual | 2        | medium
snap_unavailable     | snapd not running          | 2 ready, 1 imp    | 3        | low
brew_not_found       | Formula not found          | 1 ready, 1 manual | 2        | low
```

#### Group 2: Infrastructure Failures

```
Scenario ID          | Failure                    | Avail Mix         | Options  | Risk
─────────────────────┼────────────────────────────┼───────────────────┼──────────┼──────
network_offline      | No network connectivity    | 1 manual          | 1        | n/a
disk_full            | No space left on device    | 1 manual          | 1        | high
oom_137              | Exit code 137 (OOM)        | 2 ready, 1 manual | 3        | high
no_sudo              | sudo not available         | 1 locked, 1 imp   | 2        | n/a
permission_denied    | Permission denied          | 2 ready, 1 manual | 3        | medium
timeout_curl         | Download timeout           | 2 ready            | 2        | low
```

#### Group 3: Chain Scenarios (escalation depth)

```
Scenario ID          | Chain Depth | Breadcrumbs                       | Options
─────────────────────┼─────────────┼───────────────────────────────────┼────────
chain_depth_0        | 0           | (none)                            | 3
chain_depth_1        | 1           | ruff → pip                        | 3
chain_depth_2        | 2           | ruff → pip → pipx                 | 2
chain_depth_3        | 3           | cargo-audit → cargo → rustup → curl | 2
```

#### Group 4: Edge Cases

```
Scenario ID          | What it tests
─────────────────────┼──────────────────────────────────────────────
single_option        | Only 1 option (no choice to make)
all_impossible       | All options are impossible (dead end)
all_locked           | All options are locked (must unlock first)
long_lock_reason     | Lock reason with multi-line text + package list
many_options         | 6+ options (tests scrolling)
empty_stderr         | No stderr content (generic failure)
unknown_failure      | No handler matched (fallback options only)
```

### Total: ~25 scenarios covering the full state space.

---

## Scenario Data Shape

Each scenario is a plain JavaScript object that conforms to the §6
remediation response shape:

```javascript
const SCENARIO = {
    // Metadata (for the scenario picker UI)
    _meta: {
        id: "pep668_debian",
        label: "PEP 668 — pip on Debian",
        group: "method-family",
        description: "pip refuses to install outside venv (Debian 12+)",
        tests: ["availability:mixed", "risk:low", "options:4"],
    },

    // Actual §6 response data (passed to _showRemediationModal)
    toolId: "ruff",
    toolLabel: "Ruff",
    
    remediation: {
        failure: {
            failure_id: "pep668",
            category: "environment",
            label: "Externally Managed Python (PEP 668)",
            description: "This system's Python is managed by the OS...",
            pattern: "externally-managed-environment",
            matched_layer: "method_family",
        },
        options: [
            {
                id: "use_pipx",
                label: "Install via pipx (isolated)",
                description: "pipx installs each tool in its own venv...",
                icon: "📦",
                recommended: true,
                strategy: "install_dep_then_switch",
                risk: "low",
                availability: "ready",
                lock_reason: null,
                step_count: 3,
                estimated_time: "~30s",
            },
            {
                id: "use_venv",
                label: "Create a project venv",
                description: "Create a Python virtual environment...",
                icon: "🐍",
                recommended: false,
                strategy: "env_fix",
                risk: "low",
                availability: "ready",
                lock_reason: null,
                step_count: 2,
            },
            {
                id: "break_system_packages",
                label: "Force install (--break-system-packages)",
                description: "Override PEP 668 protection. Installs directly...",
                icon: "⚠️",
                recommended: false,
                strategy: "retry_with_modifier",
                risk: "medium",
                availability: "ready",
                lock_reason: null,
                step_count: 1,
            },
            {
                id: "install_from_apt",
                label: "Install from apt (if available)",
                description: "Some Python tools are packaged by Debian...",
                icon: "📋",
                recommended: false,
                strategy: "switch_method",
                risk: "low",
                availability: "locked",
                lock_reason: "python3-ruff is not available in Debian repos",
                step_count: 1,
            },
        ],
        chain: null,
        fallback: {
            actions: ["cancel", "retry"],
        },
    },
};
```

---

## Stage Debugger Drawer Architecture

### Visual Design

The stage debugger is a slide-out drawer anchored to the right edge
of the viewport (or bottom on narrow screens). It uses the same
glass-panel aesthetic as the assistant panel.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Admin Dashboard                                      🔧 DEV  ⚙️   │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─ main content ────────────────────────┐  ┌─ drawer ──────────┐   │
│  │                                        │  │ Stage Debugger     │   │
│  │                                        │  │ ─────────────────  │   │
│  │                                        │  │ [Scenarios] [▾...]│   │
│  │                                        │  │                    │   │
│  │                                        │  │ Method Failures    │   │
│  │                                        │  │ ┌──────────────┐  │   │
│  │                                        │  │ │ PEP 668 (Deb)│  │   │
│  │                                        │  │ │ 📦  4 opts   │  │   │
│  │                                        │  │ │ mixed avail  │  │   │
│  │                                        │  │ └──────────────┘  │   │
│  │                                        │  │ ┌──────────────┐  │   │
│  │                                        │  │ │ cargo rustc  │  │   │
│  │                                        │  │ │ 🔧  3 opts   │  │   │
│  │                                        │  │ │ locked+ready │  │   │
│  │                                        │  │ └──────────────┘  │   │
│  │                                        │  │                    │   │
│  │                                        │  │ Infrastructure     │   │
│  │                                        │  │ ┌──────────────┐  │   │
│  │                                        │  │ │ Disk Full    │  │   │
│  │                                        │  │ └──────────────┘  │   │
│  │                                        │  │                    │   │
│  │                                        │  │ Chains             │   │
│  │                                        │  │ ┌──────────────┐  │   │
│  │                                        │  │ │ Depth 2      │  │   │
│  │                                        │  │ └──────────────┘  │   │
│  └────────────────────────────────────────┘  └───────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

### Toggle mechanism

- The 🔧 DEV badge in the topbar becomes clickable
- Click → toggles the drawer open/closed
- Drawer is NOT part of the assistant panel — it's a separate layer
- Drawer has z-index above content but below modals (so modals launched
  from the drawer appear ON TOP of the drawer)
- Drawer width: ~280px (same as assistant panel)

### Scenario card design

Each scenario in the grid is a compact card:

```
┌─────────────────────────────────┐
│ PEP 668 — pip on Debian     📦 │
│ ─────────────────────────────── │
│ 4 options · mixed availability  │
│ risk: low · depth: 0            │
│ ─────────────────────────────── │
│ [▶ Launch]                      │
└─────────────────────────────────┘
```

Clicking "▶ Launch" calls:

```javascript
_showRemediationModal(
    scenario.toolId,
    scenario.toolLabel,
    scenario.remediation,
    function onSuccess() {
        console.log('[stage-debugger] scenario completed:', scenario._meta.id);
    },
    '(synthetic stderr for ' + scenario._meta.id + ')',
);
```

This is the REAL `_showRemediationModal()` — the same function that
renders during actual failures. The only difference is the data source.

---

## Scenario Data Source

### Option A: Static JSON file (backend serves)

```
src/ui/web/static/data/dev-scenarios.json
```

**Pros:** Clean separation, cacheable, could be extended at runtime
**Cons:** Separate file to maintain, requires fetch() call

### Option B: Inline in JavaScript (frontend-only)

```
src/ui/web/templates/scripts/_stage_debugger.html
  → const _DEV_SCENARIOS = [ ... ];
```

**Pros:** No network call, instant, all in one file
**Cons:** Larger script payload (but only loaded in dev mode)

### Option C: Backend renders from handler data

```python
# routes_dev.py
@dev_bp.route("/api/dev/scenarios")
def dev_scenarios():
    """Generate scenario presets from the actual handler registry."""
    scenarios = []
    for family, handlers in METHOD_FAMILY_HANDLERS.items():
        for handler in handlers:
            scenarios.append(_build_scenario_from_handler(
                handler, family, system_profiles=SYSTEM_PRESETS
            ))
    return jsonify(scenarios)
```

**Pros:** Scenarios always match the real handler data, never drift
**Cons:** Requires building the full §6 response per scenario
(which means calling `build_remediation_response()` with fake inputs)

### Decision: Option C (backend renders from real handlers)

**Rationale:**
1. The whole point of the debugger is to test real behavior. If
   scenarios are hand-crafted JSON, they can drift from the actual
   handler data.
2. `build_remediation_response()` already exists (R2.2). We just
   need to call it with synthetic inputs.
3. The frontend doesn't need to know handler internals.
4. Adding a new handler automatically creates a new scenario.
5. Custom scenarios can be layered on top (hand-crafted edge cases
   that don't correspond to a single handler).

### Backend scenario generation

```python
# In routes_dev.py or a new src/core/services/dev_scenarios.py

SYSTEM_PRESETS = {
    "debian_12": {
        "system": "Linux", "distro": {"id": "debian", "family": "debian",
        "version": "12", "name": "Debian GNU/Linux 12 (bookworm)"},
        "package_manager": {"primary": "apt"},
        "capabilities": {"has_sudo": True, "has_systemd": True},
    },
    "fedora_39": {
        "system": "Linux", "distro": {"id": "fedora", "family": "rhel",
        "version": "39", "name": "Fedora Linux 39"},
        "package_manager": {"primary": "dnf"},
        "capabilities": {"has_sudo": True, "has_systemd": True},
    },
    "alpine_318": {
        "system": "Linux", "distro": {"id": "alpine", "family": "alpine",
        "version": "3.18", "name": "Alpine Linux v3.18"},
        "package_manager": {"primary": "apk"},
        "capabilities": {"has_sudo": False, "has_systemd": False},
    },
    "macos_14": {
        "system": "Darwin", "distro": {"id": "macos", "family": "macos",
        "version": "14.0", "name": "macOS 14.0"},
        "package_manager": {"primary": "brew"},
        "capabilities": {"has_sudo": True, "has_systemd": False},
    },
    "arch_latest": {
        "system": "Linux", "distro": {"id": "arch", "family": "arch",
        "version": "", "name": "Arch Linux"},
        "package_manager": {"primary": "pacman"},
        "capabilities": {"has_sudo": True, "has_systemd": True},
    },
}

def _generate_handler_scenarios(system_preset_id: str = "debian_12"):
    """Generate one scenario per handler using the given system preset."""
    profile = SYSTEM_PRESETS[system_preset_id]
    scenarios = []
    
    # Walk METHOD_FAMILY_HANDLERS
    for family, handlers in METHOD_FAMILY_HANDLERS.items():
        for handler in handlers:
            response = build_remediation_response(
                tool_id=f"test_{family}",
                step_idx=0,
                step_label=f"Install test_{family}",
                exit_code=handler.get("exit_code", 1),
                stderr=_synthesize_stderr(handler),
                method=family,
                system_profile=profile,
            )
            if response:
                scenarios.append({
                    "_meta": {
                        "id": f"{family}_{handler['failure_id']}",
                        "label": handler["label"],
                        "group": "method-family",
                        "family": family,
                        "system": system_preset_id,
                        "description": handler.get("description", ""),
                        "option_count": len(response.get("options", [])),
                        "availability": _summarize_availability(response),
                        "max_risk": _max_risk(response),
                    },
                    "toolId": f"test_{family}",
                    "toolLabel": f"Test ({family})",
                    "remediation": response,
                })
    
    # Walk INFRA_HANDLERS
    for handler in INFRA_HANDLERS:
        response = build_remediation_response(
            tool_id="test_infra",
            step_idx=0,
            step_label="Install test_infra",
            exit_code=handler.get("exit_code", 1),
            stderr=_synthesize_stderr(handler),
            method="apt",
            system_profile=profile,
        )
        if response:
            scenarios.append({
                "_meta": {
                    "id": f"infra_{handler['failure_id']}",
                    "label": handler["label"],
                    "group": "infrastructure",
                    "description": handler.get("description", ""),
                    "option_count": len(response.get("options", [])),
                    "availability": _summarize_availability(response),
                    "max_risk": _max_risk(response),
                },
                "toolId": "test_infra",
                "toolLabel": "Test (Infra)",
                "remediation": response,
            })
    
    return scenarios


def _synthesize_stderr(handler: dict) -> str:
    """Generate minimal stderr that matches the handler's pattern."""
    # The handler has a 'pattern' field (regex string)
    # We need to generate a string that matches it
    # For simple patterns: just return the pattern literal
    # For complex regex: use a known match string stored in the handler
    return handler.get("example_stderr", handler.get("pattern", "error"))


def _summarize_availability(response: dict) -> str:
    """Summarize availability mix: 'all-ready', 'mixed', 'all-locked', etc."""
    avails = [o.get("availability", "ready") for o in response.get("options", [])]
    if all(a == "ready" for a in avails): return "all-ready"
    if all(a == "locked" for a in avails): return "all-locked"
    if all(a == "impossible" for a in avails): return "all-impossible"
    return "mixed"


def _max_risk(response: dict) -> str:
    """Return the highest risk level among options."""
    risks = [o.get("risk", "low") for o in response.get("options", [])]
    for level in ("high", "medium", "low"):
        if level in risks: return level
    return "low"
```

### Handler `example_stderr` field

To make scenario generation work, each handler needs an `example_stderr`
field — a minimal stderr string that definitively matches the handler's
pattern. This is useful for both testing AND scenario generation.

```python
# In remediation_handlers.py, each handler gains:
{
    "failure_id": "pep668",
    "pattern": r"externally-managed-environment",
    "example_stderr": "error: externally-managed-environment\n"
                      "× This environment is externally managed\n"
                      "╰─> To install Python packages system-wide, try apt install\n"
                      "    python3-xyz, where xyz is the package you are trying to\n"
                      "    install.\n",
    # ... rest of handler
}
```

This is NOT a schema change — it's an additive data field. Handlers
without `example_stderr` fall back to a minimal pattern match.

**Estimated data changes:** ~2-5 lines per handler × 31 handlers = ~100 lines.

### Chain scenario generation

Chain scenarios are special — they require pre-built chain state:

```python
def _generate_chain_scenarios():
    """Generate scenarios with escalation chains at various depths."""
    scenarios = []
    
    # Depth 1: ruff → pip failure
    chain_1 = {
        "chain_id": "test_chain_d1",
        "depth": 1,
        "breadcrumbs": [
            {"label": "Install ruff", "depth": 0, "status": "failed"},
        ],
        "original_goal": {"tool": "ruff", "label": "Ruff"},
    }
    
    response = build_remediation_response(
        tool_id="ruff", step_idx=0, step_label="Install ruff",
        exit_code=1, stderr="error: externally-managed-environment",
        method="pip",
        system_profile=SYSTEM_PRESETS["debian_12"],
        chain=chain_1,
    )
    scenarios.append({
        "_meta": {
            "id": "chain_depth_1",
            "label": "Chain Depth 1 (ruff → pip)",
            "group": "chains",
            "chain_depth": 1,
        },
        "toolId": "ruff",
        "toolLabel": "Ruff",
        "remediation": response,
    })
    
    # Depth 2, 3... similar
    
    return scenarios
```

### Custom edge-case scenarios

Some scenarios can't be generated from handlers (they test UI edge
cases, not handler logic):

```python
CUSTOM_SCENARIOS = [
    {
        "_meta": {
            "id": "single_option",
            "label": "Single Option Only",
            "group": "edge-cases",
            "description": "Tests UI when there's exactly 1 option",
        },
        "toolId": "test_edge",
        "toolLabel": "Test (Edge)",
        "remediation": {
            "failure": {
                "failure_id": "test_single",
                "category": "test",
                "label": "Single Option Test",
                "description": "Only one remediation option available.",
            },
            "options": [
                {
                    "id": "only_option",
                    "label": "The only thing you can do",
                    "description": "This is the only available option.",
                    "icon": "🔧",
                    "recommended": True,
                    "strategy": "retry_with_modifier",
                    "risk": "low",
                    "availability": "ready",
                    "step_count": 1,
                },
            ],
            "chain": None,
            "fallback": {"actions": ["cancel"]},
        },
    },
    # ... more edge cases
]
```

---

## API Endpoints

### `GET /api/dev/scenarios`

Returns all scenarios for the currently specified system preset.

**Query params:**
- `system` — system preset ID (default: "debian_12")

**Response:**
```json
{
    "scenarios": [
        {
            "_meta": { ... },
            "toolId": "...",
            "toolLabel": "...",
            "remediation": { ... }
        }
    ],
    "system_presets": ["debian_12", "fedora_39", "alpine_318", "macos_14", "arch_latest"],
    "current_system": "debian_12"
}
```

### `GET /api/dev/scenarios/:id`

Returns a single scenario by ID. Useful for deep-linking.

---

## Frontend Components

### New file: `src/ui/web/templates/scripts/_stage_debugger.html`

This is a Jinja2 include, loaded only when dev mode is active.
The boot script from D0 handles conditional loading.

### Component structure

```
_stage_debugger.html
├── State
│   ├── _debugDrawerOpen (bool)
│   ├── _debugScenarios (array, loaded from API)
│   └── _debugCurrentSystem (string, selected preset)
├── Functions
│   ├── _toggleDebugDrawer()       – open/close
│   ├── _loadDebugScenarios()      – fetch from /api/dev/scenarios
│   ├── _renderDebugDrawer()       – full drawer HTML
│   ├── _renderScenarioGrid()      – scenario cards
│   ├── _launchScenario(id)        – find scenario, call _showRemediationModal
│   ├── _changeDebugSystem(preset) – re-fetch scenarios with new system
│   └── _renderScenarioCard(s)     – single card HTML
└── CSS (inline or in admin.css)
    ├── .debug-drawer          – slide-out panel
    ├── .debug-drawer.open     – visible state
    ├── .debug-scenario-card   – clickable card
    ├── .debug-group-header    – category separator
    └── .debug-system-picker   – system preset dropdown
```

### Drawer toggle integration

In `_dev_mode.html` (or wherever the boot script lives):

```javascript
// The DEV badge becomes the toggle button
if (devActive) {
    const badge = document.getElementById('dev-mode-badge');
    if (badge) {
        badge.style.display = '';
        badge.style.cursor = 'pointer';
        badge.addEventListener('click', (e) => {
            e.stopPropagation();
            _toggleDebugDrawer();
        });
    }
}
```

### System preset picker

At the top of the drawer, a dropdown to select which system to test:

```javascript
function _renderSystemPicker() {
    const presets = _debugSystemPresets || [];
    const current = _debugCurrentSystem || 'debian_12';
    
    let html = '<select id="debug-system-select" onchange="_changeDebugSystem(this.value)">';
    for (const p of presets) {
        const label = p.replace('_', ' ').replace(/(\d)/, ' $1');
        html += `<option value="${p}" ${p === current ? 'selected' : ''}>${label}</option>`;
    }
    html += '</select>';
    return html;
}
```

Changing the system preset re-fetches scenarios from the backend with
`?system=fedora_39`, which rebuilds the full §6 response with
`SYSTEM_PRESETS["fedora_39"]` as the system profile. This means
**the same handler produces different availability results** depending
on the selected system — which is exactly what needs testing.

---

## Execution Strategy Bypass

When a scenario modal is shown and the user clicks an option's
action button, the `_remExecute()` function is called. For scenarios,
we need to **intercept** execution to avoid actually running commands.

### Two approaches:

#### A: Flag on the modal

When launching from a scenario, pass a flag:
```javascript
// In _launchScenario:
window._debugScenarioActive = true;

_showRemediationModal(
    scenario.toolId,
    scenario.toolLabel,
    scenario.remediation,
    function onSuccess() {
        window._debugScenarioActive = false;
        console.log('[debugger] scenario complete');
    },
    scenario._meta.example_stderr || '',
);
```

In `_remExecute()`:
```javascript
if (window._debugScenarioActive) {
    console.log('[debugger] Would execute strategy:', opt.strategy, opt);
    // Show a toast: "Strategy {X} would execute here"
    showToast(`🔧 Would execute: ${opt.strategy}`, 'info');
    return;
}
```

#### B: Dry-run mode flag on options

Each option in the scenario data carries `_dry_run: true`:
```javascript
for (const opt of scenario.remediation.options) {
    opt._dry_run = true;
}
```

In `_remExecute()`:
```javascript
if (opt._dry_run) {
    showToast(`🔧 Dry run: ${opt.strategy} → ${opt.label}`, 'info');
    return;
}
```

### Decision: Approach A

Simpler, doesn't mutate the scenario data, single flag to check.
The flag is set before modal open and cleared on modal close/success.

---

## Touch Point Inventory

### Files to create

| File | Purpose | Est. lines |
|------|---------|-----------|
| `src/core/services/dev_scenarios.py` | Scenario generation from handler data | ~250 |
| `src/ui/web/templates/scripts/_stage_debugger.html` | Drawer UI component | ~300 |

### Files to modify

| File | Change | Est. lines changed |
|------|--------|-------------------|
| `src/ui/web/routes_dev.py` | Add `/api/dev/scenarios` endpoint | +40 |
| `src/core/services/tool_install/data/remediation_handlers.py` | Add `example_stderr` per handler | +~100 (data) |
| `src/ui/web/templates/scripts/_globals.html` | `_remExecute` dry-run bypass | +8 |
| `src/ui/web/static/css/admin.css` | Drawer + scenario card styles | +60 |
| `src/ui/web/templates/dashboard.html` | Include `_stage_debugger.html` | +1 |
| `src/ui/web/templates/scripts/_dev_mode.html` (from D0) | Load debugger conditionally | +15 |

### Files to NOT modify

- `_showRemediationModal()` — used as-is, no changes needed
- `domain/handler_matching.py` — scenarios call the public function
- `domain/remediation_planning.py` — scenarios call build_remediation_response

---

## Implementation Order

```
D1.1  Add example_stderr to all handlers in remediation_handlers.py
      └─ Pure data, no logic changes
      └─ Validate: existing handler tests still pass

D1.2  Create src/core/services/dev_scenarios.py
      └─ Depends on: D1.1 (example_stderr exists)
      └─ Functions: _generate_handler_scenarios, _generate_chain_scenarios
      └─ Data: SYSTEM_PRESETS, CUSTOM_SCENARIOS
      └─ Test: import + call generates 20+ scenarios with valid §6 shapes

D1.3  Add /api/dev/scenarios endpoint to routes_dev.py
      └─ Depends on: D1.2 (scenario generator)
      └─ Serves scenarios, accepts ?system= param
      └─ Test: GET returns JSON array

D1.4  Create _stage_debugger.html (drawer UI)
      └─ Depends on: D1.3 (API exists)
      └─ Includes: drawer, scenario grid, system picker
      └─ Conditionally included when dev_mode = true
      └─ Test: drawer opens, scenarios render

D1.5  Add dry-run bypass to _remExecute
      └─ Depends on: D1.4 (scenarios can be launched)
      └─ Check window._debugScenarioActive flag
      └─ Show toast instead of executing
      └─ Test: click option in scenario modal → toast, no execution

D1.6  CSS: drawer + card styles
      └─ Can be done in parallel with D1.4
      └─ Match admin panel aesthetic
```

**Parallelizable:** D1.1 + D1.2 data work, D1.4 + D1.6 frontend work.
**Critical path:** D1.1 → D1.2 → D1.3 → D1.4 → D1.5

---

## Interaction with D0

D0 provides:
- `window._devModeStatus.dev_mode` — gate for everything in D1
- `document.body[data-dev-mode]` — CSS selector hook
- `🔧 DEV` badge — becomes the drawer toggle in D1

D1 adds:
- Click handler on the DEV badge
- Drawer injection (only when dev_mode = true)
- Scenario loading via API

---

## Testing Strategy

### Manual tests

1. **Badge → drawer:**
   Click 🔧 DEV badge → drawer slides open
   Click again → drawer slides closed

2. **Scenario loading:**
   Drawer opens → scenarios load from API
   System picker → change to Fedora → scenarios refresh
   Each scenario card shows correct metadata

3. **Scenario launch:**
   Click "▶ Launch" on PEP668 → remediation modal opens
   Modal shows 4 options with correct availability badges
   Click an option → toast shows "Would execute: ..."
   Modal closes → drawer still open

4. **Chain scenarios:**
   Launch chain_depth_2 → modal shows breadcrumbs
   Breadcrumbs show: "ruff → pip → pipx"

5. **Edge cases:**
   Launch all_impossible → all options greyed out
   Launch single_option → single option rendered
   Launch many_options → scrollable option list

### Integration test (backend)

```python
from src.core.services.dev_scenarios import _generate_handler_scenarios
scenarios = _generate_handler_scenarios("debian_12")
assert len(scenarios) >= 15
for s in scenarios:
    assert "remediation" in s
    assert "options" in s["remediation"]
    assert len(s["remediation"]["options"]) >= 1
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Scenario data drifts from handlers | Low | Medium | Generated from real handlers, not hand-crafted |
| example_stderr doesn't match pattern | Medium | Low | Validate at import: re.search(pattern, example) |
| Drawer interferes with assistant panel | Medium | Medium | Different z-index, independent toggle |
| Scenario modal confuses user (looks real) | Low | Low | "🔧 DEV SCENARIO" text in modal header |
| Performance: generating all scenarios on each request | Low | Low | Cache with TTL, or generate lazily |

---

## Estimated Effort

| Step | New lines | Changed lines | Files |
|------|-----------|--------------|-------|
| D1.1 example_stderr | 100 | 0 | 1 modified |
| D1.2 dev_scenarios.py | 250 | 0 | 1 new |
| D1.3 routes_dev endpoint | 40 | 0 | 1 modified |
| D1.4 _stage_debugger.html | 300 | 15 | 1 new + 2 modified |
| D1.5 dry-run bypass | 8 | 0 | 1 modified |
| D1.6 CSS styles | 60 | 0 | 1 modified |
| **Total** | **~758** | **~15** | **2 new + 6 modified** |

---

## Traceability

| Requirement | Source | Implementation |
|------------|--------|---------------|
| Test modals without real failures | User request ("test the modals") | Scenario launcher → _showRemediationModal |
| Show other system presets | User request ("show even another system preset") | SYSTEM_PRESETS + system picker dropdown |
| Show disabled options | User request ("offer it to you disabled") | build_remediation_response with locked/impossible |
| Fake visual states on toggle | User request ("fake the visual state of things on toggle") | Scenario grid with pre-built §6 data |
| Deps install options in other cases | User request ("deps install options in other cases") | Scenarios show install_dep strategies when relevant |
| Development & QA testing feature | User request ("I am in need of a development & qa testing feature") | Full stage debugger drawer with scenario library |

---

## What D1 Does NOT Include

- System profile override (active override that affects real API calls) → D2
- Tool state override (force tools missing/installed) → D2
- Assistant content inspector → D3
- Live SSE event injection → D3
- Recipe browser → D3
- Performance profiling → future
