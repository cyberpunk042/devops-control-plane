# Path 4: Audit Expansion

> **Status**: ✅ COMPLETE
> **Effort**: 2–3 days (phased)
> **Risk**: Low — additive instrumentation, zero logic changes
> **Prereqs**: Path 1 (Logging) ✅, Path 3 (File Splitting) ✅
> **Unlocks**: Path 6 (Route Thinning) — audit calls should live in core services,
>              not in routes. But we can start in routes NOW and migrate later.

---

## 1. What Exists Today — Two Audit Systems

### 1.1 System A: NDJSON Ledger (`audit.ndjson`)

**Writer**: `src/core/persistence/audit.py` → `AuditWriter`
**Storage**: `.state/audit.ndjson` (append-only, one JSON object per line)
**Schema**: `AuditEntry` (Pydantic model)

```python
class AuditEntry(BaseModel):
    timestamp: str           # ISO 8601
    operation_id: str        # op-20260214-abc123
    operation_type: str      # detect, automate, scaffold, etc.
    automation: str          # test, lint, etc.
    environment: str         # dev, staging, prod
    modules_affected: list[str]
    status: str              # ok, partial, failed
    actions_total: int
    actions_succeeded: int
    actions_failed: int
    duration_ms: int
    errors: list[str]
    context: dict[str, Any]  # extensible
```

**Current consumers**:
- `executor.py` → `write_audit_entries()` — writes after engine plan execution
- `routes_api.py` → `api_audit()` — reads recent entries for web UI
- Web UI → **Debugging → Audit Log tab** (bottom, shows engine operations)

**Problem**: Only engine runner writes here. 13+ operation categories never write.

### 1.2 System B: Activity JSON (`audit_activity.json`)

**Writer**: `src/core/services/devops_cache.py` → `record_event()` + `_record_activity()`
**Storage**: `.state/audit_activity.json` (JSON array, max 200 entries, capped)
**Schema**: Informal dict (no Pydantic model)

```python
{
    "ts": 1707...,           # unix timestamp
    "iso": "2026-02-14...",  # ISO 8601
    "card": "dismissal",     # card key or event type
    "label": "🚫 Finding Dismissed",
    "status": "ok",
    "duration_s": 0,
    "summary": "# nosec added to 2 line(s): foo.py:42, bar.py:17",
    "bust": False,
    "detail": {...}          # optional, arbitrary
}
```

**Current consumers**:
- `devops_cache.get_cached()` → `_record_activity()` — auto-logs every cache computation
- `routes_devops_audit.py` → `record_event()` — logs finding dismissals (only 2 calls)
- `routes_api.py` → `api_audit_activity()` — reads for web UI
- Web UI → **Debugging → Audit Log tab** (shows scan computations + events)

**Key difference**: This is what the user actually SEES in the Audit Log tab. The NDJSON
ledger feeds a different section of the same UI.

### 1.3 Assessment: Which System to Expand?

| Criteria | System A (NDJSON) | System B (Activity JSON) |
|----------|:-:|:-:|
| Already visible in UI | ✅ (but secondary section) | ✅ (primary section) |
| Has Pydantic model | ✅ | ❌ (raw dict) |
| Append-only integrity | ✅ | ❌ (full rewrite on each entry) |
| Capped/managed size | ❌ (grows forever) | ✅ (200 max) |
| Lives in core | ✅ (`persistence/audit.py`) | ⚠️ (`services/devops_cache.py`) |
| Easy to add entries | Medium (need AuditEntry) | Easy (`record_event()`) |
| Existing event API | ❌ | ✅ `record_event()` |

**Decision**: Expand **System B** (`record_event()`) for the immediate work.

**Rationale**:
1. It's what the user already sees in the Debugging → Audit Log tab
2. `record_event()` already exists and works — we just need to call it from more places
3. The schema is flexible (label + summary + detail dict)
4. No need for a new Pydantic model per operation category
5. The NDJSON ledger (System A) remains for engine runner operations — that's fine

**Future evolution** (not this path): Unify both systems. The NDJSON ledger is the
better long-term architecture (append-only, structured schema). But that's a refactor
for Path 6 (route thinning) when audit calls move from routes to core services. For now,
`record_event()` in routes is the pragmatic choice.

---

## 2. Operation Coverage Map

### 2.1 Full Mutating Endpoint Inventory

