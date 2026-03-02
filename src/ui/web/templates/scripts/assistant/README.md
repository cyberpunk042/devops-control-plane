# Assistant — Front-End Scripts

> **6 files · 3,622 lines · Event-driven contextual help side panel.**
>
> The assistant is an always-available side panel that reacts to the
> user's cursor position (hover/focus) and renders contextual guidance,
> state-aware breakdowns, and interactive explanations. Content is
> driven by a JSON catalogue (`assistant-catalogue.json`) combined with
> runtime **resolvers** that read live DOM state to produce dynamic HTML.

---

## How It Works

### Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│  dashboard.html                                                     │
│                                                                      │
│  {% include 'scripts/assistant/_engine.html' %}                     │
│  {% include 'scripts/assistant/_resolvers_shared.html' %}           │
│  {% include 'scripts/assistant/_resolvers_dashboard.html' %}        │
│  {% include 'scripts/assistant/_resolvers_docker.html' %}           │
│  {% include 'scripts/assistant/_resolvers_k8s.html' %}              │
│  {% include 'scripts/assistant/_resolvers_misc.html' %}             │
│                                                                      │
│  Each file is a standalone <script> (IIFE).                         │
│  Engine exposes window._assistant, resolvers register on it.        │
└────────────────────────────────────────────────────────────────────┘
```

### Three-Layer Content Model

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: Catalogue (static JSON)                                │
│                                                                   │
│  /static/data/assistant-catalogue.json                           │
│  ├── Contexts (e.g., "dashboard", "setup/docker")                │
│  │     └── Tree of nodes, each with:                             │
│  │           ├── selector: CSS selector matching DOM elements    │
│  │           ├── title: display name                              │
│  │           ├── content: description text                        │
│  │           ├── expanded: detailed HTML (shown on click)        │
│  │           ├── children: nested nodes                           │
│  │           ├── childTemplate: template for dynamic children    │
│  │           └── variants: conditional overrides                  │
│  │                                                                │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: Template Variables (resolvers)                          │
│                                                                   │
│  Text in catalogue can contain {{resolverName}} placeholders.    │
│  At render time, the engine calls window._assistant.resolvers    │
│  [resolverName]() to get live values from the DOM.               │
│  Example: "{{dockerServices}} services" → "3 services"           │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3: Enrichers (dynamic children)                            │
│                                                                   │
│  When catalogue nodes use childTemplate + dynamic: true,         │
│  the engine scans the DOM container for matching children.       │
│  For each child, it calls:                                        │
│     enrichers[parentNodeId](childEl, extractedName)              │
│  Enrichers return: { title?, content?, expanded? } to override   │
│  the template values with state-aware, per-element content.      │
└─────────────────────────────────────────────────────────────────┘
```

### Event-Driven Rendering Pipeline

```
User hovers/focuses a DOM element
    │
    ├── _onHover(e) or _onFocus(e)
    │     │
    │     ├── _matchNode(e.target)
    │     │     ├── Walk up from target to find closest selector match
    │     │     ├── Check flat index (deepest-first for specificity)
    │     │     └── Return: { node, parents[], matchedEl }
    │     │
    │     ├── _resolveVariant(node, element)
    │     │     ├── Check node.variants[] for matching conditions
    │     │     │     ├── when.textContains: text content match
    │     │     │     ├── when.dataAttr: data-attribute key/value match
    │     │     │     ├── when.hasSelector: CSS querySelector on element
    │     │     │     └── when.resolver: call resolver fn (.equals/.contains/.not)
    │     │     └── Return: merged node (variant overrides base)
    │     │
    │     └── _mergeInteractionPaths(focusPath, hoverPath)
    │           ├── Deduplicate shared parent nodes
    │           └── Return: sorted path (shallowest → deepest)
    │
    ├── _renderInteractionPath()
    │     ├── Render context header (breadcrumb)
    │     ├── For each node in path:
    │     │     ├── Resolve template variables via {{...}}
    │     │     ├── Render title, content, expanded
    │     │     ├── If dynamic children: scan DOM, call enricher
    │     │     └── Mark active/target node classes
    │     ├── _highlightSelectedStack()
    │     └── _highlightActiveEnv()
    │
    └── _centerActiveNode()
          └── Scroll panel to center the active node
```

### Variant Matching System

Variants allow catalogue nodes to change content based on DOM state:

```
Catalogue node (real example from assistant-catalogue.json):
{
  "selector": "#wiz-env-vault-list > div",
  "title": "{{name}}",
  "content": "Vault file for the {{name}} environment.",
  "variants": [
    {
      "when": { "textContains": "unlocked", "hasSelector": "[data-env-active]" },
      "expanded": "<state-card> 🔓 unlocked · ACTIVE — vault is decrypted …</state-card>"
    },
    {
      "when": { "textContains": "locked", "hasSelector": "[data-env-active]" },
      "expanded": "<state-card> 🔒 locked · ACTIVE — vault is encrypted …</state-card>"
    },
    {
      "when": { "textContains": "unlocked" },
      "expanded": "<state-card> 🔓 unlocked — vault is decrypted …</state-card>"
    }
  ]
}

Resolution logic (_resolveVariant, line 75):
1. Engine reads the hovered element
2. Tests each variant's "when" conditions (AND logic — all must pass)
3. Supported conditions: textContains, dataAttr, hasSelector, resolver
4. First match wins → overrides base content/expanded/title
5. No match → base content stays
```

### Dynamic Children Resolution

For dynamic DOM content (e.g., tool rows, Docker services), the
engine can't have pre-defined nodes. It uses enrichers:

```
Catalogue node:
{
  "id": "dash-tools",
  "selector": "#dashboard-tools-detail",
  "dynamic": true,
  "childTemplate": { "selector": "[data-tool-id]" }
}

At render time:
1. Engine finds all elements matching childTemplate.selector
2. Extracts display name from each element
3. Calls enrichers['dash-tools'](element, extractedName)
4. Enricher reads live DOM state (✅/❌, install button, etc.)
5. Returns { title, expanded } for the assistant card
```

---

## File Map

```
assistant/
├── _engine.html               Core engine — IIFE, event loop, public API (1,117 lines)
├── _resolvers_shared.html     Shared knowledge maps + parsers (151 lines)
├── _resolvers_dashboard.html  Dashboard enrichers: tools, integrations (143 lines)
├── _resolvers_docker.html     Docker resolvers + enrichers (1,256 lines)
├── _resolvers_k8s.html        K8s resolvers + enrichers (536 lines)
├── _resolvers_misc.html       Wizard, GitHub, Pages, Terraform, DNS, CI resolvers (419 lines)
└── README.md                  This file
```

---

## Per-File Documentation

### `_engine.html` — Core Engine (1,117 lines)

The brain of the assistant. An IIFE that exposes `window._assistant`.
Everything else in this domain hangs off the extension points it creates.

**State:**

| Variable | Type | Purpose |
|----------|------|---------|
| `_catalogue` | `Map` | Loaded JSON catalogue — `contextId → contextObj`. Fetched once on first `activate()`, then reused across context switches. The `Map` key is a slash-delimited context path like `"wizard/step1"` or `"setup/docker"`. |
| `_currentCtx` | `Object` | The active context node from the catalogue. Contains the root `children[]` tree and the computed `_flatNodes` index for this context. Replaced entirely on `activate()`. |
| `_flatNodes` | `Array` | Deepest-first flattened index of all catalogue nodes for this context. Built by `_flattenTree()`. The deepest-first ordering is what gives the assistant its specificity — when the user hovers inside a nested element, the most specific node wins. |
| `_focusPath` | `Object` | `{ target: node, chain: [parentNodes...], element: DOMElement }` for the currently keyboard-focused element. `null` when nothing is focused. Survives hover changes — focus is "sticky" until blur. |
| `_hoverPath` | `Object` | Same shape as `_focusPath` but for the mouse-hovered element. Cleared on `mouseleave`. Combined with `_focusPath` by `_mergeInteractionPaths()` — both show simultaneously if they point to different nodes. |
| `_stickyPath` | `Object` | Last committed hover path. Prevents the panel from going blank when the user moves the cursor from the content area to the panel itself. Updated by `_stickyDwellTimer` — only commits after 200ms on the same target to avoid transient crossings through wide elements. |
| `_panelEl` | `Element` | The `#assistant-panel` DOM element. Found by `_resolvePanel()`. |
| `_containerEl` | `Element` | The observed content area. All `mouseover`, `focusin`, `change` events are attached here. |
| `_enabled` | `boolean` | Global kill switch. When `false`, all event handlers short-circuit. |
| `_hoverDebounce` | `number` | `setTimeout` ID for the 50ms hover debounce. Prevents render spam during fast cursor sweeps. |
| `_dwellTimer` | `number` | 300ms dwell timer. After the user hovers an element for 300ms, any stale focus path is cleared. This prevents the focus path from lingering after a tab-then-mouse transition. |
| `_stickyDwellTimer` | `number` | 200ms sticky commit timer. Prevents a quick crossing through a wide element (e.g., a 3fr grid column) from overwriting a deliberately-hovered target. |
| `_listeners` | `Object` | References to all attached `addEventListener` callbacks. Used by `_detachListeners()` for clean removal. |

**Core Functions:**

| Function | What It Does |
|----------|-------------|
| `_loadCatalogue()` | `fetch('/static/data/assistant-catalogue.json')`, parse JSON, store as `Map` in `_catalogue`. Called once — subsequent `activate()` calls reuse the cached map. |
| `_resolvePanel()` | Find `#assistant-panel` in the DOM. If activating inside a modal, looks for a panel within the modal container first, then falls back to the global panel. |
| `_resolve(text)` | Regex-replaces `{{resolverName}}` placeholders in catalogue text with the return value of `window._assistant.resolvers[resolverName]()`. Called at render time for every `content` and `expanded` string. |
| `_resolveVariant(node, element)` | Engine's conditional content system. Tests each entry in `node.variants[]` against the matched DOM element using AND logic across 4 condition types (`textContains`, `dataAttr`, `hasSelector`, `resolver`). First matching variant's fields are merged over the base node — `content`, `expanded`, `title`, and `icon` can all be overridden. |
| `_resolveStaticVariant(node, matchedEl)` | Wrapper around `_resolveVariant` for non-dynamic nodes. Skips resolution entirely if the node has no variants (fast path for the majority of catalogue nodes). |
| `_flattenTree(children, parentChain)` | Recursively walks the context tree and builds a flat array. Each entry includes the node, its depth, and its parent chain. Dynamic nodes (`dynamic: true`) are resolved live via `_resolveDynamic()`. **Critical: deepest nodes are inserted first** — this ordering is what makes `_matchNode()` prefer specific matches over generic parents. |
| `_resolveDynamic(parentNode, grandParentChain, result)` | For catalogue nodes with `dynamic: true` + `childTemplate`, scans `_containerEl` for elements matching `childTemplate.selector`. For each match: extracts a display name (via `nameSelector`, font-weight heuristic, or first text node), applies `{{name}}` template interpolation, then calls the registered `enricher[parentNode.id]()` to get domain-specific content. Synthetic nodes are appended to `result[]`. |
| `_matchNode(element)` | Starting from the event target, walks up the DOM tree. At each level, checks the `_flatNodes` index for a catalogue node whose `selector` CSS selector matches. Returns `{ target: node, chain: [ancestorNodes...], element: matchedEl }`. Because `_flatNodes` is deepest-first, the first match is the most specific. |
| `_mergeInteractionPaths(focusPath, hoverPath)` | Combines focus and hover into one render list. If both point to the same node, deduplicates. If they point to different nodes, both are rendered — the hover target and the focus target each get `active-target` class. Shared parent nodes appear once with `in-chain` class. Output is sorted shallowest → deepest for visual hierarchy. |
| `_renderContextHeader()` | Renders the breadcrumb bar at the top of the panel showing the active context name (e.g., "🐳 Docker Setup"). |
| `_renderInteractionPath()` | **Main render loop (100+ lines).** Clears the panel inner container, then for each node in the merged path: resolves template variables, creates title/content/expanded DOM elements, and marks active nodes. If `_hoverPath` is `null` and `_stickyPath` exists, restores sticky to keep the panel populated. After DOM insert, calls `requestAnimationFrame` to center and highlight. |
| `_centerActiveNode()` | Scrolls the panel viewport so the deepest `.active-target` node is vertically centered. Uses `scrollIntoView` with `behavior: 'smooth'` and a calculated offset. |
| `_attachListeners(containerEl)` | Attaches all event handlers (`mouseover`, `focusin`, `focusout`, `mouseleave`, `change`, `wheel`) to the container and layout elements. Stores references in `_listeners` for clean detachment. |
| `_detachListeners()` | Removes all event handlers stored in `_listeners`. Called by `deactivate()` and before `activate()` reattaches for a new context. |

