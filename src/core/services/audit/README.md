# Audit Service

> The multi-layered code analysis engine for the devops control plane.
> Scans the host machine, the project's dependencies, structure, code
> quality, repository health, and risk posture — all without external
> APIs. Everything is computed locally from disk, PATH, and git history.

---

## How It Works

The audit engine is a **three-layer pipeline** that builds progressively
deeper understanding of the project:

```
┌─────────────────────────────────────────────────────────────────────┐
│ L0 — DETECTION (instant, < 200ms)                                   │
│                                                                      │
│  What exists on this machine and in this project?                    │
│                                                                      │
│  Fast tier:  OS, distro, arch, Python, venv, 35 CLI tools,          │
│              project modules (from project.yml), manifest files      │
│                                                                      │
│  Deep tier:  Shell, init system, network, build toolchain,           │
│              GPU (NVIDIA/AMD/Intel), kernel (modules, config,        │
│              IOMMU), WSL interop, filesystem, security (SELinux,     │
│              AppArmor), services (journald, cron)                    │
│                                                                      │
│  OUTPUT: System profile dict — feeds L1, scoring, and tool_install   │
└──────────────┬──────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────┐
│ L1 — CLASSIFICATION (auto-load, < 500ms)                             │
│                                                                      │
│  What is this project made of?                                       │
│                                                                      │
│  Dependencies:  Parse all manifests (requirements.txt, package.json, │
│                 pyproject.toml, go.mod, Cargo.toml, Gemfile, mix.exs)│
│                 → classify each against the 450+ entry catalog →     │
│                 detect frameworks, ORMs, external service clients,    │
│                 cross-ecosystem overlaps                              │
│                                                                      │
│  Structure:     What kind of project? Multi-module monorepo?         │
│                 Has CLI? Web? Tests? IaC? Docker? CI?                │
│                 Component inventory + entrypoint detection            │
│                                                                      │
│  Clients:       Which external services does the code talk to?       │
│                 Redis, PostgreSQL, Kafka, S3, etc. — grouped by      │
│                 logical service identity across ecosystems            │
│                                                                      │
│  OUTPUT: Dependency inventory, structure classification, client map   │
└──────────────┬──────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────┐
│ L2 — ANALYSIS (on-demand, 1-25s)                                     │
│                                                                      │
│  How healthy is this project?                                        │
│                                                                      │
│  Structure:   Import graph, module boundaries, exposure ratios,      │
│               cross-module dependency mapping, library usage sites    │
│                                                                      │
│  Quality:     Per-file health scores (docstrings, complexity,        │
│               nesting, comments, type hints), hotspot detection,      │
│               naming convention consistency                           │
│                                                                      │
│  Repository:  Git object weight, history depth, large/binary files,  │
│               branch hygiene, repo health score                      │
│                                                                      │
│  Risks:       Unified risk register from security, dependencies,     │
│               documentation, testing, infrastructure. Severity-       │
│               classified findings, posture score (A-F), action items  │
│                                                                      │
│  OUTPUT: Quality metrics, risk register, repo health, action items   │
└──────────────┬──────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────┐
│ SCORING (composites L0+L1, optionally L2)                            │
│                                                                      │
│  Two master scores (1-10 each):                                      │
│                                                                      │
│  Complexity:  tech diversity (25%), module count (15%),              │
│               dependency count (25%), integration count (15%),       │
│               infrastructure complexity (20%)                        │
│               + L2 enrichment: actual module boundaries, import usage │
│                                                                      │
│  Quality:     documentation (15%), testing (15%), tooling (15%),     │
│               containerization (15%), CI/CD (15%), type safety (10%), │
│               code health (5%), risk posture (10%)                   │
│               + L2 enrichment: real code health, repo health, risks  │
│                                                                      │
│  Score history tracked in .state/audit_scores.json (last 100)        │
│  Trend computation: up / down / stable / new                         │
│                                                                      │
│  OUTPUT: {complexity: {score, breakdown}, quality: {score, breakdown},│
│           trend: {snapshots, complexity_trend, quality_trend, deltas}}│
└─────────────────────────────────────────────────────────────────────┘
```

### Two-Tier Detection

| Tier | When | Budget | What |
|------|------|--------|------|
| **Fast** | Every audit scan | ~120ms | OS, distro, family, arch, PMs, container, capabilities, Python, venv, tools, modules, manifests |
| **Deep** | On demand (cached 5min) | ~2s | Shell, init system, network, build toolchain, GPU, kernel, WSL interop, filesystem, security, services |