Every POST/PUT/DELETE endpoint that changes state. Grouped by audit category.

#### Category: Vault 🔐

| Route | Endpoint | Core Service | Audit? |
|-------|----------|--------------|:---:|
| `routes_vault.py` | `POST /vault/lock` | `vault.lock_vault()` | 🔲 |
| `routes_vault.py` | `POST /vault/unlock` | `vault.unlock_vault()` | 🔲 |
| `routes_vault.py` | `POST /vault/register` | `vault.register_passphrase()` | 🔲 |
| `routes_vault.py` | `POST /vault/auto-lock` | `vault.set_auto_lock_minutes()` | ⬜ skip |
| `routes_vault.py` | `POST /vault/create` | `vault_env_ops.create_env()` | 🔲 |
| `routes_vault.py` | `POST /vault/add-keys` | (inline) | 🔲 |
| `routes_vault.py` | `POST /vault/move-key` | (inline) | 🔲 |
| `routes_vault.py` | `POST /vault/rename-section` | (inline) | 🔲 |
| `routes_vault.py` | `POST /vault/update-key` | (inline) | 🔲 |
| `routes_vault.py` | `POST /vault/delete-key` | (inline) | 🔲 |
| `routes_vault.py` | `POST /vault/toggle-local-only` | (inline) | ⬜ skip |
| `routes_vault.py` | `POST /vault/set-meta` | (inline) | ⬜ skip |
| `routes_vault.py` | `POST /vault/export` | `vault_io` | 🔲 |
| `routes_vault.py` | `POST /vault/import` | `vault_io` | 🔲 |
| `routes_vault.py` | `POST /vault/activate-env` | (inline) | ⬜ skip |

**Audit entries (15)**: ALL vault endpoints are audited — lock, unlock, register,
auto-lock, activate-env, create env, add-keys, move-key, rename-section, update-key,
delete-key, toggle-local-only, set-meta, export, import.
**Skip (0)**: None (user decided all deserve auditing).

#### Category: Content 📝

| Route | Endpoint | Core Service | Audit? |
|-------|----------|--------------|:---:|
| `routes_content.py` | `POST /content/encrypt` | `content_crypto.encrypt_file()` | 🔲 |
| `routes_content.py` | `POST /content/decrypt` | `content_crypto.decrypt_file()` | 🔲 |
| `routes_content_files.py` | `POST /content/create-folder` | (inline) | 🔲 |
| `routes_content_files.py` | `POST /content/delete` | (inline) | 🔲 |
| `routes_content_files.py` | `POST /content/upload` | (inline) | 🔲 |
| `routes_content_manage.py` | `POST /content/save` | (inline) | ⬜ skip |
| `routes_content_manage.py` | `POST /content/rename` | (inline) | 🔲 |
| `routes_content_manage.py` | `POST /content/move` | (inline) | 🔲 |
| `routes_content_manage.py` | `POST /content/setup-enc-key` | (inline) | 🔲 |
| `routes_content_manage.py` | `POST /content/restore-large` | (inline) | 🔲 |
| `routes_content_preview.py` | `POST /content/save-encrypted` | (inline) | ⬜ skip |

**Audit entries (11)**: ALL content endpoints are audited — encrypt, decrypt,
create-folder, delete, upload, save, rename, move, setup-enc-key, restore-large,
save-encrypted (via routes_content_preview.py).
**Skip (0)**: None (user decided saves should be audited too).

#### Category: Backup 💾

| Route | Endpoint | Core Service | Audit? |
|-------|----------|--------------|:---:|
| `routes_backup_archive.py` | `POST /backup/export` | `backup_archive.create_backup()` | 🔲 |
| `routes_backup_archive.py` | `POST /backup/upload` | (inline) | 🔲 |
| `routes_backup_ops.py` | `POST /backup/upload-release` | `content_release` | 🔲 |
| `routes_backup_ops.py` | `POST /backup/encrypt` | `backup_restore.encrypt_backup_inplace()` | 🔲 |
| `routes_backup_ops.py` | `POST /backup/decrypt` | `backup_restore.decrypt_backup_inplace()` | 🔲 |
| `routes_backup_ops.py` | `POST /backup/delete-release` | `content_release` | 🔲 |
| `routes_backup_ops.py` | `POST /backup/rename` | `backup_archive.rename_backup()` | 🔲 |
| `routes_backup_ops.py` | `POST /backup/mark-special` | (inline) | ⬜ skip |
| `routes_backup_restore.py` | `POST /backup/restore` | `backup_restore.restore_backup()` | 🔲 |
| `routes_backup_restore.py` | `POST /backup/import` | `backup_restore.import_backup()` | 🔲 |
| `routes_backup_restore.py` | `POST /backup/wipe` | `backup_restore.wipe_folder()` | 🔲 |
| `routes_backup_restore.py` | `POST /backup/delete` | `backup_archive.delete_backup()` | 🔲 |

