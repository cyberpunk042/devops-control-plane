# Modules Posture V2 — Execution Plan
> Status: EXECUTE — 2026-03-17
> Prerequisite: V1 data is working (per-module differentiation verified)
> Goal: Transform raw data dump into complete interactive experience

---

## What Exists (Infrastructure to Build On)

### Interaction Patterns Already in Codebase
- **Modal system**: `modalOpen({title, body, size, footerButtons, onClose, replace})`
  — supports stacking, forms, steps, preview panels. Size `'posture'` = 960px.
- **Toast**: `toast(msg, type)` — success/error/warning/info, auto-dismiss 6s
- **Buttons**: `.btn`, `.btn-sm`, `.btn-primary`, `.btn-ghost`, `.btn-danger`
  — posture buttons: `.posture-btn-update`, `.posture-btn-manual`, etc.
- **Expand/collapse**: `.posture-pillar.expanded` toggle pattern
- **Status badges**: `.status-badge.ok/.degraded/.failed`
- **Form builder**: `modalFormField({name, label, type, value, hint, options})`
- **API helpers**: `api(path, opts)`, `apiPost(path, body)`
- **Acknowledgement pattern**: `data-status="acknowledged"` with CSS styling
- **NO custom tooltip system exists** — uses browser `title=` attributes only

### Data Available But Not Sent to Frontend
- `deps_details[]` — per-package breakdown (discarded with `_` in enrichment)
- `code_features` — truncated to 3 items, full list available
- Floor tier breakdown — not computed as structured data
- Module metadata (file count, path, domain) — available from project config

---

## Execution Steps

### Step 1: Reuse Peek Panel Pattern

The dependency manager already has a battle-tested peek panel system:
- `_depShowPeek(node, x, y)` — click-triggered, viewport-aware positioning
- `.dep-peek` CSS class — styled popup with animation, shadow, border
- Dismiss on click-outside via mousedown delegation
- Smart edge detection: flips left/right/up if near viewport edge

For modules posture, build `_moduleShowPeek(cellData, x, y)` following the
same pattern. Reuse the `.dep-peek` base styling, extend with `.module-peek`
for module-specific content.

```javascript
function _moduleShowPeek(content, x, y) {
    // Remove any existing peek
    const old = document.querySelector('.module-peek');
    if (old) old.remove();

    const el = document.createElement('div');
    el.className = 'module-peek';
    el.innerHTML = content;
    document.body.appendChild(el);

    // Viewport-aware positioning (same logic as dep-peek)
    const rect = el.getBoundingClientRect();
    let left = x + 12;
    let top = y - 20;
    if (left + rect.width > window.innerWidth - 16) left = x - rect.width - 12;
    if (top + rect.height > window.innerHeight - 16) top = window.innerHeight - rect.height - 16;
    if (top < 8) top = 8;
    el.style.left = left + 'px';
    el.style.top = top + 'px';

    // Dismiss on click outside
    setTimeout(() => {
        document.addEventListener('mousedown', function handler(e) {
            if (!el.contains(e.target)) {
                el.remove();
                document.removeEventListener('mousedown', handler);
            }
        });
    }, 50);
}
```

Each table cell gets `onclick="moduleShowCellPeek('column', itemData, event)"`
which builds the appropriate content HTML and calls `_moduleShowPeek()`.

CSS extends the dep-peek pattern:
```css
.module-peek {
    /* Same base as .dep-peek */
    position: fixed; z-index: 1002;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    box-shadow: 0 8px 24px rgba(0,0,0,0.25);
    padding: var(--space-md);
    max-width: 380px;
    font-size: 0.78rem;
    line-height: 1.5;
    animation: dep-peek-in 0.12s ease-out;  /* reuse same animation */
}
```

**Files changed:**
- `_system_posture.html` — `_moduleShowPeek()` + `moduleShowCellPeek()` + per-column content builders
- `admin.css` — `.module-peek` and content classes (`.mp-title`, `.mp-row`, `.mp-section`, `.mp-muted`, `.mp-actions`)

### Step 2: Send Full Data to Frontend

The enrichment layer discards deps_details and truncates code_features.
Fix this.

