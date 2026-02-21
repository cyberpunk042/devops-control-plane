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
├── h2: "🔐 Secrets & Encryption"
├── p: intro text
├── div: "🌍 Environment Vault Status" label
├── #wiz-env-vault-list                        ← dynamic parent
│   ├── #wiz-env-vault-{envName}               ← dynamic child (one per env)
│   │   └── icon + .env filename + desc + state label + [button]
│   └── ...
├── #wiz-gh-integration                        ← static node, 3 variants
│   └── div: GITHUB_REPOSITORY row             
│       └── icon + code + desc + state + [button]
├── (conditional) GitHub Deployment Envs        ← dynamic, appears before #wiz-enc-key-status
│   ├── div per env                            ← dynamic child
│   └── ...
├── #wiz-enc-key-status                        ← static node, 2 variants
│   └── configured card OR not-set form
└── #wiz-secrets-list                          ← dynamic parent
    └── div per detected secret file           ← dynamic child, 3 variants
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
            "title": "Environment Vault Status",
            "icon": "🌍",
            "selector": "#wiz-env-vault-list",
            "separator": true,
            "content": "...",
            "expanded": "...",
            "dynamic": true,
            "childTemplate": {
                "title": "{{name}}",
                "selector": "#wiz-env-vault-list > div",
                "content": "...",
                "expanded": "...",
                "variants": [
                    { "when": { "textContains": "unlocked" }, "content": "...", "expanded": "..." },
                    { "when": { "textContains": "locked" }, "content": "...", "expanded": "..." },
                    { "when": { "textContains": "missing" }, "content": "...", "expanded": "..." }
                ]
            }
        },
        {
            "id": "gh-integration",
            "title": "GitHub Integration",
            "icon": "🔗",
            "selector": "#wiz-gh-integration",
            "separator": true,
            "content": "...",
            "expanded": "...",
            "variants": [
                { "when": { "textContains": "configured" }, "content": "...", "expanded": "..." },
                { "when": { "textContains": "detected" }, "content": "...", "expanded": "..." },
                { "when": { "textContains": "could not detect" }, "content": "...", "expanded": "..." }
            ]
        },
        {
            "id": "enc-key-status",
            "title": "Content Encryption Key",
            "icon": "🔑",
            "selector": "#wiz-enc-key-status",
            "separator": true,
            "content": "...",
            "expanded": "...",
            "variants": [
                { "when": { "textContains": "configured" }, "content": "...", "expanded": "..." },
                { "when": { "textContains": "not set" }, "content": "...", "expanded": "..." }
            ]
        },
        {
            "id": "secrets-list",
            "title": "Detected Secret Files",
            "icon": "📄",
            "selector": "#wiz-secrets-list",
            "separator": true,
            "content": "...",
            "expanded": "...",
            "dynamic": true,
            "childTemplate": {
                "title": "{{name}}",
                "selector": "#wiz-secrets-list div[style*='display:flex'] > div",
                "content": "...",
                "variants": [
                    { "when": { "textContains": "Encrypted" }, "content": "...", "expanded": "..." },
                    { "when": { "textContains": "Plaintext" }, "content": "...", "expanded": "..." },
                    { "when": { "textContains": "Missing" }, "content": "...", "expanded": "..." }
                ]
            }
        }
    ]
}
```

### Content Strategy — What the assistant says

#### Step context (no hover)

Sets the stage. Explains the three systems. Notes the immediate-action
difference from Step 1.

> "This step shows the state of your project's secrets infrastructure —
> one vault per environment, your GitHub connection, and the content
> encryption key. Unlike Step 1, some actions here take effect immediately
> when you click them."

#### 🌍 Environment Vault Status (section hover)

Explains vault-per-environment architecture. Connects back to Step 1's
environments. Uses `{{envCount}}` resolver for dynamic count.

> "Each environment you defined in Step 1 gets its own encrypted vault
> file. Development secrets never leak into production — each .env file
> is independent, encrypted separately, and managed through the 🔐
> Secrets tab.
>
> You've got {{envCount}} environments. The goal is to have each one
> either unlocked (ready to edit) or locked (encrypted, safe on disk)."

#### Dynamic env row variants

**unlocked (🔓):**
> "Your {{name}} vault is unlocked and ready. You can view and edit secrets
> through the 🔐 Secrets tab on the dashboard.
>
> Remember to lock it when you're done — plaintext .env files should
> never be committed to git. The .gitignore should already exclude them,
> but encryption is the real protection."

**locked (🔒):**
> "Your {{name}} vault is encrypted — its contents are safely stored on
> disk. To read or edit secrets, unlock it from the 🔐 Secrets tab.
>
> This is the expected state when you're not actively working with
> credentials. The vault passphrase decrypts it on demand."

**missing (📭):**
> "Your {{name}} vault doesn't exist yet. Hit + Create to generate the
> .env file seeded with your Content Vault key.
>
> This is normal for new environments. Creating it here is immediate —
> the file is written to disk as soon as you click. You can add secrets
> to it afterwards through the 🔐 Secrets tab."

#### 🔗 GitHub Integration variants

**configured (✅):**
> "Your GitHub repository is set in .env — the control plane knows where
> to push secrets, dispatch workflows, and manage PRs.
>
> This value stays local to your .env file. It's never pushed to GitHub
> secrets — it's the link between your local vault and your remote repo."

**detected (⚠️):**
> "Your git remote was auto-detected but isn't saved in .env yet. Click
> 💾 Save to .env to persist it.
>
> Once saved, the control plane uses this to sync vault secrets to GitHub
> Actions, dispatch workflows, and manage pull requests. Without it,
> GitHub integration features won't know where to target."

**unknown (❓):**
> "No git remote detected — you can set GITHUB_REPOSITORY manually in
> your .env file as owner/repo (e.g., my-org/my-project).
>
> This is needed if you want secrets sync, GitHub Actions dispatch, or
> PR management through the control plane."

#### 🔑 Content Encryption Key variants

**configured (✅):**
> "Your content encryption key is set and ready. Content files (media,
> documents, assets) managed by the content vault are encrypted with
> this key.
>
> This is separate from your environment vaults above — those handle
> .env secrets (API keys, database URLs). The content encryption key
> protects files, not variables."

**not set (⚠️):**
> "No content encryption key configured. If you plan to encrypt content
> files (media, documents), you'll need this.
>
> Enter your own key (at least 8 characters) or hit 🎲 Generate for a
> strong random one. Either way, it's stored in .env — keep that file
> safe. Losing the key means losing access to encrypted content.
>
> If you don't need content encryption, you can skip this."

#### 📄 Detected Secret Files (section)

> "These are secret files found in your project — .env files, encrypted
> vaults, and related artifacts. This is a read-only snapshot.
>
> For full vault management — locking, unlocking, adding keys, pushing
> to GitHub — use the 🔐 Secrets tab on the dashboard."

#### Dynamic file row variants

**Encrypted (🔒):**
> "{{name}} is encrypted — its contents are safe on disk. Open the 🔐
> Secrets tab if you need to unlock and read it."

**Plaintext (🔓):**
> "{{name}} is in plaintext — anyone with file access can read its
> contents. Use the 🔐 Secrets tab to lock it when you're done editing."

**Missing (❌):**
> "{{name}} is expected but not found. It may have been deleted or hasn't
> been created yet. Use + Create above or the 🔐 Secrets tab to set it up."

### Note on GitHub Deployment Environments section

This section is **conditional** — it only appears for multi-env projects.
It's inserted dynamically before `#wiz-enc-key-status`. The engine can
handle this naturally: if the DOM elements don't exist when `_flattenTree`
runs, no dynamic children are created. We have two options:

1. Add it as a static node with a selector that targets the dynamically
   inserted HTML — if the section doesn't exist, `_matchNode` simply
   won't match it.
2. Skip it for v1 and add it if the user requests it.

**Recommendation:** Option 1. The section header text "GitHub Deployment
Environments" can be the selector anchor. This is a follow-up item after
the core 5 sections are working.

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
7. 🔲 **GitHub Deployment Environments** — deferred (conditional section,
   needs wrapping ID in HTML)

---

## Risks

| Risk | Mitigation |
|------|------------|
| `textContains` ambiguity | The state labels ("unlocked", "locked", "missing", "configured") are unique enough within each element's scope |
| Dynamic section insertion (GH Envs) | Uses `insertAdjacentHTML('beforebegin', ...)` which doesn't have a stable ID — may need a wrapping ID added |
| Async rendering | Sections populate via async API calls. `_assistant.activate()` runs after the renderer's Promise resolves, but some sections load after initial render. May need `refresh()` calls or the assistant activates on the final async |
| Template variants on `childTemplate` | This is new — the current `childTemplate` has flat fields. Adding `variants` to `childTemplate` needs engine support in `_resolveDynamic` specifically |