**Event Handlers:**

| Handler | Event | Behavior |
|---------|-------|----------|
| `_onHover(e)` | `mouseover` | Calls `_matchNode(e.target)`. If no match, clears hover. If match, debounces 50ms then calls `_renderInteractionPath()`. The debounce prevents render spam during fast cursor sweeps — only the final position renders. |
| `_onFocus(e)` | `focusin` | Same node-matching as hover, but stores to `_focusPath` (not `_hoverPath`). No debounce — keyboard navigation should feel instant. |
| `_onBlur(e)` | `focusout` | Clears `_focusPath`, re-renders with hover only. If both focus and hover were showing, the panel shrinks to hover-only content. |
| `_onMouseLeave(e)` | `mouseleave` (container) | Clears `_hoverPath` but **keeps `_stickyPath`**. This is the critical interaction: when the user moves the cursor TO the assistant panel (to read or scroll), the sticky path keeps the panel content stable. |
| `_onLayoutLeave(e)` | `mouseleave` (layout) | Fires when the cursor leaves the entire wizard layout (not just the content area). Adds a CSS class that fades out element highlights, but doesn't clear the panel. |
| `_onChange(e)` | `change` | Re-triggers `_renderInteractionPath()` on any `<select>` or `<input>` change inside the container. This makes variant conditions and resolver values update immediately when the user changes a form field. |
| `_onWheel(e)` | `wheel` | Traps scroll events within the assistant panel. At scroll boundaries (top or bottom), calls `preventDefault()` to stop the event from bubbling to the main page. Without this, scrolling past the end of the assistant panel would scroll the entire page. |

**Post-Render Hooks:**

| Function | What It Does |
|----------|-------------|
| `_highlightSelectedStack()` | After render, scans for a `.assistant-stack-detail` card in the panel. If found, adds the `stack-highlight` CSS class to the entire section containing the stack picker. Scrolls the panel to center this card. This creates the visual "spotlight" effect when the user's stack selection produces a rich breakdown. |
| `_highlightActiveEnv()` | After render, scans for state cards containing "· ACTIVE" text. Adds the `env-active-highlight` CSS class so the active environment visually stands out from inactive ones. |

**Public API:**

| Method | Signature | What It Does |
|--------|-----------|-------------|
| `activate` | `(contextId, containerEl, panelEl)` | Load catalogue (if not cached), resolve context by `contextId`, build `_flatNodes`, attach listeners, render initial entry state. The entry state shows the context title and root children but no interaction path. |
| `deactivate` | `()` | Detach all listeners, clear panel HTML, null out `_currentCtx`, `_focusPath`, `_hoverPath`, `_stickyPath`. Called on tab switch and modal close. |
| `refresh` | `()` | Re-flatten the tree (picking up new dynamic children from DOM mutations), then re-render the current interaction path. Called by integration setup wizards after form field changes that mutate the DOM. |
| `enable` | `()` | Set `_enabled = true`. Event handlers resume processing. |
| `disable` | `()` | Set `_enabled = false`. All event handlers short-circuit at the top. |

**Extension Points:**

| Property | Type | Purpose |
|----------|------|---------|
| `resolvers` | `{name: fn}` | Template variable resolvers. Catalogue text contains `{{name}}` → engine calls `resolvers[name]()` at render time. Return value (string or number) replaces the placeholder. |
| `enrichers` | `{id: fn}` | Dynamic children enrichers. When a catalogue node has `dynamic: true`, the engine calls `enrichers[nodeId](element, extractedName, parentNode)` for each DOM child. The enricher reads live DOM state and returns `{ title?, content?, expanded? }` to override the template defaults. |
| `_shared` | `Object` | Cross-file utility namespace. Populated by `_resolvers_shared.html`. Holds image parsing, port classification, and conflict detection functions used by Docker and K8s resolvers. |
| `_resolveElement` | `Element` | Set by the render loop to the currently matched DOM element. Available inside resolver functions via `window._assistant._resolveElement`. This is how resolvers like `dkInfraHover()` know which specific element the user is hovering — without it, they'd have no way to determine context. Cleared to `null` after render. |

### `_resolvers_shared.html` — Shared Knowledge Base (151 lines)

