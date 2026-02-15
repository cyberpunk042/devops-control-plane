# Phase 6: Caching Architecture — Double Cache

**Status:** Planning  
**Depends on:** Phase 5 (Layer Push Down) ✅  
**Goal:** Every expensive endpoint is wrapped in server-side cache + client-side cache. The user can refresh individually, by group, or globally.

---

## 1. Problem Statement

The app is painfully slow on page refresh because:

1. **No server-side cache** on most endpoints — every request recomputes from scratch (subprocess calls, file scans, network API calls to GitHub)
2. **No client-side cache** on several high-traffic endpoints — `sessionStorage` cache exists but isn't applied universally
3. **Single-threaded Flask dev server** — one slow endpoint blocks ALL other requests
4. **`/api/project/status` is called TWICE** on integrations tab load (once from dashboard `loadSetupProgress()`, once from integrations `_fetchIntProjectStatus()`) — each call runs 8 integration probes
5. **`/api/metrics/health` runs 7 probes** — no caching at all on server, only client-side `cardCached('health-score')`

---

## 2. Architecture: The Double Cache

```
┌─────────────────────────────────────────────────────────────────┐
│  BROWSER (Client)                                               │
│                                                                 │
│  sessionStorage  ─── TTL: 10 min ─── key: _cc:{card}           │
│  cardCached(key) → hit? return data : fetch from server         │
│  cardStore(key, data) → save with timestamp                     │
│  cardInvalidate(key) → remove entry                             │
│  cardInvalidateAll(prefix?) → remove group or all               │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP GET /api/...
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  FLASK SERVER (Server)                                          │
│                                                                 │
│  devops_cache.get_cached(root, key, compute_fn, force=)         │
│    → file mtime check: any _WATCH_PATHS changed?               │
│    → no? return cached dict from .state/devops_cache.json       │
│    → yes? run compute_fn(), save result, return                 │
│                                                                 │
│  Response includes _cache metadata:                             │
│    { computed_at, fresh, age_seconds }                           │
└─────────────────────────────────────────────────────────────────┘
```

### Cache Coherency Protocol

- **Normal load:** Client checks sessionStorage → hit = skip fetch. Miss = fetch from server → server checks mtime → hit = return cached. Miss = recompute.
- **Individual refresh:** Client calls `cardInvalidate(key)` + `api('/devops/cache/bust', { card: key })` → both caches busted → reload that one card
- **Group refresh (tab-level):** Client calls `cardInvalidateAll(prefix)` + `api('/devops/cache/bust', { card: 'group:devops' })` → bust all cards in group → reload tab
- **Global refresh:** Client calls `cardInvalidateAll()` + `api('/devops/cache/bust', { card: 'all' })` → everything busted

### Cascade Invalidation (Dependency Graph)

When one integration changes, **dependent integrations must also invalidate**.
This mirrors the existing `DEPENDENCY_MAP` in `project_probes.py` but in **reverse direction**.

**Forward dependencies** (from `project_probes.py`):
```
git       → []
docker    → [git]
github    → [git]
cicd      → [git, docker]
k8s       → [docker]
terraform → []
pages     → [git]
dns       → [pages]
```

**Reverse invalidation graph** (what we need for cache):
```
When git changes       →  also invalidate: github, docker, cicd, pages, dns
When docker changes    →  also invalidate: cicd, k8s
When github changes    →  also invalidate: cicd
When cicd changes      →  (leaf — no dependents)
When k8s changes       →  (leaf)
When terraform changes →  (leaf)
When pages changes     →  also invalidate: dns
When dns changes       →  (leaf)

ALL individual changes →  also invalidate: project-status, health
```

