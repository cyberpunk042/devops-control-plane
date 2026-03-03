# Packages Routes — Dependency Detection, Audit & Management API

> **3 files · 119 lines · 6 endpoints · Blueprint: `packages_bp` · Prefix: `/api`**
>
> Two sub-domains under a single blueprint:
>
> 1. **Status (read-only)** — detect package managers, check outdated
>    packages, run security audits, list installed packages (4 endpoints)
> 2. **Actions (mutations)** — install dependencies, update packages
>    (2 endpoints)
>
> All delegate to `core/services/packages_svc/` — a 2-module package:
> - `ops.py` (275 lines) — detection, status, enriched status
> - `actions.py` (509 lines) — outdated, audit, list, install, update
>
> Supports 9 package managers: pip, npm, Go modules, Cargo, Composer,
> Maven, Gradle, .NET (NuGet), Mix (Hex), and Bundler.

---

## How It Works

### Package Status Pipeline (Cached)

```
GET /api/packages/status?bust=1
     │
     ▼
devops_cache.get_cached(root, "packages", lambda: package_ops.package_status_enriched(root))
     │
     ├── Cache HIT → return cached status
     └── Cache MISS → package_status_enriched(root)
         │
         ├── 1. package_status(root):
         │   For each of the 9 _PACKAGE_MANAGERS:
         │   ├── Check dependency files exist (e.g. requirements.txt, package.json)
         │   ├── Check lock files exist (e.g. requirements.lock, package-lock.json)
         │   ├── Check CLI available (shutil.which)
         │   └── Collect: { id, name, cli, cli_available, dependency_files, lock_files }
         │
         ├── 2. For each detected manager with CLI:
         │   └── package_list(root, manager=id) → installed packages
         │
         └── Return:
             {
                 managers: [{id, name, cli, cli_available, dependency_files, lock_files}],
                 total_managers,
                 has_packages,
                 installed_packages: { pip: [...], npm: [...] },
                 total_installed
             }
```

### Outdated Check Pipeline

```
GET /api/packages/outdated?manager=pip
     │
     ▼
package_ops.package_outdated(root, manager="pip")
     │
     ├── manager specified? Use it
     │   manager=None? Auto-detect primary: _resolve_manager(root)
     │
     ├── Dispatch to manager-specific function:
     │   ├── pip  → _pip_outdated(root)
     │   │   └── sys.executable -m pip list --outdated --format=json
     │   │       → parse [{name, version, latest_version, latest_filetype}]
     │   │
     │   ├── npm  → _npm_outdated(root)
     │   │   └── npm outdated --json
     │   │       → parse {package: {current, wanted, latest}}
     │   │
     │   ├── go   → _go_outdated(root)
     │   │   └── go list -m -u -json all
     │   │       → filter modules with Update field
     │   │
     │   └── cargo → _cargo_outdated(root)
     │       └── cargo outdated --format=json
     │           → parse outdated list
     │
     └── Return:
         { ok: true, manager: "pip", outdated: [{name, version, latest_version}] }
```

### Security Audit Pipeline

```
GET /api/packages/audit?manager=pip
     │
     ▼
package_ops.package_audit(root, manager="pip")
     │
     ├── Dispatch to manager-specific audit:
     │   ├── pip  → _pip_audit(root)
     │   │   └── pip-audit --format=json
     │   │       → count vulnerabilities
     │   │
     │   ├── npm  → _npm_audit(root)
     │   │   └── npm audit --json
     │   │       → parse vulnerability count
     │   │
     │   └── cargo → _cargo_audit(root)
     │       └── cargo audit --json
     │           → count vulnerabilities
     │
     └── Return:
         { ok: true, manager: "pip", vulnerabilities: 3, output: "..." }
```

### Install / Update Pipeline

