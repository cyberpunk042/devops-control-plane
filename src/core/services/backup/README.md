# Backup Domain

> **6 files · 1,765 lines · Archive creation, restore, encryption, and GitHub Release sync.**
>
> Full backup lifecycle: folder scan → selective archive → optional
> encryption → list/preview/rename → restore/import/wipe →
> GitHub Release artifact management.

---

## How It Works

The backup domain is a **four-layer system** that manages the full lifecycle
of `.tar.gz` archives stored in per-folder `.backup/` directories:

```
┌──────────────────────────────────────────────────────────────────────┐
│  CREATE                                                              │
│     create_backup(root, folder, paths) → .tar.gz in .backup/        │
│     ├── File selection (paths list or all files in folder)           │
│     ├── Classification (media, doc, code, config, data)              │
│     ├── Manifest generation (backup_manifest.json inside archive)    │
│     ├── Optional: decrypt .enc files during archival                 │
│     └── Optional: encrypt archive → .tar.gz.enc (COVAULT)           │
├──────────────────────────────────────────────────────────────────────┤
│  LIST / PREVIEW                                                      │
│     list_backups(root, folder) → archive metadata + release status   │
│     preview_backup(root, path) → file tree inside archive            │
├──────────────────────────────────────────────────────────────────────┤
│  RESTORE / IMPORT                                                    │
│     restore_backup(root, path)  → OVERRIDE (replaces existing)       │
│     import_backup(root, path)   → ADDITIVE (skips existing)          │
│     wipe_folder(root, folder)   → factory reset (backup + delete)    │
├──────────────────────────────────────────────────────────────────────┤
│  IN-PLACE CRYPTO                                                     │
│     encrypt_backup_inplace(root, path) → .tar.gz → .tar.gz.enc      │
│     decrypt_backup_inplace(root, path) → .tar.gz.enc → .tar.gz      │
├──────────────────────────────────────────────────────────────────────┤
│  GIT & RELEASE                                                       │
│     mark_special(root, path) → git add -f (force-track backup)       │
│     upload_backup_to_release(root, path) → GitHub Release artifact   │
│     delete_backup_release(root, path) → remove remote artifact       │
└──────────────────────────────────────────────────────────────────────┘
```

### Archive Format

Backups are standard `.tar.gz` archives with an embedded manifest:

```
backup_20260301T120000.tar.gz
├── backup_manifest.json       ← metadata (always first member)
├── docs/readme.md
├── docs/guide.md
├── media/photo.webp
└── ...
```

The manifest is written as the **first member** of the tarball via
`tarfile.TarInfo` + `io.BytesIO`, not as a file on disk. This ensures
it's always present and always first.

### Manifest Structure (format_version 2)

Verified from `create_backup()` lines 152-165:

```python
{
    "format_version": 2,
    "created_at": "2026-03-01T12:00:00+00:00",   # datetime.now(timezone.utc).isoformat()
    "trigger": "admin_export",                     # label parameter
    "target_folder": "docs",                       # target_folder parameter
    "decrypt_enc": False,                          # whether .enc files were decrypted
    "encrypt_archive": False,                      # whether archive was encrypted
    "stats": {
        "total_files": 42,
        "total_bytes": 1048576,
        "document_count": 30,                      # dynamic keys: {classify_file()}_count
        "image_count": 10,
        "config_count": 2,
    },
    "files": [                                     # flat list of relative paths (strings)
        "docs/readme.md",
        "docs/guide.md",
    ],
}
```

### create_backup Algorithm Trace

```
create_backup(root, "docs", ["docs/readme.md", "docs/guide.md"],
              label="admin_export", decrypt_enc=False, encrypt_archive_flag=False)
│
├── Validate target_folder ≠ ""
├── Validate paths ≠ []
├── resolve_folder(root, "docs") → /project/docs  (or error)
├── If decrypt_enc or encrypt_archive_flag:
│   └── get_enc_key(root) → read CONTENT_VAULT_ENC_KEY from .env
│       └── If empty → return {"error": "CONTENT_VAULT_ENC_KEY not set..."}
│
├── Resolve all selected paths:
│   ├── For each path in paths:
│   │   ├── abs_p = (root / path).resolve()
│   │   ├── Security check: abs_p.relative_to(root)  ← path traversal guard
│   │   ├── If file → append (abs_path, rel_path) to files list
│   │   └── If directory → rglob("*") all files, skip dot-prefixed parts
│   └── If files empty → return {"error": "No files found in selection"}
│
├── backup_dir_for(folder) → create .backup/ dir if needed
├── Generate filename:
│   ├── If custom_name → sanitize with regex [^a-zA-Z0-9._-] → '_'
│   └── Else → "backup_{YYYYMMDDTHHMMSS}.tar.gz"
│
├── Count files by type:
│   └── For each file → classify_file(f) → counts[type] += 1
│
├── Build manifest dict (format_version: 2)
│
├── Create tarball:
│   ├── Write manifest as first member (TarInfo + BytesIO)
│   ├── For each file:
│   │   ├── If decrypt_enc AND file is .enc AND enc_key:
│   │   │   ├── decrypt_file_to_memory(file, key) → plain_bytes
│   │   │   ├── Strip .enc from arcname
│   │   │   └── Add decrypted bytes as TarInfo + BytesIO
│   │   │   └── On failure: log warning, add original .enc file as-is
│   │   └── Else → tar.add(file, arcname=rel_path)
│   └── Close tarball
│
├── If encrypt_archive_flag AND enc_key:
│   └── encrypt_archive(archive_path, enc_key)
│       ├── encrypt_file() → .tar.gz.enc  (COVAULT format)
│       └── Delete original .tar.gz
│
├── Audit event: "📦 Backup Created"
│   ├── before_state: source_folder, selected_files, total_size
│   └── after_state: archive name, archive size, encrypted flag, type counts
│
└── Return result dict
```

