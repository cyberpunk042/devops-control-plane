# CDP Test I/O — Complete Implementation Plan (Corrected)

> This plan replaces all previous I/O plans. The I/O model was corrected
> after the original implementation used a wrong understanding of INPUT
> and OUTPUT. This plan includes the correct model, damage assessment
> of what was built wrong, and the complete implementation to the end.

---

## Part 1: The I/O Model

Two concepts. Determined by step type. No choice, no toggle.

### 📥 INPUT (suite parameter)

- **Applies to**: value-consuming steps — `type`, `navigate`, `select`, `keypress`, `inject_js`
- **What it means**: The step's value becomes a **suite parameter**. Before executing the suite, the user is presented with this variable and can set its value. The value recorded during recording becomes the default.
- **At runtime**: `${VAR_NAME}` in the step's `value` field gets replaced with whatever the user (or the plan) provided.
- **Data fields**:
  - `value` → `${VAR_NAME}` (the variable reference)
  - `_original_value` → the recorded default (e.g. `admin@test.com`)
- **A type step can ONLY be INPUT.** It consumes data — it pushes a value into the page. It produces nothing to export.
- **Example**: During recording, user types `admin@test.com` into a login field. They mark it as INPUT with variable name `LOGIN_EMAIL`. Before running the suite, user sees: "LOGIN_EMAIL: [admin@test.com]" and can change it to `test@example.com`.

### 📤 OUTPUT (export)

- **Applies to**: data-producing steps — `capture_text`, `capture_html`, `capture_value`, `capture_attribute`, `capture_screenshot`, `capture_url`, `capture_console`
- **What it means**: The value captured by this step at runtime gets **exported to the plan namespace**. Available after execution for downstream suites.
- **Data fields**:
  - `export_as` → the export name (e.g. `AUTH_TOKEN`)
- **A capture step can ONLY be OUTPUT.** It reads a value from the live page at runtime. You cannot make a captured value into a user-configurable parameter because the value doesn't exist until the capture runs.
- **Example**: During recording, a capture_text step reads a CSRF token from the page. User marks it as OUTPUT with export name `CSRF_TOKEN`. After the suite runs, `CSRF_TOKEN` is available in the plan namespace for the next suite.

### Rules

1. **No choice needed.** The step's action type determines INPUT vs OUTPUT completely.
2. **Mutually exclusive by nature.** Type = INPUT. Capture = OUTPUT. A step cannot be both.
3. **"Store as variable" does not exist.** This was a bad label in the old step editor hack. It is not a valid concept.
4. **No toggles, no radio buttons for INPUT/OUTPUT selection.** When you open I/O config on a type step, you see INPUT. When you open it on a capture step, you see OUTPUT. Period.

---

## Part 2: Damage Assessment

Code was written with a wrong model that showed both INPUT and OUTPUT on the same step,
presented "Store as variable" as a third concept, and added mode toggles.

### ✅ CLEAN — Keep as-is

| File | Change | Lines | Why clean |
|------|--------|-------|-----------|
| `src/core/services/cdp_test/session.py` | `modify_step(step_id, updates)` | 91-107 | Generic utility. Finds step by ID, applies dict update. No I/O semantics. |
| `src/ui/web/routes/cdp_test/recording.py` | `POST /record/modify-step` endpoint | 758-829 | Generic endpoint with field whitelist. Infrastructure only. |
| `src/ui/web/templates/scripts/integrations/_cdp_test.html` | 🔗 badge in step toolbar (`canIO` condition) | ~405-425 | Button placement is correct. `canIO` shows badge for value actions AND capture actions — correct. |
| `src/ui/web/templates/scripts/integrations/_cdp_test.html` | Event delegation `else if (action === 'io')` | ~548 | Dispatches to `_cdpTestOpenIOConfig`. Correct. |

### ⚠️ MINOR FIX

| File | Change | Issue | Fix |
|------|--------|-------|-----|
| `recording.py` | `POST /modify-step` docstring | Shows `value` + `export_as` in same payload as if they go together | Separate into INPUT example and OUTPUT example |
| `recording.py` | `io_bind` handler in `/record/event` (~510-558) | Sets `variable_name` AND `export_as` if both provided. No mutual exclusivity. | If `variable_name` → set input fields, clear `export_as`. If `export_as` → set export, clear input fields. |

### 🔴 REWRITE NEEDED

