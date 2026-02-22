# Assistant — Architecture (Living Document)

> **What this is:** The single source of truth for how the assistant panel
> works *as actually built*. Read this before making any change to the
> engine, catalogue, layout, or content.
>
> **Last updated:** 2026-02-21 (K8s enrichment added)
>
> **Companion docs:**
> - `assistant-realization.md` — what the assistant IS (philosophy)
> - `assistant-scenarios.md` — concrete examples of full panel output
> - `assistant-unified-plan.md` — original design (completed — historical reference)
> - `assistant-secrets-step.md` — wizard/secrets implementation (completed)
> - `assistant-content-step.md` — wizard/content implementation (completed)
> - `assistant-integrations-step.md` — wizard/integrations implementation (completed)

---

## File Map

```
src/ui/web/
├── static/
│   ├── css/admin.css                         # Panel layout + node styling
│   └── data/
│       └── assistant-catalogue.json          # Superstructure — all contexts (~2873 lines)
└── templates/
    ├── scripts/
    │   ├── _assistant_engine.html             # Engine IIFE (~1750 lines)
    │   ├── _wizard_init.html                  # Integration hook (activate on step change)
    │   ├── _wizard_integrations.html          # Renderer (IDs on Docker + K8s section rows)
    │   └── _settings.html                     # Integration hook (enable/disable toggle)
    ├── partials/
    │   └── _tab_wizard.html                   # DOM structure (assistant-layout, panel, wizard-body)
    └── dashboard.html                         # Script inclusion order
```

---

## 1. Layout (CSS)

### DOM Structure

```html
<div class="wizard-content">
  <div class="card full-width">
    <div class="assistant-layout">          <!-- display: flex row -->
      <div id="wizard-body">...</div>       <!-- flex: 1 -->
      <div id="assistant-panel" class="assistant-panel">...</div>  <!-- position: sticky -->
    </div>
    <div class="wizard-nav">...</div>
  </div>
</div>
```

### Key CSS Rules

```css
.assistant-layout {
    display: flex;          /* Side-by-side: wizard-body + panel */
    gap: var(--space-md);
    align-items: flex-start; /* Panel doesn't stretch to match body height */
    min-height: 0;
}

.assistant-layout > #wizard-body {
    flex: 1;
    min-width: 0;
}

.assistant-panel {
    position: sticky;       /* Stays visible as user scrolls the page */
    top: 4rem;              /* Clears the sticky nav bar + breathing room */
    width: 360px;
    flex-shrink: 0;
    height: calc(100vh - 8rem);  /* Viewport-sized, scrolls internally */
    overflow-y: auto;
}
```

### Why `position: sticky` + `align-items: flex-start`

The panel needs to remain visible as the user scrolls the main page (body
scroll). `position: sticky` pins it to the viewport once scrolled past its
natural position. `align-items: flex-start` on the flex container prevents
the panel from stretching to match the wizard-body height — without this,
the panel would be as tall as the content and sticky would have no effect
(the element needs to be shorter than its container to stick).

The `top: 4rem` value clears the sticky `.tabs` navigation bar (~48px)
plus breathing room.

### Wizard Content Width

```css
.wizard-content:has(.assistant-layout) {
    max-width: 1060px;     /* Wider to fit wizard-body + panel */
}
```

---

## 2. Engine Architecture

### File: `_assistant_engine.html`

Single IIFE exposing `window._assistant`. All state is private.

### State Variables

```javascript
var _catalogue = null;      // Map<contextId, contextObject> — loaded once
var _currentCtx = null;     // Active context object
var _panelEl = null;        // #assistant-panel DOM element
var _containerEl = null;    // #wizard-body — event listener target
var _flatNodes = [];        // Flattened tree: [{node, parents[]}, ...]
var _focusPath = null;      // {target: node, chain: [parents]}
var _hoverPath = null;      // {target: node, chain: [parents]}
var _listeners = {};        // Event listener cleanup refs
var _hoverDebounce = null;  // Debounce timer for hover events
var _enabled = true;        // Toggle state
```

