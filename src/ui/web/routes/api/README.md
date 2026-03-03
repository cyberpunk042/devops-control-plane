# API Routes — Core Platform Endpoints

> **4 files · 230 lines · 8 endpoints · Blueprint: `api_bp` · Prefix: `/api`**
>
> Top-level platform API — project status, environment detection, automation
> execution, system health, capability discovery, audit log, activity feed,
> and stack definitions. These are the foundational endpoints that the
> dashboard, wizard, and ops modal depend on for project-level operations.
> Every handler delegates to a use-case or service — no business logic here.

---

## How It Works

### Request Flow

```
Dashboard / Wizard / Ops Modal
     │
     ├── GET /api/status          → project overview (modules, configs, integrations)
     ├── POST /api/detect         → run environment detection (save to .devops-state.json)
     ├── POST /api/run            → execute a capability (generate, apply, validate, etc.)
     ├── GET /api/health          → system health check (tools, services, connectivity)
     ├── GET /api/capabilities    → resolved capabilities per module
     ├── GET /api/audit           → audit log entries (audit.ndjson)
     ├── GET /api/audit/activity  → activity feed (card-based, paginated, searchable)
     └── GET /api/stacks          → stack definitions (discovered from stacks/ directory)
     │
     ▼
routes/api/                          ← HTTP layer (this package)
├── status.py  — status, detect, run, health, capabilities
├── audit.py   — audit log + activity feed
└── stacks.py  — stack definitions
     │
     ▼
core/                                ← Business logic (no HTTP)
├── use_cases/status.py    — get_status(), get_capabilities()
├── use_cases/detect.py    — run_detect()
├── use_cases/run.py       — run_automation()
├── observability/health.py — check_system_health()
├── persistence/audit.py   — AuditWriter (audit.ndjson CRUD)
├── services/devops/cache.py — load_activity()
└── config/stack_loader.py — discover_stacks()
```

### Architecture Position

```
┌─────────────────────────────────────────────────────┐
│ routes/api/  — PLATFORM LEVEL                       │
│                                                     │
│ These are the endpoints that answer:                │
│   "What is this project?"  → /status                │
│   "What can it do?"        → /capabilities, /stacks │
│   "What did it do?"        → /audit, /audit/activity│
│   "How's it doing?"        → /health                │
│   "Do something"           → /detect, /run          │
│                                                     │
│ Every other route group (docker/, k8s/, content/,   │
│ etc.) is domain-specific. This group is the one     │
│ that ties the whole platform together.              │
└─────────────────────────────────────────────────────┘
```

---

## File Map

```
routes/api/
├── __init__.py     19 lines  — blueprint definition + sub-module imports
├── status.py      104 lines  — status, detect, run, health, capabilities
├── audit.py        77 lines  — audit log + activity feed (paginated, filtered)
├── stacks.py       30 lines  — stack definitions discovery
└── README.md                 — this file
```

---

## Per-File Documentation

### `__init__.py` — Blueprint Definition (19 lines)

Defines `api_bp`, imports sub-modules to register routes.

```python
api_bp = Blueprint("api", __name__)
from . import status, audit, stacks  # noqa: E402, F401
```

### `status.py` — Platform Status & Automation (104 lines)

The core platform endpoints — project overview, detection, and
automation execution. Uses the `use_cases` layer (not services directly).

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `api_status()` | GET | `/status` | Full project status overview |
| `api_detect()` | POST | `/detect` | Run environment detection (saves state) |
| `api_run()` | POST | `/run` | Execute an automation capability |
| `api_health()` | GET | `/health` | System health check |
| `api_capabilities()` | GET | `/capabilities` | Resolved capabilities per module |

**Helper:**

```python
def _config_path() -> Path | None:
    p = current_app.config.get("CONFIG_PATH")
    return Path(p) if p else None
```

Used by status, detect, run, and capabilities to locate the project
config file. Returns `None` if not configured (auto-discovery mode).

**`/api/status` — project overview:**

```python
from src.core.use_cases.status import get_status

result = get_status(config_path=config_path)
if result.error:
    return jsonify({"error": result.error}), 404
return jsonify(result.to_dict())
```

Returns modules, configurations, integration statuses, and detected
capabilities. This is the first endpoint the dashboard calls on load.

**`/api/detect` — environment detection:**

