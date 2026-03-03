# Backup Routes — Archive & Restore API

> **5 files · 495 lines · 18 endpoints · Blueprint: `backup_bp` · Prefix: `/api`**
>
> Thin HTTP wrappers over `src.core.services.backup.ops`.
> These routes power the project's backup system: folder browsing, file tree
> scanning, archive creation/listing/preview/download/upload, restore
> (overwrite and additive import), factory-reset wipe, per-archive
> encryption/decryption, GitHub Release upload/delete, rename, and
> git-tracking (mark-special). All endpoints delegate to `backup_ops` — no
> business logic in the route layer.

---

## How It Works

### Request Flow

```
Frontend (scripts/content/)
│
├── _archive.html          → /backup/list, /backup/folder-tree, /backup/folders
├── _archive_actions.html  → /backup/export, /backup/restore, /backup/import,
│                            /backup/wipe, /backup/delete, /backup/rename,
│                            /backup/encrypt, /backup/decrypt, /backup/upload-release,
│                            /backup/delete-release, /backup/mark-special
├── _archive_modals.html   → /backup/preview, /backup/tree, /backup/download,
│                            /backup/upload
│
     ▼
routes/backup/                              ← HTTP layer (this package)
├── __init__.py   — blueprint + folder-tree, folders
├── archive.py    — export, list, preview, download, upload
├── ops.py        — upload-release, encrypt, decrypt, delete-release, rename, mark-special
├── restore.py    — restore, import, wipe, delete
└── tree.py       — expandable file tree with type filters
     │
     ▼
core/services/backup/ops.py                 ← Business logic (no HTTP)
├── create_backup()          — archive creation
├── restore_backup()         — overwrite restore
├── import_backup()          — additive import
├── list_backups()           — enumerate .backup/ contents
├── preview_backup()         — peek inside archive
├── wipe_folder()            — factory reset
├── folder_tree()            — recursive directory tree
├── list_folders()           — flat folder list
├── file_tree_scan()         — type-filtered file tree
├── encrypt_backup_inplace() — encrypt .tar.gz → .tar.gz.enc
├── decrypt_backup_inplace() — decrypt .tar.gz.enc → .tar.gz
└── ...12 more functions
```

### Backup Lifecycle

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. BROWSE                                                        │
│    /folders      → flat list of scannable folders                 │
│    /folder-tree  → recursive directory tree (for selection UI)    │
│    /tree         → type-filtered file tree (within a folder)      │
├──────────────────────────────────────────────────────────────────┤
│ 2. CREATE                                                        │
│    /export       → create .tar.gz from selected paths             │
│                    options: decrypt .enc files, encrypt archive   │
│                    result stored in .backup/ subdirectory         │
├──────────────────────────────────────────────────────────────────┤
│ 3. MANAGE                                                        │
│    /list         → enumerate backups in .backup/                  │
│    /preview      → peek at file tree inside a .tar.gz             │
│    /download     → download archive file                          │
│    /upload       → upload archive into .backup/                   │
│    /rename       → rename with safety (sanitized name)            │
│    /encrypt      → encrypt .tar.gz in place → .tar.gz.enc        │
│    /decrypt      → decrypt .tar.gz.enc in place → .tar.gz        │
│    /mark-special → git add -f (bypass .gitignore for this file)   │
├──────────────────────────────────────────────────────────────────┤
│ 4. CLOUD                                                         │
│    /upload-release → push archive to GitHub Release               │
│    /delete-release → remove archive from GitHub Release           │
├──────────────────────────────────────────────────────────────────┤
│ 5. RESTORE                                                       │
│    /restore      → extract archive → OVERWRITE existing files     │
│                    options: wipe first, encrypt/decrypt restored   │
│    /import       → extract archive → ADDITIVE (skip existing)     │
│    /wipe         → factory reset folder (optional backup first)   │
│    /delete       → delete a .backup/ archive file                 │
└──────────────────────────────────────────────────────────────────┘
```

### Path Security Model

```
All path inputs
     │
     ▼
(root / path).resolve()
     │
     ├── file_path.relative_to(root)    ← rejects path traversal
     ├── ".backup" in file_path.parts   ← for delete: must be in .backup/
     └── Returns 400 if either fails
