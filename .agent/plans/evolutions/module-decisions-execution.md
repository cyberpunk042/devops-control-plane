# Module Decisions — Full Integration Execution Plan
> Status: READY — 2026-03-18
> Scope: Make deferrals and version plans actually WORK end-to-end
> Gap count: 27 frontend + 4 backend

---

## What exists (write side only)

- ModuleDeferral + ModuleVersionPlan models on ModuleRef ✓
- Endpoints to write deferral/plan to project.yml ✓
- Frontend forms to create deferral/plan ✓
- Confirmation modals with admonitions ✓

## What's completely missing (read side)

Nothing reads the decisions back. A deferred module looks identical to a
non-deferred one. A module with a plan shows no plan info anywhere.

---

## Step 1: Backend utilities — date parsing + status checks

New functions in `module_intel.py`:

```python
def is_deferral_expired(until_str: str) -> bool:
    """Check if a deferral date has passed.

    Handles: "2026-09-01", "Q3 2026", "2026-09"
    Returns True if the date is in the past.
    """

def is_plan_overdue(date_str: str) -> bool:
    """Check if a plan target date has passed."""

def is_plan_met(target_floor: str, effective_floor: str) -> bool:
    """Check if the effective floor meets or exceeds the plan target."""
```

Quarter parsing: "Q1" = Jan-Mar, "Q2" = Apr-Jun, "Q3" = Jul-Sep, "Q4" = Oct-Dec.
"Q3 2026" → end of Q3 = 2026-09-30.

---

## Step 2: Bridge reads and acts on decisions

In `bridge_modules()`, after computing floor/rank/verdict:

```python
# Check deferral
deferral = mod.get("deferral")
if deferral:
    expired = is_deferral_expired(deferral["until"])
    deferral["expired"] = expired

    if not expired:
        # Active deferral: suppress warnings, soften presentation
        # Don't add floor warnings for this module
        # Keep the rank data (don't lie) but mark as deferred
        mod["_deferred_active"] = True
    else:
        # Expired: add warning about expiry
        warnings.append(
            f"{name}: ⏰ deferral expired (was deferred until {deferral['until']} "
            f"because: {deferral['reason']})"
        )

# Check version plan
plan = mod.get("version_plan")
if plan:
    overdue = is_plan_overdue(plan["date"])
    met = is_plan_met(plan["target"], effective or floor)
    plan["overdue"] = overdue
    plan["met"] = met

    if met:
        # Plan complete — could auto-clear or just show success
        pass
    elif overdue:
        warnings.append(
            f"{name}: ⏰ version plan overdue — target ≥{plan['target']} "
            f"by {plan['date']}, currently at {effective or floor}"
        )

# Suppress floor warnings for actively deferred modules
if not mod.get("_deferred_active"):
    # ... existing warning logic (floor CVEs, EOL, etc.)
```

---

## Step 3: Enrichment computes flags

In `posture.py` enrichment, the deferral/plan dicts get computed flags:

```python
item["deferral"] = {
    "until": deferral.until,
    "reason": deferral.reason,
    "expired": is_deferral_expired(deferral.until),
} if deferral and deferral.until else None

item["version_plan"] = {
    "target": plan.target,
    "date": plan.date,
    "overdue": is_plan_overdue(plan.date),
    "met": is_plan_met(plan.target, effective or floor),
} if plan and plan.target else None
```

---

## Step 4: Table shows indicators

In `renderModulePillar()`:

**Floor cell** gets deferral/plan icons:
```javascript
let floorDisplay = iEmoji;
if (note) floorDisplay += ' 📝';
if (item.deferral && !item.deferral.expired) floorDisplay += ' 📅';
if (item.deferral && item.deferral.expired) floorDisplay += ' ⏰';
if (item.version_plan && !item.version_plan.met) floorDisplay += ' 📋';
if (item.version_plan && item.version_plan.met) floorDisplay += ' ✅';
```

**Row class** gets deferred styling:
```javascript
const isDeferred = item.deferral && !item.deferral.expired;
const rowClasses = `posture-row posture-module-row ${iCss} ${isDeferred ? 'posture-module-deferred' : ''}`;
```