### Public API

```javascript
window._assistant = {
    activate(contextId, containerEl),  // Set active context, attach listeners
    deactivate(),                      // Clear context, detach listeners
    refresh(),                         // Re-flatten tree, re-render
    enable(),                          // Show panel
    disable(),                         // Hide panel
    resolvers: {}                      // { varName: () => string }
};
```

### Core Flow

```
activate("wizard/welcome", wizardBody)
  → _loadCatalogue()                    // fetch JSON once, build Map
  → _currentCtx = catalogue.get(id)
  → _panelEl = getElementById("assistant-panel")
  → _flatNodes = _flattenTree(ctx.children, [])
  → _renderEntryState(ctx)             // Show context header centered
  → _attachListeners(containerEl)      // mouseover, focusin, focusout, mouseleave, wheel
```

---

## 3. Tree Flattening & Dynamic Nodes

### `_flattenTree(children, parentChain)`

Recursively flattens the superstructure tree into a flat array ordered
**deepest-first** (children before parents). This ordering ensures specific
selectors match before general ones.

For each node:
1. If `node.dynamic === true` and `node.childTemplate` exists → call `_resolveDynamic()`
2. Recurse into `node.children`
3. Push `{node, parents: [...parentChain]}` to result

### `_resolveDynamic(parentNode, grandParentChain, result)`

Creates synthetic nodes for dynamically generated DOM elements (environment
rows, domain badges, etc.).

**Pattern:**
```javascript
// 1. Query DOM for elements matching childTemplate.selector
var elements = _containerEl.querySelectorAll(tpl.selector);

// 2. Extract display name from each element
//    - Try: el.querySelector('[style*="font-weight:600"]')
//    - Fallback: TreeWalker for first text node
var extractedName = ...;

// 3. Apply {{name}} interpolation to template strings
var nodeTitle = (tpl.title || '').replace(/\{\{name\}\}/g, extractedName);
var nodeContent = (tpl.content || '').replace(/\{\{name\}\}/g, extractedName);
var nodeExpanded = tpl.expanded
    ? tpl.expanded.replace(/\{\{name\}\}/g, extractedName)
    : undefined;

// 4. Context-aware enrichment (e.g., detect "default" badge)
//    Read DOM attributes/elements to append contextual information
var defaultBadge = el.querySelector('[style*="accent-glow"]');
if (defaultBadge && defaultBadge.textContent.trim().toLowerCase() === 'default') {
    nodeTitle += ' · default';
    nodeExpanded += '\n\nAs the default environment, it will be pre-selected...';
}

// 5. Create synthetic node with _element reference for matching
var syntheticNode = {
    id: parentNode.id + '-dyn-' + i,
    title: nodeTitle,
    content: nodeContent,
    expanded: nodeExpanded,
    selector: null,         // Dynamic nodes don't use CSS selectors
    _element: el,           // Direct DOM reference for matching
    _isDynamic: true,
    children: []
};
```

**Critical: variable naming.** The extracted text MUST be named `extractedName`
(not `name`) to avoid shadowing `_resolve()`'s regex callback parameter.

### Catalogue Schema for Dynamic Nodes

```json
{
  "id": "environments",
  "dynamic": true,
  "childTemplate": {
    "title": "{{name}}",
    "content": "The {{name}} environment — one of your deployment targets...",
    "expanded": "When you define secrets and variables in Step 3...",
    "selector": "#wiz-envs > div"
  },
  "children": [
    { "id": "add-env-name", ... }
  ]
}
```

The `childTemplate` is a template that gets instantiated for EACH DOM element
matching `childTemplate.selector`. The `{{name}}` placeholder gets replaced
with text extracted from each element.

#### `nameSelector` (optional)

By default, the engine extracts the display name from the first element matching
`[style*="font-weight:600"]` or `<strong>`, then falls back to the first text
node. Some DOM structures (like vault rows or secret file rows) have an icon as
the first text and the actual name inside a `<code>` element.