Registers data tables and parser functions on `window._assistant._shared`
for use by Docker and K8s resolvers. This file exists because both Docker
and K8s resolvers need the same image-parsing and port-classification logic —
without it, the same 60-line table would be duplicated across files.

**`dockerImageKnowledge` — 18 Runtime Entries:**

```
Map of Docker Hub repository name → { label, family, variantInfo }

Families: python, go, node, rust, java, ruby, elixir, php, c, swift,
          generic, webserver, database, cache, dotnet

Each family determines role classification in compose service analysis.
When a compose service uses `redis:7-alpine`, the parser knows it's
family "cache" → the enricher classifies the service role as "cache"
and applies the blue info card style instead of the green app style.
```

**`parseDockerImage(str)` — Image String Parser:**

```
Input:  "python:3.12-slim"
                │
                ├── Split on last ":"  → repo="python", tag="3.12-slim"
                ├── Split tag on "-"   → version="3.12", variant="slim"
                ├── Lookup repo in dockerImageKnowledge
                │     → label="Python", family="python"
                └── Lookup variant in variantInfo
                      → variantExplain="Debian-based minimal (~150MB)..."

Output: {
    raw: "python:3.12-slim",
    repo: "python",
    tag: "3.12-slim",
    version: "3.12",
    variant: "slim",
    label: "Python",
    family: "python",
    variantExplain: "Debian-based minimal (~150MB) — good balance..."
}
```

Unknown runtimes return `family: "unknown"` with a generic explanation.
The fallback logic handles common variant names (`slim`, `alpine`, `latest`)
even for unrecognized repositories.

**`portRanges` — 4 Port Classification Ranges:**

| Range | Min | Max | Icon | State Class | Purpose |
|-------|-----|-----|------|-------------|---------|
| Well-known | 0 | 1,023 | 🔒 | `state-warning` | IANA reserved, requires root |
| Common app | 1,024 | 9,999 | ✅ | `state-success` | Where most frameworks default |
| Registered | 10,000 | 49,151 | ℹ️ | `state-info` | Check for known service conflicts |
| Ephemeral | 49,152 | 65,535 | ⚠️ | `state-warning` | OS uses for outbound — avoid binding |

**`knownPorts` — 20 Well-Known Port Entries:**

Maps port numbers to `{ label, note }` with contextual guidance.
Example: port 5432 → `{ label: "PostgreSQL", note: "Database wire protocol — this should be an infrastructure service, not your app." }`.
Used by `dkPortHover`, `dkExposeHover`, `dkInfraPortHover`, and `k8sPortHover`.

**`classifyPort(num)` — returns the matching `portRanges` entry for a number.**

**`detectPortConflicts(hostPort, excludeRowEl)` — Cross-Service Conflict Scanner:**

```
1. Scan all .dk-port-row elements for matching host ports
2. Also scan window._infraOptions for enabled infra services
3. For each enabled infra service, check current port input values
4. Return: Array of service names that conflict
```

This is how the assistant warns "Port 5432 is already used by postgres"
when the user types 5432 into a service's host port field.

### `_resolvers_dashboard.html` — Dashboard Enrichers (143 lines)

Two enrichers for the dashboard tab's dynamic children. These are the
simplest enrichers in the system — they read status indicators from DOM
styling conventions and produce state-aware cards.

**`dash-tools` Enricher — Tool Status Detection:**

```
For each [data-tool-id] row in the dashboard tools section:

1. Read DOM:
   ├── font-weight:500 spans → tool display label
   ├── monospace-family spans → CLI binary name
   ├── span.textContent === "✅" → isAvailable = true
   ├── el.querySelector('button') → hasInstallBtn
   └── Walk up 2 levels → category header text

2. Build title: "Label · cli" (e.g., "Python · python")

3. State detection:
   ├── ✅ available → green "Installed on this system" card
   ├── ❌ + install button → yellow "Not found + Auto-install available" card
   └── ❌ + no button → yellow "Not found + Manual install required" card

4. Return: { title: "Python · python", expanded: "<state-card>..." }
```

**`dash-integrations` Enricher — Integration Status Detection:**

```
For each [data-int-id] row:

1. Read DOM:
   ├── font-weight:500 spans → integration label
   ├── font-weight:600 spans → status text ("Ready" / "Partial" / "Not set up")
   └── accent border/background → isSuggested

2. State detection:
   ├── status === "Ready" → ✅ green card
   ├── status === "Partial" → 🔶 yellow card + "some pieces in place" detail
   └── else → ⬜ yellow card + "Nothing detected" detail

3. If isSuggested → append 💡 "Suggested next step" info card

4. Return: { title: label, expanded: "<state-cards>..." }
```

### `_resolvers_docker.html` — Docker Domain (1,256 lines)

The largest resolver file — 2 enrichers + 24 resolvers = 26 total functions.
Covers the Docker wizard step, Docker Setup modal, and Docker dashboard cards.

**Two Enrichers:**

The `docker-section-dockerfiles` enricher examines each detected Dockerfile
by reading accent-colored spans (base images), muted spans (build stages),
and port annotations. For each base image, it calls `_shared.parseDockerImage()`
to produce runtime/version/variant pills. Multi-stage builds show stage count
and names. EXPOSE ports are extracted with a regex.

The `docker-section-compose-svcs` enricher classifies each compose service
by its **role** in the stack. It parses the image tag to determine the
`family` field, then maps it:

```
family "database" → role "database"     (blue info card)
family "cache"    → role "cache"        (blue info card)
family "webserver"→ role "proxy"        (blue info card)
image "(build)"   → role "application"  (green success card)
everything else   → role "application"  (green success card)
```

This classification drives both the card coloring and the topology summary
at the top of `dockerSvcAnalysis` (e.g., "Full stack (app + database + cache)").

**24 Template Variable Resolvers — Organized by Scope:**

