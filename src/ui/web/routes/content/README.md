# Content Routes — File & Crypto API

> **5 files · 864 lines · 22 endpoints · Blueprint: `content_bp` · Prefix: `/api`**
>
> Thin HTTP wrappers over `src.core.services.content.*`.
> These routes power the content vault: file browsing, upload/download,
> encryption/decryption (COVAULT format), preview (text/image/video/audio),
> release management (GitHub Release for large files), and media optimization.
> No business logic lives here — every handler delegates to a core service.

---

## How It Works

### Request Flow

```
Frontend (scripts/content/)
│
├── _browser.html       → /api/content/folders, /list, /create-folder
├── _upload.html        → /api/content/upload, /optimize-status, /optimize-cancel
├── _preview.html       → /api/content/preview, /download, /save, /rename, /move
├── _preview_enc.html   → /api/content/preview-encrypted, /save-encrypted
└── _chat_refs.html     → /api/content/release-*, /clean-release-sidecar
     │
     ▼
routes/content/                            ← HTTP layer (this package)
├── __init__.py   — folders, list, encrypt, decrypt, metadata
├── files.py      — create-folder, delete, download, upload, enc-key, optimize
├── preview.py    — preview, preview-encrypted, save-encrypted
└── manage.py     — setup-enc-key, save, rename, move, release-*
     │
     ▼
core/services/content/                     ← Business logic (no HTTP)
├── crypto.py       — COVAULT encrypt/decrypt, folder detection, listing
├── file_ops.py     — file CRUD, upload pipeline, release restore
├── release.py      — GitHub Release upload/status/cancel/inventory
└── optimize.py     — media optimization (ffmpeg)
```

### Encryption Lifecycle

```
                        ┌── encrypt ────────┐
 PLAIN FILE ────────────┤                   ├───── .enc FILE (COVAULT)
                        └── decrypt ────────┘
                                │
                  preview-encrypted ──── decrypt to memory only
                       │                    (no disk write)
                       │
                  save-encrypted ──────── re-encrypt edited text
                                          back to .enc file
                                │
                    metadata ────────── read .enc header only
                                        (no key required)
```

### Release Management Flow

```
Large file (>100MB)
     │
     ▼
Upload to GitHub Release (background thread)
     │
     ├── .release.json sidecar written next to original file
     │   {"asset_name": "...", "size": ..., "sha256": "..."}
     │
     ├── release-status        ← poll upload progress
     ├── release-status/<id>   ← poll single upload
     ├── release-cancel/<id>   ← kill running upload
     │
     └── After upload complete:
         ├── release-inventory   ← cross-ref local sidecars vs remote assets
         ├── restore-large       ← re-download from release (after clone)
         └── clean-release-sidecar ← delete orphaned .release.json
```

### Path Security Model

```
ALL path inputs
     │
     ▼
resolve_safe_path(rel_path)         ← from ui/web/helpers.py
     │
     ├── Resolves relative to project root
     ├── Rejects path traversal (../)
     ├── Rejects absolute paths
     └── Returns None → 400 error
```

Every endpoint that accepts a `path` parameter runs it through
`resolve_safe_path()` before touching the filesystem.

---

## File Map

```
routes/content/
├── __init__.py     249 lines  — blueprint + core listing/crypto endpoints (6 routes)
├── preview.py      265 lines  — file preview for plain + encrypted files (3 routes)
├── manage.py       187 lines  — key setup, save, rename, move, release mgmt (10 routes)
├── files.py        150 lines  — folder/file CRUD, upload, optimize (7 routes)
├── helpers.py       13 lines  — re-exports project_root, resolve_safe_path, get_enc_key
└── README.md                  — this file
```

---

## Per-File Documentation

### `__init__.py` — Blueprint + Core Listing & Crypto (249 lines)

Defines the `content_bp` blueprint and the most fundamental endpoints:
folder detection, file listing, encrypt/decrypt, and metadata reading.
Imports sub-modules at the END of the file to register their routes.

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `content_folders()` | GET | `/content/folders` | Detect content folders in project + suggest defaults |
| `content_all_folders()` | GET | `/content/all-folders` | List ALL project directories (flat) |
| `content_list()` | GET | `/content/list` | List files in folder with summary stats |
| `content_encrypt()` | POST | `/content/encrypt` | Encrypt file → .enc (COVAULT format) |
| `content_decrypt()` | POST | `/content/decrypt` | Decrypt .enc → original file |
| `content_metadata()` | GET | `/content/metadata` | Read .enc metadata without key |