| File | Function/Section | What's wrong |
|------|-----------------|--------------|
| `_cdp_test.html` | `_cdpTestOpenIOConfig()` (~1190-1290) | Shows both input AND output sections simultaneously. Has "Store as variable" field. Wrong conditions (`isCaptureAction \|\| isValueAction` for output). |
| `_cdp_test.html` | `_cdpTestSaveIO()` (~1292-1370) | Reads from all fields. Can send input + output in same request. |
| `cdp_recorder.js` | I/O badge in `_showAssertBadge` (~470-535) | May be architecturally wrong — badge appears after clicks, but INPUT applies to type steps (input events). |
| `cdp_recorder.js` | `_openIOModal()` (~1245-1430) | Has Input/Output mode toggle radio. Wrong labels. Wrong model. |
| `cdp_recorder.js` | `_saveIO()` (~1445-1490) | Sends wrong payload. Can combine input + output. |
| `cdp_recorder.js` | `_closeIOModal()` (~1435-1442) | Depends on `__dcp_io_overlay` ID from wrong modal — harmless but needs to match rewrite. |

### 🔴 NOT YET BUILT (from original plan)

| Feature | File | Description |
|---------|------|-------------|
| 📋 Capture Config I/O | `_cdp_test.html` | Add OUTPUT field to capture config overlay (the "reverse" — set export_as at creation time) |
| Step editor I/O section | `_cdp_test.html` | Replace dual "Store as variable" + "Export as" fields with correct single field per step type |
| Step editor save fix | `_cdp_test.html` | `_cdpTestApplyStepEdit()` — enforce correct model |
| Step row badges | `_cdp_test.html` | `_cdpTestValStepRow()` — show 📥/📤 indicators |
| I/O summary panel fix | `_cdp_test.html` | `_cdpTestBuildIOPanel()` — make interactive, correct labels |
| SSE handler for step_modified | `_cdp_test.html` | Listen for `cdp_test:step_modified` SSE events to update live step list |

---

## Part 3: Implementation — Layer by Layer

### Layer 1: Backend Foundation

**Status: ✅ DONE (with minor fixes needed)**

#### 1a. `session.py` — `modify_step()` ✅ DONE
Generic method. No changes needed.

#### 1b. `recording.py` — `POST /modify-step` ✅ DONE (docstring fix)
- Fix docstring to show separate INPUT and OUTPUT examples
- No code logic changes needed

#### 1c. `recording.py` — `io_bind` handler ⚠️ FIX
- Enforce mutual exclusivity in the handler
- If `io_config.variable_name`: set `value = ${VAR}`, set `_original_value`, clear `export_as`
- If `io_config.export_as`: set `export_as`, clear `variable_name` if present
- Never set both

#### 1d. `recording.py` — `POST /add-step` enhancement
- The existing `add-step` endpoint accepts arbitrary step_data fields
- `export_as` can be included in the request body — no backend change needed
- The frontend (📋 overlay) just needs to send it

#### 1e. SSE event `cdp_test:step_modified`
- Already broadcast by `POST /modify-step` endpoint ✅
- Already broadcast by `io_bind` handler ✅
- Frontend SSE listener needed (Layer 2)

---

### Layer 2: Admin Panel Recording View (`_cdp_test.html`)

#### 2a. 🔗 Badge in Step Toolbar ✅ DONE
- Badge appears for value actions AND capture actions
- Event delegation dispatches to `_cdpTestOpenIOConfig`
- No changes needed

#### 2b. I/O Config Overlay — REWRITE `_cdpTestOpenIOConfig()` 🔴

**Current code (WRONG):** Shows both input binding section AND output export section. Has "Store as variable" concept. Has `isValueAction || isCaptureAction` condition allowing both.

**Correct implementation:**

```
function _cdpTestOpenIOConfig(step) {
    const isValueAction = ['navigate','type','select','keypress','inject_js'].includes(step.action);
    const isCaptureAction = step.action.startsWith('capture_');

    if (isValueAction) {
        // Show INPUT overlay
        // - Title: "📥 Input — Suite Parameter"
        // - Subtitle: "This value becomes configurable when running the suite"
        // - Field: Variable name (monospace, placeholder: "LOGIN_EMAIL")
        // - Info: Current value shown as "Default: admin@test.com"
        // - Pre-populate if already bound (detect ${VAR} in value)
        // - Purple accent (#8b5cf6) for visual identity
    } else if (isCaptureAction) {
        // Show OUTPUT overlay
        // - Title: "📤 Output — Export"
        // - Subtitle: "The captured value will be exported to the plan namespace"
        // - Field: Export name (monospace, placeholder: "AUTH_TOKEN")
        // - Pre-populate if export_as already set
        // - Green accent (#22c55e) for visual identity
    }
}
```

