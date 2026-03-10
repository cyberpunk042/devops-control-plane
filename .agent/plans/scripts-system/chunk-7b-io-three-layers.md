# Chunk 7b — CDP Test I/O: Three-Layer Implementation Plan

## Context & Problem Statement

The CDP test system has **three layers** where users interact with test steps:

1. **Target Site** — the actual webpage being recorded; the recorder JS
   (`cdp_recorder.js`) is injected into it, showing floating badges and
   modals when the user clicks elements.
2. **Admin Panel Recording View** — the live step list in the DCP admin
   panel during an active recording session. Steps appear as they are
   captured, with a toolbar (✅ Assert, 📋 Capture, 💉 Diag) on hover.
3. **Step Editor (Validation View)** — the post-recording step editor
   (`_cdpTestEditStep` / `_cdpTestBuildEditForm`) plus the suite-level
   I/O summary panel.

**None of these layers have proper I/O support.**

Layer 3 has raw form fields hacked into an existing edit modal — a
checkbox toggling variable binding, a bare text field for export_as, and
a read-only auto-detection dump called an "I/O summary panel." This is
scaffolding exposed to the user through an existing UI surface. It is not
a designed I/O experience. It is not acceptable as delivered work.

---

## Current State — Honest Assessment

| Layer | What exists | Status |
|-------|-------------|--------|
| **1. Target Site** (`cdp_recorder.js`) | Nothing. Zero I/O UI. | ❌ Not started |
| **2. Admin Panel Recording View** (`_cdp_test.html` recording) | Nothing. No I/O badge in toolbar. No I/O overlay. | ❌ Not started |
| **3. Step Editor / Validation View** (`_cdp_test.html` validation) | Hack. Raw form fields jammed into `_cdpTestBuildEditForm`. Read-only detection tables in a collapsible div. No first-class I/O experience. No visual indicators in step rows. | ❌ Hack, needs proper implementation |

### What the Layer 3 "hack" actually is:

- **Variable binding toggle** (lines 2019-2047): A checkbox "Bind to
  variable" injected between the value field and the attribute field in
  the generic step edit form. No visual separation, no grouping, no
  identity as I/O. Just another form element in a list.

- **Export_as field** (line 2063): A single `modalFormField()` call —
  `label: 'Export as (plan output)'` — thrown into the capture fields
  section. No context, no preview, no guidance.

- **I/O summary panel** (lines 1378-1530): `_cdpTestBuildIOPanel()` —
  auto-detects `${VAR}` references and `export_as` values, renders two
  read-only HTML tables. Cannot add, edit, remove, or configure anything.
  No click-through to source steps. No ability to set types or defaults.
  Purely passive dump.

- **Save logic** (lines 2142-2168): The data plumbing works — variable
  binding wraps/unwraps `${VAR}`, preserves `_original_value`, saves
  `export_as`. The DATA layer is functional. The EXPERIENCE is not.

- **Validation step row** (`_cdpTestValStepRow`, lines 1603-1653): Shows
  ZERO I/O indication. No badges for variable-bound steps. No badges
  for export steps. You cannot tell which steps have I/O without clicking
  into each one.

### The data plumbing that DOES work (keep, don't rewrite):

- `_cdpTestAutoDetectIO(steps)` — scans for `${VAR}` and `export_as`
- `_cdpTestApplyStepEdit()` — variable binding wrap/unwrap + export_as save
- `_cdpTestVarBindToggle()` — checkbox show/hide + readonly toggle
- TestStep model fields: `export_as`, `variable_name`, `_original_value`
- Replayer `${VAR}` substitution via `_resolve_variables()`
- Suite save/load round-trip for `variable_defs`, `outputs`, `variables`

---

## Architecture: How Assertion Works Across 3 Layers (Pattern to Follow)

The assertion feature already exists across all three layers. It serves as
the architectural pattern to follow — BUT I/O is a separate, independent
feature that must NOT be conflated with assertions.

