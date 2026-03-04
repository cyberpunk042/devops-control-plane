# Core

> **435 files. 107,286 lines. The business logic of the DevOps Control Plane.**
>
> The core module contains all domain models, configuration loading, the
> execution engine, 29 service domains, use cases, persistence, reliability
> patterns, observability, and the data catalog registry. Both the CLI and
> the Web Admin delegate 100% of their logic to this layer.

---

## How It Works

The core module implements a layered architecture where each layer has a
clear responsibility and strict dependency direction:

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Core Architecture                             │
│                                                                      │
│  ┌─────────────┐                                                     │
│  │  use_cases/  │   ← Entry points: orchestrate full workflows       │
│  │  run, detect,│      Load config → detect → plan → execute         │
│  │  status,     │                                                    │
│  │  config_check│                                                    │
│  └──────┬───────┘                                                    │
│         │                                                            │
│  ┌──────▼───────┐                                                    │
│  │   engine/    │   ← Orchestration: action planning + execution     │
│  │   executor   │      Build actions → dispatch to adapters          │
│  └──────┬───────┘                                                    │
│         │                                                            │
│  ┌──────▼──────────────────────────────────────────────────────┐     │
│  │                       services/                              │     │
│  │   29 domain packages + facade modules                        │     │
│  │                                                              │     │
│  │   audit/        docker/       k8s/          tool_install/    │     │
│  │   backup/       docs_svc/     ledger/       trace/           │     │
│  │   changelog/    env/          metrics/      vault/           │     │
│  │   chat/         generators/   packages_svc/ wizard/          │     │
│  │   ci/           git/          pages/                         │     │
│  │   content/      devops/       pages_builders/                │     │
│  │   dns/          artifacts/    quality/                       │     │
│  │                 secrets/      security/                      │     │
│  │                 terraform/    testing/                       │     │
│  └──────┬──────────────────────────────────────────────────────┘     │
│         │                                                            │
│  ┌──────▼───────┐  ┌──────────────┐  ┌──────────────┐               │
│  │   models/    │  │   config/    │  │    data/     │               │
│  │   7 Pydantic │  │   loader,    │  │   20 JSON    │               │
│  │   types      │  │   stack_     │  │   catalogs   │               │
│  │              │  │   loader     │  │   + registry │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ persistence/ │  │ reliability/ │  │observability/│               │
│  │ state_file,  │  │ circuit_     │  │ logging,     │               │
│  │ audit store  │  │ breaker,     │  │ metrics,     │               │
│  │              │  │ retry_queue  │  │ health       │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
│                                                                      │
│  ┌──────────────┐                                                    │
│  │  context.py  │   ← Singleton: project root for the process       │
│  └──────────────┘                                                    │
└──────────────────────────────────────────────────────────────────────┘
```

### Data Flow: A Complete Request

```
User: "controlplane docker build"
    │
    ├─ CLI/Web parses command → calls use_case: run(...)
    │
    ├─ use_cases/run.py:
    │   ├─ config/loader.py → loads project.yml → Project model
    │   ├─ config/stack_loader.py → discovers stacks/ → Stack models
    │   ├─ services/detection.py → detects modules in project
    │   ├─ engine/executor.py:
    │   │   ├─ Plans Action from Stack capabilities
    │   │   ├─ Dispatches to AdapterRegistry
    │   │   │   └─ adapters/containers/docker.py → runs `docker build`
    │   │   └─ Collects Receipt (success/failure + output)
    │   └─ persistence/state_file.py → writes state.json
    │
    └─ Receipt returned to CLI/Web → formatted for user
```

### Configuration Loading

```
project.yml  ──→  config/loader.py  ──→  models/project.py  (Project)
                          │