**Decorators:** `content_encrypt()` and `content_decrypt()` use
`@run_tracked("setup", "setup:encrypt")` / `@run_tracked("setup", "setup:decrypt")`
for activity tracking.

**Imports from core:**
```python
from src.core.services.content.crypto import (
    classify_file, decrypt_file_to_memory, detect_content_folders,
    encrypt_content_file, decrypt_content_file, format_size,
    is_covault_file, list_folder_contents, list_folder_contents_recursive,
    read_metadata, DEFAULT_CONTENT_DIRS, DOC_EXTS, CODE_EXTS,
    SCRIPT_EXTS, CONFIG_EXTS, DATA_EXTS,
)
```

**Circular import guard:** Sub-module imports appear at the END:
```python
# These imports MUST come after content_bp is defined
from . import files    # noqa: E402, F401
from . import preview  # noqa: E402, F401
from . import manage   # noqa: E402, F401
```

### `preview.py` — File Preview (265 lines)

Handles preview for both plain and encrypted files. The most complex
file in this package — contains type detection, media response
generation, and the encrypted preview flow.

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `content_preview()` | GET | `/content/preview` | Preview file: text/image/video/audio/binary |
| `content_preview_encrypted()` | POST | `/content/preview-encrypted` | Decrypt to memory + preview |
| `content_save_encrypted()` | POST | `/content/save-encrypted` | Re-encrypt edited content |

**Type detection constants (module-level):**
```python
_TEXT_EXTS = (
    DOC_EXTS | CODE_EXTS | SCRIPT_EXTS | CONFIG_EXTS | DATA_EXTS
    | {".log", ".gitignore", ".dockerignore", ".editorconfig",
       "Makefile", "Dockerfile", "Procfile", "Vagrantfile"}
)
_MAX_PREVIEW_BYTES = 512 * 1024  # 512 KB
```

**Preview type decision tree:**
```
file suffix / MIME type
     │
     ├── suffix in _TEXT_EXTS or mime starts with "text/"
     │   └── type: "markdown" (if .md) or "text"
     │       Content: UTF-8 text, truncated at 512 KB
     │
     ├── mime starts with "image/"
     │   └── type: "image", url: /api/content/download?path=...
     │
     ├── mime starts with "video/"
     │   └── type: "video", url: /api/content/download?path=...
     │
     ├── mime starts with "audio/"
     │   └── type: "audio", url: /api/content/download?path=...
     │
     └── else
         └── type: "binary", error: "Cannot preview binary files"
```

**Encrypted preview — different delivery mechanism:**

For encrypted files, there is no disk file to serve via `send_file()`.
The decrypted bytes exist only in memory. So media files are returned
as base64 data URLs:

| Type | Plain File | Encrypted File |
|------|-----------|---------------|
| Text | `{"content": "..."}` | `{"content": "..."}` (decoded UTF-8) |
| Image | `{"url": "/api/content/download?path=..."}` | `{"url": "data:image/png;base64,..."}` |
| Video | `{"url": "/api/content/download?path=..."}` | `{"url": "data:video/mp4;base64,..."}` |
| Audio | `{"url": "/api/content/download?path=..."}` | `{"url": "data:audio/mp3;base64,..."}` |

**Release sidecar check:** Every plain file preview includes release
metadata from `check_release_sidecar()`:
```python
rel_fields = {
    "has_release": rs["has_release"],
    "release_status": rs["release_status"],
    "release_orphaned": rs["release_orphaned"],
}
```

### `manage.py` — Key Setup, File Ops, Release Management (187 lines)

The widest endpoint file — covers setup, editing, filesystem ops,
and the full release management surface.

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `content_setup_enc_key()` | POST | `/content/setup-enc-key` | Set/generate `CONTENT_VAULT_ENC_KEY` in .env |
| `content_save()` | POST | `/content/save` | Save text content to file |
| `content_rename()` | POST | `/content/rename` | Rename file in-place |
| `content_move()` | POST | `/content/move` | Move file to another folder |
| `content_release_status()` | GET | `/content/release-status` | Poll all background release uploads |
| `content_release_status_single()` | GET | `/content/release-status/<id>` | Poll single upload status |
| `content_release_cancel()` | POST | `/content/release-cancel/<id>` | Cancel running release upload |
| `content_restore_large()` | POST | `/content/restore-large` | Download missing large files from GitHub Release |
| `content_release_inventory()` | GET | `/content/release-inventory` | Cross-ref local sidecars vs remote assets |
| `content_clean_release_sidecar()` | POST | `/content/clean-release-sidecar` | Delete stale `.release.json` sidecar |