### restore_backup Algorithm Trace

```
restore_backup(root, "docs/.backup/backup_20260301T120000.tar.gz",
               wipe_first=True, target_folder="docs")
│
├── Validate backup_path ≠ ""
├── file_path = (root / backup_path).resolve()
├── Security check: file_path.relative_to(root)
├── Existence check: file_path.exists()
│
├── If encrypt_restored or decrypt_restored:
│   └── get_enc_key(root) → enc_key (or error if empty)
│
├── If archive is .enc:
│   ├── get_enc_key(root) → archive_key (or error)
│   └── decrypt_archive(file_path, archive_key) → temp tar_path
│
├── If wipe_first AND target_folder:
│   ├── resolve_folder(root, target_folder) → wipe_folder_path
│   ├── Collect files to wipe:
│   │   ├── rglob("*") all files in folder
│   │   └── Skip files whose relative parts intersect _PROTECTED_DIRS
│   │       (_PROTECTED_DIRS = .backup, .git, .github, .venv, venv,
│   │        __pycache__, node_modules, .mypy_cache, .ruff_cache, .pytest_cache)
│   │
│   ├── Create safety backup BEFORE wiping:
│   │   ├── backup_dir_for(wipe_folder_path)
│   │   ├── Name: "backup_{timestamp}_pre_wipe.tar.gz"
│   │   ├── Manifest trigger: "pre_wipe_restore"
│   │   └── Archive all to-wipe files
│   │   └── If backup fails → abort entire restore
│   │
│   ├── Delete files:
│   │   ├── _cleanup_release_sidecar(f, root) → best-effort
│   │   └── f.unlink()
│   │
│   └── Clean up empty directories (bottom-up, skip _PROTECTED_DIRS)
│
├── Extract files from archive:
│   ├── For each tar member (skip dirs, skip backup_manifest.json):
│   │   ├── If selected_paths set → skip if not in set
│   │   ├── dest = root / member.name
│   │   ├── Security check: dest.resolve().relative_to(root)
│   │   ├── Create parent dirs
│   │   ├── Extract file bytes
│   │   │
│   │   ├── If decrypt_restored AND .enc file AND enc_key:
│   │   │   ├── Write bytes to temp .enc file
│   │   │   ├── decrypt_file_to_memory() → plaintext
│   │   │   ├── Update dest to strip .enc
│   │   │   └── Clean up temp file
│   │   │
│   │   ├── If encrypt_restored AND NOT .enc AND enc_key:
│   │   │   ├── Write bytes to temp file
│   │   │   ├── encrypt_file() → encrypted bytes
│   │   │   ├── Update dest to add .enc
│   │   │   └── Clean up temp files
│   │   │
│   │   ├── Track: was_override = dest.exists()
│   │   └── Write content to dest
│   │
│   └── Track: restored[], overridden[], skipped[]
│
├── Audit event: "♻️ Backup Restored"
│   ├── before_state: source, encrypted_archive, wiped details
│   └── after_state: destination, restored/overridden/new/skipped counts
│
├── Finally: clean up decrypted temp archive if archive was .enc
│
└── Return result dict
```

### Restore Modes

| Mode | Function | Behavior |
|------|----------|----------|
| **Override** | `restore_backup()` | Replace existing files with archive contents |
| **Import** | `import_backup()` | Only extract files that don't exist locally |
| **Wipe** | `wipe_folder()` | Auto-backup → delete selected files |

The restore function supports additional options:
- `paths=["file1.md"]` — selective restore (only named files)
- `wipe_first=True` — delete folder contents before restoring (with safety backup)
- `encrypt_restored=True` — encrypt files after extraction via COVAULT
- `decrypt_restored=True` — decrypt `.enc` files after extraction

---

## File Map

```
backup/
├── __init__.py    Public API re-exports (61 lines)
├── common.py      Constants, helpers, crypto bridge (131 lines)
├── archive.py     Create, list, preview, delete, rename, upload (601 lines)
├── restore.py     Restore, import, wipe, encrypt/decrypt inplace (575 lines)
├── extras.py      Git tracking, file tree scan, release ops (341 lines)
├── ops.py         Backward-compat re-export hub (56 lines)
└── README.md      This file
```

---

## Per-File Documentation

### `common.py` — Shared Foundation (131 lines)

Channel-independent helpers. No Flask, no route dependency. Every other
module in this domain imports from here.

