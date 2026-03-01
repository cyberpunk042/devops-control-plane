# Routes Refactor Plan

> The routes layer should be THIN HTTP dispatchers. No business logic,
> no shared helpers, no cross-imports between route files.
> **Core first. Routes on top.**

**Covers progress tracker items:** #8, #9, #10

---

## The Real Problem

The file location (`routes_*.py` flat in `ui/web/`) is a cosmetic issue.
The structural disease is **business logic and shared utilities leaked
into route files**, creating a dependency web that makes the files
un-moveable without shims.

### Disease #1: `_project_root()` duplicated 28 times

Every route file defines the same 2-line function:

```python
def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])
```

28 copies. Identical. This belongs in ONE place — `helpers.py` already
exists but doesn't provide it.

### Disease #2: Content utilities leaked into routes

`routes_content.py` defines and exports to 3 sub-files:
- `_resolve_safe_path()` — path traversal guard (security utility)
- `_get_enc_key()` — reads encryption key from `.env`

These are **service-level concerns**. Path safety is security.
Encryption key retrieval is vault/secrets territory. Neither belongs
in a route handler file.

### Disease #3: Auth decorator lives in a route file

`routes_git_auth.py` defines `requires_git_auth`, a decorator used by
`routes_chat.py`, `routes_integrations.py`, and `routes_pages_api.py`.

This is **cross-cutting middleware** — it should live in `helpers.py` or
a dedicated `middleware.py`, not in a route file. It's the primary cause
of inter-route imports.

### Disease #4: `_get_stack_names()` duplicated

Both `routes_quality.py` and `routes_security_scan.py` define the same
function that loads project config, discovers stacks, and extracts names.
This is service logic — it could live in `detection.py` or helpers.

### Disease #5: `_refresh_server_path()` — 44 lines of OS logic in a route

`routes_audit.py` defines a 44-line function that manipulates
`os.environ["PATH"]` — prepending `~/.cargo/bin`, `~/.local/bin`,
`/usr/local/go/bin`, etc. This is called after tool installs to ensure
`shutil.which()` finds newly-installed binaries.

This is **system-level infrastructure**. It belongs in `tool_install/`
or a dedicated server utility module. It has zero relationship to HTTP
routing.

### Disease #6: Cache-bust pattern copy-pasted 8+ times

After every tool install/update/remove, the same 4-line cache-bust block
is repeated:

```python
root = Path(current_app.config["PROJECT_ROOT"])
devops_cache.invalidate_scope(root, "integrations")
devops_cache.invalidate_scope(root, "devops")
devops_cache.invalidate(root, "wiz:detect")
```

This appears in: `audit_update_tool`, `audit_execute_plan_sync`,
`audit_execute_plan` (twice — linear + DAG), `audit_resume_plan`,
`audit_remove_tool`. It should be a single helper:
`bust_tool_caches(root)`.

---

## The Hard Problem: `routes_audit.py` (1,781 lines)

This isn't just "big" — it contains **multiple distinct concerns** that
have been stuffed into one file. Here's the real decomposition:

### Line-by-Line Map

