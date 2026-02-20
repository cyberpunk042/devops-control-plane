# Layer 1 — Data (Superstructure)

> The assistant's knowledge base. External JSON files that describe the
> entire UI hierarchy with pre-written assistant content for every element.

---

## What this layer IS

A set of JSON files — one per UI context (wizard step, modal step, etc.) —
that encode:
1. The **hierarchy** of elements on each page
2. The **assistant content** for each element (what to say)
3. The **selectors** for mapping DOM elements to tree nodes
4. **Template variables** for dynamic runtime content

This is where ALL assistant intelligence lives. The engine (L2) is a dumb
renderer — it reads these files and puts them on screen. The smarts are here.

---

## Analysis — What exists in the DOM today

### Wizard step 1 (Welcome) — IDs available

| Element | ID/Selector | Notes |
|---------|-------------|-------|
| Project Name input | `#wiz-name` | Exists |
| Description textarea | `#wiz-desc` | Exists |
| Repository input | `#wiz-repo` | Exists |
| Domains container | `#wiz-domains` | Exists |
| Add domain input | `#wiz-new-domain` | Exists |
| Environments container | `#wiz-envs` | Exists |
| Add env name input | `#wiz-new-env-name` | Exists |
| Add env desc input | `#wiz-new-env-desc` | Exists |
| Environment rows | No unique ID | Generic divs inside `#wiz-envs` |
| Domain badges | No unique ID | Spans inside `#wiz-domains` |

### K8s wizard step 2 (Configure) — Dynamic IDs

K8s uses dynamically generated IDs with index patterns:
- `k8s-svc-vol-type-{i}-{j}` — volume type for service i, volume j
- `k8s-infra-kind-{name}` — infra service kind dropdown
- `k8s-svc-init-name-{i}-{j}` — init container name
- `k8s-svc-sc-name-{i}-{j}` — sidecar container name

This means **selectors can't be hardcoded by index** — the superstructure
needs a way to match dynamic elements.

### Wizard step 5 (Integrations) — ID patterns

Integration cards are rendered by `_wizard_integrations.html`. Need to check
what IDs/classes exist on those cards.

### Summary of selector availability

| Context | Selector quality | Approach |
|---------|-----------------|----------|
| Wizard step 1 | Good — most elements have IDs | Direct `#id` selectors |
| Wizard step 2 (Modules) | Needs investigation | TBD |
| Wizard step 3 (Secrets) | Has `#wiz-env-vault-{name}`, `#wiz-enc-key-*` | Mix of fixed + dynamic |
| Wizard step 4 (Content) | Has `#wiz-content-folders` | Needs investigation |
| Wizard step 5 (Integrations) | Has `#wiz-int-body` | Cards need investigation |
| K8s Detect | Need to check `_raw_step1_detect.html` | TBD |
| K8s Configure | Dynamic IDs `k8s-svc-*-{i}-{j}` | Pattern-based matching |
| K8s Review | Need to check `_raw_step3_review.html` | TBD |

---

## Design Decisions

### 1. Static vs dynamic selectors

**Problem:** K8s configure generates elements with indexed IDs like
`k8s-svc-vol-type-0-1`. The superstructure can't hardcode these because
the services come from runtime data.

**Decision:** Two selector strategies:

**A. Static selectors** — for elements that always exist in the same place:
```json
{ "selector": "#wiz-name" }
```

**B. Pattern selectors** — for dynamically generated elements:
```json
{ "selector": "[id^='k8s-svc-vol-type-']" }
```

This matches any element whose ID starts with `k8s-svc-vol-type-`. The
assistant content applies to ALL instances — "Volume type controls how
K8s provisions storage for this container..." applies regardless of which
service's volume you're hovering.

**C. Closest-parent** — for elements without IDs that live inside an
identifiable parent:
```json
{ "selector": "#wiz-envs > div" }
```

Matches any direct child div of `#wiz-envs` — i.e., any environment row.

### 2. Dynamic nodes (runtime-generated children)

**Problem:** Environment rows, service cards, and module entries are created
dynamically. The superstructure can't list them ahead of time.

