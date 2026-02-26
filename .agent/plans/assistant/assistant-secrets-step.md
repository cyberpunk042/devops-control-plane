# Assistant — wizard/secrets Implementation Plan

> Step 3: 🔐 Secrets & Encryption
>
> **Prerequisite:** Engine evolution for state-variant content nodes.
> This plan covers the evolution first, then the catalogue content.

---

## Phase 1: Engine Evolution — State-Variant Content ✅

### The Problem

The current engine assumes every node has exactly one `content` and one
`expanded` string. For the Secrets step, the same DOM element shows different
states (📭 missing / 🔒 locked / 🔓 unlocked) and the assistant needs to
say different things depending on what's actually on screen.

The existing context-aware enrichment pattern in `_resolveDynamic` handles
this for specific cases (default badge, stack metadata) with hardcoded
if/else logic. That pattern doesn't scale — we need a generic mechanism
the catalogue can drive.

### The Solution: `variants` array on catalogue nodes

A node in the catalogue can carry a `variants` array. Each variant has a
`when` condition and its own `content` / `expanded`. The engine evaluates
conditions against the matched DOM element and picks the first match.
If no variant matches, the node's base `content` / `expanded` are used
as fallback.

#### Catalogue Schema

```json
{
    "id": "env-vault-row",
    "title": "{{name}}",
    "content": "Environment vault for {{name}}.",
    "expanded": "Fallback text if no variant matches.",
    "variants": [
        {
            "when": { "textContains": "unlocked" },
            "content": "Your {{name}} vault is unlocked and ready...",
            "expanded": "You can view, add, or modify secrets..."
        },
        {
            "when": { "textContains": "locked" },
            "content": "Your {{name}} vault is encrypted...",
            "expanded": "You'll need to unlock it from the Secrets tab..."
        },
        {
            "when": { "textContains": "missing" },
            "content": "Your {{name}} vault doesn't exist yet...",
            "expanded": "Hit + Create to generate a .env file..."
        }
    ]
}
```

#### Condition Types

Start with minimal conditions that read the DOM element:

| Condition | Meaning | Implementation |
|-----------|---------|----------------|
| `textContains` | Element's `textContent` contains this string (case-insensitive) | `el.textContent.toLowerCase().includes(val.toLowerCase())` |
| `hasSelector` | Element contains a descendant matching this CSS selector | `!!el.querySelector(val)` |
| `borderContains` | Element's `style.borderColor` contains this value | `el.style.borderColor.includes(val)` |

`textContains` covers 90% of cases — the vault rows literally say
"unlocked", "locked", "missing" in their text. The GitHub integration
rows say "configured", "detected", "could not detect".

#### Engine Change: `_resolveVariant(node, element)`

```javascript
function _resolveVariant(node, element) {
    if (!node.variants || !node.variants.length || !element) return node;

    for (var i = 0; i < node.variants.length; i++) {
        var v = node.variants[i];
        if (!v.when) continue;

        var match = true;

        if (v.when.textContains) {
            match = match && element.textContent
                .toLowerCase()
                .includes(v.when.textContains.toLowerCase());
        }

        if (v.when.hasSelector) {
            match = match && !!element.querySelector(v.when.hasSelector);
        }

        if (v.when.borderContains) {
            match = match && (element.style.borderColor || '')
                .includes(v.when.borderContains);
        }

        if (match) {
            // Merge: variant fields override base fields
            return {
                ...node,
                content: v.content || node.content,
                expanded: v.expanded !== undefined ? v.expanded : node.expanded,
                title: v.title || node.title,
                icon: v.icon || node.icon,
                _variantMatched: true
            };
        }
    }

    return node;  // No match → fallback to base
}
```

#### Where it hooks in

Two integration points:

1. **`_resolveDynamic()`** — after creating the synthetic node from the
   `childTemplate`, call `_resolveVariant(syntheticNode, el)` to select
   variant content. The `{{name}}` interpolation happens BEFORE variant
   selection, so `when.textContains` checks against the real DOM, and
   the variant's `content`/`expanded` can still use `{{name}}`.