**Release inventory response stripping:** The raw `release_inventory()`
result includes verbose `meta` dicts. The route strips these:
```python
for lst_key in ("orphaned", "synced", "local_sidecars"):
    for item in result.get(lst_key, []):
        item.pop("meta", None)
```

### `files.py` — File CRUD + Upload + Optimize (150 lines)

Straightforward CRUD plus the upload pipeline with optimization support.

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `content_create_folder()` | POST | `/content/create-folder` | Create content folder in project root |
| `content_delete()` | POST | `/content/delete` | Delete a file |
| `content_download()` | GET | `/content/download` | Download/stream file (supports `?download=1`) |
| `content_upload()` | POST | `/content/upload` | Upload file (multipart form, auto-optimize) |
| `content_enc_key_status()` | GET | `/content/enc-key-status` | Check if encryption key is configured |
| `content_optimize_status()` | GET | `/content/optimize-status` | Poll media optimization progress |
| `content_optimize_cancel()` | POST | `/content/optimize-cancel` | Cancel active optimization (kills ffmpeg) |

**Upload pipeline detail:**
```python
uploaded = request.files["file"]
safe_name = secure_filename(uploaded.filename) or "upload"
result = content_file_ops.upload_content_file(
    _project_root(),
    folder_rel=request.form.get("folder", ""),
    filename=safe_name,
    raw_data=uploaded.read(),               # multipart → bytes
)
```

**Download inline vs attachment:**
```python
send_file(target, as_attachment=request.args.get("download", "0") == "1")
# ?download=0 (default) → inline (preview in browser)
# ?download=1           → attachment (triggers Save As dialog)
```

### `helpers.py` — Shared Re-exports (13 lines)

```python
from src.ui.web.helpers import (
    project_root,
    resolve_safe_path,
    get_enc_key,
)
```

Exists so sub-modules import `from .helpers import project_root`
instead of reaching two packages up to `src.ui.web.helpers`.

---

## Dependency Graph

