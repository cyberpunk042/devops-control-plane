# Path 2: Static Data Extraction & Data Layer Architecture

> **Status**: Phase 2A ✅ | Phase 2B ✅ | Phase 2C ✅ | Phase 2D pending
> **Effort**: 2–3 days (phased)
> **Risk**: Medium — extracting data from JS templates requires careful JS import rewiring
> **Prereqs**: Path 1 (Logging) ✅
> **Unlocks**: Path 3 (Monster file split), Path 7 (Caching architecture)

---

## 1. Inventory: Every Piece of Hardwired Data

### 1.1 Infrastructure Service Catalog (JS)

**Location**: `_integrations_setup_modals.html` lines 716–1248
**Lines**: ~517 lines of pure JSON-as-JavaScript
**Structure**: Array of 60+ service definitions (Postgres, Redis, Kafka, etc.)

```javascript
const _infraOptions = [
    { key:'postgres', label:'PostgreSQL', cat:'db-rel',
      images:['postgres:16-alpine', ...],
      ports:[{port:5432,label:'PostgreSQL'}],
      envFields:[ {key:'POSTGRES_DB', label:'Database', default:'app'}, ... ],
      volumes:[{name:'pgdata',mount:'/var/lib/postgresql/data'}],
    },
    // ... 60+ entries
];
const _infraCategories = {
    'db-rel':  '🗄️ Relational Databases',
    'db-nosql':'🍃 NoSQL & Time-Series',
    // ... 10 categories
};
```

**Currently exposed as**: `window._infraOptions`, `window._infraCategories`
**Consumers**: Docker Setup Wizard, K8s Setup Wizard (both read `_infraOptions`)
**Nature**: 100% static — never changes during runtime

### 1.2 Docker Stack Defaults (JS)

**Location**: `_integrations_setup_modals.html` lines 1282–1376
**Lines**: ~95 lines
**Structure**: Object mapping stack family → Dockerfile defaults

```javascript
const _dockerStackDefaults = {
    python: { images:['python:3.12-slim',...], workdir:'/app', install:'pip install...', cmd:'...', expose:8000 },
    node:   { images:['node:20-alpine',...], workdir:'/app', install:'npm ci...', cmd:'node index.js', expose:3000 },
    // ... 10 stack families
};
const _restartPolicies = ['unless-stopped','always','on-failure','no'];
const _platformOptions = ['','linux/amd64','linux/arm64','linux/amd64,linux/arm64'];
```

**Consumers**: Docker Setup Wizard only
**Nature**: 100% static

### 1.3 K8s StorageClass Catalog (JS)

**Location**: `_integrations_setup_modals.html` lines 3646–3672
**Lines**: ~27 lines
**Structure**: Grouped by cloud provider

```javascript
const _SC_CATALOG = [
    { group: 'Self-hosted', items: [
        { name:'longhorn', provisioner:'driver.longhorn.io', hint:'Distributed block storage' },
        // ...
    ]},
    { group: 'AWS', items: [...] },
    { group: 'GKE', items: [...] },
    { group: 'Azure', items: [...] },
    { group: 'DigitalOcean', items: [...] },
];
```

**Consumers**: K8s Setup Wizard only (merged with live cluster detection)
**Nature**: Base is static; cluster detection adds `_detected` flags at runtime

### 1.4 K8s Resource Kinds (JS)

**Location**: `_integrations_k8s.html` line 635
**Lines**: 1 line
**Structure**: Simple array

```javascript
const _KW_KINDS = ['Deployment','Service','ConfigMap','Ingress','Namespace','Secret','Job','CronJob','StatefulSet','DaemonSet'];
```

**Consumers**: K8s Manifest Wizard
**Nature**: 100% static

### 1.5 Secret Pattern Detection (Python × 2 + JS × 1)

**DUPLICATED across 3 files**:
- `src/core/services/vault_env_ops.py` line 29 (Python, frozenset)
- `src/core/services/secrets_ops.py` line 30 (Python, frozenset — **IDENTICAL copy**)
- `_integrations_setup_modals.html` line 3269 (JS array — **mirrors Python**)

All three contain the same 14 pattern strings. The JS version even has a comment
saying `// Mirrors _SECRET_PATTERNS from vault_env_ops.py / secrets_ops.py`.

### 1.6 .env Template Sections (Python)

**Location**: `src/core/services/vault_env_ops.py` lines 40–122
**Lines**: ~83 lines
**Structure**: List of section definitions with key templates

```python
ENV_TEMPLATE_SECTIONS = [
    {"id": "content_vault", "name": "Content Vault", "keys": [...]},
    {"id": "github_ci", "name": "GitHub CI", "keys": [...]},
    {"id": "database", "name": "Database", "keys": [...]},
    {"id": "api_keys", "name": "API Keys", "keys": [...]},
    {"id": "app_config", "name": "App Config", "keys": [...]},
    {"id": "email", "name": "Email / SMTP", "keys": [...]},
    {"id": "cloud", "name": "Cloud / Storage", "keys": [...]},
]
```

