# 🔬 Project Audit — Architecture & Implementation Plan

> **Status:** Design document — for review and discussion before implementation.
> **Scope:** New "Audit" tab in the Web Admin panel, plus the backend analysis engine.

---

## 1. Vision

A multi-layered project intelligence system that gives developers
**x-ray vision** into their codebase. From "what libraries do I use?" to
"where are my coupling hotspots?" — progressive depth, always available,
never in the way.

The Audit isn't a one-shot report. It's a **living instrument panel**
that adapts to what the project actually contains and lets users drill
into exactly the dimension they care about.

---

## 2. Design Principles

| Principle | Meaning |
|---|---|
| **Layered depth** | L0 is instant (file existence). L3 takes seconds (AST walks). Never block on what you don't need |
| **Language-agnostic where possible** | Same analysis model for Python, Node, Go, Rust. Language-specific analyzers plug into a common interface |
| **Progressive disclosure** | Card → modal → full-page detail. Don't overwhelm |
| **On-demand heavy work** | Anything > 2s is user-triggered with progress indication |
| **Composable** | Each analysis pass produces a structured dict. Passes can be combined or run independently |
| **Cacheable** | All results go through `devops_cache` with mtime-based invalidation |

---

## 3. Analysis Layer Model

The entire audit engine is built on **four computational layers**, each
building on the previous:

```
┌─────────────────────────────────────────────────────────────────┐
│  L0 — DETECTION          (< 100ms)     Files, manifests         │
│  ─────────────────────────────────────────────────────────────  │
│  L1 — CLASSIFICATION     (< 500ms)     Libraries, frameworks    │
│  ─────────────────────────────────────────────────────────────  │
│  L2 — STRUCTURE ANALYSIS (1-5s)        AST, imports, call map   │
│  ─────────────────────────────────────────────────────────────  │
│  L3 — DEEP ANALYSIS      (5-30s)       Coupling, patterns,      │
│                                        recursion, scoring       │
└─────────────────────────────────────────────────────────────────┘
```

### L0 — Detection (instant)

**What it does:** Identify what exists on disk. Zero computation.