**Key details:**
- Purple border/accent for INPUT overlays
- Green border/accent for OUTPUT overlays
- Same overlay shell (position:fixed, backdrop-filter, same sizing)
- Same dismiss behavior (click outside, cancel button)
- Same overlay ID (`cdp-io-config-overlay`) — remove previous before creating

#### 2c. I/O Save — REWRITE `_cdpTestSaveIO()` 🔴

**Correct implementation:**

```
async function _cdpTestSaveIO() {
    const stepData = _cdpStepDataMap.get(_cdpCurrentStepId);
    const isValueAction = ['navigate','type','select','keypress','inject_js'].includes(stepData.action);
    const updates = {};

    if (isValueAction) {
        // INPUT: read variable name, wrap value in ${VAR}
        const varName = document.getElementById('cdp-io-var-name')?.value?.trim();
        if (!varName) return;  // validation
        const currentVal = stepData.value || '';
        if (currentVal && !currentVal.match(/^\$\{\w+\}$/)) {
            updates._original_value = currentVal;
        }
        updates.value = '${' + varName + '}';
        updates.export_as = '';  // clear any stale export
    } else {
        // OUTPUT: read export name
        const exportName = document.getElementById('cdp-io-export-name')?.value?.trim();
        if (!exportName) return;  // validation
        updates.export_as = exportName;
    }

    await api('/cdp-test/record/modify-step', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ step_id: stepData.id, updates }),
    });

    Object.assign(stepData, updates);
    toast('I/O configured for step ' + (stepData.sequence + 1), 'success');
    document.getElementById('cdp-io-config-overlay')?.remove();
}
```

#### 2d. 📋 Capture Config Enhancement (the "reverse") — NEW

The existing `_cdpTestOpenCaptureConfig()` lets users add capture steps. Currently only picks capture type. Need to add OUTPUT field.

**What to add before the "Add Capture" button:**

```html
<div style="margin-top:0.8rem;padding:10px;border:1px solid #22c55e33;border-radius:8px;background:#22c55e0a">
    <div style="font-weight:600;font-size:0.78rem;color:#22c55e;margin-bottom:6px">📤 Export (optional)</div>
    <input id="cdp-capture-export-name" type="text" placeholder="AUTH_TOKEN (optional)"
        style="width:100%;font-size:0.78rem;padding:6px 10px;background:var(--bg-secondary);
        border:1px solid var(--border-subtle);border-radius:6px;color:var(--text-primary);font-family:monospace">
    <div style="font-size:0.62rem;color:var(--text-muted);margin-top:4px">
        Exports captured value to plan namespace for downstream suites
    </div>
</div>
```

**What to change in `_cdpTestSaveCapture()`:**

Add `export_as` to the step data sent to `/add-step`:
```javascript
const exportName = document.getElementById('cdp-capture-export-name')?.value?.trim() || '';
// In the step object:
body: JSON.stringify({
    action: captureType,
    selector: ...,
    after_step_id: ...,
    value: attrName,
    export_as: exportName,  // ← ADD THIS
}),
```

#### 2e. SSE Listener for `cdp_test:step_modified` — NEW

In `_cdpTestStartSSE()`, add listener alongside the existing `cdp_test:step_captured`:

```javascript
_cdpTestSSESource.addEventListener('cdp_test:step_modified', (e) => {
    try {
        const data = JSON.parse(e.data);
        if (data.data?.session_id !== sessionId) return;
        const step = data.data?.step;
        if (!step) return;

        // Update local step data
        _cdpStepDataMap.set(step.id, step);

        // Find and re-render the step row in the live list
        const row = document.querySelector(`.cdp-rec-step-row[data-step-id="${step.id}"]`);
        if (row) {
            // Update the row content with I/O indicators
            _cdpTestUpdateStepRowIO(row, step);
        }
    } catch (err) {
        console.warn('step_modified SSE parse error', err);
    }
});
```

#### 2f. Visual I/O Indicators in Live Step List — NEW

When a step has I/O configured, show badges in the step row:

**In `_cdpTestStepRow()` (the rendering function), after the desc line:**

