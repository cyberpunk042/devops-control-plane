# Web Admin

> **115 .py files. 139 templates. 7,208 lines of CSS. The browser-based control plane.**
>
> The web admin is a Flask-based single-page application that provides a
> browser interface for managing the project. It exposes 33 API blueprints
> across 31 route domains, renders a tabbed dashboard with live data injection,
> and communicates with the same core services used by the CLI.

---

## How It Works

The web admin follows a classic Flask architecture: an **app factory**
creates the application, **blueprints** organize routes into domains, and
**Jinja2 templates** render the single-page dashboard. All business logic
lives in `core/services/` — routes are thin HTTP wrappers.

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Browser (SPA)                                 │
│                                                                      │
│  dashboard.html ── loads partials (tabs) + scripts (JS logic)       │
│  ├── _tab_dashboard.html     Overview + project status              │
│  ├── _tab_integrations.html  Docker, Git, GitHub, CI                │
│  ├── _tab_devops.html        9 DevOps cards (env, k8s, etc.)       │
│  ├── _tab_audit.html         Code quality analysis                  │
│  ├── _tab_content.html       Media gallery + vault                  │
│  ├── _tab_secrets.html       Secrets management                     │
│  ├── _tab_commands.html      Terminal / command runner              │
│  ├── _tab_debugging.html     Tracing + stage debugger              │
│  └── _tab_wizard.html        Setup wizard                          │
│                                                                      │
│  All JS logic lives in <script> blocks inside templates/scripts/    │
│  No external JS framework — vanilla JS with Jinja2 templating      │
└───────────────────────┬──────────────────────────────────────────────┘
                        │
                        │  REST API calls (JSON)
                        │  SSE stream (events)
                        ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      Flask App (server.py)                           │