**Implementation in `devops_cache.py`:**
```python
# Reverse dependency map: when key X is invalidated, also invalidate these
_CASCADE: dict[str, list[str]] = {
    "int:git":       ["int:github", "int:docker", "int:ci", "int:pages"],
    "int:docker":    ["int:ci", "int:k8s"],
    "int:github":    ["int:ci"],
    "int:pages":     ["int:dns"],
    # Any integration card bust → also bust aggregates
    "_aggregates":   ["project-status", "health"],
}

def invalidate_with_cascade(project_root: Path, card_key: str) -> list[str]:
    """Invalidate a card and all its dependents, plus aggregates."""
    busted = [card_key]
    invalidate(project_root, card_key)

    # Direct cascade
    for dep in _CASCADE.get(card_key, []):
        invalidate(project_root, dep)
        busted.append(dep)

    # Aggregate cascade (any int:* bust → bust project-status + health)
    if card_key.startswith("int:"):
        for agg in _CASCADE["_aggregates"]:
            invalidate(project_root, agg)
            busted.append(agg)

    return busted
```

**Client-side mirror** — `refreshCard()` must also invalidate dependents in sessionStorage:
```js
const _CASCADE = {
    'git':       ['github', 'docker', 'ci', 'pages'],
    'docker':    ['ci', 'k8s'],
    'github':    ['ci'],
    'pages':     ['dns'],
};

function refreshCardCascade(key) {
    cardInvalidate(key);
    for (const dep of _CASCADE[key] || []) cardInvalidate(dep);
    // Always bust aggregates
    cardInvalidate('project-status');
    cardInvalidate('health-score');
}
```

---

## 3. Complete Endpoint Audit

### 3A. Dashboard Endpoints

| Endpoint | Server Cache | Client Cache | Fix Needed |
|---|---|---|---|
| `GET /api/status` | ❌ NONE | ❌ NONE | Add both. Watch: `project.yml` |
| `GET /api/health` | ❌ NONE | ❌ NONE | Low cost, skip server cache. Add client. |
| `GET /api/audit?n=10` | ❌ NONE | ❌ NONE | Read-only log, low cost. Add client TTL=30s. |
| `GET /api/capabilities` | ❌ NONE | ❌ NONE | Static per session. Add client cache. |
| `GET /api/metrics/health` | ❌ NONE | ✅ `cardCached('health-score')` | **Add server cache.** Watch: union of all probe paths. Key: `health`. |
| `GET /api/project/status` | ❌ NONE | ❌ NONE | **Add BOTH.** Watch: union of probe paths. Key: `project-status`. Called TWICE — deduplicate. |

### 3B. DevOps Tab Endpoints (Status/Read)

| Endpoint | Server Cache | Client Cache | Fix Needed |
|---|---|---|---|
| `GET /api/quality/status` | ✅ `get_cached` | ✅ `cardCached('quality')` | ✅ DONE |
| `GET /api/testing/status` | ✅ `get_cached` | ✅ `cardCached('testing')` | ✅ DONE |
| `GET /api/security/posture-summary` | ✅ via audit cache | ✅ `cardCached('security')` | ✅ DONE |
| `GET /api/packages/status` | ✅ `get_cached` | ✅ `cardCached('packages')` | ✅ DONE |
| `GET /api/env/card-status` | ✅ `get_cached` | ✅ `cardCached('env')` | ✅ DONE |
| `GET /api/docs/status` | ✅ `get_cached` | ✅ `cardCached('docs')` | ✅ DONE |
| `GET /api/k8s/status` | ✅ `get_cached` | ✅ `cardCached('k8s')` | ✅ DONE |
| `GET /api/terraform/status` | ✅ `get_cached` | ✅ `cardCached('terraform')` | ✅ DONE |
| `GET /api/dns/status` | ✅ `get_cached` | ✅ `cardCached('dns')` | ✅ DONE |

### 3C. Integration Tab Endpoints