```javascript
// I/O indicator
let ioTag = '';
const varMatch = (step.value || '').match(/^\$\{(\w+)\}$/);
if (varMatch) {
    ioTag = '<span style="font-size:0.6rem;padding:1px 5px;background:#8b5cf622;color:#8b5cf6;' +
        'border-radius:3px;margin-left:4px;font-family:monospace">📥 ${' + esc(varMatch[1]) + '}</span>';
}
if (step.export_as) {
    ioTag = '<span style="font-size:0.6rem;padding:1px 5px;background:#22c55e22;color:#22c55e;' +
        'border-radius:3px;margin-left:4px;font-family:monospace">📤 ' + esc(step.export_as) + '</span>';
}
```

Add `${ioTag}` to the row HTML after the description span.

**Update function for SSE changes:**

```javascript
function _cdpTestUpdateStepRowIO(row, step) {
    // Remove existing IO badge
    row.querySelector('.cdp-io-badge')?.remove();
    // Add new badge if applicable
    const varMatch = (step.value || '').match(/^\$\{(\w+)\}$/);
    if (varMatch) {
        const badge = document.createElement('span');
        badge.className = 'cdp-io-badge';
        badge.style.cssText = 'font-size:0.6rem;padding:1px 5px;background:#8b5cf622;color:#8b5cf6;border-radius:3px;margin-left:4px;font-family:monospace';
        badge.textContent = '📥 ${' + varMatch[1] + '}';
        row.querySelector('.cdp-step-desc')?.appendChild(badge);
    } else if (step.export_as) {
        const badge = document.createElement('span');
        badge.className = 'cdp-io-badge';
        badge.style.cssText = 'font-size:0.6rem;padding:1px 5px;background:#22c55e22;color:#22c55e;border-radius:3px;margin-left:4px;font-family:monospace';
        badge.textContent = '📤 ' + step.export_as;
        row.querySelector('.cdp-step-desc')?.appendChild(badge);
    }
}
```

---

### Layer 3: Target Site Overlay (`cdp_recorder.js`)

#### 3a. I/O Badge — DECISION NEEDED

**The question:** The I/O badge currently appears after every click, alongside the assert badge. But:
- INPUT applies to type steps (triggered by input events, not clicks)
- OUTPUT applies to capture steps (added separately via 📋 or assert modal)

**Option A: Remove target site I/O badge entirely.** I/O is configured from the admin panel only (🔗 toolbar button, 📋 capture config). Simpler. Less code to maintain.

**Option B: Keep badge but change behavior.** After clicking on a form field, the I/O badge lets you pre-mark that field as INPUT — so when the type event fires, the step is automatically created with `${VAR}` binding. This requires:
- Storing a "pending I/O config" per selector
- When `sendEvent({action:'type', selector:X})` fires, checking if that selector has pending I/O
- Applying the I/O automatically

**Option C: Badge appears only AFTER a type step exists.** After the user types and lifts focus, the recorder could show an I/O badge on the field they just typed in, offering to mark it as INPUT. This requires:
- Detecting that a type step was just recorded for an element
- Showing the badge on that element after the type event is sent
- The badge would open the INPUT overlay

**Recommendation:** Option A (remove) for now. The admin panel 🔗 button covers all I/O configuration. Target site badge can be added later if needed.

**If Option A chosen:**
- Remove I/O badge creation from `_showAssertBadge()` (lines ~470-535)
- Remove `_lastIOBadge` and `_ioBadgeTimer` variables (lines 307-308)
- Remove `_openIOModal()`, `_closeIOModal()`, `_saveIO()` (lines ~1245-1500)
- Clean deletion, no replacement

