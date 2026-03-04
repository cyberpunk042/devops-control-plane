# Documentation

> **113 files. 22,680 lines. Project knowledge base — from quickstart to deep architecture.**
>
> This module contains all project documentation: architecture guides, domain
> references, planning analyses, architectural decision records, deployment
> examples, and full-spectrum tool specifications. It serves as the single
> source of truth for understanding, using, and extending the DevOps Control Plane.

---

## How It Works

The documentation module is organized into **four tiers** that serve different
audiences and purposes:

```
┌──────────────────────────────────────────────────────────────────────┐
│                     docs/ — Knowledge Tiers                          │
│                                                                      │
│  Tier 1: Foundation           ← Start here                          │
│  ├── QUICKSTART.md            "git clone to running in 5 min"       │
│  ├── ARCHITECTURE.md          "how the system is structured"         │
│  ├── DESIGN.md                "philosophy and product direction"     │
│  └── DEVELOPMENT.md           "dev env setup, tests, contributing"   │
│                                                                      │
│  Tier 2: Domain Guides        ← Feature-specific deep dives         │
│  ├── ADAPTERS.md              "adapter pattern and tool bindings"    │
│  ├── STACKS.md                "stack definitions and execution"      │
│  ├── CONTENT.md               "content browsing, encryption, media"  │
│  ├── VAULT.md                 "AES-256-GCM secrets management"       │
│  ├── PAGES.md                 "documentation site builder"           │
│  └── WEB_ADMIN.md             "web admin dashboard features"         │
│                                                                      │
│  Tier 3: Planning & Analysis  ← Architecture decisions               │
│  ├── ANALYSIS.md              "future development roadmap"           │
│  ├── AUDIT_ARCHITECTURE.md    "audit tab design document"            │
│  ├── AUDIT_PLAN.md            "audit implementation plan"            │
│  ├── CONSOLIDATION_AUDIT.md   "extraction audit (completed)"        │
│  ├── DEVOPS_UI_GAP_ANALYSIS   "UI completeness analysis"            │
│  └── INTEGRATION_GAP_ANALYSIS "integration/card coverage"           │
│                                                                      │
│  Tier 4: Reference Data       ← Generated/structured specs          │
│  ├── adr/                     "Architectural Decision Records"       │
│  ├── examples/                "Deployment scenarios"                 │
│  └── tool_install/tools/      "94 tool specification sheets"         │
└──────────────────────────────────────────────────────────────────────┘
```

### Reading Order for New Contributors

```
1. QUICKSTART.md          → Get the system running
         │
2. ARCHITECTURE.md        → Understand the structure
         │
3. DESIGN.md              → Understand the philosophy
         │
4. DEVELOPMENT.md         → Set up dev environment
         │
5. Pick a domain guide    → Deep-dive into the feature you'll work on
         │
6. Read relevant plans    → Understand ongoing/future work
```

### How Docs Relate to Source Code

Each domain guide in `docs/` corresponds to a source code module. The naming
convention maps guides to the code they document:

```
docs/ADAPTERS.md          → src/adapters/
docs/STACKS.md            → src/core/data/catalogs/ + src/core/engine/
docs/CONTENT.md           → src/core/services/content/
docs/VAULT.md             → src/core/services/vault/ + src/core/services/secrets/
docs/PAGES.md             → src/core/services/pages/ + src/core/services/pages_builders/
docs/WEB_ADMIN.md         → src/ui/web/
docs/ADAPTERS.md          → src/adapters/
```

Each source module also has its own `README.md` with code-level details.
The `docs/` guides provide the **user-facing** perspective; the source
READMEs provide the **developer-facing** perspective.

---

## File Map

