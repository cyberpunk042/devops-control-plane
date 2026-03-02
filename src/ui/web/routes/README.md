# Routes Package

> The HTTP transport layer for the devops control plane.
> 336 endpoints. Zero business logic. Every route is a thin dispatcher
> that translates HTTP requests into service calls and returns JSON.

---

## How It Works

The admin panel is a Flask application. The browser sends HTTP requests
to route endpoints. Each endpoint does exactly three things and nothing else:

```
┌─────────────────────────────────────────────────────────────────────┐
│ BROWSER                                                              │
│   fetch("/api/audit/system")                                         │
└──────────────┬──────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────┐
│ ROUTE HANDLER  (routes/audit/analysis.py)                            │
│                                                                      │
│  1. PARSE — read request.args, request.json, path params             │
│  2. DISPATCH — call a service function from core/services/           │
│  3. RESPOND — return jsonify(result) with a status code              │
│                                                                      │
│  That's it. No subprocess calls. No file I/O. No string formatting.  │
│  No caching logic. No data transformation. If a route handler does   │
│  more than 10 lines, the extra logic belongs in a service.           │
└──────────────┬──────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────┐
│ CORE SERVICE  (core/services/audit/...)                               │
│                                                                      │
│  The actual work. Detection, analysis, scoring, plan resolution,     │
│  file I/O, subprocess execution — all here. Testable without Flask.  │
│  Same service function works from CLI, TUI, or Web.                  │
└──────────────────────────────────────────────────────────────────────┘
```

### Concrete Example — A Thin Route

This is what a route handler looks like. Every one of the 336 endpoints
follows this exact pattern:

```python
@audit_bp.route("/audit/system")
def audit_system():
    """L0 system profile — OS, distro, arch, tooling inventory."""
    root = _project_root()
    result = devops_cache.get_cached(
        root, "audit:system",
        lambda: l0_system_profile(root),
        force=("bust" in request.args),
    )
    return jsonify(result)
```

Parse → dispatch → respond. The route knows nothing about what
`l0_system_profile` does internally. It doesn't know about distro
detection, CLI scanning, or capability probing. It just calls and returns.

### SSE Streaming — The One Exception

Plan execution endpoints use Server-Sent Events to stream step-by-step
progress to the browser. The route still follows the pattern, but wraps
a generator in Flask's `stream_with_context`:

```python
@audit_bp.route("/audit/install-plan/execute", methods=["POST"])
def audit_execute_plan():
    # 1. Parse
    data = request.get_json()
    plan = data.get("plan")
    sudo_password = data.get("sudo_password")

    # 2. Dispatch (returns a generator)
    def generate():
        for event in stream_plan_execution(plan, sudo_password, root):
            yield f"data: {json.dumps(event)}\n\n"

    # 3. Respond (SSE stream)
    return Response(stream_with_context(generate()),
                    content_type="text/event-stream")
```

The step execution logic — DAG scheduling, subprocess management,
remediation analysis, restart detection — lives in
`core/services/tool_install/orchestration/stream.py`. The route
is just the SSE transport wrapper.

---

## Package Architecture

Twenty-eight domain sub-packages, each with its own blueprint and
self-contained route modules. **8,860 lines total.**

