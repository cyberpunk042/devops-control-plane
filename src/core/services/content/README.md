# Content Domain

> **10 files · 3,763 lines · File management, encryption, optimization, and release sync.**
>
> Full content lifecycle: folder detection → file listing → upload with
> automatic optimization → COVAULT envelope encryption → GitHub Release
> sync for large files → restore from release.

---

## How It Works

Every file uploaded through the Content Vault goes through a pipeline:

```
Upload (raw bytes)
    │
    ├── 1. MIME detection → _guess_mime → classify_file
    │
    ├── 2. Optimization dispatcher (optimize_media)
    │       ├── Image  → resize + WebP (Pillow)
    │       ├── Video  → H.264 MP4 (ffmpeg, optional NVENC)
    │       ├── Audio  → AAC M4A (ffmpeg)
    │       └── Text   → gzip (if compressible + large enough)
    │
    ├── 3. Storage classification (classify_storage)
    │       ├── ≤ 2 MB  → "git" tier (tracked normally)
    │       └── > 2 MB  → "large" tier (.large/ subfolder, gitignored)
    │
    ├── 4. Write to disk + audit
    │
    └── 5. If "large" tier → upload_to_release_bg
            ├── Create .release.json sidecar
            ├── gh release upload (background thread)
            └── Sidecar status: queued → uploading → uploaded / failed
```

### Upload Pipeline (step by step)

```
upload_content_file(project_root, folder_rel, filename, raw_data)
     │
     ├── Resolve folder path (resolve_safe_path)
     │     └── Prevent directory traversal → None if invalid
     │
     ├── Detect MIME type:
     │     └── _guess_mime(filename)
     │           ├── Strip .enc suffix if present
     │           ├── Check _EXT_MIME lookup (27 entries)
     │           └── Fall back to mimetypes.guess_type()
     │
     ├── Optimize (optimize_media):
     │     ├── should_optimize_image(size, mime)?
     │     │     └── image/* AND > 100 KB AND not SVG/GIF
     │     │     └── YES → optimize_image(data, mime)
     │     │           ├── Open with PIL.Image
     │     │           ├── Resize if max(w,h) > 2048
     │     │           │     └── ratio = 2048 / max(w,h)
     │     │           │     └── img.resize((new_w, new_h), LANCZOS)
     │     │           ├── Convert color mode:
     │     │           │     ├── JPEG + RGBA → composite onto white RGB
     │     │           │     ├── WEBP + P → convert to RGBA
     │     │           │     └── RGBA without alpha → convert to RGB
     │     │           └── Encode as WEBP (quality=85, method=4)
     │     │
     │     ├── video/* → optimize_video(data, mime)
     │     │     ├── Write to temp file
     │     │     ├── _probe_media() → codec, resolution, bitrate
     │     │     ├── _needs_video_reencode(probe, size)?
     │     │     │     └── Skip if size < 10 MB (VIDEO_SKIP_BELOW)
     │     │     ├── _detect_hw_encoder() → NVENC or software
     │     │     ├── Build ffmpeg command:
     │     │     │     ├── GPU: h264_nvenc -preset medium -rc vbr_hq
     │     │     │     └── CPU: libx264 -crf 28 -preset fast
     │     │     ├── Scale if height > 1080
     │     │     ├── Run with progress tracking (1s poll)
     │     │     └── Keep result only if smaller than original
     │     │
     │     ├── audio/* → optimize_audio(data, mime)
     │     │     └── ffmpeg -c:a aac -b:a 96k → M4A
     │     │
     │     ├── Compressible text? → optimize_text(data, mime)
     │     │     ├── Check COMPRESSIBLE_MIMES or COMPRESSIBLE_EXTENSIONS
     │     │     ├── Skip if < 100 KB
     │     │     └── gzip.compress(data, compresslevel=9)
     │     │
     │     └── Fallback: try generic gzip for unknown > 100 KB
     │           └── Keep only if compressed < 90% of original
     │
     ├── Determine filename:
     │     ├── Extension changed? → stem + new_ext
     │     └── Same extension? → keep original name
     │
     ├── Classify storage:
     │     └── classify_storage(final_size)
     │           ├── > 2 MB → "large" → folder/.large/
     │           └── ≤ 2 MB → "git"   → folder/
     │
     ├── Avoid overwrite:
     │     └── If dest exists → append _1, _2, ... counter
     │
     ├── Write bytes to disk
     │
     ├── Audit:
     │     └── _audit("⬆️ File Uploaded", ...)
     │
     └── If tier == "large":
           ├── upload_to_release_bg(file_id, dest, project_root)
           └── Write .release.json sidecar → {"status": "uploading"}
```

### COVAULT Envelope Format

Binary format for at-rest encryption of individual content files:

```
┌───────────┬──────────────┬──────────┬────────────┬──────┐
│ COVAULT_v1│ fname_len(2) │ filename │ mime_len(2)│ mime │
│ (10 bytes)│              │          │            │      │
├───────────┴──────────────┴──────────┴────────────┴──────┤
│ SHA-256(32) │ Salt(16) │ IV(12) │ Tag(16) │ Ciphertext  │
└─────────────┴──────────┴────────┴─────────┴─────────────┘
```

| Parameter | Value |
|-----------|-------|
| Magic | `COVAULT_v1` (10 bytes) |
| Cipher | AES-256-GCM |
| KDF | PBKDF2-SHA256 |
| Iterations (default) | 480,000 |
| Iterations (export) | 600,000 |
| Salt | 16 bytes (random per file) |
| IV | 12 bytes (random per file) |
| Tag | 16 bytes (GCM authentication) |
| Length fields | 2 bytes each, little-endian uint16 |
| Min passphrase | 4 characters |

### Encryption Flow

```
encrypt_file(source_path, passphrase, output_path, iterations)
     │
     ├── Validate:
     │     ├── source_path.exists()? → FileNotFoundError
     │     └── len(passphrase) >= 4? → ValueError
     │
     ├── Read source bytes
     │
     ├── Metadata:
     │     ├── stored_name = original_filename or source_path.name
     │     ├── filename = stored_name.encode("utf-8")
     │     └── mime_type = _guess_mime(stored_name).encode("utf-8")
     │
     ├── Integrity:
     │     └── sha256 = hashlib.sha256(plaintext).digest()
     │
     ├── Crypto:
     │     ├── salt = os.urandom(16)
     │     ├── iv = os.urandom(12)
     │     ├── key = PBKDF2HMAC(SHA256, 32, salt, 480_000)
     │     ├── aesgcm = AESGCM(key)
     │     └── ct_with_tag = aesgcm.encrypt(iv, plaintext, None)
     │           ├── ciphertext = ct_with_tag[:-16]
     │           └── tag = ct_with_tag[-16:]
     │
     ├── Build envelope:
     │     MAGIC + len(filename) + filename + len(mime) + mime
     │     + sha256 + salt + iv + tag + ciphertext
     │
     └── Write envelope to output_path
```

### Decryption Flow

