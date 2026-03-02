# Secrets — Front-End Scripts

> **7 files · 2,462 lines · The entire Secrets tab.**
>
> This domain owns the Secrets tab — a full secrets manager UI for
> `.env` files with vault encryption, GitHub Secrets/Variables sync,
> multi-environment support, and cryptographic key generation. It lets
> users view, edit, push, and lock their project secrets from the
> browser.

---

## How It Works

### Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│ dashboard.html                                                      │
│                                                                      │
│  {% include 'partials/_tab_secrets.html' %}             ← line 8    │
│  {% include 'scripts/secrets/_secrets.html' %}          ← line 66   │
│                                                                      │
│  _secrets.html is the LOADER — it wraps a single <script> scope    │
│  and includes all 6 modules so they share state.                    │
└────────────────────────────────────────────────────────────────────┘
```

### Module Loading Order

```
_secrets.html               ← Loader (24 lines)
    │
    ├── _init.html           ← State, constants, tier logic, tab load
    ├── _render.html         ← Status bars, file list, main form
    ├── _form.html           ← Target selector, dirty tracking, sections
    ├── _sync.html           ← Save/push, sync, remove, clear, refresh
    ├── _keys.html           ← Add/create modal, templates, generators
    └── _vault.html          ← Vault lock/unlock modals
```

All modules share a single `<script>` scope. `_init.html` defines
shared state, `_render.html` builds the form, and the remaining
modules handle mutations and modals.

### Tab Load Lifecycle

```
loadSecretsTab()                     ← called by _tabs.html on tab switch
    │
    ├── 1. Load project environments (once)
    │     └── GET /api/config → extract environments[]
    │     └── GET /api/vault/active-env → determine which env is live
    │
    ├── 2. Render environment selector pill bar
    │     └── renderEnvSelector() — hidden when single env
    │
    ├── 3. Parallel data fetch (6 requests)
    │     ├── GET /api/vault/status?env=X       → vault state (locked/unlocked/empty)
    │     ├── GET /api/vault/secrets             → env file data (masked values)
    │     ├── GET /api/vault/keys?env=X          → structured key list with sections
    │     ├── GET /api/gh/status                 → GitHub CLI availability
    │     ├── GET /api/gh/secrets                → GitHub secrets list (names only)
    │     └── GET /api/gh/environments           → GitHub deployment environments
    │
    ├── 4. Merge optimistic push results (_recentPushResults)
    │
    ├── 5. Render UI based on vault state:
    │     ├── STATE: empty   → create wizard (manual or template)
    │     ├── STATE: locked  → unlock modal CTA
    │     └── STATE: unlocked → full secrets form
    │
    ├── 6. renderSecretsForm(keys, status)
    │     ├── Section headers with collapse/expand
    │     ├── Per-key rows with value input + local status + GitHub status
    │     ├── Target selector (Both/Local/GitHub)
    │     ├── Save & Push button
    │     └── Manage section (sync, clear, refresh)
    │
    └── 7. Post-render
          ├── renderGhStatusAlert()     — gh CLI status bar
          ├── renderGhEnvAlert()        — missing env warning
          ├── Snapshot initial values    — for dirty tracking
          └── Attach input listeners    — for live dirty checking
```

### Secret Tier System

Every key is assigned a **tier** that determines how it's handled:

```
getSecretTier(keyName, keyMeta)
    │
    ├── 'auto'   → GITHUB_TOKEN / GITHUB_REPOSITORY (runtime-provided)
    │              Result: read-only, cannot be set/deleted
    │
    ├── 'local'  → key has `# local-only` comment in .env
    │              Result: never pushed to GitHub
    │
    ├── 'secret' → key has `# secret` comment OR name contains sensitive patterns
    │              Result: pushed as GitHub encrypted secret
    │
    └── 'var'    → everything else
                   Result: pushed as GitHub variable (plaintext)
```

This tier system drives the GitHub column rendering, push logic,
and per-key action menus.

### Multi-Environment System

When `project.yml` defines multiple environments (dev, staging, production),
the secrets tab gains an environment selector:

```
┌─────────────────────────────────────────────────┐
│ 🌍 Environment: [dev] [staging] [production]    │
│                       ↑ active                  │
│ File: .env.staging                              │
└─────────────────────────────────────────────────┘
```

| Concept | How It Works |
|---------|-------------|
| `selectedEnv` | The environment the user is currently viewing/editing |
| `activeEnv` | The environment whose `.env` file is the live one |
| `_envFile()` | Returns `.env` for dev, `.env.staging` for staging, etc. |
| `_envQS()` | Returns `?env=staging` query string for API calls |
| `activateEnvironment()` | POST `/api/vault/activate-env` to swap live `.env` |
| `switchSecretEnv()` | Client-side switch — reloads tab with new env |

### Dirty Tracking

The form tracks changes in real-time using `checkSecretsDirty()`:

```
For each [data-secret-name] input:
    ├── Compare current value to snapshotted initial value
    ├── Check for marked-for-deletion keys
    └── Check for unsynced keys (local but not on GitHub)

Result → Update save button state + badge showing:
    "3 changed · 2 pending secrets · 1 pending var"