```python
from src.core.use_cases.detect import run_detect

result = run_detect(config_path=_config_path(), save=True)
```

Always saves detection results (`save=True`). This captures the
current state of the project's environment — installed tools,
active integrations, platform info — and persists it for later use.

**`/api/run` — automation execution:**

```python
data = request.get_json(silent=True) or {}
capability = data.get("capability", "")     # e.g. "docker:generate"
modules = data.get("modules")               # optional: limit scope
environment = data.get("environment", "dev") # dev/staging/prod
dry_run = data.get("dry_run", False)
mock_mode = data.get("mock", current_app.config.get("MOCK_MODE", False))

result = run_automation(
    capability=capability,
    config_path=_config_path(),
    modules=modules,
    environment=environment,
    dry_run=dry_run,
    mock_mode=mock_mode,
)
```

This is the universal "do something" endpoint. The `capability` string
determines what runs (e.g., `docker:generate`, `k8s:validate`, etc.).

**`/api/health` — system health:**

```python
from src.core.observability.health import check_system_health
health = check_system_health()
return jsonify(health.to_dict())
```

Checks tool availability, service connectivity, filesystem permissions.

**`/api/capabilities` — capability discovery:**

```python
from src.core.use_cases.status import get_capabilities
result = get_capabilities(config_path=_config_path(), project_root=_project_root())
```

Returns the resolved set of capabilities available for this project,
considering detected integrations and installed tools.

### `audit.py` — Audit Log & Activity Feed (77 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `api_audit()` | GET | `/audit` | Recent CLI audit log entries |
| `api_audit_activity()` | GET | `/audit/activity` | Paginated, filtered activity feed |

**`/api/audit` — CLI audit log:**

```python
from src.core.persistence.audit import AuditWriter

n = request.args.get("n", 20, type=int)
audit = AuditWriter(project_root=_project_root())
entries = audit.read_recent(n)

return jsonify({
    "total": audit.entry_count(),
    "entries": [e.model_dump(mode="json") for e in entries],
})
```

Reads from `audit.ndjson` — the structured log of CLI operations.
Each entry is a Pydantic model serialized to JSON.

**`/api/audit/activity` — activity feed with pagination + filtering:**

The most complex endpoint in this package. Supports:
- **Card filtering:** `?card=docker` — show only docker-related activity
- **Text search:** `?q=failed` — search across label, summary, target, card
- **Pagination:** `?offset=20&limit=50`

```python
all_entries = devops_cache.load_activity(_project_root(), n=max(n_legacy, 2000))
all_entries = list(reversed(all_entries))  # newest-first

# Card filter
if card_filter:
    filtered = [e for e in filtered if e.get("card") == card_filter]

# Text search (multi-field)
if search_q:
    def _matches(entry: dict) -> bool:
        for field in ("label", "summary", "target", "card"):
            val = entry.get(field, "")
            if val and search_q in str(val).lower():
                return True
        return False
    filtered = [e for e in filtered if _matches(e)]

# Pagination
page = filtered[offset : offset + limit]
```

**Card discovery:** The response also returns `cards` — a deduplicated,
ordered list of card names seen across ALL entries (not just the filtered
page). This powers the frontend's card filter dropdown:

```python
cards_seen: list[str] = []
cards_set: set[str] = set()
for e in all_entries:
    c = e.get("card", "")
    if c and c not in cards_set:
        cards_seen.append(c)   # preserves first-seen order
        cards_set.add(c)
```

### `stacks.py` — Stack Definitions (30 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `api_stacks()` | GET | `/stacks` | Discover and list stack definitions |

```python
from src.core.config.stack_loader import discover_stacks

stacks_dir = _project_root() / "stacks"
stacks = discover_stacks(stacks_dir)

return jsonify({
    name: {
        "name": s.name,
        "description": s.description,
        "capabilities": [
            {"name": c.name, "command": c.command, "description": c.description}
            for c in s.capabilities
        ],
    }
    for name, s in stacks.items()
})
```

Discovers stack definitions from YAML files in the `stacks/` directory.
Each stack defines a set of automation capabilities.

---

## Dependency Graph

