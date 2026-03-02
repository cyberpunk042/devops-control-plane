# DevOps Domain

> **3 files · 1,604 lines · Server-side caching, activity logging,
> and card preference management for the admin panel.**
>
> Two-module system: `cache.py` provides mtime-based caching with
> per-key thread locking, cascade invalidation, background recompute,
> SSE event publishing, audit staging, and preference management.
> `activity.py` maintains a structured activity log recording scan
> computations and user-initiated events with per-card summary and
> detail extraction for 25+ card types.

---

## How It Works

### Cache Architecture

Every DevOps/Integration/Audit card in the admin panel goes through
`get_cached()`. The cache prevents redundant computation by checking
whether source files have changed since the last scan:

```
Frontend card request → /api/devops/<card>
    │
    ├── get_cached(root, "security", compute_fn, force=False)
    │       │
    │       ├── 1. Acquire per-key lock (_get_key_lock(card_key))
    │       │      └── Prevents duplicate computation for same card
    │       │          other cards compute in parallel
    │       │
    │       ├── 2. Load cache from .state/devops_cache.json
    │       │
    │       ├── 3. Compute _max_mtime(project_root, watch_paths)
    │       │       ├── For files: single os.stat() call
    │       │       └── For directories (ending "/"): _walk_max_mtime()
    │       │             ├── os.walk() with depth limit = 3
    │       │             ├── Skip dirs: _WALK_SKIP (15 dirs)
    │       │             ├── Skip hidden files (start with ".")
    │       │             └── Skip .release.json files
    │       │
    │       ├── 4. Compare: current_mtime ≤ cached_mtime?
    │       │       │
    │       │       ├── YES (cache HIT):
    │       │       │     ├── Inject _cache metadata:
    │       │       │     │     {computed_at, fresh: true, age_seconds}
    │       │       │     ├── Publish "cache:hit" SSE event
    │       │       │     └── Return cached data
    │       │       │
    │       │       └── NO (cache MISS, or force=True, or no entry):
    │       │             ├── Publish "cache:miss" with reason
    │       │             │     (reason: "forced" | "expired" | "absent")
    │       │             ├── Call compute_fn()
    │       │             │     └── Wrapped in try/except
    │       │             ├── On success:
    │       │             │     ├── Acquire _file_lock
    │       │             │     ├── Re-read cache (avoid losing parallel writes)
    │       │             │     ├── Write new entry with data + mtime + elapsed
    │       │             │     ├── Publish "cache:done" SSE event
    │       │             │     └── Release _file_lock
    │       │             ├── On error:
    │       │             │     └── Publish "cache:error" SSE event
    │       │             ├── Inject _cache: {computed_at, fresh: false, age: 0}
    │       │             ├── Record scan activity → activity.py
    │       │             ├── Stage audit snapshot (fail-safe)
    │       │             └── Return data (or re-raise exception)
    │       │
    │       └── 5. Release per-key lock
    │
    └── Response: data dict + _cache metadata
```

### Watch Paths

Each card key maps to specific file/directory paths. When ANY path
has mtime newer than the cached result, the cache is stale. These
are the **exact** paths from `_WATCH_PATHS` in `cache.py`:

| Card Key | Watch Paths (exact) |
|----------|-------------------|
| `security` | `.gitignore`, `.gitignore.global`, `src/` |
| `testing` | `tests/`, `pyproject.toml`, `package.json`, `setup.cfg` |
| `quality` | `pyproject.toml`, `.ruff.toml`, `ruff.toml`, `mypy.ini`, `.mypy.ini`, `.eslintrc.json`, `.eslintrc.js`, `.prettierrc`, `biome.json`, `setup.cfg` |
| `packages` | `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `package.json`, `package-lock.json`, `Cargo.toml`, `go.mod`, `Pipfile` |
| `env` | `.env`, `.env.active`, `.env.vault`, `project.yml`, `project.yaml` |
| `docs` | `docs/`, `README.md`, `CHANGELOG.md`, `LICENSE`, `CONTRIBUTING.md`, `openapi.yaml`, `openapi.json` |
| `k8s` | `k8s/`, `kubernetes/`, `deploy/`, `charts/`, `kustomization.yaml`, `kustomization.yml` |
| `terraform` | `terraform/`, `infra/`, `main.tf`, `variables.tf`, `outputs.tf` |
| `dns` | `netlify.toml`, `vercel.json`, `wrangler.toml`, `CNAME`, `cloudflare/` |
| `git` | `.git/HEAD`, `.git/index`, `.gitignore` |
| `github` | `.github/`, `.git/config` |
| `ci` | `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/`, `bitbucket-pipelines.yml` |
| `docker` | `Dockerfile`, `docker-compose.yml`, `docker-compose.yaml`, `.dockerignore` |
| `pages` | `project.yml` |
| `audit:system` | `project.yml`, `stacks/` |
| `audit:deps` | `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `package.json`, `package-lock.json`, `Cargo.toml`, `go.mod`, `Gemfile`, `mix.exs` |
| `audit:structure` | `project.yml`, `src/`, `Dockerfile`, `docker-compose.yml`, `docker-compose.yaml`, `.github/workflows/`, `Makefile` |
| `audit:clients` | `pyproject.toml`, `requirements.txt`, `package.json`, `go.mod`, `Cargo.toml` |
| `audit:scores` | `pyproject.toml`, `requirements.txt`, `package.json`, `project.yml`, `tests/`, `docs/`, `.gitignore` |
| `wiz:detect` | `Dockerfile`, `docker-compose.yml`, `docker-compose.yaml`, `.github/workflows/`, `k8s/`, `kubernetes/`, `terraform/`, `main.tf`, `project.yml`, `pyproject.toml`, `package.json` |
| `project-status` | `.git/HEAD`, `.git/index`, `.github/workflows/`, `Dockerfile`, `docker-compose.yml`, `docker-compose.yaml`, `k8s/`, `kubernetes/`, `terraform/`, `main.tf`, `project.yml`, `CNAME`, `netlify.toml`, `vercel.json` |
| `gh-pulls` | `.git/HEAD`, `.git/refs/` |
| `gh-runs` | `.github/workflows/`, `.git/HEAD` |
| `gh-workflows` | `.github/workflows/` |

