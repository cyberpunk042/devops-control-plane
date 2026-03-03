# DevOps Routes — Dashboard Preferences, Cache Management, Wizard Actions & Audit Dismissals

> **4 files · 459 lines · 12 endpoints · Blueprint: `devops_bp` · Prefix: `/api`**
>
> Central hub for DevOps dashboard and wizard operations. This package spans
> four concerns: card load preferences (DevOps tab and Integration tab),
> server-side cache management with scoped busting and background recompute,
> wizard actions (environment detection, setup execution, CI composition,
> state validation, tool checking), and audit finding dismissals. It owns
> the compute function registry — the mapping from cache keys to core
> service functions used by background recompute.

---

## How It Works

### Request Flow

```
Frontend
│
├── devops/_init.html ──────────────── Preferences + Cache
│   ├── GET  /api/devops/prefs
│   ├── PUT  /api/devops/prefs
│   └── POST /api/devops/cache/bust
│
├── integrations/_init.html ────────── Integration Preferences
│   ├── GET  /api/devops/integration-prefs
│   └── PUT  /api/devops/integration-prefs
│
├── wizard/_nav.html ───────────────── Wizard Actions
│   ├── GET  /api/wizard/detect
│   ├── POST /api/wizard/setup
│   ├── POST /api/wizard/compose-ci
│   ├── POST /api/wizard/validate
│   ├── POST /api/wizard/check-tools
│   └── DELETE /api/wizard/config
│
└── audit/_modals.html ─────────────── Audit Dismissals
    ├── POST   /api/devops/audit/dismissals
    └── DELETE /api/devops/audit/dismissals
     │
     ▼
routes/devops/                          ← HTTP layer (this package)
├── __init__.py  — prefs, cache bust, compute registry
├── detect.py    — wizard detection (cached)
├── apply.py     — wizard setup, compose, validate, check-tools, delete
└── audit.py     — dismiss/undismiss findings
     │
     ▼
Core services:
├── devops/cache.py        — cache, prefs, scoped invalidation
├── wizard_ops.py          — wizard_detect(), wizard_setup()
├── wizard_validate.py     — validate_wizard_state(), check_required_tools()
├── ci_compose.py          — compose_ci_workflows()
├── security/ops.py        — batch_dismiss_findings(), undismiss_finding_audited()
└── 12+ domain services    — registered as compute functions
```

### Preference System

```
GET /api/devops/prefs
     │
     ▼
devops_cache.load_prefs(root)
     │
     └── .state/devops_prefs.json
         {
             "docker": "visible",     ← devops tab cards
             "k8s": "hidden",
             "security": "auto",
             "int:ci": "visible",     ← integration tab cards
             "int:dns": "hidden",
         }

PUT /api/devops/prefs  { "docker": "hidden" }
     │
     ▼
existing = load_prefs(root)
existing.update(incoming)        ← merge, not replace
save_prefs(root, existing)
     │
     └── Preserves all existing keys (no data loss)
```

Integration preferences are a filtered view of the same file:

```
GET /api/devops/integration-prefs
     → { k: v for k, v in prefs if k.startswith("int:") }

PUT /api/devops/integration-prefs
     → only updates keys starting with "int:"
     → preserves all devops tab keys untouched
```

### Cache Bust System

```
POST /api/devops/cache/bust  { "card": "security" }
     │
     ├── Single card bust (with cascade):
     │   invalidate_with_cascade(root, "security")
     │   → clear "security" + any dependents
     │   → return { ok: true, busted: ["security", ...] }
     │
     ├── Scope bust:
     │   { "card": "devops" }        → bust DEVOPS_KEYS only
     │   { "card": "integrations" }  → bust INTEGRATION_KEYS only
     │   { "card": "audit" }         → bust AUDIT_KEYS only
     │
     └── Full bust:
         { "card": "all" } or {}
         │
         ├── invalidate_all(root)       ← clear all cached data
         └── recompute_all(root)        ← background thread
              │
              ├── Recompute each registered key sequentially:
              │   packages, quality, git, ci, security,
              │   docker, k8s, env, docs, terraform,
              │   dns, testing, github,
              │   audit:scores, audit:system, audit:deps,
              │   audit:structure, audit:clients
              │
              └── Per-key lock prevents duplicate work:
                  browser GET during recompute blocks on lock,
                  gets fresh result without re-running compute
```

### Compute Function Registry

