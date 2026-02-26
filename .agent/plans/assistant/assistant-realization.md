# Assistant — Full Realization

> Written after completing 4 scenarios that walked through the assistant's
> actual behavior from the user's perspective. This document captures what
> the assistant IS, how it reasons, and the architectural decision to drive
> it from an external superstructure rather than hardcoded DOM attributes.

---

## What the assistant IS

The assistant is a **full-height side panel** that shows contextual help
driven by user interaction — not a tooltip, not a single message, not a chat.

Every visible element on the page has a corresponding entry **in the
superstructure**, but the panel only shows content relevant to the current
interaction. On page entry, only the step context is shown. As the user
hovers or focuses elements, the panel builds content along the interaction
path — the element itself plus its full parent chain. The panel is a
colleague standing next to you, narrating what you're looking at.

### Core behavior

1. **Content is event-driven** — the panel shows content based on hover
   and focus events. On page entry, only the step context (header + content)
   is visible. As the user interacts, the panel builds up content along the
   interaction path.

2. **Parent chain cascades** — hovering or focusing an element shows that
   element's content AND the content of every parent up to the step context.
   For example, hovering a specific environment shows the Environments
   section content and the hovered environment's content.

3. **Focus and hover coexist** — if the user has focus on one element
   (e.g., clicked into an input) and hovers another, both elements and
   their parent chains are shown simultaneously.

4. **Step context persists** — the top of the panel always shows where the
   user is: which wizard step, which modal, which tab. This never disappears
   when drilling into deeper elements.

5. **Scroll centering** — when the user hovers or focuses an element,
   the panel scrolls so that element's content is **vertically centered**
   in the panel viewport. Parent chain above, additional content below.
   The active target is the visual anchor.

---

## How the assistant talks

The assistant speaks like a helpful colleague, not a reference manual.

### Rules

- **Conversational** — "Good to have", "Think of them as", "You've got 2 set
  up so far", "Take your time — this is the heart of your K8s configuration."
- **Never restate the visible** — don't echo field values, badge text, or
  status labels. Explain what they MEAN.
- **Explain consequences** — "If it exceeds memory limit, it gets OOM-killed",
  "3 × 15s = 45 seconds of failures before action."
- **Cross-reference** — link related elements. kubectl missing explains why
  K8s shows "not installed". Multi-env banner connects to environments from
  step 1. Compose services connect to K8s deployments.
- **Teach** — explain K8s concepts, security implications, operational
  tradeoffs. The user may not know what a QoS class is.
- **Never lie or generalize** — development ≠ local. Docker daemon offline
  ≠ blocker. Only say things that are true.
- **Silence is better than noise** — if there's nothing useful to add for an
  element, don't force content.

---

## How the reasoning works

The assistant doesn't look at a single element in isolation. It reasons
across three dimensions simultaneously:

### 1. Vertical — Where am I in the hierarchy?

```
Wizard                              (application context)
  └── Step 5: Integrations          (step context)
        └── INTEGRATIONS section    (section context)
              └── Docker card       (instance context)
                    └── Full Setup  (element context)
```

Every level contributes to the output. The step context tells the user
where they are in the journey. The section context explains what this
group of things is. The instance context explains this specific thing.
The element context explains the action they're about to take.

### 2. Horizontal — What else exists at this level?

When looking at Docker, the assistant is aware of the OTHER integrations:
CI/CD is ready, Git is ready, GitHub is ready, Pages is ready, K8s needs
kubectl, Terraform needs config. This awareness lets the assistant say
things like "2 of 7 still need setup" without the user counting.

### 3. Forward — What comes next?

The assistant knows the wizard flow. When explaining environments in step 1,
it says "pre-selected when you define secrets in step 3." When explaining
compose services in K8s detect, it says "you'll make this choice in
Configure." The assistant guides the user's journey forward.

---

## The Superstructure — external JSON, not hardcoded attributes

### The problem with hardcoded attributes

The previous approach scattered `data-guide` attributes across HTML templates:

```html
<h2 data-guide="step:welcome">👋 Project Configuration</h2>
<div data-guide="field:name">
    <label>Project Name</label>
    <input id="wiz-name">
</div>
```