**Decision:** Use a `dynamic` flag on parent nodes:

```json
{
  "id": "environments",
  "title": "📋 Environments",
  "selector": "#wiz-envs",
  "content": "Environments scope your secrets...",
  "dynamic": true,
  "childTemplate": {
    "title": "{{name}}",
    "content": "Deployment environment. Configured in step 3.",
    "selector": "#wiz-envs > div"
  },
  "children": []
}
```

When `dynamic: true`, the engine:
1. Queries the DOM for elements matching `childTemplate.selector`
2. Creates synthetic child nodes from the template
3. Resolves `{{name}}` from the element's text content

This handles environments, modules, domain badges, compose services, etc.

### 3. Single catalogue file

**Decision:** One single file — `assistant-catalogue.json` — containing ALL
contexts. The file is structured as an array of context objects, each with
a `context` key (e.g. `"wizard/welcome"`, `"wizard/integrations"`,
`"k8s/detect"`) and its node tree.

Reasoning:
- Simpler — one fetch, one cache, one file to maintain
- The engine loads it once on boot and indexes by context key
- All contexts are available immediately — no lazy-loading complexity
- The file is reviewable as a single source of truth
- Content doesn't change during a session — it's static data

**File location:** `src/ui/web/static/data/assistant-catalogue.json`

The engine fetches it via `fetch('/static/data/assistant-catalogue.json')`
and builds a `Map<contextId, AssistantContext>` from the array.

### 4. Template variable syntax

**Decision:** `{{variableName}}` in content strings. Resolved by the
engine at render time using registered resolver functions.

Variables are simple DOM reads — never complex logic:
```
{{envCount}}    → document.querySelectorAll('#wiz-envs > div').length
{{toolCount}}   → count of .tool-badge elements
{{scanAge}}     → text content of scan time element
```

### 5. Content depth — `content` vs `expanded`

**Decision:** Two content tiers per node:

- `content` — shown when the node is on the interaction path (hovered/focused
  element or one of its parents). 1–3 sentences. What this element is and why
  it matters.
- `expanded` — shown only when this node is the directly hovered/focused
  target (not just a parent in the chain). Additional detail, options,
  consequences, tips.

Not every node needs `expanded`. Simple fields like "Port" may only need
`content`. Complex sections like "Resource Limits" or "Service Mesh" need both.

### 6. Separator control

**Decision:** `"separator": true` on a node means "draw a horizontal line
BEFORE this node." Used between major sections (e.g., between Domains and
Environments, between Application Deployments and Infrastructure Services).

---

## Node Schema — Final

```typescript
interface AssistantNode {
  id: string;                    // Unique within parent
  title: string;                 // Display label
  icon?: string;                 // Emoji prefix
  selector?: string;             // CSS selector for DOM mapping
  content: string;               // Assistant text (shown when on interaction path)
  expanded?: string;             // Additional text when focused (appended)
  separator?: boolean;           // Horizontal line before this node
  dynamic?: boolean;             // Children are generated from DOM
  childTemplate?: {              // Template for dynamic children
    title: string;               // With {{var}} placeholders
    content: string;
    expanded?: string;
    selector: string;            // Selector for each child element
  };
  children: AssistantNode[];     // Nested nodes
}

interface AssistantContext {
  context: string;               // Context ID (e.g. "wizard/welcome")
  title: string;                 // Top-level title
  icon?: string;                 // Top-level icon
  content: string;               // Step-level summary
  children: AssistantNode[];     // Page sections
}
```

---

## Context inventory — V1 (Wizard + Integrations focus)

All contexts live inside the single `assistant-catalogue.json` file.

### Must-have (covers the 4 scenarios we wrote)

| Context ID | Scope | Source scenario |
|------------|-------|-----------------|
| `wizard/welcome` | Wizard step 1 | Scenario 1 |
| `wizard/integrations` | Wizard step 5 | Scenario 2 |
| `k8s/detect` | K8s modal step 1 | Scenario 3 |
| `k8s/configure` | K8s modal step 2 | Scenario 4 |

### Follow-up (remaining wizard steps + modals)