| Endpoint | Server Cache | Client Cache | Fix Needed |
|---|---|---|---|
| `GET /api/git/status` | ❌ NONE | ✅ `cardCached('git')` | **Add server cache.** Key: `int:git`. Watch: `.git/`, `.gitignore` |
| `GET /api/integrations/gh/status` | ❌ NONE | ✅ `cardCached('github')` | **Add server cache.** Key: `int:github`. Watch: `.github/` |
| `GET /api/ci/status` | ❌ NONE | ✅ `cardCached('ci')` | **Add server cache.** Key: `int:ci`. Watch: `.github/workflows/` |
| `GET /api/docker/status` | ❌ NONE | ✅ `cardCached('docker')` | **Add server cache.** Key: `int:docker`. Watch: `Dockerfile`, `docker-compose.yml` |
| `GET /api/gh/pulls` | ❌ NONE | ❌ NONE | Network-bound (GitHub API). Add client cache (short TTL). Optionally server cache. |
| `GET /api/gh/actions/runs` | ❌ NONE | ❌ NONE | Same as pulls — network-bound. Add client cache. |
| `GET /api/gh/actions/workflows` | ❌ NONE | ❌ NONE | Same. Add client cache. |
| `GET /api/pages/segments` | ❌ NONE | ❌ NONE | File read. Add server cache. Watch: `project.yml`, `.pages/` |
| `GET /api/pages/builders` | ❌ NONE | ❌ NONE | Static per session. Add client cache. |
| `GET /api/devops/integration-prefs` | Reads prefs file | ❌ NONE | Low cost. Add client cache for session. |

### 3D. Audit Tab Endpoints

| Endpoint | Server Cache | Client Cache | Fix Needed |
|---|---|---|---|
| All `/api/audit/*` | ✅ `get_cached` | ✅ `cardCached('audit:*')` | ✅ DONE |

### 3E. Content Tab Endpoints

| Endpoint | Server Cache | Client Cache | Fix Needed |
|---|---|---|---|
| `GET /api/content/folders` | ❌ NONE | ❌ NONE | File scan. Not critical (fast). Consider later. |
| `GET /api/content/list` | ❌ NONE | ❌ NONE | File scan. Not critical. Consider later. |

---

## 4. Implementation Plan

### Phase 6A: Server-Side Cache for Blocking Endpoints (Critical)

**Goal:** Wrap the two worst offenders that block ALL loading.

#### 6A-1: `/api/project/status` (highest priority)

**File:** `routes_project.py`

1. Add `_WATCH_PATHS` entry for `project-status`:
   ```python
   "project-status": [
       ".git/", ".github/workflows/", "Dockerfile",
       "docker-compose.yml", "docker-compose.yaml",
       "k8s/", "kubernetes/", "terraform/", "main.tf",
       "project.yml", ".pages/",
   ],
   ```

2. Wrap `project_status()` route:
   ```python
   @project_bp.route("/project/status")
   def project_status():
       root = _root()
       force = request.args.get("force") == "1"
       def _compute():
           statuses = run_all_probes(root)
           return {
               "integrations": statuses,
               "suggested_next": suggest_next(statuses),
               "progress": compute_progress(statuses),
           }
       return jsonify(get_cached(root, "project-status", _compute, force=force))
   ```

3. Add client-side cache in `_dashboard.html` `loadSetupProgress()`:
   ```js
   const cached = cardCached('project-status');
   const data = cached || await api('/project/status');
   if (!cached) cardStore('project-status', data);
   ```

4. Deduplicate: make `_fetchIntProjectStatus()` also use `cardCached('project-status')`:
   ```js
   async function _fetchIntProjectStatus() {
       if (_intProjectStatus) return _intProjectStatus;
       const cached = cardCached('project-status');
       _intProjectStatus = cached || await api('/project/status');
       if (!cached) cardStore('project-status', _intProjectStatus);
       return _intProjectStatus;
   }
   ```

#### 6A-2: `/api/metrics/health`

**File:** `routes_metrics.py`

1. Add `_WATCH_PATHS` entry for `health`:
   ```python
   "health": [
       ".git/", "Dockerfile", "docker-compose.yml",
       ".github/workflows/", "pyproject.toml", "package.json",
       ".env", "tests/", "docs/", "README.md", ".gitignore",
   ],
   ```

2. Wrap `project_health()` route:
   ```python
   @metrics_bp.route("/metrics/health")
   def project_health():
       root = _project_root()
       force = request.args.get("force") == "1"
       return jsonify(get_cached(root, "health", lambda: metrics_ops.project_health(root), force=force))
   ```

Client already has `cardCached('health-score')` — ✅ no change needed.