| Analysis | Method | Output |
|---|---|---|
| Dependency manifests | Check `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `*.csproj`, `mix.exs`, `Gemfile` | List of manifest files with type |
| Config files | Check for `.env`, `Dockerfile`, `docker-compose.yml`, `k8s/`, `terraform/` | Config inventory |
| System tools | `shutil.which()` for: python, node, go, cargo, kubectl, terraform, docker, ffmpeg, gzip, etc. | Tool availability map |
| OS/Runtime | `platform.system()`, `sys.version`, check WSL | System identity |
| Project structure | Walk top 3 directory levels | File tree summary |

**Already exists (partially):** `detection.py`, `package_ops.py`, `quality_ops.py`, `testing_ops.py`

### L1 — Classification (fast)

**What it does:** Parse manifests to understand what's declared. No AST yet.

| Analysis | Method | Output |
|---|---|---|
| **Library inventory** | Parse `requirements.txt`, `pyproject.toml [dependencies]`, `package.json dependencies/devDependencies`, `Cargo.toml [dependencies]`, `go.mod require` | `[{name, version, dev, source}]` per module |
| **Library classification** | Match library names against a knowledge base (built-in dict) | `{category: framework|orm|client|utility|testing|typing|logging|...}` |
| **Framework identification** | Detect Flask, Django, FastAPI, Express, Next.js, Spring, Rails, Phoenix, etc. from dependencies + marker files | `{framework, version, features}` |
| **ORM identification** | Detect SQLAlchemy, Django ORM, Prisma, TypeORM, GORM, Diesel, Ecto, ActiveRecord | `{orm, version, backend}` |
| **Client identification** | Detect Redis, Kafka, RabbitMQ, MySQL, PostgreSQL, MongoDB, Elasticsearch, gRPC clients | `[{name, type, library}]` |
| **Crossover detection** | Same logical dependency across modules/languages (e.g. Redis client in Python module + Node module) | Crossover map |
| **VENV detection** | Check for `.venv/`, `venv/`, `Pipfile.lock`, `poetry.lock` presence and health | VENV status |

**Knowledge base:** A curated dict mapping ~500 popular library names to categories:
```python
_LIBRARY_CATALOG = {
    # Python frameworks
    "flask": {"category": "framework", "type": "web", "ecosystem": "python"},
    "django": {"category": "framework", "type": "web", "ecosystem": "python"},
    "fastapi": {"category": "framework", "type": "web", "ecosystem": "python"},
    # Python ORMs
    "sqlalchemy": {"category": "orm", "type": "relational", "ecosystem": "python"},
    "tortoise-orm": {"category": "orm", "type": "relational", "ecosystem": "python"},
    # Python clients
    "redis": {"category": "client", "type": "cache/store", "ecosystem": "python"},
    "celery": {"category": "client", "type": "task-queue", "ecosystem": "python"},
    "kafka-python": {"category": "client", "type": "message-broker", "ecosystem": "python"},
    "boto3": {"category": "client", "type": "cloud-aws", "ecosystem": "python"},
    # Node frameworks
    "express": {"category": "framework", "type": "web", "ecosystem": "node"},
    "next": {"category": "framework", "type": "web-ssr", "ecosystem": "node"},
    "nestjs": {"category": "framework", "type": "web", "ecosystem": "node"},
    # Node clients
    "ioredis": {"category": "client", "type": "cache/store", "ecosystem": "node"},
    "pg": {"category": "client", "type": "database", "ecosystem": "node"},
    "prisma": {"category": "orm", "type": "relational", "ecosystem": "node"},
    # ... hundreds more
}
```

### L2 — Structure Analysis (medium, on-demand)

**What it does:** Parse source code to understand usage patterns. Uses Python `ast` for Python files, regex-based heuristics for other languages.

| Analysis | Method | Output |
|---|---|---|
| **Import graph** | AST-walk all `.py` files → extract `import X` / `from X import Y` | Per-file import list, per-library usage sites |
| **Module boundary map** | Which functions/classes are defined in each module's `__init__.py` or exported | Public API surface per module |
| **Exposure ratio** | Count public symbols vs total symbols per module | `exposed / total` ratio |
| **Cross-module imports** | Which internal modules import from which other internal modules | Internal dependency graph |
| **Library usage sites** | For each library: every file + line where it's imported | Usage heatmap |
| **Function/class inventory** | All top-level functions and classes per file | Symbol table |
| **Entrypoint detection** | `if __name__ == '__main__'`, CLI entry points, WSGI/ASGI apps, `@app.route`, etc. | Entrypoint list |

**Technology choices:**
- **Python:** `ast` module (stdlib, fast, reliable)
- **JavaScript/TypeScript:** Regex-based import extraction (`import ... from`, `require(...)`)
- **Go:** Regex-based (`import "..."`, `import (...)`)
- **Rust:** Regex-based (`use ...`, `mod ...`)
- **Other languages:** Generic regex for `import`/`include`/`require` patterns

### L3 — Deep Analysis (heavy, user-triggered)

**What it does:** Higher-order analysis that needs the full picture from L2.

| Analysis | Method | Output |
|---|---|---|
| **Coupling score** | Fan-in / fan-out per module. Shannon entropy of import distribution | `{module: {coupling_score, fan_in, fan_out, assessment}}` |
| **Circular dependency detection** | Tarjan's SCC on the import graph | List of cycles with severity |
| **Dead code detection** | Symbols defined but never imported/called anywhere | List of unreferenced symbols |
| **Pattern consistency** | Compare naming conventions, file organization, import styles across modules | Consistency score + deviations |
| **Spaghetti detection** | Files with > N imports, functions with > N lines, deeply nested call chains | Hotspot list |
| **Recursion analysis** | Detect recursive calls, classify as healthy (bounded) or dangerous (unbounded) | Recursion report |
| **Code health metrics** | Comment ratio, docstring coverage, average function length, max nesting depth | Per-module health scorecard |
| **Repo weight analysis** | `git count-objects`, large file detection, history depth, binary blobs | Repo health + optimization suggestions |

---

## 4. Scoring Model

Two master scores, each composed of sub-scores:

### 4.1 Complexity Score (1-10)

| Dimension | Weight | What it measures |
|---|---|---|
| Tech diversity | 25% | How many languages/runtimes/frameworks coexist (1 tech = low, 4+ = high) |
| Module count | 15% | Number of distinct modules |
| Dependency count | 20% | Total declared dependencies (combined across manifests) |
| Cross-language coupling | 15% | How much cross-language interaction exists |
| Infrastructure layers | 15% | Docker + K8s + Terraform + CI = layers of orchestration |
| External integrations | 10% | Number of external service clients (Redis, Kafka, AWS, etc.) |

### 4.2 Quality Score (1-10)

| Dimension | Weight | What it measures |
|---|---|---|
| Documentation coverage | 15% | README, docstrings, CHANGELOG, API docs present |
| Test coverage | 15% | Test files exist, test-to-source ratio, coverage % if available |
| Code health | 20% | Comment ratio, function length, nesting depth, naming consistency |
| Security posture | 15% | No hardcoded secrets, .gitignore complete, dependencies audited |
| Dependency health | 10% | No known vulnerabilities, no severely outdated packages |
| Coupling score | 10% | Low circular deps, reasonable fan-out, isolated modules |
| Pattern consistency | 10% | Consistent naming, import style, file organization |
| Repo hygiene | 5% | Reasonable git history size, no binary blobs, clean branches |

---

## 5. System & Environment Audit Layer

A dedicated sub-section that characterizes the runtime environment:

```
┌────────────────────────────────────────────────────────────┐
│  🖥️ SYSTEM PROFILE                                        │
│                                                            │
│  OS: Linux Ubuntu 24.04 (WSL)                              │
│  Python: 3.12.1 (venv: ✅ active at .venv/)               │
│  Node: v20.11.0 (npm: 10.2.4)                             │
│  Go: 1.22.0                                                │
│  Docker: 24.0.7 (running)                                  │
│                                                            │
│  🔧 Available Tools                                        │
│  ✅ git  ✅ ruff  ✅ mypy  ✅ pytest  ❌ terraform          │
│  ✅ docker  ❌ kubectl  ✅ ffmpeg  ✅ gzip  ❌ cargo         │
│                                                            │
│  📦 Solution Contains                                      │
│  → src/core       python-lib     Domain models & services  │
│  → src/adapters   python-lib     Tool bindings             │
│  → src/ui/cli     python-cli     Click CLI ▸ 12 commands   │
│  → src/ui/web     python-flask   Web admin  ▸ 18 routes    │
│  → docs           markdown       Documentation             │
└────────────────────────────────────────────────────────────┘
```

---

## 6. UI Architecture

### 6.1 Tab Structure

**New tab: `🔬 Audit`** in the Web Admin panel.

Top-level layout:

```
┌─────────────────────────────────────────────────────────────┐
│  🔬 Audit                    [⚙️ Prefs]  [🔄 Refresh All]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─── Master Scores ──────────────────────────────────── ┐  │
│  │ Complexity: 4.2/10 ████░░░░░░   Quality: 7.1/10 ███████░│
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ 🖥️ System   │  │ 📦 Deps     │  │ 🏗️ Structure│         │
│  │ Profile     │  │ & Libraries │  │ & Modules   │         │
│  │             │  │             │  │             │         │
│  │ [auto-load] │  │ [auto-load] │  │ [auto-load] │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ 🔌 Clients  │  │ 📊 Code     │  │ 🔗 Coupling │         │
│  │ & Services  │  │ Health      │  │ & Patterns  │         │
│  │             │  │             │  │             │         │
│  │ [auto-load] │  │ [on-demand] │  │ [on-demand] │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ 📂 Repo     │  │ ⚠️ Risks    │  │ 🎯 Action   │         │
│  │ Health      │  │ & Issues    │  │ Items       │         │
│  │             │  │             │  │             │         │
│  │ [on-demand] │  │ [on-demand] │  │ [computed]  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 Card Definitions

