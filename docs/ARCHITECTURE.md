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
│  Models       Services       Engine       Use-Cases                  │
│  (Pydantic)   (detection,    (runner,     (detect, status,           │
│               validation)    evaluator)    automate, health)         │
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
project.yml  +  stacks/  +  state/
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
│   │   │   └── state.py       #   ProjectState (root state model)
│   │   ├── config/            # YAML loaders
│   │   │   └── loader.py      #   project.yml → Project model
│   │   ├── services/          # Business logic (detection, validation)
│   │   │   └── detection.py   #   Stack matching, module scanning
│   │   ├── engine/            # Execution loop
│   │   │   └── runner.py      #   Run capabilities through adapters
│   │   ├── use_cases/         # High-level entry points (CLI/Web call these)
│   │   │   ├── detect.py
│   │   │   ├── status.py
│   │   │   ├── automate.py
│   │   │   └── health.py
│   │   ├── reliability/       # Circuit breaker, retry queue
│   │   ├── observability/     # Health checks, metrics
│   │   ├── persistence/       # State file, audit ledger
│   │   └── security/          # Vault passphrase management
│   │
│   ├── adapters/              # Tool bindings (pluggable)
│   │   ├── base.py            #   Adapter ABC
│   │   ├── registry.py        #   Adapter registry + mock swap
│   │   ├── mock.py            #   Universal mock adapter
│   │   └── shell/             #   Shell command + filesystem adapters
│   │
│   └── ui/
│       ├── cli/               # Click CLI commands
│       └── web/               # Flask web admin
│           ├── server.py      #   App factory
│           ├── vault.py       #   AES-256-GCM vault
│           ├── vault_io.py    #   Vault file I/O
│           ├── content_crypto.py     # Content file encryption
│           ├── content_optimize.py   # Image/video optimization
│           ├── content_release.py    # GitHub Release uploads
│           ├── pages_engine.py       # Pages orchestrator
│           ├── pages_builders/       # SSG builder plugins
│           │   ├── base.py           #   PageBuilder ABC + ConfigField
│           │   ├── raw.py            #   Static file copy
│           │   ├── mkdocs.py         #   MkDocs builder
│           │   ├── hugo.py           #   Hugo builder
│           │   ├── docusaurus.py     #   Docusaurus builder
│           │   ├── sphinx.py         #   Sphinx builder
│           │   ├── custom.py         #   User-defined build
│           │   └── template_engine.py  # Docusaurus template system
│           ├── md_transforms.py      # MD → MDX transforms
│           ├── routes_api.py         # Core status/run/detect API
│           ├── routes_vault.py       # Vault lock/unlock API
│           ├── routes_secrets.py     # Secrets management API
│           ├── routes_content*.py    # Content vault API
│           ├── routes_integrations.py # Git/GitHub/CI API
│           ├── routes_pages*.py      # Pages builder API
│           ├── routes_backup*.py     # Backup/restore API
│           ├── routes_config.py      # Config management API
│           ├── static/css/admin.css  # Dark-mode CSS
│           └── templates/            # Jinja2 templates
│               ├── dashboard.html    #   Master template
│               ├── partials/         #   HTML structure (_tab_*.html)
│               └── scripts/          #   JS logic (_*.html)
│
├── stacks/                    # Technology definitions
│   ├── python/stack.yml
│   ├── node/stack.yml
│   └── docker-compose/stack.yml
│
├── state/                     # Generated state (disposable)
│   ├── state.json             #   Current project state
│   └── audit.ndjson           #   Append-only operation log
│
├── tests/                     # pytest suite (280+ tests)
│   ├── test_models.py
│   ├── test_config.py
│   ├── test_adapters.py
│   ├── test_cli.py
│   ├── test_detection.py
│   ├── test_engine.py
│   ├── test_reliability.py
│   ├── test_observability.py
│   ├── test_persistence.py
│   ├── test_vault.py
│   ├── test_web.py
│   ├── test_e2e.py
│   └── test_smoke.py
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

A Flask-based single-page app with 7 tabs:

| Tab | Partial | Script |
|-----|---------|--------|
| 📊 Dashboard | `_tab_dashboard.html` | `_dashboard.html` |
| 🧙 Setup | `_tab_wizard.html` | `_wizard.html` |
| 🔐 Secrets | `_tab_secrets.html` | `_secrets*.html` |
| ⚡ Commands | `_tab_commands.html` | `_commands.html` |
| 📁 Content | `_tab_content.html` | `_content*.html` |
| 🔌 Integrations | `_tab_integrations.html` | `_integrations.html` |
| 🐛 Debugging | `_tab_debugging.html` | `_debugging.html` |

Each tab follows the same pattern: **partial for HTML structure, script for JS
logic**. No business logic in the frontend — all actions call API endpoints.

### Reliability (`src/core/reliability/`)

- **Circuit Breaker** — CLOSED → OPEN → HALF_OPEN state machine per adapter
- **Retry Queue** — persistent, exponential backoff with max retries

### Security (`src/ui/web/vault.py`)

- **AES-256-GCM** encryption with PBKDF2-SHA256 key derivation
- **480,000 KDF iterations** (600,000 for portable exports)
- **Secure delete** — 3-pass random overwrite before unlink
- **Auto-lock** — timer-based re-encryption after inactivity
- **Rate limiting** — on failed passphrase attempts

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