```
decrypt_file(vault_path, passphrase, output_path, iterations)
     │
     ├── Read entire file → data
     │
     ├── _parse_envelope(data):
     │     ├── Verify magic bytes == COVAULT_v1
     │     ├── Read filename_len (2 bytes LE) → read filename
     │     ├── Read mime_len (2 bytes LE) → read mime_type
     │     ├── Read sha256 (32 bytes)
     │     ├── Read salt (16 bytes)
     │     ├── Read iv (12 bytes)
     │     ├── Read tag (16 bytes)
     │     └── Remaining bytes → ciphertext
     │
     ├── Derive key: PBKDF2(passphrase, salt, 480_000)
     │
     ├── Decrypt: aesgcm.decrypt(iv, ciphertext + tag, None)
     │     └── Wrong passphrase → ValueError
     │
     ├── Integrity: sha256(plaintext) == stored_sha256?
     │     └── Mismatch → ValueError("file may be corrupted")
     │
     └── Write plaintext to output_path
           └── Default: vault_path.parent / meta["filename"]
```

### File Classification

```
classify_file(path) → category
```

| Category | Extensions |
|----------|-----------|
| `image` | `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.svg`, `.bmp`, `.ico` |
| `video` | `.mp4`, `.webm`, `.mov`, `.avi`, `.mkv` |
| `audio` | `.mp3`, `.wav`, `.ogg`, `.flac`, `.aac` |
| `document` | `.pdf`, `.docx`, `.doc`, `.txt`, `.md`, `.rst`, `.xlsx`, `.rtf` |
| `code` | `.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.java`, `.c`, `.cpp`, `.go`, `.rs`, `.rb`, `.php`, +29 more |
| `script` | `.sh`, `.bash`, `.zsh`, `.fish`, `.bat`, `.cmd`, `.ps1`, `.psm1`, `.pl`, `.awk`, `.sed` |
| `config` | `.yaml`, `.yml`, `.json`, `.toml`, `.ini`, `.cfg`, `.conf`, `.env`, `.properties`, `.xml`, `.plist` |
| `data` | `.csv`, `.tsv`, `.sql`, `.sqlite`, `.db`, `.parquet`, `.ndjson`, `.jsonl`, `.avro`, `.feather` |
| `archive` | `.zip`, `.tar`, `.gz`, `.7z`, `.rar`, `.bz2`, `.xz` |
| `encrypted` | `.enc` (bare, no inner extension) |
| `other` | Anything not matching above |

For `.enc` files, classification is based on inner extension: `foo.md.enc` → `document`.

Special config filenames (matched regardless of extension):

```
Makefile, Dockerfile, Vagrantfile, Procfile,
.gitignore, .gitattributes, .editorconfig,
.dockerignore, .eslintrc, .prettierrc,
docker-compose.yml, docker-compose.yaml,
project.yml, pyproject.toml, setup.cfg,
package.json, tsconfig.json, Cargo.toml, go.mod
```

### Storage Tiers

| Tier | Threshold | Storage | Managed By |
|------|-----------|---------|------------|
| `git` | ≤ 2 MB | Tracked normally in git | Standard git flow |
| `large` | > 2 MB | `.large/` subfolder, gitignored | `release.py` uploads to GitHub Release |

### Release Upload Lifecycle

```
upload_to_release_bg(file_id, file_path, project_root)
     │
     ├── Check: gh CLI on PATH?
     │     └── NO → status = "failed", message = "gh CLI not installed"
     │
     ├── Check: file exists?
     │     └── NO → status = "failed"
     │
     ├── Set status = "pending" (with size_mb)
     │
     └── Start daemon thread → _do_upload()
           │
           ├── Check cancelled?
           │
           ├── Phase 1: Ensure release exists
           │     ├── gh release view content-vault
           │     └── If not found → gh release create content-vault
           │           --title "Content Vault"
           │           --notes "Large content files..."
           │           --latest=false
           │
           ├── Phase 2: Upload asset
           │     ├── gh release upload content-vault <file> --clobber
           │     ├── Poll every 1s while proc.poll() is None:
           │     │     ├── Check cancelled → proc.kill()
           │     │     ├── Estimate progress: elapsed / (size_mb / 2.0 MB/s)
           │     │     │     └── Cap at 95%
           │     │     └── Update: message, progress_pct, speed, eta
           │     │
           │     ├── On success (returncode == 0):
           │     │     ├── status = "done", progress_pct = 100
           │     │     └── _update_sidecar(file_path, "done")
           │     │
           │     └── On failure:
           │           ├── status = "failed"
           │           └── _update_sidecar(file_path, "failed")
           │
           └── On timeout/exception:
                 ├── Kill process
                 └── status = "failed"
```

---

## Key Data Shapes

### detect_content_folders response

```python
[
    {
        "name": "docs",
        "path": "docs",
        "file_count": 42,
        "total_size": 1_048_576,
        "encrypted_count": 3,
        "categories": {"document": 30, "image": 10, "config": 2},
    },
]
```

### list_folder_contents response

```python
[
    # File entry
    {
        "name": "readme.md",           # display name (.enc stripped)
        "path": "docs/readme.md",      # relative to project root
        "is_dir": False,
        "size": 2048,
        "category": "document",
        "mime_type": "text/markdown",
        "encrypted": False,
        "tier": "git",                 # or "large"
        "covault_meta": None,          # dict if encrypted
        "has_release": False,          # True if .release.json exists
        "release_status": "",          # "uploading", "done", "failed", "stale"
        "release_orphaned": False,     # True if no matching remote asset
    },
    # Directory entry
    {
        "name": "images",
        "path": "docs/images",
        "is_dir": True,
        "file_count": 15,
        "size": 524_288,
    },
]
```

Note: `.large/` subdirectory contents are merged into the parent listing
with `tier: "large"`. Hidden dot-dirs (`.backup/`, `.git/`) are excluded.

### list_folder_contents_recursive response

Same shape as `list_folder_contents`, with an additional field:

```python
{
    "subfolder": "images/icons",   # relative location within the folder
    # ... all other fields same as above
}
```

### upload_content_file response

```python
# Optimized upload
{
    "success": True,
    "name": "photo.webp",           # final name after optimization
    "path": "media/photo.webp",
    "original_name": "photo.png",
    "original_size": 180_000,
    "size": 45_000,
    "optimized": True,
    "tier": "git",
    "mime": "image/webp",
    "savings": 135_000,
    "savings_pct": 75.0,
}

# Large file upload (triggers release)
{
    "success": True,
    "name": "video.mp4",
    "path": "media/.large/video.mp4",
    "original_name": "video.mov",
    "original_size": 50_000_000,
    "size": 8_000_000,
    "optimized": True,
    "tier": "large",
    "mime": "video/mp4",
    "savings": 42_000_000,
    "savings_pct": 84.0,
    "release_upload": "video",      # file_id for status polling
}
```

### encrypt_content_file response

```python
{
    "success": True,
    "source": "docs/secret.md",
    "output": "docs/secret.md.enc",
    "original_size": 2048,
    "encrypted_size": 2200,
    "original_deleted": True,       # if delete_original=True
    "release_updated": True,        # if file was in .large/
}

# Error cases
{"error": "Invalid path"}
{"error": "File not found: docs/missing.md"}
{"error": "CONTENT_VAULT_ENC_KEY is not set in .env", "needs_key": True}
{"error": "Encryption failed: ...", "_status": 500}
```

### decrypt_content_file response