**Directory mtime walk:** For directory watch paths (ending `/`), the
cache calls `_walk_max_mtime()`:

- Uses `os.walk()` with depth limit `_WALK_MAX_DEPTH = 3`
- Skips 16 directories in `_WALK_SKIP`: `.git`, `.backup`,
  `node_modules`, `__pycache__`, `.venv`, `venv`, `build`, `dist`,
  `.tox`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `.next`,
  `.nuxt`, `site-packages`, `_build`
- Also skips hidden directories (starting with `.`)
- Skips hidden files and `.release.json` files
- Checks individual file mtimes (not directory mtimes — on Linux,
  dir mtime only changes on file create/delete, not edits)

### Card Key Sets

```python
DEVOPS_KEYS = {
    "security", "testing", "quality", "packages",
    "env", "docs", "k8s", "terraform", "dns",
}                                                      # 9 keys

INTEGRATION_KEYS = {
    "git", "github", "ci", "docker", "k8s",
    "terraform", "pages",
}                                                      # 7 keys

AUDIT_KEYS = {
    "audit:scores", "audit:system", "audit:deps",
    "audit:structure", "audit:clients",
    "audit:scores:enriched", "audit:l2:structure",
    "audit:l2:quality", "audit:l2:repo", "audit:l2:risks",
}                                                      # 10 keys

ALL_CARD_KEYS = DEVOPS_KEYS | INTEGRATION_KEYS | AUDIT_KEYS
```

### Card Preferences

Users control card visibility via `.state/devops_prefs.json`:

| Preference | Meaning |
|-----------|---------|
| `"auto"` | Show card if detection finds relevant data |
| `"manual"` | Always show card |
| `"visible"` | Always show card |
| `"hidden"` | Never show card |

Valid values are checked against `_VALID_PREFS = ("auto", "manual", "hidden", "visible")`.

**Default preferences** (`_DEFAULT_PREFS`, 16 keys):

```python
{
    # DevOps tab (9)
    "security": "auto",
    "testing": "auto",
    "quality": "auto",
    "packages": "auto",
    "env": "auto",
    "docs": "auto",
    "k8s": "auto",
    "terraform": "auto",
    "dns": "hidden",            # ← No integration card yet, hidden by default

    # Integrations tab (7)
    "int:git": "auto",
    "int:github": "auto",
    "int:ci": "auto",
    "int:docker": "auto",
    "int:k8s": "auto",
    "int:terraform": "auto",
    "int:pages": "auto",
}
```

Note: Integration tab preference keys are prefixed with `int:` (e.g.,
`int:git` not `git`). This is different from the card keys used in
`get_cached()` and watch paths.

### Cascade Invalidation

When a card is invalidated, its dependents are automatically busted:

```python
_CASCADE = {
    "git":    ["github", "docker", "ci", "pages"],
    "docker": ["ci", "k8s"],
    "github": ["ci"],
    "pages":  ["dns"],
}
```

`invalidate_with_cascade(root, "git")` busts: `git`, `github`,
`docker`, `ci`, `pages`, and their health probes (`hp:*`), plus
`project-status` (because `git` is an integration card).

Implementation: single read-modify-write under `_file_lock` to
avoid N separate I/O operations.

### Background Recompute

After bust-all, `recompute_all()` pre-fills the cache in a background
daemon thread. Cards are computed sequentially in a specific order,
slowest first:

```python
_RECOMPUTE_ORDER = [
    # Slowest (6-30s alone, 30s+ under contention)
    "testing",
    # Slow (5-20s)
    "dns", "terraform", "docs",
    # Medium (1-5s)
    "env", "k8s", "docker", "security",
    # Fast (< 1s) — browser can handle these
    "ci", "git", "quality", "packages",
    # Integration-only
    "github",
    # Audit L0/L1 (fast, 0.5-2s each)
    "audit:scores", "audit:system", "audit:deps",
    "audit:structure", "audit:clients",
]
```