```

The `archive.py` download and `restore.py` delete endpoints manually
verify path containment. Other endpoints delegate path security to
`backup_ops` which applies its own checks.

---

## File Map

```
routes/backup/
├── __init__.py     67 lines  — blueprint + folder-tree + folders (2 routes)
├── archive.py     123 lines  — export + list + preview + download + upload (5 routes)
├── ops.py         128 lines  — upload-release, encrypt, decrypt, delete-release, rename, mark-special (6 routes)
├── restore.py     128 lines  — restore, import, wipe, delete (4 routes)
├── tree.py         49 lines  — expandable type-filtered file tree (1 route)
└── README.md                 — this file
```

---

## Per-File Documentation

### `__init__.py` — Blueprint + Folder Browsing (67 lines)

Defines `backup_bp` and hosts the two folder-level browsing endpoints.
Imports sub-modules at the end to register their routes.

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `api_folder_tree()` | GET | `/backup/folder-tree` | Recursive directory tree (max depth 10) |
| `api_folders()` | GET | `/backup/folders` | Flat list of top-level scannable folders |

**Folder tree depth control:**
```python
max_depth = min(int(request.args.get("depth", "6")), 10)  # user-controlled, capped at 10
tree = backup_ops.folder_tree(_project_root(), max_depth=max_depth)
```

**Sub-module registration (circular import guard):**
```python
# These imports MUST come after backup_bp is defined
from . import ops       # noqa: E402, F401
from . import tree      # noqa: E402, F401
from . import archive   # noqa: E402, F401
from . import restore   # noqa: E402, F401
```

### `archive.py` — Export, List, Preview, Download, Upload (123 lines)

The archive lifecycle — from creating backups to inspecting and
transferring them.

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `api_export()` | POST | `/backup/export` | Create .tar.gz from selected paths |
| `api_list()` | GET | `/backup/list` | List backups in folder's .backup/ directory |
| `api_preview()` | GET | `/backup/preview` | Preview file tree inside an archive |
| `api_download()` | GET | `/backup/download/<path:filepath>` | Download archive file |
| `api_upload()` | POST | `/backup/upload` | Upload archive into .backup/ |

**Export with encryption + decryption options:**
```python
result = backup_ops.create_backup(
    root,
    target_folder,
    paths,
    label=data.get("label", "admin_export"),
    decrypt_enc=data.get("decrypt_enc", False),       # decrypt .enc files during export
    encrypt_archive_flag=encrypt_flag,                  # encrypt the archive itself
    custom_name=data.get("custom_name", "").strip(),    # override auto-generated name
)
```

**Download security — path traversal + extension whitelist:**
```python
file_path = (root / filepath).resolve()

# Security: must be within project root
file_path.relative_to(root)  # raises ValueError if traversal attempt

# Extension whitelist
if not (file_path.name.endswith(".tar.gz") or file_path.name.endswith(".tar.gz.enc")):
    return jsonify({"error": "File not found"}), 404
```

**List with release cross-reference:**
```python
result = backup_ops.list_backups(
    _project_root(), rel_path,
    check_release=check_release,  # cross-ref with GitHub Release assets
)
```

### `ops.py` — Encryption, Release, Rename, Mark Special (128 lines)

Per-archive operations — encryption/decryption, GitHub Release
management, renaming, and git-tracking.

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `api_upload_release()` | POST | `/backup/upload-release` | Upload archive to GitHub Release |
| `api_encrypt_backup()` | POST | `/backup/encrypt` | Encrypt .tar.gz → .tar.gz.enc in place |
| `api_decrypt_backup()` | POST | `/backup/decrypt` | Decrypt .tar.gz.enc → .tar.gz in place |
| `api_delete_release()` | POST | `/backup/delete-release` | Delete archive from GitHub Release |
| `api_rename_backup()` | POST | `/backup/rename` | Rename archive with sanitization |
| `api_mark_special()` | POST | `/backup/mark-special` | `git add -f` to bypass .gitignore |

**Rename with name sanitization:**
```python
safe_name = backup_ops.sanitize_backup_name(
    new_name,
    is_encrypted=backup_path.endswith(".enc"),  # preserves .enc extension
)
result = backup_ops.rename_backup(root, backup_path, safe_name)
if "error" in result:
    code = 409 if "already exists" in result.get("error", "") else 400