```python
# posture.py enrichment — STOP discarding
deps_floor, deps_details = compute_dependency_floor(...)
item["deps_floor"] = f"≥{deps_floor}" if deps_floor else "—"
item["deps_details"] = deps_details  # ← SEND THE FULL LIST

code_floor_ver, code_features = compute_code_floor(...)
item["code_floor"] = code_floor_ver or "—"
item["code_features"] = code_features  # ← SEND ALL, NOT [:3]
```

Also build and send floor tier analysis:
```python
item["floor_tiers"] = {
    "tier1": {"source": "module", "found": bool, "value": "..."},
    "tier2": {"source": "stack", "found": bool, "value": "...", "stack_name": "..."},
    "tier3": {"source": "project", "found": bool, "value": "..."},
    "used": "stack",  # which tier was actually used
}
```

Also send module metadata for the Module column tooltip:
```python
item["module_meta"] = {
    "path": ref.path,
    "domain": ref.domain,
    "description": ref.description,
    "file_count": count of .py files in module dir,
}
```

Also send stack metadata for the Stack column tooltip:
```python
item["stack_meta"] = {
    "parent": stack_def.parent,
    "requires": [{adapter, min_version}],
    "capabilities": [cap.name for cap in stack_def.capabilities],
}
```

**Files changed:**
- `posture.py` — enrichment section: pass full details, build new structures
- May need to load stack definitions in enrichment (already imported)

### Step 3: Render Tooltips for All 9 Columns

Each cell gets a hover tooltip with contextual information.

**Module column:**
```html
<td class="posture-module-cell-name" data-tooltip>
    core
    <div class="module-tip">
        <div class="tip-title">Module: core</div>
        <div class="tip-row">Path: src/core</div>
        <div class="tip-row">Domain: library</div>
        <div class="tip-row">Stack: python-lib (detected)</div>
        <div class="tip-row">Files: 582 .py files</div>
    </div>
</td>
```

**Stack column:**
```html
<td class="posture-module-cell-stack" data-tooltip>
    python-lib
    <div class="module-tip">
        <div class="tip-title">Stack: python-lib</div>
        <div class="tip-row">Parent: python</div>
        <div class="tip-row">Requires: python ≥ 3.8</div>
        <div class="tip-row">Capabilities: install, lint, format, test, types</div>
    </div>
</td>
```

**Declared column:**
```html
<td class="posture-module-cell-declared" data-tooltip>
    <code>≥3.8</code> <span class="posture-floor-source">stack</span>
    <div class="module-tip">
        <div class="tip-title">Declared floor: ≥3.8</div>
        <div class="tip-section">Source: stack definition (tier 2)</div>
        <div class="tip-row dim">Tier 1 (module config): no pyproject.toml in src/core/</div>
        <div class="tip-row active">Tier 2 (stack requires): python ≥ 3.8 ← USED</div>
        <div class="tip-row dim">Tier 3 (project root): requires-python = ">=3.11"</div>
    </div>
</td>
```

**Deps column:**
```html
<td class="posture-module-cell-deps" data-tooltip>
    ≥3.10
    <div class="module-tip">
        <div class="tip-title">Dependency floor: ≥3.10</div>
        <div class="tip-section">Packages with Python constraints:</div>
        <div class="tip-row">click 8.3.1 → ≥3.10 ← drives floor</div>
        <div class="tip-row">pydantic 2.12 → ≥3.9</div>
        <div class="tip-row">pyyaml 6.0 → ≥3.8</div>
        <div class="tip-muted">12 packages imported, 3 with constraints</div>
    </div>
</td>
```

**Code column:**
```html
<td class="posture-module-cell-code" data-tooltip>
    3.9
    <div class="module-tip">
        <div class="tip-title">Code floor: 3.9</div>
        <div class="tip-section">Features detected:</div>
        <div class="tip-row">3.9 — runtime list[X] in builders/__init__.py:24</div>
        <div class="tip-row">3.8 — walrus := in helm_generate.py:369</div>
        <div class="tip-row">3.6 — f-strings in peek.py:47</div>
        <div class="tip-muted">582 files scanned. 480 use __future__ annotations.</div>
    </div>
</td>
```

