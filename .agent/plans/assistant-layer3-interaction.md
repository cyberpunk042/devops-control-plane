# Layer 3 — Interaction (Events + Matching)

> Hover/focus event handling, selector matching from DOM elements to
> superstructure nodes, debouncing, and scroll synchronization.

---

## What this layer IS

The bridge between user actions (hover, focus) and the tree state
(which node is expanded). It listens for DOM events on the content
container, matches the event target to a superstructure node, and
tells the engine to expand that node in the panel.

This also handles scroll synchronization — keeping the panel's scroll
position aligned with the content so the relevant node is visible.

All of this lives INSIDE the engine IIFE (`_assistant_engine.html`).
It's not a separate file — it's a set of functions within the engine.

---

## Analysis — Scroll contexts

### Wizard

The wizard content lives inside `#tab-wizard`, which is inside the main
page scroll (`.main` or `body`). The wizard-content div has `max-width:
700px` and is centered. There is no separate scroll container — the
whole page scrolls.

**Implication:** If the assistant panel sits next to `#wizard-body` in a
flex layout, BOTH scroll with the page. Scroll sync is free — they're in
the same scroll context.

**Concern:** The `.wizard-content` has `max-width: 700px`. Adding a panel
next to it means either:
- A) Removing the max-width and letting the flex layout handle widths
- B) Wrapping at a higher level

**Decision:** The `.assistant-layout` flex wrapper goes INSIDE
`.wizard-content`, replacing the `max-width` constraint with flex
children that have their own max-widths. The wizard body gets
`flex: 1; max-width: 700px;` and the panel gets `flex: 0 0 280px;`.

### Modals

The modal body (`.modal-body`) has its OWN scroll via `overflow-y: auto`.
The panel is injected inside `.modal-body` in a flex layout, so both
content and panel share the same scroll context.

**Implication:** Same-scroll-context again. No sync logic needed.

**Wait — is that right?** Let me think...

The modal body wraps everything. If we put content + panel side by side
inside modal-body, they scroll together vertically. But the content may
be much taller than the panel (or vice versa). If content is 2000px tall
and panel is 800px, scrolling down in the modal will scroll past the panel
content.

**Solution:** The panel should be `position: sticky; top: 0;` inside the
flex layout. This way, the panel sticks to the top of the visible area
while the content scrolls. The panel's own content can overflow with its
own scroll.

```css
.assistant-panel {
    flex: 0 0 280px;
    position: sticky;
    top: 0;
    align-self: flex-start;
    max-height: calc(100vh - 200px);  /* viewport minus header/footer */
    overflow-y: auto;
}
```

This works for BOTH wizard (page scroll) and modal (modal-body scroll)
because `position: sticky` works relative to the nearest scroll ancestor.

---

## Design Decisions

### 1. Event delegation

**Decision:** One `mouseover` and one `focusin` listener, delegated on
the content container element.

```javascript
function _attachListeners(containerEl) {
    const onMove = (e) => _onHover(e.target);
    const onFocus = (e) => _onFocus(e.target);
    const onLeave = () => _onLeave();

    containerEl.addEventListener('mouseover', onMove);
    containerEl.addEventListener('focusin', onFocus);
    containerEl.addEventListener('mouseleave', onLeave);

    _listeners = [
        [containerEl, 'mouseover', onMove],
        [containerEl, 'focusin', onFocus],
        [containerEl, 'mouseleave', onLeave],
    ];
}

function _detachListeners() {
    for (const [el, event, fn] of _listeners) {
        el.removeEventListener(event, fn);
    }
    _listeners = [];
}
```

**Why delegated?** The content container's children are dynamically rendered.
We can't attach listeners to individual elements — they don't exist at
attach time. Delegation on the container catches everything.

### 2. Debouncing

**Decision:**
- **Hover:** 150ms debounce. User moving across elements shouldn't cause
  rapid expand/collapse.
- **Focus:** Immediate (0ms). Focus is intentional — the user tabbed or
  clicked into a field. No delay.