### Layer 1: Target Site (`cdp_recorder.js`)

```
User clicks element
  → sendEvent({ action:'click', selector, ... })
  → setTimeout(150ms) → _showAssertBadge(el, selector, ...)
    → Green ✅ badge floating near element
    → Badge click → _openAssertModal(selector, elemText, elemRect, selectorChain)
      → Full overlay modal:
        §0: Target Element picker (ancestor chain — gone elements greyed out)
        §1: What to Capture (text/html/value/attr/screenshot/state/console)
        §2: Live Preview
        §3: Assertion Check (type + expected)
        §4: On Failure
        §5: Diagnostics
      → Save → sendEvent({ action:'assert', assert_config:{...} })
```

**Key design detail**: Elements that disappeared from DOM are **greyed out**
with `⚠ gone` and disabled radio + warning message. This is CORRECT for
assertions — you can't assert on what doesn't exist.

### Layer 2: Admin Panel (`_cdp_test.html` recording view)

```
Step row rendered by _cdpTestStepRow(step)
  → Hover reveals toolbar: [✅] [📋] [💉]
  → ✅ → _cdpTestOpenAssertConfig(step) → full overlay → POST /add-step
  → 📋 → _cdpTestOpenCaptureConfig(step) → simpler overlay → POST /add-step
  → 💉 → _cdpTestOpenDiagConfig(step) → diagnostic overlay → POST /add-step
```

### Layer 3: Step Editor (`_cdpTestEditStep`)

```
Validation view → step list → click step → _cdpTestEditStep(index)
  → Sub-modal with _cdpTestBuildEditForm(step)
    → Action type, selector, value fields, assert config, optional flag
    → [HACK] Variable binding checkbox buried in form
    → [HACK] export_as text field buried in captures section
  → Save → updates steps array
```

---

## I/O Feature: What It IS vs What It ISN'T

### It IS:
- A **first-class feature** with its own identity, colors, icons, and experience
- A **separate badge** alongside the assert badge — NOT inside assertions
- Its own properties on steps (`variable_bind` for inputs, `export_as` for outputs)
- For **any action with a value** (type, select, navigate, keypress, inject_js) → input binding
- For **any capture action** (capture_text, capture_html, etc.) → output export
- A feature where disappeared elements are still **valid targets** (unlike assertions)

### It ISN'T:
- A subset of assertions
- A form field tacked onto an existing modal
- Limited by DOM availability
- A read-only detection dump

---

## Critical Design Difference: Element Availability

| Feature | Element gone from DOM | Behavior |
|---------|----------------------|----------|
| **Assertion** | Greyed out, disabled, `⚠ gone` | ✅ Correct — can't assert on nonexistent |
| **I/O Input** | **Still selectable, NOT greyed out** | Variable feeds value at replay time |

If user already typed text → that becomes the **suggested default**.
Variable input **overrides** hardcoded input at replay time.

---

## Implementation Plan

### Phase 1: Backend Foundation

**1.1 — New endpoint: `POST /cdp-test/record/modify-step`**

Input binding MODIFIES an existing step (changes `"admin@test"` to
`"${LOGIN_EMAIL}"`). This is different from assertion/capture which
INSERT new steps. Needs a new endpoint.

```python
@cdp_test_bp.route("/cdp-test/record/modify-step", methods=["POST"])
def cdp_test_record_modify_step():
    """Modify an existing step in the active recording.

    Body (JSON):
        {
            "step_id": "uuid",
            "value": "${LOGIN_EMAIL}",
            "_original_value": "admin@test",
            "export_as": "TOKEN",
        }
    """
```

File: `src/ui/web/routes/cdp_test/recording.py`

**1.2 — Session methods: `find_step()` + `modify_step()`**

The recording session currently only supports `add_step` and
`insert_step_after`. Needs `find_step(step_id)` to locate and
`modify_step(step_id, updates)` to update.

File: `src/core/services/cdp_test/session.py`