**Dashboard card resolvers (8):** Read DOM pill elements by ID to extract
simple values for catalogue template interpolation.

| Resolver | DOM Source | Read Strategy |
|----------|-----------|---------------|
| `dockerDaemon` | `#wiz-docker-pill-daemon` | Check for "✓" in textContent |
| `dockerVersion` | `#wiz-docker-pill-daemon` | Regex `· (.+)` after the status icon |
| `dockerComposeCli` | `#wiz-docker-pill-compose-cli` | Check for "✓" in textContent |
| `dockerDockerfiles` | `#wiz-docker-pill-dockerfile` | Regex `(\d+)` from count pill |
| `dockerServices` | `#wiz-docker-pill-composefile` | Regex `(\d+)\s*svc` from pill |
| `dockerIgnoreRules` | `#wiz-docker-pill-dockerignore` | Regex `(\d+)\s*rule` from pill |
| `dockerModules` | `#wiz-docker-fullsetup-pill-modules` | Regex `(\d+)` from pill |
| `dockerStack` | `#wiz-docker-stack-badge` | Direct textContent |

**Base image resolvers (5):** All read from `#wiz-docker-base` input, call
`_shared.parseDockerImage()`, and return one field from the parsed result.
`dockerBaseBreakdown` is the composite — it returns 3 state-cards (runtime,
version, variant) as formatted HTML, with the variant card colored green
(known variant) or yellow (default/unknown).

**Analysis resolvers (2):** `dockerfileAnalysis` and `dockerSvcAnalysis`
iterate visible DOM rows, parse each image, and build multi-card HTML.
`dockerSvcAnalysis` adds a topology summary card at the top that classifies
the entire stack architecture.

**Setup modal resolvers (9):** These power the Docker Setup sub-wizard.
They use `window._assistant._resolveElement` to determine which specific
element the user is hovering, then produce context-specific cards:

| Resolver | Context Detection | Output |
|----------|------------------|--------|
| `dkSetupBaseBreakdown` | Finds first visible `[id^="mf-dk-img-"]` select | Image breakdown pills with EXPOSE port |
| `dkSetupVolBreakdown` | Iterates all `.dk-vol-row` elements | Per-volume cards with source → dest mapping, mount type (bind/named), and read/write mode |
| `dkSetupDepBreakdown` | Checks all `input[type=checkbox]:checked` in dep wrappers | Per-dependency cards with ports, env vars, volumes from `_infraOptions` |
| `dkSetupDepHover` | Walks up from `_resolveElement` to find the `<label>`, reads checkbox value | Single-service preview with checked/unchecked status |
| `dkInfraHover` | 3-step key resolution: (1) `.dk-infra-toggle` data-attr, (2) `[id^="dk-infra-cfg-"]` panel, (3) input ID regex | Full infrastructure service card: description, current image, purpose-aware port pills, env vars, volumes, command, restart policy. **145 lines** — the most complex resolver. |
| `dkInfraVolState` | Reads volume checkbox state from infra config panel | Include/exclude pill per volume |
| `dkInfraRestartState` | Reads restart policy `<select>` value | Policy explanation (no/always/unless-stopped/on-failure) with trade-off guidance |
| `dkInfraCategoryInfo` | Walks up to category header from `_resolveElement` | Category-level descriptions (databases, caches, message brokers, etc.) with guidance on what belongs in each |
| `dkPortHover` / `dkExposeHover` / `dkInfraPortHover` | Read port input value, call `_shared.classifyPort()` + `_shared.detectPortConflicts()` | Port range classification, known service detection, cross-service conflict warnings |

### `_resolvers_k8s.html` — Kubernetes Domain (536 lines)

4 enrichers + 9 resolvers = 13 total functions.

**Enrichers — K8s Asset Analysis:**

The `k8s-section-manifests` enricher contains a **kindMap** with 18 Kubernetes
resource types, each with an icon and one-line description:

```
Deployment → 🚀 "manages replicated pods with rolling updates"
StatefulSet → 🗄 "pods with stable identity and persistent storage"
Service → 🌐 "stable network endpoint for pods"
Ingress → 🌍 "HTTP routing rules for external traffic"
NetworkPolicy → 🔐 "pod-level network access rules"
... 13 more
```

For each manifest file card, it reads the kind count from a muted span
(e.g., "3 · Deployment, Service, ConfigMap"), splits on commas, and
renders a pill per kind with icon + description.

The `k8s-cfg-skf-profiles` enricher is the most sophisticated — an
**insight engine** that interprets Skaffold profile feature badges into
meaningful guidance. It reads 10 feature patterns:

```
"no push"           → "Images stay on your machine — no registry creds needed"
"push to registry"  → "Registry auth must be configured"
"sha256"            → "Content-addressable tags — unchanged images won't redeploy"
"gitcommit"         → "Tags are pinned to Git SHAs — every deploy traceable"
"port forward"      → "Services accessible on localhost — no ingress needed"
"file sync"         → "Code changes sync without rebuilds"
"server-side apply" → "K8s detects field conflicts before applying"
"kustomize overlay" → "Patches merged on top of base manifests"
"namespace"         → "Resources scoped to dedicated namespace"
"envsubst"          → "Local .env values flow into manifests"
```

It also classifies the profile type:
- Profile name contains "local" or activation contains "dev" → green card + "built for your dev workstation"
- Profile name contains "prod" → yellow card + "safety and traceability over speed"
- Everything else → blue card + "inherits base pipeline"

**Template Variable Resolvers — 9 Functions:**