| Symbol | Type | What It Does |
|--------|------|-------------|
| `SKIP_DIRS` | `frozenset` | 17 directory names excluded from scan (.git, .venv, __pycache__, node_modules, dist, build, .egg-info, .idea, .vscode, .gemini, .agent, state, .tox, .mypy_cache, .ruff_cache, .pytest_cache, venv) |
| `MEDIA_EXT` | `frozenset` | 18 media file extensions (.mp4, .webm, .mov, .avi, .mkv, .mp3, .wav, .flac, .ogg, .aac, .jpg, .jpeg, .png, .gif, .webp, .svg, .bmp, .tiff) |
| `DOC_EXT` | `frozenset` | 14 document file extensions (.md, .txt, .pdf, .json, .yaml, .yml, .xml, .csv, .docx, .rst, .html, .htm, .toml, .ini) |
| `classify_file(path)` | function | Delegates to `content.crypto.classify_file` — single classification source |
| `backup_dir_for(folder)` | function | Returns `folder/.backup/`, creating it via `mkdir(exist_ok=True)` |
| `safe_backup_name(name)` | function | Validates regex `^backup_\d{8}T\d{6}\.tar\.gz(\.enc)?$` — returns bool |
| `resolve_folder(root, rel)` | function | Resolves path, checks `relative_to(root)` (traversal guard) + `is_dir()` |
| `read_manifest(archive)` | function | Opens tarball, extracts `backup_manifest.json` member, parses JSON. Returns `None` on any failure |
| `get_enc_key(root)` | function | Reads `.env` line-by-line, finds `CONTENT_VAULT_ENC_KEY=`, strips quotes |
| `encrypt_archive(path, passphrase)` | function | Calls `content.crypto.encrypt_file()` → `.tar.gz.enc`, then **unlinks original** `.tar.gz` |
| `decrypt_archive(enc_path, passphrase)` | function | Calls `content.crypto.decrypt_file()` → temp `.tar.gz`. **Caller must clean up temp file** |

### `archive.py` — Create & Manage (601 lines)

Core archive CRUD plus folder scanning for the UI.

| Function | Signature | What It Does |
|----------|-----------|-------------|
| `folder_tree(root, max_depth=6)` | `Path, int → list[dict]` | Recursive directory tree. Skips dot-dirs and `SKIP_DIRS`. Each node: `{name, path, files, has_backup, children}`. Caps at depth 10. |
| `list_folders(root)` | `Path → list[dict]` | Flat list of top-level dirs. Each: `{name, path}`. Skips dot-dirs and `SKIP_DIRS`. |
| `create_backup(root, folder, paths, ...)` | see trace above | Creates `.tar.gz` with embedded manifest. Options: `label`, `decrypt_enc`, `encrypt_archive_flag`, `custom_name`. |
| `list_backups(root, rel_path, check_release=False)` | `Path, str → dict` | Globs `.backup/` for `*.tar.gz` and `*.tar.gz.enc`. Batch-checks git tracking via `git ls-files`. Reads release sidecars. Checks live upload status. |
| `preview_backup(root, path)` | `Path, str → dict` | Opens archive (decrypting if needed), reads all members. Returns file list with type classification. Cleans up temp decrypt. |
| `delete_backup(root, path)` | `Path, str → dict` | Unlinks archive file. Calls `cleanup_release_sidecar()` first. Removes orphan `.release.json` sidecar. |
| `rename_backup(root, path, new_name)` | `Path, str, str → dict` | Sanitizes new name via regex. Renames file. Updates release sidecar JSON: saves `old_asset_name`, writes new `asset_name`. |
| `sanitize_backup_name(name, is_encrypted=False)` | `str → str` | Strips `[^a-zA-Z0-9._-]` → `_`. Ensures `.tar.gz` or `.tar.gz.enc` extension. |
| `upload_backup(root, bytes, name, folder)` | `Path, bytes, str, str → dict` | Validates extension. Uses `safe_backup_name()` or generates timestamped name. Writes bytes to disk. For unencrypted: requires valid manifest (deletes if missing). |

### `restore.py` — Restore & Transform (575 lines)

Write-heavy operations with complex option combinations.

| Function | Signature | What It Does |
|----------|-----------|-------------|
| `restore_backup(root, path, ...)` | see trace above | Override restore. Options: `paths` (selective), `wipe_first`, `target_folder`, `encrypt_restored`, `decrypt_restored`. Creates safety backup before wipe. |
| `import_backup(root, path)` | `Path, str → dict` | Additive import. Skips existing files with reason string: `"(exists)"`, `"(path traversal)"`, `"(empty)"`. Handles encrypted archives. |
| `wipe_folder(root, folder, paths, create_backup_first=True)` | `Path, str, list, bool → dict` | Resolves each path (files + recursive dirs). Skips `.backup` dirs. Creates safety backup (manifest trigger: `"factory_reset"`). Deletes files with `_cleanup_release_sidecar()`. Removes empty dirs bottom-up. |
| `encrypt_backup_inplace(root, path)` | `Path, str → dict` | Reads passphrase from `.env`. Calls `encrypt_archive()` which encrypts + deletes original. Returns new `.enc` path. |
| `decrypt_backup_inplace(root, path)` | `Path, str → dict` | Calls `decrypt_archive()` → temp file. Renames temp to final (strip `.enc`). Deletes encrypted original. |

**Protected directories (never wiped by `restore_backup` wipe_first):**

```python
_PROTECTED_DIRS = frozenset({
    ".backup", ".git", ".github", ".venv", "venv", "__pycache__",
    "node_modules", ".mypy_cache", ".ruff_cache", ".pytest_cache",
})
```

Note: `wipe_folder()` uses a different guard — it skips paths where
`abs_p.name == ".backup"` and where `".backup" not in f.parts`.
The `_PROTECTED_DIRS` set is only used by `restore_backup`'s wipe logic.

### `extras.py` — Git & Release Ops (341 lines)

Auxiliary operations for git tracking and GitHub Release integration.

