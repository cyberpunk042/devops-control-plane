# Globals — Shared Frontend Foundation

> **7 files. 3,614 lines. The JavaScript layer every page depends on.**
>
> API client, caching, modals, card builders, tool install UI,
> authentication flows, and remediation handling — all loaded before
> any domain-specific script. The load order IS the dependency graph.

---

## How It Works

Every page in the admin panel is a single HTML file (`dashboard.html`)
that includes scripts via Jinja `{% include %}` directives. The globals
are the **first scripts loaded** (lines 36-42 in `dashboard.html`),
meaning every domain script — integrations, wizard, audit, content,
devops — can call global functions without import statements.

```
dashboard.html
│
├── Data injection (lines 30-33)
│   window._dcp        ← Python DataRegistry catalogs (tool list, etc.)
│   window.__INITIAL_STATE__  ← Pre-computed card data for zero-RTT paint
│
├── globals/ (lines 36-42) ← THIS PACKAGE — loaded first
│   ├── _api.html         ← fetch() wrapper + concurrency + toast + esc
│   ├── _cache.html       ← sessionStorage card/wizard cache + cascade
│   ├── _card_builders.html ← reusable HTML builder functions for cards
│   ├── _modal.html       ← generic modal system (open/close/forms/steps)
│   ├── _missing_tools.html ← missing tool banners + install buttons
│   ├── _ops_modal.html   ← SSE streaming + step modal + remediation + choices
│   └── _auth_modal.html  ← GitHub auth (device flow + terminal + token)
│
├── Domain scripts (lines 43-78) ← use globals freely
│   ├── _event_stream.html
│   ├── wizard/
│   ├── integrations/setup/
│   ├── assistant/
│   ├── secrets/
│   ├── content/
│   ├── devops/
│   ├── audit/
│   └── ...
│
└── _boot.html (line 79) ← last — initializes everything
```

### Load Order Contract

The files MUST be loaded in this order because each file depends on
functions defined in earlier files:

```
1. _api.html         ← standalone — defines api(), esc(), toast()
2. _cache.html       ← uses esc() from _api
3. _card_builders.html ← uses esc() from _api
4. _modal.html       ← uses esc() from _api
5. _missing_tools.html ← uses esc(), installWithPlan() (forward ref, resolved at call time)
6. _ops_modal.html   ← uses api(), apiPost(), toast(), esc(), modalOpen(), modalClose()
7. _auth_modal.html  ← uses api(), apiPost(), toast(), modalOpen(), installWithPlan()
```

The dependency flows **downward only** — `_api.html` never calls
functions from `_ops_modal.html`. Forward references (like
`_missing_tools.html` calling `installWithPlan()` from `_ops_modal.html`)
work because they're only invoked at runtime via onclick handlers,
not at parse time.

### Why These Were Extracted from `_globals.html`

The original `_globals.html` was a **3,606-line god file** containing
all 7 concerns in a single `<script>` block. It violated every
principle in the refactor plan:

- 7x over the 500-line limit
- 15+ distinct concerns in one file
- Any change risked breaking unrelated functionality
- AI tools couldn't navigate it reliably (post-mortem #13 context)

The split preserved every function signature, every comment, every
variable name. No logic was changed — pure file-boundary extraction.

---

## File Map

```
globals/
├── _api.html           HTTP client + utilities (92 lines)
├── _cache.html          Client-side caching system (222 lines)
├── _card_builders.html  Reusable card HTML builders (110 lines)
├── _modal.html          Generic modal framework (175 lines)
├── _missing_tools.html  Missing tool UI + install triggers (153 lines)
├── _ops_modal.html      Install/remediation/choice modals + SSE (2,045 lines)
├── _auth_modal.html     GitHub auth multi-path modal (817 lines)
└── README.md            This file
```

---

## `_api.html` — HTTP Client + Utilities (92 lines)

The foundation. Every other file uses `api()`, `esc()`, or `toast()`.

### Concurrency Control

The browser limits HTTP/1.1 to 6 TCP connections per origin. Without
throttling, the dashboard's 15+ parallel card fetches cause the browser
to silently queue excess requests. The AbortController timeout ticks
during that invisible wait, killing healthy requests that simply
hadn't gotten a connection slot.

Fix: a JavaScript-level semaphore (`_API_MAX_CONCURRENT = 3`) keeps
requests queued inside the JS runtime where the timeout hasn't started.
Slot 4-6 are left free for static assets, WebSocket, and other traffic.

```
fetch() call
    │
    ▼
_apiAcquire()  ← wait for a slot (max 3 in-flight)
    │
    ▼
Start AbortController timeout (30s default)
    │
    ▼
fetch('/api' + path, {...})
    │
    ▼
_apiRelease()  ← hand slot to next waiter or decrement counter
```

### Functions