| # | Card | Layer | Auto/Manual | What it shows |
|---|------|-------|-------------|---------------|
| 1 | **System Profile** | L0 | Auto | OS, runtime versions, available tools, VENV status |
| 2 | **Dependencies & Libraries** | L0+L1 | Auto | Library inventory, framework/ORM/client detection, crossover map |
| 3 | **Structure & Modules** | L0+L1 | Auto | Module map, file counts, entrypoints, solution classification |
| 4 | **Clients & Services** | L1 | Auto | Detected external service clients (Redis, Kafka, DB, cloud) |
| 5 | **Code Health** | L2 | On-demand | Comment ratio, docstring coverage, function metrics, naming |
| 6 | **Coupling & Patterns** | L2+L3 | On-demand | Import graph, circular deps, coupling scores, consistency |
| 7 | **Repo Health** | L0+L3 | On-demand | Git history, repo size, large files, optimization suggestions |
| 8 | **Risks & Issues** | L3 | On-demand | Dead code, dangerous recursion, spaghetti hotspots, deprecations, vulns |
| 9 | **Action Items** | All | Computed | Prioritized list of findings and recommendations from all cards |

### 6.3 Drill-Down Pattern

Every card follows: **Summary → Modal → Full Detail**

```
Card shows:    "📦 23 dependencies (3 frameworks, 2 ORMs, 5 clients)"
Click:         Modal with categorized library table
Deep link:     "View usage sites for sqlalchemy" → shows every import location
Deeper:        "View all calls to Session.query" → full call map
```