```
docs/
├── README.md                          This file (navigation hub)
│
├── QUICKSTART.md                      Getting started guide (118 lines)
├── ARCHITECTURE.md                    System structure and data flow (284 lines)
├── DESIGN.md                          Design philosophy and direction (317 lines)
├── DEVELOPMENT.md                     Dev environment and contributing (203 lines)
│
├── ADAPTERS.md                        Adapter pattern guide (201 lines)
├── STACKS.md                          Stack definitions guide (206 lines)
├── CONTENT.md                         Content management guide (136 lines)
├── VAULT.md                           Secrets management guide (139 lines)
├── PAGES.md                           Documentation builder guide (222 lines)
├── WEB_ADMIN.md                       Web admin dashboard guide (241 lines)
│
├── ANALYSIS.md                        Future development analysis (777 lines)
├── AUDIT_ARCHITECTURE.md              Audit tab design document (505 lines)
├── AUDIT_PLAN.md                      Audit implementation plan (667 lines)
├── CONSOLIDATION_AUDIT.md             Architecture extraction audit (303 lines)
├── DEVOPS_UI_GAP_ANALYSIS.md          DevOps UI completeness (265 lines)
├── INTEGRATION_GAP_ANALYSIS.md        Integration/card coverage (266 lines)
│
├── Screenshot_2026-02-01_122520.png   UI screenshot reference
│
├── adr/                               Architectural Decision Records
│   └── 001-python-version.md          Python 3.12 with pyenv (21 lines)
│
├── examples/                          Deployment scenario walkthroughs
│   ├── MULTI_SERVICE.md               Multi-service project example (126 lines)
│   └── SELF_HOSTING.md                Self-hosting example (66 lines)
│
└── tool_install/                      Tool specification sheets
    └── tools/
        ├── docker.md                  Full-spectrum Docker analysis (348 lines)
        ├── terraform.md               Full-spectrum Terraform analysis (260 lines)
        ├── python.md                  Full-spectrum Python analysis (362 lines)
        ├── kubectl.md                 Full-spectrum kubectl analysis (242 lines)
        └── ... (94 tool specs total)
```

---

## Per-File Documentation

### Tier 1: Foundation

#### `QUICKSTART.md` — Getting Started (118 lines)

The entry point for new users. Covers the minimum path from `git clone` to
running the system.

| Section | What It Covers |
|---------|---------------|
| Prerequisites | Python 3.12, pyenv, system requirements |
| Clone & Install | Repository setup, virtualenv, dependencies |
| First Run | Starting the web admin, running a first automation |
| Next Steps | Pointers to architecture and domain guides |

---

#### `ARCHITECTURE.md` — System Structure (284 lines)

The technical blueprint. How the system is structured, how data flows, and
where everything lives.

| Section | What It Covers |
|---------|---------------|
| High-Level Overview | 4-layer architecture diagram (CLI → Core → Adapters → Tools) |
| Directory Layout | File tree with purpose annotations |
| Core Layer | Models, engine, services, use cases |
| Adapter Layer | Protocol pattern, registered adapters |
| UI Layer | CLI (Typer), Web Admin (Flask) |
| Data Flow | Action lifecycle: user → CLI/Web → core → adapter → receipt |

**Key diagram — 4-Layer Architecture:**

```
┌─────────┐     ┌─────────┐
│   CLI   │     │   Web   │      ← UI Layer (presentation)
└────┬────┘     └────┬────┘
     │               │
     └───────┬───────┘
             │
     ┌───────┴───────┐
     │     Core      │            ← Business Logic
     │  (services,   │               (models, engine,
     │   use cases)  │                services)
     └───────┬───────┘
             │
     ┌───────┴───────┐
     │   Adapters    │            ← External Interface
     │  (protocol)   │               (shell, docker, git, etc.)
     └───────┬───────┘
             │
     ┌───────┴───────┐
     │  External     │            ← Real Tools
     │  Tools        │               (docker CLI, git, python, etc.)
     └───────────────┘
```

---

#### `DESIGN.md` — Philosophy & Direction (317 lines)

The "why" behind the system. Design philosophy, product direction, and
guiding principles.

| Section | What It Covers |
|---------|---------------|
| Vision | Single pane of glass for all DevOps operations |
| Design Principles | Convention over configuration, receipts not exceptions, etc. |
| Product Direction | From CLI-first to web-first, from local to cloud-native |
| Module Boundaries | How domains are separated and why |
| Extension Points | Where the system is designed to be extended |

---

#### `DEVELOPMENT.md` — Developer Guide (203 lines)

Setting up a development environment and contributing changes.

| Section | What It Covers |
|---------|---------------|
| Prerequisites | Python 3.12, pyenv, Poetry/pip |
| Dev Setup | Virtual environment, dependencies, pre-commit hooks |
| Running Tests | pytest configuration, test organization |
| Code Style | Formatting, linting, type checking |
| Contributing | Branch strategy, PR process, review guidelines |

---

### Tier 2: Domain Guides

#### `ADAPTERS.md` — Adapter Pattern Guide (201 lines)

User-facing guide for understanding and creating adapters.

| Section | What It Covers |
|---------|---------------|
| Overview | What adapters are and why they exist |
| Built-in Adapters | Table of all 6 adapters with capabilities |
| Creating an Adapter | Step-by-step with code examples |
| Mock Mode | How to use mock adapters for testing |
| Action Params | Common param patterns across adapters |

---

