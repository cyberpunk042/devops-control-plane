# Assistant V1 — Implementation Plan

> Traceable plan for the superstructure data file and engine.
> Every decision links back to: goal → requirement → change → test → evidence.

---

## Scope

Two deliverables:

1. **Data**: `src/ui/web/static/data/assistant-catalogue.json` — wizard/welcome context
2. **Engine**: `src/ui/web/templates/scripts/_assistant_engine.html` — IIFE engine

One integration point:

3. **Include**: Add `{% include 'scripts/_assistant_engine.html' %}` to `dashboard.html`

The wizard hook already exists (`_wizard_init.html` line 184–191). No changes needed there.

---

## Pre-conditions (verified)

| Fact | Evidence | Risk if wrong |
|------|----------|---------------|
| `#assistant-panel` exists in DOM | `_tab_wizard.html` line 14 | Engine can't find panel container |
| `#wizard-body` exists in DOM | `_tab_wizard.html` line 13 | Engine has no container to listen on |
| `.assistant-layout` wraps both | `_tab_wizard.html` line 12 | Flex layout won't work |
| `renderWizard()` calls `_assistant.activate()` | `_wizard_init.html` lines 184-191 | Engine never gets activated |
| Hook fires AFTER step renderer completes | Lines 187-191: waits for promise | Selectors would miss dynamically rendered elements |
| CSS classes are in `admin.css` | Just appended ~300 lines | Engine depends on these class names |
| Static files served at `/static/` | Flask standard | JSON fetch would 404 |

---

## Deliverable 1: `assistant-catalogue.json`

### File location

```
src/ui/web/static/data/assistant-catalogue.json
```

Served at: `GET /static/data/assistant-catalogue.json`

### Structure

```json
[
  {
    "context": "wizard/welcome",
    "title": "...",
    "icon": "...",
    "content": "...",
    "children": [ ... ]
  }
]
```

### Wizard Step 1 (Welcome) — Node tree

Built from the actual DOM in `_wizard_steps.html` lines 17-109.

```
wizard/welcome
├── project-name        selector: "#wiz-name"
├── description         selector: "#wiz-desc"
├── repository          selector: "#wiz-repo"
├── domains             selector: "#wiz-domains" (parent section)
│   ├── domain-badges   selector: "#wiz-domains > span"    (dynamic)
│   └── add-domain      selector: "#wiz-new-domain"
└── environments        selector: "#wiz-envs" (parent section)
    ├── env-rows         selector: "#wiz-envs > div"        (dynamic)
    ├── add-env-name     selector: "#wiz-new-env-name"
    └── add-env-desc     selector: "#wiz-new-env-desc"
```

### Selector verification checklist

| Node | Selector | Verified in | Line |
|------|----------|-------------|------|
| Project Name | `#wiz-name` | `_wizard_steps.html` | 28 |
| Description | `#wiz-desc` | `_wizard_steps.html` | 38 |
| Repository | `#wiz-repo` | `_wizard_steps.html` | 48 |
| Domains container | `#wiz-domains` | `_wizard_steps.html` | 61 |
| Domain badges | `#wiz-domains > span` | `_wizard_steps.html` | 63 |
| Add domain input | `#wiz-new-domain` | `_wizard_steps.html` | 70 |
| Environments container | `#wiz-envs` | `_wizard_steps.html` | 84 |
| Environment rows | `#wiz-envs > div` | `_wizard_steps.html` | 86 |
| Add env name | `#wiz-new-env-name` | `_wizard_steps.html` | 95 |
| Add env desc | `#wiz-new-env-desc` | `_wizard_steps.html` | 98 |

### Content authoring

Rules from `assistant-layer1-data.md` (section "Content authoring rules"):
1. Never restate the visible
2. Explain consequences
3. Cross-reference related elements
4. Teach concepts
5. Be accurate
6. Conversational tone
7. Silence > noise
8. Use `\n` for line breaks

### Template variables for wizard/welcome

| Variable | DOM query | Returns |
|----------|-----------|---------|
| `{{envCount}}` | `document.querySelectorAll('#wiz-envs > div').length` | Number |
| `{{domainCount}}` | `document.querySelectorAll('#wiz-domains > span').length` | Number |

### Risks

| Risk | What would happen | How to diagnose |
|------|-------------------|-----------------|
| DOM renders AFTER activate() | Selectors find nothing | Console: "no elements matched" |
| Dynamic env rows have no parent ID | Can't match dynamic children | Check `#wiz-envs > div` selector |
| Domain spans don't match `> span` | Nesting changed | Inspect DOM, check actual child tag |
| JSON syntax error | fetch() fails silently | Console: JSON.parse error |

---

## Deliverable 2: `_assistant_engine.html`

### File location

```
src/ui/web/templates/scripts/_assistant_engine.html
```

Included via Jinja2 in `dashboard.html`.

### Architecture: IIFE exposing `window._assistant`

