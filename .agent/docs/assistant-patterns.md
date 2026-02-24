# Assistant Engine — Pattern Reference

> Complete reference for all patterns used to interface with the assistant UI.
> Covers: catalogue shapes, resolvers, enrichers, variants, selectors, CSS classes,
> and DOM querying conventions.

---

## Architecture Overview

```
 assistant-catalogue.json     (declarative: what to show)
        │
        ▼
 _assistant_engine.html       (core: matching, rendering, dispatch)
        │
        ├── _assistant_resolvers_shared.html   (shared utilities)
        ├── _assistant_resolvers_misc.html      (wizard/integration resolvers)
        ├── _assistant_resolvers_docker.html    (Docker resolvers + enrichers)
        └── _assistant_resolvers_k8s.html       (K8s resolvers + enrichers)
```

### Inclusion order in `dashboard.html`

```html
{% include "scripts/_assistant_engine.html" %}
{% include "scripts/_assistant_resolvers_shared.html" %}
{% include "scripts/_assistant_resolvers_misc.html" %}
{% include "scripts/_assistant_resolvers_docker.html" %}
{% include "scripts/_assistant_resolvers_k8s.html" %}
```

Order matters: engine first (defines `window._assistant`), shared second
(populates `_shared`), then domain files (register resolvers + enrichers).

---

## 1. Catalogue Shapes

The catalogue is a JSON array of **contexts**. Each context maps to a wizard/modal
via its `context` string.

### 1.1 Context (root)

```json
{
  "context": "k8s-configure",
  "title": "Kubernetes Configuration",
  "icon": "☸️",
  "content": "Static or {{resolver}} text shown in header.",
  "children": [ ... ],
  "variants": [ ... ]
}
```

The engine selects a context when `activate(contextId)` is called.

### 1.2 Static Node

The simplest shape — fixed text, no resolver, no variants.

```json
{
  "id": "my-node",
  "title": "Label shown in tree",
  "selector": "#my-dom-element",
  "content": "Main content text."
}
```

**540 total nodes** across 9 contexts. **44 nodes** are purely static.

### 1.3 Node with Resolver

Content contains `{{resolverName}}` placeholders. The engine calls
`window._assistant.resolvers[resolverName]()` and interpolates the return value.

```json
{
  "id": "docker-baseimg",
  "title": "Base Image",
  "selector": "#docker-base-image",
  "content": "Runtime: {{dockerBaseRuntime}} version {{dockerBaseVersion}}"
}
```

- **48 unique resolvers** registered across all files.
- Resolvers return **strings** (plain text or HTML).
- A resolver returning `''` renders as empty (the placeholder disappears).

### 1.4 Node with Resolver-Only Content

When `content` is a single `{{resolver}}` that returns full HTML:

```json
{
  "id": "k8s-cfg-svc-ports",
  "title": "Service Ports",
  "selector": "#k8s-svc-port-0",
  "content": "{{k8sPortHover}}"
}
```

The resolver builds and returns complete state-card HTML. Used when the
content is entirely dynamic and context-dependent.

### 1.5 Node with Expanded

`expanded` provides collapsible detail below the main content.

```json
{
  "id": "gh-card",
  "title": "GitHub",
  "selector": "#gh-card",
  "content": "Connected to {{ghRepo}}.",
  "expanded": "<div class='assistant-state-card state-success'>...</div>"
}
```

Both `content` and `expanded` support `{{resolver}}` interpolation.

### 1.6 Node with Children

Static hierarchy — child nodes render as indented sub-items.

```json
{
  "id": "k8s-configure",
  "title": "Configure",
  "selector": ".k8s-step-configure",
  "children": [
    { "id": "k8s-cfg-ns",  "title": "Namespace", "selector": "#k8s-namespace", ... },
    { "id": "k8s-cfg-svc", "title": "Services",  "selector": ".k8s-svc-card", ... }
  ]
}
```

The engine recursively matches children — the deepest match wins.

### 1.7 Node with `childTemplate` (Dynamic Children)

For lists that come from the DOM (detected files, profiles, etc.):

