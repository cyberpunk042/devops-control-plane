# Assistant — Unified System Plan (v2)

> **What this document is:** The single source of truth for the assistant system.
> Supersedes all previous layer plans (L1–L9). The architecture was fundamentally
> revised after building 4 concrete scenarios that revealed what the assistant
> actually IS — a full-panel page mirror, not a single-message element tooltip.
>
> **Reference documents:**
> - `assistant-realization.md` — what the assistant IS, how it reasons
> - `assistant-scenarios.md` — 4 concrete examples of full panel output
>
> **What changed from v1:** The 9-layer pipeline, provider protocol, category
> priority system, and data-guide attribute approach are all replaced. The new
> architecture has 4 concerns driven by an external JSON superstructure.

---

## What We're Building

A **full-height side panel** that shows contextual help driven by
user interaction.

Every visible element on the page has a corresponding entry **in the
superstructure JSON**, but the panel only renders content relevant to the
current interaction — not the entire page at once.

### What the user sees

A panel to the right of the wizard content (or modal content).

**On page entry:** only the step context is shown (header + content).
The panel is otherwise empty.

**On hover/focus:** the hovered or focused element's content appears in
the panel, along with the content of every parent in the hierarchy up to
the step context. This builds a path: step context → section → sub-section
→ element.

**Focus and hover coexist:** if the user has focus on one element (e.g.,
clicked into an input) and hovers another, both elements and their parent
chains are shown simultaneously. Shared parents appear once.

The panel scrolls in sync with the content so the relevant assistant entry
is always aligned with the element the user is looking at.

### How it talks

- Conversational — like a colleague, not a reference manual
- Never restates the visible — explains what things MEAN
- Cross-references between related elements
- Teaches concepts the user may not know
- Explains consequences — "if you exceed this, K8s will kill the pod"
- Never lies or generalizes — development ≠ local, daemon offline ≠ blocker

### Base requirements (non-negotiable)

1. **Event-driven content** — the panel shows content based on hover/focus, not all at once
2. **Parent chain cascade** — interacting with an element shows its content + all ancestors
3. **Focus + hover coexistence** — both interaction paths render simultaneously
4. **Hierarchical superstructure** — the JSON tree mirrors the page's nesting (sections, sub-sections, sub-sub-sections)
5. **Synced scroll** — panel scrolls with content
6. **Step context persists** — top of panel always shows where user is

---

## Architecture Overview — 4 Concerns

The old 9-layer pipeline is replaced by 4 distinct concerns:

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│   1. SUPERSTRUCTURE (Data)                               │
│   Single JSON catalogue — the knowledge tree             │
│   All contexts in one file (assistant-catalogue.json)     │
│                                                          │
│   Contains: titles, content, expanded content,           │
│   selectors, hierarchy, template variables               │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                                                          │
│   2. ENGINE (Logic)                                      │
│   _assistant_engine.html — ~300 lines                    │
│                                                          │
│   Does: loads superstructure, renders panel tree,        │
│   maps DOM events to tree nodes, scroll sync,            │
│   expand/collapse on hover/focus, template resolution    │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                                                          │
│   3. PRESENTATION (Visual)                               │
│   CSS in admin.css                                       │
│                                                          │
│   Does: panel layout, depth indentation, section         │
│   separators, expansion animation, typography,           │
│   responsive hiding, scroll behavior                     │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                                                          │
│   4. INTEGRATION (Hooks)                                 │
│   Thin glue in existing templates                        │
│                                                          │
│   Does: tells engine when context changes (tab switch,   │
│   modal open/close, wizard step change), settings toggle │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### Why 4 concerns, not 9 layers

The old 9-layer system was designed for a different product — a single-message,
element-focused assistant that needed providers to assess DOM state, categories
to prioritize output, and state machines to track interactions.

The new product is fundamentally simpler in architecture:
- **Content is pre-written** — it lives in JSON, not generated by providers
- **Hierarchy is explicit** — it's in the JSON tree, not resolved by DOM walking
- **Content is event-driven** — only the interaction path is rendered, not the full tree
- **Hover/focus controls visibility** — content appears along the parent chain of the interacted element