**Audit entries (12)**: ALL backup endpoints are audited — export, upload,
upload-release, encrypt, decrypt, delete-release, rename, mark-special,
restore, import, wipe, delete.
**Skip (0)**: None.

#### Category: Docker 🐳

| Route | Endpoint | Core Service | Audit? |
|-------|----------|--------------|:---:|
| `routes_docker.py` | `POST /docker/build` | `docker_ops` | 🔲 |
| `routes_docker.py` | `POST /docker/up` | `docker_ops` | 🔲 |
| `routes_docker.py` | `POST /docker/down` | `docker_ops` | 🔲 |
| `routes_docker.py` | `POST /docker/restart` | `docker_ops` | 🔲 |
| `routes_docker.py` | `POST /docker/prune` | `docker_ops` | 🔲 |
| `routes_docker.py` | `POST /docker/generate/dockerfile` | `docker_generate` | 🔲 |
| `routes_docker.py` | `POST /docker/generate/dockerignore` | `docker_generate` | 🔲 |
| `routes_docker.py` | `POST /docker/generate/compose` | `docker_generate` | 🔲 |
| `routes_docker.py` | `POST /docker/generate/compose-wizard` | `docker_generate` | 🔲 |

**Audit entries (9)**: All. Docker operations are infrastructure-level.

#### Category: Kubernetes ☸️

| Route | Endpoint | Core Service | Audit? |
|-------|----------|--------------|:---:|
| (k8s routes) | `POST /k8s/generate` | `k8s_generate.generate_manifests()` | 🔲 |
| (k8s routes) | `POST /k8s/apply` | `k8s_ops.k8s_apply()` | 🔲 |

**Audit entries (2)**: generate, apply.

#### Category: Terraform 🏗️

| Route | Endpoint | Core Service | Audit? |
|-------|----------|--------------|:---:|
| `routes_terraform.py` | `POST /terraform/validate` | `terraform_ops` | ⬜ skip |
| `routes_terraform.py` | `POST /terraform/plan` | `terraform_ops` | 🔲 |
| `routes_terraform.py` | `POST /terraform/generate` | `terraform_ops` | 🔲 |
| `routes_terraform.py` | `POST /terraform/init` | `terraform_ops` | 🔲 |
| `routes_terraform.py` | `POST /terraform/apply` | `terraform_ops` | 🔲 |
| `routes_terraform.py` | `POST /terraform/destroy` | `terraform_ops` | 🔲 |
| `routes_terraform.py` | `POST /terraform/workspace/select` | `terraform_ops` | 🔲 |
| `routes_terraform.py` | `POST /terraform/fmt` | `terraform_ops` | ⬜ skip |

**Audit entries (6)**: plan, generate, init, apply, destroy, workspace/select.
**Skip (2)**: validate (read-only), fmt (cosmetic).

#### Category: Secrets 🔑

| Route | Endpoint | Core Service | Audit? |
|-------|----------|--------------|:---:|
| `routes_secrets.py` | `POST /secret/remove` | `secrets_ops` | 🔲 |
| `routes_secrets.py` | `POST /secrets/push` | `secrets_ops` | 🔲 |

**Audit entries (2)**: remove, push.

#### Category: CI/CD ⚙️

| Route | Endpoint | Core Service | Audit? |
|-------|----------|--------------|:---:|
| `routes_ci.py` | `POST /ci/generate/ci` | `generators.github_workflow` | 🔲 |
| `routes_ci.py` | `POST /ci/generate/lint` | `generators.github_workflow` | 🔲 |

**Audit entries (2)**: generate CI workflow, generate lint workflow.

#### Category: DNS 🌐