```
POST /api/packages/install  { manager: "pip" }
     │
     ├── @run_tracked("install", "install:packages")
     │
     ▼
package_ops.package_install(root, manager="pip")
     │
     ├── pip  → sys.executable -m pip install -r requirements.txt
     ├── npm  → npm install
     ├── go   → go mod download
     └── cargo → cargo build
     │
     └── Return: { ok: true, output: "..." }

POST /api/packages/update  { manager: "pip", package: "requests" }
     │
     ├── @run_tracked("install", "install:packages_update")
     │
     ▼
package_ops.package_update(root, package="requests", manager="pip")
     │
     ├── package specified?
     │   ├── YES (pip) → pip install --upgrade requests
     │   └── NO  (pip) → pip install --upgrade -r requirements.txt
     │
     └── Return: { ok: true, output: "..." }
```

---

## File Map

```
routes/packages/
├── __init__.py     18 lines — blueprint definition + 2 sub-module imports
├── status.py       57 lines — 4 read-only endpoints
├── actions.py      44 lines — 2 mutation endpoints
└── README.md                — this file
```

Core business logic:
- `packages_svc/ops.py` (275 lines) — detection, status, enriched status
- `packages_svc/actions.py` (509 lines) — outdated, audit, list, install, update

---

## Per-File Documentation

### `__init__.py` — Blueprint Definition (18 lines)

```python
packages_bp = Blueprint("packages", __name__)

from . import status, actions  # register routes
```

### `status.py` — Read-Only Endpoints (57 lines)

| Function | Method | Route | Cached | What It Does |
|----------|--------|-------|--------|-------------|
| `package_status()` | GET | `/packages/status` | ✅ `"packages"` | Detect managers + installed |
| `package_outdated()` | GET | `/packages/outdated` | No | Check outdated packages |
| `package_audit()` | GET | `/packages/audit` | No | Security vulnerability scan |
| `package_list()` | GET | `/packages/list` | No | List installed packages |

**All three non-cached endpoints accept an optional `?manager=`
parameter.** When omitted, the core service auto-detects the
primary package manager via `_resolve_manager()`.

### `actions.py` — Mutation Endpoints (44 lines)

| Function | Method | Route | Tracked | What It Does |
|----------|--------|-------|---------|-------------|
| `package_install()` | POST | `/packages/install` | ✅ `install:packages` | Install dependencies |
| `package_update()` | POST | `/packages/update` | ✅ `install:packages_update` | Update packages |

**Update supports per-package targeting:**

```python
data = request.get_json(silent=True) or {}
manager = data.get("manager")
package = data.get("package")  # optional: specific package to update

result = package_ops.package_update(root, package=package, manager=manager)
```

---

## Dependency Graph

```
__init__.py
└── Imports: status, actions

status.py
├── packages_svc.ops ← package_status_enriched, package_outdated,
│                      package_audit, package_list (eager)
├── devops.cache     ← get_cached (lazy, inside handler)
└── helpers          ← project_root (eager)

actions.py
├── packages_svc.ops ← package_install, package_update (eager, re-exported from actions)
├── run_tracker      ← @run_tracked (eager)
└── helpers          ← project_root (eager)
```

**Supported package managers (9 total):**

```
_PACKAGE_MANAGERS registry:
├── pip       — Python (requirements.txt, pyproject.toml, Pipfile)
├── npm       — Node.js (package.json)
├── go        — Go (go.mod)
├── cargo     — Rust (Cargo.toml)
├── composer  — PHP (composer.json)
├── maven     — Java (pom.xml)
├── gradle    — Java (build.gradle)
├── dotnet    — .NET (*.csproj, *.fsproj)
├── mix       — Elixir (mix.exs)
└── bundler   — Ruby (Gemfile)
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `packages_bp`, registers at `/api` |
| DevOps card | `scripts/devops/_packages.html` | `/packages/status` (cached) |
| Health probe | `metrics/ops._probe_packages` | `packages` cache key |

---

## Data Shapes

### `GET /api/packages/status` response

```json
{
    "managers": [
        {
            "id": "pip",
            "name": "pip",
            "cli": "pip",
            "cli_available": true,
            "dependency_files": ["requirements.txt", "pyproject.toml"],
            "lock_files": []
        },
        {
            "id": "npm",
            "name": "npm",
            "cli": "npm",
            "cli_available": true,
            "dependency_files": ["package.json"],
            "lock_files": ["package-lock.json"]
        }
    ],
    "total_managers": 2,
    "has_packages": true,
    "installed_packages": {
        "pip": [
            { "name": "flask", "version": "3.1.0" },
            { "name": "requests", "version": "2.31.0" }
        ],
        "npm": [
            { "name": "esbuild", "version": "0.19.0" }
        ]
    },
    "total_installed": 3
}
```

### `GET /api/packages/outdated?manager=pip` response

```json
{
    "ok": true,
    "manager": "pip",
    "outdated": [
        { "name": "requests", "version": "2.31.0", "latest_version": "2.32.0" },
        { "name": "flask", "version": "3.0.0", "latest_version": "3.1.0" }
    ]
}
```

### `GET /api/packages/audit?manager=npm` response

```json
{
    "ok": true,
    "manager": "npm",
    "vulnerabilities": 2,
    "output": "2 vulnerabilities found\n\n  high: prototype-pollution in lodash"
}
```

### `GET /api/packages/list?manager=pip` response

```json
{
    "ok": true,
    "manager": "pip",
    "packages": [
        { "name": "flask", "version": "3.1.0" },
        { "name": "requests", "version": "2.31.0" }
    ]
}
```

### `POST /api/packages/install` request + response

```json
// Request:
{ "manager": "pip" }