```
helpers.py          ← re-exports from src.ui.web.helpers (standalone)

__init__.py         ← defines content_bp
├── crypto.*        ← encrypt/decrypt/list/detect from core
├── run_tracker     ← activity tracking decorator
└── helpers.py      ← project_root, resolve_safe_path, get_enc_key

files.py            ← imports content_bp from __init__
├── content.file_ops  ← CRUD operations from core
└── helpers.py

preview.py          ← imports content_bp from __init__
├── crypto.*        ← decrypt_file_to_memory, _guess_mime from core
├── content.file_ops  ← check_release_sidecar, save_encrypted_content
└── helpers.py

manage.py           ← imports content_bp from __init__
├── content.file_ops  ← setup_enc_key, save/rename/move, restore_large
├── content.release   ← status/cancel/inventory/sidecar from core
└── helpers.py
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `content_bp`, registers on Flask app |
| Frontend | `scripts/content/_browser.html` | `/folders`, `/all-folders`, `/list`, `/create-folder` |
| Frontend | `scripts/content/_upload.html` | `/upload`, `/optimize-status`, `/optimize-cancel` |
| Frontend | `scripts/content/_preview.html` | `/preview`, `/download`, `/save`, `/rename`, `/move`, `/delete` |
| Frontend | `scripts/content/_preview_enc.html` | `/preview-encrypted`, `/save-encrypted`, `/enc-key-status`, `/setup-enc-key` |
| Frontend | `scripts/content/_chat_refs.html` | `/release-status`, `/release-inventory`, `/clean-release-sidecar` |

---

## Service Delegation Map

```
Route Handler                    →   Core Service Module.Function
──────────────────────────────────────────────────────────────────
content_folders()                →   crypto.detect_content_folders()
content_all_folders()            →   file_ops.list_all_project_folders()
content_list()                   →   crypto.list_folder_contents[_recursive]()
content_encrypt()                →   crypto.encrypt_content_file()
content_decrypt()                →   crypto.decrypt_content_file()
content_metadata()               →   crypto.read_metadata()
content_preview()                →   crypto._guess_mime() + file I/O
content_preview_encrypted()      →   crypto.decrypt_file_to_memory()
content_save_encrypted()         →   file_ops.save_encrypted_content()
content_setup_enc_key()          →   file_ops.setup_enc_key()
content_save()                   →   file_ops.save_content_file()
content_rename()                 →   file_ops.rename_content_file()
content_move()                   →   file_ops.move_content_file()
content_create_folder()          →   file_ops.create_content_folder()
content_delete()                 →   file_ops.delete_content_file()
content_download()               →   Flask send_file() (direct)
content_upload()                 →   file_ops.upload_content_file()
content_restore_large()          →   file_ops.restore_large_files_from_release()
content_release_status()         →   release.get_all_release_statuses()
content_release_status_single()  →   release.get_release_status()
content_release_cancel()         →   release.cancel_release_upload()
content_release_inventory()      →   release.release_inventory()
content_clean_release_sidecar()  →   release.remove_orphaned_sidecar()
content_optimize_status()        →   optimize.get_optimization_status()
content_optimize_cancel()        →   optimize.cancel_active_optimization()
```

---

## Data Shapes

### `/api/content/folders` response

```json
{
    "folders": [
        {"name": "docs", "path": "docs", "file_count": 12, "categories": ["markdown", "text"]},
        {"name": "media", "path": "media", "file_count": 45, "categories": ["image", "video"]}
    ],
    "suggestions": ["assets", "content"]
}
```

### `/api/content/list` response

```json
{
    "path": "docs",
    "recursive": false,
    "files": [
        {"name": "setup.md", "size": 4096, "encrypted": false, "is_dir": false},
        {"name": "secret.md.enc", "size": 8192, "encrypted": true, "is_dir": false},
        {"name": "images", "is_dir": true}
    ],
    "summary": {
        "file_count": 12,
        "dir_count": 3,
        "total_size": 1048576,
        "total_size_human": "1.0 MB",
        "encrypted_count": 2
    }
}
```

### `/api/content/preview` response (text file)

```json
{
    "type": "markdown",
    "mime": "text/markdown",
    "content": "# Setup Guide\n\nThis document...",
    "truncated": false,
    "size": 4096,
    "line_count": 120,
    "has_release": false,
    "release_status": "none",
    "release_orphaned": false
}
```

### `/api/content/preview` response (image file)

```json
{
    "type": "image",
    "mime": "image/png",
    "url": "/api/content/download?path=media/diagram.png",
    "has_release": true,
    "release_status": "synced",
    "release_orphaned": false
}
```

### `/api/content/preview-encrypted` response (encrypted image)

```json
{
    "type": "image",
    "url": "data:image/png;base64,iVBORw0KGgo...",
    "original_name": "diagram.png",
    "mime": "image/png",
    "size": 51200
}
```

### `/api/content/preview-encrypted` error (wrong key)

```json
{
    "error": "Wrong key or corrupted file",
    "wrong_key": true
}
```

### `/api/content/encrypt` request + response

```json
// POST body
{"path": "docs/secret.md", "delete_original": true}

// Success response
{"ok": true, "encrypted_path": "docs/secret.md.enc", "original_deleted": true}
```

### `/api/content/release-inventory` response

```json
{
    "orphaned": [
        {"path": "media/old.release.json", "asset_name": "old.mp4"}
    ],
    "synced": [
        {"path": "media/video.release.json", "asset_name": "video.mp4", "size": 104857600}
    ],
    "local_sidecars": [
        {"path": "media/video.release.json"}
    ]
}
```

---

## Advanced Feature Showcase

### 1. Release Cross-Reference in File Listing

The `/api/content/list` endpoint supports `check_release=true` which
fetches remote GitHub Release assets and cross-refs with local sidecars:

```python
# __init__.py — release cross-ref during listing
ra: set[str] | None = None
if check_release:
    from src.core.services.content.release import list_release_assets
    remote = list_release_assets(root)
    if remote.get("available"):
        ra = {a["name"] for a in remote["assets"]}
    else:
        ra = set()  # Release doesn't exist → every sidecar is orphaned

if recursive:
    files = list_folder_contents_recursive(folder, root, remote_assets=ra)
else:
    files = list_folder_contents(folder, root, remote_assets=ra)
