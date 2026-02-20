# Layer 4 — Presentation (Visual Design)

> CSS for the assistant panel layout, node styling, depth indentation,
> expand/collapse animation, and responsive behavior.

---

## What this layer IS

CSS additions to `admin.css` that style the assistant panel and its contents.
No new CSS files — everything goes into the existing stylesheet to stay
consistent with the project's design system.

The panel must feel like a natural part of the UI — same fonts, same colors,
same spacing scale. It's quiet, never competing with the main content.

---

## Analysis — Design system tokens

The project uses a dark theme with these tokens:

### Colors
| Token | Value | Use |
|-------|-------|-----|
| `--bg-primary` | `hsl(225, 25%, 8%)` | Page background |
| `--bg-secondary` | `hsl(225, 22%, 11%)` | Header/sidebar |
| `--bg-card` | `hsl(225, 20%, 13%)` | Cards |
| `--bg-card-hover` | `hsl(225, 20%, 16%)` | Card hover |
| `--bg-inset` | `hsl(225, 18%, 9%)` | Inset inputs |
| `--border-subtle` | `hsl(225, 12%, 15%)` | Borders |
| `--text-primary` | `hsl(220, 20%, 92%)` | Main text |
| `--text-secondary` | `hsl(220, 12%, 60%)` | Secondary text |
| `--text-muted` | `hsl(220, 10%, 42%)` | Muted text |
| `--accent` | `hsl(210, 100%, 62%)` | Accent blue |
| `--accent-glow` | `hsla(210, 100%, 62%, 0.15)` | Accent bg |

### Spacing
| Token | Value |
|-------|-------|
| `--space-xs` | 0.25rem |
| `--space-sm` | 0.5rem |
| `--space-md` | 1rem |
| `--space-lg` | 1.5rem |
| `--space-xl` | 2rem |

### Typography
| Token | Value |
|-------|-------|
| `--font-sans` | 'Inter', -apple-system, system-ui, sans-serif |
| `--font-mono` | 'JetBrains Mono', 'Fira Code', monospace |

### Existing patterns
- Cards: `bg-card`, rounded 12px, 1px border-subtle
- Inputs: `bg-inset`, rounded 8px, border-subtle
- Labels: 0.85rem, font-weight 600, text-secondary
- Muted descriptions: 0.78rem, text-muted
- `.wizard-content` has `max-width: 700px; margin: 0 auto`

---

## Design Decisions

### 1. Panel width

**Decision:** 280px on desktop, hidden below 1100px.

280px is enough to show 1–3 sentences per line at 0.78rem. It's narrow
enough not to compress the wizard content significantly (700px → still
comfortable on a 1200px+ screen).

### 2. Panel visual weight

**Decision:** Transparent background, subtle left border, muted text.

The panel should be QUIET. Not a card, not a box — just text floating
next to the content with a thin border separating it. The active node
gets a slight accent treatment, but everything else is subdued.

### 3. Depth indentation

**Decision:** 14px per depth level, via `padding-left` set inline by JS.

14px is enough to show hierarchy without wasting horizontal space in a
280px panel. At 14px:
- Depth 0: 0px (top-level sections)
- Depth 1: 14px (sub-sections)
- Depth 2: 28px (instances)
- Depth 3: 42px (fields)

Max practical depth in our scenarios is 4 (42px), leaving ~238px for
text — still comfortable.

### 4. Active node treatment

**Decision:** Accent-colored left border + text promotion from muted →
secondary. Expanded content fades in.

No heavy background changes, no card elevation. Just a 2px left border
in accent blue and the text becoming slightly more readable.

### 5. Layout modification for wizard

**Decision:** Keep `.wizard-content` but change it from `max-width: 700px`
to a flex container when the assistant is active.

```css
.wizard-content.has-assistant {
    max-width: none;
    display: flex;
    gap: var(--space-lg);
    justify-content: center;
}

.wizard-content.has-assistant .card.full-width {
    flex: 1;
    max-width: 700px;
}
```

The `.has-assistant` class is toggled by the engine when enabled/disabled.
When disabled, `.wizard-content` reverts to its original `max-width: 700px`
centered layout.

---

## CSS Specification