#### `STACKS.md` — Stack Definitions Guide (206 lines)

How to define, discover, and execute technology stacks.

| Section | What It Covers |
|---------|---------------|
| What is a Stack? | Declarative automation definitions |
| Stack Catalog | Where stacks are defined (JSON catalogs) |
| Stack Capabilities | Docker, Python, Node, Terraform actions |
| Detection | Automatic project type detection |
| Execution | How stacks translate to adapter actions |

---

#### `CONTENT.md` — Content Management Guide (136 lines)

Browsing, encrypting, and releasing project content files.

| Section | What It Covers |
|---------|---------------|
| Media Gallery | File browsing with thumbnails and previews |
| Encryption | Per-file AES-256-GCM encryption |
| Optimization | Image compression and format conversion |
| Release Artifacts | Publishing content to cloud storage |

---

#### `VAULT.md` — Secrets Management Guide (139 lines)

AES-256-GCM encryption for `.env` files and project secrets.

| Section | What It Covers |
|---------|---------------|
| Overview | What the vault protects and how |
| Encryption | AES-256-GCM with rotating keys |
| Key Management | Master key derivation and storage |
| Environment Files | Managing `.env` across environments |
| CLI Usage | Vault lock/unlock/rotate commands |

---

#### `PAGES.md` — Documentation Builder Guide (222 lines)

Building and deploying documentation sites from the web admin.

| Section | What It Covers |
|---------|---------------|
| Overview | Multi-segment documentation pipeline |
| Builders | Docusaurus, MkDocs, static site generators |
| Segments | How multiple doc sources are merged |
| Build Process | Discovery → transform → build → deploy |
| CI Integration | GitHub Actions deployment workflow |

---

#### `WEB_ADMIN.md` — Web Admin Dashboard Guide (241 lines)

The Flask-based single-page application for managing the project through
a browser.

| Section | What It Covers |
|---------|---------------|
| Overview | Dashboard layout and navigation |
| DevOps Tab | Integration cards, status monitoring |
| Audit Tab | Code quality analysis and insights |
| Content Tab | File management and preview |
| Pages Tab | Documentation builder UI |
| Settings | Preferences, wizard, configuration |

---

### Tier 3: Planning & Analysis

#### `ANALYSIS.md` — Future Development Roadmap (777 lines)

The most comprehensive planning document. Breaks down the path from current
state to final product vision.

| Section | What It Covers |
|---------|---------------|
| Current State Assessment | What exists today, what's mature vs. prototype |
| Phase Breakdown | Multi-phase development roadmap |
| Priority Queue | Work items ranked by impact and effort |
| Technical Debt | Known shortcuts that need proper solutions |
| Extension Vision | Where the platform is headed long-term |

---

#### `AUDIT_ARCHITECTURE.md` — Audit System Design (505 lines)

Design document for the Audit tab — the code quality analysis engine.

| Section | What It Covers |
|---------|---------------|
| Overview | What the audit system measures and how |
| L0/L1 Pipeline | Fast local scans (structure, quality, patterns) |
| L2 Pipeline | Deep analysis (risks, vulnerabilities, security) |
| Score Enrichment | How raw metrics become health scores |
| Data Flow | Scan → parse → score → cache → display |

---

#### `AUDIT_PLAN.md` — Audit Implementation Plan (667 lines)

Execution plan matching the architecture document.

| Section | What It Covers |
|---------|---------------|
| Current Inventory | What exists in the codebase today |
| Gap Analysis | Missing features vs. design spec |
| Phase Plan | Implementation phases with milestones |
| Test Strategy | How each phase will be validated |

---

#### `CONSOLIDATION_AUDIT.md` — Extraction Audit (303 lines)

**Status: ✅ COMPLETED.**

Post-mortem of the architecture consolidation — extracting monolithic service
files into domain packages.

| Section | What It Covers |
|---------|---------------|
| Extraction Phases | 9 phases of domain extraction |
| Test Results | 324 tests passing, zero regressions |
| Cleanup | Dead imports, orphaned helpers removed |
| Lessons Learned | What worked well, what to avoid |

---

#### `DEVOPS_UI_GAP_ANALYSIS.md` — UI Completeness (265 lines)

Systematic analysis of the DevOps tab — what's implemented vs. what's specced.

| Section | What It Covers |
|---------|---------------|
| Phase Status | Which UI phases are complete |
| Card Coverage | Integration cards implemented vs. missing |
| Action Gaps | User actions that need UI surfaces |
| Priority Items | What to implement next |

---

