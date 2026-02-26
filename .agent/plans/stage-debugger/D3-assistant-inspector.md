# Phase D3 — Assistant Inspector & Advanced Debugger

> **Status:** Planning
> **Created:** 2026-02-25
> **Parent:** Stage Debugger feature
> **Depends on:** D0 (identity gate), D1 (debugger drawer), D2 (overrides)

---

## Objective

Build the assistant content inspector and advanced debugging tools
that allow the developer to test and verify the assistant panel's
context-aware content without navigating through the entire UI,
and to inspect the internal state of the assistant engine, variant
resolution, and catalogue structure.

This phase also adds a catalogue browser, SSE event inspector, and
a recipe viewer — completing the stage debugger as a full QA workbench.

---

## Problem Statement

### Why the assistant inspector is needed

The assistant panel (built in the K8s/Docker conversation series) uses
a catalogue (`assistant-catalogue.json`) with ~100+ nodes organized
in a deep tree. Each node can have:
- Static content (`content`, `expanded` fields)
- Variants (`variants[]` with `when` conditions against DOM selectors)
- Resolvers (JavaScript functions that generate content dynamically)

Testing all combinations requires:
1. Navigating to the correct page/tab
2. Hovering/focusing on the correct element
3. Having the right DOM state (input values, selections)
4. Verifying the rendered content is correct

This is tedious and error-prone. The inspector lets the developer:
- Browse the entire catalogue tree
- Force-activate any node
- See variant resolution traces (which variant matched and why)
- Test resolvers with different input states

### Why the recipe viewer is needed

With 296 recipes in `TOOL_RECIPES`, the developer needs to:
- Browse recipes to verify their structure
- Check that `on_failure` handlers exist and are well-formed
- See which recipes have choices, data packs, custom steps
- Compare a recipe's plan output across different system profiles

### Why the SSE inspector is needed

The SSE stream is the communication backbone between back and frontend
during plan execution. When debugging:
- What events were sent? In what order?
- What was the exact data shape of each event?
- Did the remediation event carry the correct §6 response?

Currently this requires browser DevTools + manual SSE inspection.
An in-app inspector is faster and contextual.

---

## Component Breakdown

### Tab 3: Assistant Inspector