**Effective column:**
```html
<td class="posture-module-cell-effective" data-tooltip>
    <code>≥3.10</code>
    <div class="module-tip">
        <div class="tip-title">Effective floor: ≥3.10</div>
        <div class="tip-section">Highest of all three:</div>
        <div class="tip-row dim">Declared: 3.8 (from stack)</div>
        <div class="tip-row dim">Code: 3.9 (runtime generics)</div>
        <div class="tip-row active">Deps: 3.10 (click) ← highest</div>
        <div class="tip-muted">This module needs Python 3.10+ to run.</div>
    </div>
</td>
```

**Compat column:**
```html
<td class="posture-module-cell-compat" data-tooltip>
    ████░░░░ 4v
    <div class="module-tip">
        <div class="tip-title">Compatibility: 4 versions</div>
        <div class="tip-section">Range: 3.10 — 3.13</div>
        <div class="tip-row">3.10 ✓ supported (EOL Oct 2026)</div>
        <div class="tip-row">3.11 ✓ supported (EOL Oct 2027)</div>
        <div class="tip-row">3.12 ✓ supported (EOL Oct 2028)</div>
        <div class="tip-row">3.13 ✓ current</div>
    </div>
</td>
```

**Floor column:**
```html
<td class="posture-module-cell-health" data-tooltip>
    🟢
    <div class="module-tip">
        <div class="tip-title">Floor health: supported</div>
        <div class="tip-row">Effective floor 3.10 receives security patches.</div>
        <div class="tip-row">EOL: October 2026</div>
        <div class="tip-row">No known CVEs.</div>
    </div>
</td>
```

**Status column:**
```html
<td class="posture-module-cell-verdict" data-tooltip>
    ⚠️
    <div class="module-tip module-tip-action">
        <div class="tip-title">⚠️ Gap detected</div>
        <div class="tip-row">Declared ≥3.8 but deps need ≥3.10</div>
        <div class="tip-row">click 8.3.1 requires Python ≥3.10</div>
        <div class="tip-actions">
            <button class="posture-btn" onclick="moduleAcknowledge('core')">📝 Acknowledge</button>
            <button class="posture-btn" onclick="moduleViewReport('core')">📋 Full Report</button>
            <button class="posture-btn" onclick="moduleDismiss('core')">✕ Dismiss</button>
        </div>
    </div>
</td>
```

**Files changed:**
- `_system_posture.html` — rewrite `renderModulePillar()` to embed tooltip divs

### Step 4: Fix Data Accuracy

**Floor health must evaluate EFFECTIVE floor, not declared.**
Currently adapters/cli/web show 🔴 because declared is 3.8 (CVEs).
But effective is 3.9/3.10 which is healthy.
Fix in bridge: `check_floor_health(effective_floor, lifecycle)` not declared.

**Verdict "could_lower" needs context when floor comes from stack.**
"declared 3.8 but nothing needs more than 3.6" is confusing when 3.8 is the
stack baseline. Fix verdict to acknowledge stack source:
"Stack baseline is 3.8. Code only uses 3.6 features. Module is compatible
below the stack baseline."

**Files changed:**
- `bridges/modules.py` — floor health evaluation uses effective
- `module_intel.py` — verdict logic accounts for floor_source

### Step 5: Action Handlers

Implement the click actions from the Status tooltip:

**Acknowledge**: opens modal STACKED on posture modal (`replace: false`).
Textarea for version_note. Writes to project.yml via new API endpoint.
```javascript
window.moduleAcknowledge = function(moduleName) {
    modalOpen({
        title: '📝 Acknowledge: ' + moduleName,
        replace: false,  // CRITICAL: stack on posture modal, don't replace it
        body: modalFormField({
            name: 'note', label: 'Version Note',
            type: 'textarea', placeholder: 'Explain why this gap is acceptable...',
            hint: 'Saved to project.yml as version_note'
        }),
        footerButtons: [
            { label: '💾 Save', cls: 'btn-primary', onclick: 'moduleSaveNote("' + moduleName + '")' },
            { label: 'Cancel', onclick: 'modalClose()' },
        ],
    });
};
```

**Full Report**: opens modal with all deps, code features, tier analysis.
Pure read — no API call needed, data already in the item.

**Dismiss**: shortcut for acknowledge with "Reviewed — accepted" note.

**API endpoint needed:**
```python
@posture_bp.route("/posture/module-note", methods=["POST"])
def posture_module_note():
    """Update version_note or version_strategy for a module in project.yml."""
    body = request.get_json()
    module_name = body.get("module")
    note = body.get("version_note")
    strategy = body.get("version_strategy")
    # Read project.yml, update the ModuleRef, write back
    ...
```

