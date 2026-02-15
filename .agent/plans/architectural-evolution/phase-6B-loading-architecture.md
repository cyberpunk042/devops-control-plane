# Phase 6B: Loading Architecture Overhaul

**Status:** Ready to implement  
**Parent:** Phase 6 — Caching Architecture  
**Priority:** 🔴 Critical — causes K8s/Terraform/DNS cards to hang, integrations to re-fetch, and overall 6-10s page load times  
**Date:** 2026-02-15

---

## 1. Root Cause Analysis

The app has a **cascading failure** pattern caused by compounding issues.

### 1.1 The False Premise

Both tab loaders (`_devops_init.html` line 87, `_integrations_init.html` line 164) contain this comment:

```js
// Load auto cards sequentially (Flask dev server is single-threaded)
```

**This is WRONG.** `server.py` line 138:

```python
app.run(host=host, port=port, debug=debug, use_reloader=False, threaded=True)
```

The server is **already multi-threaded** (`threaded=True`). Every request gets its own thread. The sequential `for...await` loading is an artificial bottleneck — there is no reason for it.

### 1.2 Sequential card loading

Because of the false premise, both tabs use `for...await` loops that serialize ALL card loads:

```
DevOps tab:  security → testing → quality → packages → env → docs → K8s → TF → DNS
                                                                      ↑
                                                                   NEVER REACHED
                                                                   if env hangs
```

- **DevOps tab** (`_devops_init.html` line 88-93): sequential, **NO try/catch** — if any card throws, the loop dies and all subsequent cards (K8s, TF, DNS) never load.
- **Integrations tab** (`_integrations_init.html` line 164-178): sequential, has try/catch — but still unnecessarily serial.

### 1.3 Uncached subprocess endpoints

These endpoints call `gh`/`git` CLI subprocesses with **zero caching** (server or client):

| Endpoint | What it calls | Est. time |
|---|---|---|
| `/gh/pulls` | `gh pr list` | ~2-3s |
| `/gh/actions/runs` | `gh run list --json` | ~2s |
| `/gh/actions/workflows` | `gh workflow list` | ~1s |
| `/gh/user` | `gh api user` | ~1s |
| `/gh/repo/info` | `gh repo view` | ~1s |
| `/git/log` | `git log` | ~0.3s |
| `/git/remotes` | `git remote -v` | ~0.1s |
| `/metrics/summary` | computation | ~1s |

### 1.4 GitHub card auto-fires uncached calls on every render

`_integrations_github.html` line 89-92:
```js
setTimeout(() => { firstTab.click(); }, 50);
// → _ghLiveTab('prs') → api('/gh/pulls') — NO CACHE, 2-3s subprocess
```

Even when the GitHub card itself renders from client cache in 0ms, it immediately fires an uncached `gh pr list` subprocess call.

### 1.5 CI card double-fetch

`_integrations_cicd.html` line 13-14:
```js
let ciStatus = null;
try { ciStatus = await api('/ci/status'); } catch (_) {}  // ← ALWAYS fires

const cached = cardCached('ci');
const data = cached || await api('/gh/actions/runs?n=5');  // ← only this is cached
```

`/ci/status` fires outside the cache check — every render, regardless of cache.

### 1.6 Cache module is NOT thread-safe

With `threaded=True`, concurrent requests can hit `get_cached()` simultaneously. `devops_cache.py` has **no locking**:

```python
def get_cached(root, key, compute_fn, force=False):
    cache = _load_cache(root)          # Thread A reads file
                                        # Thread B reads SAME file
    if miss:
        data = compute_fn()             # Both threads run subprocess
        cache[key] = {...}
        _save_cache(root, cache)        # Thread A writes
                                        # Thread B writes → overwrites A's entry!
```

**Consequences:**
1. Duplicate subprocess work (both threads compute the same probe)
2. Lost updates (thread B's `_save_cache` overwrites thread A's entry because it loaded a stale snapshot)

### 1.7 Boot fires too many requests

`_boot.html` line 32-39:
```js
await Promise.all([
    loadStatus(),         // → /api/status
    loadCapabilities(),   // → /api/capabilities
    loadHealth(),         // → /api/health
    loadAudit(),          // → /api/audit?n=10
    loadHealthScore(),    // → /api/metrics/health  ← 7 sequential probes
    loadSetupProgress(),  // → /api/project/status  ← 8 integration probes
]);
```