```python
{
    "success": True,
    "source": "docs/secret.md.enc",
    "output": "docs/secret.md",
    "decrypted_size": 2048,
    "encrypted_deleted": True,      # if delete_encrypted=True
    "release_updated": True,        # if file was in .large/
}
```

### optimize_media response (dispatcher)

```python
(
    optimized_bytes,    # bytes — optimized file content
    new_mime_type,      # "image/webp"
    new_extension,      # ".webp"
    was_optimized,      # True — False if unchanged
)
```

### release_inventory response

```python
{
    "gh_available": True,
    "remote_assets": ["video.mp4", "archive.tar.gz"],
    "local_sidecars": [
        {"name": "video.mp4", "path": "media/.large/video.mp4.release.json",
         "asset_name": "video.mp4", "meta": {...}},
    ],
    "orphaned": [
        {"name": "deleted.mp4", "path": "media/.large/deleted.mp4.release.json",
         "asset_name": "deleted.mp4"},
    ],
    "synced": [
        {"name": "video.mp4", "asset_name": "video.mp4"},
    ],
    "extra_remote": ["old-file.bin"],
}
```

### restore_large_files response

```python
{
    "gh_available": True,
    "restored": ["video.mp4"],
    "failed": [{"name": "broken.mp4", "error": "Download failed"}],
    "already_present": ["other.mp4"],
}
```

### save_encrypted_content response

```python
{"success": True, "size": 2200}   # encrypted file size
```

---

## Architecture

```
              Routes / CLI
                  │
                  │ imports
                  │
         ┌────────▼────────┐
         │  __init__.py     │  Public API re-exports
         └──┬──┬──┬──┬──┬──┘
            │  │  │  │  │
  ┌─────────┘  │  │  │  └────────────┐
  ▼            ▼  ▼  ▼               ▼
crypto.py   file_ops.py   optimize.py   release.py
(COVAULT    (CRUD:        (universal    (GitHub
 envelope,   create/del/   pipeline:     Release
 classify,   upload/save/  image/video/  upload, bg
 listing     rename/move)  audio/text)   thread, status)
 re-export)      │            │              │
  │         file_advanced.py  │         release_sync.py
  │         (restore,         │         (restore from
  │          sidecar check,   │          release,
  │          encrypted save)  │          inventory)
  │                           │
  └──────── crypto_ops.py ────┘
            (encrypt/decrypt
             with audit,
             release updates)
                              │
                         optimize_video.py
                         (ffmpeg pipeline,
                          NVENC detection,
                          progress tracking)
```

---

## Dependency Graph

```
crypto.py                               ← foundation layer
   │
   ├── cryptography (AESGCM, PBKDF2)    ← module level
   ├── listing.py (re-export)            ← at bottom of file
   └── crypto_ops.py (re-export)         ← at bottom of file

crypto_ops.py                            ← orchestration layer
   │
   ├── crypto.encrypt_file               ← module level
   ├── crypto.decrypt_file               ← module level
   ├── audit_helpers.make_auditor        ← module level
   ├── release.cleanup_release_sidecar   ← lazy (inside functions)
   └── release.upload_to_release_bg      ← lazy (inside functions)

listing.py                               ← read-only layer
   │
   ├── crypto._guess_mime                ← module level
   ├── crypto.classify_file              ← module level
   ├── crypto.is_covault_file            ← module level
   └── crypto.read_metadata              ← module level

file_ops.py                              ← CRUD layer
   │
   ├── audit_helpers.make_auditor        ← module level
   ├── crypto._guess_mime                ← re-exported at bottom
   ├── optimize.classify_storage         ← lazy (inside upload)
   ├── optimize.optimize_media           ← lazy (inside upload)
   ├── release.cleanup_release_sidecar   ← lazy (inside delete)
   ├── release.upload_to_release_bg      ← lazy (inside upload)
   └── file_advanced.* (re-export)       ← at bottom of file

file_advanced.py                         ← advanced ops layer
   │
   ├── audit_helpers.make_auditor        ← module level
   ├── release.restore_large_files       ← lazy (inside function)
   ├── release._release_upload_status    ← lazy (inside function)
   ├── release.list_release_assets       ← lazy (inside function)
   ├── crypto.decrypt_file_to_memory     ← lazy (inside function)
   └── crypto.encrypt_file               ← lazy (inside function)

optimize.py                              ← optimization dispatcher
   │
   ├── audit_helpers.make_auditor        ← module level
   └── optimize_video.* (re-export)      ← module level

optimize_video.py                        ← ffmpeg layer
   │
   ├── subprocess                        ← ffmpeg, ffprobe
   └── threading                         ← progress tracking

release.py                               ← upload layer
   │
   ├── audit_helpers.make_auditor        ← module level
   ├── subprocess                        ← gh CLI
   ├── threading                         ← background uploads
   └── release_sync.* (re-export)        ← at bottom of file

release_sync.py                          ← restore layer
   │
   ├── subprocess                        ← gh CLI
   └── crypto.DEFAULT_CONTENT_DIRS       ← lazy (inside function)
```

Key: Lazy imports (`├── ... ← lazy`) are inside function bodies to
avoid circular imports. Module-level imports run at import time.

### Dependency Rules

| Rule | Detail |
|------|--------|
| `crypto.py` is the foundation | All COVAULT operations + listing + classification |
| `listing.py` is read-only | Only imports from `crypto.py`, no mutations |
| `file_ops.py` imports `crypto.py` + `optimize.py` | Upload pipeline uses both |
| `crypto_ops.py` orchestrates `crypto.py` + `release.py` | High-level encrypt/decrypt with side effects |
| `optimize.py` delegates to `optimize_video.py` | Video/audio via ffmpeg |
| `release.py` handles upload, `release_sync.py` handles restore | Split by direction |
| `file_advanced.py` is the misc bucket | Operations that touch multiple concerns |
| Circular import prevention | `file_ops → release` and `crypto_ops → release` use lazy imports |

---

## File Map

```
content/
├── __init__.py         82 lines   — public API re-exports
├── crypto.py          469 lines   — COVAULT envelope encrypt/decrypt + classification
├── crypto_ops.py      208 lines   — high-level encrypt/decrypt with audit integration
├── file_ops.py        652 lines   — CRUD: create, delete, upload, save, rename, move
├── file_advanced.py   273 lines   — restore, folder listing, sidecar check, enc save
├── listing.py         341 lines   — folder detection, file scanning, size formatting
├── optimize.py        361 lines   — image + text optimization, storage classification
├── optimize_video.py  678 lines   — video/audio optimization via ffmpeg with NVENC
├── release.py         436 lines   — GitHub Release upload, sidecar management
├── release_sync.py    273 lines   — restore from release, release inventory
└── README.md                      — this file
```

---

## Per-File Documentation

### `crypto.py` — COVAULT Envelope (469 lines)

**Constants:**