**Consumers**: `vault_env_ops.create_env()`, `vault_env_ops.get_templates()`, web routes
**Nature**: Static (but user might want to add custom sections → extensibility)

### 1.7 Pages Builder Duplication (Python)

**FULL CODE DUPLICATION**:
- `src/core/services/pages_builders/` — The "real" location in core
- `src/ui/web/pages_builders/` — An **exact copy** in the web layer

`routes_pages_api.py` imports from the WEB copy (`src.ui.web.pages_builders`),
not from core. This is the opposite of the architecture rule.

---

## 2. Data Classification Matrix

| Dataset | Lines | Layer | Format | Static? | Extensible? | Duplicated? |
|---------|------:|-------|--------|:-------:|:-----------:|:-----------:|
| Infra services | 517 | JS only | JS object | ✅ | Should be | ❌ |
| Docker defaults | 95 | JS only | JS object | ✅ | Should be | ❌ |
| K8s StorageClasses | 27 | JS only | JS object | ✅ | Should be | ❌ |
| K8s resource kinds | 1 | JS only | JS array | ✅ | No | ❌ |
| Secret patterns | 5 | Core+JS | frozenset/array | ✅ | No | **3 copies** |
| .env templates | 83 | Python | list[dict] | ✅ | Should be | ❌ |
| Pages builders | ~865 | Python | Python code | N/A | N/A | **Full copy** |

**Total static data embedded in JS**: ~640 lines
**Total duplicated code**: ~870 lines (pages builders) + ~10 lines (secret patterns)

---

## 3. Architecture Decision: Where Should Data Live?

### The principle (from your vision)

> CLI is core. Core is CLI. TUI is on top. Web is over more on top.
> Everything has to use the core.

This means: **data catalogs are core infrastructure**. They should be:
1. Defined in `src/core/data/` as JSON files (human-editable, tooling-friendly)
2. Loaded by Python at startup (once)
3. Served to JS via Jinja template injection (once, at page render)
4. Available to CLI for any future catalog-browsing commands
5. Extensible via user-provided additions (base + custom merge)

### 3.1 New directory structure

```
src/core/data/
├── __init__.py              # DataRegistry class
├── catalogs/
│   ├── infra_services.json  # The 60+ services (517 lines → JSON)
│   ├── docker_defaults.json # Stack-specific Dockerfile defaults (95 lines → JSON)
│   ├── storage_classes.json # K8s StorageClass catalog (27 lines → JSON)
│   └── k8s_kinds.json       # Resource kind list (1 line → JSON)
├── patterns/
│   └── secret_patterns.json # Single source of truth (14 patterns)
└── templates/
    └── env_sections.json    # .env template sections (83 lines → JSON)
```

### 3.2 Why JSON, not Python dicts?

1. **Human-editable** — users can eventually edit via Content Vault file preview
2. **Format-agnostic approach** — later we can accept CSV, YAML additions
3. **Tooling** — linters, validators, schema generators can work with JSON
4. **Layer-independent** — same JSON consumed by Python (core) and injected into JS (web)
5. **Extensibility** — base JSON + user overrides naturally merge as `{**base, **user}`

### 3.3 The DataRegistry pattern

```python
# src/core/data/__init__.py

class DataRegistry:
    """Central registry for static data catalogs.
    
    Loads base catalogs from src/core/data/catalogs/ at startup.
    Optionally merges user-provided additions from project-local
    .controlplane/data/ directory.
    
    Data is loaded once and cached for the process lifetime.
    Subsequent calls return the cached version.
    """
    
    def __init__(self, project_root: Path | None = None):
        ...
    
    @cached_property
    def infra_services(self) -> list[dict]: ...
    
    @cached_property  
    def docker_defaults(self) -> dict[str, dict]: ...
    
    @cached_property
    def storage_classes(self) -> list[dict]: ...
    
    @cached_property
    def k8s_kinds(self) -> list[str]: ...
    
    @cached_property
    def secret_patterns(self) -> frozenset[str]: ...
    
    @cached_property
    def env_templates(self) -> list[dict]: ...
    
    def to_js_dict(self) -> dict:
        """Return all catalogs as a JSON-serializable dict for Jinja injection."""
        return {
            "infraOptions": self.infra_services,
            "infraCategories": self.infra_categories,
            "dockerDefaults": self.docker_defaults,
            "storageClasses": self.storage_classes,
            "k8sKinds": self.k8s_kinds,
        }
```

### 3.4 How data flows through layers