Route modules register compute functions via `register_compute(key, fn)`.
Only one recompute thread runs at a time (`_recompute_thread` guard).
Browser requests arriving during recompute block on the per-key lock
and get the fresh result as soon as the background thread finishes.

SSE events: `sys:warming` at start (with key list), `sys:warm` at end
(with duration and count).

---

## Activity Log

The activity log records two types of entries to
`.state/audit_activity.json` (max 200 entries):

### Scan Activities (automatic)

Recorded by `record_scan_activity()` whenever `get_cached()` completes
a computation:

```python
{
    "ts": 1709312400.0,             # Unix timestamp (float)
    "iso": "2026-03-01T17:00:00",   # ISO 8601
    "card": "security",             # card_key
    "label": "🔐 Security",        # from DataRegistry.card_labels
    "status": "ok",                 # or "error"
    "duration_s": 1.23,             # computation time
    "summary": "3 issues · Score: 85 (B)",  # from _extract_summary
    "bust": false,                  # True if user-initiated refresh
    "detail": { ... },              # from _extract_detail (optional)
}
```

### User Events (explicit)

Recorded by `record_event()` for arbitrary user-initiated actions:

```python
{
    "ts": 1709312700.0,
    "iso": "2026-03-01T17:05:00",
    "card": "security",             # or "event" (default)
    "label": "🚫 Finding Dismissed",
    "status": "ok",
    "duration_s": 0,
    "summary": "# nosec added to 2 line(s): a.py:10, b.py:20 — test",
    "bust": false,
    "detail": { ... },              # optional
    "action": "dismissed",          # optional verb
    "target": "a.py:10, b.py:20",  # optional target
    "before": { ... },              # optional (NOT "before_state")
    "after": { ... },               # optional (NOT "after_state")
}
```

Note: the parameter names are `before_state` and `after_state`, but
they are stored in the entry dict as `"before"` and `"after"`.

### Summary Extraction

`_extract_summary()` (214 lines) generates one-liners for **29 card
types**. Each has type-specific logic. Examples:

| Card | Example Summary |
|------|----------------|
| `security` | `3 issues · Score: 85 (B)` |
| `testing` | `12 test files, 85 functions (pytest)` |
| `quality` | `3 tool(s) available: ruff, mypy, eslint` |
| `packages` | `2 manager(s): pip, npm` |
| `env` | `3 environment(s), active: production` |
| `docs` | `README ✓ · CHANGELOG ✗ · 2 doc dir(s)` |
| `k8s` | `5 manifest(s)` |
| `terraform` | `12 resource(s)` |
| `git` | `Branch: main · ↑0 ↓2 · 3 changed` |
| `docker` | `2 Dockerfile(s) · 3 service(s)` |
| `ci` | `5 workflow(s) (GitHub Actions)` |
| `audit:scores` | `Complexity 6/10 · Quality 8/10` |
| `audit:system` | `Ubuntu 22.04 · Python 3.12.1 · 8/12 tools available` |
| `audit:deps` | `45 dependencies across 2 ecosystem(s)` |
| `audit:l2:risks` | `12 findings (3 critical, 5 high, 4 medium)` |
| `project-status` | `7/9 integrations ready (78%)` |
| `gh-pulls` | `3 open PR(s)` |

### Detail Extraction

`_extract_detail()` (434 lines) extracts compact metric dicts for each
card type for rich UI rendering. Returns `None` on error or when no
useful data can be extracted. Falls back to a generic extractor that
grabs up to 10 top-level scalar fields.

---

## Key Data Shapes

### get_cached: `_cache` metadata injected into response

```python
# Cache HIT
data["_cache"] = {
    "computed_at": 1709312400.0,    # Unix timestamp when computed
    "fresh": True,                  # True = from cache, False = just computed
    "age_seconds": 42,              # seconds since computation
}

# Cache MISS (just computed)
data["_cache"] = {
    "computed_at": 1709312700.0,
    "fresh": False,
    "age_seconds": 0,
}
```

There is **no** `source`, `cached_at` (as ISO string), or `elapsed_ms`
field — the old README fabricated those.

### Cache entry (in .state/devops_cache.json)

```python
{
    "security": {
        "data": { ... },           # the compute_fn result
        "cached_at": 1709312400.0, # when computed (Unix timestamp)
        "mtime": 1709312399.0,     # max mtime of watch paths at compute time
        "elapsed_s": 1.23,         # how long compute_fn took
    },
    "testing": { ... },
    # ...
}
```

### Preferences (`.state/devops_prefs.json`)

```python
{
    "security": "auto",
    "testing": "manual",
    "dns": "hidden",
    "int:git": "auto",
    "int:k8s": "visible",
    # ... 16 keys total
}
```

`load_prefs()` merges from defaults — missing keys get default values,
unknown keys with invalid values are ignored.

### load_activity response