On cold cache, this launches 6+ requests that collectively spawn 15+ subprocesses. Even with threading, this is a thundering herd on startup.

---

## 2. Fix Plan

### Step 0: Thread-safe cache (prerequisite for everything)

**File:** `src/core/services/devops_cache.py`

**What:** Add a per-key lock to `get_cached()` so concurrent requests don't duplicate work or corrupt the cache file.

```python
import threading

# One lock per cache key — prevents duplicate computation
_key_locks: dict[str, threading.Lock] = {}
_key_locks_guard = threading.Lock()

# Global file lock — prevents concurrent JSON file writes
_file_lock = threading.Lock()


def _get_key_lock(key: str) -> threading.Lock:
    """Get or create a lock for a specific cache key."""
    with _key_locks_guard:
        if key not in _key_locks:
            _key_locks[key] = threading.Lock()
        return _key_locks[key]
```

Then in `get_cached()`:

```python
def get_cached(project_root, card_key, compute_fn, force=False):
    lock = _get_key_lock(card_key)
    with lock:
        cache = _load_cache(project_root)
        entry = cache.get(card_key)
        # ... existing mtime check, return if hit ...

        # Recompute (only one thread does this per key)
        data = compute_fn()

        # Save with file lock to prevent write corruption
        with _file_lock:
            cache = _load_cache(project_root)  # re-read to not lose other keys
            cache[card_key] = {
                "data": data,
                "cached_at": time.time(),
                "mtime": current_mtime,
                "elapsed_s": elapsed,
            }
            _save_cache(project_root, cache)

    return data
```

**Key design decisions:**
- **Per-key lock:** Two different cards (e.g., `docker` and `k8s`) can compute in parallel — they don't share a lock.
- **Same-key lock:** Two requests for the same card — the second waits for the first to finish, then gets the cached result.
- **File lock on write:** Re-reads the file before writing to avoid losing other keys that were computed concurrently by a different key's thread.

**Risk:** Low — this is a defensive mechanism that only changes timing, not data.

### Step 1: Parallel card loading with error resilience

**Files:**
- `src/ui/web/templates/scripts/_devops_init.html`
- `src/ui/web/templates/scripts/_integrations_init.html`

**What:** Replace `for...await` with `Promise.allSettled()`. Since the server is multi-threaded, there's no reason to serialize. All cards load concurrently and render as they arrive.

**DevOps tab — `_devops_init.html` (line 87-93):**

Before:
```js
// Load auto cards sequentially (Flask dev server is single-threaded)
for (const [key, meta] of Object.entries(_DEVOPS_CARDS)) {
    const pref = prefs[key] || 'auto';
    if (pref === 'auto') {
        await meta.loadFn();
    }
}
```

After:
```js
// Load auto cards in parallel (server is threaded — concurrent requests are fine)
const autoCards = Object.entries(_DEVOPS_CARDS)
    .filter(([key]) => (prefs[key] || 'auto') === 'auto');

await Promise.allSettled(autoCards.map(async ([key, meta]) => {
    try {
        await meta.loadFn();
    } catch (e) {
        console.error(`[DEVOPS] ${key}:`, e);
        const b = document.getElementById('devops-' + key + '-badge');
        const d = document.getElementById('devops-' + key + '-detail');
        if (b) { b.className = 'status-badge failed'; b.innerHTML = '<span class="status-dot"></span>Error'; }
        if (d) d.innerHTML = `<p class="empty-state-sm" style="color:var(--error)">${esc(e.message || 'Load failed')}</p>`;
    }
}));
```

**Integrations tab — `_integrations_init.html` (line 164-178):**

Same transformation — replace sequential `for...await` with `Promise.allSettled()`. The existing `try/catch` error rendering for each card is preserved.

### Step 2: Server-side cache for GitHub live-tab endpoints

**Files:**
- `src/ui/web/routes_integrations.py`
- `src/core/services/devops_cache.py`

**What:** Wrap the 3 high-impact GitHub endpoints in `get_cached()`:

```python
# /gh/pulls — currently line 133-136
@integrations_bp.route("/gh/pulls")
def gh_pulls():
    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "gh-pulls",
        lambda: git_ops.gh_pulls(root),
        force=force,
    ))

# /gh/actions/runs — currently line 142-146
@integrations_bp.route("/gh/actions/runs")
def gh_actions_runs():
    root = _project_root()
    n = request.args.get("n", 10, type=int)
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "gh-runs",
        lambda: git_ops.gh_actions_runs(root, n=n),
        force=force,
    ))

# /gh/actions/workflows — currently line 168-171
@integrations_bp.route("/gh/actions/workflows")
def gh_actions_workflows():
    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "gh-workflows",
        lambda: git_ops.gh_actions_workflows(root),
        force=force,
    ))
```

**Watch paths in `devops_cache.py`:**

```python
# GitHub API data — changes independently of local files.
# Watch paths are a proxy: cache busts on push (HEAD changes) or workflow edits.
# For truly fresh data, user clicks 🔄 which sends ?bust=1.
"gh-pulls":     [".git/HEAD", ".git/refs/"],
"gh-runs":      [".github/workflows/", ".git/HEAD"],
"gh-workflows": [".github/workflows/"],
```

### Step 3: Client-side cache for GitHub live tabs

**File:** `src/ui/web/templates/scripts/_integrations_github.html`

**What:** Add `cardCached`/`cardStore` to `_ghLiveTab()` using sub-keys like `gh-live:prs`, `gh-live:runs`:

```js
async function _ghLiveTab(what, panelId) {
    const panel = document.getElementById(panelId);
    if (!panel) return;

    const liveKey = 'gh-live:' + what;
    const cached = cardCached(liveKey);

    if (!cached) {
        panel.innerHTML = '<span class="spinner"></span> Loading…';
    }

    try {
        if (what === 'prs') {
            const data = cached || await api('/gh/pulls');
            if (!cached) cardStore(liveKey, data);
            // ... render PRs (existing render code unchanged) ...
        } else if (what === 'runs') {
            const data = cached || await api('/gh/actions/runs?n=10');
            if (!cached) cardStore(liveKey, data);
            // ... render runs (existing render code unchanged) ...
        }
        // ... envs, secrets remain as-is (they use different patterns)
    } catch (e) { ... }
}
```

**Also: Always auto-open the first live tab** (keep existing behavior), but it renders from cache instantly instead of making an API call. No need to suppress the auto-click — it's the caching that matters.

### Step 4: Fix CI card double-fetch

**File:** `src/ui/web/templates/scripts/_integrations_cicd.html`

**What:** Move the `/ci/status` call inside the cache check and use `Promise.all` to parallelize both calls on cold cache:

Before:
```js
let ciStatus = null;
try { ciStatus = await api('/ci/status'); } catch (_) {}

const cached = cardCached('ci');
const data = cached || await api('/gh/actions/runs?n=5');
if (!cached) cardStore('ci', data);
```

After:
```js
const cached = cardCached('ci');
let ciStatus, data;
if (cached) {
    ciStatus = cached._ciStatus || null;
    data = cached;
} else {
    // Parallel fetch — both calls run concurrently (server is threaded)
    const [ciRes, runsRes] = await Promise.all([
        api('/ci/status').catch(() => null),
        api('/gh/actions/runs?n=5').catch(() => ({ available: false })),
    ]);
    ciStatus = ciRes;
    data = runsRes;
    // Stash ciStatus inside the data for cache
    data._ciStatus = ciStatus;
    cardStore('ci', data);
}
```

### Step 5: Prioritized boot sequence

**File:** `src/ui/web/templates/scripts/_boot.html`

**What:** Split boot into **critical** (needed for visible dashboard) and **deferred** (background preloads):

Before:
```js
await Promise.all([
    loadStatus(),
    loadCapabilities(),
    loadHealth(),
    loadAudit(),
    loadHealthScore(),
    loadSetupProgress(),
]);
```

After:
```js
// Critical path — needed for visible dashboard, fires first
await Promise.all([
    loadStatus(),
    loadHealth(),
]);

// Deferred — load after critical UI is painted
// These are allowed to take longer without blocking the UI
Promise.allSettled([
    loadCapabilities(),
    loadAudit(),
    loadHealthScore(),     // heavy: 7 probes
    loadSetupProgress(),   // heavy: 8 probes
]);
```

