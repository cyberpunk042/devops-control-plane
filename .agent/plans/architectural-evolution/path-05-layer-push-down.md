# Path 5: Push Logic Down — Layer Hierarchy

> **Status**: Deep Analysis
> **Effort**: 6–8 days (phased by domain)
> **Risk**: Medium — structural refactoring, but each sub-phase is independently shippable
> **Prereqs**: Path 1 (Logging) ✅, Path 2 (Datasets) ✅, Path 3 (File Splitting) ✅, Path 4 (Audit) ✅
> **Unlocks**: Path 6 (Caching), Path 7 (Modal Preview), Phase 8 (TUI Enhancement)

---

## 1. The Architectural Principle

### 1.1 The Onion

```
┌──────────────────────────────────────────────────────┐
│  WEB  (admin panel, extreme observability, UX)       │
│  ┌──────────────────────────────────────────────┐    │
│  │  TUI  (manage.sh, interactive console)       │    │
│  │  ┌──────────────────────────────────────┐    │    │
│  │  │  CLI  (python -m src.main)           │    │    │
│  │  │  ┌──────────────────────────────┐    │    │    │
│  │  │  │  CORE  (services, data, audit)│    │    │    │
│  │  │  └──────────────────────────────┘    │    │    │
│  │  └──────────────────────────────────────┘    │    │
│  └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

**Core** = services, data, persistence, audit, logging. No framework deps.
**CLI** = Click commands that call core. No Flask, no browser.
**TUI** = manage.sh with interactive sub-menus. Calls CLI.
**WEB** = Flask routes that call core. Thin HTTP wrappers only.

**The rule**: Every outer layer calls inward, never outward.
Logic lives as deep in the onion as possible.

### 1.2 What "Thin Route" Actually Means

A route handler's ONLY job:
1. Parse HTTP input (request.get_json, request.args, request.files)
2. Call a core service function (passing primitive args, not Flask objects)
3. Return HTTP response (jsonify the result)

It does NOT:
- Contain business logic
- Make subprocess calls
- Read/write files directly
- Make decisions about what to do
- Record audit events (the SERVICE does that)

### 1.3 What "Audit in Core" Means

**Wrong** (current — 93 calls in routes, 0 in CLI):
```python
# Route calls service, then records audit
result = vault.lock_vault(path, passphrase)
devops_cache.record_event(root, label="🔒 Vault Locked", ...)
```
Problem: CLI does `vault.lock_vault()` too, but gets zero audit trail.

**Right** (target — audit is the service's responsibility):
```python
# Service does the work AND records audit
def lock_vault(secret_path, passphrase, *, project_root=None):
    # ... encryption logic ...
    if project_root:
        record_event(project_root, label="🔒 Vault Locked", ...)
    return result