```json
{
  "id": "k8s-cfg-skf-profiles",
  "title": "Profiles",
  "selector": "#k8s-skf-profiles",
  "childTemplate": {
    "containerSelector": "#k8s-skf-profiles-list",
    "itemSelector": "> div",
    "nameSelector": "code",
    "nameAttr": "",
    "title": "Profile: {{name}}",
    "content": "Skaffold profile.",
    "expanded": ""
  }
}
```

| Field               | Purpose                                                   |
|---------------------|-----------------------------------------------------------|
| `containerSelector` | CSS selector for the parent element containing list items |
| `itemSelector`      | CSS selector for each child item (relative to container)  |
| `nameSelector`      | CSS selector inside each item to extract the display name |
| `nameAttr`          | If set, reads `element.getAttribute(nameAttr)` instead of `textContent` |
| `title`             | Template — `{{name}}` is replaced with extracted name     |
| `content`           | Template — same `{{name}}` interpolation                  |
| `expanded`          | Template — same `{{name}}` interpolation                  |

**23 childTemplate entries** across all contexts. Each produces synthetic
nodes at runtime from DOM content.

---

## 2. Variant System

Variants let a single node produce different content based on DOM state.
**424 variants** across 540 nodes.

### 2.1 Variant Structure

```json
{
  "id": "docker-base-runtime",
  "title": "Runtime",
  "selector": "#docker-base-runtime",
  "content": "Default content when no variant matches.",
  "variants": [
    {
      "when": { "resolver": "dockerBaseRuntime", "equals": "" },
      "content": "⚠ No runtime detected."
    },
    {
      "when": { "resolver": "dockerBaseRuntime", "contains": "Python" },
      "content": "✓ Python runtime — CPython interpreter with pip."
    }
  ]
}
```

Variants are evaluated **in order** — first match wins. If no variant matches,
the base `content`/`expanded` are used.

### 2.2 When Condition Types

| Pattern                                    | Count | Description                                          |
|--------------------------------------------|------:|------------------------------------------------------|
| `{ textContains: "..." }`                  | 204   | Element's `textContent` contains the string          |
| `{ resolver: "...", equals: "..." }`       | 140   | Resolver return value === equals                     |
| `{ hasSelector: "..." }`                   | 41    | Element contains a child matching the CSS selector   |
| `{ resolver: "...", contains: "..." }`     | 19    | Resolver return includes substring (case-insensitive)|
| `{ dataAttr: { key: "value" } }`           | 18    | Element's `data-*` attributes match                  |
| `{ resolver: "...", not: "..." }`          | 2     | Resolver return value !== not                        |

### 2.3 `textContains`

Checks `element.textContent.toLowerCase().includes(value.toLowerCase())`.

```json
{ "when": { "textContains": "configured" }, "content": "..." }
```

Most common pattern (204x). Used when the DOM text itself indicates state
(e.g., "configured" vs "not detected" in status badges).

### 2.4 `resolver` + `equals` / `contains` / `not`

Calls a named resolver and compares the return value.

```json
{ "when": { "resolver": "k8sFieldValue", "not": "" }, "content": "..." }
```

This enables **state-aware content** — the assistant reads the live value of an
input field and adjusts its guidance accordingly.

### 2.5 `hasSelector`

Checks if a child element matching the selector exists.

```json
{ "when": { "hasSelector": "option:checked[value*='python']" }, "content": "..." }
```

Useful for select dropdowns where you want to match the currently selected option.

### 2.6 `dataAttr`

Checks `element.dataset` or `data-*` attributes.

```json
{ "when": { "dataAttr": { "aligned": "true" } }, "content": "..." }
```

### 2.7 Variant Override Fields

When a variant matches, it can override:

| Field      | Behavior                                    |
|------------|---------------------------------------------|
| `title`    | Replaces node title (optional)              |
| `content`  | Replaces node content                       |
| `expanded` | Replaces node expanded detail               |
| `icon`     | Replaces node icon (optional)               |

Fields NOT specified in the variant are inherited from the base node.

---

## 3. Resolvers

Resolvers are functions registered on `window._assistant.resolvers`.
Called during `{{name}}` interpolation and `when.resolver` conditions.

### 3.1 Registration

