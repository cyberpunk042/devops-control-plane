# Project Routes — Unified Integration Status & Onboarding API

> **1 file · 67 lines · 2 endpoints · Blueprint: `project_bp` · Prefix: `/api`**
>
> Two high-level endpoints that aggregate the setup status of
> **all integrations** into a unified progress picture:
>
> 1. **Status** — runs all 9 integration probes (project, git, github,
>    docker, ci, k8s, terraform, pages, dns) and returns a complete
>    readiness map with progress percentage and a suggested next step
> 2. **Next** — same probes, but returns only the suggested next
>    integration to configure, optimized for onboarding prompts
>
> Backed by `core/services/project_probes.py` (486 lines) —
> the "connected journey" intelligence layer.

---

## How It Works

### Integration Status Pipeline (Cached)

```
GET /api/project/status?bust=1
     │
     ▼
devops_cache.get_cached(root, "project-status", _compute)
     │
     ├── Cache HIT → return cached status
     └── Cache MISS → _compute()
         │
         ├── run_all_probes(root)
         │   ├── probe_project(root)  — project.yml exists? configured?
         │   ├── probe_git(root)      — git repo? remote? clean?
         │   ├── probe_github(root)   — gh CLI? repo linked? auth?
         │   ├── probe_docker(root)   — Dockerfile? compose? daemon?
         │   ├── probe_cicd(root)     — CI workflows? valid?
         │   ├── probe_k8s(root)      — manifests? kubectl? cluster?
         │   ├── probe_terraform(root)— tf files? state? CLI?
         │   ├── probe_pages(root)    — segments? built? builder?
         │   └── probe_dns(root)      — zone files? CNAME? CDN?
         │
         │   Each probe returns:
         │   {
         │       status: "configured" | "partial" | "not_configured" | "unavailable",
         │       details: { ...probe-specific data... },
         │       suggestions: ["Install Docker", ...]
         │   }
         │
         ├── suggest_next(statuses)
         │   ├── Load integration dependency graph from DataRegistry
         │   ├── Walk graph topologically
         │   └── Return first not-configured integration whose
         │       dependencies are all configured
         │       e.g. "docker" (because "git" and "project" are done)
         │
         ├── compute_progress(statuses)
         │   ├── Count configured + partial integrations
         │   └── Return: { configured: 6, total: 9, percent: 67 }
         │
         └── Return:
             {
                 integrations: { project: {...}, git: {...}, ... },
                 suggested_next: "docker",
                 progress: { configured: 6, total: 9, percent: 67 }
             }
```

### Next Suggestion Pipeline (Cached, Same Key)

```
GET /api/project/next?bust=1
     │
     ▼
devops_cache.get_cached(root, "project-status", _compute)
     │
     ├── Uses the SAME cache key as /project/status
     │   (first caller populates, second is free)
     │
     └── _compute():
         ├── run_all_probes(root)
         ├── suggest_next(statuses) → "docker"
         ├── statuses.get("docker") → { status, details, suggestions }
         └── compute_progress(statuses) → { percent: 67 }
         │
         └── Return:
             {
                 suggested_next: "docker",
                 status: { ...docker probe result... },
                 progress: { configured: 6, total: 9, percent: 67 }
             }
```

---

## File Map

```
routes/project/
├── __init__.py     67 lines — blueprint + 2 endpoints (all in one file)
└── README.md                — this file
```

Core business logic: `core/services/project_probes.py` (486 lines).

---

## Per-File Documentation

### `__init__.py` — Blueprint + Endpoints (67 lines)

| Function | Method | Route | Cached | What It Does |
|----------|--------|-------|--------|-------------|
| `project_status()` | GET | `/project/status` | ✅ `"project-status"` | Full integration status map |
| `project_next()` | GET | `/project/next` | ✅ `"project-status"` | Next suggested integration |

**Both endpoints share the same cache key:**

```python
# /project/status
return jsonify(get_cached(root, "project-status", _compute, force=force))

# /project/next
return jsonify(get_cached(root, "project-status", _compute, force=force))
```

This means whichever endpoint is called first populates the cache,
and the second call returns instantly. The compute functions differ
only in what they extract from the probe results.

**Custom `_root()` helper** — unlike most routes that use
`from helpers import project_root`, this module defines its own
root accessor:

```python
def _root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])
```

**Eager imports** — unlike most route files that lazy-import caching,
this module imports `get_cached` and probe functions at module level:

```python
from src.core.services.devops.cache import get_cached
from src.core.services.project_probes import (
    compute_progress,
    run_all_probes,
    suggest_next,
)
```

---

## Dependency Graph

```
__init__.py
├── project_probes   ← run_all_probes, suggest_next, compute_progress (eager)
├── devops.cache     ← get_cached (eager)
└── flask            ← current_app.config (for PROJECT_ROOT)
```

**The probe service itself touches many other services:**