```python
[
    {
        "ts": 1709312400.0,
        "iso": "2026-03-01T17:00:00",
        "card": "security",
        "label": "🔐 Security",
        "status": "ok",
        "duration_s": 1.23,
        "summary": "3 issues · Score: 85 (B)",
        "bust": False,
        "detail": {"score": "85/100", "grade": "B", "findings": "3"},
    },
    # ... up to N entries (default 50, max 200 on disk)
]
```

If the activity file is empty but cache data exists, `load_activity()`
seeds entries from cache metadata with summary `"loaded from cache
(historical)"`.

---

## Architecture

```
         Routes (DevOps / Integrations / Audit / Wizard)
              ↓ register_compute()     ↓ get_cached()
         ┌────────────────────────────────────────────┐
         │  __init__.py (38 lines)                     │
         │  Re-exports all public API                  │
         └──┬─────────────────────────────────────┬───┘
            │                                     │
    ┌───────▼──────────┐              ┌───────────▼────────┐
    │  cache.py (701)  │              │  activity.py (865) │
    ├──────────────────┤              ├────────────────────┤
    │ get_cached       │              │ record_scan_activity│
    │ invalidate       │ ──────────►  │ record_event       │
    │ invalidate_all   │  delegates   │ load_activity      │
    │ invalidate_scope │ via wrapper  │ _extract_summary   │
    │ invalidate_with_ │              │ _extract_detail    │
    │   cascade        │              │ _card_label        │
    │ register_compute │              │ _activity_path     │
    │ recompute_all    │              └────────────────────┘
    │ load_prefs       │
    │ save_prefs       │
    │ _max_mtime       │
    │ _walk_max_mtime  │
    │ _publish_event   │
    │ _load_cache      │
    │ _save_cache      │
    └──────────────────┘
```

`cache.py` imports from `activity.py` at module level (line 639):
`record_scan_activity`, `record_event`, `load_activity`,
`_extract_summary`, `_card_label`, `_activity_path`.

The `_record_activity` function in `cache.py` is a thin wrapper that
delegates to `record_scan_activity` in `activity.py`.

### Thread Safety

| Mechanism | Type | Purpose |
|-----------|------|---------|
| `_key_locks` | `dict[str, Lock]` | Per-card lock — prevents duplicate computation |
| `_key_locks_guard` | `Lock` | Guards creation of per-key locks |
| `_file_lock` | `Lock` | Guards read-modify-write of `devops_cache.json` |
| `_recompute_thread` | `Thread \| None` | Background recompute — only one at a time |

### SSE Event Bus Integration

`_publish_event()` publishes cache lifecycle events to the SSE bus.
Fail-safe: if the bus is not available or publish raises, the error
is silently swallowed. Events:

| Event Type | When | Data |
|-----------|------|------|
| `cache:hit` | Cached result returned | `{age_seconds, mtime}` |
| `cache:miss` | Recomputing | `{reason}` |
| `cache:done` | Computation succeeded | `{data, duration_s}` |
| `cache:error` | Computation failed | `{error, duration_s}` |
| `cache:bust` | Scope invalidated | `{scope, keys}` |
| `sys:warming` | Background recompute starting | `{keys, total}` |
| `sys:warm` | Background recompute finished | `{keys_computed, total, duration_s}` |

---

## Dependency Graph

```
cache.py (central hub)
  │
  ├── json, os, threading, time, pathlib ← stdlib
  │
  ├── activity.py (module-level import)
  │     ├── record_scan_activity
  │     ├── record_event
  │     ├── load_activity
  │     ├── _extract_summary
  │     ├── _card_label
  │     └── _activity_path
  │
  ├── event_bus.bus.publish (lazy, fail-safe)
  ├── audit_staging.stage_audit (lazy, fail-safe)
  │
  └── NO other service imports at module level

activity.py (summary + detail extraction)
  │
  ├── json, logging, time, pathlib ← stdlib
  ├── DataRegistry.card_labels (lazy via _card_label)
  └── cache._load_cache (lazy, only in load_activity seeding)
```

Key design: `activity.py` has **no module-level imports from cache.py**.
It only imports from cache inside `load_activity()` when seeding from
cache data. This avoids circular imports since `cache.py` imports from
`activity.py` at module level.

---

## Consumers

The devops cache is the **most imported module** in the project:

| Layer | Module | What It Uses |
|-------|--------|-------------|
| **Web Routes** | `routes/devops/__init__.py` | `cache` module (all ops) |
| **Web Routes** | `routes/devops/detect.py` | `cache` module |
| **Web Routes** | `routes/security_scan/detect.py` | `get_cached`, `_load_cache` |
| **Web Routes** | `routes/testing/status.py` | `get_cached` |
| **Web Routes** | `routes/quality/status.py` | `get_cached` |
| **Web Routes** | `routes/packages/status.py` | `get_cached` |
| **Web Routes** | `routes/k8s/detect.py` | `get_cached` |
| **Web Routes** | `routes/terraform/status.py` | `get_cached` |
| **Web Routes** | `routes/ci/status.py` | `get_cached` |
| **Web Routes** | `routes/dns/__init__.py` | `get_cached` |
| **Web Routes** | `routes/pages/api.py` | `get_cached` |
| **Web Routes** | `routes/integrations/git.py` | `get_cached` |
| **Web Routes** | `routes/integrations/github.py` | `get_cached` |
| **Web Routes** | `routes/integrations/gh_auth.py` | `cache` module |
| **Web Routes** | `routes/project/__init__.py` | `get_cached` |
| **Web Routes** | `routes/api/audit.py` | `cache` module |
| **Web Routes** | `routes/audit/analysis.py` | `cache` module |
| **Web Routes** | `routes/audit/tool_install.py` | `cache` module |
| **Web Routes** | `routes/audit/tool_execution.py` | `cache` module |
| **Web Server** | `web/server.py` | `_load_cache` |
| **Web Helpers** | `web/helpers.py` | `cache` module |
| **Services** | `security/common.py` | `cache.invalidate`, `cache.record_event` |
| **Services** | `audit/l2_risk.py` | `_load_cache` |
| **Services** | `audit_helpers.py` | `record_event` |
| **Services** | `staleness_watcher.py` | `_WATCH_PATHS`, `_load_cache`, `_max_mtime` |
| **Services** | `metrics/ops.py` | `get_cached` (6 uses) |
| **Services** | `wizard/detect.py` | `cache` module |
| **Services** | `wizard/setup_infra.py` | `cache` module (4 uses) |
| **Services** | `wizard/setup_git.py` | `cache` module |
| **Services** | `wizard/setup_ci.py` | `cache` module |
| **Services** | `wizard/setup_dns.py` | `cache` module |
| **Services** | `wizard/dispatch.py` | `cache` module |
| **Services** | `chat/chat_refs.py` | `load_activity` |
| **Shim** | `devops_cache.py` | `from devops.cache import *` |
| **Shim** | `devops_activity.py` | `from devops.activity import *` |

---

## File Map

```
devops/
├── __init__.py    38 lines   — public API re-exports
├── cache.py       701 lines  — mtime cache + prefs + SSE + cascade + recompute
├── activity.py    865 lines  — activity log: scan + events + summary + detail
└── README.md                 — this file
```

---

## Per-File Documentation

### `cache.py` — Server-Side Cache (701 lines)

**Public functions:**

| Function | What It Does |
|----------|-------------|
| `get_cached(root, key, compute_fn, *, force=False)` | **Main** — return cached data or recompute. Per-key lock. SSE events. Activity recording. Audit staging. Injects `_cache` metadata. |
| `invalidate(root, key)` | Delete a single card's cache entry. Thread-safe under `_file_lock`. |
| `invalidate_all(root)` | Delete ALL cache entries. Thread-safe. |
| `invalidate_scope(root, scope)` | Delete a named scope of cards. Scopes: `"devops"`, `"integrations"`, `"audit"`, `"all"`. Returns busted key list. |
| `invalidate_with_cascade(root, key)` | Delete a card + its dependents (via `_CASCADE`) + health probes + aggregates. Single read-modify-write. Returns busted key list. |
| `register_compute(key, fn)` | Register a compute function for background recompute. Called by routes at import time. |
| `recompute_all(root, *, keys=None)` | Recompute registered cards in background daemon thread. Slowest-first order. At most one thread at a time. |
| `load_prefs(root)` | Load card preferences. Merges from `_DEFAULT_PREFS`. Unknown/invalid values ignored. |
| `save_prefs(root, prefs)` | Save card preferences. Validates against `_VALID_PREFS`. Returns merged result. |
| `record_event(...)` | *(re-exported from activity.py)* |

**Private functions:**

| Function | What It Does |
|----------|-------------|
| `_load_cache(root)` | Read `.state/devops_cache.json` → dict |
| `_save_cache(root, cache)` | Write cache dict. Caller MUST hold `_file_lock`. |
| `_max_mtime(root, watch_paths)` | Get newest file mtime across watch paths. Directories get walked. |
| `_walk_max_mtime(directory)` | Depth-limited (3), filtered directory walk for max file mtime. |
| `_publish_event(event_type, **kw)` | SSE bus publish, fail-safe. |
| `_get_key_lock(key)` | Get or create per-key lock. |
| `_cache_path(root)` | → `root / .state/devops_cache.json` |
| `_prefs_path(root)` | → `root / .state/devops_prefs.json` |
| `_record_activity(...)` | Thin wrapper → `record_scan_activity()` |

**Constants:**