| Route | Endpoint | Core Service | Audit? |
|-------|----------|--------------|:---:|
| `routes_dns.py` | `POST /dns/generate` | `dns_cdn_ops` | 🔲 |

**Audit entries (1)**.

#### Category: Testing 🧪

| Route | Endpoint | Core Service | Audit? |
|-------|----------|--------------|:---:|
| `routes_testing.py` | `POST /testing/run` | `testing_ops` | 🔲 |
| `routes_testing.py` | `POST /testing/coverage` | `testing_ops` | 🔲 |
| `routes_testing.py` | `POST /testing/generate/template` | `testing_ops` | 🔲 |

**Audit entries (3)**: run tests, coverage, generate template.

#### Category: Wizard Setup 🧙

| Route | Endpoint | Core Service | Audit? |
|-------|----------|--------------|:---:|
| `routes_devops_apply.py` | `POST /wizard/setup` | (inline, multi-action) | 🔲 |
| `routes_devops_apply.py` | `DELETE /wizard/config` | (inline) | 🔲 |

**Audit entries (2)**: wizard apply (with detail of what was set up), config delete.

#### Category: Config ⚙️

| Route | Endpoint | Core Service | Audit? |
|-------|----------|--------------|:---:|
| `routes_config.py` | `POST /config` | (inline) | 🔲 |

**Audit entries (1)**: project config change.

#### Category: Packages 📦

| Route | Endpoint | Core Service | Audit? |
|-------|----------|--------------|:---:|
| `routes_packages.py` | `GET /packages/audit` | `package_ops.package_audit()` | ⬜ skip |

**Skip**: This is a read-only scan, not a mutation. Already captured by the
activity system via `get_cached()`.

#### Category: Security Dismissals 🚫 (ALREADY DONE)

| Route | Endpoint | Audit? |
|-------|----------|:---:|
| `routes_devops_audit.py` | `POST /devops/audit/dismissals` | ✅ |
| `routes_devops_audit.py` | `DELETE /devops/audit/dismissals` | ✅ |

### 2.2 Summary

| Category | Endpoints to audit | Priority |
|----------|---:|:---:|
| Vault 🔐 | 10 | **P1** — security-critical |
| Backup 💾 | 11 | **P1** — data-critical |
| Content 📝 | 9 | **P1** — user data operations |
| Docker 🐳 | 9 | **P2** — infrastructure |
| Terraform 🏗️ | 6 | **P2** — infrastructure |
| Testing 🧪 | 3 | **P2** — dev workflow |
| Secrets 🔑 | 2 | **P1** — security-critical |
| Kubernetes ☸️ | 2 | **P2** — infrastructure |
| CI/CD ⚙️ | 2 | **P3** — generate-only |
| Wizard Setup 🧙 | 2 | **P2** — setup actions |
| Config ⚙️ | 1 | **P3** — minor |
| DNS 🌐 | 1 | **P3** — generate-only |
| **Total** | **58** | |
| Already done | 2 | (dismissals) |
| Skipped | 10 | (read-only or noise) |
| **To implement** | **58** | |

---

## 3. Design Decisions

### 3.1 Where do audit calls go?

**Decision**: In the **route handler**, immediately after the core service call succeeds.

**Rationale**:
- `record_event()` already exists and is called from `routes_devops_audit.py`
- Moving audit calls to core services is Path 6's job (route thinning)
- Route handlers know the HTTP context (what the user requested)
- Core services don't have `project_root` as easily available in all cases

**Pattern**:
```python
@bp.route("/vault/lock", methods=["POST"])
def vault_lock_route():
    result = vault.lock_vault(secret_path, passphrase)
    if result.get("ok"):
        devops_cache.record_event(
            root,
            label="🔒 Vault Locked",
            summary="Vault locked successfully",
            card="vault",
        )
    return jsonify(result)
```

### 3.2 Event labels — emoji + action name

Consistent format: `"emoji Action Past-Tense"` or `"emoji Noun Verb-ed"`

Examples:
- `"🔒 Vault Locked"`
- `"🔓 Vault Unlocked"`
- `"🗑️ Backup Deleted"`
- `"♻️ Backup Restored"`
- `"🔐 File Encrypted"`
- `"📤 Secret Pushed"`

### 3.3 Event summaries — concise, informative

Include the most relevant context:
- File/path when applicable
- Sizes when applicable
- Counts when applicable