```javascript
let _hoverTimer = null;

function _onHover(target) {
    clearTimeout(_hoverTimer);
    _hoverTimer = setTimeout(() => {
        const node = _matchNode(target);
        if (node) _expandNode(node.id);
    }, 150);
}

function _onFocus(target) {
    clearTimeout(_hoverTimer); // cancel pending hover
    const node = _matchNode(target);
    if (node) _expandNode(node.id);
}

function _onLeave() {
    clearTimeout(_hoverTimer);
    // Optional: collapse all after a delay
    // Or keep the last expanded node visible
    // Decision: keep last expanded. It's useful context.
}
```

### 3. Leave behavior

**Decision:** When the mouse leaves the content container, DO NOT collapse
the expanded node. The last context stays visible. Rationale:
- User may move to the panel to read the expanded content
- Collapsing on leave would cause flicker
- The expanded node provides useful "last context" even when idle

The node only collapses when a DIFFERENT node is expanded (via hover/focus
on another element).

### 4. Selector matching — algorithm

**Decision:** Match from most specific (deepest) to least specific (shallowest).

The flat node list is sorted by tree depth (deepest first). For each node:
1. Try `element.matches(selector)` — exact match
2. Try `element.closest(selector)` — element is inside the selector target

First match wins.

```javascript
function _flattenTree(tree) {
    const result = [];

    function walk(node, depth) {
        if (node.selector) {
            result.push({ id: node.id, selector: node.selector, depth });
        }
        // Dynamic children have _element reference
        if (node._element) {
            result.push({ id: node.id, _element: node._element, depth });
        }
        for (const child of (node.children || [])) {
            walk(child, depth + 1);
        }
    }

    for (const child of tree.children) {
        walk(child, 0);
    }

    // Sort deepest first → most specific match wins
    result.sort((a, b) => b.depth - a.depth);
    return result;
}

function _matchNode(element) {
    if (!_flatNodes) return null;

    for (const entry of _flatNodes) {
        // Dynamic children — check if element is inside the stored element
        if (entry._element) {
            if (entry._element === element || entry._element.contains(element)) {
                return entry;
            }
            continue;
        }

        // Selector-based matching
        try {
            if (element.matches(entry.selector)) return entry;
            if (element.closest(entry.selector)) return entry;
        } catch (e) {
            // Invalid selector — skip
        }
    }

    return null;
}
```

### 5. Expand/collapse mechanism

**Decision:** CSS class toggle. The engine adds `.active` to the matched
panel node div. CSS handles visibility of `.assistant-node-expanded`.

```javascript
function _expandNode(nodeId) {
    if (nodeId === _activeNodeId) return; // already expanded

    // Remove active from all
    if (_panelEl) {
        const prev = _panelEl.querySelector('.assistant-node.active');
        if (prev) prev.classList.remove('active');
    }

    // Add active to matched
    const target = _panelEl?.querySelector(
        `.assistant-node[data-node-id="${nodeId}"]`
    );
    if (target) {
        target.classList.add('active');
        _scrollPanelTo(target);
    }

    _activeNodeId = nodeId;
}
```

### 6. Scroll-to-node in panel

When a node is expanded, the panel should scroll to make that node
visible:

```javascript
function _scrollPanelTo(nodeEl) {
    if (!_panelEl) return;

    // Only scroll if the node is outside the visible area
    const panelRect = _panelEl.getBoundingClientRect();
    const nodeRect = nodeEl.getBoundingClientRect();

    if (nodeRect.top < panelRect.top || nodeRect.bottom > panelRect.bottom) {
        nodeEl.scrollIntoView({
            behavior: 'smooth',
            block: 'nearest'
        });
    }
}
```

**Note:** This scrolls the PANEL, not the page. The panel has its own
`overflow-y: auto` so `scrollIntoView` on a child scrolls the panel.

### 7. Panel click — allow interaction

**Problem:** If the user clicks inside the panel (e.g., to select text,
follow a link), we don't want that to trigger hover/focus matching.