```javascript
(function() {
    // ── State ──────────────────────────────────────
    let _catalogue = null;      // Map<contextId, context>
    let _currentCtx = null;     // current context object
    let _panelEl = null;        // #assistant-panel
    let _containerEl = null;    // #wizard-body (listener target)
    let _flatNodes = [];        // flat array of {node, parents[]}
    let _focusPath = null;      // {target: node, chain: [parents]}
    let _hoverPath = null;      // {target: node, chain: [parents]}
    let _listeners = {};        // cleanup refs

    // ── Public API ─────────────────────────────────
    window._assistant = {
        activate,     // (contextId, containerEl) → void
        deactivate,   // () → void
        refresh,      // () → void — re-render current state
        enable,       // () → show panel
        disable,      // () → hide panel
        resolvers: {} // { varName: () => string }
    };
})();
```

### Flow diagram

```
activate("wizard/welcome", wizardBody)
  │
  ├── _loadCatalogue()
  │     └── fetch("/static/data/assistant-catalogue.json")
  │           └── build Map<contextId, ctx>
  │
  ├── _currentCtx = catalogue.get("wizard/welcome")
  │
  ├── _panelEl = document.getElementById("assistant-panel")
  │
  ├── _renderContextHeader(ctx, panelEl)
  │     └── panelEl.innerHTML = context title + content
  │     └── panelEl.classList.add("entry-state")
  │
  ├── _flatNodes = _flattenTree(ctx.children, [])
  │     └── for each node, store { node, parents: [...chain] }
  │     └── recursive: child gets [grandparent, parent] as parents
  │
  ├── _focusPath = null, _hoverPath = null
  │
  └── _attachListeners(containerEl)
        ├── mouseover  → _onHover(e)
        ├── focusin    → _onFocus(e)
        ├── focusout   → _onBlur(e)
        └── mouseleave → _onMouseLeave(e)
```

### Event: hover

```
_onHover(e)
  │
  ├── element = e.target (or closest match)
  │
  ├── matched = _matchNode(element)
  │     └── for each flatNode, test element.matches(node.selector)
  │     └── OR test element.closest(node.selector) exists
  │     └── return first match (deepest first in flat list)
  │
  ├── if (!matched) return   // no node for this element
  │
  ├── _hoverPath = { target: matched.node, chain: matched.parents }
  │
  └── _renderInteractionPath()
```

### Event: focus

```
_onFocus(e)
  │
  ├── element = e.target
  ├── matched = _matchNode(element)
  ├── if (!matched) return
  ├── _focusPath = { target: matched.node, chain: matched.parents }
  └── _renderInteractionPath()
```

### Event: blur

```
_onBlur(e)
  │
  ├── _focusPath = null
  └── _renderInteractionPath()
```

### Event: mouseleave (on containerEl)

```
_onMouseLeave(e)
  │
  ├── _hoverPath = null
  └── _renderInteractionPath()
```

### _renderInteractionPath() — the core render function

```
_renderInteractionPath()
  │
  ├── if (!_focusPath && !_hoverPath)
  │     └── clear nodes below header
  │     └── panelEl.classList.add("entry-state")
  │     └── return
  │
  ├── panelEl.classList.remove("entry-state")
  │
  ├── pathNodes = _mergeInteractionPaths(_focusPath, _hoverPath)
  │     └── collect all unique nodes from both chains + targets
  │     └── sort by depth (shallowest first)
  │     └── mark each as "in-chain" or "active-target"
  │     └── target nodes get "active-target"
  │     └── parent nodes get "in-chain"
  │
  ├── clear nodes below context header
  │
  ├── for each pathNode (in depth order):
  │     └── create .assistant-node div
  │     └── set data-depth attribute
  │     └── add .active-target or .in-chain class
  │     └── render title + content
  │     └── if active-target AND node.expanded: render expanded content
  │     └── append to panelEl
  │
  └── _centerActiveNode()
        └── find first .active-target in panel
        └── scroll panel so it's vertically centered
```

### _matchNode(element) — selector matching

```
_matchNode(element)
  │
  ├── for each flatNode (deepest first):
  │     └── if node.selector starts with "#" or "[":
  │     │     try element.matches(node.selector)
  │     │     OR  element.closest(node.selector) !== null
  │     │
  │     └── if match found: return { node, parents }
  │
  └── return null
```

**Why deepest first**: If user hovers `#wiz-new-env-name`, that should match
the "Add env name" node, not the parent "Environments" section. Deepest-first
means specific wins over general.

### _flattenTree() — building the flat index

```
_flattenTree(children, parentChain) → flatNode[]
  │
  ├── for each child in children:
  │     ├── push { node: child, parents: [...parentChain] }
  │     └── recurse _flattenTree(child.children, [...parentChain, child])
  │
  └── result is ordered deepest-first for matching priority
```

**Key detail**: The flat list is sorted ALL leaves before parents. This is
achieved by reversing or by recursing children first.

### _resolve(text) — template variable resolution

```
_resolve(text)
  │
  ├── if (!text) return ''
  ├── return text.replace(/\{\{(\w+)\}\}/g, (match, name) => {
  │     const resolver = window._assistant.resolvers[name];
  │     return resolver ? resolver() : '';
  │   })
  └── return resolved string
```