| Function | What It Does |
|----------|-------------|
| `api(path, opts)` | `fetch('/api' + path)` with concurrency control, JSON parse, timeout, error handling |
| `apiPost(path, body)` | Convenience wrapper — `api()` with `method: 'POST'` and `JSON.stringify(body)` |
| `toast(message, type)` | Append a temporary notification to `#toast-container` (auto-removes after 6s) |
| `esc(str)` | HTML-escape a string via `textContent` → `innerHTML` trick (XSS prevention) |
| `showRefreshBar()` | Show the refresh indicator bar |
| `hideRefreshBar()` | Hide the refresh indicator bar |

### Internal State

| Variable | Type | Purpose |
|----------|------|---------|
| `_API_MAX_CONCURRENT` | `const(3)` | Max simultaneous fetch() calls |
| `_apiInFlight` | `let(0)` | Current number of active requests |
| `_apiQueue` | `Array` | Pending resolve callbacks waiting for a slot |

---

## `_cache.html` — Client-Side Caching System (222 lines)

Dual-namespace sessionStorage cache with cascade invalidation and
age tracking. Two parallel systems share the same pattern:

### Card Cache (dashboard cards)

Prefix: `_cc:` — TTL: 10 minutes

The server-side cache (`devops_cache.py`) handles real freshness via
mtime tracking. The client-side cache just avoids redundant network
requests when the user switches tabs. Manual refresh busts BOTH caches
(client + server via `?bust=1` query param).

| Function | What It Does |
|----------|-------------|
| `cardCached(key)` | Return cached data if < TTL, else null |
| `cardStore(key, data)` | Store data with timestamp |
| `cardInvalidate(key)` | Remove a single cache entry |
| `cardInvalidateAll(prefix)` | Remove all entries (optionally filtered by key prefix) |
| `cardAge(key)` | Age in seconds of a cached entry, or null |
| `cardRefresh(cacheKey, badgeId, detailId, loadFn)` | Bust client + server cache with cascade, show spinner, reload |
| `cardLoad(cacheKey, apiPath, badgeEl, detailEl)` | Check cache → fetch if stale → store → handle errors |

### Wizard Cache (wizard step data)

Prefix: `_wz:` — TTL: 10 minutes

Same pattern as card cache, separate namespace. Used by the setup
wizard to avoid re-fetching detection data when navigating between
steps. Supports server-side `computed_at` timestamps for sync.

| Function | What It Does |
|----------|-------------|
| `wizCached(key)` | Return cached wizard data if fresh, else null |
| `wizStore(key, data, epochMs)` | Store with server-side or explicit timestamp |
| `wizInvalidate(key)` | Remove a single wizard cache entry |
| `wizInvalidateAll(prefix)` | Remove all wizard entries |
| `wizAge(key)` | Age in seconds of a wizard cache entry |

### Cascade Invalidation

When a card is refreshed, dependent cards are automatically invalidated:

```
git  ──→  github, docker, ci, pages
docker ──→  ci, k8s
github ──→  ci
pages  ──→  dns
```

Example: refreshing the git card also invalidates github, docker, ci,
and pages caches. This prevents stale data when upstream state changes.

### Age Ticker

`_tickCardAges()` runs every 5 seconds via `setInterval`. It updates
all DOM elements with `data-card-age` attributes to show "Scanned Xs ago"
or "Scanned Xm ago", giving the user a sense of data freshness without
requiring a page refresh.

### File Navigation

`openFileInEditor(filePath, mode, line)` navigates to the Content Vault
and opens a file. Respects the user's preview mode preference: `modal`
opens a peek modal (no tab navigation), `tab` navigates to the Content
tab and opens the file there.

---

## `_card_builders.html` — Reusable HTML Builders (110 lines)

Pure functions that return HTML strings. No state, no side effects.
Every dashboard card uses these to build its sections consistently.

| Function | Parameters | What It Builds |
|----------|-----------|---------------|
| `cardStatusGrid(stats)` | `[{label, value, cls?}]` | Status grid with label-value pairs |
| `cardDetectionList(items)` | `[{icon, label, value?, click?}]` | Detection list with icons and optional click handlers |
| `cardDataTable(columns, rows)` | `string[]`, `[[{text, cls?, click?}]]` | Data table with headers and clickable cells |
| `cardActionToolbar(actions)` | `[{label, icon?, cls?, onclick, id?, disabled?}]` | Toolbar with action buttons |
| `cardEmpty(icon, text, action)` | `string`, `string`, `{label, onclick}?` | Empty state with icon, message, and optional CTA |
| `cardLivePanel(panelId, tabs, onTabClick)` | `string`, `[{key, label}]`, `string` | Tabbed live panel (for logs, stats, etc.) |
| `cardGenerateToolbar(items)` | `[{label, icon?, onclick}]` | Generate action toolbar |

All builders use `esc()` from `_api.html` for XSS prevention.
Click handlers are injected as `onclick` strings, not event listeners,
because the HTML is inserted via `innerHTML` after the DOM is built.

---

## `_modal.html` — Generic Modal Framework (175 lines)

The base modal system. All modals in the application (ops, auth, wizard,
remediation, choice) are built on top of this framework.