### Phase 6B: Server-Side Cache for Integration Cards

**Goal:** Wrap all integration status endpoints in `get_cached()`.

#### Endpoints to wrap:

| Endpoint | Key | Watch Paths |
|---|---|---|
| `GET /api/git/status` | `int:git` | `.git/`, `.gitignore` |
| `GET /api/integrations/gh/status` | `int:github` | `.github/`, `.git/config` |
| `GET /api/ci/status` | `int:ci` | `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile` |
| `GET /api/docker/status` | `int:docker` | `Dockerfile`, `docker-compose.yml`, `docker-compose.yaml`, `.dockerignore` |
| `GET /api/pages/segments` | `int:pages-segments` | `project.yml`, `.pages/` |

For each: same pattern as 6A — add watch paths → wrap in `get_cached()`.

**Files to change:**
- `routes_integrations.py` — git_status, gh_status_extended
- `routes_ci.py` — ci_status_card
- `routes_docker.py` — docker_status
- `routes_pages_api.py` — pages_segments

### Phase 6C: Client-Side Cache for Uncached Calls

**Goal:** Add `cardCached()`/`cardStore()` to dashboard calls that currently fetch raw.

| Call | Location | Cache Key |
|---|---|---|
| `api('/status')` | `_dashboard.html: loadStatus()` | `dash-status` |
| `api('/health')` | `_dashboard.html: loadHealth()` | `dash-health` |
| `api('/audit?n=10')` | `_dashboard.html: loadAudit()` | `dash-audit` |
| `api('/capabilities')` | `_dashboard.html` | `dash-capabilities` |
| `api('/gh/pulls')` | `_integrations_github.html` | `gh-pulls` |
| `api('/gh/actions/runs')` | `_integrations_github.html` | `gh-runs` |
| `api('/gh/actions/workflows')` | `_integrations_github.html` | `gh-workflows` |
| `api('/pages/builders')` | `_integrations_pages.html` | `pages-builders` |
| `api('/devops/integration-prefs')` | `_integrations_init.html` | session var only (cheap read) |

### Phase 6D: Granular Refresh Controls

**Goal:** Let the user refresh individual cards, groups, or everything.

#### 6D-1: Per-card refresh button

Every card header gets a small refresh icon:
```html
<button class="card-refresh-btn" onclick="refreshCard('git')" title="Refresh Git status">🔄</button>
```

`refreshCard(key)` function:
```js
async function refreshCard(key) {
    cardInvalidate(key);
    await api('/devops/cache/bust', { method: 'POST', body: JSON.stringify({ card: key }) });
    // Find and reload the specific card
    const meta = _INT_CARDS['int:' + key] || _DEVOPS_CARDS[key];
    if (meta?.loadFn) await meta.loadFn();
}
```

#### 6D-2: Group refresh (tab-level)

Already exists for DevOps (`loadDevopsTab(true)`) and Integrations (`loadIntegrationsTab(true)`).

**Fix:** Integrations force refresh must ALSO bust server cache:
```js
if (force) {
    // Bust server cache for integration keys
    api('/devops/cache/bust', { method: 'POST', body: JSON.stringify({ card: 'group:int' }) }).catch(() => {});
    ...
}
```

Server-side: extend `devops_cache_bust()` to support group busting:
```python
if card.startswith("group:"):
    prefix = card.split(":", 1)[1]
    # Invalidate all keys starting with prefix
    for key in list(cache.keys()):
        if key.startswith(prefix):
            invalidate(project_root, key)
```

#### 6D-3: Global refresh

Top-level refresh bar (already exists — the 🔄 button in header).

Ensure it does:
```js
function globalRefresh() {
    cardInvalidateAll();
    api('/devops/cache/bust', { method: 'POST', body: JSON.stringify({ card: 'all' }) }).catch(() => {});
    // Reload current tab
    if (activeTab === 'devops') loadDevopsTab(true);
    else if (activeTab === 'integrations') loadIntegrationsTab(true);
    else if (activeTab === 'audit') loadAuditTab(true);
    else if (activeTab === 'dashboard') { loadStatus(); loadHealthScore(); loadSetupProgress(); }
}
```