| Constant | Type | Value |
|----------|------|-------|
| `MAGIC` | `bytes` | `b"COVAULT_v1"` (10 bytes) |
| `KDF_ITERATIONS` | `int` | 480,000 |
| `KDF_ITERATIONS_EXPORT` | `int` | 600,000 |
| `SALT_LEN` | `int` | 16 |
| `IV_LEN` | `int` | 12 |
| `TAG_LEN` | `int` | 16 |
| `SHA256_LEN` | `int` | 32 |
| `LEN_FIELD` | `int` | 2 |
| `_EXT_MIME` | `dict[str, str]` | 27-entry extension → MIME lookup |
| `IMAGE_EXTS` | `set` | 8 extensions |
| `VIDEO_EXTS` | `set` | 5 extensions |
| `AUDIO_EXTS` | `set` | 5 extensions |
| `DOC_EXTS` | `set` | 8 extensions |
| `CODE_EXTS` | `set` | 41 extensions |
| `SCRIPT_EXTS` | `set` | 11 extensions |
| `CONFIG_EXTS` | `set` | 11 extensions |
| `DATA_EXTS` | `set` | 10 extensions |
| `ARCHIVE_EXTS` | `set` | 7 extensions |
| `_CONFIG_FILENAMES` | `set` | 19 special filenames |

**Functions:**

| Function | Parameters | What It Does |
|----------|-----------|-------------|
| `encrypt_file(source, passphrase, output, iterations, *, original_filename)` | `Path, str, Path\|None, int, str` | Encrypt file → COVAULT binary envelope. `original_filename` overrides the name stored in the envelope header (used by `save_encrypted_content` when encrypting from temp files). |
| `decrypt_file(vault_path, passphrase, output, iterations)` | `Path, str, Path\|None, int` | Decrypt envelope → original file on disk |
| `decrypt_file_to_memory(vault_path, passphrase, iterations)` | `Path, str, int` | Decrypt to `(bytes, {"filename", "mime_type"})` without writing |
| `read_metadata(vault_path)` | `Path` | Read envelope header without decryption → `{filename, mime_type, encrypted_size, original_hash}` |
| `classify_file(path)` | `Path` | Classify by extension → one of 11 categories |
| `is_covault_file(path)` | `Path` | Check first 10 bytes match `COVAULT_v1` magic |
| `_guess_mime(filename)` | `str` | MIME lookup: strip `.enc`, check `_EXT_MIME`, fall back to stdlib |
| `_derive_key(passphrase, salt, iterations)` | `str, bytes, int` | PBKDF2-SHA256 → 32-byte key |
| `_parse_envelope(data)` | `bytes` | Parse binary envelope → `{filename, mime_type, sha256, salt, iv, tag, ciphertext}` |

**Re-exports at bottom of file:**

- From `listing.py`: `DEFAULT_CONTENT_DIRS`, `detect_content_folders`, `list_folder_contents`, `list_folder_contents_recursive`, `format_size`
- From `crypto_ops.py`: `encrypt_content_file`, `decrypt_content_file`

### `crypto_ops.py` — Orchestrated Encrypt/Decrypt (208 lines)

**Functions:**

| Function | Parameters | What It Does |
|----------|-----------|-------------|
| `encrypt_content_file(root, rel_path, passphrase, *, delete_original)` | `Path, str, str, bool` | Encrypt → optionally delete original → update release if in `.large/` → audit |
| `decrypt_content_file(root, rel_path, passphrase, *, delete_encrypted)` | `Path, str, str, bool` | Decrypt → optionally delete `.enc` → update release if in `.large/` → audit |

Both functions follow the same pattern:
1. Resolve path + safety check (within project root)
2. Validate passphrase exists
3. Call `encrypt_file()` / `decrypt_file()`
4. Optionally delete source
5. If file is in `.large/` → cleanup old sidecar + re-upload new form
6. Audit with before/after state
7. Return result dict or `{"error": ...}`

### `file_ops.py` — CRUD Operations (652 lines)

**Functions:**

| Function | Parameters | What It Does |
|----------|-----------|-------------|
| `resolve_safe_path(root, rel)` | `Path, str` | Prevent directory traversal → `Path\|None` |
| `create_content_folder(root, name)` | `Path, str` | Create folder + `.gitkeep` + validate no separators |
| `delete_content_file(root, rel_path)` | `Path, str` | Delete file/dir + release sidecar cleanup + before-state audit |
| `upload_content_file(root, folder, name, data)` | `Path, str, str, bytes` | Full pipeline: optimize → classify → store → audit → release |
| `setup_enc_key(root, key, generate)` | `Path, str, bool` | Set/generate `CONTENT_VAULT_ENC_KEY` in `.env` (under `# ── Content Vault` section) |
| `save_content_file(root, rel_path, content)` | `Path, str, str` | Write text to existing file + unified diff audit |
| `rename_content_file(root, rel_path, new_name)` | `Path, str, str` | Rename with sidecar `old_asset_name` tracking |
| `move_content_file(root, rel_path, dest_folder)` | `Path, str, str` | Move between folders + sidecar follows |

**Safety constraints in `delete_content_file` and `save_content_file`:**

```python
# Only allow operations within known content folders
top_dir = rel.parts[0]
if top_dir not in DEFAULT_CONTENT_DIRS:
    return {"error": "Can only ... within content folders", "_status": 403}
```

**Re-exports at bottom of file:**

- From `crypto.py`: `_EXT_MIME`, `_guess_mime`
- From `file_advanced.py`: `restore_large_files_from_release`, `list_all_project_folders`, `check_release_sidecar`, `save_encrypted_content`

### `file_advanced.py` — Advanced Operations (273 lines)

**Constants:**

| Constant | Type | Contents |
|----------|------|---------|
| `_EXCLUDED_DIRS` | `set` | 19 directories excluded from folder listing |

**Functions:**

| Function | Parameters | What It Does |
|----------|-----------|-------------|
| `restore_large_files_from_release(root)` | `Path` | Delegate to `release.restore_large_files()` + audit |
| `list_all_project_folders(root)` | `Path` | List top-level dirs minus `_EXCLUDED_DIRS` (for "Explore All") |
| `check_release_sidecar(target, root)` | `Path, Path` | Read `.release.json`, detect stale "uploading", check orphan status |
| `save_encrypted_content(target, content, passphrase, rel_path)` | `Path, str, str, str` | Decrypt → re-encrypt with new content → compute unified diff → audit |

**`save_encrypted_content` flow:**

```
1. decrypt_file_to_memory(target, passphrase) → old plaintext
2. Write new content to temp file
3. encrypt_file(tmp_path, passphrase, output_path=target, original_filename=...)
4. Compute unified diff (old vs new, capped at 50 lines)
5. Audit with added/removed line counts + diff snippet
```

### `listing.py` — Folder Detection & Scanning (341 lines)

**Constants:**

| Constant | Type | Value |
|----------|------|-------|
| `DEFAULT_CONTENT_DIRS` | `list[str]` | `["docs", "content", "media", "assets", "archive"]` |

**Functions:**

| Function | Parameters | What It Does |
|----------|-----------|-------------|
| `detect_content_folders(root)` | `Path` | Check `project.yml` for `content_folders` → fall back to `DEFAULT_CONTENT_DIRS` → scan each |
| `_scan_folder(folder, root)` | `Path, Path` | `rglob("*")` → count files, total size, categories, encrypted count |
| `list_folder_contents(folder, root, include_hidden, remote_assets)` | `Path, Path, bool, set\|None` | List files with metadata, COVAULT envelope info, release sidecar status |
| `list_folder_contents_recursive(folder, root, include_hidden, remote_assets)` | `Path, Path, bool, set\|None` | Same as above but walks entire subtree, adds `subfolder` field |
| `format_size(size_bytes)` | `int` | → `"1.5 MB"` human-readable string |

