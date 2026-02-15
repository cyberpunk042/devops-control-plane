# Path 5: Push Logic Down — Status & Restart Analysis

> **Created**: 2026-02-15
> **Purpose**: Honest audit of Phase 5 progress against the actual mission

---

## 1. The Actual Mission (not "move audit calls")

**Path 5 is about LAYER HIERARCHY.** The goal:

> A route handler's ONLY job:
> 1. Parse HTTP input (request.get_json, request.args, request.files)
> 2. Call a core service function (passing primitive args, not Flask objects)
> 3. Return HTTP response (jsonify the result)
>
> It does NOT:
> - Contain business logic
> - Make subprocess calls
> - Read/write files directly
> - Make decisions about what to do
> - Record audit events (the SERVICE does that)

Audit moving into core is a **consequence** of routes becoming thin — not the objective.

---

## 2. Current State — Route By Route

### Routes that ARE thin (delegate to core, no inline logic):

| Route file | Lines | Delegates to | Thin? | Notes |
|---|---:|---|:---:|---|
| `routes_terraform.py` | 165 | `terraform_ops.py` | ✅ | Cleaned |
| `routes_secrets.py` | 228 | `secrets_ops.py` | ✅ | Cleaned |
| `routes_dns.py` | 89 | `dns_cdn_ops.py` | ⚠️ | 1 record_event remains |
| `routes_testing.py` | 119 | `testing_ops.py` | ⚠️ | 3 record_event remain |
| `routes_ci.py` | 131 | `ci_ops.py` | ⚠️ | 2 record_event remain |
| `routes_config.py` | ? | ? | ⚠️ | 1 record_event remains |
| `routes_integrations.py` | 307 | various | ? | Needs review |

### Routes that are PARTIALLY thin (delegate to core but still have some inline logic or audit):

| Route file | Lines | Delegates to | Issue |
|---|---:|---|---|
| `routes_vault.py` | 423 | `vault.py`, `vault_env_ops.py` | Audit moved, but still 423 lines — is there inline logic? |
| `routes_docker.py` | 371 | `docker_containers.py`, `docker_generate.py` | Audit moved, but still 371 lines |
| `routes_k8s.py` | 388 | `k8s_ops.py` | Still 388 lines |
| `routes_backup_ops.py` | ? | `backup_ops.py` | 4 record_event calls remain |
| `routes_backup_archive.py` | ? | `backup_archive.py` | 1 record_event remains |
| `routes_content.py` | 485 | `content_crypto.py`? | 4 record_event + 485 lines = NOT thin |

### Routes that are FAT (contain business logic, subprocess calls, NO core service):

| Route file | Lines | subprocess calls | Core service exists? | Plan phase |
|---|---:|---:|:---:|---|
| `routes_pages_api.py` | **879** | 7 | ❌ | 5H |
| `routes_devops_apply.py` | **542** | 9 | ❌ | 5G |
| `routes_content_manage.py` | **461** | 0 | ❌ | 5D |
| `routes_project.py` | **476** | 8 | ❌ | 5E |
| `routes_devops_detect.py` | **400** | 4 | ❌ | 5F |
| `routes_content_files.py` | **392** | 0 | ❌ | 5D |
| `routes_content_preview.py` | **363** | 0 | ❌? | ? |
| `routes_audit.py` | **312** | 2 | ❌? | ? |

---

## 3. What Was Done vs What Should Have Been Done

### What was done:
- Moved `record_event()` calls from some routes into `_audit()` calls in core services
- Pattern: context-based `get_project_root()` for audit

### What should have been done:
For each sub-phase, the plan requires:
1. **Analysis FIRST** — understand what logic is inline in the route
2. **Design** — define core service function signatures
3. **Extract** — move ALL logic (not just audit) from route into core
4. **Verify** — route is thin, CLI gets parity

### What went wrong:
The work narrowed to a single dimension (audit call relocation) instead of the full mission (making routes thin). This means:
- Audit calls were moved but routes still contain business logic
- No new core services were created
- No subprocess calls were moved
- No routes were actually made thin (just had audit removed)

---

## 4. Sub-phase Status (Honest)

### 5A: Vault
- **Audit moved**: ✅ (21 _audit calls in core, 0 in routes)
- **Route thin?**: ❓ UNKNOWN — 423 lines, needs review for inline logic
- **CLI parity?**: ❓ UNTESTED
- **Analysis doc written?**: ❌

### 5B: Backup + Content Crypto
- **Audit moved**: 🔴 Partial (backup_archive + backup_restore done, backup_ops + content_crypto NOT done)
- **Route thin?**: ❓ UNKNOWN
- **CLI parity?**: ❓ UNTESTED
- **Analysis doc written?**: ❌

### 5C: Docker/TF/Secrets/Testing/CI/DNS
- **Audit moved**: 🔴 Partial (Docker/TF/Secrets done, Testing/CI/DNS NOT done)
- **Routes thin?**: ❓ UNKNOWN for most, TF+Secrets likely ✅
- **CLI parity?**: ❓ UNTESTED
- **Analysis doc written?**: ❌

### 5D: Content File Ops
- **Status**: ❌ NOT STARTED
- **Core service**: `content_file_ops.py` does not exist
- **Source routes**: `routes_content_manage.py` (461 lines), `routes_content_files.py` (392 lines)

### 5E: Project Status
- **Status**: ❌ NOT STARTED
- **Core service**: `project_status.py` does not exist
- **Source route**: `routes_project.py` (476 lines, 8 subprocess calls)

### 5F: Wizard Detect
- **Status**: ❌ NOT STARTED
- **Core service**: `wizard_detect.py` does not exist
- **Source route**: `routes_devops_detect.py` (400 lines, 4 subprocess calls)

### 5G: Wizard Apply
- **Status**: ❌ NOT STARTED
- **Core service**: `wizard_apply.py` does not exist
- **Source route**: `routes_devops_apply.py` (542 lines, 9 subprocess calls)

### 5H: Builder Install
- **Status**: ❌ NOT STARTED
- **Core service**: `builder_install.py` does not exist
- **Source route**: `routes_pages_api.py` (879 lines, 7 subprocess calls)

---

## 5. What "Restart Properly" Means

### For each sub-phase (in order 5A → 5H):

**Step 1: Analyse the route**
- Read every function in the route file
- Classify each as: thin wrapper ✅ | has inline logic ❌ | has subprocess ❌
- List what logic needs to move to core

**Step 2: Design the core service**
- Define function signatures (input types, return types)
- Identify what already exists in core vs what needs to be created
- Decide where audit fits (consequence of the service doing the work)

**Step 3: Implement**
- Create/update core service with the logic
- Reduce route to thin wrapper
- Verify compilation

**Step 4: Verify**
- Route is thin (parse → call → respond)
- No subprocess in route
- No record_event in route
- No business logic in route
- CLI can call the same core service

---

## 6. Next Steps

Start with proper sub-phase analyses for 5A-5C to verify what's truly done,
then proceed to 5D (highest user-facing value per the plan).

Each analysis should answer:
1. What does the route currently do? (function by function)
2. What core service functions exist?
3. What logic is still inline in the route?
4. What needs to move?
5. Is the route truly thin after the changes that were already made?