**Sub-rows** for deferral and plan info:
```javascript
if (item.deferral) {
    const exp = item.deferral.expired;
    html += `<tr class="posture-module-decision-row">
        <td colspan="9">${exp ? '⏰' : '📅'} ${exp ? 'Deferral expired' : 'Deferred'} until ${esc(item.deferral.until)}: ${esc(item.deferral.reason)}</td>
    </tr>`;
}
if (item.version_plan && !item.version_plan.met) {
    const overdue = item.version_plan.overdue;
    html += `<tr class="posture-module-decision-row">
        <td colspan="9">${overdue ? '⏰' : '📋'} Plan: upgrade to ≥${esc(item.version_plan.target)} by ${esc(item.version_plan.date)} — ${overdue ? 'overdue' : 'in progress'}</td>
    </tr>`;
}
```

**CSS for deferred rows:**
```css
.posture-module-deferred { opacity: 0.6; }
.posture-module-deferred td { font-style: italic; }
.posture-module-decision-row td {
    font-size: 0.78rem; color: var(--text-muted);
    padding: 0.15rem 0.5rem 0.4rem 1.5rem;
    border-bottom: 1px solid var(--border-subtle);
}
```

---

## Step 5: Below-table sections for decisions

After "Needs attention" and "Status summary", add:

**📅 Deferred section** (active deferrals):
```javascript
const deferredItems = stratItems.filter(i => i.deferral && !i.deferral.expired);
if (deferredItems.length > 0) {
    html += '<div class="posture-module-status-section">';
    html += '<div class="posture-recs-title">📅 Deferred</div>';
    for (const item of deferredItems) {
        const n = (item.name || '').split(' (')[0];
        html += `<div class="posture-module-status-line info">
            📅 <strong>${esc(n)}</strong>: deferred until ${esc(item.deferral.until)}
            — ${esc(item.deferral.reason)}
        </div>`;
    }
    html += '</div>';
}
```

**⏰ Expired deferrals** (urgent):
```javascript
const expiredItems = stratItems.filter(i => i.deferral && i.deferral.expired);
if (expiredItems.length > 0) {
    html += '<div class="posture-section-warnings">';
    html += '<div class="posture-recs-title">⏰ Deferrals expired</div>';
    for (const item of expiredItems) {
        const n = (item.name || '').split(' (')[0];
        html += `<div class="posture-warn-line">
            ⏰ <strong>${esc(n)}</strong>: deferral expired — was deferred because: ${esc(item.deferral.reason)}.
            <button class="posture-btn posture-btn-update" style="font-size:0.72rem;margin-left:0.5rem"
                onclick="moduleRemediate('${esc(n)}')">Address</button>
        </div>`;
    }
    html += '</div>';
}
```

**📋 Planned upgrades**:
```javascript
const plannedItems = stratItems.filter(i => i.version_plan && !i.version_plan.met);
if (plannedItems.length > 0) {
    html += '<div class="posture-module-status-section">';
    html += '<div class="posture-recs-title">📋 Planned upgrades</div>';
    for (const item of plannedItems) {
        const n = (item.name || '').split(' (')[0];
        const status = item.version_plan.overdue ? '⏰ overdue' : '🎯 in progress';
        html += `<div class="posture-module-status-line ${item.version_plan.overdue ? 'gap' : 'info'}">
            ${status} — <strong>${esc(n)}</strong>: upgrade to ≥${esc(item.version_plan.target)}
            by ${esc(item.version_plan.date)}
        </div>`;
    }
    html += '</div>';
}
```

---

## Step 6: Peek panels show decisions

**_peekStatus()** — after existing verdict content:
```javascript
// Show deferral if exists
if (item.deferral) { ... show deferral info + expired warning ... }
// Show plan if exists
if (item.version_plan) { ... show plan status ... }
```

**_peekFloor()** — after floor health info:
```javascript
if (item.version_plan) { ... show plan target vs current ... }
```