```

### Save & Push Pipeline

```
pushSecrets(target)                    target = 'both' | 'local' | 'github'
    │
    ├── Gate: ensureGhReady() if pushing to GitHub
    │
    ├── Collect changed values from form inputs
    ├── Collect marked-for-deletion keys
    ├── Collect unsynced keys (local → GitHub)
    │
    ├── Split by tier:
    │     ├── tier='secret' → secretsForGh   (encrypted secrets)
    │     ├── tier='var'    → variablesForGh  (plaintext variables)
    │     └── tier='local'  → local only, skip GitHub
    │
    ├── POST /api/secrets/push?env=X
    │     body: { secrets, variables, deletions, local_secrets }
    │
    ├── Show results in terminal output
    │     ├── ✅ Local .env saved
    │     ├── ☁️ SECRET_KEY pushed as secret
    │     ├── 📋 APP_NAME pushed as variable
    │     └── 🗑️ OLD_KEY deleted
    │
    └── Buffer results → _recentPushResults (optimistic update)
        └── Reload tab
```

---

## File Map

```
secrets/
├── _secrets.html     Loader — includes all modules (24 lines)
├── _init.html        State, constants, tier logic, tab load (514 lines)
├── _render.html      Status bars, file list, main form (537 lines)
├── _form.html        Target selector, dirty tracking, sections (179 lines)
├── _sync.html        Save/push, sync, remove, clear, refresh (372 lines)
├── _keys.html        Add/create modal, templates, generators (693 lines)
├── _vault.html       Vault lock/unlock modals (143 lines)
└── README.md         This file
```

---

## Per-File Documentation

### `_secrets.html` — Loader (24 lines)

Pure Jinja2 include orchestrator. Wraps all modules in a single
`<script>` tag. No logic.

### `_init.html` — State & Tab Orchestrator (514 lines)

The core of the Secrets tab. Owns state, environment logic, and
the main `loadSecretsTab()` orchestrator.

**State variables:**

| Variable | Type | Purpose |
|----------|------|---------|
| `envData` | `Object` | Raw env file data (key → masked value) |
| `envKeys` | `Array` | Structured key list from `/vault/keys` |
| `envSections` | `Array` | Sectioned key groups from `/vault/keys` |
| `ghSecrets` | `Array<string>` | GitHub secret names (uppercase) |
| `ghVariables` | `Array<string>` | GitHub variable names (uppercase) |
| `ghEnvironments` | `Array<string>` | GitHub deployment environment names |
| `secretsInitialValues` | `Object` | Snapshot for dirty tracking |
| `secretsDirty` | `boolean` | Whether form has unsaved changes |
| `secretsLoaded` | `boolean` | Guard against duplicate tab loads |
| `_recentPushResults` | `Array` | Optimistic update buffer for push results |
| `currentTarget` | `string` | Active target: `'both'`, `'local'`, or `'github'` |
| `selectedEnv` | `string` | Currently viewed environment |
| `activeEnv` | `string` | Currently active (live) environment |
| `projectEnvironments` | `Array` | All environments from project config |

**Functions:**

| Function | What It Does |
|----------|-------------|
| `getSecretTier(keyName, keyMeta)` | Classify key tier (auto/local/secret/var) |
| `loadSecretsTab()` | Main orchestrator — parallel fetch + render |
| `renderEnvSelector()` | Build environment pill bar |
| `activateEnvironment(envName)` | POST to swap live `.env` file |
| `switchSecretEnv(envName)` | Client-side env switch + tab reload |
| `togglePasswordVis(btn)` | Show/hide password input (lazy-fetches raw value) |
| `showB64Decoded(btn, keyName)` | Decode base64 value in popup modal |
| `regenerateKey(keyName, genType)` | Regenerate a generated key (password/ssh/cert/token) |
| `showKeyConfig(event, keyName)` | Key config popover (type, encoding, options) |
| `saveKeyConfig(keyName)` | POST meta tags for a key |

### `_render.html` — UI Rendering (537 lines)

Handles all visual output for the secrets form.

| Function | What It Does |
|----------|-------------|
| `renderVaultStatusBar(status)` | Vault status icon + lock/unlock button |
| `renderGhStatusAlert(ghStatus, ghData)` | GitHub CLI status bar (ready/not ready) |
| `renderGhEnvAlert()` | Warning when GitHub env doesn't exist |
| `createGhEnvironment(envName)` | Create GitHub deployment environment |
| `renderSecretFiles(files)` | Show related files (.env, .env.vault, etc.) |
| `renderSecretsForm(data, status)` | **Main form renderer** — handles all 3 states |

**Form states:**

| State | Trigger | UI |
|-------|---------|-----|
| `empty` | No `.env` file | Create wizard + template button |
| `locked` | `.env.vault` exists, `.env` doesn't | Unlock CTA |
| `unlocked` | `.env` exists and readable | Full secrets form |

**Per-key rendering:**

Each key row includes:
- Kind icon (🔑 secret / 📋 config)
- Key name with move menu + config gear
- Meta badges (b64, gen:password, type:toggle, etc.)
- Value input (text, password, toggle, select — driven by meta)
- Local status column (✅/❌)
- GitHub status column (tier-aware: secret/variable/auto/local)
- Action buttons (delete, mark deletion, pin local-only)

### `_form.html` — Form Controls (179 lines)

| Function | What It Does |
|----------|-------------|
| `selectTarget(target)` | Switch between both/local/github targets |
| `checkSecretsDirty()` | Compare current values to snapshot, update badge |
| `toggleSecretSection(catId)` | Collapse/expand a section (persisted in sessionStorage) |
| `renameSectionPrompt(oldName)` | Rename a section via prompt |
| `markForDeletion(name)` | Mark a key for deletion (visual strikethrough) |
| `unmarkDeletion(name)` | Undo deletion mark |

### `_sync.html` — Push & Sync Operations (372 lines)

| Function | What It Does |
|----------|-------------|
| `pushSecrets(target)` | **Main save/push orchestrator** — collects changes, splits by tier, POSTs |
| `syncEnvToGithub()` | Bulk sync: push ALL `.env` keys to GitHub |
| `removeSecret(name, target, kind)` | Remove a single key from local/github/both |
| `clearSecretsPrompt(target)` | Clear ALL secrets from local or GitHub |
| `toggleLocalOnly(name, makeLocal)` | Toggle the `# local-only` flag on a key |
| `refreshSecrets()` | Force-reload tab (with dirty confirmation) |