stacks/*.yml ──→  config/stack_loader.py ──→  models/stack.py  (Stack)
                          │
                  Both loaded once, cached, passed to services
```

### Service Layer Pattern

Services follow a consistent internal pattern:

```
services/<domain>/
├── __init__.py    Re-exports (public API)
├── ops.py         Main operations (orchestrates lower-level modules)
├── actions.py     Mutating operations
├── detect.py      Detection/status checks
└── ...            Domain-specific modules
```

Many services also have **facade modules** at the `services/` top level
(e.g., `docker_ops.py`, `git_ops.py`) that re-export from the domain
package for backward compatibility.

---

## File Map

```
src/core/
├── __init__.py                         Module marker (1 line)
├── context.py                          Project root singleton (37 lines)
│
├── models/                             Domain models (7 files, 526 lines)
│   ├── __init__.py                     Re-exports all models
│   ├── action.py                       Action + Receipt (121 lines)
│   ├── module.py                       Module + ModuleHealth (54 lines)
│   ├── project.py                      Project + Environment + ExternalLinks (86 lines)
│   ├── stack.py                        Stack + StackCapability + DetectionRule (87 lines)
│   ├── state.py                        ProjectState + ModuleState + OperationRecord (108 lines)
│   └── template.py                     Template model (23 lines)
│
├── config/                             Configuration loading (3 files, 314 lines)
│   ├── __init__.py                     Module marker
│   ├── loader.py                       project.yml parser (112 lines)
│   └── stack_loader.py                 Stack YAML discovery & parsing (201 lines)
│
├── data/                               Static data catalogs (1 .py + 20 JSON, 298 lines)
│   ├── __init__.py                     DataRegistry class (298 lines)
│   └── catalogs/                       20 JSON catalog files
│       ├── api_spec_files.json         API spec file patterns
│       ├── card_labels.json            UI card display labels
│       ├── docker_defaults.json        Docker default configurations
│       ├── docker_options.json         Docker compose options
│       ├── env_files.json              Environment file patterns
│       ├── gitignore_patterns.json     Gitignore generation patterns
│       ├── health_weights.json         Health score weightings
│       ├── iac_providers.json          Infrastructure-as-Code providers
│       ├── infra_categories.json       Infrastructure categories
│       ├── infra_services.json         Infrastructure service types
│       ├── integration_graph.json      Service integration map
│       ├── k8s_kinds.json              Kubernetes resource kinds
│       ├── mesh_annotations.json       Service mesh annotations
│       ├── publish_targets.json        Deployment targets
│       ├── secret_file_patterns.json   Secret file detection patterns
│       ├── sensitive_files.json        Sensitive file patterns
│       ├── storage_classes.json        K8s storage class definitions
│       ├── terraform_backends.json     Terraform backend configs
│       ├── terraform_k8s.json          Terraform K8s provider config
│       └── terraform_providers.json    Terraform provider catalog
│
├── engine/                             Execution engine (2 files, 257 lines)
│   ├── __init__.py                     Module marker
│   └── executor.py                     Action planning + dispatch (256 lines)
│
├── use_cases/                          Top-level workflows (5 files, 586 lines)
│   ├── __init__.py                     Module marker
│   ├── run.py                          Full automation run (189 lines)
│   ├── detect.py                       Module discovery (119 lines)
│   ├── status.py                       Project status check (171 lines)
│   └── config_check.py                 Configuration validation (106 lines)
│
├── observability/                      Logging, metrics, health (4 files, 439 lines)
│   ├── __init__.py                     Module marker
│   ├── logging_config.py               Structured logging setup (105 lines)
│   ├── metrics.py                      Metric collection (169 lines)
│   └── health.py                       Health check aggregation (164 lines)
│
├── persistence/                        State storage (3 files, 227 lines)
│   ├── __init__.py                     Module marker
│   ├── state_file.py                   JSON state persistence (92 lines)
│   └── audit.py                        Audit data persistence (134 lines)
│
├── reliability/                        Fault tolerance (3 files, 373 lines)
│   ├── __init__.py                     Module marker
│   ├── circuit_breaker.py              Circuit breaker pattern (164 lines)
│   └── retry_queue.py                  Deferred retry mechanism (208 lines)
│
├── security/                           Security namespace (1 file, 1 line)
│   └── __init__.py                     Marker only
│
└── services/                           Business logic (404 files, 104,227 lines)
    ├── __init__.py                     Module marker
    ├── README.md                       Services overview
    │
    ├── [29 domain sub-packages]        See Services section below
    │
    └── [~60 facade/utility modules]    Top-level service files
```

---

## Sub-Package Documentation

### `context.py` — Project Root Singleton (37 lines)

Module-level singleton that stores the active project root. Set once at
startup by whichever entry point launches the app (CLI, Web, or tests).

| Function | Purpose |
|----------|---------|
| `set_project_root(path)` | Set the project root (called once at startup) |
| `get_project_root()` | Get the project root (returns `None` if unset) |

---

### `models/` — Domain Models (526 lines)

Pydantic models that define the shape of all domain data.

| Model | File | Lines | Purpose |
|-------|------|-------|---------|
| `Action` | `action.py` | 121 | Describes an operation to execute (adapter, action, params) |
| `Receipt` | `action.py` | — | Result of execution (success, output, error, timing) |
| `Module` | `module.py` | 54 | A detected project module (path, stack, health) |
| `ModuleHealth` | `module.py` | — | Health metrics for a module |
| `Project` | `project.py` | 86 | Top-level project config (name, description, modules) |
| `Environment` | `project.py` | — | Environment definition (name, vars) |
| `ExternalLinks` | `project.py` | — | Project external links (repo, docs, etc.) |
| `Stack` | `stack.py` | 87 | Technology stack definition (capabilities, detection rules) |
| `StackCapability` | `stack.py` | — | What a stack can do (build, test, deploy, etc.) |
| `DetectionRule` | `stack.py` | — | How to auto-detect a stack (file patterns, content) |
| `ProjectState` | `state.py` | 108 | Persistent state (last run, module states, history) |
| `ModuleState` | `state.py` | — | Per-module persistent state |
| `OperationRecord` | `state.py` | — | Audit log of an executed operation |
| `Template` | `template.py` | 23 | File generation template |

---

### `config/` — Configuration Loading (314 lines)

| File | Lines | Purpose |
|------|-------|---------|
| `loader.py` | 112 | Reads `project.yml`, finds project files, returns `Project` model |
| `stack_loader.py` | 201 | Discovers and loads stack YAML files from `stacks/` directory |

**Key functions:**

| Function | File | Purpose |
|----------|------|---------|
| `load_project(path)` | `loader.py` | Parse project.yml → `Project` |
| `find_project_file()` | `loader.py` | Walk up directories looking for project.yml |
| `discover_stacks(stacks_dir)` | `stack_loader.py` | Load all `.yml` files → `dict[str, Stack]` |

---

### `data/` — Data Catalog Registry (298 lines + 20 JSON catalogs)

The `DataRegistry` class provides lazy-loaded, cached access to all 20
static JSON catalogs.

**Catalog inventory:**

| Catalog | File | Content |
|---------|------|---------|
| Docker defaults | `docker_defaults.json` | Default Dockerfile templates |
| Docker options | `docker_options.json` | Compose file options |
| K8s kinds | `k8s_kinds.json` | Kubernetes resource types |
| Terraform providers | `terraform_providers.json` | Provider configurations |
| Terraform backends | `terraform_backends.json` | Backend configurations |
| Health weights | `health_weights.json` | Score calculation weights |
| Gitignore patterns | `gitignore_patterns.json` | .gitignore generation rules |
| Secret patterns | `secret_file_patterns.json` | Secret file detection |
| Sensitive files | `sensitive_files.json` | Sensitive file patterns |
| Infrastructure | `infra_services.json` | Service type definitions |
| Card labels | `card_labels.json` | UI card display text |
| Integration graph | `integration_graph.json` | Service dependency map |
| ... | *(20 total)* | |

**Usage pattern:**

```python
from src.core.data import get_registry

registry = get_registry()
patterns = registry.secret_patterns    # frozenset
services = registry.infra_services     # list[dict]
js_data  = registry.to_js_dict()       # For web template injection
```

---

### `engine/` — Execution Engine (257 lines)

The central orchestration loop that transforms actions into results.

| Component | Lines | Purpose |
|-----------|-------|---------|
| `Executor` class | 256 | Takes an automation request, resolves targets, builds actions from stack capabilities, dispatches through the adapter registry, collects receipts |

**Execution flow:**

```
Executor.run(request)
    │
    ├─ Resolve target modules (by name, by stack, or all)
    │
    ├─ For each module:
    │   ├─ Get effective stack
    │   ├─ Build Action from StackCapability + request params
    │   ├─ Dispatch to AdapterRegistry
    │   │   └─ Registry finds adapter → calls adapter.execute(action, context)
    │   │       └─ Returns Receipt
    │   └─ Collect Receipt into results
    │
    └─ Return list[Receipt]
```

---

### `use_cases/` — Top-Level Workflows (586 lines)

Use cases are the full vertical slices from user intent to result.

| Use Case | File | Lines | Purpose |
|----------|------|-------|---------|
| `run` | `run.py` | 189 | Full automation: load config → detect → plan → execute → persist |
| `detect` | `detect.py` | 119 | Module discovery: find and classify project modules |
| `status` | `status.py` | 171 | Project status: aggregate health across all modules |
| `config_check` | `config_check.py` | 106 | Configuration validation: verify project.yml + stacks |

---

### `observability/` — Logging, Metrics, Health (439 lines)

| File | Lines | Purpose |
|------|-------|---------|
| `logging_config.py` | 105 | Structured logging setup (console + file handlers, log levels) |
| `metrics.py` | 169 | Metric collection and aggregation (execution counts, timings) |
| `health.py` | 164 | Health check aggregation (adapter availability, service status) |

---

### `persistence/` — State Storage (227 lines)

| File | Lines | Purpose |
|------|-------|---------|
| `state_file.py` | 92 | Read/write `state.json` — project state persistence (last run, history) |
| `audit.py` | 134 | Audit data persistence — store/retrieve scan results |

---

### `reliability/` — Fault Tolerance (373 lines)

| File | Lines | Purpose |
|------|-------|---------|
| `circuit_breaker.py` | 164 | Circuit breaker pattern: prevents cascading failures when adapters fail repeatedly |
| `retry_queue.py` | 208 | Deferred retry mechanism: queues failed operations for later retry |

**Circuit breaker states:**

```
CLOSED  ───fail──→  OPEN  ───timeout──→  HALF_OPEN  ───success──→  CLOSED
                     │                       │
                     └── (reject calls) ◄────┘── (fail again)
```

---

### `services/` — Business Logic (404 files, 104,227 lines)

The services layer contains 99% of the core module's code. It's organized
into **29 domain sub-packages** and **~60 facade/utility modules** at the
top level.

#### Service Domain Summary

| Domain | Files | Lines | Purpose |
|--------|-------|-------|---------|
| `artifacts/` | 25 | 6,613 | Release artifact management (upload, download, CRUD) |
| `audit/` | 30 | 14,305 | Code quality analysis (L0/L1/L2 pipelines, scoring) |
| `backup/` | 6 | 1,759 | Project backup and restore |
| `changelog/` | 4 | 1,081 | Changelog generation from git history |
| `chat/` | 8 | 2,410 | Chat threads, messages, git sync |
| `ci/` | 3 | 1,163 | CI/CD pipeline generation |
| `content/` | 10 | 3,763 | Content file management (encrypt, optimize, release) |
| `devops/` | 3 | 1,601 | DevOps card detection + caching |
| `dns/` | 2 | 569 | DNS/CDN operations |
| `docker/` | 6 | 2,032 | Docker & Compose operations |
| `docs_svc/` | 3 | 697 | Documentation coverage + generation |
| `env/` | 3 | 685 | Environment file management |
| `generators/` | 11 | 1,975 | File generation (Dockerfile, compose, K8s, etc.) |
| `git/` | 7 | 3,560 | Git operations + GitHub integration |
| `k8s/` | 19 | 8,620 | Kubernetes operations + manifest generation |
| `ledger/` | 4 | 1,543 | Activity ledger (audit trail) |
| `metrics/` | 2 | 507 | Project health metrics |
| `packages_svc/` | 3 | 804 | Package management (pip, npm, etc.) |
| `pages/` | 8 | 2,387 | Documentation site pipeline |
| `pages_builders/` | 12 | 5,831 | Static site generators (Docusaurus, MkDocs) |
| `quality/` | 2 | 538 | Code quality tools (lint, format, typecheck) |
| `secrets/` | 4 | 937 | Secrets management (GitHub, env) |
| `security/` | 5 | 1,127 | Security scanning + posture |
| `terraform/` | 4 | 1,459 | Terraform operations |
| `testing/` | 3 | 854 | Test framework detection + execution |
| `tool_install/` | 134 | 26,677 | Tool installation system (94 tools, recipes, remediation) |
| `trace/` | 3 | 833 | Request tracing + recording |
| `vault/` | 5 | 2,074 | AES-256-GCM encryption + vault operations |
| `wizard/` | 9 | 2,638 | Setup wizard logic |

#### Top-Level Facade Modules

Many services have facade files at the `services/` top level that re-export
from their domain package. This provides backward-compatible import paths.

**Pattern:**

```python
# services/docker_ops.py (9 lines — pure re-export)
from src.core.services.docker.ops import *
```

**Notable non-facade top-level files:**

| File | Lines | Purpose |
|------|-------|---------|
| `detection.py` | 300 | Project module detection (find modules, match stacks) |
| `config_ops.py` | 333 | Project configuration CRUD |
| `event_bus.py` | 360 | Pub/sub event system (SSE events, state changes) |
| `dev_scenarios.py` | 902 | Development scenario simulation |
| `project_probes.py` | 485 | Deep project inspection (structure, patterns) |
| `run_tracker.py` | 379 | Track automation run history |
| `smart_folders.py` | 303 | Module tree resolution for UI |
| `md_transforms.py` | 217 | Markdown transformation utilities |
| `audit_staging.py` | 333 | Audit scan staging pipeline |
| `stream_subprocess.py` | 192 | Stream subprocess output in real-time |
| `terminal_ops.py` | 350 | Terminal management for web admin |
| `server_lifecycle.py` | 163 | Graceful server shutdown |
| `staleness_watcher.py` | 123 | File change detection (mtime polling) |
| `identity.py` | 116 | Project identity management |
| `tool_requirements.py` | 67 | Declare required tools for operations |

---

## Dependency Graph

### Internal Dependencies

```
context.py          ← Imported by everything that needs project root
    ▲
    │
models/             ← Pure data types, no imports from other core packages
    ▲
    │
config/             ← Imports models/ (returns Project, Stack)
    ▲
    │
data/               ← Self-contained (reads JSON catalogs)
    │
    │
persistence/        ← Imports models/ (reads/writes ProjectState)
    ▲
    │
reliability/        ← Self-contained (circuit breaker, retry queue)
    ▲
    │
observability/      ← Self-contained (logging, metrics, health)
    │
    │
engine/             ← Imports models/, adapters (AdapterRegistry)
    ▲
    │
services/           ← Imports models/, config/, data/, persistence/,
    ▲                   reliability/, observability/, context
    │
use_cases/          ← Imports services/, config/, models/, engine/,
                        adapters (AdapterRegistry registration)
```

### External Dependencies (to src/adapters)

```
core/engine/executor.py     → adapters.registry.AdapterRegistry
core/use_cases/run.py       → adapters.registry.AdapterRegistry
                               (registers all adapters at startup)
core/reliability/            → Used BY adapters.registry (circuit breaker)
```

### Service Interdependencies

Most services are independent of each other. Key cross-service imports:

```
services/devops/      → services/detection, services/{all domain services}
services/audit/       → services/tool_install/, services/detection
services/wizard/      → services/detection, services/devops/
services/pages_builders/ → services/pages/, services/audit/ (audit directive)
services/git/         → services/vault/ (for encrypted commits)
```

---

## Consumers

| Consumer | What It Uses |
|----------|-------------|
| `src/ui/cli/` | Imports service functions directly (thin wrappers) |
| `src/ui/web/routes/` | Imports service functions via Flask route handlers |
| `src/adapters/` | Uses `models/action.py` (Action, Receipt) |
| `tests/` | Tests services, models, config, engine, use_cases |

Both CLI and Web call the **same service functions** with the same arguments.
The core module is completely independent of its consumers.

---

## Design Decisions

### Why Pydantic Models?

All domain types use Pydantic for:

- **Validation** — config files are validated at load time; malformed YAML fails
  fast with clear error messages
- **Serialization** — models convert to/from JSON for persistence and API responses
- **Documentation** — type annotations serve as living documentation
- **Immutability** — `frozen=True` on critical models prevents accidental mutation

### Why a Data Registry Instead of Inline Constants?

Static data (K8s kinds, Terraform providers, Docker defaults) lives in JSON
catalogs rather than Python code because:

- **Non-developers can edit catalogs** — JSON is universally understood
- **No Python required to add a provider** — just edit the JSON file
- **Cached at startup** — `@cached_property` ensures catalogs are loaded once
- **Web injection** — `to_js_dict()` serializes catalogs directly into HTML
  templates, avoiding a separate API call

### Why Facade Modules?

Top-level files like `docker_ops.py` that simply `from .docker.ops import *`
exist for backward compatibility. When services were extracted from monolithic
files into domain packages, the old import paths were preserved:

```python
# Before extraction:
from src.core.services.docker_ops import docker_build

# After extraction (still works):
from src.core.services.docker_ops import docker_build  # → re-export

# New canonical path:
from src.core.services.docker.ops import docker_build
```

### Why Circuit Breakers in Core?

The circuit breaker lives in `core/reliability/` (not in adapters) because:

- It's a **domain-agnostic pattern** — any component can use it
- The `AdapterRegistry` in `src/adapters/` imports and uses it, but the
  pattern itself doesn't know about adapters
- It could protect any unreliable service call (API, database, etc.)

### Why Module-Level Singleton for Context?

`context.py` uses a simple module-level variable instead of a class because:

- **One project per process** — the control plane always operates on one project
- **Thread-safe reads** — Python's GIL makes simple reference reads safe
- **Testable** — tests call `set_project_root(tmp_path)` in fixtures
- **No dependency injection needed** — services import `get_project_root()`
  directly; no DI framework required

### Why 29 Service Domains?

Each service domain maps 1:1 to a **feature boundary**:

- `docker/` = Docker operations
- `k8s/` = Kubernetes operations
- `vault/` = Encryption operations

This alignment means:

- **Changes to Docker never touch K8s code** and vice versa
- **Each domain has its own README** (34 exist today)
- **New features = new domain packages** (no existing code modified)
- **Domains can be independently tested** with focused test files

### Why the Engine is Separate from Services?

The `engine/executor.py` sits between use cases and services because:

- **Services don't know about each other** — the engine coordinates them
- **The action→receipt loop is domain-agnostic** — it doesn't care if it's
  running Docker or Terraform
- **Testable in isolation** — mock the adapter registry, test the planning logic

---

## Per-Package Line Counts

### Infrastructure Packages

| Package | Files | Lines | Description |
|---------|-------|-------|-------------|
| `context.py` | 1 | 37 | Project root singleton |
| `models/` | 7 | 526 | Domain models (Pydantic) |
| `config/` | 3 | 314 | Configuration loading |
| `data/` | 1+20 | 298 | Data catalog registry + JSON catalogs |
| `engine/` | 2 | 257 | Execution engine |
| `use_cases/` | 5 | 586 | Top-level workflows |
| `observability/` | 4 | 439 | Logging, metrics, health |
| `persistence/` | 3 | 227 | State persistence |
| `reliability/` | 3 | 373 | Circuit breaker, retry queue |
| `security/` | 1 | 1 | Namespace marker |
| **Total** | **30** | **3,058** | |

### Service Packages (Top 10 by Size)

| Package | Files | Lines | Description |
|---------|-------|-------|-------------|
| `tool_install/` | 134 | 26,677 | Tool installation system (94 tools) |
| `audit/` | 30 | 14,305 | Code quality analysis pipeline |
| `k8s/` | 19 | 8,620 | Kubernetes operations |
| `artifacts/` | 25 | 6,613 | Release artifact management |
| `pages_builders/` | 12 | 5,831 | Static site generators |
| `git/` | 7 | 3,560 | Git + GitHub operations |
| `content/` | 10 | 3,763 | Content management |
| `wizard/` | 9 | 2,638 | Setup wizard logic |
| `chat/` | 8 | 2,410 | Chat system |
| `pages/` | 8 | 2,387 | Documentation site pipeline |

### Grand Total

| Component | Files | Lines |
|-----------|-------|-------|
| Infrastructure packages | 30 | 3,058 |
| Service packages | 338 | 99,043 |
| Top-level facade/utility modules | 67 | 5,184 |
| **Total** | **435** | **107,286** |

---

## Existing Sub-Module Documentation

34 README files already exist within core, primarily in the services layer:

| README | Location |
|--------|----------|
| Services overview | `services/README.md` |
| Per-domain (22) | `services/{domain}/README.md` |
| Tool install system (8) | `services/tool_install/*/README.md` |
| Generators | `services/generators/README.md` |
| Pages builders | *(covered in services/README.md)* |

These sub-module READMEs provide detailed per-file documentation within
each service domain. This README provides the **module-level overview**
of how all sub-packages fit together.