```
Now EVERY caller (CLI, TUI, Web) gets audit for free.

The `project_root` parameter is optional because some core services
are called in contexts where we don't have a project root (tests, etc.).
When it's provided, audit fires. When it's not, it silently skips.

---

## 2. Current State Diagnosis

### 2.1 The Three Layers Today

**Core services** (`src/core/services/`): 44 Python modules, ~28K lines
- These exist and work. CLI calls them. Web calls them.
- But they DON'T record audit events. Only `devops_cache.py` defines `record_event()`.

**CLI** (`src/ui/cli/`): 18 command groups, ~5K lines
- Thin Click wrappers that call core services. Well-structured.
- BUT: No audit trail. CLI operations are invisible.
- Some CLI commands call `vault_env_ops.add_keys()` directly — same function
  the web route calls — but only the web route records the audit event.

**Web routes** (`src/ui/web/routes_*.py`): 31 files, ~9K lines
- **Some are thin** (call core, format response) — good
- **Some are fat** (contain business logic, subprocess calls) — bad
- ALL audit calls (93 total) live here — bad

**TUI** (`manage.sh`): 166 lines, 13 menu items
- Barebones launcher. Items 8-13 just print `--help`.
- No interactive sub-menus, no prompts, no formatted output.
- Reference (continuity-orchestrator): 445 lines, interactive prompts,
  confirmation dialogs, formatted output, real TUI functions.

### 2.2 Audit Call Locations (The Problem Quantified)

| Route file | Audit calls | CLI equivalent? | CLI has audit? |
|---|---:|:---:|:---:|
| `routes_vault.py` | 20 | ✅ `cli/vault.py` | ❌ |
| `routes_content_manage.py` | 8 | ❌ no CLI for save/rename/move | — |
| `routes_content_files.py` | 6 | ❌ no CLI for create-folder/delete/upload | — |
| `routes_content.py` | 4 | ✅ `cli/content.py` (encrypt/decrypt) | ❌ |
| `routes_backup_ops.py` | 10 | ✅ `cli/backup.py` | ❌ |
| `routes_backup_archive.py` | 4 | ✅ `cli/backup.py` | ❌ |
| `routes_backup_restore.py` | 8 | ✅ `cli/backup.py` | ❌ |
| `routes_docker.py` | 13 | ✅ `cli/docker.py` | ❌ |
| `routes_terraform.py` | 7 | ✅ `cli/terraform.py` | ❌ |
| `routes_secrets.py` | 7 | ✅ `cli/secrets.py` | ❌ |
| `routes_devops_apply.py` | 7 | ❌ no CLI for wizard setup | — |
| `routes_devops_detect.py` | 0 | ✅ `cli` (detect command) | — |
| `routes_testing.py` | 3 | ✅ `cli/testing.py` | ❌ |
| `routes_ci.py` | 2 | ✅ `cli/ci.py` | ❌ |
| `routes_dns.py` | 1 | ✅ `cli/dns.py` | ❌ |
| `routes_config.py` | 1 | partial | ❌ |
| `routes_pages_api.py` | 2 | ✅ `cli/pages.py` | ❌ |
| **Total** | **93** | | **0** |

**The direct consequence**: If you lock the vault from CLI (`controlplane vault lock`),
it works but the audit log shows nothing. If you do the same from the web UI,
it records the event. This is a fundamental design flaw.

### 2.3 Fat Routes (Business Logic in the Wrong Layer)

#### Routes that contain business logic with NO core service backing:

| Route | Lines | What's inline | Core service exists? |
|---|---:|---|:---:|
| `routes_pages_api.py` | 879 | Builder install (210 lines: pip, hugo binary, npm), Pages init, builder detection | ❌ |
| `routes_devops_apply.py` | 542 | Wizard setup: git init/branch/hooks, subprocess calls × 9 | ❌ |
| `routes_content_manage.py` | 461 | File save (with diff compute), rename, move, enc key setup | ❌ |
| `routes_devops_detect.py` | 400 | Wizard detection assembly (230 lines), status probes | ❌ |
| `routes_content_files.py` | 392 | Folder create, file delete, upload pipeline | ❌ |
| `routes_project.py` | 476 | 9 status probes (git, docker, github, k8s, etc.), subprocess × 8 | ❌ |
| `routes_content_preview.py` | 363 | Encrypted save-in-place | ❌ |
| **Total inline business logic** | **~2,500** | | |

#### Routes that are already thin (delegate to core services):

| Route | Lines | Core service | Pattern |
|---|---:|---|---|
| `routes_vault.py` | 642 | `vault.py`, `vault_env_ops.py` | ✅ delegates (but audit is in route) |
| `routes_docker.py` | 497 | `docker_ops.py`, `docker_generate.py` | ✅ delegates (but audit is in route) |
| `routes_k8s.py` | 388 | `k8s_ops.py`, `k8s_generate.py` | ✅ delegates |
| `routes_terraform.py` | 230 | `terraform_ops.py` | ✅ delegates |
| `routes_backup_*.py` | ~687 | `backup_*.py` | ✅ delegates |
| `routes_secrets.py` | 297 | `secrets_ops.py` | ✅ delegates |
| `routes_testing.py` | 119 | `testing_ops.py` | ✅ delegates |
| `routes_ci.py` | 131 | `ci_ops.py` | ✅ delegates |
| `routes_dns.py` | 89 | `dns_cdn_ops.py` | ✅ delegates |

For these "already thin" routes, the work is:
1. Move audit calls from route → core service
2. Remove audit boilerplate from route (route shrinks)
Done. No business logic extraction needed.

### 2.4 Subprocess Calls in Routes

28 total. These should all live in core services:

| Route | Count | What |
|---|---:|---|
| `routes_devops_apply.py` | 9 | git init, git branch, git commit, git hooks |
| `routes_project.py` | 8 | git, docker, gh, kubectl, terraform probes |
| `routes_pages_api.py` | 7 | pip install, hugo download, npm install |
| `routes_devops_detect.py` | 4 | git, docker, gh probes |
| `routes_audit.py` | 2 | pip install audit tool |

---

## 3. The Two Workstreams

This phase has two distinct workstreams that can be interleaved:

### Workstream A: Move Audit Into Core Services (the "thin" routes)

For routes that ALREADY delegate to core services (vault, docker, terraform,
backup, secrets, testing, ci, dns), the work is:

1. Add `project_root: Path | None = None` parameter to each core service function
2. Move the `record_event()` call from the route INTO the service function
3. Remove the audit boilerplate from the route
4. CLI gets audit for free (pass `project_root` from Click context)

**Scope**: ~93 audit calls to relocate across ~20 core service files.

### Workstream B: Extract Business Logic Into New Core Services (the "fat" routes)

For routes that contain business logic with no core service:

1. Create the missing core service module
2. Extract the business logic (with audit built in)
3. Reduce the route to a thin wrapper

**New modules to create**:
| Module | Source | Key functions |
|---|---|---|
| `content_file_ops.py` | `routes_content_manage.py`, `routes_content_files.py` | save, rename, move, create_folder, delete, upload |
| `project_status.py` | `routes_project.py` | All 9 probes, suggest_next, compute_progress |
| `wizard_detect.py` | `routes_devops_detect.py` | Detection assembly, status probes |
| `wizard_apply.py` | `routes_devops_apply.py` | Per-integration setup (git, docker, k8s, ci, tf) |
| `builder_install.py` | `routes_pages_api.py` | pip/hugo/npm installation |

---

## 4. Phased Execution Plan

### Phase 5A: Vault — Move Audit Down (reference implementation)

**Why first**: Vault is the BEST example because:
- Core services already exist (`vault.py`, `vault_env_ops.py`)
- CLI already exists (`cli/vault.py`) and calls the same core functions
- 20 audit calls to move — proves the pattern
- After this, CLI `vault lock` gets an audit trail

**Work**:
1. Add `project_root: Path | None = None` to `lock_vault()`, `unlock_vault()`,
   `register_passphrase()`, `vault_env_ops.add_keys()`, `update_key()`,
   `delete_key()`, `move_key()`, `rename_section()`, `create_env()`,
   `activate_env()`, `vault_env_ops.set_auto_lock_minutes()`,
   `toggle_local_only()`, `set_meta()`, `export_vault_file()`, `import_vault_file()`
2. Move 20 `record_event()` calls from `routes_vault.py` into these functions
3. Strip audit boilerplate from `routes_vault.py` 
4. Update `cli/vault.py` to pass `project_root` to core functions
5. Verify: CLI vault lock → audit log entry appears

**Files touched**: `vault.py`, `vault_env_ops.py`, `vault_io.py`,
`routes_vault.py`, `cli/vault.py`

### Phase 5B: Backup, Content Crypto — Move Audit Down

**Same pattern** as 5A for services that already exist:
- `backup_archive.py`, `backup_restore.py`, `backup_ops.py` (move 22 audit calls)
- `content_crypto.py` (move 4 audit calls for encrypt/decrypt)
- Update corresponding CLI modules

### Phase 5C: Docker, Terraform, Secrets, Testing, CI, DNS — Move Audit Down

**Same pattern** for remaining thin routes:
- `docker_ops.py`, `docker_generate.py` (13 audit calls)
- `terraform_ops.py` (7)
- `secrets_ops.py` (7)
- `testing_ops.py` (3)
- `ci_ops.py` (2)
- `dns_cdn_ops.py` (1)

After 5A–5C: All 93 audit calls live in core services. CLI gets full audit parity.

### Phase 5D: Extract Content File Ops → Core Service

**Create**: `src/core/services/content_file_ops.py`

Extract from `routes_content_manage.py`:
- `save_file(root, rel_path, content) → dict` (with diff computation + audit)
- `rename_file(root, rel_path, new_name) → dict` (with collision check + audit)
- `move_file(root, rel_path, dest_folder) → dict` (with sidecar handling + audit)
- `setup_encryption_key(root, key, generate=False) → dict` (with .env management + audit)

Extract from `routes_content_files.py`:
- `create_folder(root, name) → dict` (with validation + audit)
- `delete_path(root, rel_path) → dict` (with sidecar cleanup + audit)
- `upload_file(root, folder, data, filename, mime) → dict` (with optimization + audit)

**Why this matters**: Content file management is the most common user operation.
There is NO CLI command for it today. After this phase, we can add
`controlplane content save`, `controlplane content rename`, etc.

### Phase 5E: Extract Project Status → Core Service

**Create**: `src/core/services/project_status.py`

This is the cleanest extraction — the 9 `_probe_*` functions in
`routes_project.py` already take `root: Path` as their only argument
and have NO Flask dependency. They use `subprocess.run()` and `Path`.

Move: `probe_project`, `probe_git`, `probe_github`, `probe_docker`,
`probe_cicd`, `probe_k8s`, `probe_terraform`, `probe_pages`, `probe_dns`,
`suggest_next`, `compute_progress`, `INTEGRATION_ORDER`, `DEPENDENCY_MAP`

Route becomes literally:
```python
@project_bp.route("/project/status")
def project_status_route():
    return jsonify(project_status.full_status(_root()))
