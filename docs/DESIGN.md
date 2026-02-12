# DevOps Control Plane — Design Document

> **Status:** Living document — reflects design philosophy and architectural decisions  
> **Origin:** Distilled from the architectural vision and proven patterns of the
> `continuity-orchestrator` (22k+ lines, 89 modules, full operational stack).  
> **Note:** For the current file layout and implementation status, see
> [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Table of Contents

1. [Vision](#1-vision)
2. [Core Principles](#2-core-principles)
3. [Architecture Overview](#3-architecture-overview)
4. [Layer Specification](#4-layer-specification)
   - 4.1 [project.yml — Canonical Truth](#41-projectyml--canonical-truth)
   - 4.2 [core/ — Domain & Use-Cases](#42-core--domain--use-cases)
   - 4.3 [adapters/ — Tool Bindings](#43-adapters--tool-bindings)
   - 4.4 [ui/ — Interfaces](#44-ui--interfaces)
   - 4.5 [modules/ — Project Components](#45-modules--project-components)
   - 4.6 [stacks/ — Technology Knowledge](#46-stacks--technology-knowledge)
   - 4.7 [automations/ — Named Capabilities](#47-automations--named-capabilities)
   - 4.8 [templates/ — File Shape Only](#48-templates--file-shape-only)
   - 4.9 [state/ — Observed Reality](#49-state--observed-reality)
   - 4.10 [docs/](#410-docs)
   - 4.11 [scripts/](#411-scripts)
   - 4.12 [.proj/ — Internal Metadata](#412-proj--internal-metadata)
5. [Invariant Infrastructure](#5-invariant-infrastructure)
   - 5.1 [Reliability](#51-reliability)
   - 5.2 [Observability](#52-observability)
   - 5.3 [Security & Vault](#53-security--vault)
   - 5.4 [Persistence](#54-persistence)
6. [Engine Design](#6-engine-design)
7. [Adapter Protocol](#7-adapter-protocol)
8. [Policy System](#8-policy-system)
9. [Three-Interface Parity](#9-three-interface-parity)
10. [Admin Console Architecture](#10-admin-console-architecture)
11. [Deployment & Infrastructure](#11-deployment--infrastructure)
12. [Plugin & Extension Model](#12-plugin--extension-model)
13. [Growth Rules](#13-growth-rules)
14. [Technology Choices](#14-technology-choices)
15. [Appendix: Pattern Lineage](#appendix-pattern-lineage)

---

## 1. Vision

Build a **general-purpose project control plane** — a scaffold that manages
project infrastructure, modules, stacks, and automations through a unified
domain model.

The control plane is **not an application**. It is a *meta-tool*: a structured
way to discover what a project is, what it needs, and how to act on it — through
any interface (CLI, Web, TUI), backed by pluggable tool bindings, driven by
declarative policy.

### What it replaces

The fragmented reality of most projects:
- Scattered shell scripts with duplicated logic
- CI/CD configs that encode business rules
- Manual environment management
- Tool-specific knowledge locked in people's heads
- No unified view of project state

### What it enables

- **One model, many interfaces** — CLI, Web, and TUI all drive the same engine
- **Policy as data, engine as code** — behavior is configured, not hardcoded
- **Pluggable tool bindings** — swap adapters without touching domain logic
- **Deterministic operations** — same input → same output, always
- **Progressive complexity** — start simple, grow without refactoring

### Proven lineage

This design is not hypothetical. It is extracted from a production system
(`continuity-orchestrator`: 22k+ lines of Python, 550k+ of web UI, 639 tests,
13 adapters, 5 GitHub Actions workflows, Docker deployment, Cloudflare Workers,
multi-repo mirroring, content encryption, media optimization pipeline) that
successfully applies these exact patterns to a specific use case.

The control plane generalizes those patterns so the same scaffold can drive
**any** project domain — by swapping the policy, adapters, and modules.

---

## 2. Core Principles

### 2.1 Everything is a domain object first

Scripts, templates, CI/CD, infrastructure, and tools are *expressions* of
intent — never the source of truth. If something cannot be expressed as a
domain concept, it does not belong in the system.

### 2.2 Determinism

Given the same project state and policy, the engine will always produce the same
result. No randomness, no implicit external dependencies in core logic.

### 2.3 Idempotency

Operations track execution status via receipts. Re-running an operation will not
re-execute already-completed actions.

### 2.4 Monotonic progress

State machines progress forward. A state cannot regress without an explicit
reset operation.

### 2.5 Auditability

Every operation writes to an append-only ledger with full context: what ran,
what changed, why.

### 2.6 Three-layer touch rule

If a change requires touching three or more architectural layers (e.g., core +
adapters + ui), it is a **design error**. New capabilities must emerge as
branches, never as root mutations.

### 2.7 Configuration defines wiring

The control plane is generic. The `project.yml` and stack definitions wire it to
a specific use case. Changing the domain means changing configuration, not code.

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INTERFACES (thin)                             │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────┐ │
│  │  manage.sh   │  │  CLI (click) │  │  Web Admin (Flask SPA)     │ │
│  │  (TUI menu)  │  │  ui/cli/     │  │  ui/web/                   │ │
│  └──────┬───────┘  └──────┬───────┘  └────────────┬───────────────┘ │
│         │                 │                        │                  │
├─────────┴─────────────────┴────────────────────────┴─────────────────┤
│                        CORE DOMAIN (pure)                            │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  Engine         Services          Models         Use-Cases      │ │
│  │  (run loop)     (detection,       (Project,      (detect,       │ │
│  │                  planning,         Module,         scaffold,     │ │
│  │                  validation,       Stack,          automate,     │ │
│  │                  graph)            Action,         graph)        │ │
│  │                                    Environment)                 │ │
│  └─────────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────┤
│                        POLICY (data)                                 │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐ │
│  │  project.yml   │  │  stacks/*.yml  │  │  automations/*.yml     │ │
│  │  (identity)    │  │  (tech rules)  │  │  (capabilities)        │ │
│  └────────────────┘  └────────────────┘  └────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────┤
│                       ADAPTER LAYER                                  │
│  ┌──────┐ ┌────────┐ ┌────────┐ ┌──────┐ ┌──────┐ ┌──────────────┐│
│  │ git  │ │ docker │ │ kubectl│ │ helm │ │ shell│ │ filesystem   ││
│  └──────┘ └────────┘ └────────┘ └──────┘ └──────┘ └──────────────┘│
│  ┌──────┐ ┌────────┐ ┌────────┐ ┌──────┐ ┌──────┐ ┌──────────────┐│
│  │python│ │  node  │ │  go    │ │ rust │ │ mock │ │ ... (custom) ││
│  └──────┘ └────────┘ └────────┘ └──────┘ └──────┘ └──────────────┘│
├──────────────────────────────────────────────────────────────────────┤
│                   INVARIANT INFRASTRUCTURE                           │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐ │
│  │ Reliability   │ │ Observability│ │ Security     │ │ Persistence│ │
│  │ (circuit      │ │ (health,     │ │ (vault,      │ │ (state,    │ │
│  │  breaker,     │ │  metrics,    │ │  encryption, │ │  audit)    │ │
│  │  retry queue) │ │  logging)    │ │  rate-limit) │ │            │ │
│  └──────────────┘ └──────────────┘ └──────────────┘ └────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

### Data flow

```
project.yml + stacks/ + state/
        │
        ▼
   ┌──────────┐
   │  Engine   │  ← triggered by CLI, Web, cron, or manage.sh
   │  (detect  │
   │   plan    │
   │   act)    │
   └─────┬────┘
         │
    ┌────┴────┐
    ▼         ▼
 Adapters   State
 (side      (next
  effects)   snapshot)
    │         │
    ▼         ▼
 Receipts   Audit
 (results)  (ledger)
```

---

## 4. Layer Specification

### 4.1 project.yml — Canonical Truth

The single file that defines *what the project is*.

```yaml
# project.yml — Canonical Truth
version: 1

project:
  name: my-platform
  description: "Multi-service platform with API, frontend, and workers"
  repository: github.com/org/my-platform

# What domains does this project span?
domains:
  - service        # backend services
  - library        # shared libraries
  - infra          # infrastructure-as-code
  - ops            # operational tooling
  - docs           # documentation

# What environments exist?
environments:
  - name: dev
    description: "Local development"
    default: true
  - name: staging
    description: "Pre-production"
  - name: production
    description: "Live"

# Declared modules (what the project contains)
modules:
  - name: api
    path: services/api
    domain: service
    stack: python-fastapi

  - name: frontend
    path: services/frontend
    domain: service
    stack: node-nextjs

  - name: worker
    path: services/worker
    domain: service
    stack: python-celery

  - name: shared-lib
    path: libs/common
    domain: library
    stack: python-lib

  - name: infra
    path: infrastructure
    domain: infra
    stack: terraform

  - name: docs
    path: docs
    domain: docs
    stack: mkdocs

# External system links
external:
  ci: github-actions
  registry: ghcr.io/org/my-platform
  monitoring: grafana.internal
```

**Rules:**
- Discovery may enrich this model but must never contradict it
- If a module is not declared here, it does not exist to the system
- External links are informational; adapters resolve them at runtime

### 4.2 core/ — Domain & Use-Cases (Tool-Free)

The heart of the system. **Zero** shell execution, **zero** direct tool imports.

```
core/
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── project.py          # Project, Environment
│   ├── module.py            # Module, ModuleDescriptor
│   ├── stack.py             # Stack, StackCapability
│   ├── action.py            # Action, ActionResult, Receipt
│   ├── automation.py        # Automation, Step, Prerequisite
│   └── state.py             # ProjectState (root state model)
│
├── services/
│   ├── __init__.py
│   ├── detection.py         # Detect stacks, versions, capabilities
│   ├── planning.py          # Build execution plans from automations
│   ├── validation.py        # Validate project config + state
│   └── graph.py             # Build dependency graphs
│
├── engine/
│   ├── __init__.py
│   ├── runner.py            # Main execution loop (like tick.py)
│   ├── evaluator.py         # Rule/condition evaluation
│   └── resolver.py          # Resolve templates, variables, references
│
└── use_cases/
    ├── __init__.py
    ├── detect.py            # Discover project shape
    ├── scaffold.py          # Generate project structure
    ├── automate.py          # Run named automations
    ├── status.py            # Compute comprehensive status
    └── graph.py             # Generate dependency/architecture graphs
```

**The `models/` layer** uses Pydantic for strong typing and validation — proven
in the orchestrator with `State`, `Policy`, `Receipt`, etc.

**The `services/` layer** contains pure business logic that operates on models.
No side effects. No tool calls.

**The `engine/` layer** orchestrates execution phases:

```
1. Initialize      → Load project.yml + state
2. Detect          → Discover modules, stacks, versions
3. Evaluate        → Match conditions against state
4. Plan            → Determine actions needed
5. Execute         → Dispatch actions through adapters
6. Persist         → Save state + audit entry
```

This mirrors the orchestrator's 8-phase tick lifecycle, generalized.

**The `use_cases/` layer** provides high-level entry points that the UI layers
call. Each use case is a function that takes models and returns results.
Use cases compose services and engine operations — they are the **only** public
API of core/.

### 4.3 adapters/ — Tool Bindings

Adapters translate domain intent into real-world effects.

```
adapters/
├── __init__.py
├── base.py              # Abstract Adapter protocol
├── registry.py          # Adapter discovery, lookup, mock swap
├── mock.py              # Universal mock adapter for testing
│
├── vcs/
│   ├── git.py           # git operations
│   └── github.py        # GitHub API (repos, secrets, workflows)
│
├── containers/
│   ├── docker.py        # docker / docker compose
│   ├── podman.py        # podman (alternative)
│   └── registry.py      # container registry operations
│
├── orchestration/
│   ├── kubectl.py       # kubernetes CLI
│   └── helm.py          # helm chart operations
│
├── iac/
│   ├── terraform.py     # terraform
│   └── ansible.py       # ansible
│
├── languages/
│   ├── python.py        # python/pip/poetry/uv
│   ├── node.py          # node/npm/yarn/pnpm
│   ├── go.py            # go modules
│   └── rust.py          # cargo
│
├── shell/
│   ├── command.py       # generic shell command execution
│   └── filesystem.py    # file/directory operations
│
└── notification/
    ├── email.py         # email notifications
    ├── webhook.py       # generic webhooks
    └── slack.py         # slack integration
```

**The Adapter Protocol** (from `base.py`):

```python
class Adapter(ABC):
    """Abstract base class for all adapters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique adapter identifier (e.g., 'git', 'docker')."""

    @abstractmethod
    def capabilities(self) -> list[str]:
        """What this adapter can do (e.g., ['clone', 'commit', 'push'])."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the underlying tool is installed and accessible."""

    @abstractmethod
    def version(self) -> str | None:
        """Get the tool version, or None if not available."""

    @abstractmethod
    def validate(self, context: ExecutionContext) -> tuple[bool, str]:
        """Validate that the action can be executed. Returns (ok, error)."""

    @abstractmethod
    def execute(self, context: ExecutionContext) -> Receipt:
        """Execute the action and return a receipt. Never raises."""
```

**Key properties** (proven in the orchestrator):

- **Receipts, not exceptions**: `execute()` always returns a `Receipt` with
  success/failure details. The caller decides what to do with failures.
- **Mock mode**: `AdapterRegistry` can swap all adapters to mocks with a single
  flag. Essential for testing and dry-runs.
- **Capability reporting**: Adapters declare what they can do. The engine uses
  this for validation before execution.
- **Version awareness**: Adapters report their tool version. Stacks can declare
  version constraints.

### 4.4 ui/ — Interfaces (Thin Only)

```
ui/
├── cli/
│   ├── __init__.py
│   ├── main.py          # Click group, entrypoint
│   ├── status.py        # status, health
│   ├── detect.py        # detect modules/stacks
│   ├── automate.py      # run automations
│   ├── scaffold.py      # generate project structure
│   ├── config.py        # check/validate config
│   └── graph.py         # generate dependency graphs
│
├── web/
│   ├── __init__.py
│   ├── server.py        # Flask app factory
│   ├── routes_core.py   # Dashboard, status API
│   ├── routes_*.py      # Feature-specific blueprints
│   ├── static/
│   │   └── css/
│   │       └── admin.css
│   └── templates/
│       ├── index.html
│       ├── partials/    # HTML structure
│       └── scripts/     # JS logic (shared <script> block pattern)
│
└── tui/
    └── (future: Rich/Textual-based TUI)
```

**Iron rule**: No business logic. No direct tool calls. All actions route through
core use-cases. CLI, Web, and TUI must remain **functionally equivalent**.

The web layer follows the orchestrator's proven architecture:
- **Blueprint-per-domain** (routes_core, routes_docker, routes_git, etc.)
- **Single-page app** via server-side Jinja2 rendering
- **Shared `<script>` block** pattern for JS modules
- **Partials for HTML, scripts for logic** — strict separation
- **Polling-based reactivity** for live status updates

### 4.5 modules/ — Project Components

Represents the user's actual project structure. Each module is a self-contained
unit with no global assumptions.

```
modules/
├── api/
│   ├── module.yml       # Module descriptor
│   ├── src/             # Module's own source
│   └── ...
│
├── frontend/
│   ├── module.yml
│   └── ...
│
└── worker/
    ├── module.yml
    └── ...
```

**Module descriptor** (`module.yml`):

```yaml
name: api
domain: service
stack: python-fastapi
version: 1.2.0

dependencies:
  - shared-lib

environments:
  dev:
    port: 8000
    debug: true
  production:
    replicas: 3
    port: 80
```

Modules are classified by domain: `service`, `library`, `infra`, `ops`, `docs`.

### 4.6 stacks/ — Technology Knowledge

Stacks define *how a kind of module behaves*. They are the **reusable
intelligence** of the system.

```
stacks/
├── python-fastapi/
│   ├── stack.yml            # Stack definition
│   ├── detection.yml        # How to detect this stack
│   ├── automations.yml      # What this stack can do
│   └── defaults/            # Default configurations
│       ├── Dockerfile
│       ├── pyproject.toml
│       └── .github/
│
├── node-nextjs/
│   ├── stack.yml
│   ├── detection.yml
│   ├── automations.yml
│   └── defaults/
│
├── terraform/
│   └── ...
│
└── docker-compose/
    └── ...
```

**Stack definition** (`stack.yml`):

```yaml
name: python-fastapi
description: "Python FastAPI web service"
domain: service

# What tool adapters does this stack require?
requires:
  - python >= 3.11
  - docker
  - pip | poetry | uv

# How to detect this stack in an existing module
detection:
  files:
    any_of:
      - pyproject.toml
      - setup.py
      - requirements.txt
  content:
    pyproject.toml:
      contains: "fastapi"

# What automations are available for this stack
automations:
  - install
  - lint
  - test
  - build
  - serve
  - deploy

# Version constraints for adapters
constraints:
  python:
    min: "3.11"
  docker:
    min: "24.0"
```

**Key insight**: Stacks are reusable across modules and projects. A `python-fastapi`
stack works the same way whether it's in project A or project B. Only the
module-specific configuration changes.

### 4.7 automations/ — Named Capabilities

Automations represent **what can be done**, not scripts. Each automation is a
declarative definition of prerequisites, steps, and expected outcomes.

```
automations/
├── install.yml
├── lint.yml
├── test.yml
├── build.yml
├── deploy.yml
├── scaffold.yml
└── custom/
    └── release.yml
```

**Automation definition** (`build.yml`):

```yaml
name: build
description: "Build all modules for a given environment"

# What must be true before this can run
prerequisites:
  - adapter: docker
    capability: build
  - state: modules_detected

# Ordered steps
steps:
  - name: validate
    action: core.validate
    params:
      scope: build

  - name: install_deps
    action: stack.install
    for_each: module
    when:
      module.stack.has: install

  - name: build_images
    action: adapter.docker.build
    for_each: module
    when:
      module.domain: service
    params:
      tag: "{{ module.name }}:{{ env.name }}"

  - name: tag_release
    action: adapter.git.tag
    when:
      env.name: production
    params:
      tag: "v{{ project.version }}"

# What this achieves
produces:
  - docker_images
  - build_receipts

# Failure handling
on_failure:
  retry:
    max_attempts: 2
    backoff_seconds: 30
  on_exhausted:
    record_failure: true
    continue: false
```

**This enables:**
- **Dry-runs**: execute the plan without side effects
- **Dependency graphs**: visualize what runs and in what order
- **Cross-interface reuse**: the same automation runs from CLI, Web, or CI
- **Partial execution**: resume from a failed step
- **Receipt tracking**: know exactly what happened and when

### 4.8 templates/ — File Shape Only

Templates are **dumb**. They render files, contain no detection, no logic,
and never call tools.

```
templates/
├── dockerfile/
│   ├── python.Dockerfile.j2
│   ├── node.Dockerfile.j2
│   └── multi-stage.Dockerfile.j2
│
├── ci/
│   ├── github-actions.yml.j2
│   └── gitlab-ci.yml.j2
│
├── config/
│   ├── pyproject.toml.j2
│   ├── package.json.j2
│   └── docker-compose.yml.j2
│
└── docs/
    ├── readme.md.j2
    └── contributing.md.j2
```

Logic belongs in stacks or core use-cases. Templates are Jinja2 files that
receive a context dict and produce output. Nothing more.

### 4.9 state/ — Observed Reality (Generated)

Contains cached, generated, or discovered data. This directory is **disposable
and reproducible** — delete it and the engine will regenerate everything.

```
state/
├── current.json         # Current project state snapshot
├── detected/
│   ├── modules.json     # Detected modules and stacks
│   ├── versions.json    # Tool/adapter versions
│   └── graph.json       # Dependency graph snapshot
│
├── cache/
│   ├── checksums.json   # File checksums for change detection
│   └── env_checks.json  # Environment verification results
│
└── audit/
    └── ledger.ndjson    # Append-only execution log
```

The `current.json` is the root state model — equivalent to the orchestrator's
`state/current.json`. It captures everything about the current project state
in a single Pydantic-serialized document.

### 4.10 docs/

Documentation is part of the system, not an afterthought.

```
docs/
├── DESIGN.md            # This document
├── ARCHITECTURE.md      # Runtime architecture diagrams
├── QUICKSTART.md        # 5-minute setup
├── STACKS.md            # How to create/customize stacks
├── ADAPTERS.md          # How to create adapters
├── AUTOMATIONS.md       # How to define automations
└── DEVELOPMENT.md       # Developer setup and testing
```

### 4.11 scripts/

Scripts are allowed only as:
- Entrypoints (`manage.sh`)
- Convenience shims
- Backward-compatibility helpers

No logic is allowed here. Logic belongs in core/ or stacks/.

### 4.12 .proj/ — Internal Metadata

Private system metadata: internal indexes, caches, version markers.
Ignored by users and tooling.

---

## 5. Invariant Infrastructure

These layers are **domain-independent**. They stay the same regardless of
whether the control plane is managing a DevOps project, a publishing pipeline,
or any other domain. They are extracted directly from the orchestrator's
production-proven implementations.

### 5.1 Reliability

```
core/reliability/
├── __init__.py
├── circuit_breaker.py    # Three-state circuit breaker for adapters
└── retry_queue.py        # Persistent retry with exponential backoff
```

**Circuit Breaker** (from orchestrator):
- States: `CLOSED` → `OPEN` → `HALF_OPEN` → `CLOSED`
- Per-adapter failure tracking with configurable thresholds
- Windowed failure counting to avoid false positives
- Global registry with `get_circuit_breaker(name)` accessor
- Statistics export for observability

**Retry Queue** (from orchestrator):
- Persistent to disk (survives restarts)
- Exponential backoff with max retry limits
- Per-action tracking with full receipt history
- Queue statistics for monitoring

### 5.2 Observability

```
core/observability/
├── __init__.py
├── health.py             # Component health checks
├── metrics.py            # Counter, Gauge, Histogram (Prometheus-compatible)
└── logging.py            # Structured logging configuration
```

**Health Checker** (from orchestrator):
- Component-level health status: `HEALTHY`, `DEGRADED`, `UNHEALTHY`
- Checks: state file validity, audit log writability, operation freshness,
  retry queue depth, circuit breaker states
- Aggregate status with component details

**Metrics** (from orchestrator):
- `Counter`: monotonically increasing (tick count, action count)
- `Gauge`: up/down (queue depth, active connections)
- `Histogram`: timing distributions (action duration, detection time)
- Prometheus text format export
- JSON export for web dashboard

### 5.3 Security & Vault

```
core/security/
├── __init__.py
├── vault.py              # .env encryption at rest (AES-256-GCM)
├── crypto.py             # Content encryption utilities
└── secrets.py            # Secret resolution and management
```

**Vault** (from orchestrator):
- `.env` → `.env.vault` encryption using AES-256-GCM with PBKDF2 key derivation
- Passphrase-based lock/unlock
- Auto-lock on inactivity (configurable timeout)
- Auto-lock on server shutdown
- Rate-limited unlock attempts with tiered lockouts (3→30s, 6→5min, 10→15min)
- Secure delete (overwrite before unlink)
- Portable export/import for backup

**Secrets** (from orchestrator):
- Master config JSON pattern (single secret → all credentials)
- Individual secret fallback
- Adapter-specific credential resolution
- GitHub Secrets sync

### 5.4 Persistence

```
core/persistence/
├── __init__.py
├── state_file.py         # Atomic state file read/write
└── audit.py              # Append-only audit ledger (NDJSON)
```

**State file** (from orchestrator):
- Atomic write (write to temp, rename)
- Pydantic serialization/deserialization
- Schema version tracking for migrations

**Audit ledger** (from orchestrator):
- Append-only NDJSON (one JSON object per line)
- Fields: timestamp, operation ID, type, state before/after, actions executed
- Queryable and summarizable from the admin console

---

## 6. Engine Design

The engine is the core execution loop — the generalized equivalent of the
orchestrator's `tick.py`.

### Execution Phases

```
┌─────────────────────────────────────────────────────────────┐
│                     ENGINE EXECUTION                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Phase 1: INITIALIZE                                          │
│  ├── Generate operation ID                                    │
│  ├── Load project.yml                                         │
│  ├── Load state/current.json                                  │
│  └── Load stack definitions                                   │
│                                                               │
│  Phase 2: DETECT                                              │
│  ├── Discover modules (file system scan)                      │
│  ├── Match stacks to modules                                  │
│  ├── Check adapter availability                               │
│  └── Compute version information                              │
│                                                               │
│  Phase 3: EVALUATE                                            │
│  ├── Match automation conditions against state                │
│  ├── Identify required actions                                │
│  └── Build execution plan                                     │
│                                                               │
│  Phase 4: VALIDATE                                            │
│  ├── Check prerequisites                                      │
│  ├── Validate adapter availability                            │
│  └── Verify idempotency (skip already-executed actions)       │
│                                                               │
│  Phase 5: EXECUTE                                             │
│  ├── Dispatch actions through adapter registry                │
│  ├── Collect receipts                                         │
│  ├── Handle failures (circuit breaker + retry queue)          │
│  └── Track progress                                           │
│                                                               │
│  Phase 6: PERSIST                                             │
│  ├── Update state/current.json                                │
│  ├── Write audit entry                                        │
│  └── Report results                                           │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Engine Result

```python
@dataclass
class EngineResult:
    """Result of an engine execution."""

    operation_id: str
    started_at: str
    ended_at: str | None = None
    duration_ms: int = 0

    # What was requested
    automation: str = ""
    scope: list[str] = field(default_factory=list)  # module names

    # What happened
    modules_detected: int = 0
    stacks_matched: int = 0
    actions_planned: int = 0
    actions_executed: int = 0
    actions_skipped: int = 0
    actions_failed: int = 0

    # Detailed results
    receipts: list[Receipt] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # State change
    state_changed: bool = False
```

### Dry-Run Support

The engine accepts a `dry_run: bool` parameter. In dry-run mode:
- All phases run except EXECUTE and PERSIST
- Adapters are swapped to mocks via the registry
- The result shows **what would happen** without doing it

---

## 7. Adapter Protocol

### Base Protocol

```python
class ExecutionContext:
    """Context provided to adapters during execution."""

    def __init__(
        self,
        project: Project,
        module: Module | None,
        action: Action,
        operation_id: str,
        environment: Environment,
        dry_run: bool = False,
    ):
        self.project = project
        self.module = module
        self.action = action
        self.operation_id = operation_id
        self.environment = environment
        self.dry_run = dry_run


class Receipt(BaseModel):
    """Result of an adapter execution."""

    adapter: str
    action_id: str
    status: Literal["ok", "skipped", "failed"]
    started_at: str
    ended_at: str
    duration_ms: int = 0
    output: str = ""
    error: str | None = None
    delivery_id: str | None = None  # unique execution identifier
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### Registry Pattern

```python
class AdapterRegistry:
    """Registry for adapter lookup by name."""

    def __init__(self, mock_mode: bool = False):
        self._adapters: dict[str, Adapter] = {}
        self.mock_mode = mock_mode
        if mock_mode:
            self._register_mock_adapters()
        else:
            self._register_real_adapters()

    def get(self, name: str) -> Adapter:
        """Get adapter by name, with fallback to mock."""

    def execute_action(
        self, action: Action, context: ExecutionContext
    ) -> Receipt:
        """Full execution pipeline: lookup → validate → execute → receipt."""

    def available_adapters(self) -> dict[str, dict]:
        """Report all adapters with their availability and capabilities."""
```

### Writing a New Adapter

1. Create `adapters/category/my_tool.py`
2. Extend `Adapter` base class
3. Implement `name`, `capabilities`, `is_available`, `version`, `validate`, `execute`
4. Register in `AdapterRegistry._register_real_adapters()`

The mock adapter automatically handles any unregistered adapter name, returning
success receipts with logged parameters.

---

## 8. Policy System

Policy is **data that drives behavior**. The engine evaluates policy — it does
not contain hardcoded business rules.

### Three Policy Layers

```
1. project.yml        → What the project IS (identity, modules, environments)
2. stacks/*.yml       → What technology KNOWS (detection, defaults, capabilities)
3. automations/*.yml  → What CAN BE DONE (steps, prerequisites, failure handling)
```

### Condition Evaluation

Conditions in automations reference state paths, similar to the orchestrator's
rule conditions:

```yaml
when:
  module.stack.name: python-fastapi
  module.domain: service
  adapter.docker.available: true
  state.last_build_at.age_minutes_gt: 60
```

The evaluator supports:
- Exact match: `field: value`
- Set membership: `field_in: [a, b, c]`
- Comparison: `field_gt`, `field_gte`, `field_lt`, `field_lte`
- Existence: `field_exists: true`
- Negation: `field_not: value`

These operators are extensible — new operators are registered in a dict, just
like the orchestrator's `OPERATORS` in `rules.py`.

### Constants and Variables

```yaml
constants:
  build_timeout_seconds: 300
  max_parallel_modules: 4
  default_python_version: "3.11"

variables:
  registry: "{{ external.registry }}"
  branch: "{{ state.detected.git.branch }}"
```

---

## 9. Three-Interface Parity

One of the orchestrator's strongest patterns: three ways to access the same
functionality, all calling the same underlying engine.

### manage.sh — Interactive TUI

```bash
╔══════════════════════════════════════════════════════════════╗
║           DEVOPS CONTROL PLANE — MANAGER                      ║
╚══════════════════════════════════════════════════════════════╝

Available Commands:

  1) status          Show project status
  2) detect          Detect modules and stacks
  3) build           Build all modules

  4) automate        Run an automation
  5) scaffold        Generate project files

  w) web             Open web admin panel
  c) config          Show configuration status
  h) help            Show all CLI commands
  q) quit            Exit
```

**Design rules:**
- `manage.sh` activates the venv, shows a banner, then routes to CLI commands
- Dual-mode: interactive (menu loop) and direct (`./manage.sh build`)
- Live-reload server support (SPACE to restart web server)
- All commands delegate to `python -m src.main <command>`

### CLI — Programmatic Interface

```bash
python -m src.main status
python -m src.main detect
python -m src.main automate build --env production --dry-run
python -m src.main scaffold --stack python-fastapi --name new-service
```

- Click groups with clean help text
- `--dry-run` on every destructive command
- `--env` for environment targeting
- `--module` for scope filtering
- JSON output mode (`--json`) for scripting

### Web Admin — Visual Dashboard

```
Blueprint-per-domain architecture:

core_bp         /            Dashboard, status, operations
modules_bp      /api/modules Module management
stacks_bp       /api/stacks  Stack information
adapters_bp     /api/adapters Adapter status
automations_bp  /api/auto    Run automations
config_bp       /api/config  Configuration
git_bp          /api/git     Git status
docker_bp       /api/docker  Container management
vault_bp        /api/vault   Vault operations
```

---

## 10. Admin Console Architecture

The web admin is a **local-only** Flask SPA, modeled directly on the
orchestrator's proven template architecture.

### Template Structure

```
templates/
├── index.html                 ← Main entry point
├── partials/
│   ├── _head.html             ← <head>, CSS
│   ├── _nav.html              ← Tab navigation
│   ├── _tab_dashboard.html    ← Dashboard container
│   ├── _tab_modules.html      ← Module management
│   ├── _tab_automations.html  ← Automation runner
│   ├── _tab_config.html       ← Configuration
│   └── _vault.html            ← Vault overlay
│
├── scripts/
│   ├── _globals.html          ← Opens <script>, global state
│   ├── _theme.html            ← Theme toggle
│   ├── _tabs.html             ← Tab switching
│   ├── _dashboard.html        ← Dashboard rendering
│   ├── _modules.html          ← Module UI logic
│   ├── _automations.html      ← Automation UI logic
│   ├── _vault.html            ← Vault lock/unlock logic
│   └── _boot.html             ← Boot sequence, closes </script>
│
└── modals/
    ├── _audit_log.html        ← Audit log viewer
    └── _confirmation.html     ← Action confirmation
```

### Convention Rules (from orchestrator README)

1. **`scripts/`**: Raw JavaScript only — no `<script>` tags
2. **`_globals.html`** opens the `<script>`, **`_boot.html`** closes it
3. All functions share global scope — no modules
4. **`partials/`**: HTML only — no `<script>` tags
5. Inline `onclick` handlers reference functions from scripts
6. All API calls use `fetch()` with JSON
7. Polling for status updates (status: 30s, vault: 10s)

### Security

- **Bind to 127.0.0.1 only** — never exposed to the internet
- **Vault overlay** blocks all UI when locked
- **Port cleanup** — kill existing process before starting
- **Vault auto-lock** on shutdown (atexit + SIGINT handler)

---

## 11. Deployment & Infrastructure

### Local Development

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Daily use
./manage.sh            # Interactive
python -m src.main     # Direct CLI
./manage.sh web        # Web admin
```

### Docker Compose

Profile-based deployment modes (from orchestrator):

```yaml
services:
  # Profile: standalone (default)
  control-plane:
    profiles: [standalone]
    # ... runs with local state

  # Profile: git-sync (persistent)
  control-plane-git-sync:
    profiles: [git-sync]
    # ... commits state back to git

  # Profile: tunnel (external access)
  cloudflared:
    profiles: [tunnel]
    # ... Cloudflare tunnel for remote access
```

### GitHub Actions

```yaml
# .github/workflows/detect.yml
on:
  push:
    branches: [main]

jobs:
  detect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python -m src.main detect --json
      - run: python -m src.main automate lint --all
```

---

## 12. Plugin & Extension Model

### Adding a New Stack

1. Create `stacks/my-stack/stack.yml` with detection rules and capabilities
2. Add default configurations in `stacks/my-stack/defaults/`
3. Add templates in `templates/` if the stack needs file generation
4. Register stack-specific automations in `stacks/my-stack/automations.yml`

No code changes required. The engine discovers stacks from the `stacks/` directory.

### Adding a New Adapter

1. Create `adapters/category/my_tool.py`
2. Extend `Adapter` base class
3. Implement the 6 required methods
4. Register in `AdapterRegistry._register_real_adapters()`

### Adding a New Automation

1. Create `automations/my-operation.yml`
2. Define prerequisites, steps, and failure handling
3. It's immediately available in CLI, Web, and TUI

### Adding a New UI Tab

1. Create `ui/web/templates/partials/_tab_mytab.html` (HTML structure)
2. Create `ui/web/templates/scripts/_mytab.html` (JS logic)
3. Add `{% include %}` in `index.html`
4. Create `ui/web/routes_mytab.py` (API endpoints)
5. Register blueprint in `server.py`

### Customizing for a Specific Domain

The control plane ships as a generic scaffold. To wire it to a specific project:

1. Write `project.yml` with your project's identity and modules
2. Choose or create stacks that match your technology choices
3. Define automations for your operational workflows
4. Configure adapter credentials in `.env`

**No core code changes.** The configuration defines the wiring.

---

## 13. Growth Rules (Non-Negotiable)

### Layer Touch Rule

If a change requires touching:
- core + adapters → acceptable
- core + ui → acceptable
- adapters + ui → acceptable
- **three or more layers → design error**

### Root Stability

Nothing outside the defined root layout is allowed. New capabilities emerge as
**branches** (new files within existing directories), never as root mutations.

### Dependency Direction

```
ui/  →  core/  →  (nothing)
ui/  →  adapters/  →  core/models (types only)
adapters/  →  core/models (types only)
```

Core never imports from ui/ or adapters/. Adapters never import from ui/.
Only core/models are shared as type definitions.

### Test Coverage Requirements

- **core/**: 90%+ coverage (pure logic, fully testable)
- **adapters/**: integration tests with mocks
- **ui/**: endpoint tests (response codes, JSON shapes)
- **invariant infrastructure/**: 90%+ coverage

---

## 14. Technology Choices

| Component | Technology | Rationale |
|---|---|---|
| Language | Python 3.11+ | Proven in orchestrator, ecosystem breadth |
| Models | Pydantic 2+ | Validation, serialization, schema evolution |
| CLI | Click 8+ | Proven in orchestrator, composable groups |
| Web | Flask 3+ | Proven in orchestrator, blueprint architecture |
| Templates | Jinja2 3+ | Proven in orchestrator, both for web and file generation |
| Config | YAML (PyYAML 6+) | Human-readable policy, proven in orchestrator |
| Env | python-dotenv 1+ | .env loading, proven |
| Build | Hatchling | Modern Python build backend |
| Test | pytest 7+ | Proven, 639 tests in orchestrator |
| Lint | ruff 0.1+ | Fast, comprehensive |
| Types | mypy 1+ | Gradual typing with Pydantic |

### Web Frontend

- **No build step** — vanilla JS in Jinja2 templates
- **No framework** — direct DOM manipulation via template literals
- **CSS custom properties** for theming (dark/light mode)
- Inline `fetch()` for API calls
- Polling for reactivity (no WebSocket complexity)

This is a deliberate choice proven in the orchestrator: 550k+ of fully
functional web UI with zero npm dependencies.

---

## 15. Appendix: Pattern Lineage

Every major design decision in this document traces directly to a working
implementation in the continuity-orchestrator. The table below maps each control
plane concept to its proven origin:

| Control Plane Concept | Orchestrator Origin | Files |
|---|---|---|
| Engine execution phases | Tick lifecycle (8 phases) | `src/engine/tick.py` |
| Pydantic domain models | State + Receipt + Policy models | `src/models/state.py`, `src/policy/models.py` |
| Adapter protocol | `Adapter` ABC | `src/adapters/base.py` |
| Adapter registry + mock swap | `AdapterRegistry` | `src/adapters/registry.py` |
| Receipt-based error handling | `Receipt` model | `src/models/receipt.py` |
| Policy as YAML data | rules.yaml, states.yaml, plans/ | `policy/` |
| Condition evaluation | Rule matching engine | `src/engine/rules.py` |
| Three-interface parity | manage.sh + CLI + Flask admin | `manage.sh`, `src/cli/`, `src/admin/` |
| Blueprint-per-domain web | 13 Flask blueprints | `src/admin/routes_*.py` |
| Shared `<script>` block SPA | Template README convention | `src/admin/templates/` |
| .env vault encryption | AES-256-GCM vault | `src/admin/vault.py` |
| Circuit breaker | `CircuitBreaker` + registry | `src/reliability/circuit_breaker.py` |
| Retry queue | `RetryQueue` with backoff | `src/reliability/retry_queue.py` |
| Health checks | `HealthChecker` with components | `src/observability/health.py` |
| Prometheus-compatible metrics | Counter/Gauge/Histogram | `src/observability/metrics.py` |
| Atomic state persistence | State file + audit ledger | `src/persistence/` |
| Content encryption | AES-256-GCM with PBKDF2 | `src/content/crypto.py` |
| Docker profile management | Profile-based compose | `docker-compose.yml`, `routes_docker.py` |
| Multi-repo mirroring | Mirror manager | `src/mirror/` |
| Interactive TUI | manage.sh menu loop | `manage.sh` |
| Config loader | Master JSON + individual vars | `src/config/loader.py` |
| Template resolution | Template resolver + context | `src/templates/` |

---

*This document is the foundation. Everything else grows from here.*