| Function | Signature | What It Does |
|----------|-----------|-------------|
| `mark_special(root, path, unmark=False)` | `Path, str, bool → dict` | If `unmark`: `git rm --cached`. If mark: validates size ≤ 25 MB (`_SPECIAL_MAX_BYTES`), then `git add -f`. Timeout: 15s. |
| `file_tree_scan(root, path, allowed_types=None, max_depth=5, respect_gitignore=False)` | `Path, str, ... → dict` | Builds expandable file tree filtered by type. Default types: document, code, script, config, data, image, video, audio, archive, encrypted, other. If `respect_gitignore`: runs `git ls-files --cached --others --exclude-standard` to build allowed set. Returns `{root, tree, counts}`. |
| `upload_backup_to_release(root, path)` | `Path, str → dict` | Imports `content.release.upload_to_release_bg()`. Creates file_id = `"backup_{stem}"`. Writes `.release.json` sidecar with `{file_id, asset_name, uploaded_at, status: "uploading"}`. Returns `{success, file_id, message}`. |
| `delete_backup_release(root, path)` | `Path, str → dict` | Reads `.release.json` sidecar. Uses `old_asset_name` or `asset_name` or filename. Calls `content.release.delete_release_asset()`. Unlinks sidecar. |
| `_cleanup_release_sidecar(file_path, root)` | `Path, Path → None` | Best-effort cleanup: calls `content.release.cleanup_release_sidecar()` with try/except. Used by `delete_backup`, `wipe_folder`, `restore_backup` wipe. |

### `ops.py` — Backward-Compat Hub (56 lines)

Pure re-export module. Imports every public symbol from `common`, `archive`,
`restore`, and `extras` (including `_cleanup_release_sidecar`). Exists so that
`from src.core.services.backup import ops as backup_ops` works for consumers
that import via the `ops` submodule.

### `__init__.py` — Public API (61 lines)

Identical structure to `ops.py`. Re-exports all public symbols. Exists so that
`from src.core.services.backup import create_backup` works directly.

Both `__init__.py` and `ops.py` export the same symbols. This is intentional —
consumers use whichever import path they prefer, both resolve to the same functions.

---

## Key Data Shapes

All data shapes verified from actual return statements in the source code.

### create_backup Response

From `archive.py` lines 205-213:

```python
{
    "success": True,                                          # NOT "ok"
    "filename": "backup_20260301T120000.tar.gz",              # or .tar.gz.enc
    "backup_folder": "docs/.backup",                          # relative to root
    "full_path": "docs/.backup/backup_20260301T120000.tar.gz",
    "size_bytes": 524288,
    "encrypted": False,                                       # encrypt_archive_flag
    "manifest": {                                             # full manifest dict
        "format_version": 2,
        "created_at": "...",
        "trigger": "admin_export",
        "target_folder": "docs",
        "decrypt_enc": False,
        "encrypt_archive": False,
        "stats": {"total_files": 42, "total_bytes": 1048576, "document_count": 30},
        "files": ["docs/readme.md", "docs/guide.md"],
    },
}
```

### list_backups Response

From `archive.py` lines 297-349. Returns a **dict with "backups" key**, not a flat list:

```python
{
    "backups": [
        {
            "filename": "backup_20260301T120000.tar.gz",
            "folder": "docs",                                 # rel_path param
            "full_path": "docs/.backup/backup_20260301T120000.tar.gz",
            "size_bytes": 524288,
            "encrypted": False,                               # .enc extension check
            "git_tracked": False,                             # from git ls-files batch
            "manifest": {...},                                # only for unencrypted
            # Optional release fields:
            "release": {                                      # from .release.json sidecar
                "file_id": "backup_...",
                "asset_name": "backup_20260301T120000.tar.gz",
                "uploaded_at": "...",
                "status": "done",                             # "uploading"|"done"|"stale"
            },
            "release_orphaned": True,                         # if asset not in remote
        },
    ],
}
```

### preview_backup Response

From `archive.py` lines 404-410:

```python
{
    "backup_path": "docs/.backup/backup_20260301T120000.tar.gz",
    "encrypted": False,
    "manifest": {...},                                        # or None
    "files": [
        {
            "name": "readme.md",                              # Path(member.name).name
            "path": "docs/readme.md",                         # member.name (rel path)
            "type": "document",                               # classify_file() result
            "size": 2048,                                     # member.size
        },
    ],
    "total": 42,                                              # len(files)
}
```

### restore_backup Response

From `restore.py` lines 210-216. Returns **lists**, not counts:

```python
{
    "success": True,
    "restored": ["docs/readme.md", "docs/guide.md"],          # list of rel paths
    "overridden": ["docs/readme.md"],                         # subset: files that existed
    "skipped": [],                                            # traversal failures, etc.
    "wiped_count": 15,                                        # int: files deleted in wipe
}
```

### import_backup Response

From `restore.py` line 345:

```python
{
    "success": True,
    "imported": ["docs/new_file.md"],                         # list of imported paths
    "skipped": ["docs/readme.md (exists)", "bad/path (path traversal)"],
}
```

### wipe_folder Response

From `restore.py` line 469:

```python
{
    "success": True,
    "deleted": ["docs/readme.md", "docs/guide.md"],           # list of deleted paths
    "errors": ["docs/locked.md: Permission denied"],          # list of error strings
    "backup": {                                               # or None if not created
        "filename": "backup_20260301T120000.tar.gz",
        "full_path": "docs/.backup/backup_20260301T120000.tar.gz",
        "size_bytes": 524288,
    },
}
```

### mark_special Response

From `extras.py` lines 86-90 (mark) and line 54 (unmark):

```python
# Mark
{
    "success": True,
    "message": "Added to git (force): backup_20260301T120000.tar.gz",
    "size_bytes": 524288,
}

# Unmark
{"success": True, "message": "Removed from git tracking"}
```

### encrypt/decrypt_backup_inplace Response

From `restore.py` lines 514-519 and 566-571:

```python
{
    "success": True,
    "filename": "backup_20260301T120000.tar.gz.enc",          # or .tar.gz for decrypt
    "full_path": "docs/.backup/backup_20260301T120000.tar.gz.enc",
    "size_bytes": 524800,
}
```