**`.large/` virtual directory behavior:**

```
list_folder_contents(media/)
     │
     ├── Iterate sorted(folder.iterdir()):
     │     ├── .large/ dir → merge contents with tier="large"
     │     ├── Other dot-dirs → skip entirely
     │     ├── Regular dirs → include as {is_dir: True, file_count, size}
     │     └── Regular files → _add_file(f, tier="git")
     │
     └── _add_file(f):
           ├── Skip hidden files (unless include_hidden)
           ├── Skip .release.json sidecars
           ├── Detect COVAULT: f.suffix == ".enc" AND is_covault_file(f)
           ├── Display name: strip .enc for foo.md.enc → foo.md
           ├── Read envelope metadata if encrypted
           ├── Check release sidecar:
           │     ├── Detect stale "uploading" (no live upload thread)
           │     └── Orphan check (asset not in remote_assets set)
           └── Append entry dict
```

### `optimize.py` — Optimization Pipeline (361 lines)

**Constants:**

| Constant | Value | Purpose |
|----------|-------|---------|
| `MAX_DIMENSION` | 2048 px | Longest side for image resize |
| `WEBP_QUALITY` | 85 | Lossy WebP quality |
| `JPEG_QUALITY` | 85 | Fallback JPEG quality |
| `TARGET_FORMAT` | `"WEBP"` | Preferred image output |
| `VIDEO_MAX_HEIGHT` | 1080 px | Max vertical resolution |
| `VIDEO_BITRATE` | `"1500k"` | Video bitrate cap |
| `AUDIO_BITRATE` | `"96k"` | Audio bitrate cap |
| `VIDEO_CRF` | 28 | H.264 constant rate factor |
| `VIDEO_SKIP_BELOW` | 10 MB | Don't re-encode videos under this |
| `TEXT_COMPRESS_THRESHOLD` | 100 KB | Gzip text files above this |
| `LARGE_THRESHOLD_BYTES` | 2 MB | Storage tier boundary |
| `IMAGE_OPTIMIZE_THRESHOLD` | 100 KB | Optimize images above this |
| `COMPRESSIBLE_MIMES` | 13 types | MIME types eligible for gzip |
| `COMPRESSIBLE_EXTENSIONS` | 17 exts | Extensions eligible for gzip |

**Functions:**

| Function | Parameters | What It Does |
|----------|-----------|-------------|
| `optimize_image(data, mime, *, max_dimension, quality, target_format)` | `bytes, str, int, int, str` | Resize + convert to WebP. Skip SVG/GIF. Requires Pillow. |
| `optimize_text(data, mime, original_name)` | `bytes, str, str` | Gzip compress if > 100 KB and smaller result |
| `optimize_media(data, mime, original_name)` | `bytes, str, str` | Universal dispatcher: image → video → audio → text → fallback gzip |
| `should_optimize_image(size_bytes, mime)` | `int, str` | Decision: `image/*` AND > 100 KB AND not SVG/GIF |
| `classify_storage(size_bytes)` | `int` | → `"git"` (≤ 2 MB) or `"large"` (> 2 MB) |
| `_is_compressible(mime, name)` | `str, str` | Check MIME set + extension set |
| `_has_meaningful_alpha(img)` | `PIL.Image` | Check if RGBA actually uses transparency |
| `_mime_to_ext(mime)` | `str` | `"image/webp"` → `".webp"` (7 entries) |

**Re-exports from `optimize_video.py`:**

- `optimize_video`, `optimize_audio`, `cancel_active_optimization`, `get_optimization_status`, `extend_optimization`

### `optimize_video.py` — ffmpeg Pipeline (678 lines)

**Module-level state:**

| Variable | Type | Purpose |
|----------|------|---------|
| `_hw_encoder_cache` | `dict` | Caches NVENC detection result |
| `_active_ffmpeg_proc` | `Popen\|None` | Active process (for cancellation) |
| `_optimization_state` | `dict` | Frontend polling state |

**Functions:**

| Function | Parameters | What It Does |
|----------|-----------|-------------|
| `optimize_video(data, mime, *, max_height, video_bitrate, audio_bitrate, crf)` | `bytes, str, int, str, str, int` | Smart video re-encode: probe → decide → encode → compare sizes |
| `optimize_audio(data, mime, *, bitrate)` | `bytes, str, str` | Audio → AAC M4A (96 kbps) |
| `cancel_active_optimization()` | — | Kill active ffmpeg process |
| `get_optimization_status()` | — | Return current `_optimization_state` dict |
| `extend_optimization(extra_seconds)` | `int` | Push deadline forward (default 300s) |
| `_parse_ffmpeg_progress(line)` | `str` | Extract frame, fps, size, time from stderr |
| `_ffmpeg_available()` | — | `shutil.which("ffmpeg")` |
| `_detect_hw_encoder()` | — | Test NVENC by running tiny encode (cached) |
| `_probe_media(path)` | `Path` | `ffprobe -v error -of json` → codec, resolution, bitrate |
| `_needs_video_reencode(probe, size, max_height)` | `dict, int, int` | Skip if < 10 MB; always try for larger files |
| `_build_scale_filter(path, max_height)` | `Path, int` | ffprobe dimensions → `scale=-2:1080` if needed |
| `_ext_for_video_mime(mime)` | `str` | → `.mp4`, `.webm`, `.mov`, `.avi`, `.mkv`, `.ogv`, `.3gp` (7 entries) |
| `_ext_for_audio_mime(mime)` | `str` | → `.mp3`, `.m4a`, `.aac`, `.ogg`, `.wav`, `.weba`, `.flac` (9 entries, incl. `x-wav`, `x-flac` variants) |

**Video optimization defaults:**

| Parameter | Value |
|-----------|-------|
| Max height | 1080p |
| Video CRF | 28 |
| Video bitrate cap | 1500k (1.5 Mbps) |
| Audio bitrate | 96k |
| Skip below | 10 MB |
| Target format | H.264 MP4 |
| GPU encoder | NVENC h264_nvenc (auto-detected, cached) |
| CPU encoder | libx264 |
| GPU preset | medium |
| CPU preset | fast |

### `release.py` — GitHub Release Sync (436 lines)

**Constants:**

| Constant | Type | Value |
|----------|------|-------|
| `CONTENT_RELEASE_TAG` | `str` | `"content-vault"` |

**Module-level state:**

| Variable | Type | Purpose |
|----------|------|---------|
| `_release_upload_status` | `dict[str, dict]` | In-memory upload status per `file_id` |
| `_release_active_procs` | `dict[str, Popen]` | Active subprocess refs for cancellation |

**Functions:**

| Function | Parameters | What It Does |
|----------|-----------|-------------|
| `upload_to_release_bg(file_id, path, root)` | `str, Path, Path` | Background daemon thread: ensure release exists → `gh release upload --clobber` → poll progress |
| `cleanup_release_sidecar(file_path, root)` | `Path, Path` | Delete `.release.json` + remote asset. Safe if no sidecar. |
| `remove_orphaned_sidecar(file_path)` | `Path` | Delete sidecar only (no remote deletion) |
| `get_release_status(file_id)` | `str` | Return `_release_upload_status[file_id]` or `None` |
| `get_all_release_statuses()` | — | Return copy of all upload statuses |
| `cancel_release_upload(file_id)` | `str` | Set status to "cancelled" + `proc.kill()` |
| `delete_release_asset(name, root)` | `str, Path` | Fire-and-forget `gh release delete-asset` via Popen |
| `_update_sidecar(file_path, status)` | `Path, str` | Read `.release.json`, update `status` field, write back |

