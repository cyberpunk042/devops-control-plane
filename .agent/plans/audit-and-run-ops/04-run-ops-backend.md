# Phase 4: Run Operations — Backend

> **Status**: Draft  
> **Depends on**: Nothing (parallel with Phase 1-3)

---

## Goal

Create a **scalable, decorator-based Run tracking pattern** at the core services layer so that any integration action — current or future — becomes a tracked Run with minimal boilerplate.

## Design Pattern: `@tracked_run` Decorator

### Problem

There are **60+ POST action routes** across 36 route files. Wiring `record_run()` individually into each one is:
- Not scalable
- Error-prone (miss one, inconsistent)  
- Violates DRY

### Solution: Core-level decorator

A new module `src/core/services/run_tracker.py` provides a decorator and a context manager that any route handler or service function can use:

```python
# src/core/services/run_tracker.py

from contextlib import contextmanager
from functools import wraps
from src.core.services.ledger.models import Run
from src.core.services.ledger.ledger_ops import record_run

@contextmanager
def tracked_run(project_root, run_type, subtype, summary="", **metadata):
    """Context manager for tracking a run operation.
    
    Usage in a route handler:
        with tracked_run(root, "deploy", "deploy:k8s", summary="Apply manifests") as run:
            result = k8s_ops.k8s_apply(root, path, namespace=ns)
            run.summary = result.get("summary", "")
            run.status = "ok" if result.get("ok") else "failed"
            # result is returned normally after the with block
    
    The Run is automatically:
      1. Created with timestamps
      2. Recorded to the ledger on exit
      3. Published via SSE (run:started at __enter__, run:completed at __exit__)
    """

def run_tracked(run_type, subtype, *, summary_fn=None):
    """Decorator for route handlers that should create a Run.
    
    Usage:
        @bp.route("/k8s/apply", methods=["POST"])
        @run_tracked("deploy", "deploy:k8s", summary_fn=lambda r: r.get("summary", ""))
        def k8s_apply():
            ...
            return jsonify(result)
    
    The decorator:
      1. Wraps the route function
      2. Creates a Run with type/subtype
      3. Captures the result dict
      4. Sets status from result (ok/failed based on get("ok") or HTTP status)
      5. Records to ledger
      6. Adds run_id to the response JSON
    """
```

### Why This Pattern

1. **Scalable**: Adding Run tracking to a new route = adding one decorator line
2. **Consistent**: Same Run lifecycle everywhere
3. **Non-breaking**: Existing routes keep working — decorator is additive
4. **Future-proof**: New integrations just use the decorator
5. **Follows existing patterns**: The codebase already uses `devops_cache.get_cached()` as a wrapper pattern for caching. This is the same idea for Run tracking.

## Run Taxonomy

Every Run has `type` (broad) and `subtype` (specific, format `type:detail`):

```python
# src/core/services/run_tracker.py

RUN_TYPES = {
    # ── Lifecycle operations ──
    "install":   "Package/tool installation",
    "build":     "Build artifacts (images, sites, binaries)",
    "deploy":    "Deploy to target (cluster, cloud, pages)",
    "destroy":   "Tear down resources",
    
    # ── Maintenance operations ──
    "setup":     "Initial setup/configuration of an integration",
    "plan":      "Dry-run / preview (terraform plan, helm template)",
    "validate":  "Validation / linting",
    "format":    "Code/config formatting",
    
    # ── Execution operations ──
    "test":      "Test execution",
    "scan":      "Security / audit scans",
    "generate":  "Generate configs, templates, scaffolding",
    
    # ── Data operations ──
    "backup":    "Backup / export",
    "restore":   "Restore / import",
    
    # ── Git operations ──
    "git":       "Git operations (commit, push, pull)",
    "ci":        "CI/CD workflow operations",
}
```

## Full Action Inventory (grouped by integration)

### Kubernetes (`routes_k8s.py`)
| Route | HTTP | Run type:subtype | Summary |
|-------|------|-----------------|---------|
| `/k8s/apply` | POST | `deploy:k8s` | Apply manifests |
| `/k8s/delete` | POST | `destroy:k8s` | Delete resource |
| `/k8s/scale` | POST | `deploy:k8s_scale` | Scale deployment |
| `/k8s/generate/manifests` | POST | `generate:k8s_manifests` | Generate K8s manifests |
| `/k8s/generate/wizard` | POST | `generate:k8s_wizard` | Wizard-generated manifests |
| `/k8s/helm/install` | POST | `install:helm` | Helm chart install |
| `/k8s/helm/upgrade` | POST | `deploy:helm_upgrade` | Helm release upgrade |
| `/k8s/helm/template` | POST | `plan:helm_template` | Helm template render (dry-run) |