```
┌─────────────────────────────────────────────┐
│ [Scenarios] [Overrides] [Assistant] [...]   │
│ ─────────────────────────────────────────── │
│                                              │
│ 🤖 Assistant Inspector                       │
│                                              │
│ ┌── Catalogue Tree ────────────────────────┐ │
│ │ ▾ root                                    │ │
│ │   ▾ dashboard                             │ │
│ │     ▸ project-pulse                       │ │
│ │     ▸ toolchain                           │ │
│ │     ▸ integrations                        │ │
│ │   ▾ wizard                                │ │
│ │     ▸ step-1-project                      │ │
│ │     ▸ step-2-integrations                 │ │
│ │     ▸ step-3-k8s                          │ │
│ │       ▾ fields                            │ │
│ │         • namespace                       │ │
│ │         • workload-type    ← click        │ │
│ │         • replicas                        │ │
│ │   ▸ modals                                │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│ ┌── Selected Node ─────────────────────────┐ │
│ │ Path: wizard.step-3-k8s.fields           │ │
│ │       .workload-type                      │ │
│ │ Selector: select[name="workloadType"]     │ │
│ │ Has variants: yes (4)                     │ │
│ │ Has resolver: yes                         │ │
│ │                                           │ │
│ │ ── Preview ─────────────────────────────  │ │
│ │ [Force Activate]  [Show in Panel]         │ │
│ │                                           │ │
│ │ Content: "Choose the Kubernetes workload  │ │
│ │ type that best matches your application…" │ │
│ │                                           │ │
│ │ ── Variants ────────────────────────────  │ │
│ │ ▸ when: value = "deployment"  ← matched  │ │
│ │ ▸ when: value = "statefulset"             │ │
│ │ ▸ when: value = "daemonset"               │ │
│ │ ▸ when: value = "cronjob"                 │ │
│ │                                           │ │
│ │ ── Resolver Trace ──────────────────────  │ │
│ │ Input: { value: "deployment" }            │ │
│ │ Output: "<h4>Deployment</h4>..."          │ │
│ │ Duration: 2ms                             │ │
│ └──────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

#### Features

1. **Catalogue tree browser**
   - Fetches `assistant-catalogue.json` and renders as collapsible tree
   - Each node shows: selector, content preview, variant count, resolver flag
   - Click to select a node

2. **Node detail view**
   - Full path, selector, content, expanded text
   - Variant list with match status
   - Resolver output (if resolver exists)

3. **Force Activate**
   - Calls `window._assistant.activate(context, node)` directly
   - The real assistant panel renders the selected node's content
   - Bypasses DOM matching entirely

4. **Variant resolution trace**
   - Shows which variant matched, which didn't, and why
   - For element-state variants: shows what DOM value was used
   - For resolver variants: shows input → output + timing

5. **Input simulator** (for resolver/variant testing)
   - When node has a selector targeting an input/select:
     - Shows a mini-form to set the simulated value
     - Re-runs variant resolution with the simulated value
     - Shows updated preview

### Tab 4: Recipe Browser

```
┌─────────────────────────────────────────────┐
│ [Scenarios] [Overrides] [Assist] [Recipes]  │
│ ─────────────────────────────────────────── │
│                                              │
│ 📦 Recipe Browser  (296 recipes)             │
│ ┌──────────────────────────────────────────┐ │
│ │ 🔍 [search...........................]   │ │
│ │ Filter: [All] [pip] [cargo] [apt] [npm] │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│ ┌── Recipe List ───────────────────────────┐ │
│ │ ruff          pip       2 deps    ✅     │ │
│ │ mypy          pip       1 dep     ✅     │ │
│ │ cargo-audit   cargo     3 deps    ⚠️     │ │
│ │ docker        apt+repo  5 steps   ✅     │ │
│ │ terraform     snap/brew 0 deps    ❌     │ │
│ │ ...                                      │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│ ┌── Selected: ruff ────────────────────────┐ │
│ │ Methods: pip (prefer), pipx, apt         │ │
│ │ Deps: python3, pip                       │ │
│ │ on_failure: 1 handler (pep668)           │ │
│ │ verify: ruff --version                   │ │
│ │                                           │ │
│ │ ── Plan Preview ─────────────────────── │ │
│ │ System: [Debian ▾]                       │ │
│ │ ┌────────────────────────────────────┐   │ │
│ │ │ Step 1: Install pip (packages)     │   │ │
│ │ │ Step 2: Install ruff (pip)         │   │ │
│ │ │ Step 3: Verify ruff                │   │ │
│ │ └────────────────────────────────────┘   │ │
│ │ [Resolve as Fedora] [Resolve as Alpine]  │ │
│ │                                           │ │
│ │ ── on_failure Handlers ─────────────── │ │
│ │ pep668: 4 options                       │ │
│ │ [▶ Launch Scenario]                     │ │
│ └──────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

#### Features

1. **Recipe list with search and filter**
   - Searchable by tool name
   - Filterable by install method (pip, cargo, apt, npm, etc.)
   - Shows: tool ID, primary method, dep count, on_failure status

2. **Recipe detail view**
   - Full recipe structure (methods, deps, verify, post_install)
   - on_failure handlers with option summary

3. **Plan preview across systems**
   - Calls `resolve_install_plan()` with different system presets
   - Shows the resulting plan steps side-by-side
   - Highlights differences between systems

4. **Direct scenario launch**
   - If the recipe has on_failure handlers, button to launch
     the corresponding scenario (bridges to D1)

### Tab 5: Event Inspector