### upload_backup_to_release Response

From `extras.py` lines 253-257:

```python
{
    "success": True,
    "file_id": "backup_backup_20260301T120000",
    "message": "Upload started for backup_20260301T120000.tar.gz",
}
```

### Error Responses

Every function returns `{"error": "message"}` on failure. Some include
`_status` for HTTP status code hinting:

```python
{"error": "Missing 'target_folder'"}
{"error": "Folder not found: bad_path", "_status": 404}
{"error": "CONTENT_VAULT_ENC_KEY not set — configure in Secrets tab"}
{"error": "File too large for git (30.5 MB). Maximum is 25 MB. Use '🚀 Upload to Release' instead."}
{"error": "Invalid archive: no backup_manifest.json found"}
{"error": "Upload failed: ...", "_status": 500}
```

---

## Architecture

```
              Routes / CLI
                  │
                  │  from src.core.services.backup import ops as backup_ops
                  │
         ┌────────▼────────┐
         │  __init__.py     │  Public API re-exports
         │  ops.py          │  Backward-compat re-exports (identical)
         └──┬──┬──┬──┬────┘
            │  │  │  │
     ┌──────┘  │  │  └─────────┐
     ▼         ▼  ▼             ▼
  archive.py  restore.py   extras.py
  (create,    (restore,    (mark_special,
   list,       import,      file_tree_scan,
   preview,    wipe,        release upload,
   delete,     encrypt/     release delete,
   rename,     decrypt      _cleanup_release_sidecar)
   upload)     inplace)
        │         │              │
        └────┬────┘──────────────┘
             ▼
         common.py
         (SKIP_DIRS, MEDIA_EXT, DOC_EXT,
          classify, backup_dir, safe_name,
          resolve_folder, read_manifest,
          get_enc_key, encrypt/decrypt archive)
              │
              │ lazy import
              ▼
          content/crypto.py
          (COVAULT format:
           classify_file, encrypt_file,
           decrypt_file, decrypt_file_to_memory)
```

---

## Dependency Graph

```
common.py              standalone — constants + helpers + crypto bridge
   ↑                      lazy imports content.crypto for classify/encrypt/decrypt
   │
archive.py             imports common (classify_file, backup_dir_for,
   │                      safe_backup_name, resolve_folder, read_manifest,
   │                      get_enc_key, encrypt_archive, SKIP_DIRS, MEDIA_EXT, DOC_EXT)
   │                   lazy imports content.crypto.decrypt_file_to_memory (in create_backup)
   │                   lazy imports content.release.list_release_assets (in list_backups)
   │                   lazy imports content.release._release_upload_status (in list_backups)
   │                   lazy imports content.release.cleanup_release_sidecar (in delete_backup)
   │                   uses subprocess for git ls-files (in list_backups)
   │                   uses audit_helpers.make_auditor("backup")
   │
restore.py             imports common (backup_dir_for, resolve_folder,
   │                      read_manifest, get_enc_key, encrypt_archive, decrypt_archive)
   │                   lazy imports content.crypto.decrypt_file_to_memory (in restore_backup)
   │                   lazy imports content.crypto.encrypt_file (in restore_backup)
   │                   imports extras._cleanup_release_sidecar (via restore.py import at runtime)
   │                   uses audit_helpers.make_auditor("backup")
   │
extras.py              imports common (backup_dir_for, classify_file, resolve_folder,
   │                      SKIP_DIRS, MEDIA_EXT, DOC_EXT)
   │                   lazy imports content.release.upload_to_release_bg
   │                   lazy imports content.release.delete_release_asset
   │                   lazy imports content.release.cleanup_release_sidecar
   │                   uses subprocess for git add -f, git rm --cached, git ls-files
   │                   uses audit_helpers.make_auditor("backup")
   │
ops.py                 re-exports everything from common + archive + restore + extras
   ↑
__init__.py            re-exports everything from common + archive + restore + extras
```

Key design decisions in the graph:
- **All `content.crypto` imports are lazy** — `from src.core.services.content.crypto import ...`
  appears inside function bodies, not at module level. This avoids a hard dependency
  on the crypto package at import time.
- **All `content.release` imports are lazy** — same pattern. Release integration
  is optional; if the module isn't available, operations gracefully degrade.
- **`_cleanup_release_sidecar`** is a private helper in `extras.py` but re-exported
  through both `ops.py` and `__init__.py` because `restore.py` and `archive.py`
  call it during wipe and delete operations.

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| **Routes** | `ui/web/routes/backup/__init__.py` | `from src.core.services.backup import ops as backup_ops` — all functions via `backup_ops.*` |
| **Routes** | `ui/web/routes/backup/archive.py` | `backup_ops.create_backup`, `list_backups`, `preview_backup`, `delete_backup`, `rename_backup`, `upload_backup`, `folder_tree`, `list_folders`, `sanitize_backup_name` |
| **Routes** | `ui/web/routes/backup/restore.py` | `backup_ops.restore_backup`, `import_backup`, `wipe_folder`, `encrypt_backup_inplace`, `decrypt_backup_inplace` |
| **Routes** | `ui/web/routes/backup/ops.py` | `backup_ops.mark_special`, `upload_backup_to_release`, `delete_backup_release` |
| **Routes** | `ui/web/routes/backup/tree.py` | `backup_ops.file_tree_scan`, `folder_tree` |
| **Services** | `core/services/vault/io.py` | Imports from backup for vault archive operations |
| **Compat** | `core/services/backup_ops.py` | Legacy re-export shim |
| **Compat** | `core/services/backup_archive.py` | Legacy re-export shim |
| **Compat** | `core/services/backup_restore.py` | Legacy re-export shim |
| **Compat** | `core/services/backup_extras.py` | Legacy re-export shim |
| **Compat** | `core/services/backup_common.py` | Legacy re-export shim |