| Context ID | Scope |
|------------|-------|
| `wizard/modules` | Wizard step 2 |
| `wizard/secrets` | Wizard step 3 |
| `wizard/content` | Wizard step 4 |
| `wizard/review` | Wizard step 6 |
| `k8s/review` | K8s modal step 3 |
| `docker/detect` | Docker modal step 1 |
| `docker/configure` | Docker modal step 2 |
| `docker/preview` | Docker modal step 3 |
| `integrations` | Integrations tab |

---

## File location

```
src/ui/web/static/data/
└── assistant-catalogue.json      ← single file, all contexts
```

Served at `/static/data/assistant-catalogue.json`.
The engine loads once and indexes by `context` key.

---

## Content authoring rules

These rules apply when writing the JSON content strings:

1. **Never restate the visible** — the user can see "Port: 8000". Don't
   say "The port is 8000." Say "The port your container listens on inside
   the pod."

2. **Explain consequences** — "If it exceeds memory limit, it gets
   OOM-killed and the pod restarts."

3. **Cross-reference** — "This is why Kubernetes shows 'not installed'
   in the DevOps Extensions below."

4. **Teach concepts** — "QoS classes are how K8s decides which pods to
   evict under pressure."

5. **Be accurate** — don't generalize. development ≠ local. Docker daemon
   offline ≠ blocker. Only state what is true.

6. **Conversational tone** — "You've got 2 set up so far." "Take your time."
   "Good to have." Not: "There are 2 environments configured."

7. **Silence > noise** — if there's nothing useful to add, keep content
   short. Not every field needs a paragraph.

8. **Use \n for line breaks** — JSON content strings use `\n` for newlines,
   rendered with `white-space: pre-line` in CSS.

---

## Resolver registry (dynamic content)

Resolvers are simple functions registered on `window._assistant.resolvers`.
They read the DOM and return a string.

### V1 resolvers

| Variable | Returns | Used in context |
|----------|---------|----------------|
| `envCount` | Number of environment rows | `wizard/welcome` |
| `domainCount` | Number of domain badges | `wizard/welcome` |
| `toolCount` | "8 of 15" format | `wizard/integrations` |
| `scanAge` | Scan timestamp text | `wizard/integrations` |
| `serviceCount` | Number of compose services | `k8s/detect` |
| `appCount` | Application service count | `k8s/configure` |
| `infraCount` | Infrastructure service count | `k8s/configure` |

Each resolver is ~1–3 lines of DOM reading. No business logic.

---

## Risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Catalogue gets stale relative to UI changes | Assistant says wrong things | Include catalogue path in template comments so devs know to update |
| Selectors don't match after refactors | Nodes fail to highlight | Engine logs unmatched selectors in dev mode for debugging |
| Dynamic element patterns are too broad | Wrong node highlights | Use specific pattern prefixes (e.g., `[id^='k8s-svc-vol-']`) not generic classes |
| Catalogue file gets large | Hard to review | Use clear section comments, context IDs as anchors. File is static data — size is manageable |
| Template variables resolve to empty | Content shows `{{envCount}}` literally | Engine shows empty string for unresolved vars in production, logs warning in dev |

---

## Implementation tasks

1. **Create file** — `src/ui/web/static/data/assistant-catalogue.json`
2. **Author `wizard/welcome` context** — from actual HTML in `_wizard_steps.html` (lines 10-110)
3. **Author `wizard/integrations` context** — from actual HTML in `_wizard_integrations.html`
4. **Author `k8s/detect` context** — from actual HTML in `k8s_wizard/_raw_step1_detect.html`
5. **Author `k8s/configure` context** — from actual HTML in `k8s_wizard/_raw_step2_*.html`
6. **Author remaining wizard contexts** — modules, secrets, content, review
7. **Author `integrations` tab context** — from `_tab_integrations.html`
8. **Verify selectors** — test each selector against live DOM to confirm matches
9. **Identify gaps** — elements without IDs that need `data-assist` attributes
10. **Add minimal `data-assist` attributes** — only where no other selector works

All contexts go into the single `assistant-catalogue.json` file.
Task 8 must happen before L3 (Interaction) can work reliably.