```
Lines  1-33    Imports, blueprint, _project_root
Lines  36-79   _refresh_server_path() — OS PATH manipulation (44 lines)
Lines  82-185  AUDIT DATA: L0/L1/L2 analysis endpoints (7 endpoints)
                - audit_system, audit_dependencies, audit_structure
                - audit_clients, audit_scores, audit_scores_enriched
                - audit_scores_history
Lines  188-258 AUDIT DATA: L2 on-demand analysis (4 endpoints)
                - audit_structure_analysis, audit_code_health
                - audit_repo_health, audit_risks
Lines  261-287 TOOL INSTALL: simple install (1 endpoint)
                - audit_install_tool
Lines  290-351 TOOL INSTALL: remediation SSE (1 endpoint)
                - audit_remediate
Lines  353-471 TOOL INSTALL: resolver (5 endpoints)
                - audit_check_deps, audit_resolve_choices
                - audit_install_plan, tools_status
Lines  472-570 AUDIT STAGING: snapshot lifecycle (7 endpoints)
                - audits_pending, audits_pending_detail
                - audits_save, audits_discard
                - audits_saved, audits_saved_detail, audits_saved_delete
Lines  573-650 TOOL VERSION: update/check/version (3 endpoints)
                - audit_update_tool, audit_check_updates, audit_tool_version
Lines  653-751 DEEP DETECTION: hardware/GPU/network (1 endpoint, 95 lines)
                - audit_deep_detect — orchestrates 6 detection domains
Lines  754-1286 PLAN EXECUTION: the monsters (2 endpoints, 530 lines)
                - audit_execute_plan_sync (63 lines — sync, clean)
                - audit_execute_plan (464 lines — SSE streaming)
                    • Pre-flight network checks (30 lines)
                    • DAG execution path (82 lines)
                    • Linear execution path (265 lines)
                    • Remediation analysis (40 lines)
                    • Restart detection (25 lines)
Lines 1289-1518 RESUMABLE PLANS: (3 endpoints, 230 lines)
                - audit_pending_plans, audit_resume_plan (200 lines SSE)
                - Note: audit_resume_plan.generate() is 90% copy-paste
                  from audit_execute_plan.generate() — the step execution
                  loop is duplicated
Lines 1521-1616 PLAN LIFECYCLE: cancel/archive/remove (3 endpoints)
Lines 1619-1719 OFFLINE CACHE: pre-download artifacts (4 endpoints)
Lines 1722-1753 DATA PACKS: freshness/usage (2 endpoints)
Lines 1757-1781 SERVICE STATUS: systemd query (1 endpoint)
```

### The Real Split

This file is actually **5 files** pretending to be one:

```
routes/audit/
├── __init__.py              — audit_bp + shared helpers
├── analysis.py              — L0/L1/L2 audit data endpoints
│                              Lines 82-258 → ~175 lines
│                              11 endpoints, all thin dispatchers
│
├── staging.py               — Audit snapshot lifecycle
│                              Lines 472-570 → ~100 lines
│                              7 endpoints (pending/save/discard/saved)
│
├── tool_install.py          — Install, update, remove, version
│                              Lines 261-471 + 573-650 + 1521-1616
│                              → ~250 lines
│                              12 endpoints (install/remediate/resolve/
│                              update/check/version/remove/status)
│
├── tool_execution.py        — Plan execution SSE streams
│                              Lines 754-1518 → ~760 lines
│                              The hard part. Contains:
│                              - execute_plan_sync (clean, 63 lines)
│                              - execute_plan SSE (464 lines)
│                              - resume_plan SSE (200 lines)
│                              - pending_plans (24 lines)
│                              BUT: execute_plan and resume_plan share
│                              ~80% of their step-loop logic. This
│                              MUST be extracted into a shared generator.
│
├── deep_detection.py        — Deep system detection
│                              Lines 653-751 → ~100 lines
│                              1 endpoint, but 95 lines of orchestration
│                              logic that belongs in core/services
│
└── offline_cache.py         — Pre-download and cache management
                               Lines 1619-1753 → ~135 lines
                               4 endpoints + data pack endpoints
                               + service status (could stay or separate)
```

### The Execute/Resume Duplication — The Core Design Problem

`audit_execute_plan()` (464 lines) and `audit_resume_plan()` (200 lines)
share the same step-execution-loop pattern:

```
For each step:
  1. yield SSE step_start
  2. Execute step (streaming or blocking)
  3. Emit stdout/stderr as log lines
  4. Handle skipped → yield step_done
  5. Handle ok → save_plan_state + yield step_done
  6. Handle fail → save_plan_state + remediation analysis + yield done
After all steps:
  7. save_plan_state(done) + bust caches + restart detection
  8. yield done(ok=true)
```

The only differences between execute and resume:
- Execute resolves the plan first; resume loads from saved state
- Execute has a DAG path; resume doesn't
- Execute has pre-flight network checks; resume doesn't
- Execute runs remediation analysis on failure; resume doesn't
- Step indexing: resume offsets by `completed_count`

**Solution**: Extract a shared `_stream_step_execution()` generator that
both endpoints call. It takes `steps`, `plan_id`, `tool`, `sudo_password`,
`offset`, and `features` dict (network_warnings, do_remediation, etc.)
and yields SSE events. Each route handler does its own setup (resolve
plan vs load plan) then delegates to the shared generator.