| Resolver | Context Detection | Output |
|----------|------------------|--------|
| `k8sManifests` | `#wiz-k8s-section-manifests summary` | Count extracted by regex `(\d+)\s*file` |
| `k8sResources` | `#wiz-k8s-section-status span` pills | Count extracted by regex `(\d+)\s*resource` |
| `k8sFieldValue` | Uses `_resolveElement` — if it IS an input, returns `.value`; otherwise `querySelector` for child input | Generic field value reader for simple catalogue templates |
| `k8sSvcCardKind` | Walks up from `_resolveElement` to `[id^="k8s-svc-card-"]`, extracts index, reads `#k8s-svc-kind-{idx}` | Workload kind (`Deployment`/`StatefulSet`/`DaemonSet`) for the service card being hovered |
| `k8sDepHover` | Walks to `<label>`, reads checkbox value, looks up in `_k8sInfraData` (compose-detected) or `_INFRA_CATALOG` (catalogue) | **130-line resolver.** Renders full infra service preview: image, ports, env vars, volumes, K8s deployment decision (StatefulSet/Deployment/DaemonSet/Managed/Skip), checked/unchecked status. |
| `k8sInfraCardHover` | Walks to `.k8s-infra-card`, reads `data-infra-name` | **98-line resolver.** Full infra card overview with kind decision guidance, summary pills, port/env/volume counts, and kind-specific explanations. |
| `k8sInfraKind` | Walks to `.k8s-infra-card`, reads kind select value | Simple value read for catalogue variant matching |
| `k8sVolRowType` | Walks to `.k8s-vol-row`, reads volume type select | Volume type for catalogue variant matching |
| `k8sPortHover` | Reads `_resolveElement`, finds number input, calls `_shared.classifyPort()` and `_shared.knownPorts` | Port analysis with K8s-specific context: containerPort, targetPort, probe endpoints, and low-port warnings |

### `_resolvers_misc.html` — Multi-Domain Resolvers (419 lines)

3 enrichers + 28 resolvers = 31 total functions. Covers 6 domains that
are each too small to warrant their own file.

**Terraform Enrichers (3):**

| Enricher ID | Knowledge Map | DOM Read Strategy |
|-------------|--------------|------------------|
| `tf-section-files` | 10-entry `tfFileTypeMap` (resource, variable, output, provider, data, module, backend, locals, terraform, mixed) | Reads `span[style*="text-muted"]` for file type classification |
| `tf-section-providers` | 15-entry `tfProviderMap` (aws, google, azurerm, digitalocean, kubernetes, helm, cloudflare, github, gitlab, null, random, local, tls, docker, vault) | Strips namespace prefix, looks up provider → icon + label + description + registry link |
| `tf-section-modules` | Source type detection chain: registry, git, local, HTTP, cloud storage | Reads `code[style*="text-muted"]` for source path, classifies by prefix (`./` = local, `git::` = git, etc.) |

**Wizard Resolvers (10):** Read DOM counters from wizard step elements.
Most use `querySelectorAll` with specific ID prefixes and count results.
`selectedStack` is the exception — it's 43 lines and produces a rich
multi-line text breakdown with stack icon, description, domain, parent
chain (if flavored stack), inherited capabilities, and added capabilities.

**GitHub Resolvers (8):** Read pill elements by ID (`wiz-gh-pill-*`).
Notable: `ghEnvMissing` computes by calling `ghEnvTotal() - ghEnvAligned()`
rather than reading its own DOM element.

**Pages Resolvers (6):** Read pill elements by ID (`wiz-pages-pill-*`).
`pagesBuildersAvail` counts pills containing "✅". `pagesUninit` counts
pills with "⬜" to identify uninitialized content folders.

**Terraform / DNS / CI Resolvers (7):** Simple `<select>` value readers
for form fields. Each reads a single element by ID and returns `.value`.
These enable catalogue variant matching — e.g., when the user selects
"S3" as Terraform backend, the variant with `when.resolver: "tfBackendValue"`
+ `when.equals: "s3"` triggers and shows S3-specific configuration guidance.

---

## Data Shapes

### Enricher Contract

Every enricher receives the same signature and returns the same shape:

```javascript
// Registration
window._assistant.enrichers['parent-node-id'] = function(element, extractedName, parentNode) {
    // element:       the matched DOM child element
    // extractedName: display name extracted by the engine (from nameSelector or heuristic)
    // parentNode:    the parent catalogue node (rarely used)

    return {
        title:    'Override title',           // optional — replaces template title
        content:  'Override content text',    // optional — replaces template content
        expanded: '<div>Rich HTML</div>'      // optional — replaces template expanded
    };
    // Return null to keep template defaults
};
```

### Resolver Contract

Resolvers are zero-argument functions. The engine provides context via
`window._assistant._resolveElement` (the currently matched DOM element).

```javascript
// Simple resolver (returns a string/number for {{placeholder}} interpolation)
window._assistant.resolvers.envCount = function() {
    var envs = document.querySelectorAll('#wiz-envs > div');
    return envs ? envs.length : 0;
};

// Rich resolver (returns HTML for catalogue content/expanded fields)
window._assistant.resolvers.dkInfraHover = function() {
    var el = window._assistant._resolveElement;  // ← engine-provided context
    if (!el) return '';
    // ... 145 lines of DOM analysis and HTML construction
    return '<div class="assistant-state-card">...</div>';
};
```

### Interaction Path Shape

The internal data structure passed through the render pipeline:

```
_focusPath / _hoverPath = {
    target:  { id, title, content, expanded, selector, ... },  // catalogue node
    chain:   [ rootNode, parentNode, ... ],                     // ancestor chain
    element: HTMLElement                                         // matched DOM element
}

_mergeInteractionPaths() output = [
    { node: rootNode,    depth: 0, isTarget: false },   // "in-chain"
    { node: parentNode,  depth: 1, isTarget: false },   // "in-chain"
    { node: targetNode,  depth: 2, isTarget: true  }    // "active-target"
]
```