### Terraform (`routes_terraform.py`)
| Route | HTTP | Run type:subtype | Summary |
|-------|------|-----------------|---------|
| `/terraform/init` | POST | `setup:terraform` | Terraform init |
| `/terraform/validate` | POST | `validate:terraform` | Terraform validate |
| `/terraform/plan` | POST | `plan:terraform` | Terraform plan |
| `/terraform/apply` | POST | `deploy:terraform` | Terraform apply |
| `/terraform/destroy` | POST | `destroy:terraform` | Terraform destroy |
| `/terraform/generate` | POST | `generate:terraform` | Generate scaffolding |
| `/terraform/workspace/select` | POST | `setup:terraform_ws` | Switch workspace |
| `/terraform/fmt` | POST | `format:terraform` | Format files |

### Docker (`routes_docker.py`)
| Route | HTTP | Run type:subtype | Summary |
|-------|------|-----------------|---------|
| `/docker/build` | POST | `build:docker` | Docker build |
| `/docker/up` | POST | `deploy:docker_up` | Compose up |
| `/docker/down` | POST | `destroy:docker_down` | Compose down |
| `/docker/restart` | POST | `deploy:docker_restart` | Compose restart |
| `/docker/prune` | POST | `destroy:docker_prune` | Docker prune |
| `/docker/pull` | POST | `install:docker_pull` | Pull image |
| `/docker/exec` | POST | `test:docker_exec` | Execute in container |
| `/docker/rm` | POST | `destroy:docker_rm` | Remove container |
| `/docker/rmi` | POST | `destroy:docker_rmi` | Remove image |
| `/docker/generate/dockerfile` | POST | `generate:dockerfile` | Generate Dockerfile |
| `/docker/generate/dockerignore` | POST | `generate:dockerignore` | Generate .dockerignore |
| `/docker/generate/compose` | POST | `generate:compose` | Generate compose file |
| `/docker/generate/compose-wizard` | POST | `generate:compose_wizard` | Wizard compose |
| `/docker/generate/write` | POST | `generate:docker_write` | Write generated file |

### Pages (`routes_pages_api.py`)
| Route | HTTP | Run type:subtype | Summary |
|-------|------|-----------------|---------|
| `/pages/init` | POST | `setup:pages` | Initialize pages |
| `/pages/builders/<name>/install` | POST | `install:pages_builder` | Install builder deps |
| `/pages/build/<name>` | POST | `build:pages_segment` | Build single segment |
| `/pages/build-all` | POST | `build:pages_all` | Build all segments |
| `/pages/merge` | POST | `build:pages_merge` | Merge segments |
| `/pages/deploy` | POST | `deploy:pages` | Deploy to gh-pages |
| `/pages/ci` | POST | `generate:pages_ci` | Generate CI workflow |
| `/pages/build-stream/<name>` | POST | `build:pages_stream` | Build with SSE stream |

### Git / GitHub (`routes_integrations.py`)
| Route | HTTP | Run type:subtype | Summary |
|-------|------|-----------------|---------|
| `/git/commit` | POST | `git:commit` | Git commit |
| `/git/pull` | POST | `git:pull` | Git pull |
| `/git/push` | POST | `git:push` | Git push |
| `/git/remote/add` | POST | `setup:git_remote` | Add remote |
| `/git/remote/remove` | POST | `destroy:git_remote` | Remove remote |
| `/git/remote/rename` | POST | `setup:git_remote_rename` | Rename remote |
| `/git/remote/set-url` | POST | `setup:git_remote_url` | Set remote URL |
| `/gh/actions/dispatch` | POST | `ci:gh_dispatch` | Dispatch workflow |
| `/gh/repo/create` | POST | `setup:gh_repo` | Create repo |
| `/gh/repo/visibility` | POST | `setup:gh_visibility` | Change visibility |
| `/gh/repo/default-branch` | POST | `setup:gh_default_branch` | Set default branch |

### Testing (`routes_testing.py`)
| Route | HTTP | Run type:subtype | Summary |
|-------|------|-----------------|---------|
| `/testing/run` | POST | `test:run` | Execute tests |
| `/testing/coverage` | POST | `test:coverage` | Run coverage |
| `/testing/generate/template` | POST | `generate:test_template` | Generate test template |