**1.3 — SSE event: `cdp_test:step_modified`**

New event so admin panel updates step row in-place when I/O is configured
(not re-render entire list).

---

### Phase 2: Admin Panel Recording View — I/O Badge + Overlay

**2.1 — Add I/O badge to step toolbar**

Add a 4th button to `_cdpTestStepRow` toolbar:

```javascript
// Current (lines 409-417):
[✅ Assert] [📋 Capture] [💉 Diag]

// New:
[✅ Assert] [📋 Capture] [💉 Diag] [🔗 I/O]
```

The I/O badge should also appear for steps WITHOUT a selector (e.g.,
`navigate` steps can have their URL bound to a variable). Condition:

```javascript
const canIO = ['type','navigate','select','keypress','inject_js'].indexOf(step.action) !== -1
    || step.action.indexOf('capture_') === 0;
```

**2.2 — I/O configuration overlay: `_cdpTestOpenIOConfig(step)`**

New overlay function, pattern follows `_cdpTestOpenAssertConfig` but
with I/O-specific content. Purple accent (#8b5cf6) to distinguish from
assertion green.

**For value actions** (type, select, navigate, keypress, inject_js):
```
┌─────────────────────────────────────────────┐
│ 🔗 I/O Configuration                       │
│ selector: input[name="email"]               │
├─────────────────────────────────────────────┤
│                                             │
│ INPUT BINDING                               │
│ Variable name: [LOGIN_EMAIL        ]        │
│ Current value: "admin@example.com"          │
│   → will become default for this variable   │
│                                             │
│ OUTPUT EXPORT (optional)                    │
│ Export as: [                       ]         │
│   → exports captured value to plan namespace│
│                                             │
│              [Cancel]  [💾 Save I/O]        │
└─────────────────────────────────────────────┘
```

**For capture actions** (capture_text, capture_html, etc.):
```
┌─────────────────────────────────────────────┐
│ 🔗 I/O Configuration                       │
│ selector: div.auth-token-display            │
├─────────────────────────────────────────────┤
│                                             │
│ OUTPUT EXPORT                               │
│ Export as: [AUTH_TOKEN             ]         │
│ Description: [Token from login    ]         │
│                                             │
│ LIVE PREVIEW                                │
│ "Bearer eyJhbGciOiJIUzI1NiIs..."           │
│                                             │
│              [Cancel]  [💾 Save I/O]        │
└─────────────────────────────────────────────┘
```

**Save behavior:**
- Input binding → `POST /cdp-test/record/modify-step` (modifies existing)
- Output export → `POST /cdp-test/record/modify-step` (sets export_as on existing capture)
  OR `POST /cdp-test/record/add-step` (creates new capture step with export_as)

**2.3 — Visual feedback in step rows**

After I/O is configured, step row shows inline indicators:
- Input-bound: `📥 ${VAR_NAME}` badge in purple
- Export: `📤 TOKEN_NAME` badge in green
- These appear alongside existing assertion indicators

**2.4 — Event delegation update**

Add `'io'` to the click handler at line ~535-546:
```javascript
if (action === 'io') _cdpTestOpenIOConfig(step);
```

---

### Phase 3: Target Site — I/O Badge + Modal (`cdp_recorder.js`)

**3.1 — I/O badge next to Assert badge**

Currently `_showAssertBadge` shows: `✅ Assert` with tiny `📋 💉` icons.
Add a **second badge** — the I/O badge — that appears alongside it.

```
User clicks element
  → existing assert badge (green, ✅)
  → new I/O badge (purple, 🔗) appears next to/below it
    → Click → _openIOModal(selector, elemText, elemRect, selectorChain)
```

Design:
- Purple (#8b5cf6) background to distinguish from assertion green (#22c55e)
- Both badges appear simultaneously — independent features
- Auto-dismiss after 4s (same pattern as assert badge)
- Only appears for eligible actions (input elements get input mode,
  all elements get output mode)

**3.2 — I/O modal on target site: `_openIOModal()`**

Similar structure to `_openAssertModal` but I/O-specific:

```
┌─────────────────────────────────────────────┐
│ 🔗 Variable Configuration                  │
│ selector: input[name="email"]               │
├─────────────────────────────────────────────┤
│                                             │
│ TARGET ELEMENT                              │
│ (ancestor chain — same as assertion BUT     │
│  elements gone from DOM are NOT greyed out  │
│  — they are "📦 variable-ready")            │
│  ● <input> input[name="email"]   ✓ in DOM  │
│  ○ <form> form.login             ✓ in DOM  │
│                                             │
│ MODE                                        │
│ ● Input — bind value to variable            │
│ ○ Output — export captured value            │
│                                             │
│ ── INPUT ────────────────────────────────── │
│ Variable name: [LOGIN_EMAIL        ]        │
│ Current value: "admin@example.com"          │
│   (will be suggested as default)            │
│                                             │
│ ── OUTPUT ───────────────────────────────── │
│ What to capture:                            │
│ ○ Text  ○ HTML  ○ Value  ○ Attribute       │
│ Export as: [AUTH_TOKEN             ]         │
│ Live preview: "Bearer eyJ..."               │
│                                             │
│              [Cancel]  [💾 Save I/O]        │
└─────────────────────────────────────────────┘
```

**Key behaviors:**
- **Ancestor chain**: Same element picker as assertion BUT elements gone
  from DOM are NOT greyed out / disabled. Instead of `⚠ gone` → show
  `📦 variable-ready` or `🔗 bindable`. Because variables CAN feed values
  to gone elements at replay time.
- **Auto-detection**: If clicked step was `type` → pre-select Input mode.
  If capture action → pre-select Output mode.
- **Save (Input)**: Sends to `POST /record/modify-step` to change
  existing step's value to `${VAR_NAME}`.
- **Save (Output)**: Sends to `POST /record/add-step` to create new
  capture step with `export_as`, or modify existing capture.

**3.3 — sendEvent modifications**

No changes to `sendEvent()` itself. I/O save calls go to different
endpoints:
- `POST /record/modify-step` (input binding — modify existing step)
- `POST /record/add-step` (output capture — insert new capture step)

---

### Phase 4: Step Editor — Proper I/O Experience (Replace the Hack)

The existing hack (scattered form fields) must be replaced with a
first-class I/O section in the step editor.

**4.1 — I/O badges in `_cdpTestValStepRow`**

The validation step list must show inline I/O indicators:

```javascript
// After existing optBadge (line 1642-1644), add:
var ioBadges = '';
if (step.value && step.value.match(/^\$\{\w+\}$/)) {
    var varName = step.value.slice(2, -1);
    ioBadges += '<span style="font-size:0.58rem;padding:1px 4px;background:#8b5cf622;color:#8b5cf6;border-radius:3px;margin-left:4px">📥 ${' + esc(varName) + '}</span>';
}
if (step.export_as) {
    ioBadges += '<span style="font-size:0.58rem;padding:1px 4px;background:#22c55e22;color:#22c55e;border-radius:3px;margin-left:4px">📤 ' + esc(step.export_as) + '</span>';
}
```

These badges appear inline in the step row so you can see I/O at a
glance without clicking into each step.

**4.2 — Dedicated I/O section in step edit form**

Replace the scattered hack with a proper I/O section in
`_cdpTestBuildEditForm`. This section has:

- Its own visual identity (purple accent, border, icon)
- Clear "I/O Configuration" header with 🔗 icon
- Grouped under a distinct panel, not mixed with other fields

**For value actions:**
```
┌─ 🔗 I/O Configuration ────────────────────┐
│                                            │
│ ☑ Bind to variable                        │
│ Variable name: [LOGIN_EMAIL       ]        │
│ Default value: "admin@example.com"         │
│                                            │
│ (When bound, the step will receive its     │
│  value from the variable at replay time)   │
│                                            │
└────────────────────────────────────────────┘
```

**For capture actions:**
```
┌─ 🔗 I/O Configuration ────────────────────┐
│                                            │
│ Store as variable: [my_token      ]        │
│ Export as (plan output): [AUTH_TOKEN]       │
│                                            │
│ (Stored variables are available within     │
│  this suite. Exported variables are        │
│  available to the plan namespace.)         │
│                                            │
└────────────────────────────────────────────┘
```

**4.3 — I/O summary panel: from read-only dump to configuration tool**

Replace the current passive `_cdpTestBuildIOPanel` with an interactive
panel:

- **Click-through**: Clicking a variable name navigates to the step
  that references it (scrolls + highlights the step row).
- **Inline editing**: Can edit default values, types, descriptions
  directly in the table.
- **Add manual**: Button to add manual input variables not detected
  from steps.
- **Remove**: Can remove manual variables.
- **Output descriptions**: Editable description field for each output.

---

## Implementation Order

```
Phase 1 (Backend)            — modify-step endpoint + session support
   ↓
Phase 2 (Admin Panel)        — Recording view: I/O badge + overlay + visual
   ↓
Phase 3 (Target Site)        — cdp_recorder.js: I/O badge + modal
   ↓
Phase 4 (Step Editor)        — Replace hack with proper I/O experience
```

Rationale:
- Backend/API first so UI layers have something to call
- Admin panel before target site because it's easier to test (no CDP injection)
- Step editor last because the existing data plumbing works (save logic,
  auto-detection). What needs replacement is the UI/UX, not the data layer.

---

## File Impact Map

| File | Changes |
|------|---------|
| `src/ui/web/routes/cdp_test/recording.py` | New `/record/modify-step` endpoint |
| `src/core/services/cdp_test/session.py` | `find_step()`, `modify_step()` methods |
| `src/ui/web/templates/scripts/integrations/_cdp_test.html` | I/O badge in recording toolbar, new I/O overlay, step row indicators, event delegation, replace hack in edit form, interactive I/O panel |
| `src/core/data/cdp_recorder.js` | I/O badge, I/O modal, element availability changes |

---

## What Already Works (Keep, Don't Rewrite)

These are the data plumbing pieces that work correctly. The implementation
should build the proper experience ON TOP of these, not replace them:

- **Replayer**: `_resolve_variables()` handles `${VAR_NAME}` substitution
- **TestStep model**: `export_as`, `variable_name` fields exist and persist
- **Plan executor**: Reads `export_as` and pushes to namespace
- **Suite save/load**: Round-trips `variable_defs`, `outputs`, `variables`
- **Auto-detection**: `_cdpTestAutoDetectIO()` scans steps correctly
- **Save logic**: `_cdpTestApplyStepEdit()` properly wraps/unwraps `${VAR}`,
  preserves `_original_value`, saves `export_as`
- **Toggle logic**: `_cdpTestVarBindToggle()` show/hide + readonly works

What failed is the **experience** — these plumbing pieces were exposed
as raw form controls scattered through an existing modal and called
"delivered." The data works. The experience doesn't exist.

---

## Design Principles

1. **I/O is a first-class citizen** — its own badge, own modal, own visual
   identity (purple accent), its own section in the editor. Not injected
   into assertion or existing forms.
2. **Not conflated with assertions** — may share UI paradigms (badge →
   overlay → step modification) but they are independent features with
   their own icons, colors, and behaviors.
3. **Disappeared elements are NOT greyed out** — unlike assertions,
   variables can still feed values to gone elements at replay time.
   Show as `📦 variable-ready` instead of `⚠ gone`.
4. **User's typed input becomes suggested default** — not lost, but
   overridable by the variable value.
5. **Three layers, one feature** — all three must properly support I/O,
   each in the way appropriate to the context (target site modal, admin
   panel overlay, step editor section).
6. **No hacks** — form fields are not features. Auto-detection dumps are
   not configuration tools. Scattered checkboxes are not experiences.