```
  JSON files (src/core/data/catalogs/*.json)
        │
        ▼
  DataRegistry (Python, at process startup)
        │
        ├──► CLI commands (e.g. `controlplane catalog list infra`)
        │
        ├──► TUI menu (future: browse catalogs)
        │
        ├──► Core services (vault_env_ops reads secret_patterns from registry)
        │
        └──► Web layer (Jinja injection into dashboard.html)
                │
                ▼
        window._dcp = {{ data_registry.to_js_dict() | tojson }};
                │
                ▼
        JS code reads window._dcp.infraOptions instead of inline const
```

### 3.5 User extensibility model

Users can create project-local overrides:

```
.controlplane/data/
├── infra_services.json      # Additional services (merged with base)
├── docker_defaults.json     # Additional/override stack defaults
└── storage_classes.json     # Additional StorageClass definitions
```

**Merge strategy**: Deep merge. User additions are appended to arrays,
user objects override matching keys in dicts.

**Format acceptance**: Phase 1 = JSON only. Phase 2 = CSV support where
it makes sense (e.g. a CSV of custom infra services).

**Restart required?**: Yes — catalogs are loaded at startup. If a user
edits a catalog file via the Content Vault editor, they need to restart
the server. The UI can display a "Restart required" toast.

**Fallback**: If a user-provided file is malformed (bad JSON), the system
falls back to the base catalog and logs a warning.

---

## 4. Implementation Plan (Phased)

### Phase 2A: Create the Data Layer (~0.5 day)

**Files created**:

| File | Lines | Content |
|------|------:|---------|
| `src/core/data/__init__.py` | ~120 | `DataRegistry` class |
| `src/core/data/catalogs/infra_services.json` | ~400 | Extracted from JS |
| `src/core/data/catalogs/infra_categories.json` | ~12 | Category labels |
| `src/core/data/catalogs/docker_defaults.json` | ~80 | Stack family defaults |
| `src/core/data/catalogs/storage_classes.json` | ~30 | K8s SC catalog |
| `src/core/data/catalogs/k8s_kinds.json` | ~12 | Resource kind list |
| `src/core/data/patterns/secret_patterns.json` | ~16 | Secret key patterns |
| `src/core/data/templates/env_sections.json` | ~85 | .env template sections |

**Verification**: 
- Unit test: `DataRegistry` loads all catalogs, returns correct types
- Spot-check: Infra catalog entry count matches original JS (60+ entries)

### Phase 2B: Wire Python Consumers (~0.5 day)

**Changes**:

| File | Change |
|------|--------|
| `src/core/services/vault_env_ops.py` | Import `secret_patterns` and `env_templates` from `DataRegistry` instead of inline |
| `src/core/services/secrets_ops.py` | Import `secret_patterns` from `DataRegistry` — remove duplicate |
| `src/ui/web/server.py` | Initialize `DataRegistry` and store on `app.config` |

**Result**: Python code uses single source of truth. No more duplicate `_SECRET_PATTERNS`.

### Phase 2C: Wire JS Consumers via Jinja (~1 day)

**Changes**:

| File | Change |
|------|--------|
| `templates/dashboard.html` | Add `<script>window._dcp = {{ dcp_data | tojson | safe }};</script>` |
| `routes_pages.py` | Pass `dcp_data=registry.to_js_dict()` to `render_template()` |
| `_integrations_setup_modals.html` | Replace inline `_infraOptions` with `window._dcp.infraOptions` |
| `_integrations_setup_modals.html` | Replace inline `_dockerStackDefaults` with `window._dcp.dockerDefaults` |
| `_integrations_setup_modals.html` | Replace inline `_SC_CATALOG` with `window._dcp.storageClasses` |
| `_integrations_k8s.html` | Replace inline `_KW_KINDS` with `window._dcp.k8sKinds` |
| `_integrations_setup_modals.html` | Replace inline `_SECRET_PATTERNS` JS with `window._dcp.secretPatterns` |

**This is the most delicate phase** — each replacement must verify the JS
code still works after the data source changes. Variables that reference
the old `const` names must be updated.

**Note on backward compatibility**: We can ease the transition by assigning:
```javascript
// Compatibility aliases — remove after all consumers updated
const _infraOptions = window._dcp.infraOptions;
const _infraCategories = window._dcp.infraCategories;
```

### Phase 2D: Code Dedup — Pages Builders (~0.5 day)

**Changes**:

| File | Change |
|------|--------|
| `src/ui/web/pages_builders/` | **DELETE** entire directory |
| `src/ui/web/routes_pages_api.py` | Change imports from `src.ui.web.pages_builders` → `src.core.services.pages_builders` |

**Pre-check**: Verify the two directories are identical or near-identical.
If the web copy has diverged, reconcile differences first (merge into core).

---

## 5. Impact on the Monster File