`nameSelector` lets the catalogue override this:
```json
"childTemplate": {
    "nameSelector": "code",
    ...
}
```
The engine queries `el.querySelector(nameSelector)` first. If found, its
`textContent` becomes `{{name}}`.

### State-Variant Resolution

A node (or `childTemplate`) can carry a `variants` array. Each variant has a
`when` condition checked against the matched DOM element. The engine evaluates
variants in order and picks the **first match**. No match → base content.

#### Schema

```json
{
    "id": "gh-integration",
    "selector": "#wiz-gh-integration",
    "content": "Fallback content if no variant matches.",
    "variants": [
        {
            "when": { "textContains": "configured" },
            "content": "Your GitHub repository is set in .env...",
            "expanded": "This value stays local..."
        },
        {
            "when": { "textContains": "detected" },
            "content": "Your git remote was auto-detected..."
        }
    ]
}
```

#### Supported `when` Conditions

| Condition | Meaning |
|-----------|--------|
| `textContains` | `element.textContent.toLowerCase().includes(val)` |
| `hasSelector` | `!!element.querySelector(val)` |

Conditions are AND'd — if both are specified, both must match.

#### Engine Functions

- **`_resolveVariant(node, element)`** — evaluates variants against the DOM
  element, returns a new node object with merged fields. Tracks `_variantIndex`.
- **`_resolveStaticVariant(node)`** — for rendering. Finds the DOM element via
  `node.selector` or `node._element`, then calls `_resolveVariant`.

#### Integration Points

1. **Dynamic nodes** — in `_resolveDynamic()`, after creating the synthetic node.
   `childTemplate.variants` are copied to the node, resolved against the DOM
   element, then `{{name}}` interpolation is re-applied to variant content.

2. **Static nodes** — in `_renderInteractionPath()`, resolved at render-time so
   variants reflect current DOM state (e.g., a vault may change from "missing"
   to "unlocked" after the user clicks + Create without leaving the step).

### Context-Aware Enrichment Pattern

Dynamic nodes can be enriched beyond template interpolation by reading DOM
state. This is how the engine adds application-specific knowledge:

- **Default badge** → appends "pre-selected in Step 3" note
- **Stack/path/domain metadata** → extracts from module row spans
- **Stack detail cards** → builds styled HTML using `window._dcp.stacks` data
- **Dockerfile analysis** → per-file base images, stages, ports via `_parseDockerImage`
- **Compose service analysis** → per-service image breakdown, role classification, metadata

This enrichment happens in `_resolveDynamic` during tree flattening, NOT
during rendering. The synthetic node carries the enriched content.

#### Module Stack Enrichment

When a module row has a stack, `_resolveDynamic()` builds a styled HTML detail
card (not raw text) using the same CSS classes as the stack select detail:

```javascript
// Styled HTML detail card for module hover
var stackHtml = '<div class="assistant-stack-detail">';

if (stackEntry.parent) {
    // Flavored: language name + description first
    stackHtml += '<div class="assistant-stack-detail-name">' + parent.icon + ' ' + parent.name + '</div>';
    stackHtml += '<div class="assistant-stack-detail-text">' + parent.detail + '</div>';
    // Then framework
    stackHtml += '<div class="assistant-stack-detail-framework">↳ ' + stack.name + '</div>';
    stackHtml += '<div class="assistant-stack-detail-text">' + stack.detail + '</div>';
} else {
    // Base stack: just show it
    stackHtml += '<div class="assistant-stack-detail-name">' + stack.icon + ' ' + stack.name + '</div>';
    stackHtml += '<div class="assistant-stack-detail-text">' + stack.detail + '</div>';
}
// Capabilities footer
stackHtml += '</div>';
```

The `detail` field contains two paragraphs: a human-friendly description first,
then a "Technical:" note. The `.assistant-stack-detail-text` has `white-space: pre-line`
so line returns are respected.