| Constant | Value | Purpose |
|----------|-------|---------|
| `_CACHE_FILE` | `".state/devops_cache.json"` | Cache file path |
| `_PREFS_FILE` | `".state/devops_prefs.json"` | Preferences file path |
| `_ACTIVITY_FILE` | `".state/audit_activity.json"` | Activity log path |
| `_ACTIVITY_MAX` | `200` | Max activity entries kept |
| `_DEFAULT_PREFS` | 16 keys | Default card preferences (dns="hidden", rest="auto") |
| `_VALID_PREFS` | `("auto", "manual", "hidden", "visible")` | Allowed preference values |
| `DEVOPS_KEYS` | 9 keys | DevOps tab card set |
| `INTEGRATION_KEYS` | 7 keys | Integrations tab card set |
| `AUDIT_KEYS` | 10 keys | Audit tab card set |
| `ALL_CARD_KEYS` | union | All card keys |
| `_WATCH_PATHS` | 24 entries | File/dir watch configuration per card |
| `_WALK_MAX_DEPTH` | `3` | Directory mtime walk depth limit |
| `_WALK_SKIP` | 16 dirs | Directories skipped during mtime walks |
| `_CASCADE` | 4 entries | Cascade invalidation graph |
| `_AGGREGATE_KEYS` | `["project-status"]` | Busted on any integration change |
| `_RECOMPUTE_ORDER` | 17 keys | Slowest-first recompute sequence |
| `_COMPUTE_REGISTRY` | dict | Card key → compute function |

### `activity.py` — Activity Log (865 lines)

**Public functions:**

| Function | What It Does |
|----------|-------------|
| `record_scan_activity(root, key, status, elapsed_s, data, error_msg, *, bust)` | Record a cache scan computation. Extracts summary and detail. Appends to JSON log. Trims to 200 max. |
| `record_event(root, label, summary, *, detail, card, action, target, before_state, after_state)` | Record a user-initiated action. Supports optional action/target/before/after for forensic audit. |
| `load_activity(root, n=50)` | Load latest N entries. Seeds from cache metadata if log is empty but cache data exists. |

**Private functions:**

| Function | Lines | What It Does |
|----------|-------|-------------|
| `_extract_summary(key, data)` | 34–247 | Per-card one-liner summary (25 card types). Returns "completed" as fallback. |
| `_extract_detail(key, data)` | 250–683 | Per-card compact metrics dict (25 card types). Returns None on error. Generic fallback grabs up to 10 scalar fields. |
| `_card_label(key)` | 24–27 | Loads display label from `DataRegistry.card_labels`. |
| `_activity_path(root)` | 30–31 | → `root / .state/audit_activity.json` |

**Summary extraction covers these card types:**

`audit:l2:risks`, `audit:scores`, `audit:scores:enriched`,
`audit:system`, `audit:deps`, `audit:structure`, `audit:clients`,
`audit:l2:quality`, `audit:l2:repo`, `audit:l2:structure`,
`testing`, `security`, `quality`, `packages`, `env`, `docs`, `k8s`,
`terraform`, `git`, `github`, `ci`, `docker`, `dns`, `pages`,
`gh-pulls`, `gh-runs`, `gh-workflows`, `project-status`, `wiz:detect`

**Detail extraction** covers the same set with card-specific field
selection. The `_extract_detail` function is 434 lines because each
card type requires custom logic to pull the right metrics.

---

## Advanced Feature Showcase

### 1. Per-Key Lock Guard — Double-Checked Lock Creation

The cache uses a lock-per-card to allow independent cards to compute in
parallel while preventing duplicate computation. The lock creation itself
is guarded by a separate lock to prevent race conditions:

```python
# cache.py — _get_key_lock (lines 39-44)

_key_locks: dict[str, threading.Lock] = {}
_key_locks_guard = threading.Lock()

def _get_key_lock(key: str) -> threading.Lock:
    with _key_locks_guard:           # guard the dict itself
        if key not in _key_locks:
            _key_locks[key] = threading.Lock()
        return _key_locks[key]
```

This is the double-checked locking pattern: `_key_locks_guard` protects
the *creation* of per-key locks, while each per-key lock protects the
*computation* of its card. Two browser tabs requesting `security`
simultaneously: one computes, the other waits on the lock and gets
the fresh cached result — no duplicate subprocess work.

### 2. Mtime Walk — Depth-Limited, Filtered Directory Scan

The cache determines staleness by walking directories (for watch paths
ending in `/`). The walk is carefully pruned for performance:

```python
# cache.py — _walk_max_mtime (lines 266-291)

_WALK_SKIP = frozenset({
    ".git", ".backup", "node_modules", "__pycache__", ".venv", "venv",
    "build", "dist", ".tox", ".mypy_cache", ".ruff_cache",
    ".pytest_cache", ".next", ".nuxt", "site-packages", "_build",
})
_WALK_MAX_DEPTH = 3

def _walk_max_mtime(directory: Path) -> float:
    max_mt = 0.0
    base = str(directory)
    for root, dirs, files in os.walk(directory):
        depth = root[len(base):].count(os.sep)
        if depth >= _WALK_MAX_DEPTH:
            dirs.clear()              # stop recursion at depth 3
            continue
        # In-place pruning: os.walk respects this modification
        dirs[:] = [d for d in dirs if d not in _WALK_SKIP
                   and not d.startswith(".")]
        for fname in files:
            if fname.startswith(".") or fname.endswith(".release.json"):
                continue
            mt = os.stat(os.path.join(root, fname)).st_mtime
            if mt > max_mt:
                max_mt = mt
    return max_mt
```