Problems:
1. **Content is nowhere** — the attribute says "field:name" but the actual
   assistant text ("This is your project's identity — it'll show up in
   Docker labels...") must live somewhere else anyway.
2. **Hierarchy is implicit** — you have to walk the DOM to figure out
   nesting. Is "field:name" inside "step:welcome"? Only the DOM knows.
3. **Pollutes templates** — every element gets an attribute. Templates
   become cluttered with guide metadata that has nothing to do with the
   element's function.
4. **Hard to review** — to see what the assistant says for a page, you'd
   have to trace attributes across multiple template files and match them
   to content definitions.
5. **Fragile** — if the DOM structure changes, the attribute hierarchy
   breaks. Renaming an element breaks the guide.

### The solution: a superstructure file

All assistant knowledge lives in **one external JSON file** — a tree that
mirrors the UI hierarchy with all content pre-defined.

```
static/data/assistant-superstructure.json
```

The superstructure is a tree of nodes. Each node has:

```json
{
  "id": "wizard/welcome",
  "title": "🧙 Welcome to the Setup Wizard",
  "content": "6 steps to configure your project...",
  "selector": "#wizard-body[data-step='welcome']",
  "children": [
    {
      "id": "project-name",
      "title": "Project Name *",
      "content": "This is your project's identity...",
      "selector": "#wiz-name",
      "expanded": "...full detail when focused...",
      "children": []
    },
    {
      "id": "description",
      "title": "Description",
      "content": "Good to have...",
      "selector": "#wiz-desc",
      "children": []
    },
    {
      "id": "environments",
      "title": "📋 Environments",
      "content": "Environments scope your secrets and variables...",
      "selector": "#wiz-environments",
      "children": [
        {
          "id": "env-development",
          "title": "development · default",
          "content": "The development environment is where...",
          "selector": "[data-env='development']",
          "expanded": "...full detail when hovered...",
          "children": []
        },
        {
          "id": "env-production",
          "title": "production",
          "content": "Production environment — live-facing...",
          "selector": "[data-env='production']",
          "children": []
        }
      ]
    }
  ]
}
```

### How the engine uses the superstructure

1. **Context change** — when the user navigates to a wizard step, opens a
   modal, or switches tabs, the engine looks up the matching top-level node
   in the superstructure (e.g., `wizard/welcome`, `wizard/integrations`,
   `k8s-setup/configure`).

2. **Render the step context** — the engine renders only the context
   header (title + content). The panel starts clean — no children visible.

3. **Focus/hover mapping** — when the user hovers or focuses a DOM element,
   the engine matches it to a superstructure node using the `selector`
   field. The matched node's content is rendered, along with the content
   of every parent node in the chain up to the context root. This builds
   the panel content dynamically based on interaction.

4. **Coexistence** — focus and hover are tracked independently. If the
   user has focus on element A and hovers element B, both paths are
   rendered. Shared parents appear once.

4. **Scroll sync** — the panel scrolls to keep the focused/hovered node's
   assistant content aligned with the corresponding element on the page.

5. **Dynamic content** — some nodes need runtime data (e.g., "You've got 2
   environments set up", "8 of 15 tools available"). The superstructure
   can include template variables or resolver functions that the engine
   evaluates at render time.

### Why this is better

| Aspect | Hardcoded attributes | Superstructure file |
|--------|---------------------|-------------------|
| Content location | Scattered in catalogue JS files + DOM attributes | One JSON file |
| Hierarchy | Implicit (DOM walking) | Explicit (JSON tree) |
| Template pollution | Every element needs data-guide | Minimal — existing IDs + rare data-assist |
| Reviewability | Trace across multiple files | Read one file top to bottom |
| Editability | Edit HTML + JS + CSS | Edit one JSON file |
| Fragility | DOM changes break hierarchy | Selector changes are localized |
| Runtime cost | DOM walking on every event | JSON lookup — fast |

### What stays in the DOM

Not everything moves to the superstructure. Some things still need DOM
presence:

1. **Element IDs** — already exist for form functionality. The
   superstructure references them via selectors. No new attributes needed
   for elements that already have IDs.

2. **Minimal data attributes** — for elements that don't have IDs and can't
   be targeted by CSS selectors alone, a `data-assist` attribute provides
   the mapping key. But this is rare — most elements already have IDs or
   can be targeted via parent + class selectors.

3. **Dynamic elements** — elements generated at runtime (e.g., environment
   rows, integration cards) may need `data-assist` attributes since their
   presence is dynamic and the superstructure needs a way to find them.

### Content organization

The superstructure is a single catalogue file containing all contexts:

```
static/data/assistant-catalogue.json
```

Each context is an object in the top-level array, keyed by `context` ID
(e.g. `"wizard/welcome"`, `"k8s/detect"`). The engine loads once and
indexes by context key.

---

## Summary of what we learned from the scenarios

| Scenario | Context | Key lesson |
|----------|---------|------------|
| 1. Wizard Step 1, hover development | Simple page, few sections | Panel shows step context + Environments section + hovered development child. Content builds along interaction path. |
| 2. Wizard Step 5, hover Docker | Complex page, many sections | Cross-references between related elements. Don't overreact to informational statuses. |
| 3. K8s Detect (modal) | Modal context, read-only scan | Modal pushes context stack. Detection data explained through lens of what's coming next (Configure). |
| 4. K8s Configure (modal) | Deep nesting, sub-sub-sub elements | 4+ levels of nesting work fine. Each level adds real value. Infrastructure decisions explained with options. |

### The assistant is NOT:
- A tooltip that appears on hover
- A single message that changes with focus
- A chatbot that responds to questions
- A validation engine that shows errors
- A documentation browser

### The assistant IS:
- A persistent side panel that shows contextual help along the interaction path
- A colleague explaining every part of the page
- A teacher that explains concepts and consequences
- A guide that connects current context to the journey
- A reference that uses the full height and depth available