**Push flow detail:**

1. Gate on `ensureGhReady()` for GitHub targets
2. Collect `secrets` (changed values), `deletions` (marked keys)
3. Collect `syncKeys` (unsynced local → GitHub keys)
4. Split by `getSecretTier()`: secrets → encrypted, vars → plaintext
5. POST to `/api/secrets/push?env=X`
6. Show terminal-style output with per-key results
7. Buffer results in `_recentPushResults` for optimistic UI update
8. Reload tab with smooth overlay transition

### `_keys.html` — Key Management & Generation (693 lines)

The largest module. Handles key CRUD, template-based creation,
and cryptographic generation.

**Key move system:**

| Function | What It Does |
|----------|-------------|
| `showMoveKeyMenu(event, keyName)` | Context menu to move key between sections |
| `moveKeyToSection(keyName, section)` | POST `/api/vault/move-key` |

**Add keys modal:**

| Function | What It Does |
|----------|-------------|
| `showAddKeysModal(mode)` | Open modal (mode = 'create' or 'add') |
| `addEnvEntry()` | Add another key-value input row |
| `removeEnvEntry(row)` | Remove a key-value row |
| `onEntryTypeChange(sel)` | Show/hide options input for select-type keys |
| `doAddKeys()` | Submit keys — routes to manual or generator |
| `onSectionSelectChange(sel)` | Toggle new-section input when "New section" selected |

**Template system:**

| Function | What It Does |
|----------|-------------|
| `createEnvFromTemplate()` | Open template picker modal |
| `templateSelectAll()` | Check all template sections |
| `doCreateFromTemplate()` | POST selected template sections → create `.env` |

**Generator tabs (within Add Keys modal):**

| Tab | Key Created | How |
|-----|------------|-----|
| ✏️ Manual | Any | User types key + value |
| 🔑 Password | `*_KEY`, `*_SECRET` | POST `/api/keys/generate` type=password |
| 🔐 SSH Key | `*_PRIVATE_KEY` + public | POST `/api/keys/generate` type=ssh, shows public key |
| 📜 Certificate | `*_CERT` + `*_KEY` | POST `/api/keys/generate` type=cert, self-signed EC P-256 |
| 🎫 Token | `*_TOKEN` | POST `/api/keys/generate` type=token |

Each generator:
1. Creates the key via API
2. Sets the value in `.env` via `/api/secret/set`
3. Applies meta tags via `/api/vault/set-meta`
4. Shows public key/cert in a modal if applicable

### `_vault.html` — Vault Lock/Unlock (143 lines)

| Function | What It Does |
|----------|-------------|
| `showVaultLockModal()` | Modal: passphrase + confirm → encrypt `.env` → `.env.vault` |
| `showVaultUnlockModal()` | Modal: passphrase → decrypt `.env.vault` → `.env` |
| `closeVaultModal()` | Remove modal from DOM |
| `vaultDoLock()` | Validate passphrase (min 4, match confirm) → POST `/api/vault/lock` |
| `vaultDoUnlock()` | POST `/api/vault/unlock` → reload tab |

**Encryption:** AES-256-GCM. Plaintext `.env` is securely deleted
after locking. Auto-lock re-encrypts after inactivity.

---

## Dependency Graph

### Internal Dependencies

```
_init.html              ← standalone, defines all shared state
    ↑
_render.html            ← uses envData, envKeys, envSections, ghSecrets,
    ↑                      ghVariables, ghEnvironments, getSecretTier
_form.html              ← uses secretsInitialValues, secretsDirty,
    ↑                      envKeys, ghSecrets, ghVariables, currentTarget
_sync.html              ← uses envData, envKeys, getSecretTier,
    ↑                      _recentPushResults, currentTarget
_keys.html              ← uses envSections, _envQS, _envFile,
    ↑                      closeVaultModal (from _vault.html)
_vault.html             ← uses _envQS, _envFile, loadSecretsTab
```

### External Dependencies