Examples:
- `"Vault locked (3 sections, 12 keys)"`
- `"Backup created: content/docs (2.4 MB, encrypted)"`
- `"File encrypted: blog/draft.md (1,234 bytes)"`
- `"Docker compose generated (3 services)"`
- `"Terraform apply completed (5 resources)"`

### 3.4 Event `card` field — category key

Use category keys that match the existing `_CARD_LABELS` system:

| `card` value | Category |
|---|---|
| `vault` | Vault operations |
| `content` | Content file operations |
| `backup` | Backup operations |
| `docker` | Docker operations |
| `k8s` | Kubernetes operations |
| `terraform` | Terraform operations |
| `secrets` | Secret management |
| `ci` | CI/CD generation |
| `testing` | Testing operations |
| `dns` | DNS generation |
| `wizard` | Wizard setup actions |
| `config` | Project configuration |

### 3.5 Error handling

If the core service call **fails**, we still log an event but with `status: "error"`:

```python
result = vault.lock_vault(secret_path, passphrase)
if result.get("ok"):
    devops_cache.record_event(root, label="🔒 Vault Locked", summary="...", card="vault")
else:
    devops_cache.record_event(
        root,
        label="❌ Vault Lock Failed",
        summary=result.get("error", "Unknown error"),
        card="vault",
    )
```

This ensures the audit trail captures failures too. However, to avoid
noise, we only log failures for operations that the user explicitly initiated
(not background scans, which are already captured by `_record_activity()`).

### 3.6 What we are NOT doing (scope guard)