**Re-exports from `release_sync.py`:**

- `restore_large_files`, `list_release_assets`, `release_inventory`

### `release_sync.py` — Restore & Inventory (273 lines)

**Constants:**

| Constant | Type | Value |
|----------|------|-------|
| `CONTENT_RELEASE_TAG` | `str` | `"content-vault"` (duplicated for independence) |

**Functions:**

| Function | Parameters | What It Does |
|----------|-----------|-------------|
| `restore_large_files(root)` | `Path` | Scan `.large/` dirs → list remote assets → `gh release download` missing ones |
| `list_release_assets(root)` | `Path` | `gh release view content-vault --json assets` → parse JSON lines |
| `release_inventory(root)` | `Path` | Cross-reference local `.release.json` sidecars with remote assets → orphaned/synced/extra |

**`release_inventory` cross-reference logic:**

```
1. Fetch remote asset names → remote_names set
2. Scan DEFAULT_CONTENT_DIRS + .backup/ → find all *.release.json
3. For each sidecar:
   └── asset_name = old_asset_name or asset_name or filename
4. orphaned = sidecars whose asset_name NOT in remote_names
5. synced = sidecars whose asset_name IN remote_names
6. extra_remote = remote_names minus all sidecar asset_names
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| **Web Routes** | `routes/content/files.py` | `list_folder_contents`, `upload_content_file`, `delete_content_file`, `save_content_file` |
| **Web Routes** | `routes/content/manage.py` | `encrypt_content_file`, `decrypt_content_file`, `rename_content_file`, `move_content_file`, `setup_enc_key` |
| **Web Routes** | `routes/content/preview.py` | `decrypt_file_to_memory`, `read_metadata`, `classify_file` |
| **Web Routes** | `routes/content/__init__.py` | Blueprint registration |
| **CLI** | `cli/content/crypto.py` | `encrypt_file`, `decrypt_file`, `read_metadata` |
| **CLI** | `cli/content/optimize.py` | `optimize_media`, `optimize_image` |
| **CLI** | `cli/content/release.py` | `restore_large_files`, `list_release_assets`, `release_inventory` |
| **Services** | `backup/archive.py` | `classify_file` |
| **Services** | `backup/common.py` | `classify_file` |
| **Services** | `backup/restore.py` | `classify_file` |
| **Services** | `backup/extras.py` | `classify_file` |
| **Services** | `chat/chat_refs.py` | `classify_file` |

---

## Backward Compatibility

The module uses re-exports at the bottom of several files to maintain
backward compatibility:

```python
# crypto.py re-exports from listing.py and crypto_ops.py
from .listing import DEFAULT_CONTENT_DIRS, detect_content_folders, ...
from .crypto_ops import encrypt_content_file, decrypt_content_file

# file_ops.py re-exports from file_advanced.py
from .file_advanced import restore_large_files_from_release, ...

# release.py re-exports from release_sync.py
from .release_sync import restore_large_files, list_release_assets, release_inventory
```

Old import paths like `from content.crypto import detect_content_folders`
continue to work even though the function lives in `listing.py`.

---

## Error Handling

| Function | Can Fail? | Error Shape |
|----------|----------|-------------|
| `encrypt_file` | Yes | Raises `FileNotFoundError`, `ValueError` |
| `decrypt_file` | Yes | Raises `FileNotFoundError`, `ValueError` ("Wrong passphrase", "corrupted") |
| `decrypt_file_to_memory` | Yes | Same as `decrypt_file` |
| `_parse_envelope` | Yes | Raises `ValueError` for truncated/invalid envelopes |
| `create_content_folder` | Validation | `{"error": "Invalid folder name"}`, `409` if exists |
| `delete_content_file` | Safety | `403` if outside content folders, `404` if not found |
| `upload_content_file` | Pipeline | `{"error": "Invalid folder path"}` |
| `save_content_file` | Safety | `403` if outside content folders, `404` if not found |
| `rename_content_file` | Conflict | `409` if destination exists, `404` if source missing |
| `move_content_file` | Conflict | `409` if destination exists, `404` if source missing |
| `setup_enc_key` | Validation | `{"error": "Encryption key must be at least 8 characters"}` |
| `encrypt_content_file` | Pipeline | `{"error": "...", "needs_key": True}` if no passphrase |
| `decrypt_content_file` | Pipeline | Same as above |
| `upload_to_release_bg` | Silent | Failures logged + status dict updated (no exceptions) |
| `optimize_image` | Graceful | Returns original data on failure (Pillow not installed, etc.) |
| `optimize_video` | Graceful | Returns original data if ffmpeg unavailable or re-encode larger |
| `restore_large_files` | Partial | Returns lists of restored/failed/skipped (never raises) |

---

## Audit Trail

All audit entries use `make_auditor("content")`.

| Event | Icon | Action | Target |
|-------|------|--------|--------|
| File uploaded | ⬆️ | `created` | `<folder>/<file>` |
| File deleted | 🗑️ | `deleted` | `<rel_path>` |
| File renamed | ✏️ | `renamed` | `<new_path>` |
| File moved | 📦 | `moved` | `<dest_path>` |
| File saved (text) | 📝 | `modified` | `<rel_path>` |
| File saved (encrypted) | 📝 | `modified` | `<rel_path>` |
| File encrypted | 🔒 | `encrypted` | `<output_path>` |
| File decrypted | 🔓 | `decrypted` | `<output_path>` |
| Encrypt failed | ❌ | — | `<rel_path>` |
| Decrypt failed | ❌ | — | `<rel_path>` |
| Folder created | 📁 | `created` | `<name>` |
| Enc key configured | 🔐 | `configured` | `CONTENT_VAULT_ENC_KEY` |
| Large files restored | ⬇️ | `restored` | `content-vault` |

---

## Advanced Feature Showcase

### 1. COVAULT Binary Envelope — Position-Tracked Field Parsing

The `_parse_envelope` function in `crypto.py` implements a binary protocol
parser that reads variable-length fields from a byte stream using a manual
cursor (`pos`). Each field has boundary checks to catch truncation:

```python
# crypto.py — _parse_envelope (lines 327-394)

MAGIC = b"COVAULT_v1"        # 10 bytes
LEN_FIELD = 2                # uint16 little-endian

def _parse_envelope(data: bytes) -> dict:
    if data[:MAGIC_LEN] != MAGIC:
        raise ValueError("Not a COVAULT file — magic bytes mismatch")

    pos = MAGIC_LEN

    # Variable-length filename
    fn_len = struct.unpack("<H", data[pos:pos + LEN_FIELD])[0]
    pos += LEN_FIELD
    filename = data[pos:pos + fn_len].decode("utf-8")
    pos += fn_len

    # Variable-length MIME type
    mime_len = struct.unpack("<H", data[pos:pos + LEN_FIELD])[0]
    pos += LEN_FIELD
    mime_type = data[pos:pos + mime_len].decode("utf-8")
    pos += mime_len

    # Fixed-length crypto fields
    sha256 = data[pos:pos + 32]; pos += 32   # integrity hash
    salt   = data[pos:pos + 16]; pos += 16   # KDF salt
    iv     = data[pos:pos + 12]; pos += 12   # AES-GCM nonce
    tag    = data[pos:pos + 16]; pos += 16   # auth tag

    ciphertext = data[pos:]  # remainder