```

### Phase 5F: Extract Wizard Detect → Core Service

**Create**: `src/core/services/wizard_detect.py`

`_wizard_detect_compute(root)` (230 lines) already takes `root` as its
only argument. All `_wizard_*` helper functions (~130 lines) similarly.
Clean extraction.

### Phase 5G: Extract Wizard Apply → Core Service

**Create**: `src/core/services/wizard_apply.py`

The 446-line `wizard_setup()` function is one giant if/elif chain:
```python
if action == "git": ... subprocess × 6
elif action == "github": ... subprocess × 3
elif action == "docker": ... 
elif action == "k8s": ...
elif action == "ci": ...
elif action == "terraform": ...
```

Each branch becomes its own function in the core service:
- `setup_git(root, config) → dict`
- `setup_github(root, config) → dict`
- `setup_docker(root, config) → dict`
- `setup_k8s(root, config) → dict`
- `setup_ci(root, config) → dict`
- `setup_terraform(root, config) → dict`
- `delete_config(root, target) → dict`

### Phase 5H: Extract Builder Install → Core Service

**Create**: `src/core/services/builder_install.py`

Three install strategies, each as a generator (for streaming output):
- `install_pip(root, packages) → Generator[str, None, dict]`
- `install_hugo(root) → Generator[str, None, dict]`
- `install_npm(root, packages) → Generator[str, None, dict]`

Also extract `_detect_best_builder()` and `init_pages()` into `pages_engine.py`.

---

## 5. Interface Principles

### Core services return plain `dict`

Every core service function returns a plain Python dict. Never a Flask
Response, never Click-formatted text. The dict IS the interface contract.

Each caller layer transforms the dict for its medium:
- **CLI**: `dict` → formatted text (`click.secho`, tables)
- **TUI**: same CLI output + interactive prompts around it
- **WEB**: `dict` → `jsonify(result)` 

### Audit lives in the service, not the caller

When a core service performs a mutating operation, it records the audit
event itself. The caller (route, CLI command) doesn't need to know.

**How** the service accesses the audit system is an implementation detail
to be resolved per sub-phase. The plan doesn't prescribe the mechanism — 
it prescribes the principle: the service owns the operation AND its audit trail.

### One operation = one audit entry

No double-logging. If `backup_archive.create_backup()` internally calls
helper functions, there is ONE audit entry for "Backup Created," not
separate entries for each internal step.

---

## 7. Execution Order & Priority

```
5A  Vault audit → core         ── reference implementation, proves the pattern
 ↓
