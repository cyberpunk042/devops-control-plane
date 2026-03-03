# CLI Domain: Content — Encryption, Optimization & Release Management

> **4 files · 345 lines · 8 commands + 1 subgroup · Group: `controlplane content`**
>
> Three concern areas in one domain: COVAULT file encryption (encrypt,
> decrypt, inspect, classify), media optimization (folder detection,
> format conversion with storage tier classification), and GitHub Release
> asset management (list, restore, inventory for large-file storage).
>
> Core services: `core/services/content/crypto.py`, `core/services/content/optimize.py`,
> `core/services/content/release.py`

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                       controlplane content                          │
│                                                                      │
│  ┌── Crypto ──────────┐  ┌── Optimize ────┐  ┌── Release ────────┐ │
│  │ encrypt            │  │ folders        │  │ release list      │ │
│  │ decrypt            │  │ optimize       │  │ release restore   │ │
│  │ inspect            │  └────────────────┘  │ release inventory │ │
│  │ classify           │                       └──────────────────-┘ │
│  └────────────────────┘                                              │
└────────┬─────────────────────┬────────────────────┬─────────────────┘
         │                     │                    │
         ▼                     ▼                    ▼
┌─────────────────┐  ┌──────────────────┐  ┌───────────────────────┐
│ content/crypto  │  │ content/optimize │  │   content/release     │
│                 │  │                  │  │                       │
│ encrypt_file()  │  │ optimize_media() │  │ list_release_assets() │
│ decrypt_file()  │  │ classify_storage │  │ restore_large_files() │
│ read_metadata() │  │                  │  │ release_inventory()   │
│ classify_file() │  │ content/crypto   │  │                       │
│                 │  │ detect_folders() │  │ content/crypto        │
│                 │  │ format_size()    │  │ format_size()         │
└─────────────────┘  └──────────────────┘  └───────────────────────┘
```

### COVAULT Encryption

The encryption subsystem uses a custom binary envelope format (`.enc`)
that embeds metadata (original filename, MIME type, SHA-256 hash)
alongside the encrypted payload.

```
┌─────────────────────────────────────────┐
│  .enc file (COVAULT binary envelope)    │
│                                          │
│  ┌── Header ───────────────────────────┐│
│  │ magic bytes, version, metadata JSON ││
│  │ (filename, mime, hash, timestamps)  ││
│  └─────────────────────────────────────┘│
│  ┌── Payload ──────────────────────────┐│
│  │ AES-encrypted file content          ││
│  └─────────────────────────────────────┘│
└─────────────────────────────────────────┘
```

The `inspect` command reads the header without decrypting the payload,
so you can identify files without the passphrase.

### Media Optimization

```
optimize("photo.jpg")
├── Read file bytes + detect MIME type
├── optimize_media(data, mime, name)
│   ├── image/* → convert to WebP
│   ├── video/* → re-encode H.264
│   ├── text/*  → gzip compress
│   └── other   → no-op (was_optimized=false)
├── classify_storage(new_size)
│   ├── < 1 MB   → "git"       (track in repo)
│   ├── < 50 MB  → "lfs"       (Git LFS)
│   └── ≥ 50 MB  → "release"   (GitHub Release)
└── Write optimized file + report savings
```

### Release Asset Management

For files too large for Git LFS (≥ 50 MB), the project uses GitHub
Releases as a content storage layer. Each large file gets a `.sidecar`
JSON file tracked in Git that records the release asset information.

```
release restore
├── Scan project for .sidecar files
├── For each sidecar:
│   ├── Local file present? → skip
│   └── Missing? → gh release download → restore
└── Report restored / already_present / failed

release inventory
├── Read all local .sidecar files
├── Query GitHub Release for all assets
├── Cross-reference:
│   ├── synced    → sidecar + remote match
│   ├── orphaned  → sidecar but no remote asset
│   └── extra     → remote asset but no sidecar
└── Report discrepancies
```

---

## Commands

### `controlplane content encrypt FILE`

Encrypt a file into a COVAULT binary envelope (`.enc`).

```bash
# Interactive passphrase prompt
controlplane content encrypt photo.jpg

# Specify passphrase inline
controlplane content encrypt photo.jpg -p mypassphrase

# Custom output path
controlplane content encrypt photo.jpg -o /tmp/photo.enc
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `FILE` | argument | (required) | File to encrypt (must exist) |
| `-p/--passphrase` | string | (prompted) | Encryption passphrase (hidden input) |
| `-o/--output` | path | `<file>.enc` | Output path |

**Output example:**

```
✅ Encrypted: photo.jpg
   Output: /home/user/project/content/photo.jpg.enc
   Size: 1,245,768 bytes
```

---

### `controlplane content decrypt FILE`

Decrypt a COVAULT `.enc` file back to its original.

```bash
controlplane content decrypt photo.jpg.enc
controlplane content decrypt photo.jpg.enc -p mypassphrase
controlplane content decrypt photo.jpg.enc -o /tmp/photo.jpg
```

**Options:** Same as `encrypt` (FILE, -p, -o).

**Output example:**

```
✅ Decrypted: photo.jpg.enc
   Output: /home/user/project/content/photo.jpg
   Size: 1,200,000 bytes
```

**Error handling:** Wrong passphrase or corrupted file → exit(1) with message.

---

### `controlplane content inspect FILE`

Read metadata from an encrypted `.enc` file without decrypting it.

```bash
controlplane content inspect photo.jpg.enc
controlplane content inspect photo.jpg.enc --json
```

**Output example:**

```
📦 photo.jpg.enc
   Original: photo.jpg
   MIME: image/jpeg
   Encrypted size: 1,245,768 bytes
   SHA-256: a1b2c3d4e5f6...
```

---

### `controlplane content classify FILE`

Classify a file into a content category (used for storage tier decisions).

```bash
controlplane content classify photo.jpg
# → photo.jpg: image
```

---

### `controlplane content folders`

Detect content folders in the project with file counts and sizes.

```bash
controlplane content folders
controlplane content folders --json
```

**Output example:**

```
📁 Content folders (2):
   content: 42 files, 125.3 MB (8 encrypted)
   docs/media: 15 files, 23.1 MB
```

---

### `controlplane content release list`

List assets on the content-vault GitHub Release.

```bash
controlplane content release list
controlplane content release list --json
```

**Output example:**

```
☁️  Release assets (3):
   • video-intro.mp4 (52.3 MB)
   • dataset-full.csv (128.7 MB)
   • model-weights.bin (340.0 MB)
```

---

### `controlplane content release restore`

Download missing large files from the content-vault release.

```bash
controlplane content release restore
controlplane content release restore --json
```

**Output example:**

```
✅ Restored 2 file(s):
   ⬇ video-intro.mp4
   ⬇ dataset-full.csv
   Already present: 1
```

---

### `controlplane content release inventory`

Cross-reference local sidecars with remote release assets. Finds
orphaned sidecars (local but no remote) and extra remotes (remote
but no sidecar).

```bash
controlplane content release inventory
controlplane content release inventory --json
```

**Output example:**

```
📊 Release Inventory:
   Synced: 3
   Orphaned (sidecar but no remote): 1
     • old-dataset.csv → old-dataset.csv
   Extra remote (no local sidecar): 1
     • legacy-model.bin
```

---

## File Map

```
cli/content/
├── __init__.py     36 lines — group definition, _resolve_project_root,
│                              sub-module imports (crypto, optimize, release)
├── crypto.py      103 lines — encrypt, decrypt, inspect, classify commands
├── optimize.py     87 lines — folders, optimize commands
├── release.py     119 lines — release subgroup (list, restore, inventory)
└── README.md               — this file
```

**Total: 345 lines of Python across 4 files.**

---

## Per-File Documentation

### `__init__.py` — Group definition (36 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `_resolve_project_root(ctx)` | helper | Reads `config_path` from context, falls back to `find_project_file()` |
| `content()` | Click group | Top-level `content` group |
| `from . import crypto, optimize, release` | import | Registers sub-modules |

---

### `crypto.py` — Encrypt, decrypt, inspect, classify (103 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `encrypt(ctx, file, passphrase, output)` | command | Encrypt file → `.enc` COVAULT envelope |
| `decrypt(ctx, file, passphrase, output)` | command | Decrypt `.enc` → original file |
| `inspect(file, as_json)` | command | Read `.enc` header metadata (no decryption needed) |
| `classify(file)` | command | Classify file into content category (image, video, etc.) |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `encrypt_file` | `content.crypto` | Encryption with COVAULT envelope |
| `decrypt_file` | `content.crypto` | Decryption with passphrase |
| `read_metadata` | `content.crypto` | Read `.enc` header without decrypting |
| `classify_file` | `content.crypto` | Content category classification |

**Error handling pattern:** All crypto commands use try/except with
specific handlers for `FileNotFoundError` (missing file), `ValueError`
(wrong passphrase or bad format), and generic `Exception` (other failures).
Each exits with `sys.exit(1)` on error.

**Passphrase prompting:** `encrypt` and `decrypt` use Click's `prompt=True,
hide_input=True` so the passphrase is never echoed to the terminal.

---

### `optimize.py` — Folders & media optimization (87 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `detect_folders(ctx, as_json)` | command (`folders`) | Detect content folders with file counts + sizes |
| `optimize(file, as_json)` | command | Optimize a single media file (format conversion + tier) |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `detect_content_folders` | `content.crypto` | Scan project for content-bearing folders |
| `format_size` | `content.crypto` | Human-readable byte formatting |
| `optimize_media` | `content.optimize` | Convert/compress media (WebP, H.264, gzip) |
| `classify_storage` | `content.optimize` | Determine storage tier (git/lfs/release) |

**Note:** `optimize` reads the entire file into memory (`source.read_bytes()`),
calls `optimize_media()`, then writes the result. This is not suitable for
very large files (> 1 GB). Large files should use the web UI's streaming
optimization instead.

---

### `release.py` — GitHub Release asset management (119 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `release()` | Click group | `content release` subgroup |
| `release_list(ctx, as_json)` | command (`release list`) | List assets on content-vault release |
| `restore(ctx, as_json)` | command | Download missing large files from release |
| `inventory(ctx, as_json)` | command | Cross-ref local sidecars with remote assets |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `list_release_assets` | `content.release` | Query GitHub Release for assets |
| `restore_large_files` | `content.release` | Download missing files via `gh` CLI |
| `release_inventory` | `content.release` | Cross-reference sidecars with remote |
| `format_size` | `content.crypto` | Human-readable byte formatting |

**GitHub Release dependency:** `release list` and `restore` require
the `gh` CLI to be authenticated. If `gh` is not available, the commands
report an error and suggest installing it.

---

## Dependency Graph

```
__init__.py
├── click                         ← click.group
├── core.config.loader            ← find_project_file (lazy)
└── Imports: crypto, optimize, release

crypto.py
├── click                         ← click.command, click.argument, click.option
└── core.services.content.crypto  ← encrypt_file, decrypt_file,
                                     read_metadata, classify_file (all lazy)

optimize.py
├── click                         ← click.command
├── core.services.content.crypto  ← detect_content_folders, format_size (lazy)
└── core.services.content.optimize ← optimize_media, classify_storage (lazy)

release.py
├── click                         ← click.group, click.command
├── core.services.content.crypto  ← format_size (lazy)
└── core.services.content.release ← list_release_assets, restore_large_files,
                                     release_inventory (all lazy)
```

---

## Consumers

### Who registers this CLI group

| Layer | Module | What It Does |
|-------|--------|-------------|
| CLI entry | `src/main.py:448` | `from src.ui.cli.content import content` |

### Who also uses the same core services

| Layer | Module | Core Service Used |
|-------|--------|------------------|
| Web routes | `routes/content/__init__.py` | `content.crypto` (decrypt, detect, classify) |
| Web routes | `routes/content/files.py` | `content.file_ops`, `content.optimize` |
| Web routes | `routes/content/preview.py` | `content.crypto`, `content.file_ops` |
| Web routes | `routes/content/manage.py` | `content.file_ops`, `content.release` |
| Core | `backup/archive.py` | `content.crypto.decrypt_file_to_memory` |
| Core | `backup/common.py` | `content.crypto.classify_file` |

---

## Design Decisions

### Why three sub-modules instead of one file

Crypto, optimization, and release management are distinct concerns:
- **Crypto** handles file-level encryption/decryption (needs passphrase)
- **Optimize** handles media format conversion (needs MIME detection)
- **Release** handles GitHub Release API (needs `gh` CLI auth)

Each sub-module has its own set of core service imports and error patterns.
Keeping them separate makes it clear which commands need which dependencies.

### Why crypto commands don't have --json

`encrypt` and `decrypt` are file operations — the output is a file, not
structured data. Adding `--json` would only wrap "success/failure" which
is already communicated by exit code. `inspect` does have `--json`
because it returns structured metadata.

### Why classify is its own command

Classification is useful standalone for scripting (e.g., batch-categorize
files for backup strategy). Embedding it in `optimize` would hide it.

### Why optimize reads the full file into memory

The core `optimize_media()` function works on byte buffers, not streams.
This simplifies the API and avoids partial-write corruption. The tradeoff
is memory usage — files > 1 GB should use the web UI's streaming path.

### Why release is a subgroup (not flat commands)

`release list`, `release restore`, and `release inventory` are all about
the GitHub Release storage layer. Grouping them under `content release`
keeps the top-level `content` group clean and signals that these commands
share a concern (GitHub Release management) distinct from local crypto
and optimization.
