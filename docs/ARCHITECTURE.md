# Architecture

> How the DevOps Control Plane is structured, how data flows, and where
> everything lives.

---

## Layer Model

```
┌──────────────────────────────────────────────────────────────────────┐
│                         INTERFACES (thin)                            │
│                                                                      │
│  manage.sh          CLI (Click)          Web Admin (Flask SPA)       │
│  (TUI menu)         src/main.py          src/ui/web/                │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                         CORE DOMAIN (pure)                           │
│                                                                      │
│  Models       Services            Engine       Use-Cases             │
│  (Pydantic)   (vault, content,    (runner,     (detect, status,      │
│               pages, detection,   evaluator)    automate, health)    │
│               optimization)                                          │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                         POLICY (data)                                │
│                                                                      │
│  project.yml        stacks/*.yml        (future: automations/*.yml)  │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                         ADAPTER LAYER                                │
│                                                                      │
│  shell (command, filesystem)   mock   (vcs, containers — stubs)     │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                    INVARIANT INFRASTRUCTURE                          │
│                                                                      │
│  Reliability         Observability       Security       Persistence  │
│  (circuit breaker,   (health, metrics,   (vault,        (state file, │
│   retry queue)        structured log)     AES-256-GCM)   audit log)  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Principle: Three-Layer Touch Rule

A single feature should touch **at most two** of these layers. If it touches
three or more, the design is wrong — refactor.

---

## Data Flow

```
project.yml  +  stacks/  +  .state/
        │
        ▼
   ┌──────────┐
   │  Engine   │  ← triggered by CLI, Web, or manage.sh
   │  detect   │
   │  plan     │
   │  execute  │
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
 (results)  (ledger.ndjson)
