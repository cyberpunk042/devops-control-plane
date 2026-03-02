# Audit Routes — API Layer

> **7 files · 1,840 lines · 42 endpoints on `audit_bp`.**
>
> This package serves the Audit tab's API — the largest route domain
> in the application. It was split from a monolithic `routes_audit.py`
> (1,781 lines) into six focused sub-modules, each owning a clear
> slice of the audit surface area.

---

## How It Works

### Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│ __init__.py — Blueprint + Sub-Module Imports                      │
│                                                                    │
│ audit_bp = Blueprint("audit", __name__, url_prefix="/api")        │
│                                                                    │
│ from . import analysis        ← L0/L1/L2 audit data (11 EP)     │
│ from . import staging         ← snapshot lifecycle (7 EP)        │
│ from . import tool_install    ← install/resolve/check (10 EP)    │
│ from . import tool_execution  ← plan execute/resume/SSE (6 EP)  │
│ from . import deep_detection  ← hardware/GPU/network (1 EP)     │
│ from . import offline_cache   ← cache/data packs/services (7 EP)│
│                                                                    │
│ Imports MUST come after audit_bp is defined (circular guard).     │
└──────────────────────────────────────────────────────────────────┘
```

### Blueprint Registration

```
app.py
    │
    ├── from src.ui.web.routes.audit import audit_bp
    ├── app.register_blueprint(audit_bp)
    │
    └── All routes under /api/audit/* and /api/audits/*
```

### Three-Tier Analysis Model

The analysis endpoints follow a tiered depth model. Each tier
trades off speed for detail:

```
┌─────────────────────────────────────────────────────────────┐
│ L0 — System Profile                    (~0.5–2s)            │
│ Static system info: OS, CPU, RAM, shell, Python, etc.       │
│ Endpoint: GET /audit/system                                 │
│                                                              │
│ L0 Deep — Extended System Profile      (~2–5s)              │
│ GPU, kernel modules, build toolchain, network, hardware.    │
│ Endpoint: POST /audit/system/deep-detect   (on-demand)      │
├─────────────────────────────────────────────────────────────┤
│ L1 — Project Analysis                  (~1–3s each)         │
│ Dependencies, structure, clients — direct project scanning. │
│ Endpoints:                                                   │
│   GET /audit/dependencies                                   │
│   GET /audit/structure                                      │
│   GET /audit/clients                                        │
├─────────────────────────────────────────────────────────────┤
│ L2 — Deep Analysis                     (~2–25s each)        │
│ On-demand, expensive. Results cached via devops_cache.      │
│ Endpoints:                                                   │
│   GET /audit/structure-analysis  (import graph, boundaries) │
│   GET /audit/code-health         (quality metrics, hotspots)│
│   GET /audit/repo                (git objects, large files)  │
│   GET /audit/risks               (security, deps, docs, etc)│
│                                                              │
│ L2 Scores:                                                   │
│   GET /audit/scores              (aggregate scores)         │
│   GET /audit/scores/enriched     (L2-enriched master scores)│
│   GET /audit/scores/history      (trend snapshots)          │
└─────────────────────────────────────────────────────────────┘
```

All L0/L1/L2 endpoints use the same caching pattern:

```python
result = devops_cache.get_cached(
    root, "audit:cache_key",
    lambda: expensive_operation(root),
    force=bust,             # ?bust query param forces refresh
)
```

### Tool Install Lifecycle

```
Phase 1: Choices                    Phase 2: Plan
POST /audit/install/resolve-choices  POST /audit/install-plan
    │                                    │
    ├── Has choices? ──NO──→            ├── Resolve plan
    │   ↓ YES                           ├── Check availability
    │   Return decision tree             ├── Determine steps
    │   (variant, inputs, defaults)      └── Return ordered plan
    │   ↓ User selects                       │
    │   POST with answers ──────────────────►│
    │                                         ▼
    │                        ┌────────────────────────────┐
    │                        │ Phase 3: Execution          │
    │                        │                              │
    │          ┌─── sync ────┤                              │
    │          │             │ POST /audit/install-plan/    │
    │    Single JSON         │      execute-sync            │
    │    response            │                              │
    │                        │         ─── or ───           │
    │          │             │                              │
    │          └── stream ───┤ POST /audit/install-plan/    │
    │                        │      execute                 │
    │              SSE:      │                              │
    │              step_start│  resume: POST /audit/        │
    │              step_done │         install-plan/resume  │
    │              progress  │                              │
    │              done      │  cancel: POST /audit/        │
    │              error     │         install-plan/cancel  │
    │                        └────────────────────────────┘
    │
    └── Cleanup: POST /audit/install-plan/archive
```

### SSE Execution Stream

The `tool_execution.py` SSE endpoint is the most complex route in
the application (822 lines). It streams real-time installation
progress:

```
Client ←──SSE──── Server

Event types:
  plan         → Full plan details (steps, metadata)
  step_start   → Step N starting (label, command)
  progress     → Step N progress (output line, % estimate)
  step_done    → Step N completed (duration, exit_code)
  step_failed  → Step N failed (error, stderr)
  verify       → Post-install verification result
  done         → All steps complete (ok: true/false)
  error        → Fatal error (message)

Features:
  - DAG-based execution (parallel where possible)
  - Sudo password forwarding via request body
  - Automatic PATH refresh after install
  - Post-install tool cache bust
  - Run tracking via @run_tracked decorator
  - Resumable: failed plans saved with completed step state
```

### Audit Staging Pipeline

```
Background Scan ──→ Pending Snapshots ──→ Git Ledger
                        │
     GET /audits/pending    POST /audits/save
     GET /audits/pending/:id    POST /audits/discard
                                     │
                              GET /audits/saved
                              GET /audits/saved/:id
                              DELETE /audits/saved/:id
```

Snapshots flow: computed → pending (in-memory/file cache) →
saved (git ledger branch) or discarded. The staging system
decouples scan execution from persistence.

### Offline Cache System

```
POST /audit/install-plan/cache     ← Pre-download plan artifacts
GET  /audit/install-cache/status   ← Summary of cached artifacts
POST /audit/install-cache/clear    ← Clear cached artifacts
POST /audit/install-cache/artifacts ← Load cached artifact manifest

POST /audit/data-status            ← Check data pack freshness
GET  /audit/data-usage             ← Disk usage of data packs

POST /audit/service-status         ← Query systemd service status
```

---

## File Map

```
audit/
├── __init__.py              Blueprint + sub-module imports (34 lines)
├── analysis.py              L0/L1/L2 audit data endpoints (219 lines)
├── staging.py               Pending snapshot lifecycle (118 lines)
├── tool_install.py          Install, resolve, check, version (345 lines)
├── tool_execution.py        Plan execution SSE, resume, cancel (822 lines)
├── deep_detection.py        Deep system detection (112 lines)
├── offline_cache.py         Offline cache, data packs, service status (190 lines)
└── README.md                This file
```

---

## Per-File Documentation

### `__init__.py` — Blueprint & Imports (34 lines)

Defines `audit_bp = Blueprint("audit", ...)` with `/api` prefix.
Imports all 6 sub-modules after the blueprint is defined to avoid
circular imports. Each sub-module decorates functions with
`@audit_bp.route(...)` to register its endpoints.

### `analysis.py` — L0/L1/L2 Analysis (219 lines)

**11 endpoints.** All follow the same pattern: get `project_root`,
check for `?bust` param, call `devops_cache.get_cached()` with
the appropriate service function.

| Endpoint | Tier | Service Function | Cache Key |
|----------|------|-----------------|-----------|
| `GET /audit/system` | L0 | `l0_system_profile()` | `audit:system` |
| `GET /audit/system` + `?deep` | L0 | `l0_system_profile(deep=True)` | `audit:system:deep` |
| `GET /audit/dependencies` | L1 | `l1_dependencies()` | `audit:deps` |
| `GET /audit/structure` | L1 | `l1_structure()` | `audit:structure` |
| `GET /audit/clients` | L1 | `l1_clients()` | `audit:clients` |
| `GET /audit/scores` | — | `audit_scores()` | `audit:scores` |
| `GET /audit/scores/enriched` | L2 | `audit_scores_enriched()` | `audit:scores:enriched` |
| `GET /audit/scores/history` | — | `_load_history()` | none |
| `GET /audit/structure-analysis` | L2 | `l2_structure()` | `audit:l2:structure` |
| `GET /audit/code-health` | L2 | `l2_quality()` | `audit:l2:quality` |
| `GET /audit/repo` | L2 | `l2_repo()` | `audit:l2:repo` |
| `GET /audit/risks` | L2 | `l2_risks()` | `audit:l2:risks` |

**Imports from:** `src.core.services.audit` (all L0/L1/L2 functions),
`src.core.services.devops.cache` (caching layer).

### `staging.py` — Snapshot Lifecycle (118 lines)

**7 endpoints.** Manages the lifecycle of audit snapshots from
pending (in-memory) to saved (git ledger) or discarded.

| Endpoint | Method | What It Does |
|----------|--------|-------------|
| `/audits/pending` | GET | List all unsaved snapshots (metadata only) |
| `/audits/pending/:id` | GET | Full detail for one pending audit (with data blob) |
| `/audits/save` | POST | Save pending → git ledger (single or batch `"all"`) |
| `/audits/discard` | POST | Discard pending snapshots (single or batch `"all"`) |
| `/audits/saved` | GET | List saved audits from git ledger |
| `/audits/saved/:id` | GET | Full detail for one saved audit |
| `/audits/saved/:id` | DELETE | Delete saved audit from ledger branch |

**Imports from:** `src.core.services.audit_staging` (pending ops),
`src.core.services.ledger.ledger_ops` (saved ops).

### `tool_install.py` — Install & Resolve (345 lines)

**10 endpoints.** Covers the install lifecycle from choice resolution
through plan generation, tool status, updates, and removal.

| Endpoint | Method | What It Does |
|----------|--------|-------------|
| `/audit/install-tool` | POST | Simple tool install (legacy fallback) |
| `/audit/remediate` | POST | Execute remediation action via SSE stream |
| `/audit/install/check-deps` | POST | Check if system packages are installed |
| `/audit/install/resolve-choices` | POST | Phase 1: get user choices before install |
| `/audit/install-plan` | POST | Phase 2: generate ordered install plan |
| `/audit/tools/status` | GET | Centralized tool availability status |
| `/audit/install/update` | POST | Update installed tool to latest version |
| `/audit/install/check-updates` | POST | Check tools for version info |
| `/audit/install/version` | POST | Get version of single installed tool |
| `/audit/install/remove` | POST | Remove an installed tool |

**Key features:**
- `resolve-choices` returns a decision tree (variant, inputs, defaults, disabled options)
- `install-plan` accepts optional `answers` dict for two-pass flow
- `tools/status` returns all registered tools with availability, category, recipe info
- `remediate` streams output via SSE (`text/event-stream`)
- PATH refresh and cache bust after install/update/remove

**Imports from:** `src.core.services.tool_install` (resolver, detector, path refresh),
`src.core.services.run_tracker` (`@run_tracked` decorator).

### `tool_execution.py` — Plan Execution (822 lines)

**6 endpoints.** The largest file — contains the SSE-streaming plan
execution engine with DAG-based step ordering.

| Endpoint | Method | What It Does |
|----------|--------|-------------|
| `/audit/install-plan/execute-sync` | POST | Synchronous execution (single JSON response) |
| `/audit/install-plan/execute` | POST | SSE streaming execution (real-time events) |
| `/audit/install-plan/pending` | GET | List resumable (paused/failed) plans |
| `/audit/install-plan/resume` | POST | Resume failed plan via SSE |
| `/audit/install-plan/cancel` | POST | Cancel interrupted/failed plan |
| `/audit/install-plan/archive` | POST | Archive completed/cancelled plan |

**SSE execution flow (execute):**

1. Parse request body (tool, sudo_password, answers)
2. Resolve system profile (with dev overrides)
3. Generate install plan (with or without choice answers)
4. Check for DAG metadata in plan steps
5. If DAG: execute steps in parallel (topological order)
6. If linear: execute steps sequentially
7. Stream events: `plan`, `step_start`, `progress`, `step_done`, `verify`, `done`
8. On failure: save plan state for resume, stream `error`
9. On success: bust tool caches, refresh PATH

**SSE execution flow (resume):**

1. Load saved plan state from disk
2. Determine which steps completed vs. remaining
3. Re-execute remaining steps (same SSE flow)
4. Clean up plan state file on success

**Internal functions:**

| Function | Purpose |
|----------|---------|
| `_sse(data)` | Format dict as SSE event line |
| `_on_progress(step_id, status)` | DAG callback → push to event queue |
| `_run_dag()` | Background thread for DAG execution |
| `generate_dag()` | SSE generator for DAG-based plans |
| `generate()` | SSE generator for linear plans |

### `deep_detection.py` — Deep System Detection (112 lines)

**1 endpoint.** On-demand hardware/environment detection for
provisioning flows.

| Endpoint | Method | What It Does |
|----------|--------|-------------|
| `/audit/system/deep-detect` | POST | GPU, kernel, hardware, build tools, network |

**Request body:** `{"checks": ["gpu", "hardware", "kernel", "build", "network", "environment"]}`
Empty array runs all checks.

**Detection modules:**

| Check | What It Detects | Import From |
|-------|----------------|-------------|
| `gpu` | NVIDIA GPU, CUDA version, driver compat | `tool_install.detect_gpu` |
| `hardware` | CPU, memory, disk | `tool_install.detection.hardware` |
| `kernel` | Kernel version, modules | `tool_install.detect_kernel` |
| `build` | Build toolchain (gcc, make, cmake) | `tool_install.detect_build_toolchain` |
| `network` | Registry reachability, proxy, Alpine repos | `tool_install.detection.network` |
| `environment` | NVM, sandbox, CPU features | `tool_install.detection.environment` |

### `offline_cache.py` — Cache, Data Packs, Services (190 lines)

**7 endpoints.** Manages pre-downloaded install artifacts for
offline installation, data pack freshness, and systemd service status.

| Endpoint | Method | What It Does |
|----------|--------|-------------|
| `/audit/install-plan/cache` | POST | Pre-download plan artifacts |
| `/audit/install-cache/status` | GET | Summary of cached artifacts per tool |
| `/audit/install-cache/clear` | POST | Clear cached artifacts (one or all) |
| `/audit/install-cache/artifacts` | POST | Load cached artifact manifest |
| `/audit/data-status` | POST | Check data pack freshness/staleness |
| `/audit/data-usage` | GET | Disk usage of all data pack directories |
| `/audit/service-status` | POST | Query systemd/init service status |

**Cache flow:**
1. Resolve install plan for tool
2. Download all step artifacts to local cache dir
3. Store manifest (file paths, sizes)
4. Return download time estimates

---

## Dependency Graph

```
__init__.py (audit_bp)
    ↑
    ├── analysis.py
    │     ├── src.core.services.audit (L0/L1/L2 functions)
    │     ├── src.core.services.devops.cache (get_cached)
    │     └── src.ui.web.helpers (project_root)
    │
    ├── staging.py
    │     ├── src.core.services.audit_staging (pending ops)
    │     ├── src.core.services.ledger.ledger_ops (saved ops)
    │     └── src.ui.web.helpers (project_root)
    │
    ├── tool_install.py
    │     ├── src.core.services.tool_install (resolver, detector)
    │     ├── src.core.services.run_tracker (@run_tracked)
    │     ├── src.core.services.tool_install.path_refresh
    │     └── src.ui.web.helpers (bust_tool_caches)
    │
    ├── tool_execution.py
    │     ├── src.core.services.tool_install (resolver, executor)
    │     ├── src.core.services.dev_overrides (system profile)
    │     ├── src.core.services.run_tracker (@run_tracked)
    │     └── src.ui.web.helpers (bust_tool_caches)
    │
    ├── deep_detection.py
    │     ├── src.core.services.tool_install (GPU, kernel, build)
    │     ├── src.core.services.tool_install.detection.hardware
    │     ├── src.core.services.tool_install.detection.network
    │     └── src.core.services.tool_install.detection.environment
    │
    └── offline_cache.py
          ├── src.core.services.tool_install (resolver, data packs)
          ├── src.core.services.tool_install.execution.offline_cache
          ├── src.core.services.tool_install.domain.download_helpers
          ├── src.core.services.dev_overrides (system profile)
          └── src.core.services.run_tracker (@run_tracked)
```

---

## Consumers

### Blueprint Registration

| File | How |
|------|-----|
| `src/ui/web/app.py` | `app.register_blueprint(audit_bp)` |

### Frontend Consumers

| JS Module | Endpoints Called |
|-----------|----------------|
| `audit/_l0.html` | `/audit/system`, `/audit/system?deep` |
| `audit/_l1.html` | `/audit/dependencies`, `/audit/structure`, `/audit/clients` |
| `audit/_l2.html` | `/audit/structure-analysis`, `/audit/code-health`, `/audit/repo`, `/audit/risks` |
| `audit/_scores.html` | `/audit/scores`, `/audit/scores/enriched`, `/audit/scores/history` |
| `audit/_tools.html` | `/audit/tools/status`, `/audit/install-tool`, `/audit/install/resolve-choices` |
| `audit/_tools.html` | `/audit/install-plan`, `/audit/install-plan/execute` (SSE) |
| `audit/_tools.html` | `/audit/install/update`, `/audit/install/check-updates`, `/audit/install/version` |
| `audit/_tools.html` | `/audit/install/remove`, `/audit/remediate` (SSE) |
| `audit/_tools.html` | `/audit/install-plan/pending`, `/audit/install-plan/resume` (SSE) |
| `audit/_tools.html` | `/audit/install-plan/cancel`, `/audit/install-plan/archive` |
| `audit/_tools.html` | `/audit/install-plan/cache`, `/audit/install-cache/status` |
| `audit/_tools.html` | `/audit/install-cache/clear`, `/audit/install-cache/artifacts` |
| `audit/_tools.html` | `/audit/data-status`, `/audit/data-usage`, `/audit/service-status` |
| `devops/_audit_manager.html` | `/audits/pending`, `/audits/save`, `/audits/discard` |
| `devops/_audit_manager.html` | `/audits/saved`, `/audits/saved/:id` |
| `wizard/_helpers.html` | `/audit/install-tool`, `/audit/install-plan/execute` (SSE) |

### CLI Consumers

| Module | Endpoints Used |
|--------|---------------|
| `src/ui/tui/` | `/audit/install-plan/execute-sync` (non-SSE path) |

---

## Design Decisions

### Why split from monolithic `routes_audit.py`?

The original file was 1,781 lines — the largest route module in the
project. It mixed six unrelated concerns: analysis data, staging
workflow, tool installation, SSE execution, hardware detection, and
offline caching. Splitting by responsibility makes each file
independently comprehensible and reduces merge conflicts.

### Why is `tool_execution.py` still 822 lines?

SSE execution is inherently complex — it manages a streaming
response, background DAG execution, step-level progress callbacks,
failure state persistence, resume logic, and post-install verification.
These are all tightly coupled to a single HTTP response lifecycle.
Further splitting would scatter the execution state machine across
files without reducing complexity.

### Why two execution modes (sync vs. SSE)?

The SSE streaming endpoint serves the web UI — users see real-time
step progress. The sync endpoint serves CLI callers and batch
operations where streaming is impractical. Both resolve plans the
same way; the difference is only in response delivery.

### Why DAG-based execution?

Some install plans have steps that can run in parallel (e.g.,
downloading two independent binaries). The DAG executor checks for
`parallel_group` metadata on plan steps and runs compatible steps
concurrently while respecting dependency ordering.

### Why lazy imports inside route functions?

Service modules (`tool_install`, `audit_staging`, etc.) can be
heavy. Lazy imports inside route handlers avoid loading all service
code at blueprint registration time, reducing startup latency.
This is especially important for `deep_detection.py` which imports
hardware/GPU detection modules that may not be available on all
systems.

### Why `/audits/` (plural) for staging but `/audit/` for analysis?

The staging endpoints manage *audit snapshots* as resources
(`/audits/pending`, `/audits/saved/:id`). RESTful naming: plural noun
for collections. The analysis endpoints are operations on the
current project state (`/audit/system`, `/audit/risks`), not
resource collections.

### Why does offline_cache include service status?

The service status endpoint (`/audit/service-status`) was originally
used during install planning to check if Docker/systemd services
were running. It lives alongside the cache endpoints because both
serve the pre-install verification phase — ensuring the system is
ready before executing a plan.