```
globals/_api.html        ← api(), apiPost(), esc(), toast()
_tabs.html               ← switchTab() (tab navigation)
_settings.html           ← prefsGet(), prefsSet()
auth/_gh_auth.html       ← ensureGhReady() (gate for GitHub pushes)
```

---

## Consumers

### Tab Loading

| File | How |
|------|-----|
| `dashboard.html` (line 8) | `{% include 'partials/_tab_secrets.html' %}` — HTML structure |
| `dashboard.html` (line 66) | `{% include 'scripts/secrets/_secrets.html' %}` — JS logic |
| `_tabs.html` (line 78) | `loadSecretsTab()` — called on tab switch |

### Cross-Domain References

| Consumer | What It Calls | Why |
|----------|--------------|-----|
| `_tabs.html` | `loadSecretsTab()` | Tab switcher triggers load |
| Setup wizards | Env key data from vault | Wizards read vault state for env config |

### API Endpoints Used

| Category | Endpoints |
|----------|----------|
| **Vault** | `GET /api/vault/status`, `GET /api/vault/secrets`, `GET /api/vault/keys`, `POST /api/vault/lock`, `POST /api/vault/unlock`, `POST /api/vault/move-key`, `POST /api/vault/set-meta`, `POST /api/vault/raw-value`, `GET /api/vault/templates`, `POST /api/vault/create-from-template`, `GET /api/vault/active-env`, `POST /api/vault/activate-env` |
| **Secrets** | `POST /api/secrets/push`, `POST /api/secret/set`, `POST /api/secret/add`, `POST /api/secrets/remove` |
| **Keys** | `POST /api/keys/generate` |
| **GitHub** | `GET /api/gh/status`, `GET /api/gh/secrets`, `GET /api/gh/environments`, `POST /api/gh/environments/create` |
| **Config** | `GET /api/config` |

---

## Design Decisions

### Why split into 6 files instead of one monolith?

At 2,462 lines, a single file would be unmaintainable. The split
follows **concern boundaries**:
- `_init.html` — state and orchestration (what to load)
- `_render.html` — display (how to show it)
- `_form.html` — interaction tracking (what changed)
- `_sync.html` — mutations (where to send it)
- `_keys.html` — CRUD + generation (what to create)
- `_vault.html` — encryption lifecycle (how to protect it)

Each file can be read in isolation once you know the shared state
from `_init.html`.

### Why a tier system instead of per-key "push to GitHub" toggles?

The tier system (`auto`/`local`/`secret`/`var`) is more expressive
than a boolean toggle. It encodes both **intent** (should this go
to GitHub?) and **mechanism** (encrypted secret vs plaintext variable).
GitHub Actions treats secrets and variables differently — secrets are
encrypted, write-only, and available as `${{ secrets.X }}`, while
variables are plaintext, readable, and available as `${{ vars.X }}`.
The tier system maps directly to these GitHub primitives.

### Why optimistic push results?