### Phase 6E: Integrations Force Refresh Fix

**Current bug:** `loadIntegrationsTab(true)` invalidates client cache but NOT server cache.

**Fix:** Add server cache bust call, matching the devops tab pattern:
```js
if (force) {
    api('/devops/cache/bust', { method: 'POST', body: JSON.stringify({ card: 'all' }) }).catch(() => {});
    ...
}
```

---

## 5. Watch Paths Registry — Complete

New entries to add to `_WATCH_PATHS` in `devops_cache.py`:

```python
# ── Project-level aggregates ────────────────────────────────
"project-status": [
    ".git/", ".github/workflows/",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "k8s/", "kubernetes/", "terraform/", "main.tf",
    "project.yml", ".pages/",
    "CNAME", "netlify.toml", "vercel.json",
],
"health": [
    ".git/", "Dockerfile", "docker-compose.yml",
    ".github/workflows/",
    "pyproject.toml", "package.json", "package-lock.json",
    ".env", ".env.example",
    "tests/", "docs/", "README.md", ".gitignore",
    "setup.cfg", ".ruff.toml", "mypy.ini",
],
# ── Integration cards ───────────────────────────────────────
"int:git": [
    ".git/", ".gitignore",
],
"int:github": [
    ".github/", ".git/config",
],
"int:ci": [
    ".github/workflows/", ".gitlab-ci.yml", "Jenkinsfile",
    ".circleci/", "bitbucket-pipelines.yml",
],
"int:docker": [
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    ".dockerignore",
],
"int:pages-segments": [
    "project.yml", ".pages/",
],
# ── Dashboard ───────────────────────────────────────────────
"dash-status": [
    "project.yml", "stacks/",
],
```

---

## 6. Execution Order

| Step | What | Files | Risk | Priority |
|---|---|---|---|---|
| **6A-1** | Server cache `/project/status` + client dedup | `routes_project.py`, `_dashboard.html`, `_integrations_init.html`, `devops_cache.py` | Low | 🔴 Critical |
| **6A-2** | Server cache `/metrics/health` | `routes_metrics.py`, `devops_cache.py` | Low | 🔴 Critical |
| **6B** | Server cache all integration status endpoints | `routes_integrations.py`, `routes_ci.py`, `routes_docker.py`, `routes_pages_api.py`, `devops_cache.py` | Low | 🟠 High |
| **6C** | Client cache for dashboard calls | `_dashboard.html` | Low | 🟡 Medium |
| **6D** | Per-card refresh buttons + group bust | `_globals.html`, `_integrations_init.html`, `_devops_init.html`, `routes_devops.py`, `devops_cache.py` | Medium | 🟡 Medium |
| **6E** | Fix integrations force refresh to bust server | `_integrations_init.html` | Low | 🔴 Critical |

---

## 7. Success Criteria

- [ ] `/api/project/status` returns in <50ms on second call (mtime check only)
- [ ] `/api/metrics/health` returns in <50ms on second call
- [ ] All integration status endpoints use `get_cached()`
- [ ] No endpoint is called twice on the same tab load
- [ ] Page refresh (F5) serves all cards from client cache (within TTL)
- [ ] Tab switch serves all cards from client cache (within TTL)
- [ ] Force refresh (🔄 button) busts BOTH server + client caches
- [ ] Per-card refresh available on every card
- [ ] Group refresh available per tab
- [ ] Global refresh available in header
- [ ] Server logs show NO redundant API calls during normal tab switching

---

## 8. Risk Assessment

| Risk | Mitigation |
|---|---|
| Stale data shown after file change | mtime-based watch paths catch changes within the poll interval |
| Watch path too broad (e.g. `.git/`) causing frequent misses | Use specific files like `.git/HEAD`, `.git/index` instead of directory |
| sessionStorage quota exceeded | Already handled with try/catch in `cardStore()` |
| Cache key collision between tabs | Use prefixed keys: `int:*`, `dash:*`, `audit:*` |
| Force refresh doesn't clear everything | Test each path explicitly |