---

## Audit Trail

Every mutating operation records an audit event via `make_auditor("backup")`.
The auditor logs structured events with before/after state.

| Event | Icon | Action | Emitted By |
|-------|------|--------|-----------|
| Backup created | 📦 | `created` | `archive.create_backup()` |
| Backup deleted | 🗑️ | `deleted` | `archive.delete_backup()` |
| Backup renamed | ✏️ | `renamed` | `archive.rename_backup()` |
| Backup uploaded (file) | 📤 | `uploaded` | `archive.upload_backup()` |
| Backup restored | ♻️ | `restored` | `restore.restore_backup()` |
| Backup imported | 📥 | `imported` | `restore.import_backup()` |
| Folder wiped | 🧹 | `wiped` | `restore.wipe_folder()` |
| Backup encrypted | 🔐 | `encrypted` | `restore.encrypt_backup_inplace()` |
| Backup decrypted | 🔓 | `decrypted` | `restore.decrypt_backup_inplace()` |
| Git marked | 📌 | `marked` | `extras.mark_special()` |
| Git unmarked | 📌 | `unmarked` | `extras.mark_special(unmark=True)` |
| Release upload started | ☁️ | `uploaded` | `extras.upload_backup_to_release()` |
| Release asset deleted | ☁️❌ | `deleted` | `extras.delete_backup_release()` |
| Export failed | ❌ | — | `archive.create_backup()` (exception) |
| Restore failed | ❌ | — | `restore.restore_backup()` (exception) |
| Release upload failed | ❌ | — | `extras.upload_backup_to_release()` (exception) |
| Release delete failed | ❌ | — | `extras.delete_backup_release()` (exception) |

---

## Error Handling

| Function | Error Condition | Response |
|----------|----------------|----------|
| `create_backup` | Empty target_folder | `{"error": "Missing 'target_folder'"}` |
| `create_backup` | Empty paths | `{"error": "No paths selected"}` |
| `create_backup` | Folder not found | `{"error": "Folder not found: X"}` |
| `create_backup` | Missing enc key | `{"error": "CONTENT_VAULT_ENC_KEY not set — configure in Secrets tab"}` |
| `create_backup` | No files resolved | `{"error": "No files found in selection"}` |
| `create_backup` | Tar/encrypt exception | `{"error": "Export failed: ..."}` + cleanup unfinished archive |
| `list_backups` | Empty rel_path | `{"error": "Missing 'path'"}` |
| `list_backups` | Folder not found | `{"backups": []}` (not an error) |
| `preview_backup` | Empty path | `{"error": "Missing 'path'"}` |
| `preview_backup` | Path traversal | `{"error": "Invalid path"}` |
| `preview_backup` | Missing enc key | `{"error": "CONTENT_VAULT_ENC_KEY not set — cannot preview encrypted backup"}` |
| `restore_backup` | Pre-wipe backup fails | `{"error": "Pre-wipe backup failed (restore aborted): ..."}` — entire restore aborted |
| `import_backup` | File not found | `{"error": "File not found"}` |
| `wipe_folder` | Empty paths | `{"error": "No paths specified — select files to wipe"}` |
| `wipe_folder` | Backup fails | `{"error": "Backup failed (wipe aborted): ..."}` — wipe aborted |
| `mark_special` | File > 25 MB | `{"error": "File too large for git (X MB). Maximum is 25 MB. Use '🚀 Upload to Release' instead."}` |
| `upload_backup` | Bad extension | `{"error": "File must be a .tar.gz or .tar.gz.enc archive"}` |
| `upload_backup` | No manifest (unencrypted) | `{"error": "Invalid archive: no backup_manifest.json found"}` + file deleted |
| `encrypt_backup_inplace` | Already encrypted | `{"error": "Already encrypted"}` |
| `decrypt_backup_inplace` | Not encrypted | `{"error": "Not an encrypted archive"}` |

---

## Backward Compatibility

The backup domain was refactored from flat files (`backup_ops.py`, `backup_archive.py`,
`backup_restore.py`, `backup_extras.py`, `backup_common.py`) into a proper package.

Legacy shim files exist at `src/core/services/backup_*.py` — they re-export everything
from the new package location. This means old imports like
`from src.core.services.backup_ops import create_backup` still work.

Inside the package, `ops.py` and `__init__.py` are structurally **identical** — both
re-export the same complete set of symbols. `ops.py` exists because consumers that
did `from src.core.services.backup import ops as backup_ops` (notably all web route
files) continue to work without change. `__init__.py` enables direct symbol imports
like `from src.core.services.backup import create_backup`.

---

## Advanced Feature Showcase

### 1. Manifest-First Tar Writing — In-Memory Injection

`create_backup` writes the manifest as the **first** tar member without
ever creating it on disk. This uses `TarInfo` + `BytesIO` to inject a
virtual file into the archive stream:

```python
# archive.py — create_backup (lines 167-174)

with tarfile.open(archive_path, "w:gz") as tar:
    # Manifest: never touches filesystem
    manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
    info = tarfile.TarInfo(name="backup_manifest.json")
    info.size = len(manifest_bytes)
    info.mtime = int(now.timestamp())
    tar.addfile(info, io.BytesIO(manifest_bytes))

    # Then add real files
    for file_path, arcname in files:
        tar.add(str(file_path), arcname=arcname)
```