**_peekModule()** — add "Team Decisions" section:
```javascript
if (item.deferral || item.version_plan || item.version_note) {
    // Show all recorded decisions
}
```

---

## Step 7: Remediation modal shows/manages existing decisions

**_remDecide()** — at the top, before the form options:
```javascript
// Show existing deferral if present
if (item.deferral) {
    h += _adm(item.deferral.expired ? 'warning' : 'note',
        item.deferral.expired ? '⏰ Existing deferral (expired)' : '📅 Currently deferred',
        `Until: <strong>${esc(item.deferral.until)}</strong><br>
         Reason: <em>${esc(item.deferral.reason)}</em>`);
    h += `<button class="btn btn-sm btn-danger" style="margin:0.5rem 0"
        onclick="_remConfirmClearDefer('${esc(n)}')">❌ Clear deferral</button>`;
}
```

**_remTrack()** — at the top, before the form:
```javascript
// Show existing plan if present
if (item.version_plan) {
    const status = item.version_plan.met ? '✅ Complete'
        : item.version_plan.overdue ? '⏰ Overdue' : '🎯 In progress';
    h += _adm(item.version_plan.overdue ? 'warning' : 'info',
        '📋 Existing plan: ' + status,
        `Target: Python ≥<strong>${esc(item.version_plan.target)}</strong><br>
         Date: <strong>${esc(item.version_plan.date)}</strong>`);
    h += `<button class="btn btn-sm btn-danger" style="margin:0.5rem 0"
        onclick="_remConfirmClearPlan('${esc(n)}')">❌ Clear plan</button>`;
}
```

**Pre-fill forms** with existing values when modifying.

---

## Step 8: Clear decision endpoints + handlers

**Backend** — clear deferral:
```python
@posture_bp.route("/posture/module-clear-defer", methods=["POST"])
def posture_module_clear_defer():
    # Read project.yml, find module, pop("deferral"), write back
    # m.put("posture.modules", cascade=True)
```

**Backend** — clear plan (reuse module-plan with empty target):
```python
# In module-plan endpoint: if target_floor is empty, clear the plan
if not target_floor:
    mod.pop("version_plan", None)
```

**Frontend** — clear handlers:
```javascript
window._remConfirmClearDefer = function(n) {
    _remConfirm({
        title: '❌ Clear deferral for ' + n,
        body: _adm('warning', 'This will remove the deferral',
            'The warning will re-appear immediately in the posture table.'),
        confirmLabel: 'Clear deferral',
        confirmCls: 'btn-danger',
        onConfirmExpr: "moduleClearDefer('" + n + "')",
    });
};

window.moduleClearDefer = async function(moduleName) {
    const resp = await fetch('/api/posture/module-clear-defer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ module: moduleName }),
    });
    if (resp.ok) {
        toast('❌ Deferral cleared for ' + moduleName, 'success');
        modalClose();
        postureRescan();
    }
};
```

---

## Execution Order

```
Step 1: Date utilities (is_deferral_expired, is_plan_overdue, is_plan_met)
Step 2: Bridge reads + acts on decisions (suppress warnings, add expiry warnings)
Step 3: Enrichment computes flags (expired, overdue, met)
Step 4: Table indicators + deferred row styling + decision sub-rows
Step 5: Below-table sections (deferred, expired, planned)
Step 6: Peek panels show decisions
Step 7: Remediation modal shows/manages existing decisions
Step 8: Clear endpoints + handlers
```

Each step builds on the previous. Steps 1-3 are backend. Steps 4-7 are frontend.
Step 8 is both. Step 9 is the full plan experience.

---

## Step 9: Interactive Version Plan Modal

The version plan needs to be a LIVING experience — not just two strings in YAML.

### Storage: Hybrid

**project.yml** — plan structure (shared, version-controlled):
```yaml
version_plan:
  target: "3.12"
  date: "Q3 2026"
  checklist:
    - label: "Verify all dependencies support target floor"
    - label: "Update requires-python in module config"
    - label: "Update CI test matrix"
    - label: "Run full test suite on target version"
    - label: "Remove compatibility shims if any"
```