The complexity moved from the ENGINE to the DATA. The engine is now a simple
tree renderer. The intelligence is in the superstructure content.

---

## 1. The Superstructure (Data)

### File location

```
src/ui/web/static/data/
  assistant-catalogue.json       # Single file — all contexts
```

One file containing all contexts as an array. Loaded once on first use.
The engine indexes by `context` key into an in-memory Map.

### Node schema

Each node in the tree:

```json
{
  "id": "project-name",
  "title": "Project Name *",
  "icon": null,
  "selector": "#wiz-name",
  "content": "This is your project's identity — it'll show up in Docker labels, CI pipeline names, folder structures, and every generated config.",
  "expanded": "...additional detail shown when this node is focused...",
  "separator": false,
  "children": []
}
```

**Fields:**

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `id` | string | yes | Unique within parent. Used for DOM mapping fallback. |
| `title` | string | yes | Label shown in the panel. |
| `icon` | string | no | Emoji prefix (🧙, ☸️, 📦, etc.) |
| `selector` | string | no | CSS selector to map this node to a DOM element. |
| `content` | string | yes | Concise assistant text. Always shown. |
| `expanded` | string | no | Additional text shown when focused/hovered. Appended to content. |
| `separator` | boolean | no | Show a visual separator before this node. |
| `children` | node[] | yes | Nested nodes. Can be arbitrarily deep. |

### Context wrapper

Each file wraps the tree with context metadata:

```json
{
  "context": "wizard/welcome",
  "title": "🧙 Welcome to the Setup Wizard",
  "content": "6 steps to configure your project...",
  "children": [
    { "id": "project-name", ... },
    { "id": "description", ... },
    { "id": "environments", ..., "children": [
      { "id": "env-development", ... },
      { "id": "env-production", ... }
    ]}
  ]
}
```

### Dynamic content