Why this matters: the manifest is always first (regardless of filesystem
ordering), never leaks to disk (security), and survives even if archive
creation is interrupted — `read_manifest()` can always find it via
`tar.getmember("backup_manifest.json")`.

### 2. Decrypt-on-Archive — Transparent .enc Handling During Backup

When `decrypt_enc=True`, `create_backup` decrypts `.enc` files in-flight
without writing decrypted content to disk — it streams directly into the tar:

```python
# archive.py — create_backup (lines 176-192)

for file_path, arcname in files:
    if decrypt_enc and file_path.suffix.lower() == ".enc" and enc_key:
        try:
            from src.core.services.content.crypto import decrypt_file_to_memory
            plain_bytes, meta = decrypt_file_to_memory(file_path, enc_key)
            plain_name = arcname
            if plain_name.endswith(".enc"):
                plain_name = plain_name[:-4]  # strip .enc from archive entry
            member = tarfile.TarInfo(name=plain_name)
            member.size = len(plain_bytes)
            member.mtime = int(now.timestamp())
            tar.addfile(member, io.BytesIO(plain_bytes))
        except Exception as e:
            # Fallback: add original .enc file as-is
            logger.warning("Could not decrypt %s, adding as-is: %s", arcname, e)
            tar.add(str(file_path), arcname=arcname)
    else:
        tar.add(str(file_path), arcname=arcname)
```

The fallback is critical: if decryption fails for one file, the archive
still gets created with the encrypted original. No data loss.

### 3. Pre-Wipe Safety Backup — Abort-on-Failure Guard

`restore_backup` with `wipe_first=True` creates a safety archive before
deleting anything. If the backup fails, the entire restore is **aborted**:

```python
# restore.py — restore_backup (lines 95-120)

if to_wipe:
    # Create safety backup BEFORE any deletion
    safety_dir = backup_dir_for(wipe_folder_path)
    safety_name = f"backup_{timestamp}_pre_wipe.tar.gz"
    safety_path = safety_dir / safety_name
    try:
        with tarfile.open(safety_path, "w:gz") as tar:
            manifest = {
                "format_version": 2,
                "trigger": "pre_wipe_restore",  # ← marks this as auto-generated
                ...
            }
            # Archive ALL to-wipe files
            for f in to_wipe:
                tar.add(str(f), arcname=str(f.relative_to(root)))
    except Exception as e:
        # ABORT — never proceed with wipe if backup fails
        return {"error": f"Pre-wipe backup failed (restore aborted): {e}"}

    # Only after successful backup: delete files
    for f in to_wipe:
        _cleanup_release_sidecar(f, root)
        f.unlink()
```

The same pattern exists in `wipe_folder()` with trigger `"factory_reset"`.
Both ensure the user always has a recovery path.

### 4. Release Sidecar Lifecycle — Upload → Live Status → Stale Detection

`list_backups` implements a three-stage release status lifecycle by
combining on-disk sidecars with in-memory upload status:

```python
# archive.py — list_backups (lines 314-344)

release_meta_path = a.parent / f"{a.name}.release.json"
if release_meta_path.exists():
    release_meta = json.loads(release_meta_path.read_text())
    file_id = release_meta.get("file_id", "")
    if file_id:
        from src.core.services.content.release import _release_upload_status
        live_status = _release_upload_status.get(file_id, {})

        if live_status:
            # Upload thread is alive — use its real-time status
            release_meta["status"] = live_status.get("status")
            if live_status.get("status") == "done":
                # Persist final status to disk (thread is done)
                release_meta_path.write_text(json.dumps(release_meta, indent=2))

        elif release_meta.get("status") == "uploading":
            # Thread is gone (process restarted?) — mark stale
            release_meta["status"] = "stale"
```

Three states: `"uploading"` (thread active), `"done"` (persisted), `"stale"`
(process restarted before completion). The UI shows ☁️, ✅, or ⚠️ accordingly.

### 5. Gitignore-Aware File Tree Scan

`file_tree_scan` optionally respects `.gitignore` by pre-building an
allowed file set from `git ls-files`:

```python
# extras.py — file_tree_scan (lines 126-139)

gitignore_allowed: set[str] | None = None
if respect_gitignore:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=str(project_root), capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0:
        gitignore_allowed = set(result.stdout.strip().splitlines())

# During scan:
if gitignore_allowed is not None:
    rel_file = str(entry.resolve().relative_to(project_root))
    if rel_file not in gitignore_allowed:
        continue  # skip gitignored files
```

The `--cached --others --exclude-standard` flags include both tracked and
untracked-but-not-gitignored files — exactly the set you'd want for backup.

### 6. Override vs Import — Dual Restore Mode

`restore_backup` and `import_backup` share the same archive reading logic
but differ in a critical behavioral detail:

```python
# restore_backup — OVERRIDE (restore.py lines 197-202)
was_override = final_dest.exists()
final_dest.write_bytes(content)
restored.append(rel)
if was_override:
    overridden.append(rel)

# import_backup — ADDITIVE (restore.py lines 316-326)
if dest.exists():
    skipped.append(f"{member.name} (exists)")
    continue
dest.write_bytes(fobj.read())
imported.append(member.name)
```