│                                                                      │
│  create_app()                                                        │
│  ├── Configure: PROJECT_ROOT, CONFIG_PATH, MOCK_MODE                │
│  ├── Register 33 blueprints (31 under /api, 2 at root)             │
│  ├── Inject data catalogs into templates (context_processor)        │
│  ├── Track vault activity (before_request)                          │
│  └── Start staleness watcher (background mtime polling)             │
│                                                                      │
│  run_server()                                                        │
│  └── Flask dev server on 127.0.0.1:8000, threaded                  │
└───────────────────────┬──────────────────────────────────────────────┘
                        │
                        │  Delegates to core services
                        ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    src/core/services/*                                │
│                                                                      │
│  Same service layer used by CLI                                      │
│  docker_ops, git_ops, vault, audit/, pages_engine, etc.             │
└──────────────────────────────────────────────────────────────────────┘
```

### Request Lifecycle

```
Browser: GET /api/docker/containers
    │
    ├─ Flask resolves blueprint: docker_bp (url_prefix="/api")
    │    route: /docker/containers
    │
    ├─ Route handler:
    │    root = project_root()                    ← from helpers.py
    │    from core.services.docker_ops import docker_containers
    │    result = docker_containers(root)
    │    return jsonify(result)
    │
    └─ Response: 200 OK { "containers": [...] }
```

### Data Injection Pipeline

On every page render, the Flask context processor injects pre-cached data
so the dashboard loads instantly without waiting for API calls:

```
App startup
    │
    ├─ _inject_data_catalogs() runs before every template render
    │   ├─ Reads devops cache from disk (all _INJECT_KEYS)
    │   ├─ Loads data catalog registry (stacks, integrations)
    │   └─ Returns { dcp_data, initial_state } to Jinja2 context
    │
    └─ Template renders with {{ initial_state | tojson }}
        └─ JS reads injected data → renders cards immediately
            └─ Background API polls refresh data on schedule
```

### SSE Event Stream

The web admin uses Server-Sent Events (SSE) for real-time updates:

```
Browser: GET /api/events/stream
    │
    ├─ EventBus publishes events:
    │   ├── state:stale      File changed on disk
    │   ├── auth:needed      SSH/HTTPS auth required
    │   ├── audit:progress   Scan progress update
    │   ├── audit:complete   Scan finished
    │   └── chat:new         New chat message
    │
    └─ Client-side _event_stream.html handles & dispatches
```

---

## File Map

```
src/ui/web/
├── __init__.py                    Module marker (1 line)
├── server.py                      Flask app factory + run_server (237 lines)
├── helpers.py                     Shared utilities for routes (184 lines)
├── Dockerfile                     Container build spec
│
├── routes/                        31 route domains, 112 .py files, 10,851 lines
│   ├── __init__.py                Empty (1 line)
│   ├── api/                       Core status & stacks API (230 lines)
│   ├── artifacts/                 Release artifact management (448 lines)
│   ├── audit/                     Audit tab — scan, install, analysis (2,174 lines) ★
│   ├── backup/                    Backup/restore operations (495 lines)
│   ├── changelog/                 Changelog generation (350 lines)
│   ├── chat/                      Chat threads, messages, sync (641 lines)
│   ├── ci/                        CI/CD status & generation (88 lines)
│   ├── config/                    Project configuration API (83 lines)
│   ├── content/                   Content files, preview, manage (888 lines)
│   ├── dev/                       Dev mode utilities (86 lines)
│   ├── devops/                    DevOps card detection & apply (459 lines)
│   ├── dns/                       DNS/CDN operations (78 lines)
│   ├── docker/                    Docker actions & streaming (428 lines)
│   ├── docs/                      Documentation status (88 lines)
│   ├── events/                    SSE event stream (69 lines)
│   ├── git_auth/                  Git SSH/HTTPS auth (207 lines)
│   ├── infra/                     Infrastructure & env files (134 lines)
│   ├── integrations/              Git, GitHub, history (895 lines)
│   ├── k8s/                       Kubernetes operations (395 lines)
│   ├── metrics/                   Health & summary endpoints (130 lines)
│   ├── packages/                  Package management (119 lines)
│   ├── pages/                     Pages builder API & serving (541 lines)
│   ├── project/                   Project info endpoint (67 lines)
│   ├── quality/                   Code quality actions (117 lines)
│   ├── secrets/                   Secrets CRUD (210 lines)
│   ├── security_scan/             Security scanning (143 lines)
│   ├── server/                    Server status endpoint (48 lines)
│   ├── smart_folders/             Module tree resolution (190 lines)
│   ├── terraform/                 Terraform operations (182 lines)
│   ├── testing/                   Test execution (106 lines)
│   ├── trace/                     Request tracing (340 lines)
│   └── vault/                     Vault encryption & keys (421 lines)
│
├── templates/                     139 HTML/Jinja2 files, 53,702 lines
│   ├── dashboard.html             Main SPA entry point (86 lines)
│   ├── partials/                  Tab content fragments (12 files)
│   │   ├── _head.html             HTML head, meta, CSS links
│   │   ├── _nav.html              Top navigation bar
│   │   ├── _tab_dashboard.html    Dashboard overview tab
│   │   ├── _tab_integrations.html Docker/Git/GitHub/CI tab
│   │   ├── _tab_devops.html       DevOps cards tab
│   │   ├── _tab_audit.html        Code audit tab
│   │   ├── _tab_content.html      Content management tab
│   │   ├── _tab_secrets.html      Secrets tab
│   │   ├── _tab_commands.html     Terminal tab
│   │   ├── _tab_debugging.html    Trace/debug tab
│   │   ├── _tab_wizard.html       Setup wizard tab
│   │   └── _content_modals.html   Content preview/edit modals
│   └── scripts/                   Client-side JS logic (127 files)
│       ├── _boot.html             App bootstrap (120 lines)
│       ├── _tabs.html             Tab switching logic (141 lines)
│       ├── _dashboard.html        Dashboard card rendering (661 lines)
│       ├── _event_stream.html     SSE client (761 lines)
│       ├── _monaco.html           Monaco editor integration (310 lines)
│       ├── _commands.html         Terminal/command logic (247 lines)
│       ├── _debugging.html        Trace viewer logic (1,145 lines)
│       ├── _stage_debugger.html   Stage debugger UI (702 lines)
│       ├── _settings.html         Settings panel (303 lines)
│       ├── _lang.html             Internationalization (79 lines)
│       ├── _theme.html            Dark/light theme (36 lines)
│       ├── _dev_mode.html         Dev mode controls (58 lines)
│       ├── assistant/             AI assistant panel (7 files)
│       ├── audit/                 Audit tab scripts (7 files)
│       ├── auth/                  Auth modals (3 files)
│       ├── content/               Content tab scripts (16 files)
│       ├── devops/                DevOps card scripts (13 files)
│       ├── docker_wizard/         Docker setup wizard (3 files)
│       ├── globals/               Shared UI components (8 files)
│       ├── integrations/          Integration tab scripts (18 files)
│       ├── k8s_wizard/            K8s setup wizard (9 files)
│       ├── secrets/               Secrets tab scripts (8 files)
│       └── wizard/                Setup wizard scripts (10 files)
│
└── static/                        Static assets (2 files)
    ├── css/admin.css              All CSS styles (7,208 lines)
    └── data/assistant-catalogue.json  Assistant content definitions
```

---

## Per-File Documentation

### `server.py` — App Factory (237 lines)

The Flask application factory. Creates, configures, and returns the Flask app.

| Function | Lines | Purpose |
|----------|-------|---------|
| `create_app(project_root, config_path, mock_mode)` | 22–218 | Factory: configure app, register 33 blueprints, set up context processor, start watchers |
| `_track_vault_activity()` | 130–134 | `before_request` hook: resets vault auto-lock timer on every request |
| `_inject_data_catalogs()` | 160–211 | Context processor: injects cached data + data registry into every template |
| `run_server(app, host, port, debug)` | 221–237 | Starts Flask dev server with signal handlers for graceful shutdown |

**Blueprint registration order** (33 blueprints):

| Blueprint | URL Prefix | Domain |
|-----------|-----------|--------|
| `pages_bp` | `/` (root) | Pages serving (built doc sites) |
| `audit_bp` | `/api` (self-prefixed) | Audit scan & analysis |
| `artifacts_bp` | `/api/artifacts` (self-prefixed) | Release artifacts |
| All others | `/api` | REST API endpoints |

**Data injection keys** — Pre-loaded from disk cache for instant dashboard:

```
DevOps tab:     security, testing, quality, packages, env, docs, k8s, terraform, dns
Integrations:   git, github, ci, docker, gh-pulls, gh-runs, gh-workflows
Dashboard:      project-status
Audit (L0/L1):  audit:system, audit:deps, audit:structure, audit:clients, audit:scores
Wizard:         wiz:detect
```

---

### `helpers.py` — Shared Route Utilities (184 lines)

Centralized helpers used across route blueprints. Prevents duplication.

| Function | Purpose |
|----------|---------|
| `project_root()` | Get active project root from Flask app config |
| `resolve_safe_path(relative)` | Path traversal prevention — ensures path stays within project root |
| `get_enc_key()` | Read `CONTENT_VAULT_ENC_KEY` from `.env` for content encryption |
| `get_stack_names()` | Detect project stacks for UI display |
| `bust_tool_caches()` | Invalidate devops caches after tool install/update/remove |
| `requires_git_auth(fn)` | Decorator: checks git auth before executing route, returns 401 if needed |
| `fresh_env(project_root_path)` | Build subprocess env with current `.env` values (not stale startup values) |
| `gh_repo_flag(project_root_path)` | Get `-R repo` flag for `gh` CLI (handles multi-remote repos) |

---

## Route Domains

### Blueprint Inventory

All 33 blueprints organized by functional area:

#### Core Platform

| Blueprint | Package | Files | Lines | Purpose |
|-----------|---------|-------|-------|---------|
| `api` | `routes/api/` | 4 | 230 | Project status, stacks, audit summary |
| `config` | `routes/config/` | 1 | 83 | Read/write project configuration |
| `project` | `routes/project/` | 1 | 67 | Project metadata endpoint |
| `server` | `routes/server/` | 1 | 48 | Server health/status |
| `events` | `routes/events/` | 1 | 69 | SSE event stream |
| `dev` | `routes/dev/` | 1 | 86 | Dev-mode debug utilities |

#### Content & Media

| Blueprint | Package | Files | Lines | Purpose |
|-----------|---------|-------|-------|---------|
| `content` | `routes/content/` | 5 | 888 | File browsing, preview, manage, helpers |
| `artifacts` | `routes/artifacts/` | 2 | 448 | Release artifact CRUD |
| `pages` | `routes/pages/` | 3 | 541 | Pages builder API |
| `pages_api` | `routes/pages/` | — | — | Pages API (separate blueprint) |
| `changelog` | `routes/changelog.py` | 1 | 350 | Changelog generation |

#### Security & Auth

| Blueprint | Package | Files | Lines | Purpose |
|-----------|---------|-------|-------|---------|
| `vault` | `routes/vault/` | 7 | 421 | Vault lock/unlock, keys, env management |
| `secrets` | `routes/secrets/` | 3 | 210 | Secrets CRUD |
| `git_auth` | `routes/git_auth/` | 3 | 207 | SSH/HTTPS authentication |
| `security2` | `routes/security_scan/` | 3 | 143 | Security scanning |

#### DevOps & Infrastructure

| Blueprint | Package | Files | Lines | Purpose |
|-----------|---------|-------|-------|---------|
| `devops` | `routes/devops/` | 4 | 459 | DevOps card detection, audit, apply |
| `docker` | `routes/docker/` | 6 | 428 | Container operations + streaming |
| `k8s` | `routes/k8s/` | 8 | 395 | Kubernetes operations + wizard |
| `terraform` | `routes/terraform/` | 3 | 182 | Terraform operations |
| `infra` | `routes/infra/` | 3 | 134 | Infrastructure & env files |
| `dns` | `routes/dns/` | 1 | 78 | DNS/CDN operations |
| `ci` | `routes/ci/` | 3 | 88 | CI/CD status & generation |

#### Integrations

| Blueprint | Package | Files | Lines | Purpose |
|-----------|---------|-------|-------|---------|
| `integrations` | `routes/integrations/` | 9 | 895 | Git, GitHub, history, remotes, terminal |

#### Quality & Metrics

| Blueprint | Package | Files | Lines | Purpose |
|-----------|---------|-------|-------|---------|
| `quality` | `routes/quality/` | 3 | 117 | Code quality actions |
| `testing` | `routes/testing/` | 3 | 106 | Test execution |
| `metrics` | `routes/metrics/` | 3 | 130 | Health & summary |
| `packages` | `routes/packages/` | 3 | 119 | Package management |
| `docs` | `routes/docs/` | 3 | 88 | Documentation status |
| `smart_folders` | `routes/smart_folders/` | 1 | 190 | Module tree resolution |

#### Audit

| Blueprint | Package | Files | Lines | Purpose |
|-----------|---------|-------|-------|---------|
| `audit` | `routes/audit/` | 8 | 2,174 | Full audit pipeline (scan, install, staging, analysis, cache) |

#### Communication

| Blueprint | Package | Files | Lines | Purpose |
|-----------|---------|-------|-------|---------|
| `chat` | `routes/chat/` | 5 | 641 | Chat threads, messages, sync |
| `trace` | `routes/trace/` | 4 | 340 | Request tracing, recording, sharing |
| `backup` | `routes/backup/` | 5 | 495 | Backup/restore operations |

---

## Template Architecture

The web admin is a **single-page application** rendered by Jinja2 templates.
No React, no Vue, no external JS framework — all client-side logic is
vanilla JavaScript inside `<script>` blocks.

### Page Structure

```
dashboard.html                        ← Main entry point
    │
    ├── {% include "partials/_head.html" %}        HTML head, CSS
    ├── {% include "partials/_nav.html" %}          Top nav bar
    │
    ├── Tab containers (one visible at a time):
    │   ├── {% include "partials/_tab_dashboard.html" %}
    │   ├── {% include "partials/_tab_integrations.html" %}
    │   ├── {% include "partials/_tab_devops.html" %}
    │   ├── {% include "partials/_tab_audit.html" %}
    │   ├── {% include "partials/_tab_content.html" %}
    │   ├── {% include "partials/_tab_secrets.html" %}
    │   ├── {% include "partials/_tab_commands.html" %}
    │   ├── {% include "partials/_tab_debugging.html" %}
    │   └── {% include "partials/_tab_wizard.html" %}
    │
    └── Scripts (loaded in order):
        ├── {% include "scripts/_boot.html" %}         Initialization
        ├── {% include "scripts/_tabs.html" %}          Tab switching
        ├── {% include "scripts/_event_stream.html" %}  SSE client
        ├── {% include "scripts/_dashboard.html" %}     Dashboard logic
        ├── {% include "scripts/_monaco.html" %}        Editor
        ├── {% include "scripts/_commands.html" %}      Terminal
        ├── {% include "scripts/_settings.html" %}      Settings panel
        ├── {% include "scripts/_theme.html" %}         Theme toggle
        ├── {% include "scripts/_lang.html" %}          i18n
        ├── {% include "scripts/_debugging.html" %}     Trace viewer
        ├── {% include "scripts/_stage_debugger.html" %}
        │
        └── Domain-specific scripts:
            ├── scripts/auth/           Git/GitHub auth modals
            ├── scripts/assistant/      AI assistant panel
            ├── scripts/audit/          Audit tab logic
            ├── scripts/content/        Content tab logic
            ├── scripts/devops/         DevOps card logic
            ├── scripts/globals/        Shared UI (modals, API, cache)
            ├── scripts/integrations/   Integration tab logic
            ├── scripts/secrets/        Secrets tab logic
            ├── scripts/wizard/         Setup wizard
            ├── scripts/docker_wizard/  Docker wizard
            └── scripts/k8s_wizard/     K8s wizard
```

### Script Organization (127 files, ~49,000 lines)

Client-side scripts are organized by domain, matching the tab structure:

| Directory | Files | Purpose |
|-----------|-------|---------|
| `scripts/globals/` | 8 | Shared: API client, modal system, card builders, cache, auth |
| `scripts/audit/` | 7 | Audit tab: scan triggers, L2 analysis, score display |
| `scripts/content/` | 16 | Content: gallery, preview, encrypt/decrypt, upload |
| `scripts/devops/` | 13 | DevOps: 9 domain cards + manager + init |
| `scripts/integrations/` | 18 | Integration cards + setup wizards |
| `scripts/assistant/` | 7 | AI assistant: catalogue, resolver, panel |
| `scripts/secrets/` | 8 | Secrets CRUD UI |
| `scripts/wizard/` | 10 | Main setup wizard |
| `scripts/docker_wizard/` | 3 | Docker config wizard |
| `scripts/k8s_wizard/` | 9 | Kubernetes config wizard |
| `scripts/auth/` | 3 | SSH/GitHub auth modals |

### Styling — `admin.css` (7,208 lines)

All CSS lives in a single file. The stylesheet covers:

- Base reset and typography
- Dark mode color scheme
- Tab layout and transitions
- Card components (DevOps and integration cards)
- Modal system
- Monaco editor integration
- Responsive breakpoints
- Wizard step indicators
- Assistant panel layout
- Content gallery grid
- Glassmorphism effects

---

## Dependency Graph

The web module has a strict one-directional dependency: **Web → Core**.
No core module imports from web. No cross-blueprint imports.

```
src/ui/web/
    │
    ├── server.py
    │   ├── flask (Flask, Blueprint)
    │   ├── src.core.context (project root registration)
    │   ├── src.core.data (data catalog registry)
    │   ├── src.core.services.devops.cache (pre-load cached data)
    │   ├── src.core.config.stack_loader (stack discovery)
    │   ├── src.core.services.vault (auto-lock timer)
    │   └── src.core.services.staleness_watcher (file change events)
    │
    ├── helpers.py
    │   ├── src.core.config.loader (project discovery)
    │   ├── src.core.services.secrets_ops (env key reading)
    │   ├── src.core.services.devops.cache (cache invalidation)
    │   ├── src.core.services.git_auth (auth checking)
    │   └── src.core.services.event_bus (auth events)
    │
    └── routes/*
        └── Each route domain imports from its matching core service:
            routes/docker/  → core/services/docker_ops
            routes/vault/   → core/services/vault
            routes/audit/   → core/services/audit/
            routes/content/ → core/services/content/
            routes/pages/   → core/services/pages_engine
            ... (same pattern for all 31 domains)
```

**No template imports Python** — templates only use Jinja2 variables
injected by Flask's context processor or passed via `render_template()`.

---

## Consumers

| Consumer | What It Uses |
|----------|-------------|
| `manage.sh web` | Entry point: calls `create_app()` → `run_server()` |
| `src/main.py` (`controlplane web`) | Alternate entry via CLI command |
| Browser clients | HTTP + SSE to all `/api` endpoints |
| CI pipelines | Automated testing of API endpoints |

---

## Design Decisions

### Why Flask Instead of FastAPI?

Flask was chosen for the web admin because:

- **Template rendering** — Flask + Jinja2 provides server-side rendering
  for the SPA shell, with data injection at render time
- **Simplicity** — the web admin is a local tool, not a cloud API; Flask's
  synchronous model is adequate for single-user operation
- **Blueprint organization** — Flask blueprints map cleanly to route domains
- **Mature ecosystem** — well-understood patterns for auth, middleware, etc.

### Why a Single-Page App Without a JS Framework?

The web admin uses vanilla JavaScript rather than React/Vue because:

- **No build step** — templates are served directly by Flask, enabling
  live reload with zero compilation
- **Jinja2 data injection** — server-side data is injected directly into
  `<script>` blocks, avoiding the need for a separate API call on first load
- **Template splitting** — each tab and domain has its own template file,
  providing the modularity benefits of components without a framework
- **No npm dependency tree** — reduces complexity for a developer tool

### Why Pre-Load Data via Context Processor?

The `_inject_data_catalogs()` context processor reads cached data from disk
and injects it into every template render. This means:

- **Instant dashboard** — cards render immediately from cached data,
  no loading spinners
- **Degraded gracefully** — if the cache is missing, cards fall back to
  API polling
- **Cold start friendly** — the cache persists across server restarts

### Why 33 Blueprints?

Each route domain is a separate blueprint for:

- **Isolation** — a bug in audit routes doesn't affect vault routes
- **Independent READMEs** — each route domain has its own documentation
  (38 sub-module READMEs already exist)
- **Discoverability** — `routes/docker/` contains all Docker endpoints
- **Parallel development** — developers can work on different domains
  without merge conflicts

### Why Server-Sent Events Instead of WebSockets?

SSE is simpler and sufficient for this use case:

- **One-directional** — the server pushes events; the client only polls
- **Auto-reconnect** — built into the browser's EventSource API
- **No library needed** — native browser support, no socket.io
- **Firewall-friendly** — uses standard HTTP, no upgrade handshake

### Why All CSS in One File?

A single `admin.css` (7,208 lines) instead of per-component CSS:

- **No CSS build step** — no PostCSS, no Tailwind, no SCSS compilation
- **Global dark mode** — theme variables defined once, applied everywhere
- **Specificity control** — all selectors in one hierarchy, easy to debug
- **Cache-friendly** — one HTTP request, one cache entry

---

## Route Pattern

Every route handler follows the same structural pattern:

```python
@bp.route("/docker/containers")
def docker_containers_list():
    """List running Docker containers."""
    from src.core.services.docker_ops import docker_containers
    root = project_root()
    result = docker_containers(root)
    return jsonify(result)
```

**Rules:**
1. Import core service lazily inside the handler
2. Get project root from `helpers.project_root()`
3. Delegate all logic to core service
4. Return JSON via `jsonify()`
5. Never put business logic in route handlers

**For routes requiring git auth:**

```python
@bp.route("/git/push", methods=["POST"])
@requires_git_auth
def git_push():
    """Push to remote — requires SSH/HTTPS auth."""
    ...
```

---

## Summary Statistics

| Component | Count | Lines |
|-----------|-------|-------|
| Python modules (routes + server + helpers) | 115 | 11,273 |
| HTML templates | 139 | 53,702 |
| CSS | 1 | 7,208 |
| JSON (assistant catalogue) | 1 | — |
| Flask blueprints | 33 | — |
| Route domains | 31 | — |
| Existing sub-module READMEs | 38 | — |
| **Total** | **254 files** | **72,183+ lines** |
