# Layer 5 — Integration (Hooks + Resolvers)

> Thin glue code in existing templates that connects the application
> lifecycle to the assistant engine. Also defines resolver functions
> for dynamic template variables.

---

## What this layer IS

Minimal code additions (1–3 lines each) in existing template files that
call `window._assistant` methods at the right moments. Plus a small
resolver registry that provides runtime data for template variables.

This is NOT a new file — it's modifications to existing files.

---

## Analysis — Hook points identified

### 1. Wizard step render

**File:** `_wizard_init.html` (line ~182)
**Function:** `renderWizard()`
**Current code:**
```javascript
const renderFn = _wizardRenderers[wizardSteps[currentWizardStep].id];
if (renderFn) renderFn(body);
```

**Problem:** `renderFn(body)` may be async (returns a Promise). The
assistant should activate AFTER the content is rendered, not before.

**Hook:**
```javascript
const renderFn = _wizardRenderers[wizardSteps[currentWizardStep].id];
if (renderFn) {
    const result = renderFn(body);
    // Activate assistant after render completes
    if (result && typeof result.then === 'function') {
        result.then(() => {
            if (window._assistant) window._assistant.activate('wizard/' + stepId, body);
        });
    } else {
        if (window._assistant) window._assistant.activate('wizard/' + stepId, body);
    }
}
```

### 2. Modal step render

**File:** `_globals_wizard_modal.html` (line ~130)
**Function:** `_wizModalRender()`
**Current code:**
```javascript
const result = step.render(data, bodyEl);
if (result && typeof result.then === 'function') {
    result.then(() => {
        if (nextBtn) { nextBtn.disabled = false; nextBtn.style.opacity = '1'; }
    })
```

**Problem:** The modal step doesn't have a context ID built in. We need
to derive it from the modal title and step index.

**Solution:** Add a `contextId` property to each step definition. The
K8s wizard steps already include titles — we add context IDs alongside:

```javascript
// In _raw_step1_detect.html
{
    title: 'Detect',
    contextId: 'k8s/detect',  // ← add this
    render: (data, body) => { ... },
    ...
}
```

**Hook (after render resolves):**
```javascript
// After render completes
const ctxId = step.contextId;
if (ctxId && window._assistant) {
    window._assistant.activate(ctxId, bodyEl);
}
```

### 3. Modal close

**File:** `_globals_wizard_modal.html` (line ~281)
**Function:** `wizardModalClose()`
**Current code:**
```javascript
function wizardModalClose() {
    _wizModal = null;
    modalClose();
}
```

**Hook:**
```javascript
function wizardModalClose() {
    if (window._assistant) window._assistant.deactivate();
    _wizModal = null;
    modalClose();
}
```

### 4. Settings toggle

**File:** `_settings.html`
**Function:** `_renderSettingsPanel()`
**Current:** No assistant toggle exists.

**Addition** — add a settings group after "File Preview":

```javascript
// ── Assistant Guide ───────────────────────────────────────
html += `<div class="settings-group">
    <div class="settings-label">Assistant Guide</div>
    <div class="settings-hint">Side panel with context-aware help</div>
    <div class="settings-btn-group">
        <button class="settings-btn ${prefs.assistantGuide ? 'active' : ''}"
            onclick="_prefSetAssistantGuide(true)">✨ On</button>
        <button class="settings-btn ${!prefs.assistantGuide ? 'active' : ''}"
            onclick="_prefSetAssistantGuide(false)">Off</button>
    </div>
</div>`;
```

**Setter function:**
```javascript
function _prefSetAssistantGuide(enabled) {
    prefsSet('assistantGuide', enabled);
    if (window._assistant) {
        enabled ? window._assistant.enable() : window._assistant.disable();
    }
    _renderSettingsPanel();
}
```

**Default:** `assistantGuide: false` in `_PREFS_DEFAULT`. Opt-in.

### 5. Dashboard include

**File:** `dashboard.html` (between line 52 and 53)
**Current:**
```
{% include 'scripts/_wizard.html' %}
```

**Addition:**
```
{% include 'scripts/_wizard.html' %}
{% include 'scripts/_assistant_engine.html' %}
```

The engine must load AFTER `_settings.html` (for `prefsGet`) and AFTER
`_wizard.html` (so wizard functions exist). Placing it right after
`_wizard.html` satisfies both.

### 6. Tab switch

**File:** `_tabs.html`
**Function:** `switchTab(tabId)`

**Concern:** When the user switches away from the wizard tab, should the
assistant deactivate?

**Decision:** No. The assistant panel is inside `#tab-wizard`. When the tab
content is hidden (`display: none`), the panel is hidden with it. No need for
explicit deactivation. When the user returns to the wizard tab, the panel
is still there with its last state.

### 7. Boot — initial wizard render

**File:** `_boot.html` or wherever the initial wizard render is triggered.

The wizard tab renders its first step on page load. The `renderWizard()`
hook (point 1) handles this automatically — no additional boot hook needed.

---

## All modifications — summary

