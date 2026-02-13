# 🔬 Project Audit — Analysis & Implementation Plan

> **Status:** Analysis document — for discussion.
> **Goal:** Define what we're building, what we already have, what's missing, and how to execute.

---

## 1. What We're Actually Building

Not just "cards with data." A **full-spectrum development intelligence system** that:

1. **Detects everything** — languages, libraries, tools, infrastructure, services
2. **Classifies at the service level** — not "ioredis" but "Redis client"; not "psycopg2" but "PostgreSQL driver"
3. **Understands usage** — where is each library imported? Which functions call it? How exposed is a module?
4. **Diagnoses health** — dangerous recursion, coupling hotspots, spaghetti code, loop-of-loops
5. **Assesses quality** — headers, comments, naming, patterns, consistency
6. **Audits infrastructure** — Docker live vs file, K8s live vs manifest, env sync
7. **Identifies risks** — deprecated modules, known vulnerabilities, outdated deps
8. **Scores holistically** — Complexity (1-10) and Quality (1-10) with transparent breakdowns
9. **Offers remediation** — "this tool is missing, install it?", "repo too heavy, optimize?"

### The UX Contract

- **Auto-load what's cheap.** Lazy-load what's heavy. Progress bars for anything > 2s.
- **Buttons and modals, not walls of text.** Progressive disclosure at every level.
- **Card → Modal → Full Detail → Action.** Every dimension follows this.
- **"What do you want to dig into?"** The base scan presents options; the user chooses depth.

---

## 2. What Already Exists (Complete Inventory)

### 2.1 — Existing `*_ops.py` Services (16 services, ~10k LOC)

These are the **already-built engines** we can directly feed from:

| Service | Key Functions | Audit Feed |
|---------|--------------|------------|
| `package_ops.py` | `package_status()`, `package_list()`, `package_outdated()`, `package_audit()` | Dep inventory, outdated, vulnerabilities |
| `quality_ops.py` | `quality_status()`, `quality_run()` | Lint/format/type-check detection & execution |
| `testing_ops.py` | `testing_status()`, `test_inventory()`, `test_coverage()`, `run_tests()` | Test framework detection, coverage, test inventory |
| `security_ops.py` | `scan_secrets()`, `detect_sensitive_files()`, `gitignore_analysis()`, `security_posture()` | Secret scanning, .gitignore gaps, posture score |
| `docs_ops.py` | `docs_status()`, `docs_coverage()`, `check_links()` | README/docs detection, coverage, broken links |
| `docker_ops.py` | `docker_status()`, `docker_containers()`, `docker_compose_status()` | Container detection, live vs file comparison |
| `k8s_ops.py` | `k8s_status()`, `validate_manifests()`, `cluster_status()`, `get_resources()` | K8s manifest detection, live cluster diff |
| `terraform_ops.py` | `terraform_status()`, `terraform_validate()`, `terraform_state()` | Terraform detection, state, validation |
| `env_ops.py` | `env_status()`, `env_diff()`, `env_validate()`, `iac_status()` | Env file detection, cross-env diff, IaC detection |
| `git_ops.py` | `git_status()`, `git_log()`, `gh_status()`, `gh_actions_runs()` | Repo status, history, CI status |
| `ci_ops.py` | CI pipeline detection | CI/CD coverage |
| `dns_cdn_ops.py` | DNS/CDN status | External service detection |
| `metrics_ops.py` | Health metrics | System health |
| `secrets_ops.py` | Vault operations | Secret management posture |
| `vault_env_ops.py` | Vault + env integration | Secret/env sync |
| `detection.py` | `detect_modules()` | Module discovery from project.yml |

**Key insight:** ~70% of the L0/L1 data we need is **already computed by existing ops**.
The audit engine shouldn't recompute — it should **aggregate and enrich**.

### 2.2 — New Audit Engine (built so far)

