# Phase 5B: Backup + Content Crypto — Sub-Phase Analysis

> **Created**: 2026-02-15
> **Status**: Analysis → Implementation
> **Plan scope**: backup_archive.py, backup_restore.py, backup_ops.py (22 audit), content_crypto.py (4 audit)

---

## 1. Route-by-Route Analysis

### routes_backup_restore.py (133 lines) — ✅ ALREADY THIN

| Function | Thin? | Notes |
|---|:---:|---|
| `api_restore()` | ✅ | Delegates to `backup_ops.restore_backup()` |
| `api_import()` | ✅ | Delegates to `backup_ops.import_backup()` |
| `api_wipe()` | ✅ | Delegates to `backup_ops.wipe_folder()` |
| `api_delete()` | ⚠️ | Has `.backup` path check + inline `cleanup_release_sidecar()` call |

**`api_delete` issue**: Imports `content_release.cleanup_release_sidecar` and calls it inline before `backup_ops.delete_backup`. This is business logic orchestration in the route. The core `delete_backup` function should handle release cleanup internally.

### routes_backup_archive.py (186 lines) — 1 FAT function

| Function | Thin? | Notes |
|---|:---:|---|
| `api_export()` | ✅ | Delegates to `backup_ops.create_backup()` |
| `api_list()` | ✅ | Delegates to `backup_ops.list_backups()` |
| `api_preview()` | ✅ | Delegates to `backup_ops.preview_backup()` |
| `api_download()` | ✅ | Path security + send_file (HTTP concern, correct in route) |
| `api_upload()` | ❌ FAT | 65 lines of business logic: safe name generation, file saving, manifest validation, `record_event` |

**`api_upload` issues**:
1. Generates safe filename (business logic)
2. Reads manifest and validates (business logic)
3. Calls `record_event` directly
4. All of this should be a core function like `backup_archive.upload_backup(root, file_data, target_folder, filename)`

### routes_backup_ops.py (245 lines) — 3 FAT functions

| Function | Thin? | Notes |
|---|:---:|---|
| `api_upload_release()` | ❌ FAT | Path resolution, metadata JSON writing, release upload + `record_event` × 2 |
| `api_encrypt_backup()` | ✅ | Delegates to `backup_ops.encrypt_backup_inplace()` |
| `api_decrypt_backup()` | ✅ | Delegates to `backup_ops.decrypt_backup_inplace()` |
| `api_delete_release()` | ❌ FAT | Reads metadata JSON, calls `delete_release_asset`, cleans up, `record_event` × 2 |
| `api_rename_backup()` | ⚠️ | Inline regex sanitization + extension logic before calling `backup_ops.rename_backup` |
| `api_mark_special()` | ✅ | Delegates to `backup_ops.mark_special()` |

**`api_upload_release` issues**: Business logic for release artifact upload (metadata writing, file_id generation). Should be a core function.
**`api_delete_release` issues**: Reads release metadata JSON, orchestrates deletion + cleanup. Should be a core function.
**`api_rename_backup` issue**: Regex filename sanitization + extension handling is business logic.

### routes_content.py encrypt/decrypt (lines 263-449) — 2 FAT functions

| Function | Thin? | Notes |
|---|:---:|---|
| `content_folders()` | ✅ | Delegates to `detect_content_folders()` + minor enrichment |
| `content_all_folders()` | ⚠️ | Inline directory scanning with `_EXCLUDED_DIRS` filter |
| `content_list()` | ⚠️ | Imports `content_release.list_release_assets` + inline summary computation |
| `content_encrypt()` | ❌ FAT | 90 lines: encrypt + delete original + release update + metadata JSON + `record_event` × 2 |
| `content_decrypt()` | ❌ FAT | 90 lines: decrypt + delete encrypted + release update + metadata JSON + `record_event` × 2 |
| `content_metadata()` | ✅ | Delegates to `read_metadata()` |

**`content_encrypt` issues**: After calling `encrypt_file()`, the route:
1. Deletes the original file (business logic)
2. Handles `.large/` release artifact updates (imports content_release, writes JSON metadata)
3. Records audit event
All of this should be inside a core function.

**`content_decrypt` issues**: Same pattern as encrypt.

---

## 2. What Needs to Move to Core

### New core functions needed (in existing modules):

#### In `backup_archive.py`:
- `upload_backup(root, file_bytes, filename, target_folder) → dict`
  - Generate safe name, save file, validate manifest, audit
  - Currently inline in `api_upload()`

#### In `backup_extras.py`:
- `upload_backup_to_release(root, backup_path) → dict`
  - Path resolution, file_id generation, metadata writing, bg upload, audit
  - Currently inline in `api_upload_release()`
- `delete_backup_release(root, backup_path) → dict`
  - Read metadata, delete asset, cleanup metadata, audit
  - Currently inline in `api_delete_release()`

#### In `backup_archive.py` or `backup_common.py`:
- `sanitize_backup_name(name, is_encrypted) → str`
  - Regex sanitization + extension handling
  - Currently inline in `api_rename_backup()`

#### In `backup_restore.py` (modify existing):
- `delete_backup()` should call `cleanup_release_sidecar` internally
  - Currently the route imports and calls it separately

#### In `content_crypto.py`:
- `encrypt_content_file(root, rel_path, passphrase, *, delete_original=False) → dict`
  - Encrypt file, optionally delete original, handle release update, audit
  - Currently inline in `content_encrypt()` route
- `decrypt_content_file(root, rel_path, passphrase, *, delete_encrypted=False) → dict`
  - Decrypt file, optionally delete encrypted, handle release update, audit
  - Currently inline in `content_decrypt()` route

#### In `content_crypto.py` (minor):
- `list_all_project_dirs(root) → list[dict]`
  - Move `_EXCLUDED_DIRS` and directory scanning from route
  - Currently inline in `content_all_folders()` route

---

## 3. Implementation Plan

### Step 1: Content crypto (highest priority — biggest fat)
1. Create `encrypt_content_file()` and `decrypt_content_file()` in `content_crypto.py`
2. Move all business logic from `content_encrypt()` and `content_decrypt()` routes
3. Add `_audit` helper to `content_crypto.py`
4. Reduce routes to thin wrappers

### Step 2: Backup archive upload
1. Create `upload_backup()` in `backup_archive.py`
2. Move business logic from `api_upload()` route
3. Remove `record_event` from route

### Step 3: Backup release operations
1. Create `upload_backup_to_release()` and `delete_backup_release()` in `backup_extras.py`
2. Move business logic from `api_upload_release()` and `api_delete_release()` routes
3. Remove `record_event` from routes

### Step 4: Minor fixes
1. Move filename sanitization to core (`sanitize_backup_name`)
2. Fix `delete_backup` to handle release cleanup internally
3. Move `list_all_project_dirs` to core
4. Add `_audit` to `backup_ops.py` (re-export hub) if needed

### Step 5: Verify
- All route functions are thin (parse → call → respond)
- No `record_event` in any backup or content route
- No inline business logic
- Compilation passes
