# DevOps Control Plane

> A general-purpose project control plane for DevOps automation.

**Detect** project modules, **match** them to stack definitions, **run** capabilities through adapters, and **audit** every operation — all from a unified CLI and web dashboard.

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/cyberpunk042/devops-control-plane.git
cd devops-control-plane
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 2. Discover your project
./manage.sh detect

# 3. Check status
./manage.sh status

# 4. Run automations (mock mode for safety)
./manage.sh run test --mock

# 5. Launch the web dashboard
./manage.sh web --mock
```

See [docs/QUICKSTART.md](docs/QUICKSTART.md) for the full 5-minute guide.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    CLI / Web UI                       │
├──────────────────────────────────────────────────────┤
│                    Use Cases                          │
│  detect • run • status • config check • health       │
├──────────────────────────────────────────────────────┤
│  Engine         │  Reliability    │  Observability    │
│  executor       │  circuit breaker│  health checks    │
│  build_actions  │  retry queue    │  metrics          │
│  execute_plan   │                 │                   │
├──────────────────────────────────────────────────────┤
│              Adapter Registry                        │
│  shell • filesystem • (docker, k8s, ...)             │
├──────────────────────────────────────────────────────┤
│  Models         │  Persistence    │  Config           │
│  Action/Receipt │  state file     │  project.yml      │
│  Module/Stack   │  audit ledger   │  stack.yml        │
└──────────────────────────────────────────────────────┘
```

---

## Features

### 📦 Module Detection
Automatically detects project modules by scanning for marker files (e.g., `pyproject.toml`, `package.json`, `docker-compose.yml`) and matches them to stack definitions.

### ⚡ Automation Engine
Execute capabilities (test, lint, build, deploy) across any combination of modules. The engine handles action planning, execution, and result aggregation.

### 🛡️ Reliability
- **Circuit breakers** protect adapters from cascading failures (CLOSED → OPEN → HALF_OPEN state machine)
- **Retry queue** with exponential backoff + jitter, persisted to disk

### 📊 Observability
- **Health checks** aggregate component status into system-level health
- **Metrics** (counters, gauges, histograms) for operation tracking
- **Audit log** records every operation in NDJSON format

### 🌐 Web Dashboard
Dark-mode admin dashboard with real-time status, module list, automation runner, and activity feed.

### 🔌 Adapter Protocol
Pluggable adapter system — implement `Adapter.execute()` to add support for any tool or platform.

---

## CLI Commands

| Command | Description |
|---|---|
| `status [--json]` | Project overview: modules, environments, last operation |
| `detect [--json] [--no-save]` | Scan for modules and match stacks |
| `config check [--json]` | Validate `project.yml` |
| `run <capability> [--mock] [--dry-run] [-m module] [--json]` | Execute a capability |
| `health [--json]` | System health status |
| `web [--mock] [--port 8000]` | Start web admin dashboard |

Global flags: `--verbose`, `--quiet`, `--config <path>`

---

## Project Configuration

### `project.yml`

```yaml
name: my-project
description: My multi-service project
repository: github.com/org/my-project

modules:
  - name: api
    path: services/api
    domain: backend
    stack: python
  - name: frontend
    path: services/frontend
    domain: frontend
    stack: node

environments:
  - name: dev
    default: true
  - name: staging
  - name: production
```

### Stack Definitions (`stacks/<name>/stack.yml`)

```yaml
name: python
detection:
  files_any_of:
    - pyproject.toml
    - requirements.txt
capabilities:
  - name: test
    command: "pytest"
  - name: lint
    command: "ruff check ."
```

See [docs/STACKS.md](docs/STACKS.md) for details on creating stacks.

---

## Documentation

| Document | Description |
|---|---|
| [QUICKSTART.md](docs/QUICKSTART.md) | 5-minute setup guide |
| [STACKS.md](docs/STACKS.md) | How to create stack definitions |
| [ADAPTERS.md](docs/ADAPTERS.md) | How to create adapters |
| [DESIGN.md](docs/DESIGN.md) | Architecture and design decisions |
| [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Milestone-based implementation plan |

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run the full check suite (lint + types + tests)
make check

# Individual commands
make lint     # ruff
make types    # mypy
make test     # pytest
```

---

## License

MIT
