# Routes Refactor Plan

> Move 39 flat `routes_*.py` files from `src/ui/web/` into `src/ui/web/routes/`
> sub-package. Then split the oversized `routes_audit.py` (1,781 lines).

**Covers progress tracker items:** #8, #9, #10

---

## Current State

### Inventory (39 files, 8,765 total lines)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Defines Own Blueprint (27 files)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 1,781  routes_audit.py           audit_bp         ⚠️ needs split
   557  routes_chat.py            chat_bp
   520  routes_integrations.py    integrations_bp  ⚡ borderline
   419  routes_vault.py           vault_bp
   412  routes_docker.py          docker_bp
   350  routes_k8s.py             k8s_bp
   346  routes_pages_api.py       pages_api_bp
   335  routes_trace.py           trace_bp
   269  routes_content.py         content_bp       ← parent for 3 sub-files
   267  routes_chat.py            chat_bp
   234  routes_api.py             api_bp
   228  routes_secrets.py         secrets_bp
   200  routes_devops.py          devops_bp        ← parent for 3 sub-files
   190  routes_content_manage.py  (no bp)
   175  routes_terraform.py       terraform_bp
   166  routes_security_scan.py   security_bp2
   160  routes_git_auth.py        git_auth_bp      ← exports requires_git_auth
   142  routes_infra.py           infra_bp
   140  routes_quality.py         quality_bp
   127  routes_backup.py          backup_bp        ← parent for 4 sub-files
   120  routes_packages.py        packages_bp
   120  routes_metrics.py         metrics_bp
    95  routes_testing.py         testing_bp
    88  routes_ci.py              ci_bp
    86  routes_dev.py             dev_bp
    84  routes_config.py          config_bp
    79  routes_dns.py             dns_bp
    77  routes_docs.py            docs_bp
    73  routes_pages.py           pages_bp
    71  routes_devops_audit.py    (no bp)
    69  routes_events.py          events_bp
    67  routes_project.py         project_bp
    48  routes_backup_tree.py     (no bp)
    46  routes_devops_detect.py   (no bp)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Extends Parent Blueprint (12 files — NO own Blueprint)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 routes_backup_archive.py   → from .routes_backup import backup_bp
 routes_backup_ops.py       → from .routes_backup import backup_bp
 routes_backup_restore.py   → from .routes_backup import backup_bp
 routes_backup_tree.py      → from .routes_backup import backup_bp
 routes_content_files.py    → from .routes_content import content_bp
 routes_content_manage.py   → from .routes_content import content_bp
 routes_content_preview.py  → from .routes_content import content_bp
 routes_devops_apply.py     → from src.ui.web.routes_devops import devops_bp
 routes_devops_audit.py     → from src.ui.web.routes_devops import devops_bp
 routes_devops_detect.py    → from src.ui.web.routes_devops import devops_bp
```

### Cross-File Dependencies

| File | Imports from | Symbol | Import Style |
|------|-------------|--------|-------------|
| `routes_backup_archive.py` | `routes_backup.py` | `backup_bp`, `_project_root` | relative (`from .routes_backup`) |
| `routes_backup_ops.py` | `routes_backup.py` | `backup_bp`, `_project_root` | relative |
| `routes_backup_restore.py` | `routes_backup.py` | `backup_bp`, `_project_root` | relative |
| `routes_backup_tree.py` | `routes_backup.py` | `backup_bp`, `_project_root` | relative |
| `routes_content_files.py` | `routes_content.py` | `content_bp`, `_project_root`, `_resolve_safe_path`, `_get_enc_key` | relative |
| `routes_content_manage.py` | `routes_content.py` | `content_bp`, `_project_root`, `_resolve_safe_path` | relative |
| `routes_content_preview.py` | `routes_content.py` | `content_bp`, `_project_root`, `_resolve_safe_path`, `_get_enc_key` | relative |
| `routes_devops_apply.py` | `routes_devops.py` | `devops_bp` | absolute (`from src.ui.web.routes_devops`) |
| `routes_devops_audit.py` | `routes_devops.py` | `devops_bp` | absolute |
| `routes_devops_detect.py` | `routes_devops.py` | `devops_bp` | absolute |
| `routes_chat.py` | `routes_git_auth.py` | `requires_git_auth` | absolute |
| `routes_integrations.py` | `routes_git_auth.py` | `requires_git_auth` | absolute |
| `routes_pages_api.py` | `routes_git_auth.py` | `requires_git_auth` | absolute |

### Registration (server.py)

`server.py` (line 54-82) imports 29 blueprint symbols from 29 files using
absolute paths (`from src.ui.web.routes_X import X_bp`), then registers
them (line 84-112). The 10 sub-files that extend parent blueprints are
**NOT imported by server.py** — they are loaded as side effects when their
parent module imports them or registers routes at module load time.

Wait — actually, the sub-files register `@backup_bp.route(...)` decorators
at import time. But who imports them? Let me check...

**CRITICAL FINDING**: The backup/content sub-files use relative imports
(`from .routes_backup import backup_bp`) so they are siblings in the
`src.ui.web` package. They get loaded because Python imports the parent
file which contains `backup_bp`, and the sub-files register decorators
on that blueprint when they are imported. BUT — are they explicitly
imported anywhere?

**Answer needed before execution**: We must verify whether `routes_backup.py`
does `import routes_backup_archive` at the bottom, or whether `server.py`
imports them, or whether there's another mechanism.

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Broken imports crash server on startup | **HIGH** | Test every import path after move |
| Sub-file blueprint registration silently lost | **HIGH** | Verify sub-files are imported (find the import chain) |
| Relative imports (`from .routes_X`) break when package changes | **MEDIUM** | All relative imports update to new relative paths |
| Absolute imports from devops/chat/integrations break | **MEDIUM** | Update absolute paths or leave shims |
| Templates referencing `url_for('blueprint.endpoint')` | **LOW** | Blueprint names don't change, only file locations |
| CLI or tests importing from route files | **LOW** | Already verified — no external consumers |

---

## Phase 1: Investigate Before Moving (MUST DO FIRST)

Before any file moves, answer these questions:

### Q1. How are sub-files loaded?
```bash
# Check if parent files import their sub-files
grep -n 'import routes_backup_' src/ui/web/routes_backup.py
grep -n 'import routes_content_' src/ui/web/routes_content.py
grep -n 'import routes_devops_' src/ui/web/routes_devops.py
```

### Q2. Are sub-files imported by server.py or __init__.py?
```bash
grep 'backup_archive\|backup_ops\|backup_restore\|backup_tree' src/ui/web/server.py
grep 'content_files\|content_manage\|content_preview' src/ui/web/server.py
grep 'devops_apply\|devops_audit\|devops_detect' src/ui/web/server.py
```

### Q3. Are there any other import paths we missed?
```bash
grep -rn 'from src.ui.web' src/ --include='*.py' | grep -v '__pycache__' | grep -v 'routes_' | grep -v 'server' | grep -v 'helpers'
```

---

## Phase 2: Naming Convention Decision

### Option A — Drop `routes_` prefix
```
routes_audit.py    → routes/audit.py
routes_ci.py       → routes/ci.py
routes_backup.py   → routes/backup.py
```
**Pro**: Clean. **Con**: `routes/audit.py` collides conceptually with `services/audit/`.

### Option B — Keep `routes_` prefix
```
routes_audit.py    → routes/routes_audit.py
```
**Pro**: Zero rename risk. **Con**: Redundant.

### Option C — Keep names, strip only `routes_` from grouped ones
```
routes_audit.py      → routes/audit.py
routes_backup.py     → routes/backup.py
routes_backup_ops.py → routes/backup_ops.py  (or routes/backup/ops.py)
```

**Recommended**: **Option A** — drop the `routes_` prefix. The `routes/`
directory already provides the namespace. This matches how `services/ci/ops.py`
replaced `services/ci_ops.py`.

---

## Phase 3: Execute the Move (item #8)

### Step 1 — Create package
```bash
mkdir -p src/ui/web/routes
```

### Step 2 — Copy all files (drop prefix)
```bash
for f in src/ui/web/routes_*.py; do
    new_name=$(basename "$f" | sed 's/^routes_//')
    cp "$f" "src/ui/web/routes/$new_name"