```javascript
window._assistant.resolvers.myResolver = function() {
    return 'string value';
};
```

### 3.2 Resolver Categories

#### Count/Status Resolvers (return numbers or short strings)

| Resolver              | Returns                      | File          |
|-----------------------|------------------------------|---------------|
| `dockerDockerfiles`   | Number of Dockerfiles        | docker        |
| `dockerServices`      | Number of Compose services   | docker        |
| `dockerStack`         | Detected stack name          | docker        |
| `k8sManifests`        | Number of K8s manifest files | k8s           |
| `k8sResources`        | Number of K8s resources      | k8s           |
| `envCount`            | Number of environments       | misc          |
| `domainCount`         | Number of domains            | misc          |
| `toolsInstalled`      | Installed tools count        | misc          |
| `toolsTotal`          | Total tools count            | misc          |
| `ghUser`, `ghRepo`    | GitHub user/repo             | misc          |
| `ghBranch`, `ghVis`   | GitHub branch/visibility     | misc          |
| `ghWorkflows`         | Workflow count               | misc          |
| `ghEnvTotal/Aligned/Missing` | Environment sync stats | misc          |
| `pagesBranch`         | Pages branch name            | misc          |
| `pagesBuildersAvail/Total` | Builder counts            | misc          |
| `pagesSegments`       | Content segments count       | misc          |
| `pagesUninit`         | Uninitialized count          | misc          |
| `filesDetected/Total` | File detection counts        | misc          |
| `moduleCount`         | Module count                 | misc          |

#### Analysis Resolvers (return text breakdown)

| Resolver                    | Returns                          | File   |
|-----------------------------|----------------------------------|--------|
| `dockerBaseRuntime`         | Runtime name (e.g., "Python")    | docker |
| `dockerBaseVersion`         | Version string                   | docker |
| `dockerBaseVariant`         | Variant name (e.g., "slim")      | docker |
| `dockerBaseVariantExplain`  | Variant explanation              | docker |
| `dockerBaseBreakdown`       | Full image analysis HTML         | docker |
| `dockerComposeCli`          | Docker Compose CLI version       | docker |
| `dockerDaemon`              | Docker daemon status             | docker |
| `dockerModules`             | Detected Docker modules          | docker |
| `dockerIgnoreRules`         | .dockerignore rule count         | docker |
| `dkSetupBaseBreakdown`      | Setup base image analysis        | docker |
| `dkSetupVolBreakdown`       | Setup volume analysis            | docker |
| `dkSetupDepHover`           | Setup dependency hover card      | docker |
| `dkInfraHover`              | Infrastructure hover card        | docker |
| `dkInfraCategoryInfo`       | Infrastructure category info     | docker |
| `dkInfraPortHover`          | Infrastructure port analysis     | docker |
| `dkInfraRestartState`       | Restart policy state             | docker |
| `dkInfraVolState`           | Infrastructure volume state      | docker |

#### Rich Card Resolvers (return full HTML)

These return complete `assistant-state-card` HTML for resolver-only content nodes.

| Resolver              | Returns                              | File   |
|-----------------------|--------------------------------------|--------|
| `k8sPortHover`        | Port analysis card with range info   | k8s    |
| `k8sDepHover`         | Infra dependency card with pills     | k8s    |
| `k8sInfraCardHover`   | Full infra card with K8s decisions   | k8s    |
| `dkPortHover`         | Docker port analysis card            | docker |
| `dkExposeHover`       | Dockerfile EXPOSE analysis           | docker |

#### State-Reading Resolvers

These read the current DOM element being hovered/focused via
`window._assistant._resolveElement`:

| Resolver           | Reads                                     | File |
|--------------------|-------------------------------------------|------|
| `k8sFieldValue`    | Value of hovered input/select/textarea    | k8s  |
| `k8sSvcCardKind`   | Workload kind from parent service card    | k8s  |
| `k8sInfraKind`     | Infra kind select from parent card        | k8s  |
| `k8sVolRowType`    | Volume type from parent row               | k8s  |

### 3.3 `_resolveElement` — DOM Context for Resolvers

When the engine calls a resolver during variant matching, it sets:

```javascript
window._assistant._resolveElement = matchedDOMElement;
```