```

Why this matters: the variable-length filename/MIME fields mean the envelope
can store any filename regardless of length, while the fixed-offset crypto
fields after them are still parseable without decryption — enabling
`read_metadata()` to display file info in the UI without knowing the passphrase.

### 2. Adaptive Encoding Timeout with Soft Deadline + Grace Period

Video encoding can take anywhere from seconds to hours. `optimize_video` in
`optimize_video.py` implements a three-stage timeout system:

```python
# optimize_video.py — optimize_video (lines 376-537)

# Stage 1: Adaptive timeout from media duration
if duration_sec > 0:
    timeout_secs = max(900, min(14400, int(duration_sec * 1.5)))
else:
    timeout_secs = max(900, min(14400, int(size_mb / 50 * 180)))

# Stage 2: GPU gets a tighter deadline (NVENC is 10-30× faster)
if hw_encoder == "h264_nvenc":
    if duration_sec > 0:
        timeout_secs = max(300, min(3600, int(duration_sec * 0.3)))

# Stage 3: Soft deadline with grace period + user extension
while True:
    elapsed = _time.monotonic() - start_time
    current_deadline = _optimization_state.get("deadline", timeout_secs)

    if elapsed > current_deadline:
        if not _optimization_state.get("deadline_warning"):
            _optimization_state["deadline_warning"] = True
            grace_deadline = _time.monotonic() + 60  # 60s grace
        elif grace_deadline and _time.monotonic() > grace_deadline:
            proc.kill()  # only after grace expires
```

The frontend polls `get_optimization_status()` and can call
`extend_optimization(extra_seconds=300)` to push the deadline forward,
preventing premature kills of legitimate long encodes.

### 3. GPU Encoder Detection with Runtime Verification

`_detect_hw_encoder` in `optimize_video.py` doesn't just check if NVENC is
listed — it verifies it actually works by running a real encode:

```python
# optimize_video.py — _detect_hw_encoder (lines 141-182)

# Step 1: Check if h264_nvenc is listed in ffmpeg
check = subprocess.run(["ffmpeg", "-encoders"], ...)
if "h264_nvenc" not in check.stdout:
    return None

# Step 2: Actually try encoding (some systems list it but lack GPU drivers)
test = subprocess.run(
    ["ffmpeg", "-y", "-f", "lavfi",
     "-i", "color=c=black:s=256x256:d=0.1:r=30",
     "-c:v", "h264_nvenc", "-f", "null", "-"],
    ...
)
if test.returncode == 0:
    _hw_encoder_cache["h264"] = "h264_nvenc"  # cached for process lifetime
```

This catches the real-world scenario where NVENC is installed but broken
(wrong driver version, no GPU), avoiding a full video encode that would fail
30 minutes in.

### 4. Universal Optimization Dispatcher with 5-Tier Fallback

`optimize_media` in `optimize.py` routes every upload through the right
optimizer, with a final fallback for unknown types:

```python
# optimize.py — optimize_media (lines 243-309)

def optimize_media(data, mime_type, original_name=""):
    # Tier 1: Images → Pillow resize + WebP conversion
    if should_optimize_image(len(data), mime_type):
        opt_data, opt_mime, opt_ext = optimize_image(data, mime_type)
        return opt_data, opt_mime, opt_ext, len(opt_data) < len(data)

    # Tier 2: Video → ffmpeg H.264/NVENC re-encode
    if mime_type.startswith("video/"):
        ...

    # Tier 3: Audio → ffmpeg AAC M4A
    if mime_type.startswith("audio/"):
        ...

    # Tier 4: Text/documents → gzip (> 100 KB)
    if _is_compressible(mime_type, original_name):
        return optimize_text(data, mime_type, original_name)

    # Tier 5: Unknown but large → try gzip anyway
    skip_mimes = {"application/zip", "application/gzip", ...}
    if mime_type not in skip_mimes and len(data) > TEXT_COMPRESS_THRESHOLD:
        compressed = gzip.compress(data, compresslevel=6)
        if len(compressed) < len(data) * 0.9:  # only keep if 10%+ savings
            return compressed, mime_type, base_ext + ".gz", True

    # Tier 6: No optimization available — return unchanged
    return data, mime_type, ext, False
```

Key design: every tier returns original data on failure. Uploaded files are
**never lost** due to optimization errors.

### 5. Background Release Upload with Estimated Progress

`upload_to_release_bg` in `release.py` runs `gh release upload` in a daemon
thread with synthetic progress tracking (since `gh` CLI doesn't emit progress):

```python
# release.py — upload_to_release_bg (lines 127-356)

# Assumed speed for progress estimation
assumed_speed_mbps = 2.0
estimated_total_sec = max(size_mb / assumed_speed_mbps, 5)

while proc.poll() is None:
    # Check for user cancellation
    if _release_upload_status.get(file_id, {}).get("status") == "cancelled":
        proc.kill()
        return

    elapsed = time.time() - upload_start
    est_pct = min(95, int((elapsed / estimated_total_sec) * 100))

    # Speed estimate from elapsed time
    if elapsed > 2:
        speed_str = f"{size_mb / elapsed:.1f} MB/s est."

    # ETA calculation
    eta_sec = max(0, estimated_total_sec - elapsed)
    if eta_sec > 60:
        eta_str = f"~{int(eta_sec / 60)}m {int(eta_sec % 60)}s left"

    _release_upload_status[file_id].update({
        "progress_pct": est_pct,
        "speed": speed_str,
        "eta": eta_str,
    })
```

The progress caps at 95% because we don't know it's truly done until `proc`
exits with returncode 0. The sidecar is updated to `"done"` or `"failed"`
on disk after completion.

### 6. Release Inventory — 3-Way Cross-Reference

`release_inventory` in `release_sync.py` reconciles three data sources to
detect drift between local state and GitHub:

```python
# release_sync.py — release_inventory (lines 192-272)

# Source 1: Fetch remote asset names from GitHub
remote = list_release_assets(project_root)
remote_names = {a["name"] for a in remote["assets"]}

# Source 2: Scan local sidecars across all content + backup dirs
scan_dirs = [project_root / d for d in DEFAULT_CONTENT_DIRS]
for d in scan_dirs[:]:
    backup_dir = d / ".backup"
    if backup_dir.is_dir():
        scan_dirs.append(backup_dir)  # also scan backups

for meta_file in scan_dir.rglob("*.release.json"):
    asset_name = (
        meta.get("old_asset_name")    # renamed file → track old name
        or meta.get("asset_name")      # current name
        or ref_name                    # fallback to filename
    )