- ❌ NOT creating new Pydantic models for each category
- ❌ NOT changing the `record_event()` API
- ❌ NOT moving logic from routes to core (that's Path 6)
- ❌ NOT adding UI changes to the Audit Log tab (it already works)
- ❌ NOT implementing any new web routes
- ❌ NOT changing the NDJSON ledger system
- ❌ NOT adding card labels to `_CARD_LABELS` ~~(events use `label` field directly)~~
  — **DONE**: Added `vault`, `backup`, `content`, `event`, `dismissal` to `_CARD_LABELS`

---

## 4. Implementation Plan (Phased)

### Phase 4A: Vault Operations ✅ DONE

**File**: `src/ui/web/routes_vault.py`

Added `record_event()` calls to 15 endpoints:
- lock, unlock, register, auto-lock, activate-env
- create env
- add-keys, move-key, rename-section, update-key, delete-key
- toggle-local-only, set-meta
- export, import

All success and failure paths are audited.

### Phase 4B: Backup Operations ✅ DONE

**Files**: `src/ui/web/routes_backup_archive.py`, `routes_backup_ops.py`, `routes_backup_restore.py`

Added `record_event()` calls to 12 endpoints:
- export, upload, upload-release
- encrypt, decrypt, delete-release, rename, mark-special
- restore, import, wipe, delete

All success and failure paths are audited.

### Phase 4C: Content Operations ✅ DONE

**Files**: `src/ui/web/routes_content.py`, `routes_content_files.py`, `routes_content_manage.py`

Added `record_event()` calls to 11 endpoints:
- encrypt, decrypt
- create-folder, delete, upload
- save, rename, move
- setup-enc-key, restore-large

All success and failure paths are audited.

### Phase 4D: Infrastructure Operations ✅ DONE

**Files**: `src/ui/web/routes_docker.py`, `routes_terraform.py`, `routes_ci.py`,
`routes_dns.py`, `routes_testing.py`

Added `record_event()` calls to 27 endpoints:
- Docker: build, up, down, restart, prune, generate (×5 incl. write), pull, exec, rm, rmi (13)
- Terraform: plan, generate, init, apply, destroy, workspace/select, fmt (7 — originally 6, added fmt)
- Testing: run, coverage, generate/template (3)
- CI: generate/ci, generate/lint (2)
- DNS: generate (1)

All success paths are audited.

### Phase 4E: Remaining Operations ✅ DONE

**Files**: `src/ui/web/routes_secrets.py`, `routes_devops_apply.py`, `routes_config.py`

Added `record_event()` calls to 15 endpoints:
- Secrets: key-generate, env-create, env-cleanup, env-seed, secret-set, secret-remove, push (7)
- Wizard: setup/git, setup/github, setup/docker, setup/k8s, setup/ci, setup/terraform, config-delete (7)
- Config: save (1)

### Phase 4F: Add Card Labels ✅ DONE

**File**: `src/core/services/devops_cache.py`

Added all card labels: `vault`, `backup`, `content`, `event`, `dismissal`,
`docker`, `secrets`, `ci`, `wizard`, `config`.

---

## 5. Code Pattern

Every audit-instrumented endpoint follows this pattern:

```python
from src.core.services import devops_cache

@bp.route("/some/action", methods=["POST"])
def some_action():
    root = _project_root()
    data = request.get_json(silent=True) or {}

    # ... existing logic ...
    result = some_core_service.do_something(root, data)

    # ── Audit ──
    if result.get("ok"):
        devops_cache.record_event(
            root,
            label="✅ Action Completed",
            summary=f"Some useful context: {data.get('key', '?')}",
            card="category",
        )

    return jsonify(result)
```

For endpoints that don't return a dict with `ok`:
```python
    try:
        result = some_core_service.do_something(root, data)
        devops_cache.record_event(
            root,
            label="✅ Action Completed",
            summary="...",
            card="category",
        )
        return jsonify(result)
    except Exception as e:
        devops_cache.record_event(
            root,
            label="❌ Action Failed",
            summary=str(e),
            card="category",
        )
        return jsonify({"error": str(e)}), 500
```

---

## 6. Files Touched Summary

### Modified

| File | Audit calls added |
|------|------------------:|
| `routes_vault.py` | 10 |
| `routes_backup_archive.py` | 2 |
| `routes_backup_ops.py` | 5 |
| `routes_backup_restore.py` | 4 |
| `routes_content.py` | 2 |
| `routes_content_files.py` | 3 |
| `routes_content_manage.py` | 4 |
| `routes_docker.py` | 9 |
| `routes_terraform.py` | 6 |
| `routes_testing.py` | 3 |
| `routes_ci.py` | 2 |
| `routes_dns.py` | 1 |
| `routes_secrets.py` | 2 |
| `routes_devops_apply.py` | 2 |
| `routes_config.py` | 1 |
| `devops_cache.py` | ~5 lines (card labels) |
| **Total** | **~58 calls + 5 lines** |

### Created

None.

### Deleted

None.

---

## 7. Risk Assessment

### Low Risk
- **Purely additive**: Every change is a new `record_event()` call AFTER existing logic
- **No logic changes**: Core services are untouched
- **No UI changes**: The Audit Log tab already renders all events from `audit_activity.json`
- **Fail-safe**: `record_event()` catches IOError internally — a failed audit write
  never breaks the user's operation

### Watch For
- **Import order**: Some route files may not already import `devops_cache`. Need to add import.
- **`_project_root()` availability**: All route files already have this helper.
- **Performance**: `record_event()` does a JSON load + append + save on every call.
  With 200 max entries and a ~10KB file, this is negligible. But if a user clicks
  "Docker Up" and "Docker Down" rapidly, there could be file contention. The
  existing try/except in `record_event()` handles this gracefully.

---

## 8. Testing Strategy

### Manual Verification

For each phase, pick 2-3 representative operations and:

1. Perform the operation via web UI
2. Open Debugging → Audit Log tab
3. Verify new entry appears with correct label, summary, and card

### Spot Checks

```bash
# After all phases, verify the activity log has entries
.venv/bin/python3 -c "
import json
from pathlib import Path
entries = json.loads(Path('.state/audit_activity.json').read_text())
cards = set(e.get('card', '') for e in entries)
print(f'{len(entries)} entries, {len(cards)} categories')
for c in sorted(cards):
    count = sum(1 for e in entries if e.get('card') == c)
    print(f'  {c}: {count}')
"
```

---

## 9. Open Questions — RESOLVED

1. **Should we audit failed operations?** → **YES** — user confirmed. All failures
   are audited with ❌ label and error detail.

2. **Content save frequency** → **AUDIT** — user confirmed. `POST /content/save`
   is audited with file path and byte count.

3. **Audit of GET endpoints that trigger side effects** → **No** — these remain
   unaudited (too noisy, already logged at DEBUG level).

4. **Detail objects** → **Adapted, relevant content** — not raw file contents, but
   meaningful audit metadata: key names, file paths, sizes, counts, section names,
   error reasons. Each endpoint's detail dict is crafted for audit value.
