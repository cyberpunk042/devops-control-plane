# DevOps Control Plane

> A general-purpose project control plane for DevOps automation.

**Detect** project modules, **match** them to stack definitions, **run**
capabilities through adapters, **encrypt** secrets with AES-256-GCM,
**manage** content with media optimization, **build** documentation sites
with pluggable SSGs, and **audit** every operation — all from a unified CLI
and web dashboard.

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
./manage.sh web
```

See [docs/QUICKSTART.md](docs/QUICKSTART.md) for the full 5-minute guide.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    CLI / Web Admin                            │
│  manage.sh  │  Click CLI  │  Flask SPA (7 tabs)              │
├──────────────────────────────────────────────────────────────┤
│                    Core Domain (pure)                         │
│  Models  │  Services  │  Engine  │  Use-Cases                │
├──────────────────────────────────────────────────────────────┤
│                    Adapter Layer                              │
│  shell  │  filesystem  │  mock  │  (vcs, containers)         │
├──────────────────────────────────────────────────────────────┤
│                 Invariant Infrastructure                      │
│  Reliability      │  Observability   │  Security   │  State  │
│  circuit breaker  │  health checks   │  AES vault  │  audit  │
│  retry queue      │  metrics         │  rate limit  │  NDJSON │
└──────────────────────────────────────────────────────────────┘
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full layer spec.

---

## Features

### 📦 Module Detection
Automatically scans for modules by matching marker files (`pyproject.toml`,
`package.json`, `docker-compose.yml`) to stack definitions.

### ⚡ Automation Engine
Execute capabilities (test, lint, build, deploy) across modules with
planning, receipts, dry-run, and mock mode.

### 🛡️ Reliability
- **Circuit breakers** — per-adapter failure protection (CLOSED → OPEN → HALF_OPEN)
- **Retry queue** — exponential backoff, persisted to disk

### 📊 Observability
- **Health checks** — component-level status aggregation
- **Metrics** — counters, gauges, histograms (Prometheus-compatible)
- **Audit log** — append-only NDJSON ledger of every operation

### 🔐 Vault & Secrets
- **AES-256-GCM** encryption for `.env` files
- **Auto-lock** with configurable inactivity timer
- **Secrets editor** in the web admin (masked values, add/edit/delete)
- **Export/import** portable encrypted backups

### 📁 Content Management
- **File browser** with inline preview (images, video, audio, markdown)
- **Per-file encryption** with binary envelope format
- **Media optimization** (image compression, video transcoding)
- **GitHub Release** uploads for large files

### 📄 Pages Builder
- **Multi-segment** site generation (docs, blog, API, each with its own builder)
- **6 built-in builders**: Raw, MkDocs, Hugo, Docusaurus, Sphinx, Custom
- **Dynamic config schemas** — each builder declares UI-renderable fields
- **SSE build streaming** — real-time log output
- **Deploy to GitHub Pages** with auto-generated hub page

### 🌐 Web Dashboard
Dark-mode admin with 7 tabs: Dashboard, Setup Wizard, Secrets, Commands,
Content, Integrations (Git/GitHub/Pages), Debugging.

### 🔌 Adapter Protocol
Pluggable adapter system — implement `Adapter.execute()` to add support
for any tool or platform.

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `status [--json]` | Project overview: modules, environments, last operation |
| `detect [--json] [--no-save]` | Scan for modules and match stacks |
| `config check [--json]` | Validate `project.yml` |
| `run <capability> [--mock] [--dry-run] [-m module] [--json]` | Execute a capability |
| `health [--json]` | System health status |
| `web [--mock] [--port 8000]` | Start web admin dashboard |

Global flags: `--verbose`, `--quiet`, `--config <path>`

---

## Documentation

| Document | Description |
|----------|-------------|
| [QUICKSTART.md](docs/QUICKSTART.md) | 5-minute setup guide |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture and file layout |
| [DESIGN.md](docs/DESIGN.md) | Design philosophy and principles |
| [WEB_ADMIN.md](docs/WEB_ADMIN.md) | Web dashboard guide |
| [PAGES.md](docs/PAGES.md) | Pages builder system |
| [VAULT.md](docs/VAULT.md) | Vault & secrets encryption |
| [CONTENT.md](docs/CONTENT.md) | Content management |
| [STACKS.md](docs/STACKS.md) | Creating stack definitions |
| [ADAPTERS.md](docs/ADAPTERS.md) | Creating adapters |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Developer setup and contributing |

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

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for the full development guide.

---

## License

MIT