**If Option B or C chosen:**
- Rewrite `_openIOModal()` with correct model (INPUT only for type steps, OUTPUT only for capture steps — but capture steps aren't created from target site clicks, so this is effectively INPUT only)
- Rewrite `_saveIO()` to send correct payload

#### 3b. Target Site I/O Modal — REWRITE OR REMOVE

If kept (Option B or C), the modal must:

**For INPUT (shown when clicking a form field):**
- Color palette: self-contained (no CSS vars — foreign page)
- Title: "📥 Input — Suite Parameter"
- Subtitle via `.textContent` (XSS-safe): selector shown
- One field: variable name input
- Info: current element value shown as "Default value"
- Save button calls `sendEvent({ action: 'io_bind', selector, io_config: { variable_name } })`
- Cancel / click-outside closes and resumes recording

**For OUTPUT — probably NOT on target site.** Capture steps are added from the admin panel, not from target site clicks. So the target site modal would only ever show INPUT.

#### 3c. Backend `io_bind` Handler Fix

Already covered in Layer 1 (1c). Enforce mutual exclusivity.

---

### Layer 4: Step Editor — Validation View (`_cdp_test.html`)

#### 4a. Step Row Badges (`_cdpTestValStepRow`) — NEW

When rendering steps in the validation view list, show I/O indicators:

```javascript
// In _cdpTestValStepRow(), after building the description:
let ioBadge = '';
const varMatch = (step.value || '').match(/^\$\{(\w+)\}$/);
if (varMatch) {
    ioBadge = `<span style="display:inline-block;font-size:0.6rem;padding:1px 6px;
        background:#8b5cf622;color:#8b5cf6;border-radius:4px;margin-left:6px;
        font-family:monospace;font-weight:600">📥 \${${esc(varMatch[1])}}</span>`;
} else if (step.export_as) {
    ioBadge = `<span style="display:inline-block;font-size:0.6rem;padding:1px 6px;
        background:#22c55e22;color:#22c55e;border-radius:4px;margin-left:6px;
        font-family:monospace;font-weight:600">📤 ${esc(step.export_as)}</span>`;
}
// Append ioBadge after the step description in the row HTML
```

#### 4b. Step Edit Form (`_cdpTestBuildEditForm`) — REWRITE I/O SECTION

**Current state (WRONG):** For capture steps, shows two separate text fields:
- "Store as variable" (`cdp-edit-var-name`)
- "Export as (plan output)" (`cdp-edit-export-as`)

For type steps with value, shows:
- "Bind to variable" checkbox + variable name field

**Correct implementation:**

**For value actions (type, navigate, select, keypress, inject_js):**
```html
<!-- 📥 INPUT section -->
<div style="margin-top:0.8rem;padding:10px;border:1px solid #8b5cf633;border-radius:8px;background:#8b5cf60a">
    <div style="font-weight:600;font-size:0.78rem;color:#8b5cf6;margin-bottom:6px">📥 Input — Suite Parameter</div>
    <label style="font-size:0.72rem;display:flex;align-items:center;gap:6px;margin-bottom:6px">
        <input type="checkbox" id="cdp-edit-io-input" [checked if ${VAR} detected]>
        Mark as input parameter
    </label>
    <div id="cdp-edit-io-input-fields" style="[hidden if not checked]">
        <input id="cdp-edit-io-var-name" type="text" value="[extracted var name]"
            placeholder="LOGIN_EMAIL" style="monospace...">
        <div style="font-size:0.62rem;color:var(--text-muted)">
            Default: [original value] — configurable when running the suite
        </div>
    </div>
</div>
```

**For capture actions:**
```html
<!-- 📤 OUTPUT section -->
<div style="margin-top:0.8rem;padding:10px;border:1px solid #22c55e33;border-radius:8px;background:#22c55e0a">
    <div style="font-weight:600;font-size:0.78rem;color:#22c55e;margin-bottom:6px">📤 Output — Export</div>
    <input id="cdp-edit-io-export-name" type="text" value="[step.export_as]"
        placeholder="AUTH_TOKEN (optional)" style="monospace...">
    <div style="font-size:0.62rem;color:var(--text-muted)">
        Captured value exported to plan namespace for downstream suites
    </div>