| File | Lines | What It Does | Status |
|------|-------|-------------|--------|
| `l0_detection.py` | 231 | OS, Python, venv, 26 tools, modules, manifests | ✅ Working |
| `l1_classification.py` | 601 | 8 manifest parsers, catalog lookup, framework/ORM/client ID, crossovers | ✅ Working |
| `catalog.py` | 378 | ~300 library entries across Python/Node/Go/Rust | ✅ Working |
| `scoring.py` | 212 | Complexity + Quality scores (L0+L1 only) | ✅ Working |
| `routes_audit.py` | 98 | 5 API endpoints | ✅ Working |

### 2.3 — Web UI (built but premature)

| File | Status |
|------|--------|
| `_tab_audit.html` | Created, needs redesign |
| `_audit.html` (script) | Created, needs redesign |
| CSS additions in `admin.css` | Added `.kv-grid`, `.mini-table`, `.tag` utilities |
| Nav + tab routing | Wired up |

---

## 3. Analysis Dimensions (The Full Scope)

The audit covers **10 distinct dimensions**, each with its own depth and execution model.

### Dimension Map

```
 AUTO-LOAD (< 500ms)                    ON-DEMAND (1-30s)
 ═══════════════════                    ═════════════════
                                        
 ┌──────────────┐  ┌──────────────┐    ┌──────────────┐  ┌──────────────┐
 │ D1. System   │  │ D2. Deps &   │    │ D5. Code     │  │ D6. Coupling │
 │    Profile   │  │    Libraries │    │    Quality   │  │  & Patterns  │
 └──────────────┘  └──────────────┘    └──────────────┘  └──────────────┘
                                        
 ┌──────────────┐  ┌──────────────┐    ┌──────────────┐  ┌──────────────┐
 │ D3. Solution │  │ D4. Services │    │ D7. Repo &   │  │ D8. IaC      │
 │    Structure │  │    & Clients │    │    Git       │  │    Diff      │
 └──────────────┘  └──────────────┘    └──────────────┘  └──────────────┘
                                        
                                       ┌──────────────┐  ┌──────────────┐
                                       │ D9. Risks &  │  │ D10. Env &   │
                                       │    Vulns     │  │    Secrets   │
                                       └──────────────┘  └──────────────┘
```

### D1 — System Profile (auto-load, <200ms)

**What:** OS, runtime, venv, available tools, project root identity.
**Source:** `l0_detection.py` (already built)
**Existing ops reuse:** `detection.py` (modules)
**Missing from current impl:** Nothing major, L0 is solid.

### D2 — Dependencies & Libraries (auto-load, <500ms)

**What:** Full library inventory. Every dependency classified at the **service level**.
- Not "boto3" → a library called boto3.
- But "boto3" → **AWS SDK** (cloud-aws) in Python ecosystem.
- And "ioredis" → **Redis client** (cache/store) in Node ecosystem.
- And "ioredis" + "redis" in Python → **Crossover: Redis** detected across 2 ecosystems.

**Source:** `l1_classification.py` + `catalog.py` (already built)
**Existing ops reuse:** `package_ops.package_status()` (manager detection), `package_ops.package_list()` (installed packages)
**Drill-down (modal):**
- Click a library → **Library Detail Modal**: version, category, ecosystem, all import sites (needs L2), related plugins
- Click a framework → **Framework Detail Modal**: which features are used
- Click a crossover → shows the two (or more) libraries that serve the same logical service

**Missing from current impl:**
- Library detail endpoint (`/audit/library/<name>`) — needs L2 data
- Framework feature detection (e.g. "Flask uses Blueprints ✅, Jinja2 ✅, SQLAlchemy ❌")
- Service-level display in UI (group by logical service, not package name)

### D3 — Solution Structure (auto-load, <500ms)

**What:** What kind of project is this? What components exist?
- Solution type: "Multi-component Python web app with CLI"
- Components: CLI, Web, Docs, Tests, Docker, IaC
- Entrypoints: manage.sh, flask app, click CLI
- Module boundaries: what's in each module, file counts

**Source:** `l1_classification.py:l1_structure()` (already built)
**Existing ops reuse:** `detection.py` (module discovery)
**Drill-down:**
- Click a module → **Module Detail Modal**: public symbols, internal structure, dependencies
- "What does this module expose?" → exposure ratio (needs L2)
- "Who calls this module?" → caller map (needs L2)