// Response:
{ "ok": true, "output": "Successfully installed flask-3.1.0 requests-2.31.0" }
```

### `POST /api/packages/update` request + response

```json
// Request:
{ "manager": "pip", "package": "requests" }

// Response:
{ "ok": true, "output": "Successfully installed requests-2.32.0" }
```

---

## Advanced Feature Showcase

### 1. Auto-Detect Primary Package Manager

When no `manager` parameter is provided, the core service
auto-detects the primary manager by scanning for dependency files:

```python
def _resolve_manager(project_root):
    detected = _detect_pm_for_dir(project_root)
    return detected[0]["id"] if detected else None
```

### 2. sys.executable for pip

Pip commands use `sys.executable -m pip` instead of bare `pip`
to ensure the correct Python environment is used:

```python
def _pip_cmd(*args):
    return [sys.executable, "-m", "pip"] + list(args)
```

### 3. Enriched Status with Package Lists

The cached `/packages/status` endpoint returns not just detected
managers but also installed package lists. This means a single
cached call gives the dashboard everything it needs:

```python
def package_status_enriched(project_root):
    result = package_status(project_root)
    installed = {}
    for mgr in result["managers"]:
        if mgr["cli_available"]:
            pkg_result = package_list(project_root, manager=mgr["id"])
            if pkg_result.get("ok"):
                installed[mgr["id"]] = pkg_result["packages"]
    result["installed_packages"] = installed
    result["total_installed"] = sum(len(v) for v in installed.values())
    return result
```

### 4. Per-Package Updates

Update can target a specific package or update everything:

```python
# Update all:
{ "manager": "pip" }
→ pip install --upgrade -r requirements.txt

# Update one:
{ "manager": "pip", "package": "requests" }
→ pip install --upgrade requests
```

---

## Design Decisions

### Why outdated/audit/list are not cached

These operations call external package managers (pip, npm, etc.)
that check live state. Caching would hide newly outdated packages
or resolved vulnerabilities. Only `status` (file detection) is
cached because it's fast and stable.

### Why both tracked actions use "install" category

Both install and update are tracked under `install:*` because
they modify the dependency tree. There's no `update` tracker
category — updates are semantically a subset of installation.

### Why the route passes manager=None to the core service

The route layer doesn't try to detect the manager — it passes
the `?manager=` param (or None) straight through and lets the
core service auto-detect. This keeps the route thin and the
detection logic centralized.

---

## Coverage Summary

| Capability | Endpoint | Method | Tracked | Cached |
|-----------|----------|--------|---------|--------|
| Package status | `/packages/status` | GET | No | ✅ `"packages"` |
| Outdated check | `/packages/outdated` | GET | No | No |
| Security audit | `/packages/audit` | GET | No | No |
| Package list | `/packages/list` | GET | No | No |
| Install deps | `/packages/install` | POST | ✅ `install:packages` | No |
| Update packages | `/packages/update` | POST | ✅ `install:packages_update` | No |