### Modal Lifecycle

```
modalOpen(opts)
    │
    ├── Close any existing modal (single-modal policy)
    ├── Create overlay with backdrop-filter
    ├── Build modal box (header + body + optional footer)
    ├── Register close-on-click-outside
    ├── Register close-on-Escape
    └── Store in _activeModal
    
modalClose()
    │
    ├── Remove overlay from DOM
    ├── Remove Escape listener
    ├── Call opts.onClose callback
    └── Clear _activeModal
```

### Functions

| Function | What It Does |
|----------|-------------|
| `modalOpen(opts)` | Open a modal with title, body, optional footer buttons and status |
| `modalClose()` | Close the active modal, run onClose callback |
| `modalSteps(stepNames, activeIndex)` | Build step indicator HTML (Step 1 → Step 2 → Step 3) |
| `modalFormField(f)` | Build a form field (text, select, textarea, checkbox, number) |
| `modalPreview(title, content, id)` | Build a preview panel (for generated configs, diffs) |
| `mfVal(name)` | Get a modal form field value by name (`#mf-{name}`) |
| `modalStatus(text, type)` | Set modal footer status text with color (error/success/muted) |
| `modalError(msg)` | Show/clear inline error message in modal body |

### Modal Options (`modalOpen`)

```javascript
modalOpen({
    title: '🔧 Install Tool',           // Can include emoji
    body: '<div>...</div>',              // innerHTML
    size: 'wide',                        // 'narrow' | 'wide' | undefined
    footerButtons: [{                    // Optional footer actions
        label: 'Install', cls: 'btn-primary',
        onclick: 'doInstall()', id: 'btn-install'
    }],
    footerStatus: 'Ready',              // Initial footer status text
    onClose: () => cleanup()            // Callback when closed
});
```

---

## `_missing_tools.html` — Missing Tool UI (153 lines)

Renders "X tools missing" banners with install and resume buttons.
Any dashboard card or modal can call `renderMissingTools()` to show
which tools are unavailable and offer one-click installation.

### Functions

| Function | What It Does |
|----------|-------------|
| `renderMissingTools(tools, containerId, onInstalled)` | Render banner into a DOM element, with resume buttons for interrupted plans |
| `renderMissingToolsInline(tools)` | Return banner HTML string (for use inside modals, no container needed) |
| `installToolFromBanner(btn, triggerRefresh)` | Handle install button click — delegates to `installWithPlan()` |
| `resumeToolFromBanner(btn)` | Handle resume button click — delegates to `resumeWithPlan()` |
| `_showSudoInstallModal(toolId, toolLabel, originBtn, triggerRefresh)` | Backward-compat wrapper used by 6+ integration templates |

### Pending Plan Detection

Before rendering, `renderMissingTools()` fetches pending (interrupted)
plans via `_fetchPendingPlans()`. If a tool has an interrupted plan,
the banner shows a "🔄 Resume (3/7)" button alongside the regular
"📦 Install" button. This prevents the user from starting a fresh
install when a partially-completed plan exists.

### Data Shape

Each tool in the `missingTools` array:

```javascript
{
    id: "terraform",           // Tool identifier (matches recipe)
    label: "Terraform",        // Display name
    install_type: "recipe",    // "recipe" | "system"
    has_recipe: true,          // Whether a recipe exists
    needs_sudo: false          // Whether install requires sudo
}
```

---

## `_ops_modal.html` — Operations Modal System (2,045 lines)

The largest file in globals. Handles three major UI flows:

1. **Tool installation** — plan-based step modal with SSE streaming
2. **Remediation** — failure analysis with multi-option fix paths
3. **Choice resolution** — interactive Q&A for ambiguous installs

This file also contains the SSE streaming client used by multiple
features beyond tool install (audit plan execution, resume plans).

### Architecture

```
installWithPlan(toolId, toolLabel, opts)          ← PUBLIC ENTRY POINT
    │
    ├── Fetch plan: POST /audit/install-plan
    │
    ├── Has choices? ──→ showChoiceModal()
    │                         │
    │                         ├── Render choice groups
    │                         ├── Collect answers
    │                         └── Re-fetch plan with answers ──→ loop
    │
    ├── Has dependencies? ──→ _showDepInstallModal()
    │                              │
    │                              ├── Install dep first
    │                              └── Chain back to original
    │
    └── Plan ready ──→ showStepModal(plan, opts)
                            │
                            ├── Render step list with risk badges
                            ├── Risk confirmation gate (medium/high)
                            └── _executeStepModalPlan()
                                    │
                                    ├── streamSSE(url, body, callbacks)
                                    │     │
                                    │     ├── POST with fetch()
                                    │     ├── ReadableStream line reader
                                    │     ├── Parse SSE events
                                    │     └── Dispatch to callbacks
                                    │
                                    ├── onStepStart → update row ⏳
                                    ├── onLog → append to log panel
                                    ├── onProgress → update progress bar
                                    ├── onStepDone → update row ✅
                                    ├── onStepFailed → update row ❌
                                    │     └── _showRemediationModal()
                                    │           ├── Render options
                                    │           ├── Check deps availability
                                    │           ├── Stream fix commands
                                    │           └── Chain retry
                                    └── onDone → restart detection
```