Override tracks which files were replaced (for the UI to show "5 restored,
2 were overwrites"). Import skips existing files and reports why with
tagged reason strings like `"(exists)"`, `"(path traversal)"`, `"(empty)"`.

### 7. Protected Directory Guard — Two Implementations

The domain uses two distinct protection mechanisms for different contexts:

```python
# restore.py — _PROTECTED_DIRS (lines 27-30)
# Used by restore_backup wipe_first: full set intersection check
_PROTECTED_DIRS = frozenset({
    ".backup", ".git", ".github", ".venv", "venv", "__pycache__",
    "node_modules", ".mypy_cache", ".ruff_cache", ".pytest_cache",
})
parts = set(f.relative_to(wipe_folder_path).parts)
if parts & _PROTECTED_DIRS:
    continue  # skip ANY file inside protected dirs

# restore.py — wipe_folder (lines 386-388)
# Different guard: only checks immediate name and .backup presence
if abs_p.is_dir() and abs_p.name != ".backup":
    for f in sorted(abs_p.rglob("*")):
        if f.is_file() and ".backup" not in f.parts:
            to_delete.append(f)
```

`restore_backup` uses a 10-member set intersection for deep protection.
`wipe_folder` uses a simpler `.backup` name check because it operates on
user-selected paths (the user explicitly chose what to delete).

---

### Feature Coverage Summary

| Feature | Where | Complexity |
|---------|-------|-----------|
| Manifest-first in-memory tar injection | `archive.py` `create_backup` | TarInfo + BytesIO, never touches disk |
| Decrypt-on-archive with fallback | `archive.py` `create_backup` | Per-file decrypt, graceful .enc fallback |
| Pre-wipe safety backup (abort-on-failure) | `restore.py` `restore_backup` | Archive → verify → then delete. Also in `wipe_folder` |
| Release sidecar lifecycle | `archive.py` `list_backups` | uploading → done (persist) → stale (process restart) |
| Gitignore-aware file tree | `extras.py` `file_tree_scan` | `git ls-files --cached --others --exclude-standard` |
| Override vs Import dual mode | `restore.py` | Override tracks overwrites, import skips with reasons |
| Dual protected-dir guard | `restore.py` | Set intersection (restore) vs name check (wipe) |

---

## Design Decisions


### Why .tar.gz instead of .zip?

Tar+gzip is the standard archive format on Unix systems. It preserves
file permissions and symbolic links. The `tarfile` module is in
Python's stdlib (no external dependency). Gzip provides good
compression for text-heavy content folders. The `.tar.gz` extension
is universally recognized.

### Why embedded manifests instead of external metadata?

The `backup_manifest.json` inside the archive makes backups
self-describing and portable. No external metadata file to lose or
desync. The manifest can be read via `read_manifest()` without
extracting the entire archive (tarfile supports member extraction).
The manifest is written as the **first** tar member via `TarInfo` +
`BytesIO` — it never exists as a file on disk.

### Why two restore modes (override vs import)?

Override replaces existing files — useful for rolling back to a
known state. Import adds missing files — useful for merging content
from another source. Both are needed in practice: rollback scenarios
need override, while content migration needs import.

### Why does wipe_folder auto-backup by default?

Factory reset is destructive. The `create_backup_first=True` default
ensures users have a recovery path even if they accidentally wipe
the wrong files. The backup is created in `.backup/` before any
deletions occur. If the safety backup fails, the wipe is **aborted** —
never proceeds without a safety net.

### Why does restore_backup create a safety backup before wipe?

Same principle. When `wipe_first=True`, the existing folder contents
are archived with trigger `"pre_wipe_restore"` before any deletion.
If this safety backup fails, the entire restore is aborted. The user
can always recover to the pre-restore state.

### Why mark_special uses git add -f?

Backup archives in `.backup/` are gitignored by default (they're
regeneratable). But some archives contain irreplaceable data (e.g.,
production snapshots). `git add -f` overrides the gitignore and
force-tracks the file. The 25 MB limit (`_SPECIAL_MAX_BYTES`)
prevents accidentally bloating the repository. Larger files should
use the GitHub Release upload path instead.

### Why separate archive.py from restore.py?

Create/list/preview are read-heavy operations, while restore/import/
wipe are write-heavy with complex options (wipe_first, encrypt, decrypt).
Splitting them keeps each module focused and reduces merge conflicts
when modifying one concern. `archive.py` (601 lines) and `restore.py`
(575 lines) would be a 1,176-line file if combined.

### Why is archive.py 601 lines?

The `create_backup` function alone is 165 lines because it handles
selective file resolution, per-file decrypt-on-archive, manifest
generation, tar creation, optional encrypt, and full audit logging.
`list_backups` is 100 lines because it batch-checks git tracking,
reads release metadata sidecars, checks live upload status, and
detects orphaned releases. Each function in this file handles a
complete lifecycle operation with validation, execution, audit, and
error recovery — there's no dead code to extract.

### Why all crypto imports are lazy?

`content.crypto` depends on the `cryptography` package, which is an
optional dependency. Lazy `from ... import ...` inside function bodies
means the backup domain can be imported and used for non-crypto
operations (list, preview, delete, rename) even when `cryptography`
is not installed. Only operations that actually need encryption
(create with `encrypt_archive_flag`, restore encrypted archives,
in-place encrypt/decrypt) will fail if the package is missing.

### Why does list_backups check live upload status?

Release uploads happen in background threads via
`content.release.upload_to_release_bg()`. The `.release.json` sidecar
is written immediately with `status: "uploading"`. On subsequent
`list_backups` calls, the function checks `_release_upload_status`
(an in-memory dict in `content.release`) for live progress. If the
upload thread has completed (`status: "done"`), it updates the sidecar
on disk. If the process restarted and the sidecar still says
`"uploading"`, the status is set to `"stale"` so the UI can show
an appropriate indicator.