After pushing secrets to GitHub, the `gh secret list` API may not
immediately reflect the new state (GitHub's eventual consistency).
The `_recentPushResults` buffer stores what was just pushed, and
`loadSecretsTab()` merges these into the next GitHub status fetch.
This prevents the confusing UX of pushing a secret and then seeing
it listed as "not on GitHub" for a few seconds.

### Why does `togglePasswordVis()` lazy-fetch the raw value?

Secret values in the form are **masked** by default (received as
`"***"` from the API). The actual value is only fetched when the
user clicks the eye icon. This prevents secret values from being
in the DOM unless explicitly requested, reducing exposure in
browser dev tools and memory dumps.

### Why 6 parallel fetches in `loadSecretsTab()`?

The 6 data sources are independent — vault status, env keys, GitHub
secrets, etc. Fetching them sequentially would take 6× the latency.
`Promise.all()` fires all 6 in parallel, so the tab loads in the
time of the slowest single request rather than the sum of all.

### Why does the Add Keys modal have 5 generator tabs?

Different secret types have different generation requirements:
- **Manual** — user provides key and value
- **Password** — random bytes, configurable length
- **SSH Key** — ED25519 keypair, public key shown after generation
- **Certificate** — self-signed EC P-256, cert + key pair
- **Token** — URL-safe random token

Each generator calls the same `/api/keys/generate` endpoint with
a `type` param, but the UI needs different inputs (length slider,
key name, etc.) and different post-generation flows (show public
key, show certificate, etc.).

### Why use `# local-only` comments in `.env` instead of a separate config?

The `.env` file is the source of truth. Storing tier metadata
**inside** the `.env` file (as comments) means the information
travels with the file — no separate sidecar config to sync.
The `# local-only` comment convention is human-readable and
compatible with all `.env` parsers (they ignore comments).

### Why does vault lock require passphrase confirmation but unlock doesn't?

Lock is a **destructive** operation — it encrypts the plaintext
`.env` and deletes it. If the user mistypes the passphrase, they
lose access to their secrets permanently. Confirmation prevents
this. Unlock is **idempotent** — a wrong passphrase simply fails
with an error message, and the user can retry. No data is lost
on a failed unlock attempt.

---

## Advanced Feature Showcase

> Complex patterns and non-obvious techniques found in the Secrets
> front-end source code, with real code examples.

---

### 1. Six-Way Parallel Data Fetch with Optimistic Update Merge

**File:** `_init.html` · **Lines 113–143**

The tab load fires 6 independent API calls in parallel via
`Promise.all()`, then merges in buffered push results to cover
GitHub's eventual consistency gap.

```javascript
// _init.html lines 113–120
const [status, secrets, keys, ghStatus, ghData, ghEnvData] = await Promise.all([
    api(`/vault/status${qs}`),
    api('/vault/secrets'),
    api(`/vault/keys${qs}`),
    api('/gh/status').catch(() => ({ installed: false, authenticated: false })),
    api(`/gh/secrets${qs}`).catch(() => ({ available: false, secrets: [], variables: [] })),
    api('/gh/environments').catch(() => ({ available: false, environments: [] })),
]);

// _init.html lines 131–143 — optimistic merge
if (_recentPushResults.length > 0) {
    for (const r of _recentPushResults) {
        if (!r.success) continue;
        const upper = r.name.toUpperCase();
        if (r.kind === 'secret' && !ghSecrets.includes(upper)) {
            ghSecrets.push(upper);
        }
        if (r.kind === 'variable' && !ghVariables.includes(upper)) {
            ghVariables.push(upper);
        }
    }
    _recentPushResults = [];
}
```

**Why it matters:** GitHub APIs don't reflect newly-set secrets
immediately. Without the optimistic merge, a user who just pushed
`API_KEY` would see it listed as "❌ Not on GitHub" for several
seconds. The `_recentPushResults` buffer eliminates this jarring
UX gap. The `.catch()` fallbacks on each GitHub call also ensure
the entire tab doesn't fail if `gh` isn't installed.

---

### 2. Four-Tier Secret Classification System

**File:** `_init.html` · **Lines 62–72**

Every key is classified into one of 4 tiers that drive rendering,
push routing, and per-key action menus across the entire tab.

```javascript
// _init.html lines 62–72
function getSecretTier(name, keyMeta) {
    if (AUTO_PROVIDED.includes(name)) return 'auto';
    // Check per-key local_only flag from API
    if (keyMeta && keyMeta.local_only) return 'local';
    // Fallback: look it up in envKeys
    const found = envKeys.find(k => k.key === name);
    if (found && found.local_only) return 'local';
    // kind-based: secret → gh secret set, config → gh variable set
    const kind = (keyMeta && keyMeta.kind) || (found && found.kind) || 'config';
    return kind === 'secret' ? 'secret' : 'var';
}
```

**Tier routing in the GitHub column** (`_render.html` lines 411–433):

```javascript
switch (tier) {
    case 'auto':
        ghColumn = `<div title="Auto-provided by GitHub Actions">🔄 Auto</div>`;
        break;
    case 'local':
        ghColumn = `<div>📁 Local</div>
            <button onclick="toggleLocalOnly('${esc(k.key)}', false)">↗️</button>`;
        break;
    case 'secret':
        ghColumn = `<div>${ghSet ? '✅' : '❌'} Secret</div>
            <button onclick="toggleLocalOnly('${esc(k.key)}', true)">📌</button>`;
        break;
    case 'var':
        ghColumn = `<div>${varSet ? '✅' : '❌'} Variable</div>
            <button onclick="toggleLocalOnly('${esc(k.key)}', true)">📌</button>`;
        break;
}
```

**Why it matters:** The push orchestrator in `_sync.html` relies on
this tier to split keys into `secretsForGh` (encrypted, write-only)
vs `variablesForGh` (plaintext, readable). The tier also controls
which action buttons appear per-row — `auto` keys can't be deleted,
`local` keys can be "unlocal-ized" with ↗️, and sync keys get a 📌
pin to mark as local-only.

---

### 3. Multi-State Form Rendering (empty → locked → unlocked)

**File:** `_render.html` · **Lines 194–252**

The main form renderer handles 4 distinct vault states, each with a
completely different UI, using an early-return pattern.

```javascript
// _render.html lines 194–252
function renderSecretsForm(data, status) {
    const container = document.getElementById('secrets-form');

    // STATE: empty — no .env file exists
    if (data.state === 'empty') {
        container.innerHTML = `
        <div class="env-empty-state">
            <span>📝</span>
            <h3>No ${esc(envFile)} file found</h3>
            <button onclick="showAddKeysModal('create')">✨ Create ${esc(envFile)}</button>
            <button onclick="createEnvFromTemplate()">📋 Use Template</button>
        </div>`;
        return;
    }

    // STATE: locked — vault encrypted
    if (data.state === 'locked') {
        container.innerHTML = `
        <div class="env-keys-locked">
            <span>🔒</span>
            <span><code>${esc(envFile)}</code> is encrypted. Unlock the vault.</span>
        </div>`;
        return;
    }

    // STATE: unlocked, no keys
    if (!data.keys || !data.keys.length) {
        container.innerHTML = `
        <div class="empty-create-box">
            <span>📭</span>
            <h3>${esc(envFile)} is empty</h3>
            <button onclick="showAddKeysModal('add')">✨ Add Keys</button>
        </div>`;
        return;
    }

    // STATE: unlocked, has keys — full section-based form
    // ... (254–537: section headers, per-key rows, save section, manage section)
}
```

**Why it matters:** Each state presents fundamentally different
affordances. The `empty` state offers both manual creation and
template picker. The `locked` state only shows an unlock CTA.
The `unlocked+empty` state offers an add wizard. The full form
state renders sections, key rows, target selector, and management
tools. The early-return pattern keeps each branch self-contained.

---

### 4. Metadata-Driven Per-Key Input Rendering

**File:** `_render.html` · **Lines 299–397**

Each key row's input widget is dynamically chosen based on the key's
`@meta` tags — toggle switches, select dropdowns, password fields,
or plain text. Base64-encoded keys get a decode viewer button, and
generated keys get a regenerate button.

```javascript
// _render.html lines 299–397
for (const k of section.keys) {
    const meta = k.meta || {};
    const metaType = meta.type || '';
    const isToggle = metaType === 'toggle';
    const isSelect = metaType === 'select';
    const isPassword = metaType === 'password' || isSecret;
    const isB64 = meta.encoding === 'base64';
    const generated = meta.generated || '';

    let valueHtml = '';

    if (isToggle) {
        // Render a toggle switch (checkbox + label)
        const checked = ['true', '1', 'yes', 'on'].includes(
            (currentValue || k.masked || '').toLowerCase()
        );
        valueHtml = `
            <label class="toggle-switch">
                <input type="checkbox" ${checked ? 'checked' : ''}
                       data-secret-name="${esc(k.key)}"
                       data-meta-toggle="true"
                       onchange="... checkSecretsDirty()">
            </label>
            <span data-toggle-label>${checked ? 'true' : 'false'}</span>`;
    } else if (isSelect && meta.options && meta.options.length) {
        // Render a select dropdown from @options meta
        valueHtml = `
            <select data-secret-name="${esc(k.key)}" ...>
                ${meta.options.map(o =>
                    `<option ${o === currentValue ? 'selected' : ''}>${esc(o)}</option>`
                ).join('')}
            </select>`;
    } else {
        // Standard text/password input with optional extra buttons
        let extraBtns = '';
        if (isPassword)
            extraBtns += `<button onclick="togglePasswordVis(this)">👁️</button>`;
        if (isB64)
            extraBtns += `<button onclick="showB64Decoded(this, '${esc(k.key)}')">🔓 b64</button>`;
        if (generated)
            extraBtns += `<button onclick="regenerateKey('${esc(k.key)}', '${esc(generated)}')">🔄</button>`;

        valueHtml = `
            <input type="${isPassword ? 'password' : 'text'}"
                   data-secret-name="${esc(k.key)}"
                   data-tier="${tier}"
                   placeholder="${placeholder}" value="${esc(currentValue)}">
            ${extraBtns}`;
    }
}
```

**Why it matters:** A single form renderer handles 5 distinct input
types without any framework component abstraction. The meta system
(`@type:toggle`, `@type:select`, `@encoding:base64`, `@generated:ssh`)
is stored as comments inside `.env`, so it travels with the file.
The dirty tracker in `_form.html` also handles toggles specially —
reading `el.checked` instead of `el.value`.

---

### 5. Five-Tab Cryptographic Generator Modal with Preview

**File:** `_keys.html` · **Lines 84–226, 488–692**

The Add Keys modal contains 5 generator tabs (Manual, Password, SSH,
Cert, Token). Each tab has different inputs, and the modal overrides
`doAddKeys()` at runtime to route to the active generator.

```javascript
// _keys.html lines 551–555 — runtime function override
const _origDoAddKeys = doAddKeys;
doAddKeys = async function() {
    if (_activeGenTab === 'manual') {
        return _origDoAddKeys();
    }
    // ... route to password/ssh/cert/token handler
};

// _keys.html lines 606–646 — SSH key generation flow
} else if (_activeGenTab === 'ssh') {
    const keyName = document.getElementById('gen-ssh-key')?.value.trim().toUpperCase();
    if (!keyName) { errEl.textContent = 'Enter a key name'; return; }
    const algo = document.querySelector('input[name=gen-ssh-algo]:checked')?.value || 'ssh-ed25519';

    const result = await api('/keys/generate', {
        method: 'POST',
        body: JSON.stringify({ type: algo }),
    });

    await api('/vault/add-keys' + _envQS(), {
        method: 'POST',
        body: JSON.stringify({ entries: [{ key: keyName, value: result.value }] }),
    });
    // Set meta tags (encoding:base64, generated:ssh-ed25519)
    if (result.meta_tags) {
        await api('/vault/set-meta' + _envQS(), {
            method: 'POST',
            body: JSON.stringify({ key: keyName, meta_tags: result.meta_tags }),
        });
    }
    closeVaultModal();

    // Show public key in a follow-up modal
    if (result.public_value) {
        const pubModal = document.createElement('div');
        pubModal.className = 'vault-modal-overlay';
        pubModal.innerHTML = `
            <div class="vault-modal">
                <h3>🔑 ${esc(algo)} Public Key</h3>
                <pre>${esc(result.public_value)}</pre>
                <button onclick="navigator.clipboard.writeText(...)">📋 Copy</button>
            </div>`;
        document.body.appendChild(pubModal);
    }
}
```

**Why it matters:** The runtime function override pattern
(`const _origDoAddKeys = doAddKeys; doAddKeys = async function()`)
avoids the need for a conditional dispatch inside the original
`doAddKeys()`. Password and Token tabs also cache preview results
in `_lastGenResult` so the user can preview before committing,
and the already-generated value is reused instead of making a
duplicate API call.

---

### 6. Tier-Aware Push Orchestrator with Sync Key Backfill

**File:** `_sync.html` · **Lines 14–161**

The push orchestrator collects 3 categories of changes, splits them
by tier, handles the edge case of secret-type keys whose raw values
aren't in the DOM, and provides per-row loading states.

```javascript
// _sync.html lines 38–59 — sync key backfill
const syncKeys = [];
if (target === 'both') {
    for (const k of envKeys) {
        if (!k.has_value) continue;
        if (secrets[k.key] || deletions.includes(k.key)) continue;
        const t = getSecretTier(k.key, k);
        if (t === 'auto' || t === 'local') continue;
        const missingFromGh = (t === 'secret' && !ghSecrets.includes(k.key.toUpperCase()))
            || (t === 'var' && !ghVariables.includes(k.key.toUpperCase()));
        if (missingFromGh) {
            if (envData[k.key]) {
                secrets[k.key] = envData[k.key];
            } else {
                // Secret-type key — raw value not available in frontend
                // Signal backend to read from .env directly
                syncKeys.push(k.key);
            }
        }
    }
}

// _sync.html lines 67–77 — tier-based splitting
const secretsForGh = {};
const variablesForGh = {};
if (ghPush) {
    for (const [name, val] of Object.entries(secrets)) {
        const t = getSecretTier(name);
        if (t === 'auto' || t === 'local') continue;
        if (t === 'secret') secretsForGh[name] = val;
        else if (t === 'var') variablesForGh[name] = val;
    }
}

// _sync.html lines 88–92 — per-row loading state
for (const name of [...Object.keys(secrets), ...deletions, ...syncKeys]) {
    const row = document.querySelector(`[data-key-name="${name}"]`);
    if (row) { row.style.opacity = '0.5'; row.style.pointerEvents = 'none'; }
}
```

**Why it matters:** The `syncKeys` array handles a tricky edge case:
secret-type keys with `has_value=true` but whose raw values are
**not** in `envData` (because secret values are masked). These keys
can't be pushed from the frontend — the push payload sends `null`
for them, and the backend reads the raw value from `.env` directly.
This two-path approach keeps secret data out of the DOM entirely.

---

### 7. Template-Based .env Creation with Section Picker

**File:** `_keys.html` · **Lines 376–478**

When no `.env` file exists, users can bootstrap from predefined
templates. The template picker loads sections from the backend,
renders interactive checkbox cards, and creates the file with
selected sections.

```javascript
// _keys.html lines 376–438 — template picker modal
async function createEnvFromTemplate() {
    let templateSections;
    try {
        const data = await api('/vault/templates');
        templateSections = data.sections || [];
    } catch (e) {
        toast(`Failed to load templates: ${e.message}`, 'error');
        return;
    }

    // Render section cards with checkbox, name, description, and key preview
    modal.innerHTML = `
        <div id="template-sections">
            ${templateSections.map(s => {
                const isSpecial = s.special;
                const keysPreview = s.keys.map(k => k.key).join(', ');
                return `
                <label data-template-label="${esc(s.id)}">
                    <input type="checkbox" value="${esc(s.id)}" class="template-checkbox"
                           ${isSpecial ? 'checked' : ''}>
                    <div>
                        <span>${esc(s.name)}</span>
                        ${isSpecial ? '<span>Required</span>' : ''}
                        <div>${esc(s.description)}</div>
                        <div>${esc(keysPreview)}</div>
                    </div>
                </label>`;
            }).join('')}
        </div>
        <button onclick="templateSelectAll()">Select All</button>
        <button onclick="doCreateFromTemplate()">📋 Create ${esc(envFile)}</button>`;
}

// _keys.html lines 444–478 — submit selected templates
async function doCreateFromTemplate() {
    const selected = Array.from(
        document.querySelectorAll('.template-checkbox:checked')
    ).map(cb => cb.value);

    await api(`/vault/create${_envQS()}`, {
        method: 'POST',
        body: JSON.stringify({ template_sections: selected }),
    });
    toast(`${envFile} created with ${selected.length} section(s)`, 'success');
    secretsLoaded = false;
    await loadSecretsTab();
}
```

**Why it matters:** The template system lets users bootstrap a
properly-structured `.env` file with categorized sections
(General, Database, API Keys, etc.) instead of manually typing
every key. The `special` flag auto-checks required sections,
and each card shows a key preview so users know exactly what
they're getting. The "Select All" button is a convenience for
users who want the full template.

---

### 8. Lazy-Fetch Password Reveal with Base64 Decode Viewer

**File:** `_init.html` · **Lines 290–372**

Secret values are never pre-loaded into the form. The eye icon
triggers a lazy fetch of the raw value, and a separate decode
viewer handles base64-encoded keys.

```javascript
// _init.html lines 290–327 — lazy password reveal
async function togglePasswordVis(btn) {
    const input = btn.closest('.secret-config-value')?.querySelector('input');
    if (!input) return;

    if (input.type === 'text') {
        // Hide → restore password mode
        input.type = 'password';
        if (input.dataset.wasEmpty === 'true') {
            input.value = '';
            delete input.dataset.wasEmpty;
        }
        btn.textContent = '👁️';
        return;
    }

    // Reveal → if input is empty (secret with no typed value), fetch raw value
    if (!input.value && input.dataset.secretName) {
        btn.textContent = '⏳';
        try {
            const data = await api('/vault/raw-value' + _envQS(), {
                method: 'POST',
                body: JSON.stringify({ key: input.dataset.secretName }),
            });
            if (data.value) {
                input.value = data.value;
                input.dataset.wasEmpty = 'true';  // flag for re-masking
            }
        } catch (e) {
            toast('Could not fetch value: ' + e.message, 'error');
            return;
        }
    }
    input.type = 'text';
    btn.textContent = '🙈';
}

// _init.html lines 330–372 — base64 decode viewer
async function showB64Decoded(btn, keyName) {
    const data = await api('/vault/raw-value' + _envQS(), {
        method: 'POST',
        body: JSON.stringify({ key: keyName }),
    });
    let decoded;
    try { decoded = atob(data.value); }
    catch (e) { decoded = '(not valid base64)'; }

    window._b64DecodedValue = decoded;  // store for clipboard copy
    // Show modal with encoded size, decoded size, and copy button
    modal.innerHTML = `
        <h3>🔓 Decoded: ${esc(keyName)}</h3>
        <div>${data.value.length} bytes encoded → ${decoded.length} bytes decoded</div>
        <pre>${esc(decoded)}</pre>
        <button onclick="navigator.clipboard.writeText(window._b64DecodedValue)">📋 Copy Decoded</button>`;
}
```

**Why it matters:** Secret values are **never** in the DOM until
the user explicitly clicks the eye icon. This is a security pattern —
the form receives masked `"••••••••"` placeholders from the API, and
only fetches the real value on demand via POST. The `wasEmpty` flag
ensures that when the user hides the value again, the input is
cleared back to empty (so the raw value doesn't persist in the DOM).
The base64 viewer adds a second layer: keys like SSH private keys
are stored base64-encoded, and the viewer decodes them in a popup
with size information to help users verify correctness.

---

### Feature Coverage Summary

| # | Feature | File(s) | Key Function(s) | Complexity |
|---|---------|---------|-----------------|------------|
| 1 | 6-way parallel data fetch | `_init.html` | `loadSecretsTab` | High |
| 2 | Optimistic push result merge | `_init.html` | `loadSecretsTab` (lines 131–143) | Medium |
| 3 | 4-tier secret classification | `_init.html` | `getSecretTier` | Medium |
| 4 | Multi-environment selector | `_init.html` | `renderEnvSelector`, `switchSecretEnv`, `activateEnvironment` | High |
| 5 | Environment activation/swap | `_init.html` | `activateEnvironment` | Medium |
| 6 | URL hash sync on env switch | `_init.html` | `switchSecretEnv` (line 264) | Low |
| 7 | Lazy-fetch password reveal | `_init.html` | `togglePasswordVis` | Medium |
| 8 | Base64 decode viewer modal | `_init.html` | `showB64Decoded` | Medium |
| 9 | Key regeneration with meta tags | `_init.html` | `regenerateKey` | Medium |
| 10 | Key configuration popover | `_init.html` | `showKeyConfig`, `saveKeyConfig` | Medium |
| 11 | Vault status bar (4 states) | `_render.html` | `renderVaultStatusBar` | Low |
| 12 | GitHub CLI status alert (3 states) | `_render.html` | `renderGhStatusAlert` | Low |
| 13 | GitHub environment detection | `_render.html` | `renderGhEnvAlert`, `createGhEnvironment` | Medium |
| 14 | Multi-state form rendering | `_render.html` | `renderSecretsForm` | High |
| 15 | Metadata-driven input rendering | `_render.html` | `renderSecretsForm` (per-key loop) | High |
| 16 | Section collapse with sessionStorage | `_render.html`, `_form.html` | `toggleSecretSection` | Low |
| 17 | Dirty tracking with pending badge | `_form.html` | `checkSecretsDirty` | Medium |
| 18 | Mark/unmark deletion with undo | `_form.html` | `markForDeletion`, `unmarkDeletion` | Medium |
| 19 | Section rename | `_form.html` | `renameSectionPrompt` | Low |
| 20 | Tier-aware push orchestrator | `_sync.html` | `pushSecrets` | High |
| 21 | Sync key backfill (secret-type) | `_sync.html` | `pushSecrets` (syncKeys logic) | High |
| 22 | Bulk env→GitHub sync | `_sync.html` | `syncEnvToGithub` | Medium |
| 23 | Double-confirm destructive clear | `_sync.html` | `clearSecretsPrompt` | Low |
| 24 | 5-tab generator modal | `_keys.html` | `showAddKeysModal`, `switchGenTab`, `doAddKeys` | High |
| 25 | Template-based .env creation | `_keys.html` | `createEnvFromTemplate`, `doCreateFromTemplate` | Medium |