#### Dockerfile Per-File Enrichment

When the parent node is `docker-section-dockerfiles`, `_resolveDynamic()` reads
each Dockerfile row's DOM to extract base images, stages, and ports, then builds
rich per-file analysis using `_parseDockerImage()`:

```javascript
// For each Dockerfile row element:
// 1. Extract base image strings from accent-colored spans
// 2. Extract stage names from "AS xxx" text in muted spans
// 3. Extract port numbers from "EXPOSE xxx" text
// 4. Call _parseDockerImage(imageString) for each base image
//    → returns { label, version, variant, variantExplain, family }
// 5. Build styled pills: runtime (accent), version (secondary), variant (success)
// 6. Append stage info and port info
// 7. Set nodeExpanded to the complete state-card HTML
```

The renderer (`_wizard_integrations.html`) adds `id="wiz-docker-df-{i}"` to
each Dockerfile row. The catalogue's `childTemplate` uses:
- `selector: '[id^="wiz-docker-df-"]'`
- `nameSelector: "code"` (extracts the Dockerfile path)

#### Compose Service Per-Service Enrichment

Same pattern for `docker-section-compose-svcs`. Each service row gets role
classification based on `_parseDockerImage().family`:

| Family | Role | Card Style |
|--------|------|------------|
| `database` | database | `state-info` |
| `cache` | cache | `state-info` |
| `webserver` | proxy | `state-info` |
| (other) | application | `state-success` |
| `(build)` | application (builds from Dockerfile) | `state-success` |

The enrichment also reads metadata from muted spans (volumes, deps, restart)
and builds the same styled pills for image breakdown.

The renderer adds `id="wiz-docker-svc-{i}"` to each service row. The catalogue's
`childTemplate` uses:
- `selector: '[id^="wiz-docker-svc-"]'`
- `nameSelector: "strong"` (extracts the service name)

#### `_parseDockerImage(imageString)` Helper

Parses a Docker image string (e.g. `python:3.11-slim-bookworm`) into structured
components used by both the `dockerfileAnalysis` resolver and dynamic enrichment:

```javascript
// Returns:
{
    label: "Python",           // Human-friendly runtime name
    version: "3.11",           // Version tag
    variant: "slim-bookworm",  // OS variant (alpine, slim, bookworm, etc.)
    variantExplain: "Minimal Debian 12 ...",  // Human explanation of variant
    family: "runtime"          // Category: runtime, database, cache, webserver, queue
}
```

This function is defined once in the engine and reused everywhere Docker image
analysis is needed — ensuring consistent quality between parent-level resolvers
and dynamic child enrichment.

#### K8s Manifest Enrichment

Per-manifest enrichment reads resource kinds from the muted span next to each
manifest file path. A 18-entry `kindMap` maps K8s resource kinds to icons and
descriptions (Deployment → 🚀, Service → 🌐, ConfigMap → 🔧, etc.).

The renderer adds `id="wiz-k8s-section-manifests"` to the details element.
The catalogue's `childTemplate` uses:
- `selector: '#wiz-k8s-section-manifests [style*="border-bottom"]'`
- `nameSelector: "code"` (extracts the file path)

#### K8s Helm Chart Enrichment

Per-chart enrichment reads chart name from `<strong>`, version from `<code>`,
and metadata spans (values.yaml, templates/, subcharts, env values) from the
DOM row structure.

#### K8s Kustomize Overlay Enrichment

Per-overlay enrichment reads overlay name from `<code>` and patch count from
the muted span. Generates an apply command: `kubectl apply -k overlays/{name}/`.

#### K8s Template Resolvers

- `k8sManifests` — reads manifest file count from the manifests section summary
- `k8sResources` — reads total resource count from the status strip pills

---

## 4. Node Matching

### `_matchNode(element)`

Maps a DOM element (from hover/focus event) to a superstructure node.
Iterates `_flatNodes` (deepest-first) and returns the first match.

**Three matching strategies (in order per node):**

