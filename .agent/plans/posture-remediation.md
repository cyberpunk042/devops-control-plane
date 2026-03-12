# Posture Remediation — From Awareness to Action

> **Status**: Implementation — R1 ✅ R2 ✅ R3 ✅ (CSS ✅, JS ✅, ops_modal bridge ✅)
> **Created**: 2026-03-12
> **Parent**: `.agent/plans/system-health-posture.md` (Phase 1–6 complete)
> **Scope**: Complete evolution — passive posture → actionable remediation across all 4 pillars

---

## 0. User Direction (verbatim, in series)

> "you are not ready... there is a whole plan concept and modal execution window"

The simple `update_tool()` API is insufficient. Posture remediation must go through the
**plan-based execution model**: plan resolution → step modal → SSE streaming → remediation
on failure. The same execution window the user already knows from tool installs.

> "now that you understand we can discuss the solution"

After tracing the full flow: `installWithPlan()` → `resolve-choices` → `install-plan` →
`showStepModal()` → `_executeStepModalPlan()` → SSE `install-plan/execute` → remediation
modal on failure → resume/cancel/archive.

> User chose **Option A**: New backend "update plan" resolver that produces plans in the
> same format as install plans, reusing `showStepModal()` and the SSE execution window.

> On batch updates: **"we offer both"** — individual update buttons per tool AND an
> "Update All Outdated" batch operation.

> On modal stacking: **"it should stack"** — step modal stacks on top of posture modal.
> Posture stays visible behind. After completion, posture refreshes.

> On scope: **"I want to scope it all. this is a complete evolution."** — All 4 pillars,
> all action types, not just toolchain updates. Don't minimize.

---

## 1. What Exists Today

### System Posture (Phases 1–6 complete)

The posture system **detects and reports** across 4 pillars:

| Pillar | Scanner | What It Detects |
|--------|---------|-----------------|
| **Platform** | `platform.py` | OS distro + version, kernel, arch, glibc, WSL status |
| **Toolchain** | `toolchain.py` | Installed tool versions ranked against `tool_lifecycle.json` |
| **Project** | `project.py` (bridge) | Git, Docker, CI, packages, env, quality, structure probes |
| **Runtime** | `runtime.py` (bridge) | Circuit breakers, retry queue health |

Each produces `PostureItem` objects with `name`, `value`, `rank`, `detail`.
These are aggregated into `PillarResult` → `SystemPosture` and displayed
in the posture modal (nav badge click → `modalOpen({size: 'posture'})`).

**The gap**: The modal shows what's wrong but offers **zero actions**. It's a
read-only dashboard. The user sees "Docker is 3 releases behind" but can't
do anything about it from there.

### Tool Install System (fully built)

The plan-based install system is the execution engine:

```
Plan Resolution → Choice Modal → Step Modal → SSE Execute → Remediation → Resume
```

Key components:

| Component | What It Does |
|-----------|-------------|
| `resolve_install_plan()` | Walks deps, picks methods, builds ordered step list |
| `resolve_choices()` | Pass 1 — surfaces user choices before plan resolution |
| `showStepModal(plan)` | Plan review UI: step list, risk banners, sudo input, confirmation gates |
| `_executeStepModalPlan()` | Drives execution: calls SSE endpoint, updates step rows live |
| `streamSSE()` | Unified SSE reader with typed callbacks |
| `/audit/install-plan/execute` | Backend SSE: runs steps, streams progress, handles failures |
| `_showRemediationModal()` | On failure: shows remediation options with availability/risk/chains |
| `update_tool()` | Simple synchronous update (no plan, no streaming) |
| `get_update_map(recipe)` | Resolves update commands from recipe data |
| `TOOL_RECIPES` | 300+ declarative recipes with install/update/verify commands |

**The bridge needed**: A way to produce **update plans** in the same format as
install plans, so the entire execution window infrastructure is reused.

---

## 2. Architecture Decision Record

### ADR-1: Update Plan Resolver (Option A)