### Quality (`routes_quality.py`)
| Route | HTTP | Run type:subtype | Summary |
|-------|------|-----------------|---------|
| `/quality/check` | POST | `validate:quality` | Quality check |
| `/quality/lint` | POST | `validate:lint` | Run linter |
| `/quality/typecheck` | POST | `validate:typecheck` | Type checking |
| `/quality/test` | POST | `test:quality` | Run tests via quality |
| `/quality/format` | POST | `format:quality` | Run formatter |
| `/quality/generate/config` | POST | `generate:quality_config` | Generate tool config |

### Security (`routes_security_scan.py`)
| Route | HTTP | Run type:subtype | Summary |
|-------|------|-----------------|---------|
| `/security/generate/gitignore` | POST | `generate:gitignore` | Generate .gitignore |

### Packages (`routes_packages.py`)
| Route | HTTP | Run type:subtype | Summary |
|-------|------|-----------------|---------|
| `/packages/install` | POST | `install:packages` | Install packages |
| `/packages/update` | POST | `install:packages_update` | Update packages |

### Docs (`routes_docs.py`)
| Route | HTTP | Run type:subtype | Summary |
|-------|------|-----------------|---------|
| `/docs/generate/changelog` | POST | `generate:changelog` | Generate CHANGELOG |
| `/docs/generate/readme` | POST | `generate:readme` | Generate README |

### Vault (`routes_vault.py`)
| Route | HTTP | Run type:subtype | Summary |
|-------|------|-----------------|---------|
| `/vault/create` | POST | `setup:vault` | Create vault |
| `/vault/lock` | POST | `setup:vault_lock` | Lock vault |
| `/vault/unlock` | POST | `setup:vault_unlock` | Unlock vault |
| `/vault/register` | POST | `setup:vault_register` | Register vault |
| `/vault/add-keys` | POST | `setup:vault_keys` | Add keys |
| `/vault/import` | POST | `restore:vault` | Import vault |
| `/vault/export` | POST | `backup:vault` | Export vault |

### Backup (`routes_backup_*.py`)
| Route | HTTP | Run type:subtype | Summary |
|-------|------|-----------------|---------|
| `/backup/restore` | POST | `restore:backup` | Restore backup |
| `/backup/import` | POST | `restore:import` | Import backup |
| `/backup/wipe` | POST | `destroy:backup_wipe` | Wipe data |
| `/backup/delete` | POST | `destroy:backup_delete` | Delete backup |

### Infra (`routes_infra.py`)
| Route | HTTP | Run type:subtype | Summary |
|-------|------|-----------------|---------|
| `/infra/env/generate-example` | POST | `generate:env_example` | Generate .env.example |
| `/infra/env/generate-env` | POST | `generate:env` | Generate .env |

### Audit (`routes_audit.py`)
| Route | HTTP | Run type:subtype | Summary |
|-------|------|-----------------|---------|
| `/audit/install-tool` | POST | `install:tool` | Install DevOps tool |

### Content (`routes_content*.py`)
| Route | HTTP | Run type:subtype | Summary |
|-------|------|-----------------|---------|
| `/content/encrypt` | POST | `setup:encrypt` | Encrypt content |
| `/content/decrypt` | POST | `setup:decrypt` | Decrypt content |

**Total: ~70 POST action routes** across all integrations.

## Implementation

### Step 1: Create `src/core/services/run_tracker.py`