**Files changed:**
- `_system_posture.html` — action handler functions
- `posture.py` — new endpoint `/posture/module-note`
- `src/core/config/loader.py` or new writer — write back to project.yml

### Step 6: Strategy Interaction

Strategy badges in the strategy row become clickable:
```javascript
// Click on "compat.✱" → dropdown to set strategy explicitly
window.moduleSetStrategy = function(moduleName) {
    modalOpen({
        title: '🎯 Version Strategy: ' + moduleName,
        body:
            modalFormField({
                name: 'strategy', label: 'Strategy',
                type: 'select',
                options: [
                    { value: '', label: '— Let platform deduce' },
                    { value: 'latest', label: 'Latest — track current version' },
                    { value: 'compatibility', label: 'Compatibility — wide range' },
                ],
                hint: 'Controls how the platform evaluates this module'
            }) +
            modalFormField({
                name: 'note', label: 'Note (optional)',
                type: 'textarea', placeholder: 'Why this strategy?',
            }),
        footerButtons: [
            { label: '💾 Save', cls: 'btn-primary', onclick: 'moduleSaveStrategy("' + moduleName + '")' },
            { label: 'Cancel', onclick: 'modalClose()' },
        ],
    });
};
```

Uses same `/posture/module-note` endpoint to write strategy + note.

**Files changed:**
- `_system_posture.html` — strategy click handlers
- Same endpoint handles both note and strategy

### Step 7: Project.yml Writer

Need a function that reads project.yml, updates a ModuleRef's fields,
and writes it back. Must preserve YAML formatting and comments.

```python
def update_module_ref(project_path: Path, module_name: str, **fields):
    """Update fields on a ModuleRef in project.yml.

    Reads the YAML, finds the module by name, updates specified fields,
    writes back. Preserves formatting via round-trip YAML (ruamel.yaml
    if available, fallback to safe_dump).
    """
```

**Files changed:**
- New function in `src/core/config/loader.py` or `src/core/config/writer.py`

### Step 8: Polish

- Tooltip positioning: ensure tooltips don't overflow the modal
  (right-side columns need left-aligned tooltips)
- Tooltip delay: 300ms CSS transition to avoid flicker
- Responsive: tooltips collapse on narrow viewports
- Accessibility: tooltips are focusable for keyboard navigation
- Animations: fade-in on tooltip show

**Files changed:**
- `admin.css` — responsive tooltip rules, animations
- `_system_posture.html` — aria attributes

---

## File Change Summary

```
BACKEND:
  src/ui/web/routes/posture.py
    - Enrichment: pass deps_details, full code_features, floor_tiers, module_meta, stack_meta
    - New endpoint: POST /posture/module-note (write version_note + strategy to project.yml)

  src/core/services/system_posture/bridges/modules.py
    - Floor health evaluates EFFECTIVE floor, not declared

  src/core/services/system_posture/bridges/module_intel.py
    - Verdict accounts for floor_source in explanation

  src/core/config/writer.py (NEW)
    - update_module_ref() — writes to project.yml

FRONTEND:
  src/ui/web/templates/scripts/globals/_system_posture.html
    - renderModulePillar(): embed tooltip divs in every cell
    - Action handlers: moduleAcknowledge(), moduleViewReport(),
      moduleDismiss(), moduleSetStrategy(), moduleSaveNote()

  src/ui/web/static/css/admin.css
    - Tooltip system: .module-tip, .tip-title, .tip-row, .tip-section,
      .tip-muted, .tip-actions, .tip-row.active, .tip-row.dim
    - Animations: @keyframes tipFadeIn
    - Responsive: tooltip positioning for edge columns
```

---

## Execution Order

```
  1. Fix data accuracy (floor health on effective, verdict wording)
  2. Send full data to frontend (deps_details, code_features, tiers, meta)
  3. Build CSS tooltip system
  4. Render tooltips for all 9 columns
  5. Build action handlers (acknowledge, report, dismiss)
  6. Build strategy interaction
  7. Build project.yml writer + API endpoint
  8. Polish (positioning, delay, responsive, accessibility)
```

Each step is one scope. Verify each before moving to next.
