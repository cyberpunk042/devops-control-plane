# Assistant — Modal Integration Plan

> **Status:** 🔲 Not started
> **Created:** 2026-02-22
> **Depends on:** assistant-architecture.md (living reference)
>
> **What this is:** Implementation plan to bring the assistant panel into the
> Full Setup Modal system. The unified plan's Phase 4 ("Modal Contexts") was
> marked complete but never implemented. This plan covers the real work.

---

## Current State

**What works today:**
- The wizard tab has an `assistant-layout` flex container holding `#wizard-body` + `#assistant-panel` side by side.
- `_wizard_init.html` calls `_assistant.activate('wizard/' + stepId, body)` on each wizard step.
- The engine listens for hover/focus on the `containerEl` and renders matching catalogue entries in the panel.
- The integration cards on wizard step 5 are fully catalogued (git, github, pages, docker, k8s, terraform, dns-cdn, cicd).

**What doesn't work:**
- When you click "🚀 Full Setup →" on any card, `wizardModalOpen()` opens a modal overlay via `modalOpen()`.
- The modal is appended to `document.body` — outside `#wizard-body`.
- The modal contains no assistant panel element.
- No `_assistant.activate()` is ever called for the modal.
- The assistant panel behind the modal is visually covered by the overlay backdrop.
- **Result: the assistant is 100% absent from all 7 setup wizards.**

---

## Implementation — 3 Phases

### Phase A: Modal Infrastructure

The modal system needs to support an assistant panel. This is pure infrastructure — no catalogue content yet.

#### A1. `_globals_wizard_modal.html` — Add panel to modal body

`wizardModalOpen()` currently builds:
```html
<div class="wiz-modal-steps" id="wiz-modal-steps"></div>
<div class="wiz-step-body" id="wiz-step-body"></div>
<div class="wiz-step-error" id="wiz-step-error"></div>
```

Change to:
```html
<div class="assistant-layout wiz-modal-layout">
  <div class="wiz-modal-main">
    <div class="wiz-modal-steps" id="wiz-modal-steps"></div>
    <div class="wiz-step-body" id="wiz-step-body"></div>
    <div class="wiz-step-error" id="wiz-step-error"></div>
  </div>
  <div id="assistant-panel-modal" class="assistant-panel assistant-panel-modal"></div>
</div>
```

The panel gets its own ID (`assistant-panel-modal`) to avoid conflicting with `#assistant-panel` in the wizard tab.

#### A2. `_globals_wizard_modal.html` — Activate assistant on open, restore on close

In `wizardModalOpen()`, after `_wizModalRender()`:
```javascript
// Activate assistant for modal context
if (window._assistant) {
    const contextId = opts.assistantContext || null;
    if (contextId) {
        const modalMain = document.querySelector('.wiz-modal-main');
        const modalPanel = document.getElementById('assistant-panel-modal');
        window._assistant.activate(contextId, modalMain, modalPanel);
    }
}
```

In `wizardModalClose()`:
```javascript
// Re-activate the wizard context the modal was opened from
if (window._assistant) {
    const wizBody = document.getElementById('wizard-body');
    if (wizBody) {
        const stepId = wizardSteps[currentWizardStep].id;
        window._assistant.activate('wizard/' + stepId, wizBody);
    }
}
```

#### A3. `_globals_wizard_modal.html` — Refresh assistant on step transition

In `_wizModalRender()`, after `step.render(data, bodyEl)` completes:
```javascript
if (window._assistant) window._assistant.refresh();
```

This re-flattens the tree and re-matches selectors against the new step's DOM.

#### A4. `_assistant_engine.html` — Accept optional panel element

Current `activate()` signature:
```javascript
async function activate(contextId, containerEl)
```

Change to:
```javascript
async function activate(contextId, containerEl, panelEl)
```

Update `_resolvePanel()` logic:
- If `panelEl` is provided, use it directly.
- Otherwise, fall back to `document.getElementById('assistant-panel')`.

Store the provided panelEl in `_panelEl` directly in `activate()`.

#### A5. `_globals.html` + `admin.css` — New modal size class

Add `.modal-box.assisted` CSS class:
```css
.modal-box.assisted {
    max-width: 1180px;
}
```

When `wizardModalOpen()` detects an `assistantContext` in opts, it passes `size: 'assisted'` to `modalOpen()` instead of `'wide'`.

#### A6. `admin.css` — Modal-scoped panel styling

The assistant panel inside a modal can't use `position: sticky` or `height: calc(100vh - 8rem)` — it needs to be constrained to the modal box's height.

```css
.assistant-panel-modal {
    position: relative;         /* not sticky — modal doesn't scroll the page */
    height: auto;               /* grows with content */
    max-height: calc(100vh - 12rem);  /* bounded by modal viewport */
    width: 300px;               /* slightly narrower than wizard panel */
}
```

The `.wiz-modal-main` wrapper gets:
```css
.wiz-modal-main {
    flex: 1;
    min-width: 0;
    overflow-y: auto;
}
```

#### A7. Each setup wizard — Pass `assistantContext` to `wizardModalOpen()`

Each of the 7 setup wizard functions calls `wizardModalOpen()`. Add `assistantContext` to their opts:

| Wizard | File | `assistantContext` value |
|--------|------|------------------------|
| Git | `_integrations_setup_git.html` | `'setup/git'` |
| GitHub | `_integrations_setup_github.html` | `'setup/github'` |
| Docker | `_integrations_setup_docker.html` | `'setup/docker'` |
| K8s | `_integrations_setup_k8s.html` | `'setup/k8s'` |
| Terraform | `_integrations_setup_terraform.html` | `'setup/terraform'` |
| CI/CD | `_integrations_setup_cicd.html` | `'setup/cicd'` |
| DNS | `_integrations_setup_dns.html` | `'setup/dns'` |