---

## Advanced Feature Showcase

### 1. Image Parser Pipeline (shared → Docker/K8s enrichers)

The image parser is the foundation of all Docker content intelligence.
A single string like `"python:3.12-slim"` flows through 3 layers:

```
User hovers a Dockerfile row containing "python:3.12-slim"
    │
    ├── Engine calls enrichers['docker-section-dockerfiles'](el, "Dockerfile")
    │
    ├── Enricher calls _shared.parseDockerImage("python:3.12-slim")
    │     │
    │     ├── Split: repo="python", tag="3.12-slim"
    │     ├── Split: version="3.12", variant="slim"
    │     ├── Lookup: dockerImageKnowledge["python"]
    │     │     → label="Python", family="python"
    │     └── Lookup: variantInfo["slim"]
    │           → "Debian-based minimal (~150MB) — good balance..."
    │
    └── Enricher builds pill-style HTML:
          🔧 Python  |  📌 3.12  |  📦 slim
          "Debian-based minimal (~150MB) — good balance of
           compatibility and size"
```

This same pipeline runs in `dockerSvcAnalysis`, `dkSetupBaseBreakdown`,
`dkInfraHover`, and `k8sInfraCardHover` — any context that deals with
Docker images gets consistent, knowledge-backed breakdowns.

### 2. Compose Service Role Classification

When `dockerSvcAnalysis` or the `docker-section-compose-svcs` enricher
processes a compose file, it doesn't just list services — it classifies
the entire stack topology:

```
compose.yml with: web (build), postgres:15-alpine, redis:7-alpine, nginx:1.25-alpine

Service         Image                  Family      Role           Card
────────────────────────────────────────────────────────────────────────
web             (build)                —           application    🟢 green
postgres        postgres:15-alpine     database    database       🔵 blue
redis           redis:7-alpine         cache       cache          🔵 blue
nginx           nginx:1.25-alpine      webserver   proxy          🔵 blue

Topology summary: "Full stack (app + database + cache)" — 4 services
```

The topology summary uses boolean checks: `hasDb && hasCache` → "Full stack",
`hasDb` alone → "App + Database", else → "Multi-service (N services)".

### 3. Infrastructure Service Hover (dkInfraHover — 145 lines)

The most complex resolver in the system. When the user hovers ANY element
within an infrastructure service card, it must determine WHICH service:

```
User hovers a port input inside the PostgreSQL config panel
    │
    ├── Step 1: Try .dk-infra-toggle with data-infra-key attribute
    │           (works when hovering the toggle label)
    │
    ├── Step 2: Try [id^="dk-infra-cfg-"] ancestor
    │           (works when hovering inside the expanded config panel)
    │
    ├── Step 3: Try regex on element ID
    │           /mf-dk-infra-(?:img|port|vol|cmd|restart|imgcustom)-([a-z0-9]+)/
    │           (works when hovering a specific input field)
    │
    └── infraKey = "postgres"
        │
        ├── Look up in window._infraOptions → full service definition
        ├── Read current toggle state → isEnabled
        ├── If enabled, read current image select → parse with _shared
        ├── Build purpose-aware port pills (wire/http/admin/grpc/peer/ws/ssh/smtp)
        ├── Build env var pills (🔒 for passwords, 📋 for regular)
        ├── Build volume pills (💾 name → mount path)
        └── Output: 8-section state card with all live configuration values
```

The port pills use a purpose-aware coloring system — 8 purpose types with
different icons and colors. A `wire` port (database protocol) gets 🔌 accent,
an `http` port gets 🌐 green, an `admin` port gets ⚙️ yellow.

### 4. Skaffold Profile Insight Engine (k8s-cfg-skf-profiles enricher)

This enricher doesn't just display data — it interprets Skaffold features
into actionable guidance. Given feature badges like
`["no push", "sha256", "port forward", "file sync"]`:

```
Profile: "local-dev"
    │
    ├── Name analysis: contains "local" → isLocal = true
    │   → stateClass = "state-success" (green card)
    │   → intro: "Built for your dev workstation..."
    │
    ├── Feature interpretation (10 patterns):
    │   ├── "no push" → "Images stay on your machine"
    │   ├── "sha256"  → "Unchanged images won't redeploy"
    │   ├── "port forward" → "Services accessible on localhost"
    │   └── "file sync" → "Code changes sync without rebuilds"
    │
    └── Footer: "Profiles are additive — they patch the base config"
```

Compare with a production profile `["push to registry", "gitcommit", "server-side apply"]`:
- Yellow card, not green
- "Every setting prioritizes safety and traceability over speed"
- Different insights for each feature

### 5. Port Conflict Detection (shared → Docker/K8s port resolvers)

When the user enters a port number, the assistant doesn't just classify it —
it warns about conflicts across ALL services in the compose stack:

```
User types "5432" into the host port field for their app service
    │
    ├── classifyPort(5432) → { name: "Common app", icon: "✅", state: "state-success" }
    ├── knownPorts[5432]   → { label: "PostgreSQL", note: "Database wire protocol..." }
    │
    └── detectPortConflicts(5432, thisRow)
          ├── Scan all .dk-port-row inputs → found 5432 in "postgres" row
          ├── Scan _infraOptions → postgres infra has port 5432 enabled
          └── Return: ["postgres"]
              → ⚠️ "Port 5432 conflicts with: postgres"
```

### 6. K8s Deployment Decision Preview (k8sDepHover/k8sInfraCardHover)

These resolvers read the K8s deployment "kind" selector for each
infrastructure service and explain the implications:

```
Kind select value: "Managed"
    │
    └── k8sContext = "☁️ Managed externally — no K8s resources generated.
         Connection vars injected as Secrets into your pod."

    vs.

Kind select value: "StatefulSet"
    │
    └── k8sContext = "🗄️ Deployed as StatefulSet — stable network
         identity (redis-0, redis-1) + persistent storage. Pods
         restart on same PVC."
```