```
project_probes.py
├── probe_project → reads project.yml directly
├── probe_git     → shells out to git (status, remote, branch)
├── probe_github  → shells out to gh (auth status, repo view)
├── probe_docker  → shutil.which + docker info subprocess
├── probe_cicd    → file-system scan (.github/workflows/)
├── probe_k8s     → file-system scan (k8s/*, Helm charts)
│                   + shutil.which(kubectl, helm)
├── probe_terraform → file-system scan (*.tf)
│                     + shutil.which(terraform)
├── probe_pages   → reads project.yml pages section
└── probe_dns     → file-system scan (dns/, cdn/, CNAME)
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `project_bp`, registers at `/api` |
| Dashboard | `scripts/_dashboard.html` | `/project/status` (overall progress bar) |
| Boot | `scripts/_boot.html` | `/project/status` (initial state detection) |
| Integrations | `scripts/integrations/_init.html` | `/project/status` (integration panel) |
| Audit modals | `scripts/audit/_modals.html` | `/project/status` (audit context) |

---

## Data Shapes

### `GET /api/project/status` response

```json
{
    "integrations": {
        "project": {
            "status": "configured",
            "details": {
                "has_project_yml": true,
                "name": "devops-control-plane"
            },
            "suggestions": []
        },
        "git": {
            "status": "configured",
            "details": {
                "has_repo": true,
                "branch": "main",
                "remote": "origin",
                "clean": true
            },
            "suggestions": []
        },
        "github": {
            "status": "configured",
            "details": {
                "cli_available": true,
                "authenticated": true,
                "repo_linked": true
            },
            "suggestions": []
        },
        "docker": {
            "status": "partial",
            "details": {
                "dockerfile": true,
                "compose": true,
                "daemon_running": false
            },
            "suggestions": ["Start Docker daemon"]
        },
        "cicd": {
            "status": "configured",
            "details": {
                "has_workflows": true,
                "workflow_count": 3
            },
            "suggestions": []
        },
        "k8s": {
            "status": "not_configured",
            "details": {
                "manifests_found": false,
                "kubectl_available": false
            },
            "suggestions": ["Install kubectl", "Create K8s manifests"]
        },
        "terraform": {
            "status": "unavailable",
            "details": {
                "tf_files": false,
                "cli_available": false
            },
            "suggestions": ["Install Terraform"]
        },
        "pages": {
            "status": "configured",
            "details": {
                "segments": 2,
                "built": true
            },
            "suggestions": []
        },
        "dns": {
            "status": "not_configured",
            "details": {
                "zone_files": false,
                "cname": false,
                "domain": null
            },
            "suggestions": ["Add DNS configuration"]
        }
    },
    "suggested_next": "k8s",
    "progress": {
        "configured": 5,
        "total": 9,
        "percent": 56
    }
}
```

### `GET /api/project/next` response

```json
{
    "suggested_next": "k8s",
    "status": {
        "status": "not_configured",
        "details": {
            "manifests_found": false,
            "kubectl_available": false
        },
        "suggestions": ["Install kubectl", "Create K8s manifests"]
    },
    "progress": {
        "configured": 5,
        "total": 9,
        "percent": 56
    }
}
```

---

## Advanced Feature Showcase

### 1. Dependency-Aware "Next" Suggestion

The integration graph defines prerequisites. `suggest_next()` walks
the graph topologically and only suggests integrations whose
dependencies are already configured:

```
project → git → github → ci
                       → docker → k8s
                       → pages
                       → dns
                       → terraform
```

If git and github are configured but docker is not, the engine
suggests "docker" — not "k8s" (which depends on docker).

### 2. Shared Cache Key Between Endpoints

Both `/project/status` and `/project/next` use cache key
`"project-status"`. The compute function runs all 9 probes. The
first endpoint to be called populates the cache; the second is free.

### 3. Four-Level Status Classification

Each probe categorizes into exactly one of four statuses:
- **`configured`** — fully set up and functional
- **`partial`** — partially configured (e.g. Dockerfile exists but
  daemon not running)
- **`not_configured`** — not set up at all
- **`unavailable`** — tool not installed on the system

### 4. Progress Percentage

`compute_progress()` counts `configured` and `partial` integrations
against the total, producing a percentage used for the dashboard
progress bar.

---

## Design Decisions

### Why probes run on every call (within cache TTL)

There's no differential approach — all 9 probes run together
because they're fast (filesystem checks + `shutil.which`). The
cache prevents redundant execution within the TTL window.

### Why this module uses eager imports

Unlike most routes that lazy-import caching inside handlers, this
module imports everything at the top. The justification: these
are the two most-called endpoints (dashboard loads them on boot),
so import speed matters.

### Why /project/next exists separately from /project/status

The dashboard progress bar uses `/project/status` (needs full map).
The onboarding prompt uses `/project/next` (needs only one item).
Having a dedicated endpoint keeps the onboarding UI simple — just
read `.suggested_next` and `.status`.

---

## Coverage Summary

| Capability | Endpoint | Method | Tracked | Cached |
|-----------|----------|--------|---------|--------|
| Integration status | `/project/status` | GET | No | ✅ `"project-status"` |
| Next suggestion | `/project/next` | GET | No | ✅ `"project-status"` |