</div>
```

**No "Store as variable" field. No dual fields. One section per step type.**

#### 4c. Step Edit Save (`_cdpTestApplyStepEdit`) — FIX

**For value actions:**
```javascript
// Read INPUT config
const inputChecked = document.getElementById('cdp-edit-io-input')?.checked;
if (inputChecked) {
    const varName = document.getElementById('cdp-edit-io-var-name')?.value?.trim();
    if (varName) {
        // Preserve original value
        if (!step.value?.match(/^\$\{\w+\}$/)) {
            step._original_value = step.value;
        }
        step.value = '${' + varName + '}';
    }
} else {
    // Unbind — restore original value
    if (step.value?.match(/^\$\{\w+\}$/)) {
        step.value = step._original_value || '';
    }
}
step.export_as = '';  // type steps cannot be output
```

**For capture actions:**
```javascript
// Read OUTPUT config
step.export_as = document.getElementById('cdp-edit-io-export-name')?.value?.trim() || '';
// No variable binding for capture steps
```

#### 4d. I/O Summary Panel (`_cdpTestBuildIOPanel`) — FIX

**Current state:** `_cdpTestAutoDetectIO()` scans for `${VAR}` references and `export_as` declarations. `_cdpTestBuildIOPanel()` renders them in tables. Currently read-only and uses wrong labels.

**What to fix:**
- Rename columns: "Inputs" (not "Variables"), "Outputs" (not "Exports")
- Input table: variable name, default value, which step uses it
- Output table: export name, which step produces it
- Make rows clickable → scroll to / highlight the corresponding step
- Add "Configure I/O" button that opens the 🔗 overlay for the relevant step

**Input table columns:**
| Variable | Default | Step |
|----------|---------|------|
| LOGIN_EMAIL | admin@test.com | #3 type |

**Output table columns:**
| Export | Step |
|--------|------|
| AUTH_TOKEN | #7 capture_text |

---

## Part 4: Execution Order

Each step is one change, independently verifiable.

### Phase A: Fix the broken code

| # | What | File | Scope |
|---|------|------|-------|
| A1 | Rewrite `_cdpTestOpenIOConfig()` | `_cdp_test.html` | Replace overlay with correct INPUT/OUTPUT by step type |
| A2 | Rewrite `_cdpTestSaveIO()` | `_cdp_test.html` | Match new overlay, enforce mutual exclusivity |
| A3 | Fix `io_bind` handler | `recording.py` | Enforce mutual exclusivity |
| A4 | Fix `modify-step` docstring | `recording.py` | Separate INPUT/OUTPUT examples |
| A5 | User decision: target site badge | `cdp_recorder.js` | Remove or rewrite based on user choice |
| A6 | Remove or rewrite target modal | `cdp_recorder.js` | Depends on A5 |

### Phase B: Build the "reverse" (creation-time I/O)

| # | What | File | Scope |
|---|------|------|-------|
| B1 | Add OUTPUT field to 📋 Capture Config | `_cdp_test.html` | `_cdpTestOpenCaptureConfig()` |
| B2 | Send export_as in capture save | `_cdp_test.html` | `_cdpTestSaveCapture()` |

### Phase C: Fix the step editor

| # | What | File | Scope |
|---|------|------|-------|
| C1 | Replace dual fields with correct I/O section | `_cdp_test.html` | `_cdpTestBuildEditForm()` |
| C2 | Fix step edit save | `_cdp_test.html` | `_cdpTestApplyStepEdit()` |

### Phase D: Visual enhancements

| # | What | File | Scope |
|---|------|------|-------|
| D1 | Step row badges in validation view | `_cdp_test.html` | `_cdpTestValStepRow()` |
| D2 | Step row badges in recording view | `_cdp_test.html` | `_cdpTestStepRow()` |
| D3 | SSE listener for step_modified | `_cdp_test.html` | `_cdpTestStartSSE()` |
| D4 | Fix I/O summary panel | `_cdp_test.html` | `_cdpTestBuildIOPanel()` + `_cdpTestAutoDetectIO()` |

### Phase E: Data model cleanup

| # | What | File | Scope |
|---|------|------|-------|
| E1 | Remove `variable_name` from modify-step whitelist | `recording.py` | "Store as variable" is not a concept |
| E2 | Clean up stale `variable_name` references | `_cdp_test.html` | Any remaining references from old hack |

---

## Part 5: File Map

All files that will be touched:

| File | What changes |
|------|-------------|
| `src/core/services/cdp_test/session.py` | Nothing — already correct |
| `src/ui/web/routes/cdp_test/recording.py` | Fix io_bind handler, fix docstring, clean whitelist |
| `src/ui/web/templates/scripts/integrations/_cdp_test.html` | Rewrite overlay, rewrite save, add capture export field, fix step editor, add badges, SSE listener, fix IO panel |
| `src/core/data/cdp_recorder.js` | Remove or rewrite I/O badge + modal (pending user decision) |

---

## Part 6: Open Question

**Target site I/O badge — keep or remove?**

Arguments for removal:
- I/O is a configuration concern, not a recording concern
- The admin panel 🔗 button already covers all I/O configuration
- The badge appears after clicks, but INPUT applies to type steps (input events) — timing mismatch
- Simpler, less code

Arguments for keeping:
- User sees the I/O option right there while recording
- Can pre-configure INPUT on form fields before typing

**Awaiting user decision.**