2. **`_renderInteractionPath()`** — for static nodes that also have
   variants, call `_resolveVariant(node, matchedElement)` when rendering.
   This requires passing the matched DOM element through the path data.
   Currently `_matchNode` returns `{node, parents}` — it can also return
   `element` so the renderer has it.

**Phase 1 changes (files):**
- `_assistant_engine.html` — add `_resolveVariant()`, hook into
  `_resolveDynamic` and optionally into `_matchNode` result

**Scope:** ~65 lines added (including `nameSelector` support). No breaking
changes — nodes without `variants` behave exactly as before.

**Also added:** `nameSelector` option on `childTemplate` — lets the catalogue
specify exactly where the display name is in the DOM (e.g., `"code"` for vault
rows) instead of relying on the `font-weight:600` / first-text-node heuristic.

---

## Phase 2: Catalogue — wizard/secrets Context ✅

### DOM Map

The secrets step renders this DOM structure:

```
#wizard-body
├── div (flex header)
│   ├── h2: "🔐 Secrets & Encryption"
│   └── button: "🔄 Rescan"                    ← calls renderWizard()
├── p: intro text (multi-env aware)
├── div: "🌍 Environment Vault Status" label
├── #wiz-env-vault-list                        ← dynamic parent
│   ├── #wiz-env-vault-{envName}               ← dynamic child (one per env)
│   │   ├── <span data-env-active hidden>      ← hidden marker (active env only)
│   │   ├── icon + .env filename + desc
│   │   ├── ACTIVE badge (green, active env only)
│   │   └── state label + [Create button]
│   └── ...
├── #wiz-gh-integration                        ← static node, 3 variants
│   └── div: GITHUB_REPOSITORY row
│       └── icon + code + desc + state + [button]
├── #wiz-gh-deploy-envs (conditional, multi-env only) ← child of gh-integration
│   ├── div: "🌐 GitHub Deployment Environments" label
│   ├── #wiz-gh-deploy-list                    ← dynamic child container
│   │   ├── div per env (icon + code + desc + exists/not found + [Create])
│   │   └── ...
│   └── p: hint text
├── #wiz-enc-key-status                        ← static node, 2 variants
│   └── configured card OR not-set form
└── #wiz-secrets-list                          ← dynamic parent
    ├── div: "Detected Secret Files" label
    ├── #wiz-detected-files                    ← dynamic child container
    │   ├── div per secret file
    │   │   ├── icon + <code>filename</code>
    │   │   ├── active-copy badge ("= .env.{name}", .env row in multi-env only)
    │   │   └── state label (Encrypted/Plaintext/Missing)
    │   └── ...
    └── p: hint text
```

### Catalogue Tree

```json
{
    "context": "wizard/secrets",
    "title": "Secrets & Encryption",
    "icon": "🔐",
    "content": "...",
    "children": [
        {
            "id": "env-vault-status",
            "selector": "#wiz-env-vault-list",
            "dynamic": true,
            "childTemplate": {
                "selector": "#wiz-env-vault-list > div",
                "nameSelector": "code",
                "variants": [
                    // Active environment variants (match hidden [data-env-active] marker)
                    { "when": { "textContains": "unlocked", "hasSelector": "[data-env-active]" }, ... },
                    { "when": { "textContains": "locked",   "hasSelector": "[data-env-active]" }, ... },
                    { "when": { "textContains": "missing",  "hasSelector": "[data-env-active]" }, ... },
                    // Inactive environment variants (fallback — no hasSelector)
                    { "when": { "textContains": "unlocked" }, ... },
                    { "when": { "textContains": "locked" }, ... },
                    { "when": { "textContains": "missing" }, ... }
                ]
            }
        },
        {
            "id": "gh-integration",
            "selector": "#wiz-gh-integration",
            "variants": [
                { "when": { "textContains": "configured" }, ... },
                { "when": { "textContains": "detected" }, ... },
                { "when": { "textContains": "could not detect" }, ... }
            ],
            "children": [
                {
                    "id": "gh-deploy-envs",
                    "selector": "#wiz-gh-deploy-envs",
                    "dynamic": true,
                    "childTemplate": {
                        "selector": "#wiz-gh-deploy-list > div",
                        "nameSelector": "code",
                        "variants": [
                            { "when": { "textContains": "exists" }, ... },
                            { "when": { "textContains": "not found" }, ... }
                        ]
                    }
                }
            ]
        },
        {
            "id": "enc-key-status",
            "selector": "#wiz-enc-key-status",
            "variants": [
                { "when": { "textContains": "configured" }, ... },
                { "when": { "textContains": "not set" }, ... }
            ]
        },
        {
            "id": "secrets-list",
            "selector": "#wiz-secrets-list",
            "dynamic": true,
            "childTemplate": {
                "selector": "#wiz-detected-files > div",
                "nameSelector": "code",
                "variants": [
                    // Active copy — .env row in multi-env with "= .env.{name}" badge
                    { "when": { "textContains": "= .env." }, ... },
                    // Environment-specific semantic descriptions
                    { "when": { "textContains": ".env.development" }, ... },
                    { "when": { "textContains": ".env.production" }, ... },
                    // State variants
                    { "when": { "textContains": "Encrypted" }, ... },
                    { "when": { "textContains": "Plaintext" }, ... },
                    { "when": { "textContains": "Missing" }, ... }
                ]
            }
        }
    ]
}
```