```

**Upload-release path flexibility:**
```python
backup_path = (data.get("path") or data.get("backup_path", "")).strip()
# Accepts both "path" and "backup_path" keys for backward compatibility
```

**Mark-special toggle:**
```python
result = backup_ops.mark_special(root, backup_path, unmark=unmark)
# unmark=False → git add -f (bypass .gitignore, track this backup)
# unmark=True  → git rm --cached (stop tracking, respect .gitignore again)
```

### `restore.py` — Restore, Import, Wipe, Delete (128 lines)

Destructive operations — restore (overwrite), import (additive),
factory-reset wipe, and archive deletion.

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `api_restore()` | POST | `/backup/restore` | Extract archive → overwrite existing files |
| `api_import()` | POST | `/backup/import` | Extract archive → additive (skip existing) |
| `api_wipe()` | POST | `/backup/wipe` | Factory-reset folder (optional backup first) |
| `api_delete()` | POST | `/backup/delete` | Delete a .backup/ archive file |

**Restore with comprehensive options:**
```python
result = backup_ops.restore_backup(
    root, backup_path,
    paths=data.get("paths"),                        # selective restore (subset of files)
    wipe_first=data.get("wipe_first", False),       # delete target before extracting
    target_folder=target_folder,                     # override extraction target
    encrypt_restored=data.get("encrypt_restored", False),  # encrypt files after restore
    decrypt_restored=data.get("decrypt_restored", False),  # decrypt files after restore
)
```

**Wipe with safety backup:**
```python
result = backup_ops.wipe_folder(
    root, target_folder, paths,
    create_backup_first=data.get("create_backup", True),  # default: backup before wipe
)
```

**Delete security — .backup/ containment check:**
```python
file_path = (root / backup_path).resolve()
file_path.relative_to(root)               # path traversal check

if ".backup" not in file_path.parts:       # must be in a .backup/ directory
    return jsonify({"error": "Can only delete files in .backup/ directories"}), 400
```

### `tree.py` — Type-Filtered File Tree (49 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `api_tree()` | GET | `/backup/tree` | Expandable file tree filtered by type |

**Query parameters:**
```python
rel_path = request.args.get("path", "")                    # required: folder to scan
type_filter = request.args.get("types", "document,code,...") # comma-separated type list
max_depth = min(int(request.args.get("depth", "5")), 10)    # max depth, capped at 10
respect_gitignore = request.args.get("gitignore", "").lower() == "true"
```

**Supported file types:**
`document`, `code`, `script`, `config`, `data`, `image`, `video`,
`audio`, `archive`, `encrypted`, `other`

---

## Dependency Graph

```
__init__.py     ← defines backup_bp, imports all sub-modules
├── backup_ops  ← core service (eager import)
└── helpers     ← project_root (eager import)

archive.py      ← imports backup_bp from __init__
├── backup_ops  ← core service
├── flask.send_file ← for download
└── helpers     ← project_root

ops.py          ← imports backup_bp from __init__
├── backup_ops  ← core service
└── helpers     ← project_root

restore.py      ← imports backup_bp from __init__
├── backup_ops  ← core service
└── helpers     ← project_root

