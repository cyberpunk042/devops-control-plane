# Audit System

> Deep code quality analysis, security scanning, and project health scoring.

---

## Overview

The Audit system provides automated analysis of your project across multiple
dimensions. It runs three layers of progressively deeper analysis:

| Layer | Name | Speed | Trigger |
|-------|------|-------|---------|
| **L0** | Detection | Instant | Auto on tab load |
| **L1** | Classification | Fast (<500ms) | Auto on tab load |
| **L2** | Deep Analysis | Medium (2-30s) | On-demand per card |

Results are displayed as **cards** in the Audit tab of the web admin, each
with drill-down modals for detailed findings.

---

## Analysis Layers

### L0 — System Detection

Instant detection of the project's environment:

- **OS Detection** — operating system, version, architecture
- **Hardware** — CPU, memory, disk
- **Runtime Detection** — installed tools, versions, paths
- **Deep Detection** — extended tool discovery (plugins, extensions)

**Source:** `audit/l0_detection.py`, `l0_os_detection.py`,
`l0_hw_detectors.py`, `l0_deep_detectors.py`

### L1 — Classification

Fast analysis of project structure and dependencies:

- **Dependencies** — parse manifests (pyproject.toml, package.json, etc.)
  to extract all dependencies with versions
- **Structure** — detect modules, entry points, file organization
- **Clients** — identify service clients, databases, external APIs

**Parsers:** Language-specific parsers for Python, JavaScript, Go, Rust,
Java/JVM, C/C++, CSS/templates, and config files. Each parser extracts
dependency information from its native manifest format.

**Source:** `audit/l1_classification.py`, `l1_parsers.py`, `parsers/`

### L2 — Deep Analysis (On-Demand)

Heavier analysis triggered per card:

- **Code Quality** — linting, formatting, complexity metrics
- **Repository Health** — commit patterns, branch hygiene, contributor analysis
- **Risk Assessment** — vulnerability detection, outdated dependencies
- **Structure Analysis** — import graphs, coupling, dead code

**Source:** `audit/l2_quality.py`, `l2_repo.py`, `l2_risk.py`, `l2_structure.py`

---

## Scoring

The audit system produces **two composite scores** (1-10):

### Complexity Score

Measures how complex the project is:
- File count and depth
- Dependency count and cross-language usage
- Infrastructure usage (Docker, K8s, Terraform, etc.)
- Multi-service patterns

### Quality Score

Measures how well the project is maintained:
- Test presence and coverage
- Linting and formatting
- Documentation coverage
- Security practices (secrets handling, dependency auditing)
- Repository hygiene (commit messages, branch strategy)

Each score includes a **breakdown** showing which factors contributed
and their individual weights.

**Source:** `audit/scoring.py`

---

## UI — Audit Tab

The Audit tab displays results as two rows of cards:

### Row A — Auto-Load Cards (L0 + L1)

| Card | Data Source | What It Shows |
|------|------------|--------------|
| 🖥 System Profile | L0 | OS, hardware, installed tools |
| 📦 Dependencies | L1 | Parsed dependencies with versions |
| 🏗 Structure | L1 | Modules, entry points, file organization |
| 🔌 Clients | L1 | Detected service clients and APIs |

### Row B — On-Demand Cards (L2)

| Card | Data Source | What It Shows |
|------|------------|--------------|
| 🧪 Code Quality | L2 | Lint results, formatting, complexity |
| 📊 Repository Health | L2 | Commit patterns, contributor analysis |
| ⚠️ Risks | L2 | Vulnerabilities, outdated deps, security issues |
| 🔗 Import Analysis | L2 | Import graph, coupling, dead code |

### Score Banner

The **Scores** card at the top shows the composite Complexity and Quality
scores with a visual breakdown. Score history is tracked so you can see
trends over time.

### Drill-Down Modals

Clicking any card opens a modal with detailed findings. Each finding
includes severity, description, and (where applicable) remediation hints.

**Dismiss with comment** — Individual findings can be dismissed as false
positives with a required comment explaining why.

---

## Staging & Snapshots

Audit results can be staged for review before committing:

- **Save** — persist a snapshot of the current audit state
- **Discard** — throw away staged changes
- **Compare** — see what changed between snapshots
- **History** — browse saved snapshots with timestamps

---

## Tool Install Integration

The audit system integrates with the tool-install system:

- When L0 detects a missing tool, it suggests installation
- Install plans can be cached and executed from the audit tab
- The tool-install system handles recipes, platform detection,
  and failure remediation