Some content needs runtime data ("You've got 2 environments", "8 of 15
tools available"). Two approaches:

**Option A: Template variables in content strings**
```json
{
  "content": "You've got {{envCount}} set up so far."
}
```
Engine resolves `{{envCount}}` at render time by calling a resolver function
registered for that variable.

**Option B: Resolver function reference**
```json
{
  "content": "Environments scope your secrets and variables.",
  "resolver": "envSummary"
}
```
Engine calls `resolvers.envSummary()` and appends the result to content.

Option A is simpler. Option B is more flexible. **Decision: start with
Option A, add Option B only if needed.**

### Resolver registration

Template variables map to simple DOM-reading functions:

```javascript
_assistant.resolvers = {
    envCount: () => document.querySelectorAll('[data-env]').length,
    toolCount: () => {
        const badges = document.querySelectorAll('.tool-badge');
        const found = document.querySelectorAll('.tool-badge.found');
        return `${found.length} of ${badges.length}`;
    },
    scanAge: () => document.querySelector('.scan-time')?.textContent || 'unknown'
};
```

These are lightweight DOM reads — no complex logic. The intelligence is
in the content strings, not the resolvers.

### Full example: wizard/welcome context

```json
{
  "context": "wizard/welcome",
  "title": "🧙 Welcome to the Setup Wizard",
  "content": "6 steps to configure your project. Start with your project name — it's used across all generated configs and scripts.",
  "children": [
    {
      "id": "project-name",
      "title": "Project Name *",
      "selector": "#wiz-name",
      "content": "This is your project's identity — it'll show up in Docker labels, CI pipeline names, folder structures, and every generated config.",
      "children": []
    },
    {
      "id": "description",
      "title": "Description",
      "selector": "#wiz-desc",
      "content": "Good to have — it'll appear in your README header, package metadata, and repository description when you push.",
      "children": []
    },
    {
      "id": "repository",
      "title": "Repository",
      "selector": "#wiz-repo",
      "content": "This connects your project to its Git remote. CI webhooks, GitHub integration, and deployments will reference this.",
      "children": []
    },
    {
      "id": "domains",
      "title": "📂 Domains",
      "selector": "#wiz-domains",
      "separator": true,
      "content": "These are logical groupings for your modules. When you add modules in step 2, each one belongs to a domain. Think of them as folders for organizing your codebase — library for shared code, ops for tooling, docs for documentation.",
      "children": [
        {
          "id": "add-domain",
          "title": "Add domain...",
          "selector": "#wiz-add-domain",
          "content": "Type a name and hit + Add if you need another grouping.",
          "children": []
        }
      ]
    },
    {
      "id": "environments",
      "title": "📋 Environments",
      "selector": "#wiz-environments",
      "separator": true,
      "content": "Environments scope your secrets and variables. Your project config, integrations, and generated files are shared across all environments — what changes per environment are the secret values and environment variable values.\n\nSo your DB_HOST might be dev-db.internal in development but prod-db.example.com in production. Same project config, different credentials per environment.\n\nYou've got {{envCount}} set up so far.",
      "children": [
        {
          "id": "env-development",
          "title": "development · default",
          "selector": "[data-env='development']",
          "content": "The development environment is where your team builds, tests, and iterates.",
          "expanded": "It typically involves:\n• Test credentials and local service endpoints\n• Debug-level settings and verbose output\n• Relaxed security and faster feedback loops\n\nAs the default environment, it will be pre-selected when you define secrets and variables in step 3.\n\n💡 Click the name or description to edit. Use × to remove.",
          "children": []
        },
        {
          "id": "env-production",
          "title": "production",
          "selector": "[data-env='production']",
          "content": "Production environment — live-facing, real credentials and hardened settings. Configured separately in step 3.",
          "children": []
        },
        {
          "id": "add-environment",
          "title": "Add environment...",
          "selector": "#wiz-add-env",
          "content": "Add another deployment target (e.g., staging, qa, preview). Each one gets its own secret values in step 3.",
          "children": []
        }
      ]
    }
  ]
}
```

---

## 2. The Engine (Logic)

### File: `_assistant_engine.html`

One IIFE. One `window._assistant` public API. ~300 lines.

### Public API

```javascript
window._assistant = {
    enable(),              // Turn on the assistant
    disable(),             // Turn off the assistant
    activate(contextId, containerEl),   // Set active context
    deactivate(),          // Clear active context
    refresh(),             // Re-render current context
    resolvers: {}          // Template variable resolvers
};
```

### Core flow

```
App event (wizard step, modal open)
    → activate(contextId, containerEl)
    → fetch JSON for contextId (or use cache)
    → renderTree(rootNode, panelEl)
    → attachEventListeners(containerEl)

User hovers/focuses an element
    → matchNodeBySelector(element, tree)
    → expandNode(matchedNode)
    → scrollPanelToNode(matchedNode)

User navigates away (modal close, tab switch)
    → deactivate()
    → clear panel
```

### Context lookup

The engine loads `assistant-catalogue.json` once, builds a
`Map<contextId, context>`, and looks up by ID:

```javascript
const tree = _catalogue.get(contextId);
```

No file mapping needed — context IDs are the keys directly.

### Node rendering

The engine renders nodes along the **interaction path** — not the full tree.
When the user hovers or focuses an element, the engine:

1. Matches the DOM element to a superstructure node via selector
2. Walks up the tree to collect the full parent chain
3. Renders only those nodes (context → parent → ... → element)

Each node is rendered as a div with depth-based indentation:

```javascript
function renderNode(node, depth, panelEl) {
    const div = document.createElement('div');
    div.className = 'assistant-node';
    div.dataset.nodeId = node.id;
    div.dataset.depth = depth;
    div.style.paddingLeft = (depth * 16) + 'px';

    // Separator
    if (node.separator) {
        const sep = document.createElement('hr');
        sep.className = 'assistant-separator';
        panelEl.appendChild(sep);
    }

    // Title
    const title = document.createElement('div');
    title.className = 'assistant-node-title';
    title.textContent = (node.icon ? node.icon + ' ' : '') + node.title;
    div.appendChild(title);

    // Content
    const content = document.createElement('div');
    content.className = 'assistant-node-content';
    content.textContent = resolveTemplates(node.content);
    div.appendChild(content);

    // Expanded content (shown when this is the actively interacted node)
    if (node.expanded && node._isActiveTarget) {
        const expanded = document.createElement('div');
        expanded.className = 'assistant-node-expanded';
        expanded.textContent = resolveTemplates(node.expanded);
        div.appendChild(expanded);
    }

    panelEl.appendChild(div);
}
```

The engine does NOT recurse all children. Only nodes on the interaction
path(s) are rendered. Focus and hover paths are merged — shared parents
appear once.

### Selector matching

When the user hovers/focuses a DOM element, the engine finds the matching
tree node:

```javascript
function matchNode(element, tree) {
    // Try direct selector match
    for (const node of flattenTree(tree)) {
        if (node.selector && element.matches(node.selector)) {
            return node;
        }
        // Also check if element is INSIDE a selector match
        if (node.selector && element.closest(node.selector)) {
            return node;
        }
    }
    return null;
}
```

The `flattenTree` result is cached per context. Selectors are tested from
deepest to shallowest (most specific match wins).

### Scroll centering

When the user hovers or focuses an element, the panel scrolls so that
the **active target node is vertically centered** in the panel viewport.
The parent chain sits above it, any additional content below it. The
target is the visual anchor point.

```javascript
function centerActiveNode(panelEl) {
    const target = panelEl.querySelector('.assistant-node.active-target');
    if (!target) return;

    const panelRect = panelEl.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const targetCenter = targetRect.top + targetRect.height / 2;
    const panelCenter = panelRect.top + panelRect.height / 2;
    const offset = targetCenter - panelCenter;

    panelEl.scrollBy({ top: offset, behavior: 'smooth' });
}
```

### Template resolution

```javascript
function resolveTemplates(text) {
    if (!text) return '';
    return text.replace(/\{\{(\w+)\}\}/g, (match, key) => {
        const resolver = _assistant.resolvers[key];
        return resolver ? resolver() : match;
    });
}
```

### Debouncing

Hover events are debounced at 150ms to avoid jitter when the user moves
across multiple elements:

```javascript
let hoverTimer = null;

function onHover(element) {
    clearTimeout(hoverTimer);
    hoverTimer = setTimeout(() => {
        const node = matchNode(element, currentTree);
        if (node) expandNode(node);
    }, 150);
}
```

Focus events are NOT debounced — they're intentional.

---

## 3. Presentation (Visual)

### CSS additions to admin.css

```css
/* Panel layout */
.assistant-layout {
    display: flex;
    gap: var(--space-md);
}

.assistant-panel {
    flex: 0 0 300px;
    border-left: 1px solid var(--border-subtle);
    padding-left: var(--space-md);
    overflow-y: auto;
    max-height: calc(100vh - 120px);
}

/* Node styling */
.assistant-node {
    margin-bottom: var(--space-sm);
    transition: background 200ms ease;
}

.assistant-node-title {
    font-weight: 600;
    font-size: 0.78rem;
    color: var(--text-secondary);
    margin-bottom: 2px;
}

.assistant-node-content {
    font-size: 0.8rem;
    line-height: 1.55;
    color: var(--text-tertiary);
    white-space: pre-line;
}

/* Expanded content — only in the DOM when the engine renders it */
.assistant-node-expanded {
    margin-top: var(--space-xs);
    font-size: 0.8rem;
    line-height: 1.55;
    color: var(--text-secondary);
    white-space: pre-line;
}

/* Active target — the directly hovered/focused leaf node */
.assistant-node.active-target .assistant-node-title {
    color: var(--accent);
}

.assistant-node.active-target .assistant-node-content {
    color: var(--text-primary);
}

/* Separators */
.assistant-separator {
    border: none;
    border-top: 1px solid var(--border-subtle);
    margin: var(--space-md) 0;
}

/* Depth indentation handled inline via paddingLeft */

/* Responsive — hide on small screens */
@media (max-width: 1000px) {
    .assistant-panel { display: none; }
    .assistant-layout { display: block; }
}
```

### Typography

- Node titles: 0.78rem, semibold, secondary color
- Node content: 0.8rem, normal weight, tertiary color (shifts to primary when active)
- Expanded content: 0.8rem, secondary color, appears with transition
- The panel is a quiet sidebar — never competes with the main content

### Animation

- Node expansion: `display: none → block` with a subtle height transition
- Active highlight: background color transition (200ms ease)
- Scroll: `behavior: smooth` for panel scrolling

---

## 4. Integration (Hooks)

### Where hooks live

Thin glue code in existing files — NOT a new file.

### Wizard step change

In `_wizard.html` or `_wizard_init.html`:

```javascript
// When wizard step changes
function onWizardStep(stepName) {
    // ...existing step rendering...
    if (window._assistant) {
        window._assistant.activate('wizard/' + stepName, wizardBody);
    }
}
```

### Modal open/close

In modal initialization code:

```javascript
// When K8s setup modal opens
function openK8sSetup(step) {
    // ...existing modal open...
    if (window._assistant) {
        window._assistant.activate('k8s-setup/' + step, modalBody);
    }
}

// When modal closes
modal.addEventListener('close', () => {
    if (window._assistant) {
        // Re-activate wizard context
        window._assistant.activate('wizard/integrations', wizardBody);
    }
});
```

### Settings toggle

Already exists in `_settings.html`:

```javascript
function _prefSetAssistantGuide(enabled) {
    prefsSet('assistantGuide', enabled);
    if (window._assistant) {
        enabled ? window._assistant.enable() : window._assistant.disable();
    }
}
```

### Context stack (modals over wizard)

When a modal opens, it pushes a new context. When it closes, the previous
context is restored. The engine handles this internally:

```javascript
const contextStack = [];

function activate(contextId, containerEl) {
    contextStack.push({ contextId, containerEl });
    loadAndRender(contextId, containerEl);
}

function deactivate() {
    contextStack.pop();
    const prev = contextStack[contextStack.length - 1];
    if (prev) loadAndRender(prev.contextId, prev.containerEl);
}
```

---

## File Architecture Summary

```
src/ui/web/
├── static/
│   ├── css/admin.css                         # Presentation (CSS additions)
│   └── data/
│       └── assistant-catalogue.json          # Superstructure (single file)
└── templates/
    ├── scripts/
    │   ├── _assistant_engine.html             # Engine (~300 lines)
    │   ├── _wizard.html                       # Integration hook (activate)
    │   └── _settings.html                     # Integration hook (toggle)
    └── dashboard.html                         # Script inclusion
```

**Total new files:** 1 engine file + 1 catalogue file
**Modified files:** CSS, wizard template, settings template, dashboard
**Deleted concept:** Catalogue files, provider protocol, 9-layer pipeline

---

## Implementation Order

### Phase 1: Engine + First Context

1. Create `static/data/assistant-catalogue.json` with first context
2. Author `wizard/welcome` context (from Scenario 1)
3. Write the engine in `_assistant_engine.html`:
   - JSON loading + caching
   - Tree rendering (renderNode)
   - Panel injection into assistant-layout
4. Add CSS for panel layout and node styling
5. Hook wizard step change to call `activate()`
6. Include engine in dashboard.html

**User sees:** Panel appears next to wizard step 1. Full tree of assistant
content for the welcome step. No hover interaction yet.

### Phase 2: Interaction

1. Add hover/focus event listeners in the engine
2. Implement selector matching (matchNode)
3. Implement expand/collapse (add/remove `.active` class)
4. Add debouncing for hover events
5. Implement scroll sync

**User sees:** Hovering elements on the page highlights the corresponding
entry in the panel and shows expanded content.

### Phase 3: Remaining Wizard Contexts

1. Write JSON files for wizard steps 2–6 (from scenarios + new content)
2. Test context switching between steps
3. Add resolvers for dynamic content (envCount, toolCount)

**User sees:** Assistant works across all 6 wizard steps.

### Phase 4: Modal Contexts

1. Write JSON files for K8s setup (detect, configure, review)
2. Write JSON files for Docker setup (detect, configure, preview)
3. Hook modal open/close to activate/deactivate
4. Implement context stack (modal pushes, close pops)

**User sees:** Opening K8s/Docker setup shows context-specific assistant
content. Closing the modal returns to wizard context.

### Phase 5: Polish

1. Refine CSS — indentation depths, responsive behavior
2. Add template variables for dynamic counts
3. Review all JSON content for accuracy and tone
4. Test full flow: wizard → modal → back to wizard

---

## What About the Old Layer Concepts?

Many of the old layer concepts are now handled differently or eliminated:

| Old Concept | Where It Went |
|-------------|---------------|
| L1 Context Resolution (DOM walking) | **Eliminated.** Hierarchy is in the JSON tree, not the DOM. |
| L1 Positioning (output.style.top) | **Replaced.** Panel renders full tree, scroll sync keeps alignment. |
| L2 Category Priority | **Eliminated.** All content is visible. No priority filtering needed. |
| L2 State Filtering | **Eliminated.** No need to suppress/filter — everything shows. |
| L3 Providers | **Eliminated.** Content is pre-written in JSON, not generated at runtime. |
| L4 Visual Design | **Simplified.** Node styling + depth indentation, not category-specific treatments. |
| L5 Actions | **Deferred.** V1 is informational. Actions (Apply, Navigate) can be added later as node properties. |
| L6 Behavioral | **Simplified.** Expand/collapse + scroll. No crossfade, no complex transitions. |
| L7 Integration | **Simplified.** Resolvers for template variables. No DOM write operations. |
| L8 State | **Eliminated for V1.** No need to track visited, dismissed, rejected. Content is event-driven along the interaction path. |
| L9 Lifecycle | **Simplified.** activate/deactivate + context stack. No complex teardown. |

### What might come back for V2

- **Actions** — nodes could have an `action` field that triggers Apply, Navigate
- **Dynamic providers** — for nodes that need complex runtime assessment (port conflicts, validation)
- **State tracking** — to know if the user has already seen/configured something
- **Contextual warnings** — nodes that change content based on current state

These are additions to the superstructure schema, not architectural changes.
The engine already has the hooks (resolver protocol, node properties).

---

## The Test That Proves It Works

1. User enables assistant in settings → panel appears
2. User is on wizard step 1 → panel shows full welcome structure
3. User hovers "development" environment → that entry expands in panel
4. User moves to step 5 (Integrations) → panel updates with integrations content
5. User clicks Full Setup on K8s → modal opens, panel switches to K8s Detect content
6. User hits Configure → → panel switches to K8s Configure content (deep nesting)
7. User hovers resource limits → QoS explanation expands
8. User closes modal → panel returns to wizard integrations content
9. User scrolls through the configure page → panel scrolls in sync
10. User disables assistant in settings → panel disappears

This tests: context switching, modal stack, scroll sync, hover expansion,
settings toggle, deep nesting, and content accuracy.

---

## Previous Documents Status

The following documents remain as historical reference but are **superseded**
by this plan:

| Document | Status |
|----------|--------|
| `assistant-layer1-*.md` | Superseded — context resolution eliminated |
| `assistant-layer2-*.md` | Superseded — category system eliminated |
| `assistant-layer3-*.md` | Superseded — provider protocol eliminated |
| `assistant-layer4-*.md` | Partially relevant — visual concepts simplified |
| `assistant-layer5-*.md` | Deferred — actions are V2 |
| `assistant-layer6-*.md` | Partially relevant — behavioral simplified |
| `assistant-layer7-*.md` | Superseded — integration simplified to resolvers |
| `assistant-layer8-*.md` | Superseded — state tracking eliminated for V1 |
| `assistant-layer9-*.md` | Partially relevant — lifecycle simplified |
| `assistant-realization.md` | **Active** — the definitive what/why reference |
| `assistant-scenarios.md` | **Active** — the definitive content reference |
| `assistant-infrastructure-analysis.md` | Reference — still useful for understanding existing code |