```
routes/
│
├── api/                        4 files, 230 lines — Core API + health/status
├── audit/                      7 files, 1,840 lines — Tool provisioning + system analysis
├── backup/                     5 files, 495 lines — Backup & restore
├── chat/                       5 files, 581 lines — Chat sync — messages, refs, threads
├── ci/                         3 files, 88 lines — CI pipeline status + badges
├── config/                     1 file, 83 lines — Project configuration CRUD
├── content/                    5 files, 864 lines — Encrypted content vault
├── dev/                        1 file, 86 lines — Developer/debug endpoints
├── devops/                     4 files, 459 lines — DevOps dashboard control
├── dns/                        1 file, 78 lines — DNS/CDN zone status
├── docker/                     6 files, 428 lines — Docker status, compose, containers
├── docs/                       3 files, 88 lines — Documentation generation
├── events/                     1 file, 69 lines — SSE event stream
├── git_auth/                   3 files, 162 lines — SSH key auth
├── infra/                      3 files, 134 lines — Infrastructure status overview
├── integrations/               7 files, 514 lines — GitHub integration
├── k8s/                        8 files, 395 lines — Kubernetes config + status
├── metrics/                    3 files, 130 lines — Project metrics
├── packages/                   3 files, 119 lines — Package management
├── pages/                      3 files, 430 lines — Documentation site management
├── project/                    1 file, 67 lines — Project metadata CRUD
├── quality/                    3 files, 117 lines — Code quality scans
├── secrets/                    3 files, 210 lines — Secrets management
├── security_scan/              3 files, 143 lines — Security scanning
├── terraform/                  3 files, 182 lines — Terraform state/plan/apply
├── testing/                    3 files, 106 lines — Test runner
├── trace/                      4 files, 340 lines — Execution trace + replay
├── vault/                      7 files, 421 lines — Vault lock/unlock/encrypt
│
├── __init__.py                 Package root
└── README.md                   This file
```

### Domain Size Distribution

| Size | Domains |
|------|---------|
| **Large** (500+ lines) | audit, content, chat, integrations, devops, pages, backup |
| **Medium** (100–499 lines) | docker, vault, k8s, trace, api, secrets, terraform, git_auth, infra, metrics, packages, quality, security_scan, testing |
| **Small** (<100 lines) | ci, config, dev, dns, docs, events, project |

Small domains are often single-file sub-packages that were converted
for structural consistency. They may grow as features expand.

---

## Why Everything Is a Sub-Package

Every domain is a sub-package — even single-file domains like `dns/`
or `events/`. This ensures:

1. **Consistency** — one pattern for everything, no special cases
2. **Extensibility** — adding a second file to `dns/` doesn't require
   restructuring
3. **Blueprint isolation** — each `__init__.py` owns its blueprint
4. **Import uniformity** — `from src.ui.web.routes.X import X_bp`
   works for every domain

For multi-module domains, the sub-package boundary maps to a shared
blueprint:

```
content_bp is defined in content/__init__.py
    ├── files.py registers routes on content_bp
    ├── manage.py registers routes on content_bp
    └── preview.py registers routes on content_bp
```

### Route Naming Conventions

| Convention | Example |
|-----------|---------|
| `__init__.py` owns the blueprint | `audit_bp = Blueprint("audit", ...)` |
| Sub-modules import the blueprint | `from . import audit_bp` |
| Function names match the endpoint | `/api/vault/status` → `vault_status()` |
| GET for reads | `@bp.route("/X/status")` |
| POST for mutations | `@bp.route("/X/lock", methods=["POST"])` |
| `_project_root()` via helpers | Never defined locally |
| Cache-aware reads | `devops_cache.get_cached(root, key, fn, ...)` |

---

## Blueprint Registration

All blueprints are imported and registered in `server.py`:

```python
# Sub-packages — blueprint defined in __init__.py, routes in sub-modules
from src.ui.web.routes.audit import audit_bp
from src.ui.web.routes.backup import backup_bp
from src.ui.web.routes.content import content_bp
from src.ui.web.routes.devops import devops_bp
from src.ui.web.routes.pages import pages_bp, pages_api_bp

# Standalone — one file, one blueprint
from src.ui.web.routes.docker import docker_bp
from src.ui.web.routes.k8s import k8s_bp
# ... 21 more

# Registration — most get /api prefix at registration time
app.register_blueprint(pages_bp)                     # no prefix (serves /)
app.register_blueprint(audit_bp)                     # has url_prefix="/api" built-in
app.register_blueprint(docker_bp, url_prefix="/api") # prefix at registration
```

**Why does audit_bp have its prefix built in?** Because the audit sub-package
was the first to be split (1,781 lines → 7 modules), and baking the prefix
into the blueprint means sub-modules don't need to repeat it. The other
sub-packages receive their prefix at `register_blueprint()` time — both
approaches work, audit just predates the convention.

---

## Shared Utilities — `helpers.py`

Route handlers never import from each other. If two routes need the same
logic, it lives in `helpers.py` (route-level) or `core/services/` (business-level).

