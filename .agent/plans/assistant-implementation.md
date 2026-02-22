# Assistant — Implementation Plan — COMPLETED

> **Status:** ✅ All 6 stages implemented. This document is a **historical
> reference** for the staged implementation approach. For the current
> living architecture, see `assistant-architecture.md`.
>
> Ordered so each stage produces something visible and testable.
> Each stage is broken down further when we get to it.

---

## Stage 1 — Panel on screen

**Goal:** See the assistant panel next to the wizard body with a static
tree rendered. Nothing interactive yet — just visible content.

### Tasks

1. **CSS** — Add `.assistant-layout` (flex container) and `.assistant-panel`
   styles to `admin.css`. Panel width, background, border, scroll, depth
   indentation for nodes.

2. **HTML structure** — Modify `_tab_wizard.html` to wrap `#wizard-body`
   and `#assistant-panel` in `.assistant-layout` flex container.

3. **Engine (minimal)** — Create `_assistant_engine.html` with just enough
   to load the catalogue, find a context by ID, and render the tree into
   the panel. No hover, no events, no matching — just tree rendering.

4. **Include** — Add `{% include %}` for the engine in `dashboard.html`.

5. **Catalogue (stub)** — Create `assistant-catalogue.json` with ONE
   context (`wizard/welcome`) containing ~5 nodes with real content.
   Enough to see the tree structure working.

6. **Hook (one)** — Add `_assistant.activate('wizard/' + stepId, body)`
   in `renderWizard()` so the panel renders when the wizard loads.

### Test

- Open the web UI → wizard tab → step 1
- Panel appears on the right with the tree
- Nodes show titles and content at correct depth

---

## Stage 2 — Interaction

**Goal:** Hover/focus on wizard elements highlights the corresponding
node in the panel. Expand/collapse works.

### Tasks

1. **Selector matching** — Engine reads `selector` from each node,
   tests hovered element against selectors via `element.matches()`.

2. **Flatten tree** — Engine builds a flat array of all nodes with their
   selectors for fast matching.

3. **Event listeners** — Delegated `mouseover` + `focusin` on the
   wizard body container. Debounced (150ms hover, immediate focus).

4. **Expand/collapse** — When a node matches, add `.active` class to
   show `expanded` content. Remove from previous active node.

5. **Scroll sync** — Panel scrolls to bring the active node into view.

### Test

- Hover over `#wiz-name` input → "Project Name" node highlights in panel
- Move to `#wiz-desc` → "Description" node highlights, previous collapses
- Focus an input → same behavior, immediate

---

## Stage 3 — Context switching

**Goal:** Navigating wizard steps loads the correct context. Opening a
modal pushes a new context. Closing pops back.

### Tasks

1. **Context stack** — Engine maintains a stack. `activate()` pushes,
   `deactivate()` pops and restores previous.

2. **Wizard hook** — Already done in Stage 1. Verify it fires on every
   step change (not just step 1).

3. **Modal hooks** — Add `activate()` after `_wizModalRender()` and
   `deactivate()` in `wizardModalClose()` in `_globals_wizard_modal.html`.

4. **Context IDs on modal steps** — Add `contextId` property to K8s and
   Docker wizard step definitions.

5. **More catalogue contexts** — Add `wizard/modules` and at least one
   modal context (e.g. `k8s/detect`) to the catalogue so context
   switching is testable.

### Test

- Switch wizard steps → panel content changes per step
- Open K8s setup modal → panel shows K8s detect context
- Close modal → panel returns to wizard integrations context

---

## Stage 4 — Settings + polish

**Goal:** User can toggle the assistant on/off. Dynamic content resolvers
work. Panel handles edge cases gracefully.

### Tasks

1. **Settings toggle** — Add `assistantGuide` pref (default: false),
   toggle UI in `_renderSettingsPanel()`, setter function.

2. **Enable/disable** — Engine `enable()` / `disable()` show/hide panel,
   attach/detach listeners.

3. **Template resolvers** — Register resolvers for `{{envCount}}`,
   `{{domainCount}}`, etc. Verify against live DOM.

4. **Dynamic children** — Engine handles `dynamic: true` nodes —
   queries DOM for child elements, renders from `childTemplate`.

5. **Error handling** — Catalogue 404, missing context, unmatched
   selectors — all fail silently with console warnings.

### Test

- Settings → toggle assistant off → panel disappears
- Toggle on → panel reappears with correct context
- `{{envCount}}` resolves to actual count in content

---

## Stage 5 — Content authoring

**Goal:** All wizard + integrations contexts authored with real content.

### Tasks

1. Author remaining wizard contexts: `wizard/secrets`, `wizard/content`,
   `wizard/integrations`, `wizard/review` — reading from actual HTML.

2. Author modal contexts: `k8s/configure`, `k8s/review`,
   `docker/detect`, `docker/configure`, `docker/preview`.

3. Author `integrations` tab context.

4. Review and verify every selector against live DOM.

5. Add `data-assist` attributes only where no selector works.

### Test

- Every wizard step has panel content
- Every modal step has panel content
- Hovering any element with a selector → correct node activates

---

## Stage 6 — Modal panel injection

**Goal:** Panel works inside modals (not just the wizard tab).

### Tasks

1. **Panel resolution** — Engine detects whether container is wizard
   body or modal body and injects panel accordingly.

2. **Modal flex layout** — Dynamically wrap `.wiz-step-body` content
   in `.assistant-layout` when a modal context activates.

3. **Cleanup** — Remove injected layout when modal closes.

### Test

- Open K8s wizard → panel appears inside modal
- Navigate modal steps → panel updates
- Close modal → no leftover DOM artifacts

---

## Order rationale

Stage 1 first because nothing else matters if you can't see it.
Stage 2 next because interaction is the core value.
Stage 3 because multi-context is needed before authoring more content.
Stage 4 before Stage 5 because settings/resolvers affect content display.
Stage 5 is the bulk content work — iterative, one context at a time.
Stage 6 last because modal injection is the most complex DOM manipulation.