tree.py         ← imports backup_bp from __init__
├── backup_ops  ← core service
└── helpers     ← project_root
```

**All sub-modules share the same dependency set:** `backup_bp` +
`backup_ops` + `helpers.project_root`. The backup routes package is
the most uniform in the codebase — every handler follows the same
pattern: parse input → call `backup_ops.xxx()` → check for errors →
return JSON.

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `backup_bp`, registers at `/api` prefix |
| Frontend | `scripts/content/_archive.html` | `/list`, `/folder-tree`, `/folders`, `/tree` |
| Frontend | `scripts/content/_archive_actions.html` | `/export`, `/restore`, `/import`, `/wipe`, `/delete`, `/rename`, `/encrypt`, `/decrypt`, `/upload-release`, `/delete-release`, `/mark-special` |
| Frontend | `scripts/content/_archive_modals.html` | `/preview`, `/download`, `/upload` |

---

## Service Delegation Map

```
Route Handler            →   Core Service Function
──────────────────────────────────────────────────────────────
api_folder_tree()        →   backup_ops.folder_tree()
api_folders()            →   backup_ops.list_folders()
api_export()             →   backup_ops.create_backup()
api_list()               →   backup_ops.list_backups()
api_preview()            →   backup_ops.preview_backup()
api_download()           →   Flask send_file() (direct)
api_upload()             →   backup_ops.upload_backup()
api_upload_release()     →   backup_ops.upload_backup_to_release()
api_encrypt_backup()     →   backup_ops.encrypt_backup_inplace()
api_decrypt_backup()     →   backup_ops.decrypt_backup_inplace()
api_delete_release()     →   backup_ops.delete_backup_release()
api_rename_backup()      →   backup_ops.sanitize_backup_name() + rename_backup()
api_mark_special()       →   backup_ops.mark_special()
api_restore()            →   backup_ops.restore_backup()
api_import()             →   backup_ops.import_backup()
api_wipe()               →   backup_ops.wipe_folder()
api_delete()             →   backup_ops.delete_backup()
api_tree()               →   backup_ops.file_tree_scan()
```

---

## Data Shapes

### `/api/backup/folders` response

```json
{
    "folders": [
        {"name": "docs", "path": "docs", "has_backup": true, "backup_count": 3},
        {"name": "configs", "path": "configs", "has_backup": false, "backup_count": 0}
    ]
}
```

### `/api/backup/export` request

```json
{
    "target_folder": "docs",
    "paths": ["docs/setup.md", "docs/README.md"],
    "label": "pre-migration",
    "decrypt_enc": false,
    "encrypt_archive": true,
    "custom_name": "docs-migration-backup"
}
```

### `/api/backup/list` response

```json
{
    "path": "docs",
    "backups": [
        {
            "name": "docs-migration-backup.tar.gz",
            "path": "docs/.backup/docs-migration-backup.tar.gz",
            "size": 102400,
            "size_human": "100.0 KB",
            "created": "2026-02-17T14:30:00",
            "encrypted": false,
            "release_uploaded": false,
            "git_tracked": false
        }
    ]
}
```

### `/api/backup/preview` response

```json
{
    "name": "docs-backup.tar.gz",
    "files": [
        {"path": "setup.md", "size": 4096, "type": "document"},
        {"path": "images/diagram.png", "size": 51200, "type": "image"}
    ],
    "total_files": 12,
    "total_size": 102400,
    "total_size_human": "100.0 KB"
}
```

### `/api/backup/restore` request

```json
{
    "backup_path": "docs/.backup/docs-backup.tar.gz",
    "target_folder": "docs",
    "wipe_first": true,
    "paths": ["setup.md", "README.md"],
    "encrypt_restored": false,
    "decrypt_restored": true
}
```

### `/api/backup/tree` response

```json
{
    "path": "docs",
    "tree": [
        {
            "name": "setup.md",
            "type": "document",
            "size": 4096,
            "children": null
        },
        {
            "name": "images",
            "type": "directory",
            "children": [
                {"name": "diagram.png", "type": "image", "size": 51200}
            ]
        }
    ]
}
```

### `/api/backup/wipe` request

```json
{
    "target_folder": "configs",
    "paths": ["docker-compose.yml", "k8s/"],
    "create_backup": true
}
```

---

## Advanced Feature Showcase

### 1. Export with Dual Encryption Modes

Export supports two independent encryption operations:

```python
result = backup_ops.create_backup(
    root, target_folder, paths,
    decrypt_enc=data.get("decrypt_enc", False),       # INPUT: decrypt .enc files before archiving
    encrypt_archive_flag=encrypt_flag,                  # OUTPUT: encrypt the archive itself
)
```

- `decrypt_enc=True`: Decrypts COVAULT `.enc` files inside the archive,
  so the exported backup contains plaintext. Useful for migration to
  a system without the encryption key.
- `encrypt_archive_flag=True`: Encrypts the entire `.tar.gz` → `.tar.gz.enc`.
  Contents stay as-is, but the archive itself is encrypted.

Both can be combined: decrypt contents AND encrypt the archive.

### 2. Restore with Post-Processing

Restore offers encryption/decryption of files AFTER extraction:

```python
result = backup_ops.restore_backup(
    root, backup_path,
    encrypt_restored=data.get("encrypt_restored", False),  # encrypt files after extraction
    decrypt_restored=data.get("decrypt_restored", False),  # decrypt files after extraction
)
```

Use case: restore a plaintext backup and immediately encrypt all
files for vault usage, or restore an encrypted backup and decrypt
everything for a development environment.

### 3. Selective Restore

Both restore and export support selective paths:

```python
# Only restore specific files from the archive
result = backup_ops.restore_backup(root, backup_path, paths=["setup.md", "README.md"])