```python
from src.ui.web.helpers import (
    project_root,        # Path(current_app.config["PROJECT_ROOT"])
    resolve_safe_path,   # path traversal guard — rejects "../" escapes
    get_enc_key,         # reads encryption key from .env
    get_stack_names,     # loads stack names from project config
    bust_tool_caches,    # invalidates integrations + devops + wiz:detect caches
    requires_git_auth,   # decorator — aborts 401 if SSH key not unlocked
)
```

**Before this refactor:** `_project_root()` was copy-pasted into 28 files.
`_resolve_safe_path()` and `_get_enc_key()` were defined in `routes_content.py`
and imported by 3 other route files — creating inter-route dependencies.
`requires_git_auth` lived in `routes_git_auth.py` and was imported by 3 consumers.
`_get_stack_names()` was duplicated in `routes_quality.py` and `routes_security_scan.py`.

**After:** Six functions, one file, zero inter-route imports.

---

## The Cache Layer

Most DevOps card endpoints don't call services directly — they go through
`devops_cache`, a per-key LRU cache with background recomputation:

```python
@devops_bp.route("/devops/prefs", methods=["GET"])
def devops_prefs_get():
    return jsonify(devops_cache.load_prefs(_project_root()))

# Cache-aware pattern (most audit/devops endpoints):
@audit_bp.route("/audit/system")
def audit_system():
    root = _project_root()
    return jsonify(devops_cache.get_cached(
        root, "audit:system",
        lambda: l0_system_profile(root),
        force=("bust" in request.args),
    ))
```

When the user installs a tool and caches need busting, routes call
`bust_tool_caches()` — a single helper that invalidates integrations,
devops, and wizard detection caches in one shot. Before this refactor,
that same 4-line cache-bust block was copy-pasted 8 times.

---

## Design Decisions

### Why domain grouping (Option B) instead of all-flat?

The naming convention already told us the answer. Files named
`routes_content_files.py`, `routes_content_manage.py`, `routes_content_preview.py`
are already a package — they just used underscores instead of slashes.
The refactor made the implicit structure explicit:

```
BEFORE                              AFTER
routes_content.py                   routes/content/__init__.py
routes_content_files.py             routes/content/files.py
routes_content_manage.py            routes/content/manage.py
routes_content_preview.py           routes/content/preview.py
```

### Why not group docker + k8s + terraform into an "infra/" sub-package?

Because they don't share a blueprint. Each has its own blueprint registered
independently. Grouping them would be **organizational** (for humans) but
would add an import indirection layer with no structural benefit. If they
grow inter-dependencies in the future, they can be grouped then — not before.

### Why is tool_execution.py 822 lines?

It contains two SSE streaming generators (execute + resume) that are
inherently complex. The shared step-execution logic was already extracted
to `core/services/tool_install/orchestration/stream.py` — but the SSE
event formatting, Flask response wrapping, and per-endpoint setup
(resolve plan vs load saved plan, pre-flight checks vs not) remain in the
route layer because they're transport concerns, not business logic.

This is the one exception to the "< 350 lines" target. Splitting it
further would separate the SSE `yield` statements from their setup
code, making the streaming flow harder to trace.

### Why does audit_bp bake in its url_prefix?

The audit sub-package was the first to be split (1,781 lines → 7 modules),
and baking the prefix into the blueprint means sub-modules don't need
to repeat it. The other sub-packages receive their prefix at
`register_blueprint()` time. Both approaches work — audit just
predates the convention. Changing it now would break existing tests.

### Why helpers.py instead of a base class or decorator factory?

Routes are plain functions, not class methods. Flask doesn't benefit
from inheritance. A `helpers.py` module with 6 pure functions is the
simplest approach — no metaclasses, no mixin chains, no magic.
Every route file has the same `from src.ui.web.helpers import ...` line,
making the dependency explicit and grep-able.

---

## Error Handling Patterns

All route handlers follow Flask's standard error patterns:

```python
# Validation error — 400
if not data or not data.get("key"):
    return jsonify({"error": "Missing required field: key"}), 400

# Not found — 404
if not result:
    return jsonify({"error": "Resource not found"}), 404

# Service error — the service returns {"error": "..."}
result = some_service_function(root, ...)
if "error" in result:
    return jsonify(result), 400  # or 500 depending on context

# Happy path — 200
return jsonify(result)
```

