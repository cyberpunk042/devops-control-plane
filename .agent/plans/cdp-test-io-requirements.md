# CDP Test Recorder — I/O Observability & Operability Requirements

## Scope

The **CDP Test Recorder admin panel** (`_cdp_test.html`).
Three separate surfaces. Each one stays separate. Each one gets smarter.

---

## ARCHITECTURE: THREE SURFACES, THREE PURPOSES

### Surface 1: Step Row (the list)
**Purpose**: At-a-glance observability. You see the whole test flow and instantly understand what's parameterized, what's exported, and how.

### Surface 2: Step Edit Modal (`_cdpTestEditStep`)
**Purpose**: Edit THIS step's properties. When you click a row, you see everything about THAT row — its action, its selector, its value, its I/O, its assertions. Complete picture of that one step.

### Surface 3: I/O Config Overlay (`_cdpTestOpenIOConfig`)
**Purpose**: Dedicated I/O configuration. INPUT/OUTPUT toggle, capture type selection, variable/export naming, default values. This is the specialized tool for wiring inputs and outputs.

### Surface 4: I/O Summary Panel
**Purpose**: Suite-level I/O overview. All inputs, all outputs, their relationships, warnings, and validation. The bird's-eye view.

**These four surfaces are independent. None replaces another. All four get enriched.**

---

## 1. WHAT ACTUALLY EXISTS TODAY (TRUTH)

### 1.1 Step Row Badges
- INPUT: `📥 ${VAR_NAME}` — tiny purple badge, name only
- OUTPUT: `📤 EXPORT_NAME` — tiny green badge, name only
- No capture type, no attribute/CSS, no default value visible

### 1.2 Step Edit Modal
**Value actions (type, select, keypress, navigate, inject_js):**
- Value field (editable)
- INPUT section: checkbox toggle "Mark as input parameter" → variable name field
- Default value shown as STATIC TEXT (not editable!)
- If bound, value field becomes readonly

**Capture actions (capture_text, capture_attribute, etc.):**
- Selector field
- `capture_attribute`: plain text input for attribute name (no select+custom)
- `capture_computed_style`: plain text input for CSS property (no select+custom)
- export_as text field
- Capture type NOT changeable — the action IS the type, fixed
- No "capture type" dropdown

**Click/hover steps:**
- Selector only
- No I/O section at all
- If this step has a following capture step (linked output), no indication

### 1.3 I/O Config Overlay
- INPUT/OUTPUT toggle (for form-targeting actions)
- INPUT: variable name + editable default value
- OUTPUT: capture type dropdown + attribute/CSS selects + export name
- Remove I/O button
- For existing capture steps: capture type shown as info badge (NOT changeable)
- For click/hover: creates NEW capture step

### 1.4 I/O Summary Panel
- Collapsed by default
- Inputs table: Name, Default, Source (step number)
- Outputs table: Name, Source (step number), Description (always empty)
- Click row → opens I/O overlay for that step
- Auto-detected hint

---

## 2. WHAT EACH SURFACE NEEDS TO BECOME

### 2.1 Step Row Badges — ENRICHED

**INPUT badge (purple):**
```
📥 LOGIN_EMAIL = "admin@test.com"
```
Shows variable name AND truncated default value so you see at a glance what the parameter is and what it defaults to.

**OUTPUT badge (green) — shows capture detail:**
```
📤 AUTH_TOKEN (text)           — capture_text
📤 LINK_URL (attr:href)       — capture_attribute with attribute name
📤 BG_COLOR (style:color)     — capture_computed_style with CSS property
📤 PAGE_HTML (html)            — capture_html
📤 FIELD_VAL (value)           — capture_value
📤 CURRENT_URL (url)           — capture_url
📤 FRAME (screenshot)          — capture_screenshot
```
Shows export name AND capture type AND attribute/property when applicable.

**Connection indicators:**
If step 3 exports `TOKEN` and step 7 uses `${TOKEN}`:
- Step 3 badge: `📤 TOKEN (text) → step 7`
- Step 7 badge: `📥 TOKEN ← step 3`
Visual linkage showing the flow.