The fast tier runs on every page load — it feeds the system profile
that the tool_install resolver uses for method selection. The deep
tier runs when the user explicitly requests it or enters a provisioning
flow. Results are cached at module level with a 5-minute TTL.

### Catalog — The Knowledge Base

The catalog is a curated dictionary of 450+ libraries across Python,
Node, Go, Rust, Ruby, and Elixir ecosystems. Each entry has:

- `category` — web, database, testing, security, ML, etc.
- `type` — framework, ORM, client, driver, utility, etc.
- `ecosystem` — python, node, go, rust, ruby, elixir
- `description` — what it does
- `service` — logical service identity (e.g., "Redis", "PostgreSQL")

The catalog enables automatic classification without external APIs.
When L1 parses a dependency manifest, it looks up each library name
and gets instant categorization. This powers the framework detection,
ORM identification, client grouping, and crossover analysis.

### Risk Register — Unified View

L2 risks aggregates findings from **five sources** into one register:

1. **Security** — hardcoded secrets (scan_secrets), sensitive files
   not gitignored, incomplete .gitignore
2. **Dependencies** — known vulnerabilities (package_audit), outdated
   packages (package_outdated)
3. **Documentation** — missing README, CHANGELOG, LICENSE, broken links
4. **Testing** — no tests detected, low test-to-source ratio
5. **Infrastructure** — .env without .env.example, env validation issues

Each finding has: category, severity (critical/high/medium/info),
title, detail, source, recommendation, and optional file-level entries.
The posture score deducts from 10.0 with severity-weighted caps.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│ HTTP (routes_audit.py)        CLI (ui/cli/audit.py)      │
└────────────┬──────────────────────┬──────────────────────┘
             │                      │
┌────────────▼──────────────────────▼──────────────────────┐
│ PUBLIC API  (__init__.py)                                  │
│  l0_system_profile · l1_dependencies · l1_structure ·     │
│  l1_clients · l2_structure · l2_quality · l2_repo ·       │
│  l2_risks · audit_scores · audit_scores_enriched          │
└────────────┬──────────────────────────────────────────────┘
             │ composes
     ┌───────┴──────────────────────────┐
     ▼                                  ▼
┌────────────────┐           ┌────────────────────┐
│ SCORING        │           │ L2 ANALYSIS        │
│ scoring.py     │           │ l2_structure.py    │
│ Complexity +   │◄──────────│ l2_quality.py      │
│ Quality scores │ enriches  │ l2_repo.py         │
│ History+trends │           │ l2_risk.py         │
└───────┬────────┘           └─────────┬──────────┘
        │ reads                        │ reads
┌───────▼─────────────────────────┐    │
│ L1 CLASSIFICATION               │    │
│ l1_classification.py            │    │
│ l1_parsers.py                   │◄───┘
│ catalog.py                      │
└───────┬─────────────────────────┘
        │ reads
┌───────▼─────────────────────────────────────────────────┐
│ L0 DETECTION                                             │
│ l0_detection.py    — fast-tier orchestrator + public API │
│ l0_os_detection.py — OS/distro/arch/PM sub-detectors     │
│ l0_deep_detectors.py — Phase 4/5/8 deep probes          │
│ l0_hw_detectors.py   — Phase 6 GPU/kernel/WSL probes    │
└───────┬─────────────────────────────────────────────────┘
        │ reads