| File | Change | Lines |
|------|--------|-------|
| `_wizard_init.html` | Add `_assistant.activate()` after `renderFn(body)` | +5 |
| `_globals_wizard_modal.html` | Add `_assistant.activate()` after step render | +3 |
| `_globals_wizard_modal.html` | Add `_assistant.deactivate()` in `wizardModalClose()` | +1 |
| `_settings.html` | Add `_PREFS_DEFAULT.assistantGuide = false` | +1 |
| `_settings.html` | Add assistant toggle UI in `_renderSettingsPanel()` | +10 |
| `_settings.html` | Add `_prefSetAssistantGuide()` function | +6 |
| `dashboard.html` | Add `{% include '_assistant_engine.html' %}` | +1 |
| K8s step defs | Add `contextId: 'k8s/detect'` etc. to step objects | +3 |
| Docker step defs | Add `contextId: 'docker/detect'` etc. to step objects | +3 |
| **Total** | | **~33 lines** |

---

## Context ID mapping for modal steps

### K8s wizard

| Step file | Step title | Context ID |
|-----------|-----------|------------|
| `_raw_step1_detect.html` | Detect | `k8s/detect` |
| `_raw_step2_configure.html` (assembled) | Configure | `k8s/configure` |
| `_raw_step3_review.html` | Review | `k8s/review` |

### Docker wizard

| Step file | Step title | Context ID |
|-----------|-----------|------------|
| `_raw_step1_detect.html` | Detect | `docker/detect` |
| `_raw_step2_configure.html` | Configure | `docker/configure` |
| `_raw_step3_preview.html` | Preview | `docker/preview` |

These `contextId` values match the keys in the engine's `CONTEXT_FILES`
mapping and correspond to the JSON file names.

---

## Resolver definitions

Resolvers provide runtime data for `{{variable}}` placeholders in JSON
content strings. They are registered on `window._assistant.resolvers`
after the engine loads.

**Location:** Inside `_assistant_engine.html`, after the IIFE, OR as a
separate small block at the end of the engine file.

### Resolver implementations

```javascript
// ── Resolvers ────────────────────────────────────────────────────
// Registered after engine IIFE. Each reads the current DOM state.

window._assistant.resolvers = {

    // Wizard step 1 — Welcome
    envCount: () => {
        const container = document.getElementById('wiz-envs');
        return container ? container.children.length : 0;
    },

    domainCount: () => {
        const container = document.getElementById('wiz-domains');
        return container ? container.querySelectorAll('span[style*="border-radius:16px"]').length : 0;
    },

    // Wizard step 5 — Integrations
    toolCount: () => {
        const all = document.querySelectorAll('.tool-badge');
        const found = document.querySelectorAll('.tool-badge.found, .tool-badge.success');
        return all.length ? `${found.length} of ${all.length}` : '—';
    },

    // K8s detect
    serviceCount: () => {
        // Count compose services listed in detect results
        const items = document.querySelectorAll('[data-compose-svc]');
        return items.length || 0;
    },

    // K8s configure
    appCount: () => {
        const items = document.querySelectorAll('[data-svc-type="app"]');
        return items.length || 0;
    },

    infraCount: () => {
        const items = document.querySelectorAll('[data-svc-type="infra"]');
        return items.length || 0;
    },
};
```

### Important: resolver selectors may need adjustment

The selectors above are best guesses from the DOM analysis. They must be
verified against the live DOM. If the exact selectors don't exist, we
have two options:
1. Adjust the selectors to match what actually exists
2. Add minimal `data-*` attributes to the templates to make them targetable

**Fallback rule:** If a resolver returns 0 or empty, the template shows
the empty result. The content should still read naturally without the
number (e.g., "You've got some set up so far" vs "You've got 2 set up").

---

## Edge cases

### Engine not loaded yet

All hooks check `if (window._assistant)` before calling methods. If the
engine hasn't loaded (script error, missing include), the hooks are
silent no-ops.

### Async step renders

Both wizard and modal renderers may return Promises. The hooks wait for
render completion before activating the assistant. This ensures the DOM
is ready for selector matching.

### Settings preference not set

`prefsGet('assistantGuide')` returns `undefined` if never set. The engine
treats this as `false` (disabled by default). The user must explicitly
enable it in settings.

### Multiple modals

If a modal opens while another is open (unlikely but possible), the
context stack handles it cleanly — each `activate()` pushes, each
`deactivate()` pops.

---

## Implementation tasks

1. **Modify `_wizard_init.html`** — add assistant hook in `renderWizard()`
2. **Modify `_globals_wizard_modal.html`** — add hooks in `_wizModalRender()` and `wizardModalClose()`
3. **Modify `_settings.html`** — add default pref, toggle UI, setter function
4. **Modify `dashboard.html`** — add engine include
5. **Add `contextId` to K8s step defs** — in `_raw_step1_detect.html` etc.
6. **Add `contextId` to Docker step defs** — in docker wizard step files
7. **Write resolvers** — register on `_assistant.resolvers`
8. **Verify resolvers** — test each against live DOM

---

## Dependencies

| Depends on | For |
|------------|-----|
| L2 (Engine) | `window._assistant` API must exist |
| L1 (Data) | JSON files must exist for context IDs to work |
| Existing templates | Hook points must not have changed |