Each call is a one-line addition: `assistantContext: 'setup/docker',` in the opts object.

---

### Phase B: Catalogue Structure + First Wizard

Create the catalogue entries. Start with one wizard end-to-end to validate the infrastructure, then do the rest.

#### B1. Pick the first wizard

**Git** — simplest (3 steps, 494 lines, no sub-files). Proves the pattern with minimal risk.

Steps: `detect` → `config` → `review`

#### B2. Add IDs to Git Setup Wizard elements

Read `_integrations_setup_git.html` step by step. For every rendered element (status rows, form fields, buttons, detection results), add an `id` attribute.

Form fields already get `mf-{name}` IDs from `modalFormField()` — those are free.
`wizStatusRow()` and custom HTML need IDs added.

#### B3. Create `setup/git` catalogue context

Add to `assistant-catalogue.json`:
```json
{
  "context": "setup/git",
  "title": "🔀 Git Setup",
  "content": "...",
  "children": [
    {
      "id": "git-detect",
      "title": "Detect",
      "children": [ /* status rows */ ]
    },
    {
      "id": "git-config",
      "title": "Configure",
      "children": [ /* form fields */ ]
    },
    {
      "id": "git-review",
      "title": "Review",
      "children": [ /* review items */ ]
    }
  ]
}
```

#### B4. Test end-to-end

1. Open wizard → go to Integrations step → assistant works on cards ✓
2. Click "🚀 Full Setup →" on Git card → modal opens with assistant panel
3. Hover elements in Detect step → assistant shows matching content
4. Click Next → Configure step renders → assistant refreshes
5. Hover form fields → assistant shows field-level content
6. Close modal → assistant returns to wizard/integrations context

---

### Phase C: Remaining 6 Wizards

Same pattern as B2–B3, repeated for each:

| Order | Wizard | Steps | Estimated Catalogue Entries |
|-------|--------|-------|---------------------------|
| C1 | GitHub | detect → config → review | ~20–30 (env/secret tables) |
| C2 | Docker | detect → config → preview | ~25–35 (per-module config) |
| C3 | CI/CD | detect → pipeline → deploy → envs → review | ~40–60 (largest wizard) |
| C4 | K8s | detect → config (6 sub-parts) → review | ~50–70 (most complex) |
| C5 | Terraform | detect → provider → resources → envs → review | ~30–40 |
| C6 | DNS | detect → domain → cdn → routing → review | ~25–35 |

Order is deliberate: GitHub and Docker are simpler, CI/CD and K8s are the heaviest.

Each wizard follows the same steps:
1. Read the wizard file, identify all rendered elements per step
2. Add IDs where missing
3. Add resolvers if needed for dynamic state
4. Write catalogue entries with content, variants, and expanded views
5. Verify hover works on each step

---

## Files Modified — Summary

| File | Phase | Change |
|------|-------|--------|
| `_globals_wizard_modal.html` | A1, A2, A3 | Assistant panel in modal body, activate/deactivate/refresh calls |
| `_assistant_engine.html` | A4 | `activate()` accepts optional `panelEl` param |
| `_globals.html` | A5 | Add `.modal-box.assisted` to `modalOpen()` size handling |
| `admin.css` | A5, A6 | `.modal-box.assisted` width, `.assistant-panel-modal` styling, `.wiz-modal-main` |
| `_integrations_setup_git.html` | A7, B2 | `assistantContext` + IDs |
| `_integrations_setup_github.html` | A7, C1 | `assistantContext` + IDs |
| `_integrations_setup_docker.html` | A7, C2 | `assistantContext` + IDs |
| `_integrations_setup_cicd.html` | A7, C3 | `assistantContext` + IDs |
| `_integrations_setup_k8s.html` | A7, C4 | `assistantContext` + IDs |
| `_integrations_setup_terraform.html` | A7, C5 | `assistantContext` + IDs |
| `_integrations_setup_dns.html` | A7, C6 | `assistantContext` + IDs |
| `assistant-catalogue.json` | B3, C1–C6 | 7 new context entries |

---

## Assumptions

1. The `modalOpen()` function in `_globals.html` already supports arbitrary `size` classes via string — no change needed to the function logic, just a new CSS class.
2. `modalFormField()` generates `id="mf-{name}"` — these are already usable as selectors.
3. The assistant engine's `refresh()` function re-flattens `_flatNodes` from the current context tree, which means it will re-match selectors against whatever DOM is currently in `#wiz-step-body`. No step-level context switching needed — the same context tree covers all steps, and selector matching handles which entries are visible.
4. `wizStatusRow()` and `wizSection()` in `_globals_wizard_modal.html` need optional `id` parameters (same pattern as `_pill` and `_connRow` in the cards).

---

## Not In Scope

- **Context stack** — the unified plan mentions a context stack for nested modals. We don't need it. Setup modals don't nest. `activate()` on open, `activate()` back to wizard on close.
- **Step-level context IDs** — a single context per wizard (e.g., `setup/docker`) covers all steps. The engine matches selectors against live DOM, so only the current step's elements match. No need for `setup/docker/detect` vs `setup/docker/config`.
- **Docker/K8s sub-files** — the Jinja `{% include %}` files are inlined at render time. IDs go in the sub-files, catalogue entries reference the same selectors. No architectural difference.