**Missing from current impl:**
- Module detail endpoint
- Per-module sub-module breakdown
- Exposure ratio calculation

### D4 — Services & Clients (auto-load, <500ms)

**What:** External service clients detected across the entire solution.
- Not "import redis" → but **"This project connects to Redis, PostgreSQL, and AWS S3"**
- Grouped by service type: cache, database, queue, cloud, payment, email…
- Crossover view: "Redis is accessed from both Python and Node modules"

**Source:** `l1_classification.py:l1_clients()` (already built)
**Drill-down:**
- Click a service → which library, which files import it (needs L2)
- "Where is the Redis client used?" → all call sites

**Missing from current impl:**
- Usage site mapping (needs L2)
- Service-level grouping in UI (partially there)

### D5 — Code Quality (on-demand, 2-10s)

**What:** How clean is the code? Multiple sub-dimensions:
- **Header coverage**: do files have module docstrings?
- **Comment ratio**: comments per LOC
- **Docstring coverage**: what % of functions/classes have docstrings?
- **Variable naming**: consistent conventions? single-letter vars?
- **Function length**: average, max, hotspots over N lines
- **Nesting depth**: max nesting levels
- **Spaghetti detection**: files with too many imports, too-long functions, deep nesting
- **Tree vs spaghetti**: does the call graph form a clean tree or a tangled web?

**Source:** New `l2_quality.py` — Python `ast` module for Python, regex heuristics for others
**Existing ops reuse:** `quality_ops.quality_status()` (tool detection), `quality_ops.quality_run()` (lint results)
**Execution model:** On-demand. Button says "Analyze Code Quality" → progress bar → results.

### D6 — Coupling & Patterns (on-demand, 5-30s)

**What:** How healthy is the architecture?
- **Import graph**: who imports who? Internal cross-module dependencies
- **Coupling score**: fan-in/fan-out per module
- **Circular dependency detection**: Tarjan's SCC on the import graph
- **Dangerous recursion**: recursive calls, bounded vs unbounded
- **Loop-of-loops**: nested recursion patterns, why they're dangerous
- **Decoupling assessment**: "A does XYZ, B does XYZ — do they interact? share a caller?"
- **Common ancestors**: which modules serve as shared foundations?
- **Pattern consistency**: naming conventions, import styles, file organization across modules
- **Spread vs consistency**: how uniform is tool/pattern usage?