### _centerActiveNode(panelEl) — scroll centering

```
_centerActiveNode()
  │
  ├── target = panelEl.querySelector('.assistant-node.active-target')
  ├── if (!target) return
  │
  ├── panelRect = panelEl.getBoundingClientRect()
  ├── targetRect = target.getBoundingClientRect()
  ├── targetCenter = targetRect.top + targetRect.height / 2
  ├── panelCenter = panelRect.top + panelRect.height / 2
  ├── offset = targetCenter - panelCenter
  │
  └── panelEl.scrollBy({ top: offset, behavior: 'smooth' })
```

### Dynamic children (environments, domains)

When a parent node has `dynamic: true` and `childTemplate`:

```
_renderDynamicChildren(parentNode)
  │
  ├── elements = containerEl.querySelectorAll(childTemplate.selector)
  │
  ├── for each element:
  │     ├── name = element.querySelector('[style*="font-weight:600"]')?.textContent
  │     │         OR element.textContent.trim()
  │     ├── create synthetic node from template
  │     │     { id: parentNode.id + '-dyn-' + i, title: name, ... }
  │     └── add to flatNodes with parent chain including parentNode
  │
  └── these synthetic nodes participate in matching normally
```

**When does this run?** During `_flattenTree()` — when we encounter a dynamic
node, we query the DOM immediately and create the synthetic children.

### Risks and failure diagnostics

| Risk | Symptom | How to diagnose |
|------|---------|-----------------|
| JSON fetch 404 | Panel stays in entry state forever | Console: `GET .../assistant-catalogue.json 404` |
| JSON parse error | Same as above | Console: `SyntaxError: Unexpected token` |
| No context match | `_currentCtx` is null | Console: engine should log `"No context found for: wizard/welcome"` |
| Selectors miss | Hover does nothing | Console: engine should log `"No match for: [element tag/id]"` |
| Panel element missing | Nothing renders | Console: `"Panel element #assistant-panel not found"` |
| Entry state not centered | Header at top of panel | Check `.entry-state` class is set, check CSS `justify-content: center` |
| Scroll centering jitters | Panel bounces on each hover | Need to debounce or check if already centered |
| Focus/hover merge wrong | Duplicate nodes shown | Check `_mergeInteractionPaths` dedup logic by node.id |
| Dynamic children stale after add/remove | Old env shown in panel | `refresh()` should re-flatten tree |
| Template vars show raw `{{envCount}}` | Resolver not registered | Check resolver registration timing |
| Listeners leak on step change | Multiple listeners fire | `_detachListeners()` must remove all event refs |

---

## Deliverable 3: Dashboard include

### File: `src/ui/web/templates/dashboard.html`

Add this line BEFORE the wizard include (line 53):

```jinja2
{% include 'scripts/_assistant_engine.html' %}
```

**Why before wizard?** The wizard's `renderWizard()` calls `window._assistant.activate()`.
The engine must be defined before the wizard script runs. Since scripts execute
in include order, the engine include must come first.

**Exact location**: After line 52 (`{% include 'scripts/_commands.html' %}`),
before line 53 (`{% include 'scripts/_wizard.html' %}`).

### Risk

| Risk | Symptom | How to diagnose |
|------|---------|-----------------|
| Include after wizard | `window._assistant` is undefined when `renderWizard()` runs | Console: `Cannot read property 'activate' of undefined` |
| Typo in filename | Jinja2 `TemplateNotFound` error on page load | Server console: 500 error |

---

## Implementation order

1. **Create `assistant-catalogue.json`** with `wizard/welcome` context
2. **Create `_assistant_engine.html`** with the full engine IIFE
3. **Add include to `dashboard.html`** before `_wizard.html`
4. **Verify manually**: load wizard, check console, hover elements

---

## Test checklist

| Test | Expected result |
|------|-----------------|
| Open wizard step 1 | Panel shows context header centered (entry state) |
| Hover "Project Name" input | Panel shows: context header + "Project Name" node (active, with expanded) |
| Move hover away from all elements | Panel returns to entry state |
| Click into "Description" textarea | Panel shows: context header + "Description" node (active) |
| While focused on Description, hover "Repository" | Both "Description" (focus) and "Repository" (hover) shown |
| Hover an environment row | Panel shows: context header + "Environments" (in-chain) + env row (active) |
| Hover "Add domain" input | Panel shows: context header + "Domains" (in-chain) + "Add domain" (active) |
| Switch to step 2 | Panel clears, shows new context (if authored) or stays empty |
| Resize window below 1080px | Panel hidden, wizard takes full width |
| Console | No errors, no warnings in production mode |

---

## Files created/modified

| File | Action |
|------|--------|
| `src/ui/web/static/data/assistant-catalogue.json` | **CREATE** |
| `src/ui/web/templates/scripts/_assistant_engine.html` | **CREATE** |
| `src/ui/web/templates/dashboard.html` | **MODIFY** — add 1 include line |