# Source 3: Cross-reference
sidecar_asset_names = {s["asset_name"] for s in local_sidecars}
orphaned    = [s for s in local_sidecars if s["asset_name"] not in remote_names]
synced      = [s for s in local_sidecars if s["asset_name"] in remote_names]
extra_remote = sorted(remote_names - sidecar_asset_names)
```

The `old_asset_name` check is critical: when a file is renamed via
`rename_content_file`, the sidecar stores both the old and new asset names
so the inventory can still match against the remote.

### 7. Save-Encrypted-Content Round-Trip

`save_encrypted_content` in `file_advanced.py` performs a full decrypt →
edit → re-encrypt cycle with unified diff and audit:

```python
# file_advanced.py — save_encrypted_content (lines 165-272)

# 1. Decrypt to get old content + preserved metadata
old_plaintext, meta = decrypt_file_to_memory(target, passphrase)
original_name = meta["filename"]  # preserves original name through re-encrypt

# 2. Write new content to temp file
with tempfile.NamedTemporaryFile(
    suffix=Path(original_name).suffix,
    prefix=Path(original_name).stem + "_",
) as tmp:
    tmp.write(content.encode("utf-8"))

# 3. Re-encrypt with original_filename so envelope identity is preserved
encrypt_file(tmp_path, passphrase, output_path=target,
             original_filename=original_name)

# 4. Compute unified diff (capped at 50 lines for audit storage)
diff_lines = list(difflib.unified_diff(
    old_lines_list, new_lines_list,
    fromfile=f"a/{rel_path}", tofile=f"b/{rel_path}",
))
added = sum(1 for ln in diff_lines
            if ln.startswith("+") and not ln.startswith("+++"))
removed = sum(1 for ln in diff_lines
              if ln.startswith("-") and not ln.startswith("---"))
diff_text = "\n".join(diff_lines[:50])
if len(diff_lines) > 50:
    diff_text += f"\n... ({len(diff_lines) - 50} more lines)"
```

This is where `encrypt_file`'s `original_filename` parameter is essential:
without it, editing an encrypted `notes.md.enc` would re-encrypt under a
temp filename like `notes_abc123.md.enc`.

### 8. Stale Upload Detection in Sidecar Check

`check_release_sidecar` in `file_advanced.py` detects when a sidecar claims
`"uploading"` but no upload thread is actually running:

```python
# file_advanced.py — check_release_sidecar (lines 89-159)

sidecar = json.loads(meta_path.read_text())
release_status = sidecar.get("status", "unknown")

# Detect stale "uploading" — no active upload thread
if release_status == "uploading":
    _fid = sidecar.get("file_id", "")
    from .release import _release_upload_status
    live = _release_upload_status.get(_fid, {})
    if not live or live.get("status") not in ("uploading", "queued"):
        release_status = "stale"

# Orphan check: skip only genuinely active uploads
if release_status != "uploading":
    asset_name = (
        sidecar.get("old_asset_name")
        or sidecar.get("asset_name")
        or target.name
    )
    remote = list_release_assets(project_root)
    if remote.get("available"):
        remote_names = {a["name"] for a in remote["assets"]}
        if asset_name not in remote_names:
            release_orphaned = True
    else:
        release_orphaned = True  # no release → sidecar is orphaned
```

This prevents the UI from showing a permanent "uploading…" spinner after a
server restart, and also detects when someone manually deleted the GitHub
Release asset without cleaning up the local sidecar.

---

### Feature Coverage Summary

| Feature | Where | Complexity |
|---------|-------|-----------|
| Binary protocol parsing with variable-length fields | `crypto.py` `_parse_envelope` | Position-tracked cursor, 7 fields, bounds-checked |
| Adaptive timeout with user extensibility | `optimize_video.py` `optimize_video` | Duration-based + GPU-aware + grace period + frontend extension |
| GPU encoder runtime verification | `optimize_video.py` `_detect_hw_encoder` | List check + actual test encode + process-lifetime cache |
| 5-tier optimization dispatch | `optimize.py` `optimize_media` | Image → Video → Audio → Text → Generic gzip → passthrough |
| Background upload with synthetic progress | `release.py` `upload_to_release_bg` | Daemon thread, speed estimation, cancellation, sidecar sync |
| 3-way release inventory reconciliation | `release_sync.py` `release_inventory` | Remote assets × local sidecars × old_asset_name tracking |
| Encrypted file edit round-trip | `file_advanced.py` `save_encrypted_content` | Decrypt → edit → re-encrypt preserving identity + unified diff |
| Stale upload detection | `file_advanced.py` `check_release_sidecar` | In-memory status × on-disk sidecar × remote asset existence |

---

## Design Decisions


### Why COVAULT binary format instead of GPG or age?

COVAULT is purpose-built for content files: it stores the original
filename and MIME type in the envelope header, so decryption restores
the exact file identity. GPG/.age don't embed this metadata natively.
The format also uses a fixed-size header that can be read without
decrypting, enabling `read_metadata()` for UI display.

### Why PBKDF2 instead of Argon2 for content encryption?

PBKDF2 with 480K iterations is available in Python via `cryptography`,
requires no system library (unlike Argon2), and can be used across all
deployment targets. The content encryption key is typically auto-generated
(high entropy), making brute-force resistance less critical.

### Why optimize on upload instead of on demand?

Optimizing at upload time means every stored file is already in its
optimal format. This avoids serving unoptimized originals, prevents
"forgot to optimize" scenarios, and ensures storage classification
(git vs large) is based on the final size. The tradeoff is slower
uploads, but the optimization pipeline is designed to be fast
(subsecond for images, minutes for video).

### Why a two-tier storage model (git / large)?

Git repositories shouldn't contain files > 2 MB — they bloat
`.git/objects` and slow down clone/fetch operations. The `.large/`
subfolder + GitHub Release approach keeps large media accessible
without polluting the repository. The `restore_large_files` function
makes cloning seamless: run once after clone to pull down large assets.

### Why background threads for release uploads?

GitHub Release uploads can take minutes for large video files.
Running them synchronously would block the upload API and make the
UI unresponsive. Background threads with in-memory status tracking
let the UI poll for progress and offer cancellation.

### Why separate crypto.py from crypto_ops.py?

`crypto.py` is pure cryptography: encrypt bytes, decrypt bytes.
`crypto_ops.py` adds orchestration: audit logging, release artifact
updates, original file deletion. This separation means the crypto
module can be tested without side effects, and the orchestration
layer can be modified without touching the encryption logic.

### Why detect_content_folders uses project.yml fallback?

The `content_folders` key in `project.yml` lets users explicitly
configure which folders are content. The fallback to
`DEFAULT_CONTENT_DIRS` (`docs`, `content`, `media`, `assets`, `archive`)
ensures zero-config operation for standard project layouts while
allowing customization for non-standard structures.

### Why file_ops.py is the largest file (652 lines)?

It handles 8 distinct CRUD operations (create, delete, upload, save,
rename, move, setup enc key, path resolution), each with its own
validation, safety checks, audit logging, and sidecar management.
The upload function alone is 156 lines because it orchestrates the
full optimization → classification → storage → release pipeline.

### Why CRF 28 instead of lower?

H.264 CRF 28 produces visually acceptable quality at significantly
smaller file sizes. For content vault purposes (personal media, project
assets), the quality trade-off is worthwhile — the original is always
kept if the re-encode is larger. CRF 23 was initially considered but
produces files roughly 2× larger with minimal visible improvement
at 1080p.