```

When `ra` is not None, each file entry gets `release_orphaned=True/False`
based on whether its sidecar's asset name exists in the remote set.

### 2. Encrypted Media Preview via Base64 Data URLs

Decrypted file content exists only in memory — no disk write. For media
types, the route base64-encodes and returns inline data URLs:

```python
# preview.py — encrypted image preview
if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico"}:
    import base64
    b64 = base64.b64encode(plaintext).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"
    return jsonify({
        "type": "image",
        "url": data_url,                    # <-- browser renders directly
        "original_name": original_name,
        "mime": mime,
        "size": size,
    })
```

This works for images, video, and audio — the browser's `<img>`,
`<video>`, and `<audio>` elements all support data URLs.

### 3. Upload with Secure Filename + Auto-Optimization

Upload uses Werkzeug's `secure_filename()` to sanitize then delegates
to core which triggers automatic media optimization (ffmpeg) for
supported formats:

```python
# files.py — upload pipeline
from werkzeug.utils import secure_filename

uploaded = request.files["file"]
safe_name = secure_filename(uploaded.filename) or "upload"
result = content_file_ops.upload_content_file(
    _project_root(),
    folder_rel=folder_rel,
    filename=safe_name,
    raw_data=uploaded.read(),
)
# Core returns: {"path": "...", "size": ..., "optimizing": true/false}
# If optimizing, frontend polls /optimize-status until complete
```

### 4. Key Override for Encrypted Preview

The encrypted preview endpoint supports an override key, allowing
users to preview files encrypted with a different key than the
configured one:

```python
# preview.py — key resolution
passphrase = override_key or _get_enc_key()
if not passphrase:
    return jsonify({"error": "No encryption key available", "needs_key": True}), 400
```

The `needs_key: true` flag tells the frontend to show a key input dialog.

### 5. Error Classification in Encryption Routes

Encrypt/decrypt routes inspect the error message to return appropriate
HTTP status codes without hardcoding status in the service:

```python
# __init__.py — error handling pattern
if "error" in result:
    code = result.pop("_status", 400)     # service can hint status
    if "not found" in result["error"].lower():
        code = 404                         # upgrade to 404
    return jsonify(result), code
```

---

## Design Decisions

### Why preview.py is the largest file (265 lines)

Preview has the most complex branching — 5 media types × 2 modes
(plain vs encrypted) = 10 code paths. Encrypted mode adds base64
encoding, key resolution, and error handling for wrong keys.
Splitting by media type would scatter related logic.

### Why helpers.py re-exports instead of direct imports

Sub-modules need `project_root`, `resolve_safe_path`, `get_enc_key`.
Without the shim, each would import `from src.ui.web.helpers import ...`
— reaching two package levels up. The 13-line shim keeps imports clean
and makes the package self-contained.

### Why circular import guard pattern

`__init__.py` defines `content_bp`, then sub-modules import it.
But `__init__.py` also needs to trigger sub-module route registration.
Solution: sub-module imports at the END of `__init__.py` after
`content_bp` is defined. This is Flask's standard pattern for
splitting blueprints across files.

### Why release inventory strips meta dicts

The core `release_inventory()` returns full metadata dicts (SHA256,
upload timestamps, etc.) that are useful internally but too verbose
for the API response. The route strips them to reduce payload size.

### Why only encrypt/decrypt have @run_tracked

These are the only endpoints with side effects that users care about
tracking in the activity log. File operations (save, rename, move,
delete) are instant and don't need tracking. Upload tracking happens
via the optimization polling mechanism instead.

---

## Coverage Summary

| Capability | Endpoints | File |
|-----------|-----------|------|
| Folder detection | 2 | `__init__.py` |
| File listing | 1 (with recursive + release modes) | `__init__.py` |
| Encrypt/decrypt | 2 | `__init__.py` |
| Metadata read | 1 | `__init__.py` |
| Preview (plain) | 1 (5 media types) | `preview.py` |
| Preview (encrypted) | 1 (5 media types, base64) | `preview.py` |
| Save encrypted edits | 1 | `preview.py` |
| File CRUD | 4 (create-folder, delete, download, upload) | `files.py` |
| Encryption key mgmt | 2 (status, setup) | `files.py`, `manage.py` |
| Optimization | 2 (status, cancel) | `files.py` |
| File editing | 3 (save, rename, move) | `manage.py` |
| Release management | 6 (status, single, cancel, restore, inventory, clean) | `manage.py` |