**Why not `await` the deferred block?** Because we don't need to wait for health score and setup progress before the user can interact. They'll render when they arrive. If the user switches to another tab before they finish, the tab load isn't blocked.

### Step 6: Timeout protection on API calls

**File:** `src/ui/web/templates/scripts/_globals.html`

**What:** Add `AbortController` + timeout to the `api()` helper:

```js
async function api(path, opts = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), opts.timeout || 15000);
    try {
        const resp = await fetch('/api' + path, {
            ...opts,
            signal: controller.signal,
        });
        // ... existing response handling ...
    } finally {
        clearTimeout(timeout);
    }
}
```

This ensures that if any endpoint hangs, the client aborts after 15 seconds. Cards show an error state, user can retry via 🔄.

---

## 3. Impact Matrix

| Step | Change | Files | Risk | Impact |
|---|---|---|---|---|
| 0 | Thread-safe cache | 1 .py | Low | Foundation: prevents duplicate work + data loss |
| 1 | Parallel card loading | 2 .html | Low | K8s/TF/DNS no longer blocked; all cards load concurrently |
| 2 | Server cache GH endpoints | 2 files | Low | 3-5s saved per integrations load |
| 3 | Client cache GH live tabs | 1 .html | Low | PRs/runs instant on tab switch |
| 4 | Fix CI double-fetch | 1 .html | Medium | CI card 2x faster, no wasted `/ci/status` call |
| 5 | Prioritized boot | 1 .html | Medium | Dashboard renders in <1s |
| 6 | API timeout | 1 .html | Low | Safety net against infinite hangs |

## 4. Execution Order

1. **Step 0** — thread-safe cache (prerequisite: must go first)
2. **Step 6** — timeout protection (safety net before changing load patterns)
3. **Step 1** — parallel card loading (the biggest fix — unblocks K8s/TF/DNS)
4. **Step 5** — prioritized boot (dashboard instant)
5. **Step 2** — server cache for GH endpoints
6. **Step 3** — client cache for GH live tabs
7. **Step 4** — fix CI double-fetch

## 5. Files Modified

| File | Steps |
|---|---|
| `src/core/services/devops_cache.py` | 0 (thread safety), 2 (watch paths) |
| `src/ui/web/templates/scripts/_globals.html` | 6 (API timeout) |
| `src/ui/web/templates/scripts/_boot.html` | 5 (prioritized boot) |
| `src/ui/web/templates/scripts/_devops_init.html` | 1 (parallel loading) |
| `src/ui/web/templates/scripts/_integrations_init.html` | 1 (parallel loading) |
| `src/ui/web/templates/scripts/_integrations_github.html` | 3 (live tab caching) |
| `src/ui/web/templates/scripts/_integrations_cicd.html` | 4 (fix double-fetch) |
| `src/ui/web/routes_integrations.py` | 2 (server cache) |

## 6. Verification

After all steps:

1. **Cold boot:** Dashboard renders in <1s. Health score + setup progress load in background. No hangs.
2. **Warm boot (F5 within 10min):** Dashboard instant. Zero API calls for cached cards.
3. **Tab switch → Integrations:** All 7 cards load concurrently. GitHub card renders from cache, PRs tab renders from cache. No 2-3s GH subprocess calls.
4. **Tab switch → DevOps:** All 9 cards load concurrently. K8s/TF/DNS appear immediately (no more infinite spinners).
5. **Concurrent requests:** Two cards that share no cache key compute in parallel (separate threads). Two requests for the same key — second waits for first, then gets cached result.
6. **Force refresh (🔄):** Busts client + server cache, reloads single card, cascade invalidates dependents.
7. **Timeout resilience:** Hung endpoints abort after 15s. Error badge shown. User can retry.

## 7. What This Does NOT Change

- **Card rendering logic** — individual card JS functions untouched
- **Watch path definitions** — existing entries unchanged (only new ones added)
- **Cascade invalidation** — `_CASCADE` map + `invalidate_with_cascade` untouched
- **Server startup** — `manage.sh`, `server.py` unchanged
- **CLI commands** — no changes to any CLI