After Phase 2C, `_integrations_setup_modals.html` loses:
- Lines 716–1248: `_infraOptions` + `_infraCategories` (**532 lines removed**)
- Lines 1282–1376: `_dockerStackDefaults` + `_restartPolicies` + `_platformOptions` (**95 lines removed**)
- Lines 3646–3672: `_SC_CATALOG` (**27 lines removed**)
- Lines 3269–3273: `_SECRET_PATTERNS` (**5 lines removed**)

**Total reduction**: ~659 lines from the 8,283-line monster → 7,624 lines.

This is the **prerequisite** for Path 3 (Monster File Split), which becomes
significantly easier when the file is ~7,600 lines instead of ~8,300.

---

## 6. Testing Strategy

### Automated

```bash
# DataRegistry unit test
python -m pytest tests/test_data_registry.py -v

# Verify catalog integrity
python -c "
from src.core.data import DataRegistry
r = DataRegistry()
assert len(r.infra_services) >= 60, f'Expected 60+ infra services, got {len(r.infra_services)}'
assert len(r.docker_defaults) >= 10, f'Expected 10+ docker defaults, got {len(r.docker_defaults)}'
assert len(r.storage_classes) >= 5, f'Expected 5+ SC groups, got {len(r.storage_classes)}'
assert len(r.secret_patterns) == 14, f'Expected 14 patterns, got {len(r.secret_patterns)}'
print('✅ All catalogs loaded correctly')
"
```

### Manual (Web UI)

1. Open Integrations → Docker Setup Wizard → verify infra services dropdown still works
2. Open Integrations → K8s Setup Wizard → verify StorageClass dropdown still works
3. Open Secrets → Create .env → verify template sections load correctly
4. Open Integrations → K8s Manifest Wizard → verify Kind dropdown works

### Regression guards

- Before removing inline JS data, add compatibility aliases
- Test each wizard individually before removing the alias
- Final cleanup: remove aliases after all wizards verified

---

## 7. What This Enables for Later Paths

| Path | How data extraction helps |
|------|---------------------------|
| **Path 3 (Monster split)** | 659 fewer lines to deal with. Clean split boundaries. |
| **Path 7 (Caching)** | `DataRegistry` provides the "things to cache on window" concept. Extend with runtime data. |
| **UI extensibility** | Users can add custom infra services without touching code. |
| **CLI catalog commands** | `controlplane catalog list infra` becomes trivial with DataRegistry. |
| **TUI browsing** | TUI can display and search catalogs using the same data. |

---

## 8. Open Questions

1. **Name for the global JS variable**: `window._dcp` (DevOps Control Plane)?
   Or `window._controlplane`? Or `window._catalogs`?

2. **User override directory**: `.controlplane/data/` or `.state/data/` or
   `data/` at project root? `.controlplane/` fits the project config pattern
   but doesn't exist yet. `.state/` exists but is for runtime state.

3. **Should we create a `controlplane catalog` CLI group now** (as part of
   this path) or defer to a later path? Creating the data layer NOW means
   the CLI group is trivial to add later, but doing it now validates the
   data layer from all three channels.

4. **The `_restartPolicies` and `_platformOptions`**: These are tiny static
   lists (4 items each) that are only used in the Docker wizard. Extract to
   JSON for consistency, or leave inline? My recommendation: extract for
   consistency — they're still "data, not logic."

---

## 9. Files Touched Summary

### Created

| File | Lines |
|------|------:|
| `src/core/data/__init__.py` | ~120 |
| `src/core/data/catalogs/infra_services.json` | ~400 |
| `src/core/data/catalogs/infra_categories.json` | ~12 |
| `src/core/data/catalogs/docker_defaults.json` | ~80 |
| `src/core/data/catalogs/storage_classes.json` | ~30 |
| `src/core/data/catalogs/k8s_kinds.json` | ~12 |
| `src/core/data/patterns/secret_patterns.json` | ~16 |
| `src/core/data/templates/env_sections.json` | ~85 |

### Modified

| File | Change scope |
|------|-------------|
| `vault_env_ops.py` | Remove inline `ENV_TEMPLATE_SECTIONS`, import from registry |
| `secrets_ops.py` | Remove duplicate `_SECRET_PATTERNS`, import from registry |
| `server.py` | Initialize `DataRegistry`, pass to Jinja context |
| `routes_pages.py` | Pass `dcp_data` to `render_template()` |
| `dashboard.html` | Add `<script>window._dcp = ...;</script>` before other scripts |
| `_integrations_setup_modals.html` | Remove ~659 lines of inline data |
| `_integrations_k8s.html` | Remove 1 line of inline data |
| `routes_pages_api.py` | Fix imports to use core pages_builders |

### Deleted

| File/Dir | Size |
|----------|-----:|
| `src/ui/web/pages_builders/` | ~865 lines (entire duplicate directory) |