```python
"""
Run tracking — decorator + context manager for wrapping any action as a Run.

Provides two patterns:
  1. @run_tracked("type", "type:subtype") — decorator for route handlers
  2. with tracked_run(root, "type", "type:subtype") as run: — context manager

Both ensure:
  - A Run model is created
  - SSE event emitted at start and end
  - Run is recorded to the ledger branch
  - run_id is available for referencing
"""

from __future__ import annotations

import time
import logging
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from src.core.services.ledger.models import Run

logger = logging.getLogger(__name__)


@contextmanager
def tracked_run(
    project_root: Path,
    run_type: str,
    subtype: str,
    *,
    summary: str = "",
    **metadata: Any,
):
    """Context manager — creates, tracks, and records a Run."""
    run = Run(
        type=run_type,
        subtype=subtype,
        summary=summary,
        metadata=metadata,
    )
    run.ensure_id()
    t0 = time.time()
    
    # Emit start event
    _publish("run:started", run)
    
    try:
        yield run
    except Exception as exc:
        run.status = "failed"
        run.summary = run.summary or str(exc)
        raise
    finally:
        run.duration_ms = int((time.time() - t0) * 1000)
        run.ended_at = _now_iso()
        
        # Record to ledger
        try:
            from src.core.services.ledger.ledger_ops import record_run
            record_run(project_root, run)
        except Exception as e:
            logger.warning("Failed to record run %s: %s", run.run_id, e)
        
        # Emit completed event
        _publish("run:completed", run)


def run_tracked(
    run_type: str,
    subtype: str,
    *,
    summary_key: str = "summary",
    ok_key: str = "ok",
):
    """Decorator for Flask route handlers.
    
    Assumes the wrapped function returns jsonify(result_dict).
    Injects run_id into the result dict.
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from flask import current_app
            project_root = Path(current_app.config["PROJECT_ROOT"])
            
            with tracked_run(project_root, run_type, subtype) as run:
                response = fn(*args, **kwargs)
                
                # Extract result from Flask response to set Run metadata
                # (response may be a tuple of (response, status_code))
                # ... inspect + set run.status, run.summary ...
                
                return response
        return wrapper
    return decorator
```

### Step 2: Wire progressively

Start with one integration (e.g. K8s), validate the pattern works, then roll out across all others. Each route file change is **one line per route**:

```python
# Before:
@k8s_bp.route("/k8s/apply", methods=["POST"])
def k8s_apply():
    ...

# After:
@k8s_bp.route("/k8s/apply", methods=["POST"])
@run_tracked("deploy", "deploy:k8s")
def k8s_apply():
    ...
```

### Step 3: SSE events

Add `'run:started'` and `'run:completed'` to the frontend `_eventTypes` in `_event_stream.html`.

### Step 4: API for listing runs

```python
# In routes_runs.py or existing routes
GET /api/runs/recent         — list recent runs (last 50)
GET /api/runs/<run_id>       — get run detail + events
```

## File Checklist

| File | Action | Lines est. |
|------|--------|-----------|
| `src/core/services/run_tracker.py` | **CREATE** — decorator + context manager + SSE helpers | ~120 |
| `src/ui/web/routes_k8s.py` | MODIFY — add `@run_tracked` to 8 POST routes | ~8 |
| `src/ui/web/routes_terraform.py` | MODIFY — 8 routes | ~8 |
| `src/ui/web/routes_docker.py` | MODIFY — 14 routes | ~14 |
| `src/ui/web/routes_pages_api.py` | MODIFY — 8 routes | ~8 |
| `src/ui/web/routes_integrations.py` | MODIFY — 11 routes | ~11 |
| `src/ui/web/routes_testing.py` | MODIFY — 3 routes | ~3 |
| `src/ui/web/routes_quality.py` | MODIFY — 6 routes | ~6 |
| `src/ui/web/routes_packages.py` | MODIFY — 2 routes | ~2 |
| `src/ui/web/routes_docs.py` | MODIFY — 2 routes | ~2 |
| `src/ui/web/routes_vault.py` | MODIFY — 7 routes | ~7 |
| `src/ui/web/routes_backup_*.py` | MODIFY — 4 routes | ~4 |
| `src/ui/web/routes_infra.py` | MODIFY — 2 routes | ~2 |
| `src/ui/web/routes_audit.py` | MODIFY — 1 route | ~1 |
| `src/ui/web/routes_security_scan.py` | MODIFY — 1 route | ~1 |
| `src/ui/web/routes_content*.py` | MODIFY — 2 routes | ~2 |
| `_event_stream.html` | ADD 2 event types + handlers | ~15 |

## Rollout Order

1. Create `run_tracker.py` core module
2. Wire into K8s routes (most complex, best test case)
3. Validate: trigger k8s/apply → confirm Run appears in ledger + SSE fires
4. Roll out to Terraform, Docker, Pages
5. Roll out to Git/GitHub, Testing, Quality
6. Roll out to remaining (Packages, Docs, Vault, Backup, Infra, Audit, Security, Content)

## Test Criteria

1. `POST /k8s/apply` → Run recorded in `.scp-ledger/ledger/runs/` with git tag
2. SSE `run:started` and `run:completed` events fire
3. `GET /api/runs/recent` returns the run
4. `@run:` autocomplete in chat shows the run
5. Decorator is additive — no change to existing route behavior
6. Failed operations still create a Run with `status: "failed"`