This allows resolvers to walk up the DOM from the hovered element to find
contextual data (parent cards, sibling inputs, etc.).

**Pattern**: Walk up to find context:
```javascript
window._assistant.resolvers.myResolver = function() {
    var el = window._assistant._resolveElement;
    if (!el) return '';
    var card = el.closest ? el.closest('.my-card-class') : null;
    if (!card) return '';
    var input = card.querySelector('input');
    return input ? input.value : '';
};
```

---

## 4. Enrichers

Enrichers modify **dynamic children** created by `childTemplate`. They run
after the synthetic node is created but before rendering.

### 4.1 Registration

```javascript
window._assistant.enrichers['parent-node-id'] = function(el, extractedName, parentNode) {
    // el = the DOM element for this dynamic child
    // extractedName = text extracted via nameSelector
    // parentNode = the parent catalogue node
    return {
        title: 'Override title',     // optional
        content: 'Override content', // optional
        expanded: '<html>...'        // optional
    };
    // Return null to skip enrichment
};
```

### 4.2 Registered Enrichers

| Parent ID                      | Stack     | What it does                                       |
|--------------------------------|-----------|----------------------------------------------------|
| `docker-section-dockerfiles`   | Docker    | Per-file image analysis, stage count, EXPOSE info   |
| `docker-section-compose-svcs`  | Docker    | Per-service role detection, image breakdown, meta   |
| `k8s-section-manifests`        | K8s       | Per-file resource kind pills with icons             |
| `k8s-section-helm`             | K8s       | Per-chart version + metadata badge strip            |
| `k8s-section-kustomize`        | K8s       | Per-overlay patch description + apply command       |
| `k8s-cfg-skf-profiles`         | K8s       | Per-profile feature insight interpretation          |
| `tf-section-files`             | Terraform | Per-file type classification (resource/variable/…)  |
| `tf-section-providers`         | Terraform | Per-provider cloud platform mapping                 |
| `tf-section-modules`           | Terraform | Per-module source type analysis (registry/git/local)|

### 4.3 DOM Querying in Enrichers

Enrichers query the dynamic child's DOM element for data. This creates a
**coupling** between the enricher and the HTML template that renders the list items.

⚠️ **CRITICAL**: If the HTML template changes its inline styles to CSS classes
(or vice versa), enricher selectors using `style*="..."` will break.

**Before Phase 3 sweep** (queried by inline style):
```javascript
var badges = el.querySelectorAll('[style*="border-radius:3px"][style*="background"]');
```

**After Phase 3 sweep** (query by CSS class):
```javascript
var badges = el.querySelectorAll('.wiz-tag');
```

**Rule**: When replacing inline styles with CSS classes, always grep enricher
and resolver files for `style*="<property>"` selectors that reference the
removed style.

---

## 5. Selector Matching

### 5.1 How the Engine Finds Nodes

When the user hovers/focuses a DOM element, the engine walks the catalogue
tree and checks each node's `selector` against the element:

1. **Direct match**: `element.matches(selector)` — element itself matches
2. **Ancestor match**: `element.closest(selector)` — element is inside a match
3. **Proximity match**: For `input`, `select`, `textarea`, `label`, `button`,
   the engine walks up 2 levels to find a nearby wrapper that contains the
   selector match

The **deepest matching node** (most specific) wins.

### 5.2 Selector Types Used

| Type     | Count | Example                               |
|----------|------:|---------------------------------------|
| `#id`    | 372   | `#k8s-namespace`                      |
| `.class` | 124   | `.k8s-svc-card`                       |
| `[attr]` | 38    | `[data-step="configure"]`             |
| Other    | 1     | `button[onclick='wizardDetect()']`    |

---

## 6. CSS Classes for State Cards

### 6.1 Card Structure

All rich content uses `assistant-state-card` with state variants:

```html
<div class="assistant-state-card state-success">
  <div class="state-label">✅ Title</div>
  <div class="state-detail">
    <div class="state-intro">Opening guidance text.</div>
    <div class="state-insight">Interpreted insight from DOM data.</div>
    <div class="state-footer">Additive note or context.</div>
  </div>
</div>
```