```
┌─────────────────────────────────────────────┐
│ [Scenarios] [Override] [Assist] [Recipe] [⚡]│
│ ─────────────────────────────────────────── │
│                                              │
│ ⚡ SSE Event Inspector                       │
│                                              │
│ Mode: [○ Passive] [● Active]                 │
│                                              │
│ ┌── Event Log ─────────────────────────────┐ │
│ │ 16:42:01.234  step_start  { step: 0,     │ │
│ │               label: "Install pip" }      │ │
│ │ 16:42:01.456  log  "Reading package..."   │ │
│ │ 16:42:03.789  log  "Unpacking pip..."     │ │
│ │ 16:42:04.012  step_done  { step: 0 }     │ │
│ │ 16:42:04.123  step_start  { step: 1,     │ │
│ │               label: "Install ruff" }     │ │
│ │ 16:42:05.456  step_failed { step: 1,     │ │
│ │               error: "PEP 668" }          │ │
│ │ 16:42:05.567  done  { ok: false,         │ │
│ │ ▸             remediation: { ... } }      │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│ ┌── Selected Event ────────────────────────┐ │
│ │ Type: done                                │ │
│ │ Time: 16:42:05.567                        │ │
│ │ Data: {                                   │ │
│ │   "type": "done",                         │ │
│ │   "ok": false,                            │ │
│ │   "remediation": {                        │ │
│ │     "failure": { ... },                   │ │
│ │     "options": [ 4 items ],               │ │
│ │     "chain": null                         │ │
│ │   }                                       │ │
│ │ }                                          │ │
│ │ [Copy JSON] [▶ Re-render Modal]           │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│ ── Inject Event ────────────────────────────│
│ Type: [dropdown]                             │
│ Data: [textarea with JSON]                   │
│ [▶ Inject]                                   │
└─────────────────────────────────────────────┘
```

#### Features

1. **Passive mode** — captures all SSE events during normal operation
   - Hooks into the existing SSE EventSource
   - Stores events with timestamps
   - Color-coded by type (start=blue, log=grey, failed=red, done=green)

2. **Active mode** — captures AND displays events in real-time
   - Auto-scrolls to latest event
   - Expandable event data (click to see full JSON)

3. **Event detail** — click to inspect
   - Full JSON data
   - "Copy JSON" for debugging
   - "Re-render Modal" — takes the event's remediation data
     and feeds it to `_showRemediationModal()` (same as D1 scenarios)

4. **Event injection** — synthetic SSE events
   - Type dropdown + JSON data textarea
   - "Inject" button fires the event through the normal handler
   - Tests that SSE handlers work correctly with edge-case data

---

## Assistant Inspector: Technical Implementation

### Catalogue loading

The catalogue is already loaded by the assistant engine
(`_loadCatalogue()` in `_assistant_engine.html`). The inspector
reads the same data:

```javascript
function _inspectorLoadCatalogue() {
    // The engine already has the catalogue loaded
    // Access it via the engine's exposed state
    if (window._assistant && window._assistant._catalogue) {
        return window._assistant._catalogue;
    }
    // Fallback: fetch directly
    return fetch('/static/data/assistant-catalogue.json')
        .then(r => r.json());
}
```

### Tree rendering

```javascript
function _renderCatalogueTree(node, depth, path) {
    const hasChildren = node.children && node.children.length > 0;
    const indent = depth * 16;
    let html = '';
    
    // Node row
    const icon = hasChildren ? (node._expanded ? '▾' : '▸') : '•';
    const selected = _inspectorSelectedPath === path ? 'debug-tree-selected' : '';
    const hasVariants = node.variants ? ` <span class="debug-badge">${node.variants.length}v</span>` : '';
    const hasResolver = node.resolver ? ' <span class="debug-badge">ƒ</span>' : '';
    
    html += `<div class="debug-tree-node ${selected}"
        style="padding-left:${indent}px"
        onclick="_inspectorSelectNode('${path}')">
        <span class="debug-tree-icon">${icon}</span>
        <span class="debug-tree-label">${esc(node.label || node.id || '?')}</span>
        ${hasVariants}${hasResolver}
    </div>`;
    
    // Children (if expanded)
    if (hasChildren && node._expanded) {
        for (const child of node.children) {
            const childPath = path ? `${path}.${child.id || child.label}` : child.id || child.label;
            html += _renderCatalogueTree(child, depth + 1, childPath);
        }
    }
    
    return html;
}
```

### Force activation

```javascript
function _inspectorForceActivate(nodePath) {
    // Find the node in the catalogue
    const node = _findNodeByPath(_inspectorCatalogue, nodePath);
    if (!node) return;
    
    // Build a fake interaction path
    const parts = nodePath.split('.');
    const breadcrumbs = parts.map((p, i) => ({
        node: _findNodeByPath(_inspectorCatalogue, parts.slice(0, i + 1).join('.')),
        depth: i,
        isTarget: i === parts.length - 1,
    })).filter(b => b.node);
    
    // Force the assistant engine to render this path
    if (window._assistant) {
        window._assistant._forceRender(breadcrumbs);
    }
}
```

