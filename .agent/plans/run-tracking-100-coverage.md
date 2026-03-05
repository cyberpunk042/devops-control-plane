# Run Tracking — 100% Coverage Plan

> **Goal**: Every mutating operation emits a tracked Run with rich, referenceable metadata.
> **Date**: 2026-03-04

---

## Table of Contents

1. [Current State](#current-state)
2. [Problem Statement](#problem-statement)
3. [Phase 1 — Metadata Enrichment](#phase-1--metadata-enrichment)
4. [Phase 2 — Missing Domain Coverage](#phase-2--missing-domain-coverage)
5. [Phase 3 — Exclusion List (Read-Only / UX-Only)](#phase-3--exclusion-list)
6. [Implementation Order](#implementation-order)

---

## Current State

### What Exists Today

| Metric | Count |
|--------|-------|
| Total `@run_tracked` decorators | **89** |
| Route domains WITH tracking | **15** |
| Route domains WITHOUT tracking | **16** |
| Domains with mutating routes needing tracking | **6** |
| Domains that are read-only / UX-only (no tracking needed) | **10** |
| Total untracked mutating routes | **33** |

### What's Wrong With Currently-Tracked Routes

The `_extract_run_metadata()` function in `run_tracker.py` (lines 313-353) only extracts TWO fields from the response JSON:

1. **`summary`** — one-line text from `response["summary"]` or fallback to `response["message"]`
2. **`status`** — derived from HTTP status code OR `response["ok"]`

**Everything else is lost.** The Run model has a `metadata: dict[str, Any]` field that is **ALWAYS empty `{}`** in every recorded run. This means:

- A `git:commit` run records `summary: "fix: bug"` but not the commit hash, branch, or files changed
- A `docker:build` run records ok/failed but not which service was built or how long it took
- A `deploy:k8s` run records nothing — no manifest path, no namespace, no pod counts

### Run Model Fields Available

From `src/core/services/ledger/models.py` — the `Run` model:

```
run_id            — auto-generated, e.g. run_20260303T232000Z_git_czy7
type              — set by decorator (e.g. "git", "deploy", "setup")
subtype           — set by decorator (e.g. "git:commit", "deploy:k8s")
status            — "ok" | "failed" | "partial" ← extracted from response
user              — from git config user.name ← populated
code_ref          — HEAD SHA at run time ← populated
started_at        — ISO timestamp ← populated
ended_at          — ISO timestamp ← populated
duration_ms       — elapsed time ← populated
environment       — target env ← ALWAYS EMPTY
modules_affected  — which modules ← ALWAYS EMPTY []
summary           — one-liner ← sometimes populated, often empty
metadata          — arbitrary dict ← ALWAYS EMPTY {}
```

---

## Problem Statement

1. **Metadata is empty**: The 89 already-tracked routes produce runs with no operational detail.
   When referenced in traces or chat (`@run:xyz`), they show type + timestamp + status but
   nothing about *what actually happened*.

2. **33 mutating routes are untracked**: Six domains have zero tracking on operations that
   modify state (backup/restore, secrets, CI generation, wizard setup, DNS, config).

---

## Phase 1 — Metadata Enrichment ✅ COMPLETE (2026-03-04)

**Goal**: Make `_extract_run_metadata()` automatically harvest rich data from response JSON into `metadata`.

### Current Extraction (lines 313-353 of run_tracker.py)

```python
def _extract_run_metadata(response, run, summary_key, ok_key):
    # Only extracts: run["status"] and run["summary"]
    # The response JSON often contains: hash, branch, files, service, output, counts...
    # But none of that is captured.
```

### Proposed Enhancement

Add a third extraction step — **harvest response data into `run["metadata"]`**:

```python
# After setting status and summary, harvest response data into metadata
METADATA_KEYS = {
    # Git
    "hash", "branch", "files", "changes", "ahead", "behind",
    # Docker
    "service", "container", "image", "output",
    # K8s
    "namespace", "path", "replicas", "resource",
    # Terraform
    "workspace", "plan_changes",
    # Vault
    "entries", "provider",
    # Backup
    "backup_path", "target_folder", "archive",
    # General
    "count", "target", "created", "deleted", "skipped",
    "files_affected", "warnings",
}

for key in METADATA_KEYS:
    if key in data and data[key] is not None:
        run.setdefault("metadata", {})[key] = data[key]
```

### Why This Works

Nearly all service functions return dicts with descriptive keys:

| Service Return | Available Keys |
|----------------|----------------|
| `git_commit()` | `ok`, `hash`, `message` |
| `docker_build()` | `ok`, `service`, `output` |
| `k8s_apply()` | `ok`, `output`, `namespace` |
| `terraform_plan()` | `ok`, `output`, `plan_changes` |
| `vault_unlock()` | `ok`, `entries` |
| `backup_export()` | `ok`, `archive`, `target_folder`, `paths` |

The metadata harvesting reads these keys from the response JSON that the Flask route
returns via `jsonify(result)`. No route code changes needed — the decorator does it automatically.

### Files Changed

| File | Change |
|------|--------|
| `src/core/services/run_tracker.py` | Modify `_extract_run_metadata()` to harvest response data into `metadata` |
| `src/core/services/run_tracker.py` | Update `run_bag` in `tracked_run()` to support `metadata` dict |
| `src/core/services/ledger/models.py` | No change needed — `metadata: dict[str, Any]` already exists |

### Impact

- **89 existing tracked routes** immediately start recording rich metadata
- **Zero route code changes** — pure decorator-level fix
- Runs become referenceable with context: "built docker image `myapp`, took 12s, service=web"

---

## Phase 2 — Missing Domain Coverage ✅ COMPLETE (2026-03-04)

### 2.1 backup (12 mutating routes)

| Route | File | Type | Subtype | Summary Source |
|-------|------|------|---------|----------------|
| `POST /backup/export` | `archive.py:13` | `backup` | `backup:export` | `result["archive"]` |
| `POST /backup/upload` | `archive.py:104` | `backup` | `backup:upload` | filename |
| `POST /backup/upload-release` | `ops.py:17` | `backup` | `backup:upload_release` | path |
| `POST /backup/encrypt` | `ops.py:34` | `setup` | `setup:encrypt_backup` | path |
| `POST /backup/decrypt` | `ops.py:51` | `setup` | `setup:decrypt_backup` | path |
| `POST /backup/delete-release` | `ops.py:71` | `destroy` | `destroy:backup_release` | path |
| `POST /backup/rename` | `ops.py:88` | `setup` | `setup:backup_rename` | old→new |
| `POST /backup/mark-special` | `ops.py:113` | `setup` | `setup:backup_special` | path |
| `POST /backup/restore` | `restore.py:27` | `restore` | `restore:backup` | backup_path |
| `POST /backup/import` | `restore.py:56` | `restore` | `restore:backup_import` | backup_path |
| `POST /backup/wipe` | `restore.py:78` | `destroy` | `destroy:wipe` | target_folder |
| `POST /backup/delete` | `restore.py:104` | `destroy` | `destroy:backup_delete` | backup_path |

**Files to modify**: `archive.py`, `ops.py`, `restore.py` — add `from src.core.services.run_tracker import run_tracked` and decorate each route.

### 2.2 secrets (7 mutating routes)

| Route | File | Type | Subtype | Summary Source |
|-------|------|------|---------|----------------|
| `POST /keys/generate` | `actions.py:18` | `generate` | `generate:key` | type (password/token/ssh) |
| `POST /gh/environment/create` | `actions.py:35` | `setup` | `setup:gh_environment` | env name |
| `POST /env/cleanup` | `actions.py:51` | `destroy` | `destroy:environment` | env name |
| `POST /env/seed` | `actions.py:71` | `setup` | `setup:env_seed` | environments list |
| `POST /secret/set` | `actions.py:87` | `setup` | `setup:secret_set` | secret name (NOT value) |
| `POST /secret/remove` | `actions.py:108` | `destroy` | `destroy:secret` | secret name |
| `POST /secrets/push` | `actions.py:129` | `deploy` | `deploy:secrets_push` | count of secrets |

**Files to modify**: `actions.py` — add import and 7 decorators.

### 2.3 ci (2 mutating routes)

| Route | File | Type | Subtype |
|-------|------|------|---------|
| `POST /ci/generate/ci` | `generate.py:13` | `generate` | `generate:ci_workflow` |
| `POST /ci/generate/lint` | `generate.py:25` | `generate` | `generate:lint_workflow` |

**Files to modify**: `generate.py` — add import and 2 decorators.

### 2.4 devops (10 mutating routes)

| Route | File | Type | Subtype | Should Track? |
|-------|------|------|---------|---------------|
| `POST /wizard/setup` | `apply.py:29` | `setup` | `setup:wizard` | **YES** — generates configs |
| `DELETE /wizard/config` | `apply.py:51` | `destroy` | `destroy:wizard_config` | **YES** — deletes generated files |
| `POST /wizard/compose-ci` | `apply.py:69` | `generate` | `generate:wizard_ci` | **YES** — generates CI files |
| `POST /wizard/validate` | `apply.py:107` | `validate` | `validate:wizard` | **BORDERLINE** — dry-run, no mutation |
| `POST /wizard/check-tools` | `apply.py:128` | `validate` | `validate:wizard_tools` | **NO** — read-only check |
| `POST /devops/audit/dismissals` | `audit.py:26` | `scan` | `scan:dismiss_finding` | **YES** — modifies source files |
| `DELETE /devops/audit/dismissals` | `audit.py:51` | `scan` | `scan:undismiss_finding` | **YES** — modifies source files |
| `PUT /devops/prefs` | `__init__.py:46` | `setup` | `setup:devops_prefs` | **BORDERLINE** — prefs are UX, not operational |
| `PUT /devops/integration-prefs` | `__init__.py:67` | `setup` | `setup:integration_prefs` | **BORDERLINE** — prefs are UX |
| `POST /devops/cache/bust` | `__init__.py:84` | — | — | **NO** — cache bust is ephemeral |

**Decision needed**: Track prefs changes? They modify `devops_prefs.json` but are UX configuration, not operational actions.

**Files to modify**: `apply.py`, `audit.py`, optionally `__init__.py`.

### 2.5 dns (1 mutating route)

| Route | File | Type | Subtype |
|-------|------|------|---------|
| `POST /dns/generate` | `__init__.py:60` | `generate` | `generate:dns_records` |

**Files to modify**: `__init__.py` — add import and 1 decorator.

### 2.6 config (1 mutating route)

| Route | File | Type | Subtype |
|-------|------|------|---------|
| `POST /config` | `__init__.py:49` | `setup` | `setup:config_save` |

**Files to modify**: `__init__.py` — add import and 1 decorator.

---

## Phase 3 — Exclusion List

These domains have NO mutating routes or are purely UX/read-only — **no tracking needed**:

| Domain | Reason |
|--------|--------|
| `api` | Status/health checks — read-only |
| `artifacts` | Static file serving — read-only |
| `chat` | Messages tracked separately via chat_ops |
| `dev` | Dev tools (REPL, reload) — not operational |
| `events` | SSE stream — read-only |
| `metrics` | Telemetry serving — read-only |
| `project` | Project info read — read-only |
| `server` | Server control (reload) — dev-only |
| `smart_folders` | Content metadata — read-only |
| `trace` | Trace management already has its own tracking system |

---

## Implementation Order

### Step 1: Metadata Enrichment (Phase 1)
- **Single file**: `src/core/services/run_tracker.py`
- **Impact**: 89 existing routes immediately get rich metadata
- **Risk**: Low — additive change, fail-safe

### Step 2: Backup domain tracking (Phase 2.1)
- **Files**: `routes/backup/archive.py`, `routes/backup/ops.py`, `routes/backup/restore.py`
- **Routes**: 12
- **Why first**: Backup/restore are critical operations — must be tracked

### Step 3: Secrets domain tracking (Phase 2.2)
- **Files**: `routes/secrets/actions.py`
- **Routes**: 7
- **Why second**: Security-sensitive operations — must be tracked

### Step 4: DevOps domain tracking (Phase 2.4)
- **Files**: `routes/devops/apply.py`, `routes/devops/audit.py`
- **Routes**: 5-7 (depends on prefs decision)

### Step 5: CI + DNS + Config tracking (Phase 2.3, 2.5, 2.6)
- **Files**: `routes/ci/generate.py`, `routes/dns/__init__.py`, `routes/config/__init__.py`
- **Routes**: 4

### Final Tally After Completion

| Metric | Before | After |
|--------|--------|-------|
| Tracked mutating routes | 89 | **117** |
| Untracked mutating routes | 33 | **0** |
| Domains with tracking | 15 | 21 |
| Runs with metadata | 0% | 100% |
| Coverage | ~73% | **100%** |

---

## Type/Subtype Taxonomy (Complete)

All types used across the system after 100% coverage:

| Type | Subtypes |
|------|----------|
| `backup` | `backup:export`, `backup:upload`, `backup:upload_release` |
| `build` | `build:docker`, `build:pages_segment`, `build:pages_all`, `build:pages_merge` |
| `deploy` | `deploy:docker_up`, `deploy:docker_restart`, `deploy:k8s`, `deploy:k8s_scale`, `deploy:helm_upgrade`, `deploy:terraform`, `deploy:pages`, `deploy:secrets_push` |
| `destroy` | `destroy:docker_down`, `destroy:docker_prune`, `destroy:docker_rm`, `destroy:docker_rmi`, `destroy:k8s`, `destroy:terraform`, `destroy:git_remote`, `destroy:backup_release`, `destroy:backup_delete`, `destroy:wipe`, `destroy:environment`, `destroy:secret`, `destroy:wizard_config` |
| `format` | `format:quality`, `format:terraform` |
| `generate` | `generate:dockerfile`, `generate:dockerignore`, `generate:compose`, `generate:compose_wizard`, `generate:docker_write`, `generate:changelog`, `generate:readme`, `generate:k8s_manifests`, `generate:k8s_wizard`, `generate:terraform`, `generate:env_example`, `generate:env`, `generate:quality_config`, `generate:gitignore`, `generate:test_template`, `generate:pages_ci`, `generate:ci_workflow`, `generate:lint_workflow`, `generate:dns_records`, `generate:wizard_ci`, `generate:key` |
| `git` | `git:commit`, `git:push`, `git:pull`, `git:stash`, `git:stash-pop`, `git:merge-abort`, `git:checkout-file`, `git:gc`, `git:history-reset`, `git:filter-repo` |
| `install` | `install:packages`, `install:packages_update`, `install:docker_pull`, `install:helm` |
| `plan` | `plan:terraform`, `plan:helm_template` |
| `restore` | `restore:backup`, `restore:backup_import`, `restore:vault` |
| `scan` | `scan:dismiss_finding`, `scan:undismiss_finding` |
| `setup` | `setup:vault_lock`, `setup:vault_unlock`, `setup:vault_register`, `setup:vault`, `setup:encrypt`, `setup:decrypt`, `setup:terraform`, `setup:terraform_ws`, `setup:git_remote`, `setup:git_remote_rename`, `setup:git_remote_url`, `setup:gh_logout`, `setup:gh_login`, `setup:gh_device_flow`, `setup:gh_repo`, `setup:gh_visibility`, `setup:gh_default_branch`, `setup:gh_repo_rename`, `setup:pages`, `setup:encrypt_backup`, `setup:decrypt_backup`, `setup:backup_rename`, `setup:backup_special`, `setup:gh_environment`, `setup:env_seed`, `setup:secret_set`, `setup:devops_prefs`, `setup:integration_prefs`, `setup:wizard`, `setup:config_save` |
| `test` | `test:run`, `test:coverage`, `test:docker_exec`, `test:quality` |
| `validate` | `validate:quality`, `validate:lint`, `validate:typecheck`, `validate:terraform`, `validate:wizard` |
| `ci` | `ci:gh_dispatch` |