This generator doesn't belong in the route file at all — it belongs in
`core/services/tool_install/orchestration/` as a streaming executor.
The route just wraps it in a Flask `Response(stream_with_context(...))`.

### The Deep Detection Orchestration

`audit_deep_detect()` (95 lines) is 90% orchestration logic:
- Import 6 detection modules
- Run each check in a try/except
- Build a result dict

This is a **service function** that should live in
`core/services/tool_install/detection/` as `deep_detect(checks: list)`.
The route handler becomes a 5-line dispatcher.

---

## Execution Strategy

### Phase 0 — Service-level extractions (core first)

Before touching ANY route file:

**0a**: Extract `_refresh_server_path()` → `core/services/tool_install/path_refresh.py`
- Pure OS logic, no Flask dependency
- Used by routes_audit after install/update

**0b**: Extract `deep_detect()` → `core/services/tool_install/detection/deep.py`
- Orchestrates 6 detection modules
- Returns dict, no Flask dependency

**0c**: Extract `bust_tool_caches(root)` → `helpers.py`
- 4-line pattern repeated 8 times
- Depends on Flask `current_app` so stays in web layer

**0d**: Extract SSE step execution generator → 
`core/services/tool_install/orchestration/stream.py`
- The shared step-execution loop (resolve, execute, emit events)
- Pure generator yielding dicts, no Flask dependency
- Both execute_plan and resume_plan call this
- This is the **hardest extraction** — ~200 lines of core logic
  that's currently entangled with Flask's Response/stream_with_context

### Phase 1 — Route-level utility extractions

**1a**: Move `_project_root()` → `helpers.py` as `project_root()`
- Delete 28 copies

**1b**: Move `_resolve_safe_path()` + `_get_enc_key()` → `helpers.py`
- Delete from routes_content.py, update 3 sub-file imports

**1c**: Move `requires_git_auth()` → `helpers.py`
- Delete from routes_git_auth.py, update 3 consumer imports

**1d**: Move `_get_stack_names()` → `helpers.py`
- Delete 2 copies from quality + security_scan

### Phase 2 — Split routes_audit.py into routes/audit/ sub-package

Now that Phase 0 removed the bulk logic, routes_audit.py is mostly thin
dispatchers. Split into 6 files per the map above.

**2a**: Create `routes/audit/__init__.py` with `audit_bp`
**2b**: Move L0/L1/L2 endpoints → `routes/audit/analysis.py`
**2c**: Move staging endpoints → `routes/audit/staging.py`
**2d**: Move install/update/remove → `routes/audit/tool_install.py`
**2e**: Move execute/resume → `routes/audit/tool_execution.py`
  (now thin — delegates to the stream generator from Phase 0d)
**2f**: Move deep detection → `routes/audit/deep_detection.py`
  (now thin — delegates to service from Phase 0b)
**2g**: Move offline cache + data packs → `routes/audit/offline_cache.py`

### Phase 3 — Move all routes to routes/ package (Option B: domain grouping)

With all cross-dependencies resolved in Phase 1, this was mechanical.
Used **Option B** — grouped by domain with standalone files staying flat:

**Sub-packages** (4 groups that already had sub-files):
- `content/` — `__init__` + files + manage + preview (4 modules, 851 lines)
- `backup/` — `__init__` + archive + ops + restore + tree (5 modules, 495 lines)
- `devops/` — `__init__` + apply + audit + detect (4 modules, 459 lines)
- `pages/` — `__init__` + serving + api (3 modules, 430 lines)

**Standalone files** (23 modules, prefix dropped):
- api, chat, ci, config, dev, dns, docker, docs, events, git_auth,
  infra, integrations, k8s, metrics, packages, project, quality,
  secrets, security_scan, terraform, testing, trace, vault

**Cleanup:**
- 39 old `routes_*.py` deleted from `src/ui/web/`
- `server.py` imports updated to `routes.*`
- `routes/README.md` created with full documentation

### Phase 4 — Evaluate routes_integrations.py (520 lines)

