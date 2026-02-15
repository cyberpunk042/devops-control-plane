# Audit Enrichment Plan

## Problem

Every `record_event()` call currently logs a flat notification:
```
💾 File Saved — docs/ADAPTERS.md saved (6,161 bytes)
```

This is an **activity feed**, not an **audit trail**. A proper audit captures
**what changed** — before vs. after state, diffs, counts, etc.

---

## Principle

Every audit entry should answer:
- **What action?** — created / modified / deleted / renamed / encrypted / etc.
- **What target?** — file path, secret name, env name, container, etc.
- **What was the state before?** — lines, size, hash, existence, value
- **What is the state after?** — lines, size, hash, new value
- **What changed?** — diff stats (lines added/removed), size delta

Not every category needs the same depth. Files need diffs. Docker commands
need stdout. Vault operations need key counts. But every entry must be
**meaningful**, not just "something happened."

---

## Current Inventory: 90+ `record_event()` calls across 15 route files

### Category 1: Content File Operations (highest audit value)
**Files:** `routes_content_manage.py`, `routes_content_files.py`, `routes_content.py`

| Current Label | Action | Before/After Data Needed |
|---|---|---|
| 💾 File Saved | `modified` | Before: line count, size, sha256. After: same. Diff: lines +/- |
| 📁 Folder Created | `created` | After: folder name |
| 🗑️ File/Dir Deleted | `deleted` | Before: size, line count (if file), child count (if dir) |
| 📤 File Uploaded | `created` | After: filename, size, type |
| 📝 File Created (new) | `created` | After: line count, size |
| ✏️ File Renamed | `renamed` | Before: old name. After: new name |
| 📂 File Moved | `moved` | Before: old path. After: new path |
| 🔐 File Encrypted | `encrypted` | Before: size. After: encrypted size |
| 🔓 File Decrypted | `decrypted` | Before: encrypted size. After: decrypted size |

