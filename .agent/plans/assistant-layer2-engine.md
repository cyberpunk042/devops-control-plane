# Layer 2 — Engine (Core Logic)

> The runtime that loads superstructure JSON, renders the assistant panel,
> and manages context switching. A single JS file (~300 lines).

---

## What this layer IS

A single JavaScript file (`_assistant_engine.html`) included via Jinja2 in
`dashboard.html`. It provides the `window._assistant` public API and contains
all engine logic as closure-private functions inside one IIFE.

The engine is **domain-agnostic** — it knows nothing about Docker, K8s,
environments, or any specific UI. All domain knowledge lives in the JSON
superstructure (L1). The engine just renders trees and matches selectors.

---

## Analysis — What exists today

### Existing guide system

There is an existing "guide" system:
- `_guide_catalogue_wizard.html` — 481 lines of `guideRegister()` calls
- Uses: `onEnter`, `onFocus`, `onInput`, `onHover`, `onIdle` events
- Provides tooltip-style messages per element

**This is the OLD approach.** It will be replaced by the superstructure
approach. The existing guide catalogue contains useful content that can be
migrated to JSON files, but the engine and registration mechanism are replaced.

### Relevant DOM structure

**Wizard tab:**
```html
<div id="tab-wizard" class="tab-content">
    <header class="tab-header">...</header>
    <div class="wizard-steps" id="wizard-steps">...</div>
    <div class="wizard-content">
        <div class="card full-width">
            <div id="wizard-body">...</div>       ← content rendered here
            <div class="wizard-nav">...</div>
        </div>
    </div>
</div>
```

The assistant panel needs to sit NEXT TO `wizard-body`, inside
`.wizard-content > .card.full-width`. This means modifying
`_tab_wizard.html` to add a flex layout.

**Modal (K8s/Docker setup):**
```html
<div class="modal-overlay">
    <div class="modal-box">
        <div class="modal-header">...</div>
        <div class="modal-body">
            <div class="wiz-modal-steps">...</div>
            <div class="wiz-step-body">...</div>   ← content rendered here
            <div class="wiz-step-error">...</div>
        </div>
        <div class="modal-footer">...</div>
    </div>
</div>
```

For modals, the panel sits NEXT TO `.wiz-step-body`, inside `.modal-body`.

### Wizard step lifecycle

```javascript
renderWizard() {
    const stepId = wizardSteps[currentWizardStep].id;
    // Renders step indicators
    // Clears wizard-body
    // Calls _wizardRenderers[stepId](body)
}
```

**Hook point:** After `renderFn(body)` completes, call
`_assistant.activate('wizard/' + stepId, body)`.

### Modal step lifecycle

```javascript
wizardModalOpen(opts) {
    // Creates modal shell with wiz-step-body
    // Calls _wizModalRender() for first step
}
```

**Hook point:** After `_wizModalRender()`, call
`_assistant.activate(contextId, stepBody)`.

---

## Design Decisions

### 1. File location and inclusion

**Decision:** `src/ui/web/templates/scripts/_assistant_engine.html`

Included in dashboard.html via `{% include 'scripts/_assistant_engine.html' %}`
inside a `<script>` tag (same pattern as other template scripts).

### 2. Panel injection strategy

**Problem:** The panel needs to live inside the same scroll container as the
content (for wizard) or have synced scroll (for modals).

**Decision — Wizard:**
Modify `_tab_wizard.html` to wrap `#wizard-body` in a flex container:

```html
<div class="card full-width">
    <div class="assistant-layout">
        <div id="wizard-body"></div>
        <div id="assistant-panel" class="assistant-panel"></div>
    </div>
    <div class="wizard-nav">...</div>
</div>
```

Both `#wizard-body` and `#assistant-panel` scroll together inside the card.

**Decision — Modals:**
Inject the panel into `.modal-body` dynamically when a modal context is
activated. The engine creates the panel div and appends it.

### 3. Catalogue loading strategy

**Decision:** Fetch the single catalogue file once, index by context ID.

```javascript
let _catalogue = null;  // Map<contextId, AssistantContext>

async function _loadCatalogue() {
    if (_catalogue) return _catalogue;

    const resp = await fetch('/static/data/assistant-catalogue.json');
    if (!resp.ok) return null;

    const data = await resp.json();
    _catalogue = new Map();
    for (const ctx of data) {
        _catalogue.set(ctx.context, ctx);
    }
    return _catalogue;
}

function _getContext(contextId) {
    return _catalogue?.get(contextId) || null;
}
```

Single fetch on first use. All contexts available after that.
No per-context lazy loading — the catalogue is one file.