Key detail: `dirs[:] = ...` modifies the list **in-place**, which
`os.walk()` respects — skipped directories are never descended into.
`dirs.clear()` at depth limit is equivalent but even more efficient.

### 3. Cascade Invalidation — Single Read-Modify-Write

When a card like `git` is invalidated, all its dependents must also be
busted. The cascade is resolved in memory and applied in a single I/O
operation:

```python
# cache.py — invalidate_with_cascade (lines 596-634)

_CASCADE = {
    "git":    ["github", "docker", "ci", "pages"],
    "docker": ["ci", "k8s"],
    "github": ["ci"],
    "pages":  ["dns"],
}
_AGGREGATE_KEYS = ["project-status"]

def invalidate_with_cascade(root, card_key):
    keys_to_bust = [card_key]
    # Health probe for this card
    hp_key = f"hp:{card_key}"
    if hp_key in _WATCH_PATHS:
        keys_to_bust.append(hp_key)
    # Direct cascade
    for dep in _CASCADE.get(card_key, []):
        keys_to_bust.append(dep)
        dep_hp = f"hp:{dep}"
        if dep_hp in _WATCH_PATHS:
            keys_to_bust.append(dep_hp)
    # Any integration card → also bust aggregates
    if card_key in _INTEGRATION_KEYS:
        keys_to_bust.extend(_AGGREGATE_KEYS)

    # ONE read-modify-write (not N separate I/O ops)
    with _file_lock:
        cache = _load_cache(root)
        for k in keys_to_bust:
            if k in cache:
                del cache[k]
        _save_cache(root, cache)
    return keys_to_bust
```

Calling `invalidate_with_cascade("git")` busts 5+ keys in a single
disk write — not 5 separate reads and writes.

### 4. Activity Log Seeding from Cache Metadata

When the activity log is empty (first run, or file deleted), `load_activity`
seeds entries from existing cache data so the UI shows historical info:

```python
# activity.py — load_activity (lines 810-864)

def load_activity(project_root, n=50):
    path = _activity_path(project_root)
    entries = []
    if path.exists():
        entries = json.loads(path.read_text(encoding="utf-8"))

    # Seed from cache if empty
    if not entries:
        from .cache import _load_cache   # lazy — avoids circular import
        cache = _load_cache(project_root)
        if cache:
            for card_key, entry in cache.items():
                cached_at = entry.get("cached_at", 0)
                if not cached_at:
                    continue
                entries.append({
                    "ts": cached_at,
                    "iso": datetime.fromtimestamp(cached_at, tz=UTC).isoformat(),
                    "card": card_key,
                    "label": _card_label(card_key),
                    "summary": "loaded from cache (historical)",
                    ...
                })
            entries.sort(key=lambda e: e.get("ts", 0))
            # Persist so seeding only happens once
            path.write_text(json.dumps(entries, default=str))
    return entries[-n:]
```

The lazy import of `_load_cache` is critical: `cache.py` imports from
`activity.py` at module level (line 639), so the reverse must be lazy
to avoid circular imports.

### 5. Background Recompute with SSE Lifecycle

After `bust_all`, `recompute_all` pre-fills the cache in a daemon thread
with full SSE observability:

```python
# cache.py — recompute_all (lines 515-574)

_recompute_thread: threading.Thread | None = None

def recompute_all(root, *, keys=None):
    global _recompute_thread
    # Only one recompute at a time
    if _recompute_thread is not None and _recompute_thread.is_alive():
        return

    target_keys = [
        k for k in _RECOMPUTE_ORDER       # slowest-first order
        if k in _COMPUTE_REGISTRY
        and (keys is None or k in keys)
    ]

    def _worker():
        _publish_event("sys:warming", data={
            "keys": target_keys, "total": len(target_keys)
        })
        for key in target_keys:
            fn = _COMPUTE_REGISTRY[key]
            get_cached(root, key, lambda: fn(root))  # reuses full cache path
        _publish_event("sys:warm", duration_s=elapsed, data={
            "keys_computed": computed, "total": len(_COMPUTE_REGISTRY)
        })

    _recompute_thread = threading.Thread(
        target=_worker, daemon=True, name="cache-recompute"
    )
    _recompute_thread.start()
```

The worker reuses `get_cached()` — it goes through the same lock/mtime/SSE
path as browser requests. Browser GETs arriving during recompute block on
the per-key lock and get fresh results as soon as the background thread
finishes that card.

### 6. 29-Card Summary Extraction Pipeline

`_extract_summary()` implements a 214-line dispatch pipeline covering 29
distinct card types with type-specific logic:

```python
# activity.py — _extract_summary (lines 34-247)

def _extract_summary(card_key, data):
    if "error" in data:
        return f"Error: {data['error'][:100]}"

    # Audit cards — each has unique data shapes
    if card_key == "audit:l2:risks":
        findings = data.get("findings", [])
        by_sev = {}  # count by severity
        for f in findings:
            s = f.get("severity", "info")
            by_sev[s] = by_sev.get(s, 0) + 1
        # Sort by severity (critical first)
        parts = [f"{c} {s}" for s, c in sorted(by_sev.items(),
            key=lambda x: {"critical": 0, "high": 1, ...}.get(x[0], 5))]
        return f"{len(findings)} findings ({', '.join(parts)})"

    if card_key == "security":
        # ... type-specific extraction
    if card_key == "testing":
        # ... type-specific extraction
    # ... 26 more card types

    # Generic fallback
    for key in ("total", "count", "items"):
        if key in data:
            return f"{data[key]} {key}"
    return "completed"
```

No generic extraction is possible because each card returns a completely
different data structure. The fallback (`"completed"`) only fires for
unknown card types that don't match any `total`/`count`/`items` key.

### 7. Re-Read-Before-Write — Preventing Parallel Write Loss

When saving fresh computation results, `get_cached()` re-reads the cache
file under the file lock to avoid losing parallel writes:

```python
# cache.py — get_cached (lines 381-392)

if status == "ok":
    # Re-read cache before writing to avoid losing entries
    # that were computed in parallel by other key locks.
    with _file_lock:
        fresh_cache = _load_cache(project_root)      # re-read!
        fresh_cache[card_key] = {
            "data": data,
            "cached_at": now,
            "mtime": current_mtime if current_mtime > 0 else now,
            "elapsed_s": elapsed,
        }
        _save_cache(project_root, fresh_cache)
```

Why re-read? Two cards compute in parallel (each holding their own
per-key lock). Card A finishes first, writes cache. Card B finishes
second — if it writes from its stale in-memory copy, Card A's result
is lost. The re-read under `_file_lock` ensures both results are kept.

---

### Feature Coverage Summary

| Feature | Where | Complexity |
|---------|-------|-----------|
| Double-checked per-key lock creation | `cache.py` `_get_key_lock` | Threading guard + per-key lock |
| Depth-limited filtered mtime walk | `cache.py` `_walk_max_mtime` | In-place dir pruning + depth 3 limit |
| Single-I/O cascade invalidation | `cache.py` `invalidate_with_cascade` | Resolve graph in memory, one write |
| Activity seeding from cache | `activity.py` `load_activity` | Lazy import to avoid circular deps |
| Background recompute with SSE | `cache.py` `recompute_all` | Daemon thread, slowest-first, single-thread guard |
| 29-card summary dispatch pipeline | `activity.py` `_extract_summary` | 214 lines of type-specific extractors |
| Re-read-before-write pattern | `cache.py` `get_cached` | Prevents parallel write loss |

---

## Design Decisions

### Why mtime-based invalidation instead of content hashing?

Content hashing requires reading every watched file on every request.
Mtime checking is a single `os.stat()` syscall per file path — orders
of magnitude faster. The tradeoff is that touching a file without
changing content triggers a recompute, but this is rare and cheap
compared to hashing large source trees.

### Why per-key locks instead of a global lock?

Different cards scan different file sets and take different amounts of
time (testing: 6-30s, git: <100ms). A global lock serializes all cards.
Per-key locks let independent cards compute in parallel while preventing
duplicate work when two browser tabs request the same card simultaneously.

### Why does the directory mtime walk have a depth limit?

Large projects can have deeply nested directories with thousands of
files. An unbounded walk makes the mtime check slower than recomputing.
Depth 3 covers meaningful changes (source edits, config updates) without
traversing `node_modules`-style deep trees. The walk also skips 16
artifact/cache directories to avoid false staleness.

### Why slowest-first recompute order?

After bust-all, the browser requests all cards in parallel (semaphored).
If the background thread computes fast cards first, slow cards are
still cold when the browser hits them — causing contention. Computing
slow cards first (testing, dns, terraform) means they're already done
when the browser's parallel requests reach them. Fast cards (git,
quality) are trivial for the browser to compute directly.

### Why JSON activity logs instead of a database?

The activity log is small (max 200 entries), append-mostly, and
human-readable. JSON is zero-dependency, inspectable with `cat`, and
trivially backed up with the project. A database would add complexity
for minimal benefit at this scale.

### Why does record_event support before/after state?

This enables forensic debugging: "what changed when the user dismissed
a finding?" or "what was the security score before and after the audit?"
The before/after pattern (stored as `"before"` and `"after"` in the
JSON entry) is standard in audit logging and essential for understanding
the impact of user actions.

### Why is _extract_detail 434 lines?

Each of the 25+ card types returns different data structures. The
detail extractor must know the shape of each card's data to pull the
right metrics. There's no generic way to extract "the important fields"
without card-specific knowledge. The alternative — returning the full
data dict — would bloat the activity log from kilobytes to megabytes.

### Why does cache.py import from activity.py at module level?

Cache needs `record_scan_activity`, `record_event`, `_extract_summary`,
and `_card_label` for every cache operation. Lazy imports would add
overhead to the hot path. The reverse direction (activity importing
from cache) is lazy to prevent circular imports.