### 6.4 Modal Examples

**Library Details Modal:**
```
┌────────────────────────────────────────────────────────────┐
│  📦 flask — Web Framework                          [✕]     │
│────────────────────────────────────────────────────────────│
│  Version: 3.1.0    Category: Framework    Type: Web        │
│  Installed: ✅      Used in: src/ui/web                     │
│                                                            │
│  📍 Import Sites (12 files)                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ src/ui/web/server.py:8      from flask import Flask  │  │
│  │ src/ui/web/routes_api.py:3  from flask import ...    │  │
│  │ src/ui/web/routes_vault.py  from flask import ...    │  │
│  │ ... (9 more)                                         │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  🔗 Related Plugins                                        │
│  None detected                                             │
│                                                            │
│  📊 Framework Features Used                                │
│  Blueprint ✅  Jinja2 ✅  Session ❌  SQLAlchemy ❌         │
└────────────────────────────────────────────────────────────┘
```

**Coupling Analysis Modal:**
```
┌────────────────────────────────────────────────────────────┐
│  🔗 Module Coupling Map                            [✕]     │
│────────────────────────────────────────────────────────────│
│                                                            │
│  src/core/services ←→ src/core/models    Strong (28)       │
│  src/ui/web        ←→ src/core/services  Moderate (15)     │
│  src/ui/cli        ←→ src/core/services  Moderate (12)     │
│  src/adapters      ←→ src/core           Weak (3)          │
│                                                            │
│  ⚠️ Circular Dependencies: 0 detected                      │
│  ✅ All module relationships are acyclic                    │
│                                                            │
│  🎯 Isolation Score: 7.2/10                                │
│  Most modules have clean boundaries with minimal leakage   │
│                                                            │
│  [View full import graph]  [View exposure ratios]          │
└────────────────────────────────────────────────────────────┘
```

---

## 7. Backend Architecture

### 7.1 File Organization

```
src/core/services/audit/
├── __init__.py              # Public API: run_audit(), run_layer()
├── models.py                # Pydantic result models for all layers
├── catalog.py               # Library knowledge base (~500 entries)
├── l0_detection.py          # System, manifests, file structure
├── l1_classification.py     # Library classification, framework/ORM/client ID
├── l2_structure.py          # AST analysis, import graph, exposure
├── l3_deep.py               # Coupling, patterns, recursion, scoring
├── scoring.py               # Complexity + Quality score computation
└── parsers/
    ├── __init__.py
    ├── python_parser.py     # ast-based Python analysis
    ├── node_parser.py       # Regex-based JS/TS analysis
    ├── go_parser.py         # Regex-based Go analysis
    ├── rust_parser.py       # Regex-based Rust analysis
    └── generic_parser.py    # Fallback for other languages
```

### 7.2 Service API Pattern

Each layer function follows the same signature:

```python
def l0_system_profile(project_root: Path) -> dict:
    """L0: System environment detection."""
    ...

def l1_library_classification(project_root: Path, l0_result: dict) -> dict:
    """L1: Classify detected libraries. Needs L0 output."""
    ...

def l2_structure_analysis(project_root: Path, l1_result: dict) -> dict:
    """L2: AST-based structure analysis. Needs L1 output."""
    ...

def l3_deep_analysis(project_root: Path, l2_result: dict) -> dict:
    """L3: Full deep analysis. Needs L2 output."""
    ...
```

### 7.3 Route Structure

```python
# src/ui/web/routes_audit.py

GET  /audit/system           # L0 — system profile
GET  /audit/dependencies     # L0+L1 — library inventory + classification
GET  /audit/structure        # L0+L1 — module map + solution classification
GET  /audit/clients          # L1 — external service clients
GET  /audit/code-health      # L2 — code metrics (on-demand)
GET  /audit/coupling         # L2+L3 — coupling analysis (on-demand)
GET  /audit/repo             # L0+L3 — repo health (on-demand)
GET  /audit/risks            # L3 — risks & issues (on-demand)
GET  /audit/scores           # All — master scores (computed from cache)

# Drill-down endpoints
GET  /audit/library/<name>   # Library detail: usage sites, features
GET  /audit/module/<name>    # Module detail: exports, imports, metrics
GET  /audit/imports/<module> # Full import graph for a module
```

All endpoints use the `devops_cache` system we just built.

### 7.4 Caching Strategy