**Decision:** The panel is OUTSIDE the content container. Event listeners
are on the content container, not on the panel. Panel clicks don't trigger
matching.

### 8. Matching ambiguity

**Problem:** An element might match multiple selectors. For example, an
input inside `#wiz-envs` matches both `#wiz-envs` (the container) and
the input's own selector.

**Decision:** Deepest match wins. The flat list is sorted by depth, so
if `#wiz-new-env-name` (depth 2) and `#wiz-envs` (depth 1) both match,
the input-specific node wins.

For `closest()` matches, the closest selector wins because `closest()`
returns the nearest ancestor — so clicking inside `#wiz-new-env-name`
will match that selector before matching `#wiz-envs`.

---

## Edge cases

### Dynamic elements added after render

**Problem:** K8s configure generates elements dynamically (e.g., user adds
a volume, an init container). These elements didn't exist when the tree
was rendered.

**Solution:** Pattern selectors (`[id^='k8s-svc-vol-']`) match dynamically
created elements because `element.matches()` checks current DOM, not the
state at render time. The flat node list contains the pattern selector by ID
prefix, and it matches new elements with that prefix.

Only the PANEL side is static — the content-to-node mapping works dynamically.

If the panel also needs to show new dynamic children, `_assistant.refresh()`
can be called to re-render the tree.

### Rapidly switching contexts

**Problem:** User clicks through wizard steps fast. JSON may still be loading.

**Solution:** Each `_loadAndRender()` call is async. If a new call comes in
before the previous finishes, the new one wins. Use a generation counter:

```javascript
let _renderGen = 0;

async function _loadAndRender(contextId, containerEl) {
    const gen = ++_renderGen;
    const tree = await _loadContext(contextId);

    // Stale — a newer call has started
    if (gen !== _renderGen) return;

    // ... proceed with render
}
```

### Elements without selectors

**Problem:** Some elements in the content area won't match any node.

**Solution:** No-op. The panel keeps its current state. No node expands
or collapses. This is fine — not every pixel of the page needs assistant
commentary.

### Panel taller than content (or vice versa)

**Problem:** If the assistant panel content is longer than the page content,
the layout looks unbalanced.

**Solution:** Sticky positioning + max-height + overflow scroll on the panel
handles this. The panel never extends past its max-height. If it has more
content, it scrolls independently.

---

## Functions table

| Function | Purpose | ~Lines |
|----------|---------|--------|
| `_attachListeners(containerEl)` | Delegates hover + focus on container | 15 |
| `_detachListeners()` | Removes stored listeners | 5 |
| `_onHover(target)` | Debounced hover handler | 8 |
| `_onFocus(target)` | Immediate focus handler | 5 |
| `_onLeave()` | Mouse leave — keeps last node | 3 |
| `_flattenTree(tree)` | Builds sorted flat node list | 20 |
| `_matchNode(element)` | Matches DOM element to tree node | 20 |
| `_expandNode(nodeId)` | Toggles `.active` class | 12 |
| `_scrollPanelTo(nodeEl)` | Scrolls panel to make node visible | 10 |
| **Total** | | **~98 lines** |

---

## Implementation tasks

1. **Implement event delegation** — `_attachListeners`, `_detachListeners`
2. **Implement flat tree builder** — `_flattenTree` with depth sorting
3. **Implement selector matching** — `_matchNode` with depth-first priority
4. **Implement expand/collapse** — CSS class toggle + scroll-to-node
5. **Implement debouncing** — 150ms hover, immediate focus
6. **Test with wizard step 1** — hover over fields, verify correct node expands
7. **Test with K8s configure** — hover over dynamic elements, verify pattern matching
8. **Test leave behavior** — confirm last node stays expanded

---

## Dependencies

| Depends on | For |
|------------|-----|
| L2 (Engine) | IIFE scope, `_panelEl`, `_currentTree`, `_flatNodes` state |
| L3 CSS (Presentation) | `.active` class styles, `sticky` positioning |