### 2.2 Step Edit Modal — ENRICHED

The step edit modal is about THIS step. It shows everything relevant to this step, including its I/O configuration — **for reading AND editing**.

**Value actions (type, select, keypress, navigate, inject_js):**
- Value field (editable, as now)
- INPUT section (as now, with checkbox toggle):
  - Variable name field (as now)
  - **Default value: EDITABLE** (not static text — a real input field pre-populated with original value)
  - Show where this variable is consumed: "Used by: step 7, step 12" (if other steps reference `${thisVar}`)
- OUTPUT section (NEW for value actions in edit modal):
  - If this step has an associated capture step following it, show its info:
    - Capture type (what it captures)
    - Attribute name / CSS property (if applicable)
    - Export name
  - If no associated capture step, show option to add one (or direct user to I/O overlay)
- Mutual exclusivity enforced: INPUT xor OUTPUT

**Capture actions (capture_text, capture_attribute, etc.):**
- Selector field (as now)
- **Capture type: CHANGEABLE dropdown** — select from text/html/value/attribute/url/computed_style/screenshot
  - Changing this changes the step's `action` field on save
- For `capture_attribute`: **select + custom** for attribute name (not plain text)
  - Select with common attributes: href, src, data-testid, data-id, aria-label, title, alt, name, type, role, class, id
  - Custom option → reveals text input
- For `capture_computed_style`: **select + custom** for CSS property (not plain text)
  - Select with common properties: color, background-color, display, visibility, opacity, font-size, font-weight, width, height, margin, padding, border, position, z-index, overflow, text-align
  - Custom option → reveals text input
- Export name field (as now)
- Show where this export is consumed: "Consumed by: step 7 as ${TOKEN}" (if any step references this export name)

**Click/hover steps:**
- Selector (as now)
- If a capture step follows this step and targets the same selector, show its info:
  - "📤 This step has a linked capture: capture_text → exported as AUTH_TOKEN"
  - Link to edit the capture step (click to open its own edit modal)
- If no linked capture: nothing — use the I/O overlay to add one