1. **Dynamic element reference** — if `node._element === element` or
   `node._element.contains(element)` → match. This handles dynamically
   created nodes that have no CSS selector.

2. **CSS selector** — `element.matches(node.selector)` or
   `element.closest(node.selector)` → match. For static nodes with
   selectors like `#wiz-name`, `#wiz-desc`.

3. **Field-group proximity** — if the hovered element shares a wrapper
   `div` with the selector target, match. This handles hovering a `<label>`
   that is a sibling of `<input id="wiz-name">` inside the same field group.

```javascript
// Field-group proximity check:
// Use parentElement.closest('div') to skip the target element itself
// when it IS a div (e.g., #wiz-domains is a div)
const targetEl = _containerEl.querySelector(node.selector);
if (targetEl && targetEl.parentElement) {
    const wrapper = targetEl.parentElement.closest('div');
    if (wrapper && wrapper !== _containerEl &&
        (wrapper === element || wrapper.contains(element))) {
        return entry;
    }
}
```

**Why `parentElement.closest('div')`**: If `targetEl.closest('div')` is used
and the target IS a div (like `#wiz-domains`), it returns itself. The wrapper
would be the element, not its parent field group. Starting from `parentElement`
ensures we find the actual container div.

---

## 5. Interaction Path Rendering

### `_renderInteractionPath()`

Merges focus and hover paths into a single render.

1. If both paths are null → render entry state (context header centered)
2. Collect all unique nodes from both paths (targets + parent chains)
3. Sort by depth (shallowest first)
4. **Trim to target + 1 immediate parent** (max 2 nodes rendered)
5. Normalize depths so the shallowest shown renders at depth 0
6. Mark each node as `isTarget` (the leaf being focused/hovered) or
   `inChain` (a parent of a target)
7. Render nodes sequentially to the panel
8. Targets get `expanded` content rendered; chain nodes get `content` only
9. Call `_centerActiveNode()` to scroll the panel

### `_mergeInteractionPaths(focusPath, hoverPath)`

Deduplicates by `node.id`. If both paths share a parent, it appears once.
Target nodes are always promoted to `isTarget = true`. After sorting by
depth, the result is **trimmed**: only nodes within 1 depth of the deepest
target are kept (the target itself + its immediate parent). Depths are then
normalized so the shallowest remaining node renders at depth 0.

This ensures the panel focuses on the specific element being interacted
with, rather than showing the entire ancestor chain from the context root.

### `_centerActiveNode()`

Scrolls the panel so the active target is vertically centered.

```javascript
var targetTop = target.offsetTop;       // Relative to panel (position: absolute)
var targetHeight = target.offsetHeight;
var panelHeight = _panelEl.clientHeight;
var scrollTo = targetTop - (panelHeight / 2) + (targetHeight / 2);
_panelEl.scrollTo({ top: Math.max(0, scrollTo), behavior: 'smooth' });
```

Uses `offsetTop` (not `getBoundingClientRect`) because the panel is
`position: absolute` — `offsetTop` is relative to the panel itself.

---

## 6. Event Handling

### Listeners (attached to `containerEl` = `#wizard-body`)

| Event | Handler | Behavior |
|-------|---------|----------|
| `mouseover` | `_onHover` | Debounced 50ms. Matches node, updates `_hoverPath`, re-renders. |
| `focusin` | `_onFocus` | Immediate. Matches node, updates `_focusPath`, re-renders. |
| `focusout` | `_onBlur` | Clears `_focusPath`, re-renders. |
| `mouseleave` | `_onMouseLeave` | Clears `_hoverPath` — BUT preserves it if mouse moved to panel. |
| `wheel` | `_onWheel` | Attached to `.assistant-layout`. Redirects scroll to panel first. |

### Hover Deduplication

```javascript
// Same hover target as before? Don't re-render
if (_hoverPath && _hoverPath.target.id === matched.node.id) return;
```

This is the ONLY deduplication check. Do NOT add a skip for "hover matches
focus" — that causes stale hover nodes to persist in the render when the
user moves between elements.