┌───────▼────────────┐
│ MODELS             │
│ models.py          │
│ TypedDicts +       │
│ _meta envelope     │
└────────────────────┘
```

Every result wraps in the `_meta` envelope pattern: layer, dimension,
computed_at, duration_ms, scope. This makes results self-describing
and enables caching, trend tracking, and audit trails.

---

## File Map

```
audit/
├── __init__.py          Public API re-exports (59 lines)
├── models.py            TypedDicts for all layer results + _meta envelope (219 lines)
├── catalog.py           Library knowledge base — 450+ entries (488 lines)
├── l0_detection.py      Fast-tier detection + deep-tier orchestrator + public API (465 lines)
├── l0_os_detection.py   OS/distro/arch detection helpers + _detect_os() (407 lines)
├── l0_deep_detectors.py Phase 4/5/8 deep probes + DEEP_DETECTORS registry (524 lines)
├── l0_hw_detectors.py   Phase 6 GPU/kernel/WSL deep probes (340 lines)
├── l1_classification.py Dependency classification + structure + clients (423 lines)
├── l1_parsers.py        Manifest parsers (requirements.txt, package.json, etc.) (235 lines)
├── l2_structure.py      Import graph + module boundaries + usage map (371 lines)
├── l2_quality.py        Code health scores + hotspots + naming analysis (433 lines)
├── l2_repo.py           Git object weight + history + large files + health (394 lines)
├── l2_risk.py           Risk register aggregation + posture scoring (598 lines)
├── scoring.py           Complexity + Quality master scores + history (520 lines)
├── parsers/             AST-based source code analysis
│   ├── __init__.py
│   └── python_parser.py Parse Python files into analysis objects
└── README.md            This file
```

### `l0_detection.py` — Fast-Tier Orchestrator (465 lines)

The entry point for all detection. Contains the `_TOOLS` registry
(35 CLI tools to probe), fast-tier detectors, and the deep-tier
cache + orchestrator.

| Function | What It Does |
|----------|-------------|
| `_detect_python()` | Python version, implementation, executable, venv tools |
| `_detect_venv()` | Virtual environment status and discovery |
| `_detect_tools()` | Check 35 CLI tools via `shutil.which()` |
| `_detect_modules()` | Parse `project.yml` for module inventory |
| `_detect_manifests()` | Find dependency manifest files |
| `_detect_deep_profile()` | Orchestrate deep-tier detection (cached, selective) |
| `l0_system_profile()` | **Public API** — full system profile (fast + optional deep) |
| `detect_tools()` | **Public API** — alias for `_detect_tools()` |

### `l0_os_detection.py` — OS Detection (407 lines)

Architecture normalization, distro family mapping, and the composite
`_detect_os()` builder. Parses `/etc/os-release`, detects containers,
capabilities, package managers, and system libraries.

| Function | What It Does |
|----------|-------------|
| `_detect_os()` | Full OS profile: distro, family, arch, PMs, container, capabilities |

### `l0_deep_detectors.py` — Deep Probes Phase 4/5/8 (524 lines)

Expensive shell-based detections. Each function is self-contained
and returns a dict matching the system model schema.

| Function | Phase | What It Detects |
|----------|-------|----------------|
| `_detect_shell()` | 4 | Active shell, version, config files, aliases |
| `_detect_init_system_profile()` | 4 | Init system (systemd/openrc/upstart), failed units |
| `_detect_network()` | 4 | Interfaces, default gateway, DNS, firewall |
| `_detect_build_profile()` | 5 | GCC/Clang/Make/CMake versions, cross-compile targets |
| `_detect_filesystem()` | 8 | Root FS type, free space |
| `_detect_security()` | 8 | SELinux mode, AppArmor profiles |
| `_detect_services()` | 8 | journald, logrotate, cron availability |

### `l0_hw_detectors.py` — Hardware Probes Phase 6 (340 lines)

Most expensive probes — may shell out to nvidia-smi, lsmod, etc.

| Function | What It Detects |
|----------|----------------|
| `_detect_gpu_profile()` | NVIDIA (driver, CUDA, nvcc, cuDNN, compute cap), AMD (ROCm), Intel (OpenCL) |
| `_detect_kernel_profile()` | Version, config, loaded modules, DevOps module check, IOMMU groups |
| `_detect_wsl_interop()` | PowerShell available, binfmt, Windows user, .wslconfig |

### `l1_classification.py` — Dependency Classification (423 lines)

Parses all manifests, classifies against the catalog, identifies
frameworks/ORMs/clients, and detects cross-ecosystem patterns.

| Function | What It Does |
|----------|-------------|
| `l1_dependencies()` | **Public API** — full dependency inventory with classification |
| `l1_structure()` | **Public API** — solution type, components, entrypoints |
| `l1_clients()` | **Public API** — external service client detection |

### `l1_parsers.py` — Manifest Parsers (235 lines)

Pure functions: file → list of `{name, version, dev}`.

| Parser | File |
|--------|------|
| `_parse_requirements_txt()` | `requirements.txt`, `requirements-dev.txt` |
| `_parse_pyproject_toml()` | `pyproject.toml` (TOML or regex fallback) |
| `_parse_package_json()` | `package.json` |
| `_parse_go_mod()` | `go.mod` |
| `_parse_cargo_toml()` | `Cargo.toml` |
| `_parse_gemfile()` | `Gemfile` |
| `_parse_mix_exs()` | `mix.exs` |

### `l2_structure.py` — Import Graph Analysis (371 lines)

Builds the import graph from `python_parser.parse_tree()` results.

| Function | What It Does |
|----------|-------------|
| `l2_structure()` | **Public API** — import graph, module boundaries, usage map |

### `l2_quality.py` — Code Health Analysis (433 lines)

Computes per-file health scores across 5 dimensions.

| Function | What It Does |
|----------|-------------|
| `l2_quality()` | **Public API** — health scores, hotspots, naming consistency |

### `l2_repo.py` — Repository Health (394 lines)

Git object analysis with its own lightweight `_run_git()` runner.

| Function | What It Does |
|----------|-------------|
| `l2_repo()` | **Public API** — objects, history, large files, health score |

### `l2_risk.py` — Risk Register (598 lines)

Aggregates findings from 5 sources with cache-first data access.

| Function | What It Does |
|----------|-------------|
| `l2_risks()` | **Public API** — findings, summary, posture score, action items |

### `scoring.py` — Master Scores (520 lines)

Composite scoring with optional L2 enrichment and history tracking.

| Function | What It Does |
|----------|-------------|
| `audit_scores()` | **Public API** — complexity + quality scores with trend |
| `audit_scores_enriched()` | **Public API** — fully enriched scores (runs all L2) |

---

## Dependency Graph

```
models.py           standalone — TypedDicts only
   ↑