**Decision**: Create a new `resolve_update_plan()` function that produces plans
in the same `{tool, label, steps[], needs_sudo, risk_summary, confirmation_gate}`
format as install plans.

**Rationale**: 
- `update_tool()` is synchronous — no step modal, no streaming, no remediation tree
- `resolve_install_plan()` returns `already_installed` for tools that ARE installed
- The update plan is a thin wrapper (~50–or-so lines) around `get_update_map()`
- All step modal UI, SSE execution, remediation, resume/cancel — inherited for free

**What the update plan contains**:
```python
{
    "tool": "docker# ",
    "label": "Docker",
    "action": "update",              # distingu from install
    "from_version": "24.0.7",       # current installed
    "current_version": "27.5.1",    # latest known (from#  lifecycle data or recipe)
    "already_installed": False,      # Never true for updates
    "needs_sudo": True,
    "method": "apt",
    "steps": [
        {
            "type": "tool",
            "label": "Update Docker",
            "tool_id": "docker",
            "command": ["apt", "upgrade", "-y", "docker-ce"],
            "needs_sudo": True,
            "method": "apt",
            "risk": "medium",
        },
        {
            "type": "verify",
            "label": "Verify Docker",
            "command": ["docker", "--version"],
            "needs_sudo": False,
        }
    ],
    "risk_summary": {"has_high": False, "has_medium": True, ...},
    "confirmation_gate": {"type": "single", "required": True, ...},
}
```

### ADR-2: Execution Endpoint — Extend, Don't Duplicate

**Decision**: Add `mode: "update"` parameter to the existing
`POST /audit/install-plan/execute` endpoint.

**Rationale**:
- The execute endpoint currently re-resolves the plan via `resolve_install_plan()`
- With `mode: "update"`, it calls `resolve_update_plan()` instead
- The SSE generator, step execution, remediation analysis, state persistence —
  all identical, no duplication needed
- ~3 lines of change in the execute endpoint

### ADR-3: Data Enrichment at the API Boundary

**Decision**: Enrich `PostureItem` with action metadata at the posture API route
level, not in the scanner.

**Rationale**:
- Scanners stay pure: detection + ranking only
- The API route cross-references each toolchain item against `TOOL_RECIPES` and
  `get_update_map()` to determine what actions are available