#### `INTEGRATION_GAP_ANALYSIS.md` — Integration Coverage (266 lines)

Cross-cutting analysis of integrations, DevOps cards, and audit cards.

| Section | What It Covers |
|---------|---------------|
| Integration Inventory | All integrations and their current state |
| Card Duplication | Overlap between DevOps and audit cards |
| Missing Infrastructure | Backend features without UI surfaces |
| Wizard/Preferences Plan | How to expose settings vs. auto-detect |

---

### Tier 4: Reference Data

#### `adr/` — Architectural Decision Records

Formal records of significant architecture decisions, following the
standard ADR format (Status, Context, Decision, Consequences).

| ADR | Status | Decision |
|-----|--------|----------|
| `001-python-version.md` | Accepted | Python 3.12 with pyenv as the project standard |

**ADR format:**

```
# ADR-NNN: Title
**Status:** Accepted | Proposed | Superseded
**Date:** YYYY-MM-DD

## Context
What is the issue that we're seeing that motivates this decision?

## Decision
What is the change that we're proposing and/or doing?

## Consequences
What becomes easier or harder because of this change?
```

---

#### `examples/` — Deployment Scenarios

Real-world usage scenarios showing the Control Plane managing different
project types.

| Example | Lines | What It Shows |
|---------|-------|---------------|
| `MULTI_SERVICE.md` | 126 | Managing a microservices project with Docker, multiple stacks, and CI/CD |
| `SELF_HOSTING.md` | 66 | The Control Plane managing its own repository |

---

#### `tool_install/tools/` — Tool Specification Sheets (94 tools)

Full-spectrum analysis for every tool in the tool-install system. Each spec
sheet is a comprehensive reference covering installation, verification, and
remediation across all supported platforms.

**Total:** 94 tool specs, ~17,600 lines

**Format per tool (example: `docker.md`, 348 lines):**

| Section | What It Covers |
|---------|---------------|
| Tool ID & Status | Audit status, last review date |
| Recipe Coverage | Installation methods per platform |
| Verification | How the tool is detected and version-checked |
| Remediation | Failure handlers and recovery strategies |
| Scenarios | Which system presets include this tool |
| Data Shapes | Resolver data, recipe data, handler data |

**Tool categories covered:**

| Category | Tools | Examples |
|----------|-------|---------|
| Containers | 6 | docker, docker-compose, podman, buildx, dive, skopeo |
| Kubernetes | 9 | kubectl, helm, helmfile, k9s, kubectx, kustomize, stern, flux, istioctl |
| Languages | 11 | python, node, go, ruby, cargo, rustup, bun, tsx, npm, pip, pipx |
| IaC | 5 | terraform, pulumi, ansible, cdktf, tfsec |
| Security | 6 | gitleaks, trivy, grype, semgrep, snyk, detect-secrets, checkov |
| CI/CD | 3 | act, argocd-cli, gh |
| Quality | 4 | flake8, isort, phpstan, golangci-lint |
| Databases | 4 | psql, mongosh, mysql-client, redis-cli, sqlite3 |
| Cloud | 3 | aws-cli, az-cli, gcloud |
| Package Mgrs | 9 | poetry, pdm, hatch, uv, nox, tox, composer, pnpm, yarn |
| Dev Tools | 16 | jq, ripgrep, fd, fzf, bat, eza, tmux, starship, zoxide, etc. |
| Testing | 4 | playwright, cypress, vitest, storybook |
| Web/Infra | 4 | nginx, caddy, mkcert, step-cli, prometheus |

---

## Content Organization

### Document Lifecycle

Documents in `docs/` follow one of three lifecycle patterns:

```
Living Documents (continuously updated):
  ARCHITECTURE.md, DESIGN.md, QUICKSTART.md, DEVELOPMENT.md
  Domain guides: ADAPTERS, STACKS, CONTENT, VAULT, PAGES, WEB_ADMIN

Point-in-Time Analysis (written once, referenced later):
  ANALYSIS.md, AUDIT_ARCHITECTURE.md, AUDIT_PLAN.md
  DEVOPS_UI_GAP_ANALYSIS.md, INTEGRATION_GAP_ANALYSIS.md

Completed Artifacts (historical record):
  CONSOLIDATION_AUDIT.md (✅ all phases done)
```

### Naming Convention

- **UPPER_CASE.md** — Top-level guides and analysis documents
- **lower_case.md** — ADRs, examples, tool specs
- **Directory names** — Lowercase, underscore-separated

### Hidden Directories

| Directory | Purpose |
|-----------|---------|
| `.backup/` | Tar.gz snapshots of docs at specific points in time |
| `.large/` | Reserved for large binary assets (currently empty) |