### 4. Context stack (modal over wizard)

**Decision:** A simple array stack.

```javascript
const _contextStack = [];

function activate(contextId, containerEl) {
    _contextStack.push({ contextId, containerEl });
    _loadAndRender(contextId, containerEl);
}

function deactivate() {
    _contextStack.pop();
    const prev = _contextStack[_contextStack.length - 1];
    if (prev) {
        _loadAndRender(prev.contextId, prev.containerEl);
    } else {
        _clearPanel();
    }
}
```

When K8s modal opens: push `k8s/detect`. When modal closes: pop, restore
`wizard/integrations`.

### 5. Panel target — wizard vs modal

**Problem:** The wizard panel is a static element in _tab_wizard.html.
The modal panel is dynamically injected. They're different DOM locations.

**Decision:** The engine manages a `_panelEl` reference. On activate:
- If container is `#wizard-body` → use `#assistant-panel` (static sibling)
- If container is `.wiz-step-body` → create/find `#assistant-panel-modal`
  inside `.modal-body`

```javascript
function _resolvePanelEl(containerEl) {
    // Wizard context — static panel
    if (containerEl.id === 'wizard-body') {
        return document.getElementById('assistant-panel');
    }
    // Modal context — create/reuse dynamic panel
    const modalBody = containerEl.closest('.modal-body');
    if (modalBody) {
        let panel = modalBody.querySelector('.assistant-panel');
        if (!panel) {
            panel = document.createElement('div');
            panel.className = 'assistant-panel';
            // Wrap existing content in flex layout
            const wrapper = document.createElement('div');
            wrapper.className = 'assistant-layout';
            while (modalBody.firstChild) {
                wrapper.appendChild(modalBody.firstChild);
            }
            modalBody.appendChild(wrapper);
            wrapper.appendChild(panel);
        }
        return panel;
    }
    return null;
}
```

### 6. Tree rendering

**Decision:** Event-driven rendering. On context activation, only the
step context header is rendered. On hover/focus, the engine walks up
the tree from the matched node, collects the parent chain, and renders
only those nodes.

```javascript
function _renderContextHeader(tree, panelEl) {
    panelEl.innerHTML = '';

    // Render context header (always visible on this context)
    const header = document.createElement('div');
    header.className = 'assistant-context-header';
    header.innerHTML = `
        <div class="assistant-context-title">
            ${tree.icon || ''} ${tree.title}
        </div>
        <div class="assistant-context-content">
            ${_resolve(tree.content)}
        </div>
    `;
    panelEl.appendChild(header);
}

function _renderInteractionPath(panelEl) {
    // Clear everything below context header
    const header = panelEl.querySelector('.assistant-context-header');
    while (header.nextSibling) header.nextSibling.remove();

    // Collect nodes to render from focus and hover paths
    const pathNodes = _mergeInteractionPaths(_focusPath, _hoverPath);

    // Render each node in order (parent → child)
    for (const { node, depth } of pathNodes) {
        _renderNode(node, depth, panelEl);
    }
}

function _renderNode(node, depth, panelEl) {
    // Separator
    if (node.separator) {
        const sep = document.createElement('hr');
        sep.className = 'assistant-separator';
        panelEl.appendChild(sep);
    }

    const div = document.createElement('div');
    div.className = 'assistant-node';
    div.dataset.nodeId = node.id;
    div.dataset.depth = depth;
    div.style.paddingLeft = (depth * 16) + 'px';

    // Title
    const titleEl = document.createElement('div');
    titleEl.className = 'assistant-node-title';
    titleEl.textContent = (node.icon ? node.icon + ' ' : '') + node.title;
    div.appendChild(titleEl);

    // Content
    const contentEl = document.createElement('div');
    contentEl.className = 'assistant-node-content';
    contentEl.innerHTML = _resolve(node.content);
    div.appendChild(contentEl);

    // Expanded content (only for the actively targeted leaf node)
    if (node.expanded && node._isActiveTarget) {
        const expandedEl = document.createElement('div');
        expandedEl.className = 'assistant-node-expanded';
        expandedEl.innerHTML = _resolve(node.expanded);
        div.appendChild(expandedEl);
    }

    panelEl.appendChild(div);

    // Does NOT recurse children — only interaction path nodes are rendered
}
```

The engine does NOT render the full tree. Only nodes on the interaction
path(s) are rendered. Focus and hover paths are merged — shared parents
appear once.

### 7. Dynamic children

For nodes with `dynamic: true`, the engine queries the DOM and creates
synthetic child nodes:

```javascript
function _renderDynamicChildren(parentNode, depth, panelEl) {
    const tpl = parentNode.childTemplate;
    const elements = document.querySelectorAll(tpl.selector);

    elements.forEach((el, i) => {
        const name = el.querySelector('[style*="font-weight:600"]')?.textContent?.trim()
                  || el.textContent?.trim()?.substring(0, 30)
                  || `Item ${i + 1}`;

        const syntheticNode = {
            id: `${parentNode.id}-dyn-${i}`,
            title: tpl.title.replace('{{name}}', name),
            content: tpl.content.replace('{{name}}', name),
            expanded: tpl.expanded?.replace('{{name}}', name),
            selector: null, // matched by parent
            children: []
        };

        // Store reference for hover matching
        syntheticNode._element = el;

        _renderNode(syntheticNode, depth, panelEl);
    });
}
```

### 8. Template resolution

```javascript
function _resolve(text) {
    if (!text) return '';
    return text.replace(/\{\{(\w+)\}\}/g, (match, key) => {
        const resolver = window._assistant.resolvers[key];
        if (resolver) {
            try { return resolver(); }
            catch (e) { console.warn('[assistant] resolver error:', key, e); }
        }
        return ''; // swallow unresolved vars in production
    });
}
```

### 9. Enabled/disabled state

**Decision:** Check `prefsGet('assistantGuide')`. If disabled, the panel
is hidden via CSS and no events are attached.

```javascript
function _isEnabled() {
    return typeof prefsGet === 'function' && prefsGet('assistantGuide');
}
```

The `enable()` / `disable()` methods show/hide the panel and
attach/detach event listeners.

---

## Public API

```javascript
window._assistant = {
    /**
     * Enable the assistant. Shows the panel and attaches listeners.
     */
    enable(),

    /**
     * Disable the assistant. Hides the panel and detaches listeners.
     */
    disable(),

    /**
     * Push a new context onto the stack and render it.
     * @param {string} contextId - e.g. 'wizard/welcome', 'k8s/configure'
     * @param {HTMLElement} containerEl - the DOM container for this context
     */
    activate(contextId, containerEl),

    /**
     * Pop the current context and restore the previous one.
     */
    deactivate(),

    /**
     * Re-render the current context (after DOM changes).
     */
    refresh(),

    /**
     * Template variable resolvers.
     * Register: _assistant.resolvers.envCount = () => ...
     */
    resolvers: {}
};
```

---

## Context lookup

The engine loads the single `assistant-catalogue.json` file on first use,
then looks up contexts by ID from the in-memory `Map`.

No file mapping needed — context IDs are the keys directly.

---

## Full engine structure (pseudocode)

```javascript
// _assistant_engine.html
(function() {
    'use strict';

    // ── State ───────────────────────────────────────────────
    let _catalogue = null;          // Map<contextId, context>
    const _contextStack = [];       // [{contextId, containerEl}]
    let _panelEl = null;            // current panel DOM element
    let _currentTree = null;        // current rendered tree
    let _flatNodes = null;          // flattened for matching
    let _activeNodeId = null;       // currently expanded node
    let _hoverTimer = null;         // debounce timer
    let _listeners = [];            // attached event listeners (for cleanup)

    // ── Catalogue Loading ───────────────────────────────────
    async function _loadCatalogue() { ... }
    function _getContext(contextId) { ... }

    // ── Panel Resolution ────────────────────────────────────
    function _resolvePanelEl(containerEl) { ... }

    // ── Tree Rendering ──────────────────────────────────────
    function _renderContextHeader(tree, panelEl) { ... }
    function _renderInteractionPath(panelEl) { ... }
    function _renderNode(node, depth, panelEl) { ... }
    function _renderDynamicChildren(parentNode, depth, panelEl) { ... }

    // ── Template Resolution ─────────────────────────────────
    function _resolve(text) { ... }

    // ── Node Matching ───────────────────────────────────────
    function _flattenTree(tree) { ... }
    function _matchNode(element) { ... }
    function _collectPath(node) { ... }  // walks up parent chain
    function _mergeInteractionPaths(focusPath, hoverPath) { ... }

    // ── Event Handling ──────────────────────────────────────
    function _attachListeners(containerEl) { ... }
    function _detachListeners() { ... }
    function _onHover(e) { ... }   // sets _hoverPath, re-renders
    function _onFocus(e) { ... }   // sets _focusPath, re-renders
    function _onBlur(e) { ... }    // clears _focusPath, re-renders

    // ── Core ────────────────────────────────────────────────
    async function _loadAndRender(contextId, containerEl) {
        await _loadCatalogue();
        const tree = _getContext(contextId);
        if (!tree) return;

        _currentTree = tree;
        _panelEl = _resolvePanelEl(containerEl);
        if (!_panelEl) return;

        _renderContextHeader(tree, _panelEl);
        _flatNodes = _flattenTree(tree);
        _focusPath = null;
        _hoverPath = null;

        _detachListeners();
        _attachListeners(containerEl);
    }

    function _clearPanel() {
        if (_panelEl) _panelEl.innerHTML = '';
        _detachListeners();
        _currentTree = null;
        _flatNodes = null;
        _activeNodeId = null;
    }

    // ── Public API ──────────────────────────────────────────
    window._assistant = {
        resolvers: {},

        enable() {
            const panel = document.getElementById('assistant-panel');
            if (panel) panel.style.display = '';
            // Re-render if there's a current context
            const ctx = _contextStack[_contextStack.length - 1];
            if (ctx) _loadAndRender(ctx.contextId, ctx.containerEl);
        },

        disable() {
            const panel = document.getElementById('assistant-panel');
            if (panel) panel.style.display = 'none';
            _detachListeners();
        },

        activate(contextId, containerEl) {
            if (!_isEnabled()) return;
            _contextStack.push({ contextId, containerEl });
            _loadAndRender(contextId, containerEl);
        },

        deactivate() {
            _contextStack.pop();
            const prev = _contextStack[_contextStack.length - 1];
            if (prev && _isEnabled()) {
                _loadAndRender(prev.contextId, prev.containerEl);
            } else {
                _clearPanel();
            }
        },

        refresh() {
            const ctx = _contextStack[_contextStack.length - 1];
            if (ctx && _isEnabled()) {
                _loadAndRender(ctx.contextId, ctx.containerEl);
            }
        }
    };
})();
```