This requires adding a `_forceRender()` method to the assistant engine
that bypasses DOM matching and renders a given path directly.

### Variant resolution trace

```javascript
function _inspectorTraceVariants(node) {
    if (!node.variants || node.variants.length === 0) return [];
    
    const traces = [];
    for (const variant of node.variants) {
        const trace = {
            when: variant.when,
            matched: false,
            reason: '',
            content_preview: variant.content?.substring(0, 100),
        };
        
        // Try to resolve the variant's condition
        const selector = variant.when?.selector || node.selector;
        if (selector) {
            const el = document.querySelector(selector);
            if (!el) {
                trace.reason = `Selector not found: ${selector}`;
            } else {
                const elValue = el.value || el.textContent;
                const expected = variant.when?.value || variant.when?.has;
                if (variant.when?.value) {
                    trace.matched = elValue === expected;
                    trace.reason = `value="${elValue}" ${trace.matched ? '==' : '!='} "${expected}"`;
                } else if (variant.when?.has) {
                    trace.matched = el.querySelector(expected) !== null;
                    trace.reason = `has("${expected}") = ${trace.matched}`;
                }
            }
        }
        
        traces.push(trace);
    }
    return traces;
}
```

---

## Recipe Browser: Technical Implementation

### API endpoint

```python
# routes_dev.py

@dev_bp.route("/api/dev/recipes")
def dev_recipes():
    """Return recipe summary data for the browser."""
    from src.core.services.tool_install.data.recipes import TOOL_RECIPES
    
    summaries = []
    for tool_id, recipe in TOOL_RECIPES.items():
        methods = list(recipe.get("methods", {}).keys())
        deps = recipe.get("deps", [])
        on_failure = recipe.get("on_failure", [])
        
        summaries.append({
            "tool_id": tool_id,
            "label": recipe.get("label", tool_id),
            "methods": methods,
            "prefer": recipe.get("prefer", []),
            "dep_count": len(deps),
            "has_on_failure": len(on_failure) > 0,
            "on_failure_count": len(on_failure),
            "has_verify": "verify" in recipe,
            "has_choices": "choices" in recipe,
            "has_post_install": "post_install" in recipe,
        })
    
    return jsonify({"recipes": summaries, "total": len(summaries)})


@dev_bp.route("/api/dev/recipes/<tool_id>")
def dev_recipe_detail(tool_id):
    """Return full recipe data + plan preview for a specific tool."""
    from src.core.services.tool_install.data.recipes import TOOL_RECIPES
    from src.core.services.tool_install.resolver.plan_resolution import resolve_install_plan
    from src.core.services.dev_scenarios import SYSTEM_PRESETS
    
    recipe = TOOL_RECIPES.get(tool_id)
    if not recipe:
        return jsonify({"error": f"Recipe not found: {tool_id}"}), 404
    
    # Resolve plan for each system preset
    plans = {}
    for preset_id, profile in SYSTEM_PRESETS.items():
        try:
            plan = resolve_install_plan(tool_id, profile)
            plans[preset_id] = {
                "steps": len(plan.get("steps", [])),
                "method": plan.get("method", "unknown"),
                "needs_sudo": plan.get("needs_sudo", False),
                "error": plan.get("error"),
                "already_installed": plan.get("already_installed", False),
            }
        except Exception as e:
            plans[preset_id] = {"error": str(e)}
    
    return jsonify({
        "tool_id": tool_id,
        "recipe": recipe,  # full recipe data
        "plans": plans,     # plan summaries per system
    })
```

### Plan preview rendering

```javascript
function _renderPlanComparison(plans) {
    const presets = Object.keys(plans);
    
    let html = '<div class="debug-plan-grid">';
    for (const preset of presets) {
        const plan = plans[preset];
        const status = plan.error ? '❌' :
                       plan.already_installed ? '✅ installed' :
                       `${plan.steps} steps (${plan.method})`;
        
        html += `<div class="debug-plan-cell">
            <div class="debug-plan-system">${preset}</div>
            <div class="debug-plan-status">${status}</div>
            ${plan.needs_sudo ? '<span class="debug-badge">sudo</span>' : ''}
        </div>`;
    }
    html += '</div>';
    return html;
}
```

