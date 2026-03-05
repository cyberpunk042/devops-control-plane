# Content Management

> Browse, encrypt, optimize, and release project content files.

---

## Overview

The Content tab provides a file manager for project content (docs, media,
archives). It integrates with the vault for per-file encryption and supports
media optimization and GitHub Release uploads for large files.

---

## Content Folders

Content folders are auto-detected from the project or configured in
`project.yml`:

```yaml
content_folders:
  - docs
  - media
  - assets
```

The default is `docs/`. Hidden directories (`.xxx`) are excluded.

---

## Features

### File Browser

- Navigate directories with breadcrumb navigation
- View file details (size, type, encryption status)
- Multi-mode views: files, media gallery, archive

### Preview

Inline preview for supported file types:

| Type | Preview |
|------|---------|
| Images (jpg, png, gif, webp, svg) | Visual preview with zoom |
| Video (mp4, webm, mov) | Video player |
| Audio (mp3, wav, ogg) | Audio player |
| Markdown (md, mdx) | Rendered HTML |
| PDF | Embedded viewer |
| Text/Code | Syntax-highlighted |

### Encryption

Per-file AES-256-GCM encryption using a binary envelope format:

```
COVAULT_v1 │ filename_len(2) │ filename │ mime_len(2) │ mime │
sha256(32) │ salt(16) │ iv(12) │ tag(16) │ ciphertext
```

Key properties:
- **Binary format** — no base64 overhead (unlike JSON-based vaults)
- **Metadata readable** — filename and MIME type can be read without decrypting
- **Integrity** — SHA-256 hash of original content verified on decrypt
- **Encrypted files** get `.enc` extension

### Media Optimization

Automatic optimization for images and video:

| Format | Optimization |
|--------|-------------|
| JPEG | Quality reduction, progressive encoding |
| PNG | Compression, optional WebP conversion |
| WebP | Quality optimization |
| Video | Transcoding, resolution control, codec selection |

### GitHub Releases

Files too large for Git can be uploaded to GitHub Releases:

- Automatic detection of files exceeding Git's size limit
- Upload via `gh` CLI
- Release artifacts tracked with ☁️ indicators in the UI
- Auto-restore from Release during Pages build

---

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/content/list` | GET | List files in a content folder |
| `/api/content/folders` | GET | List available content folders |
| `/api/content/all-folders` | GET | List all project folders (recursive) |
| `/api/content/preview` | POST | Get file content/preview |
| `/api/content/preview-encrypted` | POST | Preview encrypted file content |
| `/api/content/metadata` | POST | Get file metadata |
| `/api/content/save` | POST | Save file content |
| `/api/content/save-encrypted` | POST | Save encrypted file content |
| `/api/content/upload` | POST | Upload a file |
| `/api/content/download` | GET | Download a file |
| `/api/content/delete` | POST | Delete a file |
| `/api/content/rename` | POST | Rename a file |
| `/api/content/move` | POST | Move a file |
| `/api/content/create-folder` | POST | Create a directory |
| `/api/content/encrypt` | POST | Encrypt a file |
| `/api/content/decrypt` | POST | Decrypt a file |
| `/api/content/enc-key-status` | GET | Check encryption key availability |
| `/api/content/setup-enc-key` | POST | Configure encryption key |
| `/api/content/optimize` | POST | Optimize media |
| `/api/content/optimize-status` | GET | Check optimization progress |
| `/api/content/optimize-cancel` | POST | Cancel running optimization |
| `/api/content/release` | POST | Upload to GitHub Release |
| `/api/content/release-status` | GET | Check release upload progress |
| `/api/content/release-status/<id>` | GET | Check specific file release |
| `/api/content/release-cancel/<id>` | POST | Cancel release upload |
| `/api/content/release-inventory` | GET | List release artifacts |
| `/api/content/restore-large` | POST | Restore file from GitHub Release |
| `/api/content/clean-release-sidecar` | POST | Clean release sidecar files |
| `/api/content/glossary` | POST | Get folder glossary (term definitions) |
| `/api/content/outline` | POST | Get file outline (headings/functions) |
| `/api/content/peek-refs` | POST | Detect references in content |
| `/api/content/peek-resolve` | POST | Resolve reference targets |

---

## Smart Folders

Smart folders group related files from different directories into virtual
views. For example, all README files across the project can be viewed as
a single "code-docs" folder.

- **Virtual paths** — smart folders use virtual namespaces (e.g.,
  `code-docs/adapters`) that don't correspond to filesystem paths
- **Configuration** — defined in `smart_folders.json` with glob patterns
- **Automatic grouping** — files are grouped by domain based on their
  real filesystem location
- **API**: `/api/smart-folders/tree`, `/api/smart-folders/file`

---

## Glossary & Outline Panel

A side panel showing contextual documentation for the current folder or file:

- **Folder glossary** — term definitions extracted from the folder's content
- **File outline** — section headers (markdown) or function signatures (Python)
- **Click-to-navigate** — clicking an outline item scrolls the preview
- Supports markdown (heading extraction) and Python (AST-based function/class extraction)

---

## Chat

Threaded conversation system for project notes and communication:

- **Threads** — create, browse, and manage chat threads per content folder
- **Messages** — markdown-formatted with reference support
- **References** — link to files, folders, or code items
- **Git sync** — chat data syncs via Git for collaboration

---

## Peek (Reference Resolution)

When previewing content files, the Peek feature detects and resolves
references to other project files:

- **Directory references** — links to `./path/` or `path/` resolved
  against the project index
- **File references** — links to specific files
- **Hover preview** — see referenced content without navigating away

---

## Archive

The archive system manages versioned file storage:

- Move files to `archive/` with timestamp
- Browse archived versions
- Restore from archive
- Optional encryption of archived files
- Tree view for archive navigation

---

## Integration with Pages

When a Pages segment builds, the content pipeline:

1. **Copies** source files to the build workspace
2. **Decrypts** any `.enc` files (temporary — never committed)
3. **Restores** large files from GitHub Releases if missing locally
4. **Builds** the site with the chosen SSG

The build workspace (`.pages/`) is gitignored — decrypted content never
enters version control.

---

## See Also

- [VAULT.md](VAULT.md) — Vault encryption (different from content crypto)
- [PAGES.md](PAGES.md) — Pages builder system
- [WEB_ADMIN.md](WEB_ADMIN.md) — Web dashboard guide