### SSE Streaming Client (`streamSSE`)

Generic SSE-over-POST client. Unlike browser-native `EventSource`
(GET-only), this uses `fetch()` with `ReadableStream` to read
server-sent events from POST endpoints.

```javascript
streamSSE('/api/audit/install-plan/execute', { plan_id, tool, ... }, {
    onLog(line)          // stdout/stderr line
    onStepStart(event)   // { index, label }
    onStepDone(event)    // { index, ok, skipped }
    onStepFailed(event)  // { index, error, stderr }
    onProgress(event)    // { index, percent }
    onDone(event)        // { ok, message, error, restart_type }
    onError(errorString) // Network or parse failure
});
```

Returns `Promise<{ok: boolean}>`.

### Step Modal (`showStepModal`)

Renders a visual step-by-step progress UI:

```
┌─────────────────────────────────────────────┐
│ 📦 Installing terraform                      │
├─────────────────────────────────────────────┤
│ ● Detect system profile          ✅  0.2s   │
│ ● Download binary                ⏳  ████░  │
│   ├── Downloading terraform v1.7.4...       │
│   └── 67% (42 MB / 63 MB)                  │
│ ○ Verify checksum                           │
│ ○ Install to /usr/local/bin                 │
├─────────────────────────────────────────────┤
│ Step 2 of 4                    [Cancel]     │
└─────────────────────────────────────────────┘
```

Features:
- Progress bars with percentage parsing from build/download logs
- Elapsed time per step
- Risk classification badges (low/medium/high)
- Confirmation gates for medium/high risk plans
- Restart detection (shell restart vs system restart)

### Remediation Modal (`_showRemediationModal`)

When a step fails, the backend returns remediation options. This modal
presents them as selectable paths with availability status:

```
┌──────────────────────────────────────────────────┐
│ ⚠️ Installation failed — 3 remediation options    │
├──────────────────────────────────────────────────┤
│ ❌ Error: externally managed environment          │
│                                                    │
│ ○ 🟢 Use virtual environment (recommended)        │
│     Create a venv and install there               │
│                                                    │
│ ○ 🟢 Switch to uv                                 │
│     Install uv, then retry with uv               │
│                                                    │
│ ○ 🔴 Break system packages                        │
│     --break-system-packages (critical risk)       │
│     ⚠️ Missing: python3-venv                      │
│                                                    │
├──────────────────────────────────────────────────┤
│                          [Cancel] [Apply Fix]     │
└──────────────────────────────────────────────────┘
```

The remediation modal handles:
- Option rendering with availability status (ready/locked/impossible)
- Missing system package detection and sub-modal install
- Streaming command execution via SSE
- Chained retries after fix application
- Sudo password prompting when needed

### Choice Modal (`showChoiceModal`)

When a tool's recipe has unresolved choices (e.g., "which version?"
or "install globally or locally?"), the planner returns choice data
instead of a ready plan. The choice modal collects user answers.

Supports input types: `select`, `radio`, `text`, `number`, `checkbox`.

### Resume Flow (`resumeWithPlan`)

Interrupted plans (machine reboot, Ctrl+C, network failure) are saved
to disk. `resumeWithPlan()` loads the saved state, shows completed
steps as pre-checked, and streams remaining steps via
`/audit/install-plan/resume`.

### Injected CSS

Both the step modal and choice modal inject their own CSS via
`_injectStepModalCSS()` and `_injectChoiceModalCSS()`. These are
self-contained IIFE blocks that check for existing style elements
before injecting. The CSS lives alongside the JS rather than in
`admin.css` because these modals are tightly coupled to their
rendering logic — the class names are generated in the same file.

---

## `_auth_modal.html` — Authentication Modal (817 lines)

Multi-path GitHub authentication: three strategies for different
deployment scenarios.

### Authentication Strategies

```
_showAuthModal(config)
    │
    ├── Path 1: 🌐 Browser (Device Flow)
    │     _opsAuthDeviceStart()
    │         │
    │         ├── POST /api/integrations/github/auth/device-start
    │         ├── Show one-time code + "Open GitHub" button
    │         ├── _opsDeviceStartPolling() — poll for completion
    │         └── On success → _opsAuthSuccess()
    │
    ├── Path 2: 🖥️ Terminal (Interactive)
    │     _opsAuthSpawnTerminal()
    │         │
    │         ├── POST /api/integrations/github/auth/terminal
    │         ├── If no terminal → _opsShowTerminalInstall()
    │         │     ├── Offer terminal emulator install
    │         │     └── _opsInstallTerminal() → retry
    │         ├── _opsTerminalSignalPoll() — poll signal file
    │         │     ├── code_ready → show code in modal
    │         │     └── success → _opsAuthSuccess()
    │         └── Fallback: _opsShowCopyFallback()
    │
    └── Path 3: 🔑 Token (Paste)
          _opsAuthWithToken()
              │
              ├── Read token from modal input
              ├── POST /api/integrations/github/auth/token
              └── On success → _opsAuthSuccess()
```