---

## SSE Event Inspector: Technical Implementation

### Event capture hook

The existing SSE handler in `_globals.html` processes events. The
inspector hooks into this pipeline:

```javascript
// In _stage_debugger.html:

// Event capture buffer
let _debugEventLog = [];
const _DEBUG_EVENT_MAX = 200;

// Hook into SSE events
function _debugCaptureEvent(event) {
    if (!window._devModeStatus?.dev_mode) return;
    
    _debugEventLog.push({
        timestamp: Date.now(),
        type: event.type,
        data: JSON.parse(JSON.stringify(event)),  // deep clone
    });
    
    // Trim buffer
    if (_debugEventLog.length > _DEBUG_EVENT_MAX) {
        _debugEventLog = _debugEventLog.slice(-_DEBUG_EVENT_MAX);
    }
    
    // Update inspector if visible
    if (_debugDrawerOpen && _debugActiveTab === 'events') {
        _renderEventLog();
    }
}

// This function is called from the SSE handler in _globals.html:
// After parsing each SSE event, call:
//   if (window._debugCaptureEvent) window._debugCaptureEvent(event);
```

### Integration point in _globals.html

The SSE event handler needs a single hook line. In the existing
SSE onmessage handler:

```javascript
// Existing code:
source.onmessage = function(e) {
    const event = JSON.parse(e.data);
    
    // ── Dev mode capture ──────────────────────────
    if (window._debugCaptureEvent) window._debugCaptureEvent(event);
    
    // ... rest of existing handler
};
```

This is ONE line added to the existing handler. Minimal invasion.

### Event injection

```javascript
function _debugInjectEvent(type, data) {
    // Build the event
    const event = { type, ...data };
    
    // Fire through the normal SSE handler
    // Requires reference to the handler function
    if (window._sseHandler) {
        window._sseHandler({ data: JSON.stringify(event) });
    } else {
        console.warn('[debugger] No SSE handler registered for injection');
    }
}
```

This requires exposing the SSE handler as `window._sseHandler` so
the debugger can inject events. Alternative: use a CustomEvent:

```javascript
// In SSE handler setup:
window.addEventListener('dcp:sse', (e) => handleSSEEvent(e.detail));

// In debugger injection:
function _debugInjectEvent(type, data) {
    window.dispatchEvent(new CustomEvent('dcp:sse', {
        detail: { type, ...data },
    }));
}
```

The CustomEvent approach is cleaner — no global function references.

---

## Touch Point Inventory

### Files to create

| File | Purpose | Est. lines |
|------|---------|-----------|
| (none) | All D3 work is in existing files | — |

### Files to modify

| File | Change | Est. lines changed |
|------|--------|-------------------|
| `_stage_debugger.html` | Add tabs 3-5 (assistant, recipes, events) | +400 |
| `_assistant_engine.html` | Expose `_forceRender()` method | +30 |
| `_globals.html` | SSE event capture hook (1 line) + CustomEvent dispatch | +10 |
| `routes_dev.py` | `/api/dev/recipes`, `/api/dev/recipes/<id>` endpoints | +80 |
| `admin.css` | Inspector tree + event log styles | +50 |

---

## Implementation Order

```
D3.1  Assistant inspector: catalogue tree browser
      └─ Load catalogue, render collapsible tree
      └─ Node selection, detail view
      └─ No force-activation yet (just browsing)

D3.2  Assistant inspector: force activation
      └─ Depends on: D3.1
      └─ Add _forceRender() to assistant engine
      └─ Button in detail view calls _forceRender
      └─ Verify panel renders the forced node

D3.3  Assistant inspector: variant trace
      └─ Depends on: D3.1
      └─ Trace variant resolution for selected node
      └─ Show match/no-match with reasons
      └─ Input simulator for resolver variants

D3.4  Recipe browser: list + search
      └─ Add /api/dev/recipes endpoint
      └─ Render searchable/filterable list
      └─ Recipe detail view with full structure

D3.5  Recipe browser: plan preview
      └─ Depends on: D3.4
      └─ Add /api/dev/recipes/<id> endpoint
      └─ Resolve plan per system preset
      └─ Side-by-side plan comparison

D3.6  Event inspector: passive capture
      └─ SSE capture hook in _globals.html
      └─ Event log with timestamps
      └─ Expandable event data

D3.7  Event inspector: injection
      └─ Depends on: D3.6
      └─ CustomEvent dispatch mechanism
      └─ Type dropdown + JSON textarea
      └─ Re-render Modal button for done events
```

