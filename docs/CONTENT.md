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
| `/api/content/list` | GET | List content folders and files |
| `/api/content/file/<path>` | GET | Get file content/metadata |
| `/api/content/encrypt` | POST | Encrypt a file |
| `/api/content/decrypt` | POST | Decrypt a file |
| `/api/content/upload` | POST | Upload a file |
| `/api/content/delete` | POST | Delete a file |
| `/api/content/rename` | POST | Rename a file |
| `/api/content/optimize` | POST | Optimize media |
| `/api/content/release` | POST | Upload to GitHub Release |
| `/api/content/preview/<path>` | GET | Get file preview |

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