### 6.2 State Variants

| Class          | Color   | Use case                         |
|----------------|---------|----------------------------------|
| `state-success`| Green   | Configured, aligned, selected    |
| `state-info`   | Blue    | Informational, neutral state     |
| `state-warning`| Yellow  | Caution, production, risky       |

### 6.3 Card Sub-elements

| Class                | Purpose                                         |
|----------------------|-------------------------------------------------|
| `state-label`        | Bold title line with icon                       |
| `state-detail`       | Container for detail content                    |
| `state-intro`        | Opening paragraph — context-setting guidance    |
| `state-insight`      | Interpreted insight (from DOM data analysis)    |
| `state-footer`       | Closing note — additive context                 |
| `state-text`         | Generic text block                              |
| `state-text-spaced`  | Text with extra top margin                      |
| `state-wrap`         | Forces normal whitespace wrapping               |

### 6.4 Grid State Cards

For key-value layouts:

```html
<div class="assistant-state-card state-info">
  <div class="state-grid">
    <span class="state-grid-key">containerPort</span>
    <span>pod spec — must match what the process binds to</span>
  </div>
</div>
```

---

## 7. Wizard Field CSS Classes

**18 classes** added in Phase 3 to replace high-frequency inline styles.
All prefixed `.wiz-*` and scoped inside wizard content areas.

### 7.1 Inputs

| Class            | Use case                         |
|------------------|----------------------------------|
| `.wiz-input`     | Compact text/number input        |
| `.wiz-input-full`| Full-width text input            |
| `.wiz-select`    | Styled dropdown select           |
| `.wiz-check`     | Checkbox/radio with accent color |

### 7.2 Labels

| Class              | Use case                    |
|--------------------|-----------------------------|
| `.wiz-label`       | Standard muted bold label   |
| `.wiz-label-accent`| Accent-colored section label|
| `.wiz-group-header`| Larger group header         |

### 7.3 Hints

| Class             | Use case                     |
|-------------------|------------------------------|
| `.wiz-hint`       | Tiny hint below a field      |
| `.wiz-hint-md`    | Slightly larger field hint   |
| `.wiz-hint-italic`| Italic state hint            |
| `.wiz-note`       | Tiny supplementary note      |

### 7.4 Actions

| Class          | Use case                              |
|----------------|---------------------------------------|
| `.wiz-action`  | Accent-colored clickable action       |
| `.wiz-toggle`  | Inline toggle link                    |
| `.wiz-add-btn` | Dashed "add" button                   |
| `.wiz-icon-btn`| Minimal icon button (delete, etc.)    |

### 7.5 Containers

| Class            | Use case                     |
|------------------|------------------------------|
| `.wiz-section`   | Inset card with border       |
| `.wiz-section-lg`| Same but more padding        |

### 7.6 Badges / Tags

| Class          | Use case                     |
|----------------|------------------------------|
| `.wiz-badge`   | Inline code-like badge       |
| `.wiz-badge-sm`| Smaller badge variant        |
| `.wiz-tag`     | Bordered tag pill            |

### 7.7 Layout

| Class           | Use case                     |
|-----------------|------------------------------|
| `.wiz-vstack`   | Vertical stack, tight gap    |
| `.wiz-vstack-md`| Vertical stack, medium gap   |
| `.wiz-row`      | Horizontal row, centered     |

---

## 8. Adding New Content — Recipes

### 8.1 Add static guidance for a new field

1. Add a `selector` that matches the field's DOM element (prefer `#id`)
2. Add the node to the correct parent in the catalogue
3. Write `content` with assistant-feel guidance

```json
{
  "id": "my-field",
  "title": "My Field",
  "selector": "#my-field-id",
  "content": "What this field controls and why it matters."
}
```

### 8.2 Add state-aware guidance

1. Create a resolver that reads the field's current value
2. Add variants that produce different content based on the value
3. Register the resolver in the appropriate `_assistant_resolvers_*.html` file

```javascript
// In resolver file
window._assistant.resolvers.myFieldState = function() {
    var el = window._assistant._resolveElement;
    if (!el) return '';
    var input = (el.tagName === 'INPUT') ? el : el.querySelector('input');
    return input ? input.value : '';
};
```