- This keeps the import boundary clean (posture doesn't import tool_install at scan time)

**Enrichment shape** (added to the `to_dict()` output per item):
```python
"actions": [
    {
        "type": "update",            # or "install", "link", "guide", "reset"
        "available": True,
        "tool_id": "docker",         # for update/install actions
        "label": "Update Docker",
        "needs_sudo": True,
    }
]
```

### ADR-4: Modal Stacking

**Decision**: Step modal stacks on top of posture modal. Both stay visible.
After update completion, posture auto-rescans.

**Implementation**:
- Posture modal uses `modalOpen()` (standard modal system, z-index per stack depth)
- Step modal uses its own overlay at `z-index: 10000`
- Step modal is already designed to stack (used for remediation stacking on install failures)
- On `onComplete` callback from step modal → call `postureRescan()`

### ADR-5: Batch Updates

**Decision**: Offer both individual "⬆️ Update" per tool AND a collective
"⬆️ Update All Outdated" button.

**Implementation**:
- Individual: one button per outdated toolchain row → launches single update plan
- Batch: button in toolchain pillar header (or posture hero area) → sequential
  execution of update plans for all outdated tools
- Batch uses the same step modal but with ALL steps from ALL tools combined,
  or sequential plan execution with progress tracking

---

## 3. Per-Pillar Action Map

### 🔧 Toolchain — Full Plan-Based Remediation

| Item State | Action | Button | Trigger |
|-----------|--------|--------|---------|
| `AGING` | ⬆️ Update | Optional | `updateWithPlan(toolId, toolLabel)` |
| `OUTDATED` | ⬆️ Update | **Yes** | `updateWithPlan(toolId, toolLabel)` |
| `DEPRECATED` | ⬆️ Update | **Yes, prominent** | `updateWithPlan(toolId, toolLabel)` |
| `DANGEROUS` | ⬆️ Update | **Yes, urgent** | `updateWithPlan(toolId, toolLabel)` |
| No update cmd | 📋 Manual | Copy command | Show manual instruction |
| No recipe | — | — | No    action available |
| **Batch** | ⬆️ Update All | **Header   button** | Sequential update plans |

**Frontend flow for    individual**:
```
User clicks "⬆️ Update" on a posture toolchain row
  → update    WithPlan('docker', 'Docker')
  → POST /audit/update-plan {tool: 'docker'}
  → Backend resolves update plan via resolve_update_plan()
  → Returns plan dict with steps, risk, gates
  → showStepModal(plan) opens on top of posture modal
  → User reviews steps, enters sudo if needed, confirms
  → POST /audit/install-plan/execute {tool: 'docker', mode: 'update'}
  → SSE streaming: step_start, log, step_done, done
  → On success: step modal closes → postureRescan() triggers
  → Posture modal refreshes with new data
```

**Frontend flow for batch**:
```
User clicks "⬆️ Update All Outdated" in toolchain pillar header
  → Collect all toolchain items with rank >= OUTDATED and has_update
  → POST /audit/update-plan/batch {tools: ['docker', 'kubectl', 'helm']}
  → Backend resolves individual plans, merges into a combined plan
  → showStepModal(combinedPlan) — multi-tool step list
  → Same SSE execution flow
  → On success: posture rescan
```

### 💻 Platform — Informational + Links

| Item | State | Action | Implementation |
|------|-------|--------|----------------|
| OS version | OUTDATED/DEPRECATED | 📖 Upgrade Guide | Inline text with OS-specific instructions |
| OS version | DANGEROUS (EOL) | ⚠️ Urgent Warning | Prominent warning + upgrade guide link |
| Kernel | Old | 📖 Info | "Consider updating kernel" text |
| glibc | Old | 📖 Info | Explains implications for tool compatibility |
| WSL | Version info | — | Informational only |
| Architecture | — | — | Informational only |

**Implementation**: The posture modal renders a "guide" area for platform items
with ranks >= OUTDATED. No automation — OS upgrades are manual. But the guide
content should be **distro-specific** (Ubuntu upgrade differs from Debian differs
from RHEL).

### 📦 Project — Navigation Links to Audit

| Probe | State | Action | Implementation |
|-------|-------|--------|----------------|
| `project:git` | Low score | 🔍 View in Audit | Navigate to audit tab, git card |
| `project:docker` | Low score | 🔍 View in Audit | Navigate to audit tab, docker card |
| `project:ci` | Low score | 🔍 View in Audit | Navigate to audit tab, ci card |
| `project:packages` | Low score | 🔍 View in Audit | Navigate to audit tab, packages card |
| `project:env` | Low score | 🔍 View in Audit | Navigate to audit tab, env card |
| `project:quality` | Low score | 🔍 View in Audit | Navigate to audit tab, quality card |
| `project:structure` | Low score | 🔍 View in Audit | Navigate to audit tab, structure card |

**Implementation**: Each project item with poor rank gets a "View in Audit →" link
that closes the posture modal and navigates to the audit tab, optionally scrolling
to the specific card. Uses existing tab navigation or URL routing.

### ⚡ Runtime — Quick Actions

| Component | State | Action | Implementation |
|-----------|-------|--------|----------------|
| Circuit breaker (open) | DEGRADED | 🔄 Reset | Call circuit breaker reset API |
| Circuit breaker (half-open) | AGING | — | Info only, self-healing |
| Retry queue (exhausted items) | DEGRADED | 🗑️ Clear | Clear exhausted items |
| Retry queue (pending) | CURRENT | — | Info only |

**Implementation**: Small inline action buttons that call existing health management
APIs. These are fast synchronous operations — no plan modal needed.

---

## 4. Backend Changes

### 4.1 New: Update Plan Resolver

**File**: `src/core/services/tool_install/resolver/update_resolution.py` (new)

```python
def resolve_update_plan(tool: str, system_profile: dict) -> dict:
    """Produce an ordered update plan for an installed tool.
    
    Similar to resolve_install_plan but for updates:
    - Skips "already installed" check
    - Uses get_update_map(recipe) instead of install map
    - Includes from_version in the plan
    - Adds verify step
    """
```

**What it does**:
1. Look up recipe in `TOOL_RECIPES`
2. Verify tool IS installed (`shutil.which(cli)`)
3. Get current version via `get_tool_version(tool)`
4. Get update command via `get_update_map(recipe)`
5. Resolve method for this system (apt/brew/pip/npm/cargo/etc.)
6. Build step(s): update command + optional verify
7. Compute risk, sudo needs, confirmation gates
8. Return plan dict in same format as install plans

### 4.2 New: Batch Update Plan

**Same file or adjacent**:

```python
def resolve_batch_update_plan(tools: list[str], system_profile: dict) -> dict:
    """Produce a combined update plan for multiple tools."""
```

Resolves individual plans, merges steps into a single ordered list.
Tools without update commands are skipped with a note.

### 4.3 New: API Endpoints

**File**: `src/ui/web/routes/audit/tool_install.py` (extend)

```
POST /audit/update-plan          → resolve_update_plan()
POST /audit/update-plan/batch    → resolve_batch_update_plan()
```

### 4.4 Modify: Execute Endpoint

**File**: `src/ui/web/routes/audit/tool_execution.py` (modify)

The execute endpoint gains a `mode` parameter:
```python
mode = body.get("mode", "install")
if mode == "update":
    plan = resolve_update_plan(tool, system_profile)
else:
    plan = resolve_install_plan(tool, system_profile)
```

### 4.5 Modify: Posture API Route

**File**: `src/ui/web/routes/posture.py` (modify)

The `/api/posture` endpoint enriches toolchain items with action metadata:
```python
# After scan_posture():
posture_dict = posture.to_dict()
_enrich_toolchain_actions(posture_dict)
return jsonify(posture_dict)
```

The enrichment function cross-references each toolchain item against:
- `TOOL_RECIPES`: does a recipe exist?
- `get_update_map(recipe)`: is there an update command?
- `recipe.needs_sudo`: does it need elevated privileges?

Adds `actions` array to each toolchain item's dict.

### 4.6 Modify: Posture API Route — Project Links

The `/api/posture` endpoint enriches project items with navigation metadata:
```python
# For project items:
item["actions"] = [{
    "type": "link",
    "target": "audit",
    "card_id": item["name"].split(":")[-1],  # "git", "docker", etc.
    "label": "View in Audit",
}]
```

---

## 5. Frontend Changes

### 5.1 Posture Modal — Action Buttons

**File**: `src/ui/web/templates/scripts/globals/_system_posture.html` (modify)

Each posture row gains a 5th column: **Actions**.

For toolchain items with `actions`:
```html
<td class="posture-cell-action">
    <button class="posture-btn update" onclick="postureUpdateTool('docker', 'Docker')">
        ⬆️ Update
    </button>
</td>
```

For project items with `actions`:
```html
<td class="posture-cell-action">
    <button class="posture-btn link" onclick="postureViewAudit('git')">
        🔍 View in Audit →
    </button>
</td>
```

For platform items with guides:
```html
<td class="posture-cell-action">
    <button class="posture-btn guide" onclick="postureShowGuide('ubuntu', '20.04')">
        📖 Guide
    </button>
</td>
```

For runtime items with resets:
```html
<td class="posture-cell-action">
    <button class="posture-btn reset" onclick="postureResetBreaker('breakerName')">
        🔄 Reset
    </button>
</td>
```

### 5.2 Batch Update Button

In the toolchain pillar header (next to the label/chevron):
```html
<button class="posture-btn batch-update" onclick="postureUpdateAllOutdated()">
    ⬆️ Update All Outdated (3)
</button>
```

Count badge shows how many tools are updatable.

### 5.3 New Functions in Posture Script

```javascript
// Individual tool update — plan-based
async function postureUpdateTool(toolId, toolLabel) {
    // 1. Fetch update plan
    // 2. showStepModal(plan, { onComplete: postureRescan })
}

// Batch update — all outdated tools
async function postureUpdateAllOutdated() {
    // 1. Fetch batch update plan
    // 2. showStepModal(combinedPlan, { onComplete: postureRescan })
}

// Navigate to audit tab + specific card
function postureViewAudit(cardId) {
    // 1. Close posture modal
    // 2. Switch to audit tab
    // 3. Scroll to card
}

// Show platform upgrade guide
function postureShowGuide(distro, version) {
    // 1. Show inline guide text in posture modal
    //    Or open a sub-modal with the guide content
}

// Reset a circuit breaker
async function postureResetBreaker(breakerName) {
    // 1. POST to health reset API
    // 2. Inline update the row
}
```

### 5.4 CSS Additions

**File**: `src/ui/web/static/css/admin.css` (extend posture section)

- `.posture-cell-action` — action column styling
- `.posture-btn` — base action button (compact, inline)
- `.posture-btn.update` — accent-colored for updates
- `.posture-btn.batch-update` — prominent batch button in pillar header
- `.posture-btn.link` — subtle link-style button
- `.posture-btn.guide` — info-style button
- `.posture-btn.reset` — warning-style button for resets

---

## 6. Data Flow Diagrams

### Individual Tool Update

```
┌─────────────────────┐
│   Posture Modal      │
│                      │
│  Docker  24.0  🟡    │
│  ┌──────────────┐    │
│  │ ⬆️ Update    │────┼───► POST /audit/update-plan {tool: "docker"}
│  └──────────────┘    │         │
│                      │         ▼
│                      │    resolve_update_plan("docker", sys_profile)
│                      │         │
│                      │         ▼
│                      │    Plan: {steps: [{update docker}], needs_sudo, risk}
│                      │         │
│                      │         ▼
│  ┌──────────────────────────────────────┐
│  │  Step Modal (z:10000, stacked)       │
│  │                                      │
│  │  📦 Update Docker                    │
│  │  ┌─────────────────────────────────┐ │
│  │  │ ⏳ Update Docker       sudo     │ │
│  │  │ ⏳ Verify Docker                │ │
│  │  └─────────────────────────────────┘ │
│  │  🔑 Sudo: [___________]             │
│  │  [Cancel]              [⬆️ Update]  │
│  └──────────────┬───────────────────────┘
│                 │
│                 ▼ (user clicks Update)
│            POST /audit/install-plan/execute
│            {tool: "docker", mode: "update", sudo_password: "..."}
│                 │
│                 ▼  SSE stream
│            step_start → log → log → step_done → done {ok: true}
│                 │
│                 ▼
│            Step modal closes
│                 │
│                 ▼
│            postureRescan() → POST /posture/rescan
│                 │
│                 ▼
│  Posture modal refreshes:
│  Docker  27.5  🟢  ✅ Up to date
└─────────────────────┘
```

### Batch Update

```
Posture Modal
  │
  │ "⬆️ Update All Outdated (3)"
  │
  ▼
POST /audit/update-plan/batch {tools: ["docker", "kubectl", "helm"]}
  │
  ▼
Combined plan with merged steps:
{
    steps: [
      {label: "Update Docker", ...},
      {label: "Verify Docker", ...},
      {label: "Update kubectl", ...},
      {label: "Verify kubectl", ...},
      {label: "Update Helm", ...},
      {label: "Verify Helm", ...},
    ]
}
  │
  ▼
showStepModal(combinedPlan)
  │
  ▼
Sequential SSE execution of all steps
  │
  ▼
On complete → postureRescan()
```

### Project → Audit Navigation

```
Posture Modal
  │
  │ project:git scored 40%  [🔍 View in Audit →]
  │
  ▼ (user clicks)
modalClose()  // close posture modal
  │
  ▼
Switch to Audit tab
  │
  ▼
Scroll to #audit-card-git (or equivalent card ID)
```

---

## 7. Implementation Phases

### Phase R1: Update Plan Backend
- [ ] Create `resolve_update_plan()` in new file
- [ ] Create `resolve_batch_update_plan()` 
- [ ] Add `POST /audit/update-plan` endpoint
- [ ] Add `POST /audit/update-plan/batch` endpoint
- [ ] Add `mode` parameter to `/audit/install-plan/execute`
- [ ] Register exports in `__init__.py`

### Phase R2: Posture API Enrichment
- [ ] Add action enrichment to `/api/posture` route
- [ ] Toolchain items: cross-reference TOOL_RECIPES + get_update_map
- [ ] Project items: add audit navigation metadata
- [ ] Platform items: add guide availability flags
- [ ] Runtime items: add reset action flags

### Phase R3: Frontend — Toolchain Actions
- [ ] Add action column to posture table
- [ ] Implement `postureUpdateTool()` — fetch plan → showStepModal
- [ ] Implement `postureUpdateAllOutdated()` — batch flow
- [ ] Wire `onComplete` → `postureRescan()`
- [ ] CSS for action buttons

### Phase R4: Frontend — Project Actions  
- [ ] Implement `postureViewAudit(cardId)` — modal close + tab switch + scroll
- [ ] Add "View in Audit →" buttons to project items

### Phase R5: Frontend — Platform Guides
- [ ] Create guide content for major distros (Ubuntu, Debian, RHEL/CentOS, macOS)
- [ ] Implement `postureShowGuide()` — inline expand or sub-modal
- [ ] Content: specific upgrade commands, links to official docs

### Phase R6: Frontend — Runtime Actions
- [ ] Implement `postureResetBreaker()` — call health reset API
- [ ] Implement retry queue clear if applicable
- [ ] Inline row update on success

### Phase R7: Polish + Edge Cases
- [ ] Handle tools with no update command (show "No automated update" message)
- [ ] Handle tools with no recipe (no action available)
- [ ] Handle batch update partial failures (some succeed, some fail)
- [ ] Step modal close-on-backdrop should NOT close when executing
- [ ] Error states in posture modal (enrichment fails, recipe lookup fails)
- [ ] Cache invalidation after update (bust posture cache + tool status cache)

---

## 8. Files to Create / Modify

### New Files
```
src/core/services/tool_install/resolver/update_resolution.py    ← update plan resolver
```

### Modified Files
```
src/core/services/tool_install/__init__.py               ← export resolve_update_plan
src/core/services/tool_install/resolver/__init__.py      ← export resolve_update_plan
src/ui/web/routes/audit/tool_install.py                  ← new endpoints
src/ui/web/routes/audit/tool_execution.py                ← mode parameter
src/ui/web/routes/posture.py                             ← action enrichment
src/ui/web/templates/scripts/globals/_system_posture.html ← action buttons + functions
src/ui/web/static/css/admin.css                          ← action button styles
```

---

## 9. Open Items

- **Guide content source**: Should platform upgrade guides be hardcoded, or loaded
  from a data file (like the lifecycle JSONs)? Hardcoded is simpler for v1.
  
- **"Update All" step modal header**: Should it say "Update 3 Tools" or list them
  individually? Individual listing is clearer.

- **Posture badge color after update**: Should the badge immediately reflect the
  new state after a successful update, or wait for the full rescan? Auto-rescan
  handles this — badge updates when rescan completes.

- **Runtime reset APIs**: Need to identify the exact API endpoints for circuit
  breaker reset and retry queue management. Verify they exist.

- **update_tool vs update plan**: The existing `update_tool()` function in
  `tool_management.py` is still useful for CLI/non-UI callers. The plan-based
  update is for UI. Both coexist.