### Device Flow — The Sophisticated Path

The device flow is the most complex auth strategy. It automates
GitHub's OAuth device authorization grant:

1. Backend spawns `gh auth login` in a PTY
2. PTY auto-answers interactive prompts
3. Backend extracts one-time code and verification URL from PTY output
4. Frontend shows code + "Open GitHub" link
5. User enters code in their browser on github.com
6. Frontend polls backend for completion
7. Backend detects PTY success, returns auth token

This works without any terminal window, making it ideal for
remote/headless deployments.

### Terminal Signal Polling

When using the terminal path, the spawned `gh` process writes
status updates to a signal file. The frontend polls this file via
`_opsTerminalSignalPoll()`:

| Signal | Meaning |
|--------|---------|
| `code_ready` | Device code extracted — show in modal |
| `success` | Authentication completed |
| `failed` | Authentication failed |
| `timeout` | Process timed out |

Poll interval: 2 seconds. Max attempts: 150 (5 minutes).

### Auth Success Handler

`_opsAuthSuccess(cfg)` handles post-authentication:
1. Close the auth modal
2. Bust relevant caches (`github`, `git`, `ci`)
3. Call `cfg.onSuccess` callback
4. Show toast notification

### Convenience Helpers

| Function | What It Does |
|----------|-------------|
| `_showGhAuthModal(onSuccess)` | Open GitHub auth modal with default config |
| `_refreshAfterInstall()` | Bust caches and reload active tab (no full page reload) |

### `_refreshAfterInstall()` — Cache Bust + Tab Reload

After a tool install or auth success, the UI needs to reflect the
new state. Instead of a full page reload (which loses scroll position,
tab state, and open modals), this function:

1. Invalidates all client-side caches (`cardInvalidateAll()`)
2. Determines the currently active tab
3. Calls that tab's load function to re-render with fresh data

This preserves the SPA feel — the user stays on their tab, the data
refreshes, and the UI updates in-place.

---

## Dependency Graph

```
_api.html                    ← standalone (no dependencies)
    ↑
_cache.html                  ← uses esc() from _api
    ↑
_card_builders.html          ← uses esc() from _api
    ↑
_modal.html                  ← uses esc() from _api
    ↑
_missing_tools.html          ← uses esc() from _api
    │                           uses installWithPlan() from _ops_modal (runtime only)
    ↑
_ops_modal.html              ← uses api(), apiPost(), toast(), esc() from _api
    │                           uses modalOpen(), modalClose() from _modal
    ↑
_auth_modal.html             ← uses api(), apiPost(), toast() from _api
                                uses modalOpen(), modalClose() from _modal
                                uses installWithPlan() from _ops_modal
                                uses cardInvalidateAll() from _cache
```

Key: `↑` means "loaded after" (later in dashboard.html include order).
All runtime dependencies flow upward — earlier files never call
functions from later files at parse time.

---

## Consumers

Every domain script in `dashboard.html` (lines 43-78) is a consumer
of globals. The most heavily used functions:

| Function | Consumers |
|----------|----------|
| `api()`, `apiPost()` | Every domain script — ALL API calls go through this |
| `esc()` | Every domain script — XSS prevention in HTML builders |
| `toast()` | Integrations, audit, wizard, content, secrets, devops |
| `cardCached()`, `cardStore()`, `cardLoad()` | Dashboard cards: docker, k8s, git, ci, pages, terraform, etc. |
| `cardRefresh()` | Dashboard refresh buttons on every card |
| `wizCached()`, `wizStore()` | Wizard detection steps, sub-wizard data sharing |
| `modalOpen()`, `modalClose()` | Wizard modals, integration setup, content preview, config editor |
| `cardStatusGrid()`, `cardDetectionList()` | Every dashboard card |
| `cardDataTable()`, `cardLivePanel()` | Docker, K8s, CI, security live panels |
| `installWithPlan()` | Audit tab, missing tool banners, integration setup |
| `_showGhAuthModal()` | Git auth tab, integrations (GitHub setup), chat sync |
| `renderMissingTools()` | Docker card, K8s card, CI card, security card, quality card |
| `streamSSE()` | Audit plan execution, tool remediation, resume plans |

---

## Advanced Feature Showcase

### 1. API Concurrency Semaphore

HTTP/1.1 browsers cap at 6 TCP connections per origin. Without throttling,
15+ parallel `fetch()` calls queue invisibly and the `AbortController` timeout
ticks during that invisible wait — killing healthy requests that just hadn't
gotten a connection slot yet.

The fix is a JS-level semaphore that queues at the application level, where
the timeout hasn't started yet:

```javascript
// _api.html — lines 17-35
const _API_MAX_CONCURRENT = 3;
let _apiInFlight = 0;
const _apiQueue = [];

function _apiAcquire() {
    if (_apiInFlight < _API_MAX_CONCURRENT) {
        _apiInFlight++;
        return Promise.resolve();
    }
    return new Promise(resolve => _apiQueue.push(resolve));
}

function _apiRelease() {
    if (_apiQueue.length > 0) {
        _apiQueue.shift()();   // hand slot to next waiter
    } else {
        _apiInFlight--;
    }
}

// Usage in api(): acquire BEFORE starting the timeout
async function api(path, opts = {}) {
    await _apiAcquire();
    const controller = new AbortController();
    const ms = opts.timeout || 30000;
    const timer = setTimeout(() => controller.abort(), ms);
    try { /* ... fetch ... */ }
    finally { clearTimeout(timer); _apiRelease(); }
}
```

Slot 6 is left free for static assets / WebSocket / SSE traffic. Max is 3
to avoid starving concurrent SSE streams from the install system.

### 2. Cascade Invalidation with Declared Dependency Map

Dashboard cards have real data dependencies — pushing code makes the CI card
stale, a Docker rebuild makes the K8s card stale. The cache declares these
relationships as a static map and propagates invalidation transitively:

```javascript
// _cache.html — lines 146-168
const _CASCADE = {
    'git':    ['github', 'docker', 'ci', 'pages'],
    'docker': ['ci', 'k8s'],
    'github': ['ci'],
    'pages':  ['dns'],
};

async function cardRefresh(cacheKey, badgeId, detailId, loadFn) {
    // Bust client cache: primary + cascade + aggregates
    cardInvalidate(cacheKey);
    for (const dep of _CASCADE[cacheKey] || []) cardInvalidate(dep);
    cardInvalidate('project-status');
    cardInvalidate('health-score');
    // Clear in-memory SSE store so loadFn doesn't short-circuit
    if (typeof _store !== 'undefined') {
        delete _store[cacheKey];
        for (const dep of _CASCADE[cacheKey] || []) delete _store[dep];
    }
    // Bust server-side cache (server also cascades)
    try { await api('/devops/cache/bust', { method: 'POST', /* ... */ }); } catch { }
    // Then reload
    await loadFn();
}
```

A single `cardRefresh('git', ...)` invalidates 5 client caches, busts
the server-side cache, clears the in-memory SSE store, and triggers a fresh
load — all in one call.

### 3. Dual-Tier Cache Timestamps (Server `computed_at` vs Client `Date.now()`)

The card cache stores a `ts` field for TTL checks, but prefers the server's
`_cache.computed_at` epoch over the client's `Date.now()` when computing age.
This prevents client clock skew from making fresh data appear stale:

```javascript
// _cache.html — lines 48-59
function cardAge(key) {
    try {
        const raw = sessionStorage.getItem(_CARD_PREFIX + key);
        if (!raw) return null;
        const c = JSON.parse(raw);
        // Use server-side computed_at if available (more accurate)
        if (c.data?._cache?.computed_at) {
            return Math.round(Date.now() / 1000 - c.data._cache.computed_at);
        }
        return Math.round((Date.now() - c.ts) / 1000);
    } catch { return null; }
}
```

The wizard cache (`wizStore`) uses the same pattern — passing
`serverAt * 1000` as the timestamp source when available (line 93).

### 4. SSE Streaming with Typed Event Dispatch

The `streamSSE()` function implements a full SSE client over `ReadableStream`,
parsing `data: ` lines and dispatching typed events through a callback map:

```javascript
// _ops_modal.html — lines 899-975
async function streamSSE(url, body, callbacks) {
    var resp = await fetch(url, { method: 'POST', /* ... */ });
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';

    while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });
        var lines = buffer.split('\n');
        buffer = lines.pop() || '';   // keep partial line in buffer

        for (var li = 0; li < lines.length; li++) {
            var ln = lines[li];
            if (!ln.startsWith('data: ')) continue;
            var event = JSON.parse(ln.slice(6));
            switch (event.type) {
                case 'log':        callbacks.onLog?.(event.line);     break;
                case 'step_start': callbacks.onStepStart?.(event);   break;
                case 'step_done':  callbacks.onStepDone?.(event);    break;
                case 'step_failed':callbacks.onStepFailed?.(event);  break;
                case 'progress':   callbacks.onProgress?.(event);    break;
                case 'done':       callbacks.onDone?.(event);
                                   return { ok: !!event.ok };
                case 'error':      callbacks.onError?.(event.error);
                                   return { ok: false };
            }
        }
    }
}
```

Key detail: the buffer accumulates partial chunks and only processes
complete `\n`-terminated lines. This handles TCP fragmentation where an
SSE event spans multiple `reader.read()` calls.

### 5. Strategy-Based Remediation Dispatch

When a tool install fails, the backend returns a `remediation` object with
typed options. The frontend dispatches each via a strategy pattern with
7 distinct strategies:

```javascript
// _ops_modal.html — lines 582-682
var strategy = opt.strategy || '';

if (strategy === 'retry_with_modifier') {
    // Re-run with sudo or environment changes
    _showInstallModal({ toolId, toolLabel, needsSudo: true, answers: modifier });
}
if (strategy === 'switch_method') {
    // Re-install using a different install method
    _showInstallModal({ toolId, toolLabel, answers: { method: opt.method } });
}
if (strategy === 'install_dep' || strategy === 'install_dep_then_switch') {
    // Install a missing dependency first, then chain-install original
    _showDepInstallModal(toolId, toolLabel, { tool: depTool, label: opt.label });
}
if (strategy === 'manual') {
    // Show read-only instructions (no command execution)
}
if (strategy === 'env_fix' || strategy === 'cleanup_retry') {
    // Execute fix/cleanup commands via SSE stream, then retry
    var fixResult = await streamCommand(fixCmds, opt.label, opt.needs_sudo);
    if (fixResult.ok && strategy === 'cleanup_retry') {
        _showInstallModal({ toolId, toolLabel });  // auto-retry after cleanup
    }
}
// Legacy fallback: opt.steps (multi-step), opt.command (single), opt.retry_sudo
```

The `_showRemediationModal` function (700 lines) also renders per-option
sudo password fields, selectable paths with risk indicators, and a
streaming log output area.

### 6. Tiered Confirmation Gates

High-risk install plans require user confirmation before execution. The
gate level comes from the backend plan and controls the UI:

```javascript
// _ops_modal.html — lines 1041-1067
var gate = plan.confirmation_gate;
if (gate && gate.required) {
    if (gate.level === 'double') {
        // 🔴 High-risk: user must type "I understand"
        gateHtml = '<div class="confirm-gate gate-double">' +
            '<input type="text" id="step-modal-confirm" ' +
            'placeholder=\'Type "I understand" to proceed\' ' +
            'oninput="document.getElementById(\'step-modal-go\').disabled' +
            ' = this.value !== \'I understand\'" />';
    } else {
        // ⚠️ Medium-risk: single checkbox
        gateHtml = '<div class="confirm-gate gate-single">' +
            '<label><input type="checkbox" id="step-modal-confirm" ' +
            'onchange="document.getElementById(\'step-modal-go\').disabled' +
            ' = !this.checked" />' +
            '⚠️ I confirm this plan modifies system components</label>';
    }
}
```

The gate also lists high-risk steps from `gate.high_risk_steps` so the
user sees exactly which operations require elevated privilege.

### 7. Multi-Path Authentication with Auto-Drive Terminal

The auth modal offers 3 authentication paths from a single configurable
entry point. The most complex is the terminal path with auto-drive:

```javascript
// _auth_modal.html — lines 285-325
async function _opsAuthSpawnTerminal() {
    // Check auto-drive checkbox
    const autoDrive = document.getElementById('ops-term-auto')?.checked ?? false;
    const res = await apiPost(cfg.loginEndpoint, { mode: 'interactive', auto_drive: autoDrive });

    if (res.ok && res.terminal) {
        if (autoDrive) {
            // Auto-drive: poll signal file for code + URL
            _opsTerminalSignalPoll(cfg, statusEl);
        } else {
            // Manual: just poll gh auth status
            _opsAuthStartPolling(cfg, statusEl);
        }
    } else if (res.no_terminal) {
        // No working terminal — show install options with radio selection
        _opsShowTerminalInstall(res, cfg);
    } else if (res.fallback && res.command) {
        // No terminal at all — show command to copy
        _opsShowCopyFallback(res, statusEl, btn);
    }
}
```

The browser device flow (`_opsAuthDeviceStart`) uses a critical ordering
trick: it starts polling FIRST, then copies the code to clipboard
(fire-and-forget, no await), then opens the GitHub URL LAST — because
`window.open()` steals focus and makes the clipboard API hang if the
document isn't focused (lines 197-221).

### 8. Chained Dependency Install with Modal Stacking

When a tool requires a dependency that isn't installed, the system chains
installs: dependency first, then the original tool automatically:

```javascript
// _ops_modal.html — lines 753-821
function _showDepInstallModal(toolId, toolLabel, dep, onSuccess) {
    modalOpen({
        title: '📦 Dependency Required',
        body: toolLabel + ' requires ' + depLabel + '. Install it first.',
        footerButtons: [{
            label: '📦 Install ' + depLabel,
            onclick: '_doDepChainInstall()',
        }],
    });

    window._doDepChainInstall = async function() {
        var depResult = await fetch('/api/audit/install-tool', { /* ... */ });
        if (depResult.ok) {
            toast(depLabel + ' installed! Now installing ' + toolLabel + '…');
            modalClose();
            installWithPlan(toolId, toolLabel, { onComplete: onSuccess });
        } else if (depResult.needs_sudo) {
            // Chain through sudo modal → then install original tool
            _showInstallModal({
                toolId: depTool,
                toolLabel: depLabel,
                onSuccess: function() {
                    installWithPlan(toolId, toolLabel, { onComplete: onSuccess });
                },
            });
        }
    };
}
```