---

## Integration points (where hooks go)

These are the EXACT locations where existing code calls into the engine.
The actual hook code is minimal — L4 (Integration) handles implementation.

| Location | Event | Call |
|----------|-------|------|
| `renderWizard()` in `_wizard_init.html` | Wizard step rendered | `_assistant.activate('wizard/' + stepId, body)` |
| `_wizModalRender()` in `_globals_wizard_modal.html` | Modal step rendered | `_assistant.activate(contextId, stepBody)` |
| `wizardModalClose()` | Modal closed | `_assistant.deactivate()` |
| `_prefSetAssistantGuide()` in `_settings.html` | Toggle | `_assistant.enable()` / `.disable()` |

---

## Error handling

| Situation | Behavior |
|-----------|----------|
| Catalogue file not found (404) | Panel shows nothing. Console warning. |
| JSON parse error | Panel shows nothing. Console error. |
| Context ID not in catalogue | Panel shows nothing. Console debug. |
| Selector matches nothing | Node renders in panel without hover highlight. Console debug. |
| Resolver throws | Returns empty string. Console warning. |
| Container element missing | No panel injected. Console warning. |
| Assistant disabled | All activate/refresh calls are no-ops. |

---

## Performance considerations

| Concern | Approach |
|---------|----------|
| Catalogue file size | Single file, ~50-100KB. One fetch, cached. Negligible. |
| DOM creation | `_renderTree()` creates ~20-50 nodes. Negligible. |
| Flat tree creation | One-time cost per context switch. Cached in `_flatNodes`. |
| Context lookup | `Map.get()` — O(1). |
| Selector matching | `element.matches()` is fast. ~20-50 checks per hover event. |
| Debounce | Hover: 150ms. Focus: immediate. Prevents rapid re-matching. |
| Event listeners | Delegated on container. One `mouseover` + one `focusin`. |

---

## Implementation tasks

1. **Create `_assistant_engine.html`** — the full IIFE with all functions
2. **Modify `_tab_wizard.html`** — add `.assistant-layout` flex wrapper
3. **Add `{% include %}` in dashboard** — load engine script
4. **Register resolvers** — create resolver definitions (can be inline in engine or separate)
5. **Test with catalogue** — load `assistant-catalogue.json` and verify panel renders

Tasks 1-3 are the core. Task 4 can happen incrementally as contexts are authored.
Task 5 requires L1 to have at least one context in the catalogue.

---

## Dependencies

| Depends on | For |
|------------|-----|
| L1 (Data) | `assistant-catalogue.json` with contexts |
| L3 (Presentation) | CSS for panel styling, node indentation |
| L4 (Integration) | Hook calls from wizard/modal lifecycle |

Can be built in parallel with L1 — test with a hardcoded tree object
before the catalogue is ready.