**Implementation for "File Modified" (the user's example):**
```python
# BEFORE the write
old_content = target.read_text(encoding="utf-8") if target.is_file() else ""
old_lines = old_content.count("\n") + (1 if old_content else 0)
old_size = len(old_content.encode("utf-8"))

# ... perform the write ...

# AFTER the write
new_lines = file_content.count("\n") + (1 if file_content else 0)
new_size = len(file_content.encode("utf-8"))

# DIFF
added = removed = 0
for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
    None, old_content.splitlines(), file_content.splitlines()
).get_opcodes():
    if tag == "insert":
        added += j2 - j1
    elif tag == "delete":
        removed += i2 - i1
    elif tag == "replace":
        removed += i2 - i1
        added += j2 - j1

devops_cache.record_event(
    root,
    label="📝 File Modified",
    summary=f"{rel_path}: +{added} -{removed} lines ({old_size:,} → {new_size:,} bytes)",
    detail={
        "action": "modified",
        "target": rel_path,
        "before": {"lines": old_lines, "size": old_size},
        "after":  {"lines": new_lines, "size": new_size},
        "diff":   {"lines_added": added, "lines_removed": removed},
    },
    card="content",
)
```

### Category 2: Vault / Secrets Operations
**Files:** `routes_vault.py`, `routes_secrets.py`

| Current Label | Action | Before/After Data Needed |
|---|---|---|
| 🔑 Secret Set | `set` | Key name, target (local/gh/both), value masked |
| 🗑️ Secret Removed | `deleted` | Key name, target |
| ✏️ Key Renamed | `renamed` | Old name → new name, env file |
| 🔑 Key Updated | `updated` | Key name, env file, old len → new len |
| 📂 Key Moved (section) | `moved` | Key → section, env file |
| 🔐 Env Encrypted | `encrypted` | Env file, key count, size before/after |
| 🔓 Env Decrypted | `decrypted` | Env file, key count, size before/after |
| 🔄 Active Env Switched | `switched` | From env → to env |
| ⏱️ Auto-lock Changed | `configured` | Old timeout → new timeout |
| 📥 Envelope Imported | `imported` | File, key count |
| 📤 Envelope Exported | `exported` | File, key count |
| 🌱 Env Seeded | `seeded` | Env count, key count per env |
| 🧹 Env Cleaned | `cleaned` | Env name, keys removed |
| 🌐 GitHub Env Created | `created` | Env name |
| 🚀 Secrets Pushed | `pushed` | Count, target |
| 🔑 Key Generated | `generated` | Type (password/api_key/etc.), length |
| 🏷️ Local-only Toggled | `configured` | Key, env, old state → new state |
| 📝 Metadata Updated | `updated` | Key, env, fields changed |

### Category 3: Backup Operations
**Files:** `routes_backup_ops.py`, `routes_backup_restore.py`, `routes_backup_archive.py`

| Current Label | Action | Before/After Data Needed |
|---|---|---|
| 📦 Backup Created | `created` | Archive name, file count, total size |
| 📥 Backup Imported | `imported` | Archive name, merge strategy, items added |
| 🔄 Backup Restored | `restored` | Archive name, files restored count |
| 🗑️ Backup Deleted | `deleted` | Archive name, size |
| ☠️ Content Wiped | `wiped` | Folder, item count removed |
| 🔐 Archive Encrypted | `encrypted` | Archive name, size before/after |
| 🔓 Archive Decrypted | `decrypted` | Archive name, size before/after |
| ☁️ Upload to Release | `uploaded` | Filename, size, release tag |
| 🗑️ Release Asset Deleted | `deleted` | Asset name, release tag |

### Category 4: Docker Operations
**File:** `routes_docker.py`

| Current Label | Action | Before/After Data Needed |
|---|---|---|
| 🐳 Dockerfile Generated | `generated` | Stack name, file path, lines written |
| 🐳 Compose Generated | `generated` | Module count, file path |
| 🐳 Compose Wizard Generated | `generated` | Service count, file path |
| 🐳 .dockerignore Generated | `generated` | Stack count, file path |
| 🐳 Image Pulled | `pulled` | Image name, tag |
| 🐳 Image Built | `built` | Service, no-cache flag |
| 🐳 Image Removed | `removed` | Image name, force flag |
| 🐳 Container Removed | `removed` | Container name, force flag |
| 🐳 Compose Started | `started` | Service (or all) |
| 🐳 Compose Stopped | `stopped` | Volumes removed? |
| 🐳 Compose Restarted | `restarted` | Service (or all) |
| 🐳 Command Executed | `executed` | Container, command, exit code |
| 🐳 Prune Executed | `pruned` | Space reclaimed |
| 📝 File Written | `created` | File path, size |

### Category 5: Terraform Operations
**File:** `routes_terraform.py`

| Current Label | Action | Before/After Data Needed |
|---|---|---|
| 🏗️ Scaffolding Generated | `generated` | Provider, backend, files created |
| 🏗️ Init | `initialized` | Upgrade flag, exit code |
| 🏗️ Plan | `planned` | Exit code, resources to add/change/destroy |
| 🏗️ Apply | `applied` | Resources added/changed/destroyed |
| 🏗️ Destroy | `destroyed` | Resources destroyed count |
| 🏗️ Format | `formatted` | Files changed count |
| 🏗️ Workspace Switch | `switched` | Old workspace → new workspace |

### Category 6: CI/CD Operations
**File:** `routes_ci.py`

| Current Label | Action | Before/After Data Needed |
|---|---|---|
| 🔄 CI Workflow Generated | `generated` | Stack count, file path, existed before? |
| 🔄 Lint Workflow Generated | `generated` | Stack count, file path, existed before? |

### Category 7: DevOps Apply (Setup Wizard)
**File:** `routes_devops_apply.py`

| Current Label | Action | Before/After Data Needed |
|---|---|---|
| 🔀 Git Configured | `configured` | Changes made (gitignore, hooks, etc.) |
| 🐙 GitHub Configured | `configured` | Envs created, secrets pushed |
| 🐳 Docker Configured | `configured` | Files created |
| ☸ K8s Configured | `configured` | Files created, files skipped |
| 🏗️ Terraform Configured | `configured` | Provider, backend |
| 🔄 CI Configured | `configured` | Files created |
| 🧹 Wizard Config Deleted | `deleted` | Configs deleted |

### Category 8: Testing Operations
**File:** `routes_testing.py`

| Current Label | Action | Before/After Data Needed |
|---|---|---|
| 🧪 Tests Run | `executed` | File, exit code, pass/fail counts |
| 📊 Coverage Run | `executed` | Coverage %, exit code |
| 📝 Test Template Generated | `generated` | Module name, file path |

### Category 9: DNS Operations
**File:** `routes_dns.py`

| Current Label | Action | Before/After Data Needed |
|---|---|---|
| 🌐 DNS Records Generated | `generated` | Domain, record count |

### Category 10: Audit Operations
**File:** `routes_devops_audit.py`

| Current Label | Action | Before/After Data Needed |
|---|---|---|
| 🔇 Finding Dismissed | `dismissed` | File, line, count |
| 🔊 Dismissal Removed | `undismissed` | File, line |

### Category 11: Project Config
**File:** `routes_config.py`

| Current Label | Action | Before/After Data Needed |
|---|---|---|
| ⚙️ Config Saved | `modified` | Project name, fields changed |

---

## Implementation Strategy

### Phase 1: Enrich `record_event()` API ✅ DONE
Added optional structured fields to the existing function without breaking anything:
- `action` (str): the verb
- `target` (str): what was acted on  
- `before_state` (dict|None): state before
- `after_state` (dict|None): state after

### Phase 2: Enrich Content File Operations (Category 1) ✅ DONE
File save now captures line-level diffs (+/- lines), before/after sizes.
File delete captures before-state (size, lines, child count).
All 9 content call sites enriched.

### Phase 3: Enrich Vault/Secrets Operations (Category 2) ✅ DONE
15 vault calls + 7 secrets calls enriched.
Lock/unlock captures before/after locked state.
Key operations capture key names and target env file.

### Phase 4: Enrich remaining categories (3-11) ✅ DONE
- **Backup** (12 calls): archive/restore/import/wipe/encrypt/decrypt/upload/delete
- **Docker** (14 calls): build/up/down/restart/prune/generate/pull/exec/remove
- **Terraform** (7 calls): plan/init/apply/destroy/format/workspace/generate
- **CI** (2 calls): workflow/lint generation
- **Testing** (3 calls): test run/coverage/template
- **DNS** (1 call): record generation
- **DevOps Apply** (7 calls): git/github/docker/k8s/ci/terraform setup + delete
- **DevOps Audit** (2 calls): dismiss/undismiss
- **Config** (1 call): project.yml save

**Total: 80 success-path calls enriched. 12 error-path calls left as-is (by design).**

### Phase 5: Update UI rendering ✅ DONE
The Audit Log UI (`_debugging.html` → `loadDebugAuditScans`) now renders:
- **Action badge**: color-coded uppercase verb (MODIFIED, DELETED, ENCRYPTED, etc.)
- **Target path**: monospace rendering of the affected resource
- **Before → After cards**: side-by-side comparison with red/green tinted backgrounds
- Size values auto-formatted with locale separators + "B" suffix
- Raw JSON detail toggle preserved for power users

---

## Scope Consideration

This is a significant but **evolutionary** change:
- `record_event()` API is extended, not replaced
- Existing entries still work (no breaking change)
- Each route file is updated independently
- UI rendering is updated once to handle new fields

~90 call sites across 15 files. 80 enriched, 12 error-only events left as-is.