```
_ensure_registry()  ← called once on first cache bust
     │
     ▼
Register 18 compute functions:

DevOps tab keys (12):
├── "packages"  → package_ops.package_status_enriched(root)
├── "quality"   → quality_ops.quality_status(root)
├── "git"       → git_ops.git_status(root)
├── "ci"        → ci_ops.ci_status(root)
├── "security"  → compound: scan_secrets() + security_posture()
├── "docker"    → docker_ops.docker_status(root)
├── "k8s"       → k8s_ops.k8s_status(root)
├── "env"       → env_ops.env_card_status(root)
├── "docs"      → docs_ops.docs_status(root)
├── "terraform" → terraform_ops.terraform_status(root)
├── "dns"       → dns_cdn_ops.dns_cdn_status(root)
└── "testing"   → testing_ops.testing_status(root)

Integration keys (1):
└── "github"    → git_ops.gh_status(root)

Audit keys (5):
├── "audit:scores"    → audit_scores(root)
├── "audit:system"    → l0_system_profile(root)
├── "audit:deps"      → l1_dependencies(root)
├── "audit:structure" → l1_structure(root)
└── "audit:clients"   → l1_clients(root)

Note: "pages" is NOT registered — it uses inlined compute
in the browser GET path (segments + build_status).
```

### Wizard Detection Flow

```
GET /api/wizard/detect?bust=1
     │
     ▼
devops_cache.get_cached(root, "wiz:detect", lambda: _detect(root), force=True)
     │
     ├── Cache HIT (no bust) → return cached snapshot
     └── Cache MISS (or bust=1) → wizard_ops.wizard_detect(root)
         │
         └── Scan: integrations, tools, project characteristics
             → { detected_integrations, available_tools, ... }
```

### Wizard Setup Dispatch

```
POST /api/wizard/setup  { "action": "docker", ... }
     │
     ▼
wizard_ops.wizard_setup(root, action, data)
     │
     ├── action = "docker"    → generate Dockerfile, docker-compose.yml
     ├── action = "k8s"       → generate K8s manifests
     ├── action = "terraform" → generate Terraform configs
     ├── action = "ci"        → generate CI workflow
     ├── action = "dns"       → generate DNS records
     └── action = ???         → { ok: false, error: "Unknown action" }
```

---

## File Map

```
routes/devops/
├── __init__.py     199 lines — blueprint, prefs, cache bust, compute registry
├── detect.py        45 lines — wizard detection (cached)
├── apply.py        145 lines — wizard setup, compose-ci, validate, check-tools, delete
├── audit.py         70 lines — dismiss/undismiss findings
└── README.md                 — this file
```

---

## Per-File Documentation

### `__init__.py` — Blueprint + Prefs + Cache (199 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `devops_prefs_get()` | GET | `/devops/prefs` | Read card load preferences |
| `devops_prefs_put()` | PUT | `/devops/prefs` | Save card load preferences (merge) |
| `integration_prefs_get()` | GET | `/devops/integration-prefs` | Read integration prefs (int:* keys) |
| `integration_prefs_put()` | PUT | `/devops/integration-prefs` | Save integration prefs (int:* keys only) |
| `devops_cache_bust()` | POST | `/devops/cache/bust` | Bust cache (scoped, single, or all) |

**Prefs merge on save:**

```python
all_prefs = devops_cache.load_prefs(_project_root())
all_prefs.update(data)  # merge incoming over existing
devops_cache.save_prefs(_project_root(), all_prefs)
return jsonify(all_prefs)
```

**Integration prefs — scoped key filter:**

```python
# Read: filter to int:* keys only
int_prefs = {k: v for k, v in prefs.items() if k.startswith("int:")}

# Write: only update int:* keys, preserve everything else
for key, val in data.items():
    if key.startswith("int:"):
        all_prefs[key] = val
```

**Cache bust — scoped invalidation with background recompute:**

```python
if card in ("all", "devops", "integrations", "audit"):
    if card == "all":
        devops_cache.invalidate_all(root)
        devops_cache.recompute_all(root)         # background thread
    else:
        devops_cache.invalidate_scope(root, card)
        scope_map = {
            "devops": devops_cache.DEVOPS_KEYS,
            "integrations": devops_cache.INTEGRATION_KEYS,
            "audit": devops_cache.AUDIT_KEYS,
        }
        devops_cache.recompute_all(root, keys=scope_map[card])
else:
    busted = devops_cache.invalidate_with_cascade(root, card)
```

**Compute registry — lazy init with all domain services:**