**Variant ordering matters** — the engine picks the first match. Active variants
and environment-specific variants are listed before generic state variants so
they win when both conditions are present in the text.

### Content Strategy — What the assistant says

#### Step context (no hover)

Sets the stage. Explains the multi-env file model.

> "This step shows the state of your project's secrets infrastructure.
> In multi-environment mode, .env is the live working copy of the active
> environment — switching environments swaps the underlying file automatically.
> Each environment has its own vault file encrypted independently."

#### 🌍 Environment Vault Status (section hover)

Explains vault-per-environment architecture. Multi-env awareness.

> "Each environment gets its own encrypted .env.{name} file. In multi-env
> mode, .env is a copy of whichever environment is currently active."

#### Dynamic env row variants (6 total: 3 active + 3 inactive)

Active variants use `hasSelector: "[data-env-active]"` to detect the hidden
marker added to the active environment's DOM row. The state label includes
"· ACTIVE" text which also triggers `_highlightActiveEnv()` in the engine.

**unlocked · ACTIVE:** Active env, unlocked. Emphasizes this is the live copy.

**locked · ACTIVE:** Active env, locked. Notes it needs unlocking to work.

**missing · ACTIVE:** Active env, missing. Urgent — the active env has no file.

**unlocked (inactive):** Non-active env, unlocked. Suggests locking when done —
each environment can have its own passphrase for independent protection.

**locked (inactive):** Non-active env, locked. Expected safe state.

**missing (inactive):** Non-active env, missing. Offer + Create.

#### 🔗 GitHub Integration variants (unchanged)

- **configured (✅):** Repo set in .env, integration ready.
- **detected (⚠️):** Auto-detected but not saved. Offer 💾 Save.
- **unknown (❓):** No remote found. Manual setup instructions.

#### 🌐 GitHub Deployment Environments (child of gh-integration)

Now a proper child node with `#wiz-gh-deploy-envs` selector and dynamic
per-env children via `#wiz-gh-deploy-list > div`.

**exists (✅):** Environment provisioned on GitHub. Can push scoped secrets.

**not found (⚠️):** Not on GitHub yet. Offer 🚀 Create.

#### 🔑 Content Encryption Key variants (unchanged)

- **configured (✅):** Key set, encryption ready.
- **not set (⚠️):** No key. Form to enter or generate.

#### 📄 Detected Secret Files (section)

Base content explains multi-env file model: .env = live copy of active
environment, .env.{name} files hold each environment's stored secrets.

#### Dynamic file row variants (6 total)

**= .env. (active copy):** The .env file with the active-copy badge. Explains
that in multi-env mode, .env is automatically maintained as a copy of the
active environment. Switching happens via the 🔐 Secrets tab.