---

## Dependency Graph

The docs module has **no code dependencies** — it's pure documentation.
However, it has **content dependencies** on the source code it describes:

```
docs/ARCHITECTURE.md        ← describes → entire project structure
docs/DESIGN.md              ← describes → core philosophy + models
docs/ADAPTERS.md            ← describes → src/adapters/
docs/STACKS.md              ← describes → src/core/data/catalogs/
docs/CONTENT.md             ← describes → src/core/services/content/
docs/VAULT.md               ← describes → src/core/services/vault/
docs/PAGES.md               ← describes → src/core/services/pages*/
docs/WEB_ADMIN.md           ← describes → src/ui/web/
docs/tool_install/tools/    ← describes → src/core/services/tool_install/
```

**Staleness risk:** When code changes, these docs may become outdated.
The audit-data directive embedded in module READMEs helps detect drift
by showing real-time code health metrics alongside the documentation.

---

## Consumers

| Consumer | How It Uses docs/ |
|----------|------------------|
| **Developers** | Read guides to understand the system and set up dev environments |
| **Pages Builder** | Copies docs/ content into Docusaurus site builds |
| **Web Admin Preview** | Renders markdown previews of docs/ files in the content vault |
| **Audit Directive** | `:::audit-data` cards in module READMEs surface code health |
| **GitHub** | GitHub renders top-level docs for repository visitors |

---

## Design Decisions

### Why a Flat `docs/` Directory?

Most documentation frameworks prefer nested directory structures. We use
a flat top-level for discoverability:

- **All 16 guides visible at a glance** — no hunting through subdirectories
- **GitHub renders them in the repo browser** — instant visibility
- **UPPER_CASE naming** — visually separates docs from code files
- **Only structured data is nested** — ADRs, examples, tool specs have their
  own directories because they follow a repeated format

### Why Separate docs/ from Source READMEs?

Two layers of documentation serve different audiences:

| Layer | Audience | Focus |
|-------|----------|-------|
| `docs/*.md` | Users, operators, new contributors | How to use the system |
| `src/*/README.md` | Developers working in that module | How the code works internally |

A user reading `docs/VAULT.md` learns what vault does and how to use it.
A developer reading `src/core/services/vault/README.md` learns how the
encryption pipeline is implemented, what functions exist, and how to
modify the code.

### Why Keep Completed Analyses?

Documents like `CONSOLIDATION_AUDIT.md` (marked ✅ COMPLETED) are kept
as historical records:

- They document **what was done and why** — invaluable for understanding
  the codebase's evolution
- They serve as **templates** for future similar work
- They capture **lessons learned** that prevent repeating mistakes

### Why 94 Individual Tool Spec Sheets?

Each tool in the tool-install system has its own comprehensive spec sheet
instead of a single large document because:

- **Tool-level granularity** — each tool can be audited, reviewed, and
  updated independently
- **Consistent format** — every tool follows the same full-spectrum analysis
  structure, making it easy to compare coverage
- **Generated from source** — many sections are verifiable against the actual
  recipe/resolver data in `src/core/services/tool_install/data/`
- **Audit trail** — each spec has a "last audited" date to track freshness

### Why ADR Format?

Architectural Decision Records (ADRs) capture **why** decisions were made,
not just what was decided. Currently only one ADR exists (Python 3.12), but
the structure is in place for future decisions. ADRs are especially valuable
when:

- A technology choice seems surprising months later
- A new contributor asks "why not X instead?"
- The decision needs to be revisited due to changed circumstances

---

## Adding New Documentation

### New Domain Guide

When a new feature domain is created (e.g., new service package):

1. Create `docs/FEATURE_NAME.md` following the tier-2 structure
2. Include: Overview, Quick Start, Feature Deep Dive, Configuration, Troubleshooting
3. Cross-link to the relevant source module README
4. Add to the file map in this README

### New ADR

```bash
# Next available number:
ls docs/adr/ | tail -1  # → 001-python-version.md
# Create:
# docs/adr/002-title-slug.md
```

Follow the standard ADR format: Status, Date, Context, Decision, Consequences.

### New Tool Spec

Tool specs are created as part of the tool coverage audit workflow
(`/tool-coverage-audit`). Each spec follows the full-spectrum analysis
format and is placed in `docs/tool_install/tools/<tool-id>.md`.

### New Example

Place in `docs/examples/` with a descriptive filename. Examples should be
self-contained walkthroughs that show the Control Plane managing a real
project scenario.