**Assert steps:**
- All existing assert config (as now — categories, check types, expected value, etc.)
- No I/O additions needed (asserts don't export or consume I/O)

### 2.3 I/O Config Overlay — STAYS, ENHANCED

This is the DEDICATED tool for I/O configuration. It stays separate. Enhancements:

**Already implemented:**
- INPUT/OUTPUT toggle for form elements
- INPUT: variable name + editable default value
- OUTPUT: capture type dropdown + attribute/CSS select+custom + export name
- Remove I/O button

**Still needed:**
- For existing capture steps: capture type should be EDITABLE (not just info badge)
  - Changing capture type here changes the step's action
- Validation: warn if export name duplicates another export
- Validation: warn if variable name doesn't follow identifier format (already done for save, add visual inline feedback)
- Show where this I/O connects: "This output will be available as ${NAME} for downstream suites"
- For INPUT: show if any step in the suite already uses this variable

### 2.4 I/O Summary Panel — ENRICHED

**Auto-expanded** when I/O exists (not collapsed by default).

**Inputs table columns (enriched):**

| Name | Default | Used at | Status |
|------|---------|---------|--------|
| `LOGIN_EMAIL` | `admin@test.com` | Steps 3, 7 | ✅ |
| `PASSWORD` | *(empty)* | Step 4 | ⚠️ no default |
| `TOKEN` | — | Step 12 | ❌ unresolved (no step exports TOKEN) |

- Name: monospace, purple, clickable → opens I/O overlay for first consuming step
- Default: shows truncated value or "—" if none
- Used at: list of step numbers where `${name}` appears
- Status:
  - ✅ has default value
  - ⚠️ no default value set (will need runtime value)
  - ❌ unresolved — variable referenced but no output provides it

**Outputs table columns (enriched):**

| Name | Capture | Detail | Step | Status |
|------|---------|--------|------|--------|
| `AUTH_TOKEN` | text | — | Step 5 | ✅ |
| `LINK_URL` | attribute | `href` | Step 8 | ✅ |
| `BG_COLOR` | computed_style | `color` | Step 11 | ⚠️ orphan |
| `AUTH_TOKEN` | value | — | Step 14 | ❌ duplicate |

- Name: monospace, green, clickable → opens I/O overlay for that step
- Capture: capture type (text, html, value, attribute, computed_style, url, screenshot)
- Detail: attribute name or CSS property (if applicable), "—" otherwise
- Step: step number
- Status:
  - ✅ consumed (some step uses `${name}` as input)
  - ⚠️ orphan (exported but never consumed — maybe intentional for downstream suites)
  - ❌ duplicate (another step exports the same name)

**Validation warnings section (below tables):**
- ⚠️ `${TOKEN}` used in step 12 but no output named `TOKEN` exists in this suite
- ⚠️ `AUTH_TOKEN` exported at step 5 AND step 14 — duplicate export name
- ⚠️ `BG_COLOR` exported at step 11 but never referenced by any input in this suite

---

## 3. DATA REQUIREMENTS

### 3.1 Step data fields used for I/O

From `TestStep` model (`models.py`):
- `value`: contains `${VAR_NAME}` pattern when bound as INPUT
- `original_value`: the recorded value before variable binding
- `export_as`: the export name for OUTPUT
- `assertion_attribute`: stores attribute name (for capture_attribute) or CSS property (for capture_computed_style)
- `action`: the capture type IS the action name (capture_text, capture_attribute, etc.)

### 3.2 What the step edit modal needs to save

When saving from the step edit modal:
- If capture type changed: update `step.action` to the new capture type
- If attribute/CSS selected: update `step.assertion_attribute`
- If export name changed: update `step.export_as`
- If variable name changed: update `step.value` to `${newName}`
- If default value edited: update `step.original_value`
- All changes go through the existing save/API flow (local step data → API call)

### 3.3 What the I/O overlay saves

Already implemented — sends to `/cdp-test/io/configure` endpoint.
- `step_id`, `io_type`, `name`, `default_value`, `capture_type`, `attribute_name`, `css_property`

---

## 4. IMPLEMENTATION PHASES

### Phase 1: Step Row Badges (Observability)
Enriched badges showing capture type + attribute/CSS + default value.
Connection indicators showing flow between steps.
**Files**: `_cdp_test.html` — step rendering functions (recording view ~line 526-543, validation view ~line 2136-2160)
**Risk**: Low — display only, no logic changes
**Test**: Visual — badges show correct enriched info

### Phase 2: Step Edit Modal Enrichment (Operability)
- Capture type dropdown for capture steps (changes action on save)
- Select+custom for attribute name and CSS property
- Editable default value for INPUT parameters
- "Connected to" info showing where I/O links to
**Files**: `_cdp_test.html` — `_cdpTestEditStep` function (~line 2480+) and save handler (~line 2660+)
**Risk**: Medium — modifying existing modal, need to preserve all current functionality
**Test**: Open edit modal for each step type, verify all fields work, save and verify data integrity

### Phase 3: I/O Summary Panel Enrichment (Observability)
- Auto-expand when I/O exists
- Enhanced tables with capture type, detail, status columns
- Validation warnings section
**Files**: `_cdp_test.html` — `_cdpTestBuildIOPanel` function (~line 1888+)
**Risk**: Low — display enhancements
**Test**: Create a suite with mixed I/O, verify tables show correct enriched data and warnings

### Phase 4: I/O Overlay Enhancements
- Make capture type editable for existing capture steps
- Live validation (duplicate export name warning)
- Connection info ("This output available as...")
**Files**: `_cdp_test.html` — `_cdpTestOpenIOConfig` function (~line 1220+)
**Risk**: Medium — changing overlay behavior for existing capture steps
**Test**: Open I/O overlay for various step types, verify all enhancements work

---

## 5. NON-GOALS (OUT OF SCOPE)

- Merging modals together (each modal has its purpose, they stay separate)
- Removing the I/O overlay (it stays as the dedicated I/O configuration tool)
- Drag-and-drop reordering of I/O bindings
- Cross-suite I/O validation (only within the current suite)