**Source:** New `l2_structure.py` (AST import graph) + `l3_coupling.py` (deep analysis)
**Execution model:** On-demand. This is the heaviest analysis. Progress stages:
  1. "Building import graph..." (parse all files)
  2. "Analyzing coupling..." (compute scores)
  3. "Detecting cycles..." (Tarjan's SCC)
  4. "Done." (render results)

### D7 — Repository & Git (on-demand, 2-5s)

**What:** How healthy is the repository itself?
- **Repo weight**: `git count-objects -v`, total size
- **History weight**: how many commits? how old? how large is `.git`?
- **Large files**: binary blobs, files over N MB
- **Branch hygiene**: stale branches, merged but not deleted
- **Optimization offers**: "Run git-filter-repo to flatten?" → tool missing? offer install!

**Source:** New `l2_repo.py` + existing `git_ops.py`
**Existing ops reuse:** `git_ops.git_status()`, `git_ops.git_log()`
**Remediation:** Active tool installation offers (git-filter-repo, BFG)

### D8 — IaC Differential (on-demand, 5-15s)

**What:** Is the live infrastructure in sync with the declared manifests?
- **Docker**: running containers vs docker-compose.yml services. Image versions match?
- **Kubernetes**: live cluster state vs manifest files. Missing resources? Extra resources? Config drift?
- **Terraform**: `terraform state` vs `.tf` files. Drift detection.
- **Per-environment**: staging vs production manifests differ how?

**Source:** New `l2_iac_diff.py` + existing ops
**Existing ops reuse:**
- `docker_ops.docker_status()` + `docker_ops.docker_compose_status()` (live state)
- `k8s_ops.k8s_status()` + `k8s_ops.cluster_status()` + `k8s_ops.get_resources()` (live vs file)
- `terraform_ops.terraform_status()` + `terraform_ops.terraform_state()` (declared vs state)
**Execution model:** On-demand. Requires live infrastructure connections. May fail gracefully if kubectl/docker unavailable.

### D9 — Risks & Vulnerabilities (on-demand, 5-15s)

**What:** What's dangerous in this project?
- **Deprecated modules**: outdated packages with known replacements
- **Known vulnerabilities**: CVEs from `pip-audit`, `npm audit`, etc.
- **Multi-tool scanning**: use multiple tools for full perspective ("pip-audit finds X, safety finds Y")
- **Hardcoded secrets**: from `security_ops.scan_secrets()`
- **Missing .gitignore patterns**: from `security_ops.gitignore_analysis()`
- **Sensitive files tracked**: from `security_ops.detect_sensitive_files()`
- **Dead code**: symbols defined but never imported/called (needs L2 import graph)

**Source:** New `l2_risk.py` + existing ops
**Existing ops reuse:**
- `security_ops.scan_secrets()`, `security_ops.detect_sensitive_files()`, `security_ops.gitignore_analysis()`
- `package_ops.package_audit()` (pip-audit, npm audit, cargo audit)
- `package_ops.package_outdated()` (outdated packages)

### D10 — Environment & Secrets Sync (on-demand, 1-3s)

**What:** Are environments in sync? Per-env vs single-env?
- **Env diff**: `.env` vs `.env.example` — missing keys?
- **Cross-env diff**: `.env.staging` vs `.env.production` — what differs?
- **Secret sync**: are vault secrets in sync with env files?
- **Variable categorization**: which vars are secrets? which are config?

**Source:** New `l2_env_sync.py` + existing ops
**Existing ops reuse:**
- `env_ops.env_status()`, `env_ops.env_diff()`, `env_ops.env_validate()`
- `vault_env_ops.vault_env_sync()` if vault is configured

---

## 4. Execution Model & Layer Architecture

### 4.1 — Revised Layer Model

The original doc had L0-L3 layers defined by compute cost. That's still valid, but the key evolution is:

```
L0 — DETECTION       (<200ms)    File existence, tool availability, manifests
     │                            → System Profile, raw manifest list
     │
L1 — CLASSIFICATION  (<500ms)    Parse manifests, catalog lookup, identify
     │                            → Libraries, frameworks, ORMs, clients, crossovers
     │                            → Solution type, components, entrypoints
     │
L2 — CODE ANALYSIS   (1-15s)     AST parsing, import graphs, metrics
     │                            → Code quality, import map, exposure, usage sites
     │                            → IaC diff, repo health, env sync, risks
     │
L3 — DEEP ANALYSIS   (5-30s)     Cross-module reasoning, pattern detection
                                  → Coupling scores, cycle detection, recursion analysis
                                  → Dead code, spaghetti detection, consistency
```

**Key rules:**
1. L0+L1 = auto-load. Always runs. Always fast.
2. L2 = on-demand per dimension. User triggers each.
3. L3 = on-demand, may combine multiple L2 results.
4. Every layer produces a structured dict.
5. Every dict is cached via `devops_cache` with mtime invalidation.
6. Higher layers can accept pre-computed lower layer results to avoid redundant work.

### 4.2 — Function Signature Pattern

Every analysis function follows:

```python
def l<N>_<dimension>(
    project_root: Path,
    *,
    # Optional pre-computed lower layer results
    l0: dict | None = None,
    l1_deps: dict | None = None,
    # Optional scope limiting
    modules: list[str] | None = None,  # Only analyze these modules
) -> dict:
    """Docstring with full return type documentation."""
    ...
```

### 4.3 — Aggregation vs Recomputation

**Critical design decision:** The audit should NOT recompute what `*_ops.py` already does.

Instead, L2/L3 functions should **call existing ops and aggregate**:

```python
# Bad: reimplement docker detection
def l2_iac_diff(root):
    # Don't do: manually parse docker-compose.yml again
    pass

# Good: call existing ops and compare
def l2_iac_diff(root):
    declared = docker_ops.docker_status(root)      # What's declared in files
    live = docker_ops.docker_compose_status(root)   # What's running
    return _compare(declared, live)                  # Diff them
```

---

## 5. Data Model

### 5.1 — Result Envelope

Every analysis result wraps in a consistent envelope:

```python
{
    "_meta": {
        "layer": "L1",
        "dimension": "dependencies",
        "computed_at": 1707744000.0,
        "duration_ms": 234,
        "scope": "full",  # or "module:src/core"
    },
    # ... dimension-specific data
}
```

### 5.2 — Library Model (service-level thinking)

```python
{
    "name": "boto3",                    # Package name
    "version": "1.34.0",
    "dev": false,
    "ecosystem": "python",
    "source_file": "pyproject.toml",
    "classification": {
        "category": "client",           # framework | orm | client | ...
        "type": "cloud-aws",            # web | relational | cache | ...
        "service": "AWS",               # Logical service identity
        "description": "AWS SDK"
    }
}
```

The `service` field is the key innovation — it enables crossover detection and service-level grouping.

### 5.3 — Module Detail Model (for drill-down)

```python
{
    "name": "src/ui/web",
    "stack": "python",
    "file_count": 35,
    "line_count": 12400,
    "public_symbols": 48,
    "total_symbols": 312,
    "exposure_ratio": 0.154,            # 15.4% exposed
    "imports_from": ["src.core.services", "src.core.models", "src.core.config"],
    "imported_by": ["src.ui.cli"],
    "external_deps": ["flask", "jinja2"],
    "entrypoints": [
        {"type": "wsgi", "path": "src/ui/web/server.py", "description": "Flask app"}
    ]
}
```

---

## 6. UI/UX Architecture

### 6.1 — The Audit Tab Layout

The tab has **two modes**:

**Mode 1: Overview (default)**
Shows the auto-loaded cards (D1-D4) + score banner + on-demand buttons (D5-D10).

**Mode 2: Drill-Down**
Modals and inline expansions for deep analysis results.

### 6.2 — Card Anatomy

```
┌─────────────────────────────────────────────┐
│ 📦 Dependencies & Libraries         🔄  2m  │  ← title, refresh, cache age
├─────────────────────────────────────────────┤
│                                             │
│  23 dependencies across 2 ecosystems        │  ← summary line
│                                             │
│  Frameworks: Flask, Jinja2                  │  ← key findings (badges)
│  ORMs: SQLAlchemy                           │
│  Clients: Redis, PostgreSQL                 │
│  Crossovers: 1 (Redis: py + node)           │
│                                             │
│  [ View All Libraries ]  [ View Crossovers ]│  ← action buttons → modals
│                                             │
└─────────────────────────────────────────────┘
```

### 6.3 — On-Demand Card Anatomy

```
┌─────────────────────────────────────────────┐
│ 📊 Code Quality                             │
├─────────────────────────────────────────────┤
│                                             │
│  This analysis examines code health across  │
│  all modules: docstrings, naming, nesting,  │
│  function length, and spaghetti patterns.   │
│                                             │
│  ⏱️ Estimated: 3–8 seconds                   │
│                                             │
│  [ ▶ Run Code Quality Analysis ]            │  ← button triggers L2
│                                             │
│  ┌─ Progress ─────────────────────────────┐ │  ← appears during run
│  │ ████████░░░░░░ Analyzing src/core...   │ │
│  └────────────────────────────────────────┘ │
│                                             │
└─────────────────────────────────────────────┘
```

### 6.4 — Modal Drill-Down Pattern

Every "View Details" or "View All" button opens a modal:

```
┌────────────────────────────────────────────────────────────┐
│  📦 Library: flask — Web Framework                   [ ✕ ] │
│─────────────────────────────────────────────────────────────│
│                                                            │
│  Version: 3.1.0          Category: framework               │
│  Ecosystem: Python       Type: web                         │
│  Service: Flask App      Installed: ✅                      │
│                                                            │
│  ─── Used In ──────────────────────────────────────────    │
│  • src/ui/web/server.py:8      from flask import Flask     │
│  • src/ui/web/routes_api.py:3  from flask import ...       │
│  • ... (10 more)                          [ Show All ▾ ]   │
│                                                            │
│  ─── Framework Features ───────────────────────────────    │
│  Blueprint ✅  Jinja2 ✅  Session ❌  SQLAlchemy ❌          │
│                                                            │
│  ─── Related ──────────────────────────────────────────    │
│  • flask-cors (not installed)                              │
│  • flask-login (not installed)                             │
│                                                            │
│  [ View All Import Sites ]  [ View Call Map ]              │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 6.5 — Interpolated Depth

The key UX principle: **right amount of detail at each level**.

| Level | Shows | Interaction |
|-------|-------|-------------|
| Card | 1-3 line summary + badges | Visible immediately |
| Card expanded | Key metrics + highlights | Click card or "details" |
| Modal | Full data table + categories | Click "View All" button |
| Deep modal | Per-item detail + code links | Click row in modal |
| Action | "Install this tool" / "Fix this" | Click action button |

---

## 7. Route Architecture

### 7.1 — Auto-Load Endpoints (L0+L1)

```
GET /api/audit/system           → D1: system profile
GET /api/audit/dependencies     → D2: library inventory + classification
GET /api/audit/structure        → D3: solution structure + components
GET /api/audit/clients          → D4: service client inventory
GET /api/audit/scores           → Master complexity + quality scores
```

### 7.2 — On-Demand Endpoints (L2+L3)

```
GET /api/audit/quality          → D5: code quality analysis
GET /api/audit/coupling         → D6: coupling + patterns + recursion
GET /api/audit/repo             → D7: repo health + git analysis
GET /api/audit/iac-diff         → D8: IaC live vs declared
GET /api/audit/risks            → D9: vulnerabilities + deprecated + dead code
GET /api/audit/env-sync         → D10: env + secrets sync
```

### 7.3 — Drill-Down Endpoints

```
GET /api/audit/library/<name>   → Library detail (imports, features, related)
GET /api/audit/module/<path>    → Module detail (symbols, exposure, callers)
GET /api/audit/imports/<path>   → Import graph for a module
GET /api/audit/usage/<library>  → All usage sites for a library
```

### 7.4 — Action Endpoints

```
POST /api/audit/install-tool    → Install a missing tool (e.g., git-filter-repo)
POST /api/audit/run-scan        → Re-run a specific scan dimension
```

---

## 8. File Organization (Target)

```
src/core/services/audit/
├── __init__.py                  # Public API: all layer functions
├── models.py                    # TypedDict / type definitions for all results
├── catalog.py                   # Library knowledge base (~300+ entries)    ✅ exists
│
├── l0_detection.py              # L0: system, tools, modules, manifests    ✅ exists
├── l1_classification.py         # L1: dep parsing, classification          ✅ exists
├── l1_structure.py              # L1: solution type, components            (move from l1_classification)
│
├── l2_quality.py                # L2: code health metrics (AST-based)
├── l2_structure.py              # L2: import graph, exposure, symbol table
├── l2_repo.py                   # L2: git repo health, large files
├── l2_iac_diff.py               # L2: IaC live vs declared
├── l2_risk.py                   # L2: vulnerabilities, deprecated, secrets
├── l2_env_sync.py               # L2: environment + secrets sync
│
├── l3_coupling.py               # L3: coupling scores, cycles, recursion
├── l3_patterns.py               # L3: consistency, spaghetti, spread
│
├── scoring.py                   # Complexity + Quality computation         ✅ exists
│
└── parsers/                     # Language-specific source parsers
    ├── __init__.py
    ├── python_ast.py            # Python: full ast module analysis
    ├── js_regex.py              # JS/TS: regex-based import/export parsing
    ├── go_regex.py              # Go: regex-based import parsing
    └── generic.py               # Fallback: generic import/require patterns
```

---

## 9. Implementation Phases

### Phase 1 — Foundation Consolidation

**Goal:** Make L0+L1 rock-solid. Fix what's built. Establish patterns.

**Tasks:**
1. Create `models.py` with proper TypedDicts for all result shapes
2. Add `_meta` envelope to all analysis results (layer, dimension, timing)
3. Enhance `catalog.py` with `service` field for every entry (logical service identity)
4. Add module-level manifest parsing (currently only root-level)
5. Review and test all 5 existing endpoints end-to-end
6. Ensure existing ops are called (not recomputed) where overlap exists

**Outcome:** Stable, tested, well-typed L0+L1 backend.

### Phase 2 — L2 Core (Import Graph + Code Quality)

**Goal:** AST analysis foundation that powers multiple dimensions.

**Tasks:**
1. Build `parsers/python_ast.py` — extract imports, functions, classes, docstrings per file
2. Build `parsers/js_regex.py` — extract imports/exports via regex
3. Build `l2_structure.py` — import graph, module boundary map, exposure ratio
4. Build `l2_quality.py` — comment ratio, docstring coverage, function metrics, naming
5. Create drill-down endpoints: `/audit/library/<name>`, `/audit/module/<path>`
6. Wire up on-demand route for code quality

**Outcome:** "Where is this library used?" works. Code quality scores are real.

### Phase 3 — L2 Ops Integration (IaC, Repo, Risk, Env)

**Goal:** Aggregate existing ops into audit dimensions.

**Tasks:**
1. Build `l2_iac_diff.py` — aggregate docker_ops + k8s_ops + terraform_ops
2. Build `l2_repo.py` — aggregate git_ops + `git count-objects` + large file detection
3. Build `l2_risk.py` — aggregate security_ops + package_ops audits
4. Build `l2_env_sync.py` — aggregate env_ops + vault_env_ops
5. Wire up all on-demand routes
6. Add remediation actions (install tool, run fix)

**Outcome:** Full L2 coverage across all 10 dimensions.

### Phase 4 — L3 Deep Analysis

**Goal:** The heavy-but-powerful architectural insights.

**Tasks:**
1. Build `l3_coupling.py` — Tarjan's SCC (cycles), fan-in/fan-out, coupling scores
2. Build `l3_patterns.py` — consistency scoring, spaghetti detection, recursion analysis
3. Enhance scoring.py to incorporate L2+L3 data
4. Progress indicator support for long-running analyses
5. "Dangerous recursion" detection with health classification

**Outcome:** Full architectural intelligence.

### Phase 5 — Audit Tab UI

**Goal:** Only now do we build the UI, with full understanding of the data.

**Tasks:**
1. Design card layouts for all 10 dimensions
2. Build modal system for drill-downs
3. Auto-load cards for D1-D4
4. On-demand cards with progress for D5-D10
5. Score banner with animated breakdowns
6. Navigation shortcuts between dimensions
7. Action buttons for remediation

**Outcome:** Complete Audit tab.

---

## 10. Open Questions (For Discussion)

1. **Phase priority:** Should we do Phase 2 (AST/import graph) or Phase 3 (ops aggregation) first?
   Phase 2 is harder but unlocks drill-downs. Phase 3 is easier but gives breadth.

2. **Module scope:** L1 currently parses root-level manifests only. Should sub-module manifest
   parsing be Phase 1 or Phase 2?

3. **Catalog service field:** Adding `service: "Redis"` to every catalog entry means editing
   ~300 entries. Automate from `type` field, or curate manually?

4. **Python AST depth:** How deep should `python_ast.py` go?
   - Just imports? (fast, sufficient for import graph)
   - Imports + function/class signatures? (medium, enables exposure ratio)
   - Full call graph? (slow, enables "who calls this?")

5. **IaC diff live connections:** Docker status is local and fast. K8s cluster status requires
   kubectl config + network. Terraform state requires init. How do we handle failures gracefully?

6. **Tool installation:** "This tool is missing, install it?" — should the audit actually
   `pip install` / `npm install` things, or just show the command?

7. **Score history:** Track scores over time in `.state/audit_scores.json`? Enables trend arrows.

8. **UI before or after Phase 4?** The plan says Phase 5 = UI. But you might want to see
   results earlier. Should we interleave basic UI as we go?