This creates a modal stack: dependency modal → sudo modal (if needed) →
step modal for original tool. Each modal chains to the next via the
`onSuccess` callback.

---

### Feature Coverage Summary

| Feature | File | Key Functions | Complexity |
|---------|------|--------------|------------|
| API concurrency semaphore | `_api.html` | `_apiAcquire()`, `_apiRelease()`, `api()` | Connection slot management |
| Client-side card cache (10m TTL) | `_cache.html` | `cardCached()`, `cardStore()`, `cardAge()` | sessionStorage with `_cache.computed_at` |
| Wizard cache (separate namespace) | `_cache.html` | `wizCached()`, `wizStore()`, `wizAge()` | Same pattern, `_wz:` prefix |
| Cascade invalidation | `_cache.html` | `cardRefresh()`, `_CASCADE` map | Transitive dependency tracking |
| Live age ticking | `_cache.html` | `_tickCardAges()`, `_formatAge()` | 5s interval, per-card `[data-cache-key]` |
| Card HTML builders (7 types) | `_card_builders.html` | `cardStatusGrid()`, `cardDataTable()`, etc. | Declarative table/grid/panel generation |
| Generic modal system | `_modal.html` | `modalOpen()`, `modalClose()`, `modalSteps()` | Escape/overlay close, step indicators |
| Modal form fields (5 types) | `_modal.html` | `modalFormField()`, `mfVal()` | text/select/textarea/checkbox/number |
| Missing tool banners | `_missing_tools.html` | `renderMissingTools()`, `installToolFromBanner()` | Pending plan detection + resume buttons |
| SSE streaming client | `_ops_modal.html` | `streamSSE()` | ReadableStream + buffer management |
| Step-by-step install modal | `_ops_modal.html` | `showStepModal()`, `_executeStepModalPlan()` | Progress bars, risk badges, elapsed times |
| Remediation dispatch (7 strategies) | `_ops_modal.html` | `_showRemediationModal()`, `_remExecute()` | Strategy pattern + streaming execution |
| Tiered confirmation gates | `_ops_modal.html` | `showStepModal()` gate rendering | Checkbox (medium) vs. type-to-confirm (high) |
| Chained dependency installs | `_ops_modal.html` | `_showDepInstallModal()` | Modal stacking with callback chaining |
| Choice modal (user-selectable install) | `_ops_modal.html` | `showChoiceModal()`, `_renderChoice()` | Multi-option selection with risk metadata |
| Plan resume (paused/failed) | `_ops_modal.html` | `resumeWithPlan()`, `_executeResumePlan()` | UUID-based plan recovery |
| Multi-path GitHub auth | `_auth_modal.html` | `_showAuthModal()`, `_opsAuthDeviceStart()` | Browser + terminal + token paths |
| Terminal auto-drive | `_auth_modal.html` | `_opsAuthSpawnTerminal()`, `_opsTerminalSignalPoll()` | Signal file polling, auto-select options |
| Post-auth cache bust | `_auth_modal.html` | `_opsAuthSuccess()`, `_refreshAfterInstall()` | Selective cache invalidation per domain |

---

## Design Decisions

### Why global functions instead of modules?

The admin panel is a **template-injected SPA** — Jinja includes
concatenate `<script>` blocks into one HTML page. There's no webpack,
no bundler, no ES modules. Global functions are the natural pattern
for this architecture. Every function is called by name from onclick
handlers, inline scripts, and other template includes.

### Why is `_ops_modal.html` so large (2,045 lines)?

It contains three tightly coupled flows (install → remediation → retry)
that share state and call each other recursively. Splitting them would
create circular dependencies or require a shared state module. The
file's internal organization uses clear section headers and follows
a top-down call hierarchy.

The remediation modal alone (`_showRemediationModal`) is 700 lines
because it handles 11 different remediation strategies with streaming
command execution, dependency checks, and chained retries. Each
strategy has different UI requirements.

### Why inject CSS from JavaScript?

The step modal and choice modal CSS is injected by their rendering
code rather than living in `admin.css`. This keeps the CSS co-located
with the HTML templates it styles — the class names exist only in this
file. If the modal rendering changes, the CSS changes in the same file.
The alternative (putting 80+ CSS rules in `admin.css` with no obvious
connection to their JS) would make maintenance harder.

### Why sessionStorage for caching instead of a JS Map?

sessionStorage survives tab refresh but not tab close. This matches
the desired behavior: switching tabs within a session reuses cached
data (fast navigation), but a fresh tab always starts with fresh data
(no stale surprises). A JS Map would lose everything on F5.

### Why cascade invalidation?

The dashboard cards have real dependency relationships. When the user
pushes code (git card refreshes), the CI card's data is now stale
(new workflows may have triggered), the Docker card's data may be
stale (Dockerfile changed), the GitHub card's data is stale (new
commits). Without cascade, the user would see inconsistent data
across cards until they manually refresh each one.