```json
{
  "id": "my-field",
  "title": "My Field",
  "selector": "#my-field-id",
  "content": "Default guidance.",
  "variants": [
    {
      "when": { "resolver": "myFieldState", "equals": "" },
      "content": "⚠ Empty — this field is required."
    },
    {
      "when": { "resolver": "myFieldState", "contains": "prod" },
      "content": "🔴 Production value — double-check this."
    }
  ]
}
```

### 8.3 Add enrichment for dynamic list items

1. Ensure the parent node has a `childTemplate`
2. Register an enricher keyed by the parent node's `id`
3. Query the dynamic child's DOM element for data
4. Return `{ title?, content?, expanded? }`

```javascript
window._assistant.enrichers['my-list-parent'] = function(el, extractedName, parentNode) {
    var badge = el.querySelector('.my-badge-class');
    var badgeText = badge ? badge.textContent.trim() : '';

    return {
        content: 'Item: ' + extractedName + (badgeText ? ' (' + badgeText + ')' : ''),
        expanded: '<div class="assistant-state-card state-info">' +
            '<div class="state-label">📦 ' + extractedName + '</div>' +
            '<div class="state-detail">Detailed analysis...</div>' +
            '</div>'
    };
};
```

### 8.4 Add a rich hover card resolver

For elements that need full HTML content (not just text interpolation):

```javascript
window._assistant.resolvers.myRichHover = function() {
    var el = window._assistant._resolveElement;
    if (!el) return '';

    var card = el.closest('.my-card');
    if (!card) return '';

    var name = card.querySelector('.name').textContent;
    var status = card.querySelector('.status').textContent;

    return '<div class="assistant-state-card ' +
        (status === 'ok' ? 'state-success' : 'state-warning') + '">' +
        '<div class="state-label">' + name + '</div>' +
        '<div class="state-detail">' + status + '</div>' +
        '</div>';
};
```

Then in the catalogue, use resolver-only content:
```json
{
  "id": "my-card-hover",
  "selector": ".my-card",
  "content": "{{myRichHover}}"
}
```

---

## 9. Common Pitfalls

### 9.1 Enricher selectors break after CSS refactoring

When bulk-replacing `style="..."` with `class="..."` in templates,
enrichers that use `querySelector('[style*="..."]')` will silently stop matching.

**Prevention**: After any inline-style sweep, grep all enricher files:
```bash
grep -n 'querySelector.*style' src/ui/web/templates/scripts/_assistant_resolvers_*.html
```

### 9.2 Variant order matters

Variants are evaluated first-to-last. Put specific matches before general ones.
If a `textContains: "configured"` variant comes after `textContains: "not configured"`,
it will never match because "not configured" also contains "configured".

### 9.3 Resolver returns HTML in `content` vs `expanded`

- `content` renders inline — use for short text or compact cards
- `expanded` renders in a collapsible section — use for detailed analysis
- Don't put giant HTML in `content` — it clutters the tree view

### 9.4 Dynamic children get variants too

`childTemplate` can carry its own `variants` array. These are applied to
each synthetic node individually, with `{{name}}` interpolated first.

### 9.5 `_resolveElement` lifecycle

`window._assistant._resolveElement` is set during variant resolution and cleared
after. Resolvers should always null-check it. It points to the actual hovered
DOM element (not the catalogue node).

---

## 10. File Reference

| File                              | Lines | Role                                    |
|-----------------------------------|------:|----------------------------------------|
| `_assistant_engine.html`          | 1,118 | Core: matching, rendering, dispatch     |
| `_assistant_resolvers_shared.html`|   151 | Docker image knowledge + port analysis  |
| `_assistant_resolvers_docker.html`| 1,256 | 26 resolvers + 2 enrichers              |
| `_assistant_resolvers_k8s.html`   |   536 | 12 resolvers + 4 enrichers              |
| `_assistant_resolvers_misc.html`  |   419 | 31 resolvers + 3 enrichers              |
| `assistant-catalogue.json`        | ~4,500| 540 nodes across 9 contexts             |
| `admin.css` (wiz-* section)       |   220 | 18 wizard field CSS classes             |