```css
/* ══════════════════════════════════════════════════════════════════
 *  Assistant Panel
 * ══════════════════════════════════════════════════════════════════ */

/* ── Layout ────────────────────────────────────────────────────── */

.assistant-layout {
    display: flex;
    gap: var(--space-lg);
}

.assistant-layout > :first-child {
    flex: 1;
    min-width: 0;  /* prevent flex child overflow */
}

/* ── Panel ─────────────────────────────────────────────────────── */

.assistant-panel {
    flex: 0 0 280px;
    position: sticky;
    top: var(--space-md);
    align-self: flex-start;
    max-height: calc(100vh - 160px);
    overflow-y: auto;
    overflow-x: hidden;
    border-left: 1px solid var(--border-subtle);
    padding-left: var(--space-md);

    /* Quiet scroll */
    scrollbar-width: thin;
    scrollbar-color: var(--border-subtle) transparent;
}

.assistant-panel::-webkit-scrollbar {
    width: 4px;
}

.assistant-panel::-webkit-scrollbar-thumb {
    background: var(--border-subtle);
    border-radius: 2px;
}

.assistant-panel::-webkit-scrollbar-track {
    background: transparent;
}

/* ── Context header ────────────────────────────────────────────── */

.assistant-context-header {
    margin-bottom: var(--space-md);
    padding-bottom: var(--space-sm);
    border-bottom: 1px solid var(--border-subtle);
}

.assistant-context-title {
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 4px;
}

.assistant-context-content {
    font-size: 0.75rem;
    line-height: 1.5;
    color: var(--text-muted);
}

/* ── Node ──────────────────────────────────────────────────────── */

.assistant-node {
    position: relative;
    margin-bottom: var(--space-sm);
    padding: 4px 0 4px 0;
    border-left: 2px solid transparent;
    transition: border-color 200ms ease, background 200ms ease;
}

.assistant-node-title {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text-muted);
    margin-bottom: 2px;
    line-height: 1.3;
}

.assistant-node-content {
    font-size: 0.74rem;
    line-height: 1.55;
    color: var(--text-muted);
    white-space: pre-line;
}

/* ── Active node ───────────────────────────────────────────────── */

.assistant-node.active {
    border-left-color: var(--accent);
    padding-left: var(--space-sm);
}

.assistant-node.active .assistant-node-title {
    color: var(--accent);
}

.assistant-node.active .assistant-node-content {
    color: var(--text-secondary);
}

/* ── Expanded content ──────────────────────────────────────────── */

.assistant-node-expanded {
    max-height: 0;
    overflow: hidden;
    opacity: 0;
    transition: max-height 250ms ease, opacity 200ms ease 50ms;
    font-size: 0.74rem;
    line-height: 1.55;
    color: var(--text-secondary);
    white-space: pre-line;
    margin-top: 0;
}

.assistant-node.active .assistant-node-expanded {
    max-height: 500px;  /* generous max for transition */
    opacity: 1;
    margin-top: var(--space-xs);
}

/* ── Separator ─────────────────────────────────────────────────── */

.assistant-separator {
    border: none;
    border-top: 1px solid var(--border-subtle);
    margin: var(--space-sm) 0;
}

/* ── Wizard layout override when assistant is active ───────────── */

.wizard-content.has-assistant {
    max-width: none;
}

.wizard-content.has-assistant > .card.full-width {
    display: flex;
    gap: var(--space-lg);
}

.wizard-content.has-assistant > .card.full-width > #wizard-body {
    flex: 1;
    max-width: 700px;
}

/* ── Modal layout when assistant is active ─────────────────────── */

.modal-body.has-assistant {
    display: flex;
    gap: var(--space-lg);
}

.modal-body.has-assistant > .assistant-layout {
    flex: 1;
    display: flex;
    gap: var(--space-lg);
}

/* ── Responsive ────────────────────────────────────────────────── */

@media (max-width: 1100px) {
    .assistant-panel {
        display: none;
    }

    .wizard-content.has-assistant {
        max-width: 700px;
    }

    .wizard-content.has-assistant > .card.full-width {
        display: block;
    }
}

/* ── Print ─────────────────────────────────────────────────────── */

@media print {
    .assistant-panel {
        display: none;
    }
}
```

---

## Visual hierarchy