`k8sInfraCardHover` goes deeper — it renders kind-specific guidance
explaining WHEN to use each option ("Usually wrong for databases. Use
this only if the service is truly stateless...").

### 7. Terraform Module Source Classification (tf-section-modules enricher)

The module enricher doesn't just show the source path — it classifies
the module's origin and explains the implications:

```
Source path analysis:

"hashicorp/consul/aws"       → 📦 Registry  (versioned, documented)
"git::github.com/org/repo"   → 🔗 Git       (pinned via ?ref=tag)
"./modules/networking"       → 📁 Local     (no network fetch needed)
"https://example.com/mod.zip"→ 🌐 HTTP      (downloaded as archive)
"s3::bucket/path"            → ☁  Cloud     (S3/GCS storage)
```

---

## Dependency Graph

```
_engine.html                       ← standalone, exposes window._assistant
    │
    ├── resolvers: {}               ← filled by resolver files
    ├── enrichers: {}               ← filled by resolver files
    └── _shared: {}                 ← filled by _resolvers_shared.html
         │
_resolvers_shared.html             ← fills _shared (image parser, port tables)
    │        │
    │        ├── _resolvers_docker.html    ← uses _shared for image parsing/ports
    │        └── _resolvers_k8s.html       ← uses _shared for port classification
    │
_resolvers_dashboard.html          ← enrichers only, no shared deps
_resolvers_misc.html               ← resolvers only, no shared deps
```

Each resolver file is an IIFE that registers functions on
`window._assistant.resolvers` or `window._assistant.enrichers`.
The engine calls them at render time — no direct coupling.

---

## Consumers

### Engine Activation

| File | Call | Context |
|------|------|---------|
| `_dashboard.html` (line 580) | `_assistant.activate('dashboard', container, panel)` | Dashboard tab |
| `wizard/_init.html` (line 185) | `_assistant.activate('wizard/' + stepId, body)` | Wizard tab steps |
| `wizard/_modal.html` (line 112) | `_assistant.activate(opts.assistantContext, modalMain, modalPanel)` | Wizard modal (Docker, K8s, etc.) |
| `wizard/_modal.html` (line 329) | `_assistant.activate('wizard/' + stepId, wizBody)` | Modal step change |

### Engine Refresh

| File | Call | When |
|------|------|------|
| `wizard/_integrations.html` | `_assistant.refresh()` | After inline sub-wizard panel opens |
| `wizard/_helpers.html` | `_assistant.refresh()` | After module detection updates DOM |
| Various integration files | `_assistant.refresh()` | After form field or DOM change |

### Script Loading (dashboard.html)

```
Line 59: {% include 'scripts/assistant/_engine.html' %}
Line 60: {% include 'scripts/assistant/_resolvers_shared.html' %}
Line 61: {% include 'scripts/assistant/_resolvers_misc.html' %}
Line 62: {% include 'scripts/assistant/_resolvers_docker.html' %}
Line 63: {% include 'scripts/assistant/_resolvers_k8s.html' %}
Line 64: {% include 'scripts/assistant/_resolvers_dashboard.html' %}
```

### External Data

| Resource | Format | Purpose |
|----------|--------|---------|
| `/static/data/assistant-catalogue.json` | JSON | Full content tree for all contexts |

---

## Design Decisions

### Why separate engine from resolvers?

The engine is a pure rendering machine — it knows nothing about
Docker, K8s, or any specific domain. Resolvers are domain experts
that know how to read specific DOM structures. This separation
means new resolver files can be added without touching the engine,
and the engine can be tested with any JSON catalogue. The enricher
registration pattern (`enrichers[id] = fn`) is runtime-extensible.

### Why is `_resolvers_docker.html` 1,256 lines?

Docker has the highest resolver density because the Docker setup
wizard has the most interaction points: base image breakdown,
compose service topology, port analysis with conflict detection,
volume mount classification, infrastructure service previews, and
dependency hover cards. Each resolver produces state-aware HTML
cards that explain what the user is looking at. Splitting this by
feature (e.g., ports.html, volumes.html) would scatter tightly
related code across too many files.

### Why deepest-first node matching?

`_flattenTree()` builds the node index with the deepest nodes first.
When the user hovers a nested element, multiple selectors might match
(a field inside a section inside a tab). Deepest-first ensures the
most specific match wins, while parent chain traversal still builds
the full breadcrumb path.

### Why IIFE wrappers on every file?

Each resolver file is a separate `<script>` tag. Without the IIFE,
`'use strict'` would be file-scoped but variables would leak to the
global scope. The IIFE prevents accidental globals while still
registering on `window._assistant` intentionally.

### Why enrichers return `{title?, content?, expanded?}` instead of full HTML?

The engine handles rendering (CSS classes, expand/collapse, scroll
anchoring). Enrichers only supply data. This keeps enrichers small
and testable — they return an object describing what to show, not
how to show it. It also means the engine can change rendering
(e.g., adding animations) without touching any enricher.

### Why does the engine trap wheel events?

Without `_onWheel()`, scrolling within the assistant panel would
bubble to the page and scroll the main content. The handler uses
`preventDefault()` at scroll boundaries to keep panel scrolling
isolated — the main page stays put.

### Why read DOM state instead of data models?

Resolvers read live DOM elements (input values, text content, CSS
classes) rather than JavaScript data models. This design decision
means the assistant works with any DOM structure — including
third-party or server-rendered content — without tight coupling to
specific JavaScript state objects. The tradeoff is resolver fragility
if DOM structure changes, but the benefit is zero coupling to the
application's data layer.
