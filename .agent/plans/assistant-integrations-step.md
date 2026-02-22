# Assistant — Integrations Step Plan — COMPLETED

> **Scope:** `wizard/integrations` catalogue entry for the assistant side panel.
> **Status:** ✅ All phases implemented. Context root, scan bar, system tools,
> file detection, integrations section, devops extensions (Docker with per-item
> dynamic enrichment for Dockerfiles and Compose Services; K8s with per-manifest
> kind breakdown, per-chart Helm analysis, and per-overlay Kustomize enrichment),
> CI/CD, and sub-forms.
> **Reference:** `assistant-architecture.md` (living source of truth)

---

## 1. Context Overview

The Integrations step (Step 5) is the **largest and most complex** wizard step.
It renders from `_wizRenderIntegrations()` after fetching `/wizard/detect` data
and contains 6 visual sections, 8 integration cards, 15 tool rows, 12 file
detection pills, and potentially deep sub-forms per integration.

Unlike earlier steps (Welcome has 5 children, Secrets has 4), Integrations can
have **40+ interactive elements** depending on project state, each needing
contextual assistant content.

### Why this is harder than previous steps

| Dimension | Welcome | Secrets | Integrations |
|-----------|---------|---------|--------------|
| Static children | 5 | 4 | 6+ sections |
| Dynamic children | 2 (domains, envs) | 3 (vaults, gh-envs, files) | 15 tools + 12 files + 8 cards |
| Max nesting depth | 3 | 3 | 4–5 (card → sub-form → field) |
| State variants | 0 | 6+6+3+2+6 = 23 | 5 card states × 8 cards = 40+ |
| Template resolvers | 3 | 0 | New ones needed |

---

## 2. Phased Delivery

We split into **5 phases** to avoid scope creep and maintain quality:

### Phase A — Context Root + Scan Bar + System Tools + File Detection ✅
- Context root (`wizard/integrations`)
- Scan status bar (stale/fresh variants)
- System Tools section with dynamic per-tool rows
- File Detection badge row
- New template resolvers: `toolCount`, `fileCount`, `integrationCount`

### Phase B — Integrations Section (Git, GitHub, Pages) ✅
- Section header
- Git card (3 status variants)
- GitHub card (3 status variants)
- Pages card (3 status variants)

### Phase C — DevOps Extensions (Docker, K8s, Terraform, DNS) ✅
- Section header
- Docker card (most complex — daemon status, Dockerfile, compose)
  - **Dockerfiles section:** dynamic nodes with `childTemplate` + per-file
    enrichment via `_parseDockerImage()` (see architecture doc)
  - **Compose Services section:** dynamic nodes with per-service role
    classification, image breakdown, and metadata extraction
- K8s card — full `#wiz-int-wrap-k8s` catalogue entry with:
  - **Card-level variants:** cluster connected / no cluster / kubectl missing
  - **12 static children:** status strip, manifests, Helm charts, Kustomize,
    environments, infra dependencies, live cluster, generate manifests (6 form
    fields), full K8s setup, delete, apply, cancel
  - **3 dynamic childTemplates:**
    - `k8s-section-manifests` → per-file resource kind breakdown (18 known kinds
      mapped with icons and descriptions)
    - `k8s-section-helm` → per-chart metadata extraction (version, values,
      templates, subcharts)
    - `k8s-section-kustomize` → per-overlay patch count and apply commands
  - **Engine enrichment:** ~90 lines in `_resolveDynamic()` for K8s-specific
    DOM parsing (resource kind map, chart metadata, overlay patches)
  - **Template resolvers:** `k8sManifests`, `k8sResources` for `{{}}` vars
  - **DOM IDs added:** 11 section IDs (`wiz-k8s-section-*`) on previously
    anonymous elements in `_wizard_integrations.html`
- Terraform card (CLI, provider, backend)
- DNS card (CDN, domains, certs)

### Phase D — CI/CD + Remaining Cards ✅
- CI/CD section header + card
- Security, Testing, Quality, Packages, Env, Docs (devops_cards extras)

### Phase E — Sub-Forms (per integration) ✅
- Each integration's ⚙️ Setup panel has its own field list
- Deepest nesting (card → setup panel → form section → individual field)
- Docker sub-form alone has ~20 fields

---

## 3. Phase A — Detailed Design

### 3.1 Page Structure (DOM hierarchy)

