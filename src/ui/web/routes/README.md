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

Five domain sub-packages for related features that were already multi-file.
Twenty-three standalone modules for self-contained domains.

```
routes/
│
├── audit/                      42 routes — Tool provisioning + system analysis
│   ├── __init__.py             Blueprint (audit_bp, url_prefix="/api")
│   ├── analysis.py             L0/L1/L2 audit data — profiles, deps, structure, scores
│   ├── staging.py              Snapshot lifecycle — pending, save, discard, delete
│   ├── tool_install.py         Install, resolve, check, version, update, remove
│   ├── tool_execution.py       SSE plan execution, resume, cancel, archive
│   ├── deep_detection.py       Hardware/GPU/kernel/network detection (on-demand)
│   └── offline_cache.py        Offline install cache, data packs, service status
│
├── content/                    20 routes — Encrypted content vault
│   ├── __init__.py             Blueprint (content_bp) + core listing/crypto
│   ├── files.py                Create, delete, download, upload
│   ├── manage.py               Setup key, save, rename, move, release
│   └── preview.py              Preview plain text, encrypted, save edited
│
├── backup/                     16 routes — Backup & restore
│   ├── __init__.py             Blueprint (backup_bp) + folder listing
│   ├── archive.py              Export, list, preview, download, upload
│   ├── ops.py                  Encrypt, decrypt, upload-release, rename
│   ├── restore.py              Restore, import, wipe, delete
│   └── tree.py                 Expandable file tree for selection UI
│
├── devops/                      8 routes — DevOps dashboard control
│   ├── __init__.py             Blueprint (devops_bp) + card prefs + cache bust
│   ├── apply.py                Wizard setup actions (Docker, K8s, Terraform…)
│   ├── audit.py                Audit finding dismissals
│   └── detect.py               Wizard environment detection
│
├── pages/                      24 routes — Documentation site management
│   ├── __init__.py             Re-exports pages_bp + pages_api_bp
│   ├── serving.py              Dashboard HTML + built site static serving
│   └── api.py                  Pages API — segments, build, deploy, status
│
├── api.py                       8  Core API — status, health, project config
├── chat.py                     12  Chat sync — messages, references, threads
├── ci.py                        5  CI pipeline — status, badges, workflows
├── config.py                    3  Project configuration CRUD
├── dev.py                       3  Developer/debug endpoints
├── dns.py                       4  DNS/CDN — zone status, record generation
├── docker.py                   24  Docker — status, compose, containers, logs
├── docs.py                      5  Documentation generation triggers
├── events.py                    1  SSE event stream (server → browser push)
├── git_auth.py                  4  SSH key auth — check, unlock, status
├── infra.py                    10  Infrastructure status overview
├── integrations.py             27  GitHub integration — repos, branches, PRs
├── k8s.py                      24  Kubernetes — config, status, namespaces
├── metrics.py                   2  Project metrics (LOC, complexity, deps)
├── packages.py                  6  Package management — status, outdated
├── project.py                   2  Project metadata CRUD
├── quality.py                   7  Code quality scans — lint, complexity
├── secrets.py                  11  Secrets management — env vars, .env files
├── security_scan.py             7  Security scanning — secrets, dependencies
├── terraform.py                12  Terraform — state, plan, apply, import
├── testing.py                   5  Test runner — execute, coverage, history
├── trace.py                    10  Execution trace — replay, timeline, export
└── vault.py                    21  Vault — lock, unlock, encrypt, decrypt
```

---

## Why Sub-Packages vs Flat Files

The sub-package boundary is NOT arbitrary. A domain becomes a sub-package
when it has **multiple modules that share a single Blueprint**:

```
content_bp is defined in content/__init__.py
    ├── files.py registers 7 routes on content_bp
    ├── manage.py registers 10 routes on content_bp
    └── preview.py registers 3 routes on content_bp
```

This is the exact same structural pattern used by the original codebase
(`routes_content.py` + `routes_content_files.py` + ...), just with
proper package boundaries instead of underscore-concatenated filenames.

Standalone files (like `docker.py` with 24 routes, or `k8s.py` with 24)
stay flat because they're self-contained — one module, one blueprint,
no sub-file dependencies.

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

Standalone files without sub-modules stay flat — no artificial nesting.

### Why not group docker + k8s + terraform into an "infra/" sub-package?

Because they don't share a blueprint. Each has its own blueprint registered
independently. Grouping them would be **organizational** (for humans) but
would add an import indirection layer with no structural benefit. If they
grow sub-modules in the future, they become sub-packages then — not before.

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
    ├── audit/                 7 modules, 1,840 lines (from 1 × 1,781)
    ├── backup/                5 modules, 495 lines
    ├── content/               4 modules, 851 lines
    ├── devops/                4 modules, 459 lines
    ├── pages/                 3 modules, 430 lines
    └── 23 standalone modules  ~4,600 lines
```

- 0 copies of `_project_root()` — one definition in `helpers.py`
- 0 inter-route imports — all shared logic in `helpers.py`
- 0 copy-pasted cache-bust blocks — one `bust_tool_caches()` call
- Largest file: 822 lines (down from 1,781), largest non-SSE file: 555 lines