catalog.py          standalone — static data + lookup/classify functions
   ↑
l1_parsers.py       standalone — pure file parsers
   ↑
l0_os_detection.py  standalone — OS detection
   ↑
l0_hw_detectors.py  standalone — GPU/kernel/WSL (imports tool_install.detect_gpu/detect_kernel)
   ↑
l0_deep_detectors.py imports from l0_hw_detectors
   ↑
l0_detection.py     imports from l0_os_detection, l0_deep_detectors, models
   ↑
l1_classification.py imports from l1_parsers, catalog, models
   ↑
l2_structure.py     imports from models, parsers/python_parser
l2_quality.py       imports from models, parsers/python_parser
l2_repo.py          imports from models (standalone git via subprocess)
l2_risk.py          imports from models (lazy: security_ops, package_ops, docs_ops, testing_ops, env_ops)
   ↑
scoring.py          imports from l0_detection, l1_classification, l2_*, models
```

Key design decisions:
- **L2 risk** uses lazy imports to the ops layer — it calls security_ops,
  package_ops, etc. but only at runtime and with try/except. This means
  the audit package has no hard dependency on those services.
- **L2 risk** reads from the devops card cache first (instant) before
  falling back to live ops calls (slow). This makes the risk register
  cheap when the dashboard has already computed the data.
- **L0 deep detectors** use the `DEEP_DETECTORS` registry pattern —
  the orchestrator iterates the dict without knowing individual functions.

---

## Key Data Shapes

### _meta Envelope (every result)

```python
{
    "_meta": {
        "layer": "L0",           # "L0" | "L1" | "L2"
        "dimension": "system",   # "system" | "dependencies" | "structure" | ...
        "computed_at": 1709123456.789,
        "duration_ms": 142,
        "scope": "full",         # "full" | "module:<path>"
    },
    # ... actual result fields
}
```

### L0 System Profile

```python
{
    "_meta": {...},
    "os": {
        "system": "Linux", "distro": "ubuntu", "distro_version": "22.04",
        "distro_family": "debian", "arch": "amd64",
        "package_manager": {"primary": "apt", "snap_available": True},
        "container": {"type": None, "runtime": None},
        "capabilities": {"has_sudo": True, "has_systemctl": True, ...},
    },
    "python": {"version": "3.12.1", "implementation": "CPython", ...},
    "venv": {"in_venv": True, "active_prefix": "/path/to/.venv", ...},
    "tools": [{"id": "git", "available": True, "path": "/usr/bin/git", ...}, ...],
    "modules": [{"name": "core", "path": "src/core", "domain": "backend", ...}, ...],
    "manifests": [{"file": "pyproject.toml", "ecosystem": "python", ...}, ...],
}
```

### Scoring Output

```python
{
    "_meta": {...},
    "complexity": {
        "score": 7.2,
        "breakdown": {
            "tech_diversity": {"score": 6.0, "weight": 0.25, "detail": "..."},
            "module_count":   {"score": 8.0, "weight": 0.15, "detail": "..."},
            ...
        },
    },
    "quality": {
        "score": 6.8,
        "breakdown": {...},
    },
    "trend": {
        "snapshots": 12,
        "complexity_trend": "stable",
        "quality_trend": "up",
        "complexity_delta": 0.1,
        "quality_delta": 0.3,
    },
}
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| **Routes** | `routes_audit.py` | All public API functions — L0/L1/L2/scoring |
| **Routes** | `routes_devops.py` | `l0_system_profile`, `l1_dependencies`, `audit_scores` |
| **CLI** | `ui/cli/audit.py` | `_detect_os`, L0/L1/L2 functions |
| **Services** | `scoring.py` (self) | `l0_system_profile`, `l1_*`, `l2_*` |
| **Services** | `tool_install/orchestrator.py` | `_detect_os` (for system profile) |
| **Services** | `tool_install/recipe_deps.py` | `_detect_os` (for distro family) |
| **Services** | `tool_install/method_selection.py` | `_detect_os` (for PM selection) |
| **Services** | `tool_requirements.py` | `detect_tools` |
| **Services** | `dev_overrides.py` | `_detect_os` |