done
```

### Step 3 — Update cross-file imports inside `routes/`

All 13 cross-file imports need updating:

| Old import | New import |
|-----------|-----------|
| `from .routes_backup import backup_bp` | `from .backup import backup_bp` |
| `from .routes_content import content_bp, ...` | `from .content import content_bp, ...` |
| `from src.ui.web.routes_devops import devops_bp` | `from .devops import devops_bp` |
| `from src.ui.web.routes_git_auth import requires_git_auth` | `from .git_auth import requires_git_auth` |

### Step 4 — Create `routes/__init__.py`

Re-export all blueprint symbols so `server.py` can do:
```python
from src.ui.web.routes import (
    api_bp, audit_bp, backup_bp, chat_bp, ci_bp, ...
)
```

The `__init__.py` must also trigger the sub-file imports so their
`@blueprint.route()` decorators fire:
```python
from src.ui.web.routes.backup import backup_bp      # defines bp
from src.ui.web.routes import backup_archive         # registers routes on bp
from src.ui.web.routes import backup_ops
from src.ui.web.routes import backup_restore
from src.ui.web.routes import backup_tree
```

### Step 5 — Update server.py

Replace the 29 individual imports (line 54-82) with a single import
from the package `__init__.py`.

### Step 6 — Convert old files to shims

Each old `routes_*.py` becomes a 1-2 line re-export:
```python
"""Backward-compat shim."""
from src.ui.web.routes.audit import audit_bp  # noqa: F401
```

### Step 7 — Validate

```bash
python -c "from src.ui.web.server import create_app; app = create_app(); print('✅')"
```

---

## Phase 4: Split routes_audit.py (item #9)

Only after Phase 3 is stable. `routes/audit.py` (1,781 lines) should
split into a sub-package `routes/audit/`:

```
routes/audit.py (1,781) → routes/audit/
├── __init__.py         — audit_bp definition + sub-file imports
├── overview.py         — dashboard, scores, risk summary
├── detection.py        — L0 system detection endpoints
├── classification.py   — L1 deps/structure endpoints
├── quality.py          — L2 quality/risk endpoints
├── tool_install.py     — tool install/remediate endpoints
└── export.py           — report export endpoints
```

This needs its own detailed analysis of which routes go where.
Defer until Phase 3 is complete and stable.

---

## Phase 5: Evaluate routes_integrations.py (item #10)

520 lines — borderline. Analyze endpoint groups before deciding.
May stay as-is if the endpoints are cohesive.

---

## Execution Order

```
1. Answer Q1-Q3 from Phase 1        (investigation)
2. Decide naming convention          (Option A/B/C)
3. Execute Phase 3 step by step      (the move)
4. Validate server starts            (gate)
5. Remove old files or keep as shims (cleanup)
6. Phase 4 — split audit             (separate PR)
7. Phase 5 — evaluate integrations   (separate PR)
```

## Status

| Phase | Status |
|-------|--------|
| Phase 1 — Investigation | ⬜ |
| Phase 2 — Naming decision | ⬜ |
| Phase 3 — Move to routes/ | ⬜ |
| Phase 4 — Split audit | ⬜ |
| Phase 5 — Evaluate integrations | ⬜ |