# Only export specific files into the archive
result = backup_ops.create_backup(root, folder, paths=["setup.md"])
```

### 4. Safe Wipe with Automatic Backup

Wipe defaults to creating a backup BEFORE destroying files:

```python
result = backup_ops.wipe_folder(
    root, target_folder, paths,
    create_backup_first=data.get("create_backup", True),  # default: True
)
```

The user must explicitly set `create_backup: false` to wipe without
safety net. This means accidental wipes are always recoverable.

### 5. Download Extension Whitelist

The download endpoint only serves `.tar.gz` and `.tar.gz.enc` files:

```python
if not (file_path.name.endswith(".tar.gz") or file_path.name.endswith(".tar.gz.enc")):
    return jsonify({"error": "File not found"}), 404
```

This prevents the backup download endpoint from being used to
download arbitrary project files — even if path traversal checks pass.

### 6. Delete Containment Check

Delete operations verify the target is inside a `.backup/` directory:

```python
if ".backup" not in file_path.parts:
    return jsonify({"error": "Can only delete files in .backup/ directories"}), 400
```

This prevents accidental deletion of project files through the
backup delete endpoint.

---

## Design Decisions

### Why every sub-module eagerly imports backup_ops

Unlike other route packages that use lazy imports, backup routes
import `backup_ops` at module level. This is because every single
handler in the package calls `backup_ops` — there's no conditional
path that skips it. Lazy imports would add boilerplate with zero benefit.

### Why archive.py has its own path security instead of using helpers

The download endpoint uses Flask's `send_file()` with a path from
the URL (`<path:filepath>`). Since this comes from the URL path
(not a JSON body), it needs manual security checks. The `resolve_safe_path()`
helper from `ui.web.helpers` is designed for JSON body paths and
returns `None` on failure. The archive download does `.resolve()` +
`.relative_to(root)` for the same effect with better error handling.

### Why ops.py accepts both "path" and "backup_path" keys

```python
backup_path = (data.get("path") or data.get("backup_path", "")).strip()
```

The frontend originally used `"path"`, then was updated to use
`"backup_path"` for clarity. The route accepts both for backward
compatibility without requiring a frontend migration.

### Why restore vs import are separate endpoints

Despite having similar mechanics (extract archive), they have
different semantics and different options:
- **Restore** = overwrite. Supports `wipe_first`, `paths` (selective),
  `encrypt_restored`, `decrypt_restored`, `target_folder` override.
- **Import** = additive skip. Takes only `backup_path`. Simpler
  semantics, fewer failure modes.

Merging them into one endpoint with a mode flag would make the API
harder to reason about and test.

---

## Coverage Summary

| Capability | Endpoints | File |
|-----------|-----------|------|
| Folder browsing | 2 (folder-tree, folders) | `__init__.py` |
| Archive CRUD | 5 (export, list, preview, download, upload) | `archive.py` |
| Per-archive ops | 6 (encrypt, decrypt, upload-release, delete-release, rename, mark-special) | `ops.py` |
| Restore & cleanup | 4 (restore, import, wipe, delete) | `restore.py` |
| Type-filtered tree | 1 (tree) | `tree.py` |