```
#wizard-body                          ← containerEl passed to activate()
├── <h2> 🔌 Integrations             ← static header (no assistant node)
├── <p> description                   ← static (no assistant node)
└── #wiz-int-body                     ← all dynamic content lives here
    ├── Scan Status Bar               ← no ID, unique structure
    │   ├── "Last scanned: X ago"     ← text
    │   ├── ⚡ stale badge            ← conditional
    │   ├── ✓ fresh badge             ← conditional
    │   └── 🔄 Re-scan button        ← action
    │
    ├── 🔧 SYSTEM TOOLS header        ← <div> with uppercase text
    │   ├── Missing tools container   ← <div> with border
    │   │   ├── #wiz-int-tool-{name}  ← per-tool row (dynamic)
    │   │   └── ...
    │   ├── ✅ All tools installed     ← alternative state
    │   └── Installed pills row       ← <div> with badge spans
    │
    ├── 📋 FILE DETECTION pills       ← <div> with badge spans
    │   └── <span> per file entry     ← ● found / ○ missing
    │
    ├── 🔌 INTEGRATIONS header        ← section
    │   ├── #wiz-int-wrap-int-git     ← card
    │   ├── #wiz-int-wrap-int-github  ← card
    │   └── #wiz-int-wrap-int-pages   ← card
    │
    ├── ⚙️ DEVOPS EXTENSIONS header   ← section
    │   ├── #wiz-int-wrap-int-docker  ← card
    │   ├── #wiz-int-wrap-k8s         ← card
    │   ├── #wiz-int-wrap-terraform   ← card
    │   └── #wiz-int-wrap-dns         ← card
    │
    ├── 🔄 CI/CD header               ← section
    │   └── #wiz-int-wrap-int-ci      ← card
    │
    └── 💡 Footer tip                 ← static
```

### 3.2 Selector Strategy for Phase A

#### Context Root
```json
{
    "context": "wizard/integrations",
    "title": "Integrations & DevOps",
    "icon": "🔌",
    "content": "...",
    "children": [...]
}
```
No selector needed — it's the context root, rendered as the header.

#### Scan Status Bar
**Problem:** No ID on this element. It's the first child of `#wiz-int-body`.
**Solution:** Use `#wiz-int-body > div:first-child` as selector.
**Verification:** Line 30–54 of `_wizard_integrations.html` — the scan bar is
always the first `<div>` injected into `el.innerHTML`.

```json
{
    "id": "scan-bar",
    "title": "Scan Status",
    "icon": "🔍",
    "selector": "#wiz-int-body > div:first-child"
}
```

**Variants:**
- `textContains: "fresh"` → ✓ fresh, scan is recent
- `textContains: "rescan recommended"` → ⚡ stale, files changed

#### System Tools Section
**Problem:** Tools header has no ID. The section is identified by its "System Tools"
text. Tool rows DO have IDs: `wiz-int-tool-{name}`.

**Solution for section:** The tools heading is always the second major visual block
after the scan bar. We can use `.assistant-node` matching via text content, but
better: add a wrapper ID. **Decision point — discuss with user.**

**Alternative:** Use `[id^='wiz-int-tool-']` parent selection. The missing tools
container has no ID but contains all `#wiz-int-tool-*` children.

**Dynamic tool rows:** Each missing tool renders as:
```html
<div id="wiz-int-tool-{name}" style="...">
    <span>✗</span>
    <code>{name}</code>
    <button>📦 Install</button>
</div>
```

These are **only rendered for missing tools**. Installed tools appear as badge pills
without IDs (just `<span>` elements in a flex row).

**childTemplate strategy:**
```json
{
    "id": "system-tools",
    "dynamic": true,
    "childTemplate": {
        "selector": "[id^='wiz-int-tool-']",
        "title": "{{name}}",
        "nameSelector": "code",
        "content": "...",
        "variants": [
            { "when": { "textContains": "bandit" }, "content": "...", "expanded": "..." },
            { "when": { "textContains": "kubectl" }, "content": "...", "expanded": "..." },
            ...
        ]
    }
}
```

**Key insight:** The `nameSelector: "code"` extracts the tool name from the
`<code>{name}</code>` element. Variants then match on `textContains` to provide
per-tool descriptions. This is the same pattern used in Secrets for
`.env.development` vs `.env.production`.

### 3.3 Per-Tool Content (15 tools)

Each tool needs content answering: "What is this? How does it fit in this project's
control plane pipeline? What happens if it's missing?"

Tool knowledge comes from multiple sources in the codebase:

| Tool | L0 Category | Audit Catalog | Pipeline Role |
|------|-------------|---------------|---------------|
| `git` | vcs | — | Foundation — all integrations depend on git repo |
| `gh` | vcs | — | GitHub CLI — secrets sync, PR management, Actions dispatch |
| `docker` | container | — | Container runtime — Dockerfile builds, daemon, images |
| `docker-compose` | container | — | Multi-service orchestration, compose files |
| `kubectl` | container | — | K8s CLI — cluster access, manifest deployment |
| `terraform` | infra | — | IaC — cloud resource provisioning, state management |
| `helm` | container | — | K8s package manager — charts, releases, values |
| `node` | runtime | — | Node.js runtime — required for npm/JS toolchain |
| `npm` | runtime | — | Node package manager — JS dependency management |
| `ruff` | quality | `devtool/linter/python: "Fast linter + formatter"` | Quality pipeline — used in audit L2, enabled in quality card |
| `mypy` | quality | `typing/checker/python: "Static type checker"` | Quality pipeline — type safety in audit scoring |
| `pytest` | quality | `testing/framework/python: "Test framework"` | Testing pipeline — test execution in audit scoring |
| `pip-audit` | security | `security/scanner/python: "Vulnerability scanner"` | Security pipeline — CVE checks against PyPI advisory DB |
| `bandit` | security | `security/scanner/python: "Security linter"` | Security pipeline — AST-level vulnerability detection |
| `safety` | security | `security/scanner/python: "Dependency checker"` | Security pipeline — known vulnerability DB cross-check |

**Install method (from `tool_install.py`):**
- **pip (no sudo):** ruff, mypy, pytest, pip-audit, safety, bandit
- **sudo required:** git, gh, docker, docker-compose, kubectl, terraform, helm, node, npm

### 3.4 File Detection Pills (12 files)

Each file detection pill renders as a `<span>` inside the file detection `<div>`.
They use `● found` vs `○ missing` indicators with colored borders.

**Problem:** These `<span>` elements have no IDs and no unique selectors beyond
their text content (e.g., "● docker compose").

**Analysis of rendering (line 93-97):**
```js
const fileEntries = Object.entries(d.files);
// each renders as: <span>● {key.replace(/_/g, ' ')}</span>
```

The file keys (from `wizard_ops.py` lines 99-118):
```
git_repo, dockerfile, docker_compose, k8s_manifests, terraform_dir,
github_actions, pyproject, package_json, pages_config, dns_dir, cdn_dir, cname_file
```

**Selector strategy options:**
1. **No dynamic matching** — file pills are too small and generic for hover
   tracking. The section-level "File Detection" node covers the entire row.
2. **Add IDs** — could add `id="wiz-int-file-{key}"` to each span in the
   renderer. This would be a minor change to `_wizard_integrations.html`.

**Recommendation:** Option 2 — add IDs to file pills. This is a small,
non-breaking change (add `id="wiz-int-file-${esc(k)}"` to the span template).
This enables per-file dynamic content with childTemplate matching, same as tools.

**Decision point for user:** Are per-file descriptions valuable enough to warrant
the renderer change, or should we treat the file detection row as one section?

### 3.5 Template Resolvers Needed

New resolvers for the Integrations context:

```js
window._assistant.resolvers.toolCount = function() {
    var tools = document.querySelectorAll('[id^="wiz-int-tool-"]');
    return tools ? tools.length : 0;
};

window._assistant.resolvers.installedToolCount = function() {
    // Installed tools appear as success-colored pills
    var pills = document.querySelectorAll('#wiz-int-body .btn-sm'); // approximate
    // Better: count from data
    return '?';  // TBD — may need to read from _wizIntDetection
};

window._assistant.resolvers.integrationCount = function() {
    var cards = document.querySelectorAll('[id^="wiz-int-wrap-"]');
    return cards ? cards.length : 0;
};
```

**Note:** Template resolvers run in the engine's `_resolve()` and substitute
`{{varName}}` in content strings. They must be registered on `window._assistant.resolvers`.

### 3.6 Data Layer Assessment for Phase A

#### What exists and is sufficient:

| Data Source | Used For | Status |
|-------------|----------|--------|
| `_wizIntDetection.tools` | Tool rows — boolean per-tool | ✅ Complete |
| `_wizIntDetection.files` | File detection pills | ✅ Complete |
| `l0_detection._TOOLS` | Tool metadata (label, category, install_type) | ✅ Rich — 35 tools |
| `audit/catalog.py` | Tool descriptions (type, ecosystem) | ✅ For ruff/mypy/pytest/bandit/safety/pip-audit |
| `tool_install.py` | Install recipes (pip vs sudo) | ✅ All 15 covered |

#### What's missing:

**Nothing from the backend.** All Phase A content is authored knowledge —
narrative descriptions of what each tool does *in this control plane*. This is
authored in the `assistant-catalogue.json`, not fetched from an API.

The engine already handles:
- Dynamic `childTemplate` with `nameSelector` extraction ✅
- `variants` with `textContains` matching ✅
- Template variable resolution via `{{resolverName}}` ✅
- Parent chain rendering with depth indentation ✅
- State card HTML (`assistant-state-card`) ✅