5B  Backup + Content crypto    ── same pattern, more volume
 ↓
5C  Docker/TF/Secrets/etc      ── same pattern, all remaining thin routes
 ↓
5D  Content file ops → core    ── new service, highest user-facing value
 ↓
5E  Project status → core      ── cleanest extraction (zero Flask deps)
 ↓
5F  Wizard detect → core       ── already root-only, clean
 ↓
5G  Wizard apply → core        ── complex (subprocess, multi-branch)
 ↓
5H  Builder install → core     ── complex (streaming, downloads)
```

### Why this order

1. **5A–5C first**: Move 93 audit calls into core. This is the highest-value
   work — every CLI command immediately gains audit trail. The pattern is
   proven on vault, then applied mechanically to everything else.

2. **5D next**: Content file ops are the most user-visible missing core service.
   After this, `controlplane content save <file>` becomes possible.

3. **5E–5H**: Progressively harder extractions. Each one unlocks future
   CLI/TUI capabilities.

---

## 8. Success Criteria

| Metric | Before | After |
|---|---|---|
| `record_event()` calls in routes | 93 | 0 |
| `record_event()` calls in core services | 0 | 93+ |
| CLI operations with audit trail | 0 | all |
| subprocess calls in routes | 28 | 0 |
| Business logic lines in routes | ~2,500 | ~200 |
| Route files > 400 lines | 9 | ≤ 1 |
| New core service modules | — | 5 |
| Flask imports in core services | 0 | 0 (enforced) |

### Verification

```bash
# After all phases:

# 1. No audit calls in routes
grep -r 'record_event' src/ui/web/routes_*.py | grep -v __pycache__
# Should return nothing

# 2. No Flask in core  
grep -r 'from flask\|import flask' src/core/ | grep -v __pycache__
# Should return nothing

# 3. No subprocess in routes
grep -r 'subprocess\.' src/ui/web/routes_*.py | grep -v __pycache__
# Should return nothing

# 4. CLI audit works
controlplane vault lock .env -p test123
cat .state/audit_activity.json | python3 -m json.tool | tail -20
# Should show the lock event
```

---

## 9. Risk Assessment

### Manageable Risks

1. **Signature changes**: Adding `project_root` to existing service functions
   is backwards-compatible (default `None`, keyword-only). No callers break.

2. **Import order**: `record_event` is defined in `devops_cache.py` which is
   already imported by many services. No circular import risk.

3. **File upload**: `content_upload()` receives `request.files` (Flask).
   The route extracts bytes/data BEFORE calling the core service.
   Core service receives `(data: bytes, filename: str, mime: str)`.

### Harder Problems

1. **SSE streaming**: `routes_pages_api.py` builder install uses
   `yield` for SSE. The core service returns a generator. The route
   wraps it in `Response(stream, content_type="text/event-stream")`.

2. **Wizard setup atomicity**: The wizard setup function does multiple
   subprocess calls. If git init succeeds but git branch fails, we need
   the audit to reflect partial success. Handle per-step try/except.

### What We Are NOT Doing (Scope Guard)

- ❌ NOT adding new CLI commands (that's Phase 8 / TUI Enhancement)
- ❌ NOT changing the TUI menu yet (Phase 8)
- ❌ NOT changing any API response formats
- ❌ NOT changing the audit event schema
- ❌ NOT refactoring the NDJSON ledger system
- ❌ NOT adding new web routes

---

## 10. Relationship to Other Phases

This is the **keystone phase**. Everything before was preparation:

- **Phase 1 (Logging)**: Core services now have `logger`, can debug
- **Phase 2 (Datasets)**: Data lives in `core/data/`, served from core
- **Phase 3 (File Splitting)**: Code is modular, ready to move
- **Phase 4 (Audit)**: 93 audit calls exist, need to move into core

Everything after depends on this:

- **Phase 6 (Caching)**: Core services control what gets cached
- **Phase 7 (Modal/UI)**: UI calls thin routes that call core
- **Phase 8 (TUI)**: TUI calls CLI which calls core (with audit)

---

## 11. Resolved Decisions

1. **No double audit**: One user-initiated operation = one audit entry.
   If backup internally calls crypto, we audit the backup operation,
   not the crypto sub-call. This is what an audit log IS.

2. **Audit failures**: Yes. Both success and failure are audited.

3. **Implementation mechanics** (how to thread audit context into core
   services, exact function signatures, parameter conventions): These are
   deferred to per-sub-phase analysis. Each sub-phase (5A, 5B, etc.)
   will get its own in-depth analysis before any code is written.