**.state/version-plans/{module}.json** — progress (operational, local):
```json
{
  "module": "core",
  "progress": {
    "0": { "done": true, "completed_at": "2026-03-15T10:30:00Z" },
    "1": { "done": false },
    "2": { "done": false },
    "3": { "done": false },
    "4": { "done": false }
  }
}
```

### Model changes

```python
class ModuleVersionPlanStep(BaseModel):
    label: str
    description: str = ""

class ModuleVersionPlan(BaseModel):
    target: str = ""
    date: str = ""
    checklist: list[ModuleVersionPlanStep] = Field(default_factory=list)
```

### Plan modal UI

```
┌─ 📋 Version Plan: core ─────────────────────────────────────┐
│                                                               │
│  Target: Python ≥3.12         Deadline: Q3 2026              │
│  Progress: ██████░░░░ 2/5 (40%)                              │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ ☑ Verify all dependencies support target floor        │   │
│  │   Completed March 15, 2026                            │   │
│  │                                                        │   │
│  │ ☑ Update requires-python in module config             │   │
│  │   Completed March 17, 2026                            │   │
│  │                                                        │   │
│  │ ☐ Update CI test matrix                               │   │
│  │                                                        │   │
│  │ ☐ Run full test suite on target version               │   │
│  │                                                        │   │
│  │ ☐ Remove compatibility shims if any                   │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                               │
│  [➕ Add step]                                                │
│                                                               │
│  💡 Check off items as you complete them. Progress is         │
│     tracked locally. The checklist structure is shared         │
│     with your team via project.yml.                           │
│                                                               │
├───────────────────────────────────────────────────────────────┤
│                                                [Close]        │
└───────────────────────────────────────────────────────────────┘
```

### Interactions

- **Check/uncheck step** → PATCH `/api/posture/module-plan-progress`
  → updates .state/version-plans/{module}.json
  → progress bar updates immediately (no full rescan needed)

- **Add custom step** → POST `/api/posture/module-plan-step`
  → adds step to project.yml checklist
  → modal re-renders with new step

- **Remove step** → DELETE `/api/posture/module-plan-step`
  → removes from project.yml
  → modal re-renders

- **Open modal from** → 📋 indicator in table, peek panels, remediation modal
  → `moduleOpenPlan(moduleName)` function

### API endpoints

```
GET  /api/posture/module-plan-detail?module=core
  → Returns merged plan (from project.yml) + progress (from .state/)
  → { target, date, checklist: [{label, done, completed_at}], progress_pct }

PATCH /api/posture/module-plan-progress
  Body: { module: "core", step_index: 2, done: true }
  → Updates .state/version-plans/core.json
  → Returns updated progress

POST /api/posture/module-plan-step
  Body: { module: "core", label: "Custom step description" }
  → Adds step to project.yml checklist
  → Returns updated plan

DELETE /api/posture/module-plan-step
  Body: { module: "core", step_index: 3 }
  → Removes step from project.yml
  → Returns updated plan
```

### CSS

```css
.plan-progress-bar { height: 6px; background: var(--bg-inset);
                     border-radius: 3px; overflow: hidden; margin: 0.5rem 0; }
.plan-progress-fill { height: 100%; background: var(--accent);
                      transition: width 0.3s ease; border-radius: 3px; }

.plan-step { display: flex; align-items: start; gap: 0.5rem;
             padding: 0.5rem 0; border-bottom: 1px solid var(--border-subtle); }
.plan-step:last-child { border-bottom: none; }
.plan-step-check { accent-color: var(--accent); width: 16px; height: 16px;
                   margin-top: 2px; cursor: pointer; }
.plan-step-label { font-size: 0.85rem; flex: 1; }
.plan-step.done .plan-step-label { text-decoration: line-through;
                                    color: var(--text-muted); }
.plan-step-date { font-size: 0.72rem; color: var(--text-muted); }
.plan-step-remove { font-size: 0.7rem; color: var(--text-muted);
                    cursor: pointer; opacity: 0; transition: opacity 0.15s; }
.plan-step:hover .plan-step-remove { opacity: 1; }
```