#### No new data JSON documents needed for Phase A.

---

## 4. Engine Limitations Check

### Maximum tree depth
The engine's `_flattenTree` is **recursive** with no depth limit. ✅ No issue.

### Dynamic node matching
Dynamic nodes match via **element reference** (`node._element === element`), not
CSS selector. This means `childTemplate` elements are matched by direct DOM
comparison, which works regardless of nesting depth. ✅ No issue.

### Variant resolution on dynamic children
At line 257-268 of the engine: variants on `childTemplate` are resolved against
the DOM element, then `{{name}}` interpolation is re-applied. ✅ Works.

### Multiple `textContains` variants on the same template
The engine iterates variants in order and returns the **first match** (line 76).
For tools, each variant's `textContains` must be **unique to that tool name**.
Since we match on the full `textContent` of the tool row, and each row contains
only one tool name in its `<code>` element, `textContains: "bandit"` won't
accidentally match a row showing "kubectl". ✅ Safe.

**Caveat:** Tool names must not be substrings of each other. Checking:
- `npm` could match `npm` in a row about `npm` — but also could false-match
  text that says "Install with npm". **The tool rows only show the tool name
  in `<code>` and "📦 Install" as button text.** The `textContent` would be
  something like `"✗ bandit 📦 Install"`. No tool name is a substring of
  another tool name in the 15-tool list. ✅ Safe.

### Selector scoping
All selectors are evaluated within `_containerEl` (the `body` element passed to
`activate()`). The integrations content lives inside `#wiz-int-body` which is a
child of `#wizard-body`. ✅ No issue.

---

## 5. Renderer Changes Needed

### 5.1 File Detection pill IDs (optional, recommended)

In `_wizard_integrations.html` line 96, change:

```js
// Before:
${fileEntries.map(([k, v]) => `<span style="...">${v ? '●' : '○'} ${esc(k.replace(/_/g, ' '))}</span>`).join('')}

// After:
${fileEntries.map(([k, v]) => `<span id="wiz-int-file-${esc(k)}" style="...">${v ? '●' : '○'} ${esc(k.replace(/_/g, ' '))}</span>`).join('')}
```

This is a single-line, non-breaking change. It enables the assistant to match
individual file detection pills.

### 5.2 Template resolvers

Add to `_assistant_engine.html` after the existing resolvers (line ~976):

```js
window._assistant.resolvers.toolsMissing = function() {
    var rows = document.querySelectorAll('[id^="wiz-int-tool-"]');
    return rows ? rows.length : 0;
};

window._assistant.resolvers.toolsTotal = function() {
    // Count installed pills + missing rows
    var missing = document.querySelectorAll('[id^="wiz-int-tool-"]').length;
    // Installed pills are success-colored spans in the tools section
    // This is approximate — exact count would need data access
    return missing + document.querySelectorAll('#wiz-int-body span[style*="success"]').length;
};
```

**Decision point:** Are these resolvers worth the complexity, or should we
hardcode counts in the content text? Different projects will have different tool
counts. Template resolvers make the content dynamic ("{{toolsMissing}} tools need
installation") vs static ("Some tools need installation").

---

## 6. Implementation Order (Phase A)

1. **Add file detection pill IDs** (renderer change — 1 line)
2. **Add template resolvers** (engine change — ~10 lines)
3. **Write catalogue entry** — `wizard/integrations` context with:
   - Context root (title, icon, content, expanded)
   - Scan bar child (selector, 2 variants)
   - System Tools child (selector, dynamic=true, childTemplate with 15 variants)
   - File Detection child (selector, dynamic=true, childTemplate with 12 variants)
4. **Test** — verify hover matching, variant resolution, depth rendering

### Estimated catalogue size
- Context root: ~200 chars content + ~500 chars expanded
- Scan bar: ~3 nodes including variants
- System Tools: 1 parent + 15 variant descriptions (~300 chars each) ≈ 5KB
- File Detection: 1 parent + 12 variant descriptions (~200 chars each) ≈ 3KB

Total Phase A addition: ~10KB of JSON.

---

## 7. Open Questions — Resolved

1. **File detection pills** — ✅ IDs added to individual file pills.
   Per-file descriptions enabled via `childTemplate` matching.

2. **Template resolvers** — ✅ Dynamic resolvers added for `{{toolsMissing}}`
   and similar. Content uses template vars for counts.

3. **Installed tools row** — Handled by the parent section node. No IDs
   added to installed tool pills — the "all installed" state is covered
   by the parent's content.

4. **Depth limits** — No issues at 3 levels in Phase A. Later phases
   (cards → sub-forms → fields) hit 4-5 without scroll height issues.
   Panel handles deep nesting well.