```python
_registry_done = False

def _ensure_registry():
    global _registry_done
    if _registry_done:
        return
    _registry_done = True

    # Deferred imports to avoid circular dependencies
    from src.core.services import (
        dns_cdn_ops, docker_ops, docs_ops, env_ops,
        k8s_ops, package_ops, quality_ops,
        security_ops, testing_ops, ci_ops, git_ops,
    )
    from src.core.services.terraform import ops as terraform_ops

    reg = devops_cache.register_compute
    reg("packages", lambda root: package_ops.package_status_enriched(root))
    reg("quality", lambda root: quality_ops.quality_status(root))
    # ... 16 more registrations
```

### `detect.py` — Wizard Detection (45 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `wizard_detect()` | GET | `/wizard/detect` | Detect integrations, tools, project characteristics |

```python
root = _project_root()
force = request.args.get("bust", "") == "1"
return jsonify(devops_cache.get_cached(
    root, "wiz:detect",
    lambda: _detect(root),
    force=force,
))
```

### `apply.py` — Wizard Actions (145 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `wizard_setup()` | POST | `/wizard/setup` | Execute a setup action (docker, k8s, terraform, etc.) |
| `wizard_delete_config()` | DELETE | `/wizard/config` | Delete wizard-generated config files |
| `wizard_compose_ci()` | POST | `/wizard/compose-ci` | Compose CI/CD workflow files from wizard state |
| `wizard_validate()` | POST | `/wizard/validate` | Validate wizard state before generation |
| `wizard_check_tools()` | POST | `/wizard/check-tools` | Check required CLI tools for wizard state |

**Setup — action dispatch:**

```python
data = request.get_json(silent=True) or {}
action = data.get("action", "")
result = wizard_ops.wizard_setup(root, action, data)
```

**CI composition — strategy-based:**

```python
state = data["state"]
strategy = data.get("strategy", "unified")   # unified or split
project_name = data.get("project_name", "")
files = compose_ci_workflows(state, strategy=strategy, project_name=project_name)
```

**Delete — target-scoped:**

```python
# target: "docker" | "k8s" | "ci" | "skaffold" | "terraform" | "dns" | "all"
result = delete_generated_configs(_project_root(), target)
```

### `audit.py` — Finding Dismissals (70 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `audit_dismissals_add()` | POST | `/devops/audit/dismissals` | Dismiss finding(s) via `# nosec` |
| `audit_dismissals_remove()` | DELETE | `/devops/audit/dismissals` | Undismiss finding (remove `# nosec`) |

**Batch or single dismiss:**

```python
items = data.get("items")
if not items:
    # Single mode
    items = [{"file": data["file"], "line": data["line"]}]
result = batch_dismiss_findings(_project_root(), items, comment)
```

**Undismiss — remove # nosec from source:**

```python
result = undismiss_finding_audited(_project_root(), file, int(line))
```

---

## Dependency Graph