---

## API Endpoints

### Analysis

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/audit/system` | GET | L0 system profile (fast tier) |
| `/api/audit/system/deep-detect` | POST | L0 deep tier detection (selective) |
| `/api/audit/dependencies` | GET | L1 dependency inventory |
| `/api/audit/structure` | GET | L1 solution structure |
| `/api/audit/clients` | GET | L1 external service clients |
| `/api/audit/structure-analysis` | GET | L2 import graph + modules |
| `/api/audit/code-health` | GET | L2 code quality + hotspots |
| `/api/audit/repo` | GET | L2 repository health |
| `/api/audit/risks` | GET | L2 risk register + posture |

### Scoring

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/audit/scores` | GET | Complexity + quality scores |
| `/api/audit/scores/enriched` | GET | L2-enriched scores (heavier) |
| `/api/audit/scores/history` | GET | Score trend history |

### Tool Management (delegates to tool_install)

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/tools/status` | GET | All tool availability |
| `/api/audit/install-tool` | POST | Legacy single-command install |
| `/api/audit/resolve-choices` | POST | Choice questions for a tool |
| `/api/audit/install-plan` | POST | Resolve install plan |
| `/api/audit/install-plan/execute` | POST | Execute plan (SSE stream) |
| `/api/audit/install-plan/execute-sync` | POST | Execute plan (blocking) |
| `/api/audit/install-plan/pending` | GET | List interrupted plans |
| `/api/audit/install-plan/resume` | POST | Resume interrupted plan |
| `/api/audit/install-plan/cancel` | POST | Cancel a plan |
| `/api/audit/install-plan/archive` | POST | Archive completed plan |
| `/api/audit/install-plan/cache` | POST | Plan cache operations |
| `/api/audit/install-cache/status` | GET | Plan cache status |
| `/api/audit/install-cache/clear` | POST | Clear plan cache |
| `/api/audit/install-cache/artifacts` | POST | Cache artifact management |
| `/api/audit/check-deps` | POST | Check system package availability |
| `/api/audit/check-updates` | POST | Check if tool has updates |
| `/api/audit/tool-version` | POST | Get installed version |
| `/api/audit/update-tool` | POST | Update a tool |
| `/api/audit/remove-tool` | POST | Remove a tool |
| `/api/audit/remediate` | POST | Run remediation command (SSE) |

### Audit Staging (snapshot save/load)

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/audits/pending` | GET | List pending audit snapshots |
| `/api/audits/pending/<id>` | GET | Get specific pending snapshot |
| `/api/audits/save` | POST | Save pending audit |
| `/api/audits/discard` | POST | Discard pending audit |
| `/api/audits/saved` | GET | List saved audits |
| `/api/audits/saved/<id>` | GET | Get specific saved audit |
| `/api/audits/saved/<id>` | DELETE | Delete saved audit |

### Data Management

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/audit/data-status` | POST | Check tool data status |
| `/api/audit/data-usage` | GET | Data storage usage |
| `/api/audit/service-status` | POST | Check external service status |