**.env.development:** Semantic description — "Development environment secrets,
typically local databases, test API keys, and debug configurations."

**.env.production:** Semantic description — "Production environment secrets,
live credentials and deployment configs. Lock when moving away — each
environment can have its own passphrase for independent protection."

**Encrypted (🔒):** Safe on disk, can commit to git.

**Plaintext (🔓):** Readable, should lock when done editing.

**Missing (❌):** Expected but not found. Offer + Create.

### Note on GitHub Deployment Environments section

This section is **conditional** — it only appears for multi-env projects.
It's inserted dynamically before `#wiz-enc-key-status` using
`insertAdjacentHTML('beforebegin', ...)`.

**Status: ✅ Done.** Wrapped in `id="wiz-gh-deploy-envs"` with child list
`id="wiz-gh-deploy-list"`. Added as a child of `gh-integration` in the
catalogue with dynamic per-env children and exists/not-found variants.

---

## Phase 3: Resolvers ✅ (no new resolvers needed)

Register resolvers in `_wizard_init.html` for the secrets step:

```javascript
// When activating wizard/secrets:
window._assistant.resolvers.envCount = function() {
    return document.querySelectorAll('#wiz-env-vault-list > div').length;
};
```

Current resolver registration happens generically for all wizard steps.
The `envCount` resolver already exists (pointing at `#wiz-envs > div`
from Step 1). For Step 3 we need an env count that reads the vault list
instead — OR we keep the same resolver and it naturally returns the right
count since both lists have the same environments.

**Decision:** Check if the existing `envCount` resolver targets exist in
the secrets step DOM. If not, the resolver should be step-aware or we
add a separate `vaultEnvCount` resolver.

---

## Implementation Order

1. ✅ **Engine: `_resolveVariant()`** — added the function, hooked into
   `_resolveDynamic` for dynamic `childTemplate` variants
2. ✅ **Engine: static node variants** — `_resolveStaticVariant()` resolves
   via `node.selector` at render-time in `_renderInteractionPath()`
3. ✅ **Engine: `nameSelector`** — added to `_resolveDynamic()` for
   catalogue-driven name extraction
4. ✅ **Catalogue: wizard/secrets** — authored full JSON entry with 4
   sections, 10 state variants total
5. ✅ **Resolvers** — no new ones needed. Existing `envCount` targets Step 1
   DOM; Step 3 content doesn't use `{{envCount}}`
6. 🔲 **Test** — verify all 4 sections, all state combinations
7. ✅ **GitHub Deployment Environments** — `id="wiz-gh-deploy-envs"` wrapper
   added, catalogue child of gh-integration with dynamic per-env children
8. ✅ **Active environment awareness** — `_activeEnvName` hoisted to step
   scope, ACTIVE badge + `[data-env-active]` marker on vault rows,
   active-copy badge on .env in detected files, 6 active/inactive vault
   variants, `_highlightActiveEnv()` in engine
9. ✅ **Backend fix** — `vault_status()` route now respects `?env=` param
10. ✅ **Config loading** — secrets step calls `wizardLoadConfig()` if null
    (fixes direct `/#wizard/secrets` navigation)
11. ✅ **Rescan button** — added to step header, calls `renderWizard()`
12. ✅ **Environment-specific file descriptions** — .env.development and
    .env.production get semantic descriptions in catalogue

---

## Risks

| Risk | Mitigation |
|------|------------|
| `textContains` ambiguity | The state labels ("unlocked", "locked", "missing", "configured") are unique enough within each element's scope |
| Dynamic section insertion (GH Envs) | Uses `insertAdjacentHTML('beforebegin', ...)` which doesn't have a stable ID — may need a wrapping ID added |
| Async rendering | Sections populate via async API calls. `_assistant.activate()` runs after the renderer's Promise resolves, but some sections load after initial render. May need `refresh()` calls or the assistant activates on the final async |
| Template variants on `childTemplate` | This is new — the current `childTemplate` has flat fields. Adding `variants` to `childTemplate` needs engine support in `_resolveDynamic` specifically |