```

The engine always follows this cycle: **load → detect → plan → execute →
persist → audit**. Every operation writes to the audit ledger regardless
of success or failure.

---

## Directory Layout

```
devops-control-plane/
├── manage.sh                  # TUI entrypoint (interactive menu + direct commands)
├── project.yml                # Project identity and module declarations
├── pyproject.toml             # Python package config + dependencies
├── Makefile                   # Dev shortcuts: make lint, test, check
│
├── src/
│   ├── main.py                # CLI entrypoint (Click)
│   │
│   ├── core/                  # Pure domain logic — no shell, no IO
│   │   ├── models/            # Pydantic data models
│   │   │   ├── project.py     #   Project, Environment
│   │   │   ├── module.py      #   Module, ModuleDescriptor
│   │   │   ├── stack.py       #   Stack, StackCapability
│   │   │   ├── action.py      #   Action, Receipt
│   │   │   ├── state.py       #   ProjectState (root state model)
│   │   │   └── template.py    #   Template models
│   │   ├── config/            # YAML loaders
│   │   │   └── loader.py      #   project.yml → Project model
│   │   ├── services/          # Business logic — 29 domain packages
│   │   │   ├── artifacts/     #   Release artifacts, version, workflow gen
│   │   │   ├── audit/         #   Security audit (L0/L1/L2 detection + scoring)
│   │   │   ├── backup/        #   Backup/restore/archive/encrypt
│   │   │   ├── changelog/     #   Changelog generation
│   │   │   ├── chat/          #   Chat threads + message management
│   │   │   ├── ci/            #   CI/CD compose + operations
│   │   │   ├── content/       #   File management, encryption, optimization
│   │   │   ├── devops/        #   DevOps card activity + caching
│   │   │   ├── dns/           #   DNS/CDN operations
│   │   │   ├── docker/        #   Docker operations
│   │   │   ├── docs_svc/      #   Documentation generation
│   │   │   ├── env/           #   Environment + infrastructure ops
│   │   │   ├── generators/    #   Config generators (Dockerfile, compose, etc.)
│   │   │   ├── git/           #   Git/GitHub CLI operations
│   │   │   ├── k8s/           #   Kubernetes (detect, generate, validate, cluster, helm)
│   │   │   ├── ledger/        #   Audit ledger
│   │   │   ├── metrics/       #   Metrics collection
│   │   │   ├── packages_svc/  #   Package management
│   │   │   ├── pages/         #   Pages segment orchestrator
│   │   │   ├── pages_builders/#   SSG builder plugins (docusaurus, mkdocs, hugo, etc.)
│   │   │   ├── quality/       #   Code quality operations
│   │   │   ├── secrets/       #   Secrets management, key generators
│   │   │   ├── security/      #   Security scanning
│   │   │   ├── terraform/     #   Terraform operations
│   │   │   ├── testing/       #   Testing operations
│   │   │   ├── tool_install/  #   Tool installation + recipes
│   │   │   ├── trace/         #   Operation tracing
│   │   │   ├── vault/         #   AES-256-GCM vault (core, io, env ops)
│   │   │   ├── wizard/        #   Setup wizard orchestration
│   │   │   └── detection.py   #   Stack matching, module scanning
│   │   ├── engine/            # Execution loop
│   │   │   └── runner.py      #   Run capabilities through adapters
│   │   ├── use_cases/         # High-level entry points (CLI/Web call these)
│   │   │   ├── config_check.py
│   │   │   ├── detect.py
│   │   │   ├── run.py
│   │   │   └── status.py
│   │   ├── reliability/       # Circuit breaker, retry queue
│   │   ├── observability/     # Health checks, metrics
│   │   ├── persistence/       # State file, audit ledger
│   │   └── security/          # Vault passphrase management
│   │
│   ├── adapters/              # Tool bindings (pluggable)
│   │   ├── base.py            #   Adapter ABC
│   │   ├── registry.py        #   Adapter registry + mock swap
│   │   ├── mock.py            #   Universal mock adapter
│   │   ├── shell/             #   Shell command + filesystem adapters
│   │   ├── vcs/               #   Git adapter
│   │   ├── containers/        #   Docker adapter
│   │   └── languages/         #   Python, Node adapters
│   │
│   └── ui/
│       ├── cli/               # Click CLI commands — 19 domain packages
│       │   ├── audit/         #   audit scan/dismiss/status
│       │   ├── backup/        #   backup create/list/restore/delete
│       │   ├── ci/            #   ci detect/compose/generate
│       │   ├── content/       #   content encrypt/decrypt/optimize/release
│       │   ├── dns/           #   dns detect/lookup/generate
│       │   ├── docker/        #   docker detect/build/status
│       │   ├── docs/          #   docs build/detect/status
│       │   ├── git/           #   git status/log/commit/push/gh
│       │   ├── infra/         #   infra detect/status
│       │   ├── k8s/           #   k8s detect/generate/apply/status
│       │   ├── metrics/       #   metrics collect/report
│       │   ├── packages/      #   packages detect/audit
│       │   ├── pages/         #   pages build/deploy/list/builders
│       │   ├── quality/       #   quality check/lint
│       │   ├── secrets/       #   secrets status/set/remove/list/generate
│       │   ├── security/      #   security scan/status
│       │   ├── terraform/     #   terraform detect/plan/apply
│       │   ├── testing/       #   testing run/status
│       │   └── vault/         #   vault lock/unlock/status/export
│       └── web/               # Flask web admin
│           ├── server.py      #   App factory + blueprint registration
│           ├── helpers.py     #   Shared route helpers
│           ├── routes/        #   31 Flask blueprint packages
│           │   ├── api/       #     Core: status, run, detect, health
│           │   ├── vault/     #     Lock, unlock, status, export, import
│           │   ├── secrets/   #     List, set, delete, push, pull
│           │   ├── content/   #     Browse, preview, encrypt, upload, glossary
│           │   ├── chat/      #     Chat threads, messages, sync
│           │   ├── audit/     #     Security audit scan, findings
│           │   ├── devops/    #     DevOps card operations
│           │   ├── integrations/ #  Git, GitHub, CI/CD operations
│           │   ├── k8s/       #     Kubernetes cluster, wizard, helm
│           │   ├── docker/    #     Docker operations
│           │   ├── terraform/ #     Terraform operations
│           │   ├── pages/     #     Pages build, deploy, config
│           │   ├── backup/    #     Backup, restore, archive
│           │   ├── smart_folders/ #  Smart folder tree, file access
│           │   └── ...        #     + 17 more domain packages
│           ├── static/css/admin.css  # Dark-mode CSS
│           └── templates/            # Jinja2 templates
│               ├── dashboard.html    #   Master SPA template
│               ├── partials/         #   HTML structure (9 tab partials)
│               └── scripts/          #   JS logic (11 subdirectories + root files)
│                   ├── globals/      #     Shared: api, cache, modals
│                   ├── content/      #     Content tab (17 files)
│                   ├── secrets/      #     Secrets tab
│                   ├── integrations/ #     Integrations tab
│                   ├── devops/       #     DevOps tab
│                   ├── wizard/       #     Setup wizard
│                   ├── audit/        #     Audit tab
│                   ├── assistant/    #     Assistant panel
│                   ├── k8s_wizard/   #     K8s sub-wizard
│                   ├── docker_wizard/#     Docker sub-wizard
│                   └── auth/         #     Auth modules
│
├── stacks/                    # Technology definitions (20 stacks)
│   ├── python/stack.yml
│   ├── node/stack.yml
│   ├── docker-compose/stack.yml
│   └── ...
│
├── .state/                    # Generated state (disposable)
│   ├── current.json           #   Current project state
│   └── audit.ndjson           #   Append-only operation log
│
├── tests/                     # pytest suite (40+ test files)
│
├── docs/                      # Documentation
└── .pages/                    # Pages build workspace (gitignored)
```

---

## Key Modules

### Core Models (`src/core/models/`)

All models use **Pydantic** for validation, serialization, and schema export:

- **Project** — name, description, repository, modules, environments
- **Module** — name, path, domain, stack
- **Stack** — name, detection rules, capabilities
- **Action** — what to do (capability + adapter + module)
- **Receipt** — result of an action (success/failure/skip + output)
- **ProjectState** — root aggregate of detected modules, versions, last operation

### Adapters (`src/adapters/`)

Adapters translate domain intent into side effects.

Key properties:
- **Receipts, not exceptions** — `execute()` always returns a Receipt
- **Mock mode** — `AdapterRegistry(mock_mode=True)` swaps all adapters to mocks
- **Capability reporting** — adapters declare what they can do

### Web Admin (`src/ui/web/`)

A Flask-based single-page app with 9 tabs:

| Tab | Partial | Script Directory |
|-----|---------|-----------------|
| 📊 Dashboard | `_tab_dashboard.html` | `scripts/_dashboard.html` |
| 🧙 Setup | `_tab_wizard.html` | `scripts/wizard/` |
| 🔐 Secrets | `_tab_secrets.html` | `scripts/secrets/` |
| ⚡ Commands | `_tab_commands.html` | `scripts/_commands.html` |
| 📁 Content | `_tab_content.html` | `scripts/content/` (17 files) |
| 🔌 Integrations | `_tab_integrations.html` | `scripts/integrations/` |
| 🛠 DevOps | `_tab_devops.html` | `scripts/devops/` |
| 🔍 Audit | `_tab_audit.html` | `scripts/audit/` |
| 🐛 Debugging | `_tab_debugging.html` | `scripts/_debugging.html` |

Each tab follows the same pattern: **partial for HTML structure, script
subdirectory for JS logic**. No business logic in the frontend — all actions
call API endpoints.

### Reliability (`src/core/reliability/`)

- **Circuit Breaker** — CLOSED → OPEN → HALF_OPEN state machine per adapter
- **Retry Queue** — persistent, exponential backoff with max retries

### Security (`src/core/services/vault/`)

- **AES-256-GCM** encryption with PBKDF2-SHA256 key derivation
- **100,000 KDF iterations** (600,000 for portable exports)
- **Secure delete** — 3-pass random overwrite before unlink
- **Auto-lock** — timer-based re-encryption after inactivity
- **Rate limiting** — on failed passphrase attempts
- **Channel-independent** — accessible from CLI, TUI, and web equally

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12 |
| CLI | Click |
| Web | Flask + Jinja2 |
| Models | Pydantic v2 |
| Encryption | `cryptography` (AES-256-GCM) |
| Lint | Ruff |
| Type check | mypy |
| Tests | pytest |
| CI | GitHub Actions |

---

## See Also

- [DESIGN.md](DESIGN.md) — Design philosophy and principles
- [ADAPTERS.md](ADAPTERS.md) — How to create adapters
- [STACKS.md](STACKS.md) — How to create stack definitions
- [WEB_ADMIN.md](WEB_ADMIN.md) — Web dashboard guide
- [PAGES.md](PAGES.md) — Pages builder system
- [VAULT.md](VAULT.md) — Vault & secrets