### Mouse Leave + Panel Awareness

```javascript
function _onMouseLeave(e) {
    // Don't clear hover if mouse moved to the assistant panel
    if (_panelEl && (e.relatedTarget === _panelEl ||
        _panelEl.contains(e.relatedTarget))) return;

    _hoverPath = null;
    _renderInteractionPath();
}
```

Because the panel is `position: absolute` (not inside `#wizard-body`),
moving the mouse from wizard-body to the panel triggers `mouseleave`.
The `e.relatedTarget` check prevents clearing hover data when the user
moves to read the panel.

### Wheel Scroll Interception

```javascript
function _onWheel(e) {
    var scrollTop = _panelEl.scrollTop;
    var scrollMax = _panelEl.scrollHeight - _panelEl.clientHeight;

    if (scrollMax <= 0) return;  // No overflow — pass through

    // Scrolling down, panel not at bottom
    if (e.deltaY > 0 && scrollTop < scrollMax) {
        e.preventDefault();
        _panelEl.scrollTop = Math.min(scrollTop + e.deltaY, scrollMax);
        return;
    }

    // Scrolling up, panel not at top
    if (e.deltaY < 0 && scrollTop > 0) {
        e.preventDefault();
        _panelEl.scrollTop = Math.max(scrollTop + e.deltaY, 0);
        return;
    }

    // Panel fully scrolled — let event pass to page
}
```

Attached to `.assistant-layout` (not wizard-body) with `{ passive: false }`
to enable `preventDefault`.

---

## 7. Template Resolution

### `_resolve(text)`

Replaces `{{variableName}}` with values from `window._assistant.resolvers`.

```javascript
text.replace(/\{\{(\w+)\}\}/g, function(match, key) {
    var resolver = window._assistant.resolvers[key];
    return resolver ? resolver() : '';
});
```

### Registered Resolvers

Resolvers are registered in `_wizard_init.html` when activating:

```javascript
window._assistant.resolvers = {
    envCount: function() {
        return document.querySelectorAll('#wiz-envs > div').length;
    },
    domainCount: function() {
        return document.querySelectorAll('#wiz-domains > span').length;
    }
};
```

Add new resolvers as needed for new contexts. They are simple DOM reads.

---

## 8. Content Authoring — Scaling to New Contexts

### Adding a new wizard step

1. **Author the catalogue entry** in `assistant-catalogue.json`:
   - Add a new top-level object with `"context": "wizard/step-name"`
   - Build the children tree to mirror the step's DOM structure
   - Verify every `selector` against the actual rendered HTML IDs/classes

2. **Register the activation** in `_wizard_init.html`:
   - The existing hook maps step names to context IDs
   - Add resolvers for any new `{{variables}}`

3. **No engine changes needed** — the engine is generic

### Adding a modal context

1. Author the catalogue entry with `"context": "modal-name/step-name"`
2. Call `window._assistant.activate('modal-name/step-name', modalBody)`
   when the modal opens
3. Call `window._assistant.deactivate()` when the modal closes
4. The panel container must exist in the DOM (currently `#assistant-panel`
   is inside the wizard tab)

### Adding dynamic nodes to a new section

1. Set `"dynamic": true` on the parent node in the catalogue
2. Define `"childTemplate"` with `"selector"` pointing to the container's
   direct children (e.g., `"#my-list > div"`)
3. Use `"{{name}}"` in title/content/expanded for text interpolation
4. Engine will query the DOM and create synthetic nodes automatically
5. Optionally add `"nameSelector"` if the default name extraction hits the
   wrong element (see section above)
6. Optionally add `"variants"` for state-dependent content (see section above)

### Content Authoring Rules — App Context Aware

The assistant is NOT a generic tooltip. It is deeply knowledgeable about the
DevOps Control Plane application. Every piece of content should demonstrate
understanding of:

1. **What this field/section does in the pipeline** — Project Name isn't just
   a label, it shows up in Docker image tags, CI pipeline names, Helm charts,
   and folder structures. The assistant KNOWS this.

2. **How steps connect** — Environments defined in Step 1 become scope
   selectors in Step 3 (Vault). The assistant says "pre-selected when you
   define secrets in Step 3" because it understands the wizard flow.

3. **What consequences choices have** — Setting a K8s resource limit below
   actual usage means OOM kills. Leaving health checks off means K8s can't
   detect deadlocks. The assistant explains WHY, not just WHAT.

4. **Cross-references between related elements** — kubectl missing →
   Kubernetes shows "not installed" below. Terraform CLI installed → but no
   .tf files yet. Docker compose services → become K8s Deployments.

5. **Operational knowledge** — development = test credentials, debug settings,
   relaxed security. production = real credentials, hardened settings,
   monitoring. The assistant knows what each environment MEANS operationally.

6. **Never restate the visible** — don't echo field values, badge text, or
   status labels. Explain what they MEAN and what to DO.

7. **Conversational tone** — "You've got 2 set up", "Take your time",
   "That's fine — they'll appear after you configure those integrations."

8. **Silence > noise** — if there's nothing useful to add, don't force content.

---

## 9. Known Patterns & Pitfalls

### Variable Shadowing

In `_resolveDynamic`, the extracted text variable MUST be named `extractedName`
(not `name`). The `_resolve()` function's regex callback uses `name` as a
parameter. If both use `name`, the closure can produce garbled output where
the extracted text gets inserted between every character.

### Field-Group Proximity False Positives

The proximity check can match elements that share a wrapper div but belong
to different logical groups. This is acceptable for the wizard's simple
structure but may need refinement for complex layouts where unrelated
elements share the same parent div.

### Dynamic Node Staleness

Dynamic nodes are created during `_flattenTree()` which runs on `activate()`
and `refresh()`. If the user adds/removes environments or domains, call
`window._assistant.refresh()` to re-flatten the tree and pick up changes.

### Scroll Centering + Bottom Padding

The panel adds dynamic bottom padding to its inner content wrapper so that
the LAST node can still be scrolled to center. Without this padding, nodes
near the bottom can never reach the center of the viewport.

---

## 10. Test Checklist

| Test | Expected |
|------|----------|
| Open wizard step 1 | Panel shows context header centered (entry state) |
| Hover "Project Name" input | Panel: context header + Project Name (active, with expanded) |
| Hover label "Project Name" | Same as above (field-group proximity match) |
| Move hover away | Panel returns to entry state |
| Click into Description textarea | Panel: context header + Description (active) |
| While focused on Description, hover Repository | Both shown, shared context header once |
| Hover environment row "development" | Panel: context + Environments (chain) + development (active) |
| Development row shows "· default" in title | Default badge detected, Step 3 note in expanded |
| Hover "Add domain" input | Panel: context + Domains (chain) + Add domain (active) |
| Mouse from wizard-body to panel | Hover data preserved (not cleared) |
| Scroll wheel over wizard area | Panel scrolls first, then page |
| Panel content overflows | Panel scrolls internally, card height unchanged |
| Resize below 1000px | Panel hidden, wizard takes full width |

---

## 11. Stack Highlighting (`_highlightSelectedStack`)

When the user selects a stack from the dropdown, the engine highlights the
corresponding section in the assistant's stack listing and inserts a detail card.

### Flow

1. Read the selected stack name from the `#wiz-mod-stack` dropdown
2. Find the stack data in `window._dcp.stacks`
3. If the stack has a parent, also find the parent (base/language) stack
4. Iterate expanded content elements (`.assistant-node-expanded`)
5. For each, split innerHTML by `\n` and search for the entry `• stackName —`
6. Walk backwards from the entry to find the section header (line with emoji)
7. Walk forwards to find the section end (next section header or end of content)
8. **Mark entries**: selected entry → `.assistant-stack-selected`, parent entry → `.assistant-stack-parent`
9. **Wrap section**: `<span class="assistant-stack-section">` around header…end
10. Set innerHTML (section + entry highlights)
11. **Insert detail card** as DOM element AFTER the section:
    - Flavored stacks: language name + description first, then `↳ framework` + description
    - Base stacks: stack name + description only
    - Capabilities listed at bottom