```
__init__.py     ← defines api_bp, imports all sub-modules

status.py
├── api_bp                          ← from __init__
├── use_cases.status.get_status     ← lazy import
├── use_cases.status.get_capabilities ← lazy import
├── use_cases.detect.run_detect     ← lazy import
├── use_cases.run.run_automation    ← lazy import
├── observability.health.check_system_health ← lazy import
└── helpers.project_root            ← from ui.web.helpers

audit.py
├── api_bp                          ← from __init__
├── persistence.audit.AuditWriter   ← lazy import
├── services.devops.cache.load_activity ← lazy import
└── helpers.project_root            ← from ui.web.helpers

stacks.py
├── api_bp                          ← from __init__
├── config.stack_loader.discover_stacks ← lazy import
└── helpers.project_root            ← from ui.web.helpers
```

**All core imports are lazy** (inside handler functions, not at module
level). This keeps the import footprint minimal and avoids circular
import chains.

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `api_bp`, registers at `/api` prefix |
| Frontend | `scripts/_dashboard.html` | `/status`, `/capabilities`, `/health` |
| Frontend | `scripts/_boot.html` | `/status` (initial load) |
| Frontend | `scripts/_commands.html` | `/detect`, `/run` |
| Frontend | `scripts/globals/_ops_modal.html` | `/run`, `/detect` |
| Frontend | `scripts/wizard/_setup.html` | `/detect` (post-wizard detection) |
| Frontend | `scripts/wizard/_integrations.html` | `/detect`, `/capabilities` |
| Frontend | `scripts/wizard/_integration_actions.html` | `/detect` |
| Frontend | `scripts/wizard/_helpers.html` | `/status` |
| Frontend | `scripts/integrations/_init.html` | `/detect`, `/status` |
| Frontend | `scripts/audit/_scores.html` | `/audit/activity` |
| Frontend | `scripts/audit/_modals.html` | `/audit` |
| Frontend | `scripts/_debugging.html` | `/status`, `/health` (debug panel) |
| Frontend | `scripts/_dev_mode.html` | `/detect` (dev mode) |
| Frontend | `scripts/auth/_gh_auth.html` | `/status` (auth state check) |
| Frontend | `scripts/assistant/_engine.html` | `/status`, `/capabilities` |

---

## Service Delegation Map

```
Route Handler          →   Core Layer.Function
──────────────────────────────────────────────────
api_status()           →   use_cases.status.get_status()
api_detect()           →   use_cases.detect.run_detect()
api_run()              →   use_cases.run.run_automation()
api_health()           →   observability.health.check_system_health()
api_capabilities()     →   use_cases.status.get_capabilities()
api_audit()            →   persistence.audit.AuditWriter.read_recent()
api_audit_activity()   →   services.devops.cache.load_activity()
api_stacks()           →   config.stack_loader.discover_stacks()
```

---

## Data Shapes

### `/api/status` response

```json
{
    "project_path": "/home/user/my-project",
    "modules": {
        "docker": {"detected": true, "config_file": "docker-compose.yml"},
        "k8s": {"detected": true, "config_file": "k8s/deployment.yaml"},
        "terraform": {"detected": false}
    },
    "integrations": {
        "github": {"configured": true, "repo": "org/repo"},
        "vault": {"locked": false, "has_passphrase": true}
    }
}
```

### `/api/run` request

```json
{
    "capability": "docker:generate",
    "modules": ["web", "api"],
    "environment": "dev",
    "dry_run": false,
    "mock": false
}
```

### `/api/health` response

```json
{
    "status": "healthy",
    "tools": {
        "docker": {"available": true, "version": "24.0.7"},
        "kubectl": {"available": true, "version": "1.28.3"},
        "terraform": {"available": false}
    },
    "services": {
        "github_api": {"reachable": true, "latency_ms": 120}
    }
}
```

### `/api/audit` response

```json
{
    "total": 1247,
    "entries": [
        {
            "timestamp": "2026-02-17T14:30:00Z",
            "command": "detect",
            "status": "success",
            "duration_ms": 450,
            "details": {"modules_found": 3}
        }
    ]
}
```

### `/api/audit/activity` response

```json
{
    "total_all": 2000,
    "total_filtered": 150,
    "offset": 0,
    "limit": 50,
    "has_more": true,
    "cards": ["docker", "k8s", "audit", "security"],
    "entries": [
        {
            "card": "docker",
            "label": "Docker Compose Generated",
            "summary": "Generated docker-compose.yml for 3 services",
            "target": "docker-compose.yml",
            "timestamp": "2026-02-17T14:30:00Z"
        }
    ]
}
```