**Path traversal guard:**
```python
safe_path = resolve_safe_path(root, user_path)
if safe_path is None:
    return jsonify({"error": "Invalid path"}), 400
```

This is enforced for all endpoints that accept user-provided file paths.
The `resolve_safe_path()` function resolves the path, then checks it
doesn't escape the project root via `../` or symlink attacks.

---

## Testing Patterns

Routes are tested by calling them via Flask's test client:

```python
def test_audit_system(client, project_root):
    """Every route test follows the same pattern."""
    response = client.get("/api/audit/system")
    assert response.status_code == 200
    data = response.get_json()
    assert "os" in data
    assert "distro" in data
```

**Cache busting in tests:**
```python
# Force a fresh computation, bypassing cache
response = client.get("/api/audit/system?bust")
```

**SSE stream testing:**
```python
response = client.post(
    "/api/audit/install-plan/execute",
    json={"plan": plan_data},
)
assert response.content_type == "text/event-stream"
events = [
    json.loads(line.removeprefix("data: "))
    for line in response.data.decode().strip().split("\n\n")
    if line.startswith("data: ")
]
assert events[-1]["type"] == "complete"
```

---

## Debugging Routes

**Route list:** Flask provides a built-in route listing:
```python
# In Flask shell or dev endpoint
for rule in app.url_map.iter_rules():
    print(f"{rule.methods} {rule.rule} → {rule.endpoint}")
```

**Common issues:**

| Symptom | Cause | Fix |
|---------|-------|-----|
| 404 on valid path | Blueprint not registered | Check `server.py` registration |
| 500 with ImportError | Circular import in route | Use lazy import inside function |
| Empty response | Service returns None | Check service function return value |
| CORS error | Missing headers | Check `after_request` handler in `server.py` |

---

## Migration History

Created 2026-02-28 during the routes refactor.

**Before:**
```
src/ui/web/
├── routes_api.py              (233 lines)
├── routes_audit.py            (1,781 lines)  ← god file, 6 concerns
├── routes_backup.py           (67 lines)     ← imports 4 sub-files
├── routes_backup_archive.py
├── routes_backup_ops.py
├── routes_backup_restore.py
├── routes_backup_tree.py
├── routes_content.py          (250 lines)    ← exports helpers to 3 sub-files
├── routes_content_files.py
├── routes_content_manage.py
├── routes_content_preview.py
├── routes_devops.py           (200 lines)    ← imports 3 sub-files
├── routes_devops_apply.py
├── routes_devops_audit.py
├── routes_devops_detect.py
├── routes_pages.py
├── routes_pages_api.py
├── ... 21 more routes_*.py files
└── 39 files total, all flat in ui/web/
```

- 28 copies of `_project_root()` spread across files
- Security utilities (`_resolve_safe_path`, `_get_enc_key`) defined in a route file
- Auth decorator (`requires_git_auth`) defined in a route file, imported by 3 others
- Cache-bust pattern copy-pasted 8 times in `routes_audit.py`
- `routes_audit.py` at 1,781 lines mixing 6 unrelated concerns

**After:**
```
src/ui/web/
├── helpers.py                 Shared utilities (was scattered across 28 files)
├── server.py                  App factory + blueprint registration
└── routes/
    ├── 28 domain sub-packages  ~8,860 lines total
    │   ├── audit/              7 modules, 1,840 lines (from 1 × 1,781)
    │   ├── content/            5 modules, 864 lines
    │   ├── backup/             5 modules, 495 lines
    │   ├── ... 25 more domains
    │   └── README.md           This file
    └── __init__.py
```

- 0 copies of `_project_root()` — one definition in `helpers.py`
- 0 inter-route imports — all shared logic in `helpers.py`
- 0 copy-pasted cache-bust blocks — one `bust_tool_caches()` call
- 28 self-contained sub-packages with uniform blueprint pattern
- Largest file: 822 lines (down from 1,781), largest non-SSE file: 345 lines