12. **Scroll** to center the selected entry using `getBoundingClientRect()`

### CSS Classes

| Class | Purpose |
|-------|---------|
| `.assistant-stack-section` | Background + left border on the entire language family section |
| `.assistant-stack-selected` | Bold + accent highlight on the selected entry |
| `.assistant-stack-parent` | Dimmer highlight on the parent entry |
| `.assistant-stack-detail` | Styled card with description and capabilities |
| `.assistant-stack-detail-name` | Stack/language name header |
| `.assistant-stack-detail-text` | Description text (`white-space: pre-line`) |
| `.assistant-stack-detail-framework` | Framework sub-header with border-top separator |
| `.assistant-stack-detail-caps` | Capabilities footer (italic, dimmer) |

### Data Layer

All stack data is injected into `window._dcp.stacks` by the server (`server.py`):

```javascript
window._dcp.stacks = [
    {
        name: "python-flask",
        description: "Flask web application",
        detail: "Flask is a lightweight...",  // Human-friendly + technical
        icon: "🐍",
        domain: "service",
        parent: "python",
        capabilities: ["install", "lint", "format", "test", "types", "serve"],
        capabilityDetails: [{name, command, description, adapter}, ...],
        requires: [{adapter, minVersion}, ...],
        detection: {filesAnyOf, filesAllOf, contentContains}
    },
    // ... 47 stacks total
];
```

---

## 12. Hidden-Marker Variant Pattern

Some DOM elements carry hidden `<span>` markers that serve as variant
selectors without affecting the visual layout. The pattern:

```html
<!-- In the wizard step renderer -->
<div id="wiz-env-vault-dev">
    <span data-env-active hidden></span>   <!-- invisible, only for assistant -->
    ...visible content...
</div>
```

```json
// In the catalogue
{
    "when": {
        "textContains": "unlocked",
        "hasSelector": "[data-env-active]"
    },
    "content": "This is the ACTIVE environment and it's unlocked..."
}
```

The `hasSelector` condition uses `element.querySelector()`, so the hidden
span doesn't need any text content — it just needs to exist inside the
element's DOM subtree.

**Why not use `textContains` alone?** Because the active badge text
("ACTIVE") appears in the `textContent` of the element, but using that
as the discriminator would be fragile — the word could appear in
descriptions or labels. A dedicated `data-*` attribute is a stable contract
between the renderer and the catalogue.

**Current usage:** `[data-env-active]` on the active environment's vault
status row in wizard/secrets step 3. The same pattern can be reused for
any future scenario where visual text alone isn't a reliable discriminator.

---

## 13. Active Environment Highlighting (`_highlightActiveEnv`)

When the assistant panel renders for `wizard/secrets`, the engine calls
`_highlightActiveEnv()` in a `requestAnimationFrame` hook to visually
distinguish the active environment's entry in the assistant node list.

### How It Works

1. After `_renderInteractionPath()` completes, scan all
   `.assistant-node-entry` elements in the panel
2. Find the one whose text contains "· ACTIVE" (the label added by the
   vault row renderer)
3. Add the CSS class `.assistant-node-active-env` to that entry
4. This applies a subtle accent-colored left border and background tint

### CSS

```css
.assistant-node-active-env {
    border-left: 3px solid var(--accent);
    background: color-mix(in srgb, var(--accent) 5%, transparent);
    border-radius: 4px;
}
```

### Relationship to Stack Highlighting

This follows the same pattern as `_highlightSelectedStack` (section 11):
a post-render decoration pass that adds CSS classes to assistant entries
based on external state. Both run in `requestAnimationFrame` to ensure
the DOM is ready.