| Layer | Watch Paths | Cache Key Pattern | Expected Staleness |
|---|---|---|---|
| L0 | `pyproject.toml`, `package.json`, `go.mod`, etc. | `audit:l0:system` | Rare (install/uninstall) |
| L1 | Same as L0 + `requirements.txt`, lock files | `audit:l1:deps` | Rare |
| L2 | `src/**/*.py`, `src/**/*.js` (dir mtimes) | `audit:l2:structure` | On code change |
| L3 | Depends on L2 | `audit:l3:coupling` | On code change |

---

## 8. Implementation Phases

### Phase 1 — Foundation (L0 + L1 auto-load cards)

**Effort:** ~2-3 sessions

1. Create `src/core/services/audit/` package
2. Implement L0: system profiler (OS, Python, Node, tools)
3. Implement L1: manifest parsers (pyproject.toml, package.json, etc.)
4. Build library catalog (start with 200 entries, grow)
5. Framework + ORM + client identification
6. Create `routes_audit.py` with L0+L1 endpoints
7. Create `_tab_audit.html` partial template
8. Create `_audit.html` script with 4 auto-load cards
9. Wire up the tab in main template

**Deliverables:** System Profile, Dependencies, Structure, Clients cards

### Phase 2 — Structure Analysis (L2 on-demand cards)

**Effort:** ~2-3 sessions

1. Implement Python AST parser (import extraction, symbol table)
2. Implement regex parsers for JS/TS, Go, Rust
3. Build import graph engine
4. Exposure ratio calculation
5. Code Health card (comment ratio, function metrics)
6. Coupling card with modal drill-downs
7. Library detail drill-down endpoint

**Deliverables:** Code Health, Coupling & Patterns cards + modals

### Phase 3 — Deep Analysis (L3 on-demand cards)

**Effort:** ~2 sessions

1. Circular dependency detection (Tarjan's SCC)
2. Dead code detection
3. Recursion analysis
4. Pattern consistency scoring
5. Repo health analysis (git objects, large files)
6. Risks & Issues card
7. Action Items card (aggregated recommendations)

**Deliverables:** Repo Health, Risks & Issues, Action Items cards

### Phase 4 — Scoring & Polish

**Effort:** ~1-2 sessions

1. Complexity score computation
2. Quality score computation
3. Score history tracking (over time)
4. Master scores banner
5. UX polish (loading states, animations, tooltips)
6. Crossover visualization
7. Integration with existing DevOps cards (links between audit findings and devops actions)

**Deliverables:** Scores, cross-tab navigation, final polish

---

## 9. What Already Exists (Reuse Map)

| Existing Component | Audit Use | Integration |
|---|---|---|
| `detection.py` | Module detection for L0 | Call directly |
| `package_ops.py` | Package manager detection, outdated/audit | Feed into L1 |
| `quality_ops.py` | Linter/formatter detection | Merge with L0 tools |
| `testing_ops.py` | Test framework detection | Merge with L1 classification |
| `security_ops.py` | Secret scanning, posture score | Feed into Risks card |
| `docs_ops.py` | Documentation inventory | Feed into Quality score |
| `k8s_ops.py` / `terraform_ops.py` | IaC detection | Complexity score input |
| `docker_ops.py` | Container detection | System profile input |
| `devops_cache.py` | Server-side caching | All audit endpoints use this |

---

## 10. Open Questions for Discussion

1. **Catalog maintenance:** The library catalog (§3, L1) needs ~500 entries.
   Ship a curated built-in catalog? Allow user extensions? Both?

2. **Multi-language AST depth:** For L2/L3, Python gets full `ast` treatment.
   Other languages get regex heuristics. Is that sufficient for your use cases,
   or do you need tree-sitter for JS/TS?

3. **Score persistence:** Should complexity/quality scores be tracked over time
   (in `.state/audit_history.json`) to show trends? Or is point-in-time enough?

4. **Live IaC differential:** You mentioned "Docker live vs current file, K8s
   live vs manifest." This requires connecting to running containers/clusters.
   Should this be an Audit card or stay in the DevOps tab with a cross-link?

5. **Git optimization tools:** You mentioned "offer to install it first" for
   git-filter-repo, BFG cleaner, etc. Do you want the audit to actively
   install tools, or just detect + recommend?

6. **Vulnerability scanning depth:** Use `pip-audit` + `npm audit` (already
   in `package_ops`)? Or also integrate with OSV.dev / Snyk APIs for offline
   databases?

7. **Tab name and position:** `🔬 Audit` — does that feel right? Where in the
   tab order? After DevOps? After Integrations?

---

*This document defines the architecture for the Project Audit system.
Implementation begins after design review and discussion.*