**Parallelizable:** D3.1-D3.3 (assistant), D3.4-D3.5 (recipes),
D3.6-D3.7 (events) are three independent tracks.
**Critical path within each track:** linear.

---

## Testing Strategy

### Assistant inspector tests

1. Open inspector → catalogue tree renders
2. Expand nodes → children appear
3. Select node → detail view shows content + variants
4. Force Activate → assistant panel renders the node
5. Variant trace → shows match/no-match with reasons

### Recipe browser tests

1. Open browser → 296 recipes listed
2. Search "ruff" → filtered to ruff
3. Filter "pip" → pip-method recipes only
4. Select ruff → detail view shows methods, deps, on_failure
5. Plan preview → shows steps per system preset
6. Click "Launch Scenario" → bridges to D1 scenario launcher

### Event inspector tests

1. Start an install → events captured in log
2. Click event → full JSON shown
3. Click "Re-render Modal" on a done event → modal opens
4. Inject event → handler receives it
5. Clear log → log emptied

---

## Estimated Effort

| Step | New lines | Changed lines | Files |
|------|-----------|--------------|-------|
| D3.1 Catalogue tree | 120 | 0 | 1 modified |
| D3.2 Force activation | 40 | 30 | 2 modified |
| D3.3 Variant trace | 80 | 0 | 1 modified |
| D3.4 Recipe list + search | 100 | 0 | 2 modified |
| D3.5 Plan preview | 60 | 0 | 1 modified |
| D3.6 Event capture | 80 | 10 | 2 modified |
| D3.7 Event injection | 50 | 0 | 1 modified |
| CSS | 50 | 0 | 1 modified |
| **Total** | **~580** | **~40** | **5 modified** |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Catalogue structure changes break tree renderer | Medium | Low | Use defensive property access |
| Force-activate conflicts with real assistant state | Low | Medium | Debounce, clear forced state on real interaction |
| Recipe endpoint exposes internal recipe data | Low | Low | Dev mode only, recipes are in source anyway |
| Event injection causes unexpected UI state | Medium | Low | Only in dev mode, visual indicator |
| Tab count (5) makes drawer too complex | Medium | Medium | Consider accordion or sub-nav instead of tabs |

---

## Traceability

| Requirement | Source | Implementation |
|------------|--------|---------------|
| Test content states | User request ("test different state in the content") | Force-activate + variant trace |
| Test assistant | User request ("and the assistant") | Catalogue browser + force-activate |
| Test modals | User request ("be able to test the modals") | Event inspector re-render + D1 scenarios |
| Development & QA | User request ("development & qa testing feature") | Full inspector suite |
| Fake visual states on toggle | User request ("fake the visual state of things on toggle") | Force-activate with input simulator |

---

## What D3 Does NOT Include

- Performance profiling (render timings) → future
- Automated regression tests (visual snapshot comparison) → future
- Remote debugging (connect from another machine) → out of scope
- Catalogue editor (modify catalogue from UI) → out of scope
- Recipe editor (modify recipes from UI) → out of scope

---

## Full Stage Debugger Summary (D0-D3)

| Phase | What | Lines | Files |
|-------|------|-------|-------|
| **D0** | Identity gate + dev mode toggle | ~160 | 2 new + 5 mod |
| **D1** | Scenario library + modal tester | ~758 | 2 new + 6 mod |
| **D2** | State override engine | ~355 | 1 new + 6 mod |
| **D3** | Assistant inspector + advanced | ~580 | 0 new + 5 mod |
| **Total** | Full stage debugger | **~1,853** | **5 new + 15 mod** |

### Incremental delivery value

| After phase | Developer can... |
|-------------|-----------------|
| D0 | See dev mode badge, toggle in settings |
| D0 + D1 | Open remediation modals with any failure scenario |
| D0 + D1 + D2 | Override system profiles and tool states for full-stack testing |
| D0 + D1 + D2 + D3 | Inspect assistant content, browse recipes, capture SSE events |

Each phase delivers standalone value. No phase requires
a later phase to be useful.