```
┌─────────────────────────────────────────────────────────────────────┐
│  WIZARD CONTENT (700px)                │  ASSISTANT PANEL (280px)   │
│                                        │                            │
│  👋 Project Configuration              │  🧙 Welcome to Setup       │
│                                        │  6 steps to configure...   │
│  Project Name *                        │  ─────────────────────     │
│  ┌─────────────────────────────┐       │  Project Name *            │
│  │ my-awesome-project          │       │  Your project's identity   │
│  └─────────────────────────────┘       │                            │
│                                        │  Description               │
│  Description                           │  Good to have...           │
│  ┌─────────────────────────────┐       │                            │
│  │                             │       │  Repository                │
│  └─────────────────────────────┘       │  Connects to Git remote... │
│                                        │                            │
│  Repository                            │  ─────────────────────     │
│  ┌─────────────────────────────┐       │  📂 Domains                │
│  │ github.com/user/project     │       │  Logical groupings for...  │
│  └─────────────────────────────┘       │                            │
│                                        │  ─────────────────────     │
│  📂 Domains                            │  📋 Environments           │
│  [library] [ops] [docs]                │  ┃ Scope your secrets...   │
│  ┌──────────┐ [+ Add]                  │  ┃ You've got 2 set up.   │
│                                        │  ┃                         │
│  📋 Environments                       │  ┃  development · default  │
│  ┌─ development ─ default ──────┐      │  ┃  Where your team builds │
│  │  local development            │      │  ┃  and iterates. It       │
│  └──────────────────────────────┘      │  ┃  typically involves:     │
│  ┌─ production ─────────────────┐      │  ┃  • Test credentials...   │
│  │  live-facing                  │      │  ┃  • Debug-level...        │
│  └──────────────────────────────┘      │  ┃                         │
│  ┌──────────┐ ┌──────────┐ [+ Add]     │  ┃  production             │
│                                        │  ┃  Live-facing, real...    │
│  💡 Click Next to continue.            │                            │
└─────────────────────────────────────────────────────────────────────┘
                                             ┃ = accent left border
                                               (active node)
```

---

## Color usage summary

| Element | Color token | Opacity |
|---------|------------|---------|
| Panel border left | `--border-subtle` | 100% |
| Context title | `--text-secondary` | 100% |
| Context content | `--text-muted` | 100% |
| Node title (default) | `--text-muted` | 100% |
| Node content (default) | `--text-muted` | 100% |
| Node title (active) | `--accent` | 100% |
| Node content (active) | `--text-secondary` | 100% |
| Active left border | `--accent` | 100% |
| Expanded content | `--text-secondary` | 100% |
| Separator | `--border-subtle` | 100% |
| Scrollbar thumb | `--border-subtle` | 100% |

### Why no backgrounds?

The panel sits on the card background (`--bg-card`). Adding backgrounds
to nodes would create visual noise in a narrow column. The left border
accent is enough to indicate the active node. Backgrounds would compete
with the main content area.

---

## Typography scale

| Element | Size | Weight | Line-height |
|---------|------|--------|-------------|
| Context title | 0.82rem | 600 | 1.3 |
| Context content | 0.75rem | 400 | 1.5 |
| Node title | 0.75rem | 600 | 1.3 |
| Node content | 0.74rem | 400 | 1.55 |
| Expanded content | 0.74rem | 400 | 1.55 |

All sizes are intentionally smaller than the main content (which uses
0.85rem+ for labels, 0.9rem for inputs). The panel is supplementary —
it reads at a glance but doesn't compete.

---

## Animation

| Property | Duration | Easing | Trigger |
|----------|----------|--------|---------|
| Border color | 200ms | ease | `.active` added/removed |
| Background | 200ms | ease | `.active` added/removed |
| Expanded max-height | 250ms | ease | `.active` added |
| Expanded opacity | 200ms | ease | `.active` added (50ms delay) |

The expand animation uses `max-height` + `opacity` because `height: auto`
can't be transitioned. The `max-height: 500px` ceiling is generous enough
for any expanded content. The 50ms delay on opacity means the height
grows first, then the text fades in — a subtle but premium feel.

---

## Template modification: `_tab_wizard.html`

Current:
```html
<div class="wizard-content">
    <div class="card full-width">
        <div id="wizard-body"></div>
        <div class="wizard-nav">...</div>
    </div>
</div>
```

Modified:
```html
<div class="wizard-content">
    <div class="card full-width">
        <div id="wizard-body"></div>
        <div id="assistant-panel" class="assistant-panel"></div>
        <div class="wizard-nav" style="grid-column: 1 / -1;">...</div>
    </div>
</div>
```

The engine toggles `.has-assistant` on `.wizard-content` and the flex
behavior on `.card.full-width` to show/hide the panel layout.

When disabled: original layout, `max-width: 700px` centered.
When enabled: flex layout, wizard body at 700px + panel at 280px.

---

## Implementation tasks

1. **Add CSS rules** to the assistant section of `admin.css`
2. **Modify `_tab_wizard.html`** — add `#assistant-panel` div
3. **Test responsive** — verify panel hides below 1100px
4. **Test dark theme** — verify colors are readable on dark background
5. **Test scroll** — verify sticky positioning works in both wizard and modal
6. **Test animation** — verify expand/collapse feels smooth

---

## Dependencies

| Depends on | For |
|------------|-----|
| L2 (Engine) | Toggles `.has-assistant`, creates panel for modals |
| L3 (Interaction) | Toggles `.active` class on nodes |
| Existing design system | All color/spacing/typography tokens |