### `/api/stacks` response

```json
{
    "devops": {
        "name": "devops",
        "description": "Full DevOps toolchain",
        "capabilities": [
            {"name": "docker:generate", "command": "generate docker", "description": "Generate Dockerfiles"},
            {"name": "k8s:validate", "command": "validate k8s", "description": "Validate K8s manifests"}
        ]
    }
}
```

---

## Advanced Feature Showcase

### 1. Activity Feed — Multi-Axis Filtering + Pagination

The `/api/audit/activity` endpoint combines three filtering mechanisms
in a single pass:

```python
# 1. Card filter (exact match on domain card)
if card_filter:
    filtered = [e for e in filtered if e.get("card") == card_filter]

# 2. Full-text search across 4 fields
if search_q:
    filtered = [e for e in filtered if _matches(e)]
    # _matches checks: label, summary, target, card

# 3. Cursor-based pagination
page = filtered[offset : offset + limit]
```

The response includes `has_more` for infinite scroll and `cards` for
the filter dropdown — computed from ALL entries, not just the page.

### 2. Config Path Auto-Discovery

All status/detect/run endpoints support two modes:

```python
config_path = _config_path()  # from Flask app config
# → Path("/path/to/config.yaml")  if CONFIG_PATH is set
# → None                          if not set (auto-discovery)
```

When `None`, the use-case layer auto-discovers the project config
by scanning for known config file patterns. This allows the admin
panel to work without explicit configuration.

### 3. Mock Mode Propagation

The `/api/run` endpoint supports mock mode from two sources:

```python
mock_mode = data.get("mock", current_app.config.get("MOCK_MODE", False))
```

The request body `mock` flag overrides the server-level `MOCK_MODE`.
This allows individual operations to run in mock mode without
restarting the server — used for testing and demos.

### 4. Card Discovery for Filter UI

The activity endpoint builds a deduplicated card list preserving
first-seen order (not alphabetical). This gives the UI a natural
ordering — most recently active cards appear first:

```python
cards_seen: list[str] = []
cards_set: set[str] = set()
for e in all_entries:            # scan ALL entries, not just filtered
    c = e.get("card", "")
    if c and c not in cards_set:
        cards_seen.append(c)     # preserves insertion order
        cards_set.add(c)
```

The final response sorts alphabetically (`sorted(cards_seen)`) for
the dropdown UI, but the underlying order tracking ensures no cards
are missed even when the current filter hides them.

---

## Design Decisions

### Why status.py uses the use_cases layer (not services directly)

The `use_cases` module (`get_status`, `run_detect`, `run_automation`)
orchestrates multiple services together. For example, `get_status()`
reads config, runs detection, resolves capabilities, checks
integrations — all in one call. Using services directly would
duplicate this orchestration logic in the route handler.

### Why all core imports are lazy

Every `from src.core...` import is inside the handler function body.
This is intentional — the API blueprint is imported at server startup,
and eager imports would pull in the entire core layer on boot. Lazy
imports keep startup fast and avoid circular dependency chains.

### Why audit/activity loads up to 2000 entries

The activity feed loads `max(n_legacy, 2000)` entries, then filters
and paginates in Python. This is acceptable because:
1. Activity data is small (each entry is ~200 bytes)
2. Total entries rarely exceed 5,000
3. Card discovery needs access to ALL entries for the filter dropdown
4. The overhead is <50ms for 2,000 entries

### Why stacks.py is only 30 lines

Stack discovery is entirely in `discover_stacks()` in core. The route
is a pure passthrough with response shaping — mapping Pydantic models
to JSON dicts. There is no HTTP-specific logic to add.

---

## Coverage Summary

| Capability | Endpoint | File |
|-----------|----------|------|
| Project status | `/status` | `status.py` |
| Environment detection | `/detect` | `status.py` |
| Automation execution | `/run` | `status.py` |
| System health | `/health` | `status.py` |
| Capability discovery | `/capabilities` | `status.py` |
| CLI audit log | `/audit` | `audit.py` |
| Activity feed (paginated + filtered) | `/audit/activity` | `audit.py` |
| Stack definitions | `/stacks` | `stacks.py` |