Look at endpoint cohesion. If it's all git/GitHub ops, it stays as-is.
If there are unrelated concerns, split.

---

## After-State

```
src/ui/web/
├── __init__.py           Package marker
├── server.py             App factory + blueprint registration
├── helpers.py            Shared utilities (project_root, resolve_safe_path, etc.)
└── routes/               336 routes across 47 files
    ├── README.md          Full documentation
    ├── audit/             42 routes · 7 modules · 1840 lines
    ├── backup/            16 routes · 5 modules · 495 lines
    ├── content/           20 routes · 4 modules · 851 lines
    ├── devops/             8 routes · 4 modules · 459 lines
    ├── pages/             24 routes · 3 modules · 430 lines
    └── 23 standalone      226 routes · ~4600 lines
```

**Before:** 39 flat `routes_*.py` (largest: 1,781 lines), 28 copies of
`_project_root()`, business logic in route handlers.

**After:** Structured package, shared helpers in `helpers.py`, business
logic in `core/services/`, domain grouping, largest: 822 lines.

---

## Risk Assessment

| Phase | Risk | Mitigation |
|-------|------|------------|
| Phase 0 | **HIGH** — extracting SSE generator | Test install SSE end-to-end after |
| Phase 0 | MEDIUM — deep_detect extraction | Pure function, safe to move |
| Phase 1 | LOW — mechanical find-replace | Validate server starts |
| Phase 2 | MEDIUM — 6-file split from 1 | One file at a time, validate each |
| Phase 3 | LOW — all cross-deps resolved | Mechanical move |

## Status

| Phase | Status |
|-------|--------|
| Investigation | 🟢 Done |
| Phase 0 — Service extractions | 🟢 Done |
| Phase 0a — `_refresh_server_path()` → `path_refresh.py` | 🟢 Done |
| Phase 0b — `deep_detect()` → `detection/deep.py` | 🟢 Done |
| Phase 0c — `bust_tool_caches()` → `helpers.py` | 🟢 Done |
| Phase 0d — SSE stream generator → `orchestration/stream.py` | 🟢 Done |
| Phase 1 — Route utility extractions | 🟢 Done |
| Phase 1a — `_project_root()` → `helpers.py` (28 copies removed) | 🟢 Done |
| Phase 1b — `_resolve_safe_path()` + `_get_enc_key()` → `helpers.py` | 🟢 Done |
| Phase 1c — `requires_git_auth()` → `helpers.py` | 🟢 Done |
| Phase 1d — `_get_stack_names()` → `helpers.py` (2 copies removed) | 🟢 Done |
| Phase 2 — Split routes_audit.py | 🟢 Done |
| Phase 2a — `__init__.py` (audit_bp + sub-imports) | 🟢 Done |
| Phase 2b — `analysis.py` (11 endpoints, 219 lines) | 🟢 Done |
| Phase 2c — `staging.py` (7 endpoints, 118 lines) | 🟢 Done |
| Phase 2d — `tool_install.py` (10 endpoints, 345 lines) | 🟢 Done |
| Phase 2e — `tool_execution.py` (6 endpoints, 822 lines) | 🟢 Done |
| Phase 2f — `deep_detection.py` (1 endpoint, 112 lines) | 🟢 Done |
| Phase 2g — `offline_cache.py` (7 endpoints, 190 lines) | 🟢 Done |
| Phase 2h — server.py import updated | 🟢 Done |
| Phase 3 — Move all to routes/ (Option B) | 🟢 Done |
| Phase 3a — content/ sub-package (4 modules, 851 lines) | 🟢 Done |
| Phase 3b — backup/ sub-package (5 modules, 495 lines) | 🟢 Done |
| Phase 3c — devops/ sub-package (4 modules, 459 lines) | 🟢 Done |
| Phase 3d — pages/ sub-package (3 modules, 430 lines) | 🟢 Done |
| Phase 3e — 23 standalone modules moved | 🟢 Done |
| Phase 3f — server.py imports updated | 🟢 Done |
| Phase 3g — 39 old routes_*.py deleted | 🟢 Done |
| Phase 3h — routes/README.md documentation | 🟢 Done |
| Phase 4 — Evaluate integrations | ⬜ |