---

## API Endpoints

### L0/L1 Auto-Load

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/audit/system` | GET | L0 system detection results |
| `/api/audit/dependencies` | GET | L1 dependency analysis |
| `/api/audit/structure` | GET | L1 structure analysis |
| `/api/audit/clients` | GET | L1 client/service detection |

### Scoring

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/audit/scores` | GET | Current composite scores |
| `/api/audit/scores/enriched` | GET | Scores with breakdown |
| `/api/audit/scores/history` | GET | Score trend over time |

### L2 On-Demand

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/audit/code-health` | GET | Code quality analysis |
| `/api/audit/repo` | GET | Repository health |
| `/api/audit/risks` | GET | Risk assessment |
| `/api/audit/structure-analysis` | GET | Import/coupling analysis |

### Scan & Actions

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/audit/scan` | POST | Trigger a full scan |
| `/api/audit/scan/<id>` | GET | Check scan progress |
| `/api/audit/system/deep-detect` | POST | Extended tool discovery |
| `/api/audit/data-status` | POST | Check analysis freshness |
| `/api/audit/data-usage` | GET | Data usage statistics |
| `/api/audit/service-status` | POST | Service availability check |

### Staging

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/audits/pending` | GET | List pending staged audits |
| `/api/audits/pending/<id>` | GET | Get specific staged audit |
| `/api/audits/save` | POST | Save staged audit |
| `/api/audits/discard` | POST | Discard staged changes |
| `/api/audits/saved` | GET | List saved snapshots |
| `/api/audits/saved/<id>` | GET | Get specific saved audit |
| `/api/audits/saved/<id>` | DELETE | Delete saved audit |

### Tool Install

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/audit/install-plan/cache` | POST | Cache an install plan |
| `/api/audit/install-cache/status` | GET | Check install cache |
| `/api/audit/install-cache/clear` | POST | Clear install cache |
| `/api/audit/install-cache/artifacts` | POST | Get install artifacts |
| `/api/audit/install-plan/execute` | POST | Execute install plan (async) |
| `/api/audit/install-plan/execute-sync` | POST | Execute install plan (sync) |

---

## CLI Commands

```bash
# Install tools from an audit install plan
./manage.sh audit install --plan <plan-file> [--dry-run]

# List available install plans
./manage.sh audit plans [--json]

# Resume a paused install
./manage.sh audit resume <plan-id>
```

---

## Architecture

```
src/core/services/audit/
├── __init__.py                # Public API
├── models.py                  # TypedDict models (L0Result, L1DepsResult, etc.)
├── catalog.py                 # Audit dimension catalog
├── scoring.py                 # Composite score calculation
├── narrative.py               # Human-readable analysis narratives
├── stack_context.py           # Stack-aware audit context
│
├── l0_detection.py            # L0: runtime/tool detection
├── l0_os_detection.py         # L0: OS identification
├── l0_hw_detectors.py         # L0: hardware detection
├── l0_deep_detectors.py       # L0: extended tool discovery
│
├── l1_classification.py       # L1: dependency + structure classification
├── l1_parsers.py              # L1: manifest parsing orchestration
│
├── l2_quality.py              # L2: code quality analysis
├── l2_repo.py                 # L2: repository health
├── l2_risk.py                 # L2: risk assessment
├── l2_structure.py            # L2: import/coupling analysis
│
└── parsers/                   # Language-specific manifest parsers
    ├── python_parser.py       #   pyproject.toml, requirements.txt, setup.py
    ├── js_parser.py           #   package.json
    ├── go_parser.py           #   go.mod
    ├── rust_parser.py         #   Cargo.toml
    ├── jvm_parser.py          #   pom.xml, build.gradle
    ├── c_parser.py            #   CMakeLists.txt
    ├── css_parser.py          #   CSS/template analysis
    ├── config_parser.py       #   Config file analysis
    ├── multilang_parser.py    #   Multi-language detection
    └── template_parser.py     #   Template/view analysis
```

---

## See Also

- [AUDIT_ARCHITECTURE.md](AUDIT_ARCHITECTURE.md) — Design document (layer model, scoring philosophy)
- [AUDIT_PLAN.md](AUDIT_PLAN.md) — Implementation plan (phases, milestones)
- [WEB_ADMIN.md](WEB_ADMIN.md) — Web dashboard overview
- [TOOL_INSTALL.md](TOOL_INSTALL.md) — Tool installation system