```
__init__.py
├── devops/cache             ← load/save prefs, invalidation, recompute
├── helpers                  ← project_root
├── COMPUTE REGISTRY (lazy init):
│   ├── dns_cdn_ops          ← dns_cdn_status
│   ├── docker_ops           ← docker_status
│   ├── docs_ops             ← docs_status
│   ├── env_ops              ← env_card_status
│   ├── k8s_ops              ← k8s_status
│   ├── package_ops          ← package_status_enriched
│   ├── quality_ops          ← quality_status
│   ├── security_ops         ← scan_secrets, security_posture
│   ├── testing_ops          ← testing_status
│   ├── ci_ops               ← ci_status
│   ├── git_ops              ← git_status, gh_status
│   ├── terraform.ops        ← terraform_status
│   └── audit module         ← audit_scores, l0/l1 profile
│
detect.py
├── devops/cache             ← get_cached (wiz:detect key)
├── wizard_ops               ← wizard_detect (lazy)
└── helpers                  ← project_root

apply.py
├── wizard_ops               ← wizard_setup, delete_generated_configs (lazy)
├── wizard_validate          ← validate_wizard_state, check_required_tools (lazy)
├── ci_compose               ← compose_ci_workflows (lazy)
└── helpers                  ← project_root

audit.py
├── security/ops             ← batch_dismiss_findings, undismiss_finding_audited (lazy)
└── helpers                  ← project_root
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `devops_bp`, registers at `/api` prefix |
| DevOps tab | `scripts/devops/_init.html` | Prefs + cache bust |
| Integrations tab | `scripts/integrations/_init.html` | Integration prefs |
| Integrations setup | `scripts/integrations/setup/*.html` | `/wizard/setup`, `/wizard/detect` |
| Wizard | `scripts/wizard/_nav.html` | `/wizard/setup`, `/wizard/validate` |
| Wizard | `scripts/wizard/_setup.html` | `/wizard/compose-ci`, `/wizard/check-tools` |
| Wizard | `scripts/wizard/_integration_actions.html` | `/wizard/config` (DELETE) |
| Docker wizard | `scripts/docker_wizard/_raw_step1_detect.html` | `/wizard/detect` |
| K8s wizard | `scripts/k8s_wizard/_raw_step1_detect.html` | `/wizard/detect` |
| Audit | `scripts/audit/_modals.html` | Dismissals (POST/DELETE) |
| Boot | `scripts/_boot.html` | `/devops/prefs` (initial load) |
| Cache | `scripts/globals/_cache.html` | `/devops/cache/bust` |

---

## Data Shapes

### `GET /api/devops/prefs` response

```json
{
    "docker": "visible",
    "k8s": "auto",
    "security": "visible",
    "terraform": "hidden",
    "quality": "visible",
    "int:ci": "visible",
    "int:dns": "hidden",
    "int:github": "auto"
}
```

### `PUT /api/devops/prefs` request + response

```json
// Request:
{ "k8s": "hidden" }

// Response (full merged prefs):
{
    "docker": "visible",
    "k8s": "hidden",
    "security": "visible",
    "terraform": "hidden",
    "quality": "visible",
    "int:ci": "visible",
    "int:dns": "hidden",
    "int:github": "auto"
}
```

### `POST /api/devops/cache/bust` — scoped

```json
// Request:
{ "card": "devops" }

// Response:
{ "ok": true, "busted": "devops" }
```

### `POST /api/devops/cache/bust` — single with cascade

```json
// Request:
{ "card": "security" }

// Response:
{ "ok": true, "busted": ["security"] }
```

### `GET /api/wizard/detect` response

```json
{
    "docker": { "detected": true, "compose_file": "docker-compose.yml" },
    "k8s": { "detected": false },
    "terraform": { "detected": true, "dir": "terraform/" },
    "ci": { "detected": true, "provider": "github_actions" },
    "tools": {
        "docker": { "installed": true, "version": "24.0.7" },
        "kubectl": { "installed": false },
        "terraform": { "installed": true, "version": "1.7.0" }
    }
}
```

### `POST /api/wizard/setup` request + response

```json
// Request:
{ "action": "docker", "port": 8080, "base_image": "python:3.12-slim" }

// Response:
{ "ok": true, "files_created": ["Dockerfile", "docker-compose.yml"] }
```

### `POST /api/wizard/compose-ci` request + response

```json
// Request:
{
    "state": { "docker": { "enabled": true }, "k8s": { "enabled": false } },
    "strategy": "unified",
    "project_name": "my-project"
}

// Response:
{
    "ok": true,
    "files": [
        { "path": ".github/workflows/ci.yml", "content": "name: CI\n..." }
    ]
}
```

### `POST /api/wizard/validate` response

```json
{ "ok": true, "errors": [], "warnings": ["K8s namespace not set"] }
```

### `POST /api/wizard/check-tools` response

```json
{
    "ok": false,
    "tools": {
        "docker": { "installed": true, "version": "24.0.7" },
        "kubectl": { "installed": false }
    },
    "missing": ["kubectl"],
    "install_available": ["kubectl"]
}
```

### `POST /api/devops/audit/dismissals` — batch

```json
// Request:
{
    "items": [
        { "file": "src/auth.py", "line": 42 },
        { "file": "src/auth.py", "line": 55 }
    ],
    "comment": "false positive — test credentials"
}

// Response:
{ "ok": true, "dismissed": 2 }
```

### `DELETE /api/devops/audit/dismissals`

```json
// Request:
{ "file": "src/auth.py", "line": 42 }

// Response:
{ "ok": true }
```

---

## Advanced Feature Showcase

### 1. Scoped Cache Invalidation with Background Recompute

The cache bust endpoint supports 4 scoping levels:

```
Single:       "security"      → bust 1 key + cascade
Devops:       "devops"        → bust 12 devops tab keys
Integrations: "integrations"  → bust integration keys
Audit:        "audit"         → bust 5 audit keys
All:          "all" or {}     → bust all 18+ keys
```

Scoped busts trigger background recompute of only the affected keys:

```python
devops_cache.recompute_all(root, keys=scope_map[card])
```

This means switching to the audit tab and busting audit cache
won't waste CPU recomputing docker/k8s/terraform status.

### 2. Merge-Based Preference Updates

Prefs use merge-on-save, not replace:

```python
all_prefs = devops_cache.load_prefs(_project_root())
all_prefs.update(data)  # merge, not replace
devops_cache.save_prefs(_project_root(), all_prefs)
```

The frontend can send `{ "k8s": "hidden" }` to change one preference
without risking overwriting other preferences. Integration prefs
go further — the route enforces the `int:` prefix guard:

```python
for key, val in data.items():
    if key.startswith("int:"):  # only int:* keys allowed
        all_prefs[key] = val
```

### 3. Lazy Compute Registry with 18 Domain Services

The compute registry defers all 18 domain service imports to the
first cache bust, avoiding circular import chains at module load:

```python
def _ensure_registry():
    global _registry_done
    if _registry_done:
        return
    _registry_done = True
    # 18 deferred imports + registrations
```

This pattern means:
- Server startup doesn't load all domain services
- First cache bust triggers one-time import (~200ms)
- Subsequent busts reuse already-imported modules

### 4. Batch vs Single Finding Dismissal

The audit dismissal endpoint accepts both formats transparently:

```python
items = data.get("items")           # batch mode
if not items:
    items = [{"file": ..., "line": ...}]  # single mode → wrap in list
result = batch_dismiss_findings(root, items, comment)
```

### 5. CI Composition Strategies

The compose-ci endpoint supports two strategies:

```python
strategy = data.get("strategy", "unified")
```

- `"unified"` → one CI workflow file with all jobs
- `"split"` → separate workflow files per concern (test, build, deploy)

---

## Design Decisions

### Why prefs and cache share a blueprint

Preferences and cache management are both "dashboard infrastructure" —
they configure how the DevOps tab and Integration tab behave. Splitting
into separate blueprints would create two tiny microservice-style
routes that always co-occur in the UI. The shared `devops_bp` keeps
the blueprint count manageable.

### Why wizard routes live under devops_bp instead of their own blueprint

The wizard is the DevOps wizard — it configures DevOps integrations.
Its detection results feed the DevOps cache (`wiz:detect` key), its
setup actions generate DevOps configs, and its validation checks
DevOps tools. Separating it would require cross-blueprint cache
access.

### Why compute functions are registered in routes, not core

The compute registry maps cache keys to core service functions.
Registration happens in the route layer (not the core service) because:
1. The route layer knows which keys exist (API-facing concern)
2. Core services don't know about caching (they're pure functions)
3. Registration requires importing 12+ services — routes already
   handle deferred imports via the lazy pattern

### Why the security compute is compound

```python
def _compute_security(root):
    scan = _sec_ops.scan_secrets(root)
    posture = _sec_ops.security_posture(root)
    return {
        "findings": scan.get("findings", []),
        "finding_count": scan.get("count", 0),
        "posture": posture,
    }
```

The security card shows both secret scan results and overall security
posture. Rather than caching two separate keys, this compound function
produces a single cached dict that the frontend uses for both displays.

### Why pages is not registered in the compute registry

The `"pages"` dashboard card requires complex inlined computation
(page segments + build status) that doesn't fit the simple
`f(root) → dict` pattern. Its compute happens in the browser GET
path with special segment assembly logic.

---

## Coverage Summary

| Capability | Endpoint | File |
|-----------|----------|------|
| Read devops prefs | GET `/devops/prefs` | `__init__.py` |
| Save devops prefs | PUT `/devops/prefs` | `__init__.py` |
| Read integration prefs | GET `/devops/integration-prefs` | `__init__.py` |
| Save integration prefs | PUT `/devops/integration-prefs` | `__init__.py` |
| Cache bust | POST `/devops/cache/bust` | `__init__.py` |
| Environment detection | GET `/wizard/detect` | `detect.py` |
| Setup action | POST `/wizard/setup` | `apply.py` |
| CI composition | POST `/wizard/compose-ci` | `apply.py` |
| State validation | POST `/wizard/validate` | `apply.py` |
| Tool checking | POST `/wizard/check-tools` | `apply.py` |
| Delete configs | DELETE `/wizard/config` | `apply.py` |
| Dismiss findings | POST `/devops/audit/dismissals` | `audit.py` |
| Undismiss findings | DELETE `/devops/audit/dismissals` | `audit.py` |
