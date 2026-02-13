# Refactoring Plan: File Size Reduction & Documentation

> **Target**: No file over 500 lines (700 max for justified exceptions)
> **Date**: 2026-02-11
> **Status**: In Progress — File 1 ✅ DONE

---

## Current State: Files Over 500 Lines

| # | File | Lines | Ratio | Domain |
|---|------|------:|------:|--------|
| 1 | `templates/scripts/_content.html` | **4,011** | 8.0× over | JS: Content tab |
| 2 | `routes_backup.py` | **1,526** | 3.1× over | API: Backup & Restore |
| 3 | `templates/scripts/_secrets.html` | **1,347** | 2.7× over | JS: Secrets tab |
| 4 | `routes_content.py` | **1,252** | 2.5× over | API: Content vault |
| 5 | `content_optimize.py` | **967** | 1.9× over | Media optimization |
| 6 | `vault.py` | **885** | 1.8× over | Secrets vault core |
| 7 | `routes_vault.py` | **732** | 1.5× over | API: Vault |
| 8 | `content_crypto.py` | **693** | 1.4× over | Content encryption |
| 9 | `routes_secrets.py` | **553** | 1.1× over | API: Secrets (.env) |

**Total lines to redistribute: ~12,000+**

---

## Modal Inventory

Modals are a **major source of bloat**. They live in two places:
- **HTML markup** (the dom structure) → in `partials/_tab_*.html`
- **JS logic** (open/close/confirm handlers) → in `scripts/_*.html` and inline HTML strings built by JS

### Content Tab — 11 modals total

| Modal ID | Type | Location (markup) | Location (JS) | Lines |
|----------|------|-------------------|---------------|------:|
| `ct-rename-modal` | Static HTML | `_tab_content.html:69-105` | `_content.html: contentRenameFile, contentDoRenameConfirm` | ~36+86 |
| `ct-move-modal` | Static HTML | `_tab_content.html:107-138` | `_content.html: contentMoveFile, contentDoMoveConfirm, _ctMoveSelectFolder` | ~32+133 |
| `ct-delete-modal` | Static HTML | `_tab_content.html:140-173` | `_content.html: contentDeleteFile, contentDoDeleteConfirm` | ~34+58 |
| `ct-encrypt-modal` | Static HTML | `_tab_content.html:175-208` | `_content.html: contentEncryptFile, contentDoEncryptConfirm` | ~34+56 |
| `ct-decrypt-modal` | Static HTML | `_tab_content.html:210-244` | `_content.html: contentDecryptFile, contentDoDecryptConfirm` | ~35+52 |
| `bk-wipe-modal` | **JS-generated** | Built inside `renderArchivePanel()` in `_content.html:594-607` | `_content.html: archiveShowWipeModal, archiveDoWipe` | ~14+80 |
| `bk-restore-modal` | **JS-generated** | Built inside `renderArchivePanel()` in `_content.html:609-657` | `_content.html: archiveDoRestoreFrom, archiveDoRestoreFromModal` | ~49+100 |
| `bk-release-modal` | **JS-generated** | Built inside `renderArchivePanel()` in `_content.html:659-679` | `_content.html: archiveUploadToRelease, archiveDoUploadRelease` | ~21+80 |
| `bk-delete-modal` | **JS-generated** | Built inside `renderArchivePanel()` in `_content.html:681-697` | `_content.html: archiveDeleteBackup, archiveDoDeleteConfirm` | ~17+50 |
| `bk-crypto-modal` | **JS-generated** | Built inside `renderArchivePanel()` in `_content.html:699-716` | `_content.html: archiveToggleCrypto, archiveDoCryptoConfirm` | ~18+60 |
| `bk-rename-modal` | **JS-generated** | Built inside `renderArchivePanel()` in `_content.html:718-741` | `_content.html: archiveRenameBackup, archiveDoRenameConfirm` | ~24+50 |

### Secrets Tab — 3 modals total

| Modal ID | Type | Location (markup) | Location (JS) | Lines |
|----------|------|-------------------|---------------|------:|
| `vault-modal` (Lock) | **JS-created** `document.createElement` | Built in `showVaultLockModal()` | `_secrets.html:1221-1252` | ~32+35 |
| `vault-modal` (Unlock) | **JS-created** `document.createElement` | Built in `showVaultUnlockModal()` | `_secrets.html:1254-1277` | ~24+27 |
| `vault-modal` (Add Keys) | **JS-created** `document.createElement` | Built in `showAddKeysModal()` | `_secrets.html:1064-1118` | ~55+57 |

### Summary

| Tab | Static HTML modals | JS-generated modals | Total |
|-----|-------------------:|--------------------:|------:|
| Content | 5 (in `_tab_content.html`) | 6 (in `_content.html`) | **11** |
| Secrets | 0 | 3 (in `_secrets.html`) | **3** |
| Dashboard | 0 | 0 | 0 |
| **Total** | **5** | **9** | **14** |

> **Modals are ~800+ lines of combined HTML+JS** — they absolutely need extraction.

---

## Split Strategy

### Principles

1. **Split by domain concern**, not arbitrary line count
2. **Follow existing section dividers** — the files already have `// ═══` and `# ──` markers that define natural boundaries
3. **Each new file gets a header docstring** explaining what it owns and what it doesn't
4. **JS files use Jinja2 include** — zero runtime cost, clean separation
5. **Python files use standard imports** — route blueprints register to existing blueprint prefix

---

## File 1: `_content.html` + `_tab_content.html` → 12 files ✅ DONE

**Completed 2026-02-11.** Split 4,257 lines (4,011 JS + 246 HTML) into 12 files.
Verified: concatenation of split files is byte-identical to original body (diff = 0).

### Actual split — JS (`scripts/`)

| File | Lines | Domain |
|------|------:|--------|
| `scripts/_content.html` | 32 | **Thin loader** — `<script>` + 10 `{% include %}` directives |
| `scripts/_content_init.html` | 52 | State vars, constants, category definitions |
| `scripts/_content_nav.html` | 361 | Tab init, folder bar, mode switching, URL hash, empty state |
| `scripts/_content_archive.html` | 624 | Archive panel rendering, folder tree, file tree, export |
| `scripts/_content_archive_modals.html` | 563 | Archive modal JS handlers: wipe, upload, restore, delete, encrypt/decrypt, rename |
| `scripts/_content_archive_actions.html` | 393 | Non-modal archive actions: mark git-tracked, release, list backups, browse/selective |
| `scripts/_content_browser.html` | 536 | File browser: category filtering, name search, recursive list, gallery |
| `scripts/_content_actions.html` | 239 | File management: create folder, encrypt, decrypt, delete, release upload/delete |
| `scripts/_content_preview.html` | 259 | Plain file preview: text, markdown, image, video, audio, binary, edit, save |
| `scripts/_content_preview_enc.html` | 490 | Encrypted preview, enc edit/save, key entry, rename/move/close modal handlers |
| `scripts/_content_upload.html` | 569 | Enc key setup, markdown renderer, format helpers, upload with progress, drag-drop |

### Actual split — HTML modals (`partials/`)

| File | Lines | Contains |
|------|------:|----------|
| `partials/_content_modals.html` | 183 | 5 static modals extracted from `_tab_content.html` |
| `partials/_tab_content.html` | 70 | **Reduced from 246** — layout only + `{% include %}` |

### Integration (verified working)

`_tab_content.html` includes `_content_modals.html` for HTML modals.
`_content.html` includes 10 JS modules inside a single `<script>` block.
All files have header docstrings.

---

## File 2: `routes_backup.py` → 3 files (1,526 lines)

### Proposed split

| New file | Lines | Covers |
|----------|------:|--------|
| `routes_backup_core.py` | ~490 | Blueprint definition, helpers, folder/tree endpoints, encrypt/decrypt/delete/rename/mark-special endpoints |
| `routes_backup_archive.py` | ~400 | Export, list, preview, download, upload endpoints |
| `routes_backup_restore.py` | ~430 | Restore (override), import (additive), wipe (factory reset), delete backup |

### Integration pattern

Each file defines routes on the same `backup_bp` blueprint (imported from `routes_backup_core.py`), so `server.py` only registers one blueprint. The split files are loaded by importing:

```python
# routes_backup_core.py — defines backup_bp + helpers
# routes_backup_archive.py — import backup_bp from .routes_backup_core
# routes_backup_restore.py — import backup_bp from .routes_backup_core
```

In `routes_backup.py` (thin re-export):
```python
"""Backup & Restore — route registration."""
from .routes_backup_core import backup_bp  # noqa: F401
import routes_backup_archive  # noqa: F401 — registers routes on backup_bp
import routes_backup_restore  # noqa: F401
```

---

## File 3: `_secrets.html` → 4 files (1,347 lines)

This file has **3 dynamically-created modals** (using `document.createElement`) — all for vault operations.

### Proposed split

| New file | Lines | Covers |
|----------|------:|--------|
| `scripts/_secrets_core.html` | ~450 | State, load, status bars, main form rendering, section collapsing, dirty tracking |
| `scripts/_secrets_actions.html` | ~430 | Save/push, sync to GitHub, remove, clear, toggle local-only, move key, refresh |
| `scripts/_secrets_keys.html` | ~200 | **Add/Create keys modal** — showAddKeysModal, doAddKeys, addEnvEntry, removeEnvEntry, onSectionSelectChange, createEnvFromTemplate |
| `scripts/_secrets_vault_modals.html` | ~270 | **Vault lock/unlock/close modals** — showVaultLockModal, showVaultUnlockModal, closeVaultModal, vaultDoLock, vaultDoUnlock |

### Integration pattern

Same as `_content.html` — Jinja2 includes inside the existing `<script>` block.

> Note: These modals use `document.createElement` + `document.body.appendChild`, so there's no static HTML partial to extract. The JS that *builds* them is what gets split out.

---

## File 4: `routes_content.py` → 3 files (1,252 lines)

### Proposed split

| New file | Lines | Covers |
|----------|------:|--------|
| `routes_content_core.py` | ~460 | Blueprint, helpers, folders, list, encrypt, decrypt, metadata, create folder, delete |
| `routes_content_files.py` | ~400 | Download, upload (+ optimization pipeline), save, rename, move |
| `routes_content_preview.py` | ~350 | Preview (plain + encrypted), save encrypted, enc key setup, release status/cancel |

### Integration pattern

Same blueprint-sharing approach as `routes_backup`.

---

## File 5: `content_optimize.py` → 2 files (967 lines)

### Proposed split

| New file | Lines | Covers |
|----------|------:|--------|
| `content_optimize_image.py` | ~200 | optimize_image, should_optimize_image, _has_meaningful_alpha, _mime_to_ext |
| `content_optimize.py` (keep) | ~500 | Video/audio (stays big — ffmpeg logic is inherently complex), text compression, universal dispatcher, classify_storage. The video optimizer alone (optimize_video) is ~300 lines of ffmpeg pipeline, which is a justified exception. |

**Alternative**: If `content_optimize.py` still exceeds 500 after image extraction, additionally extract:
| `content_optimize_av.py` | ~480 | optimize_video, optimize_audio, all ffmpeg helpers |

Leaving `content_optimize.py` as the dispatcher (~250 lines).

---

## File 6: `vault.py` → 2 files (885 lines)

### Proposed split

| New file | Lines | Covers |
|----------|------:|--------|
| `vault.py` (keep) | ~500 | Core crypto, lock/unlock/register, auto-lock, rate limiting, session management |
| `vault_env.py` | ~380 | Secret file detection, .env parsing (list_env_keys, list_env_sections), export/import |

---

## File 7: `routes_vault.py` (732 lines) — borderline

### Proposed split

| New file | Lines | Covers |
|----------|------:|--------|
| `routes_vault.py` (keep) | ~400 | Status, lock, unlock, register, auto-lock, detect, read keys |
| `routes_vault_env.py` | ~330 | Create .env, add keys, update key, delete key, move key, rename section, toggle local-only, export, import |

---

## File 8: `content_crypto.py` (693 lines) — borderline

### Proposed split

| New file | Lines | Covers |
|----------|------:|--------|
| `content_crypto.py` (keep) | ~440 | Encrypt, decrypt, decrypt_to_memory, read_metadata, envelope parsing, is_covault_file |
| `content_classify.py` | ~250 | All classification: classify_file, detect_content_folders, list_folder_contents, list_folder_contents_recursive, format_size, extension sets |

---

## File 9: `routes_secrets.py` (553 lines) — marginal

Can likely be left as-is (553 is just over 500). If desired split:

| New file | Lines | Covers |
|----------|------:|--------|
| `routes_secrets.py` (keep) | ~350 | List, get, set, delete |
| `routes_secrets_sync.py` | ~200 | Push, pull, GitHub sync |

---

## Execution Order

1. ~~**`_content.html`** — highest ROI, 4,011 → 12 files~~ ✅ **DONE** (2026-02-11)
2. ~~**`routes_backup.py`** — second largest, clean domain boundaries~~ ✅ **DONE** (2026-02-11) — 1,527 → 5 files (210+385+142+453+480)
3. ~~**`_secrets.html`** — same pattern as _content, easy once #1 establishes the template~~ ✅ **DONE** (2026-02-11) — 1,348 → 7 files (26+108+370+175+362+233+140)
4. ~~**`routes_content.py`** — same pattern as routes_backup~~ ✅ **DONE** (2026-02-11) — 1,253 → 4 files (422+329+315+306)
5. ~~**`content_optimize.py`** — independent, clean split~~ ✅ **DONE** (2026-02-11) — 968 → 2 files (356+673)
6. ~~**`vault.py`** — straightforward~~ ✅ **DONE** (2026-02-11) — 886 → 2 files (537+398)
7. **`routes_vault.py`** — borderline, lower priority
8. **`content_crypto.py`** — borderline, lower priority
9. **`routes_secrets.py`** — smallest, lowest priority
10. ~~**`_integrations.html`** — largest template monolith~~ ✅ **DONE** (2026-02-12) — 4,358 → 11 files (loader + 10 children)
11. ~~**`_devops.html`** — second largest template monolith~~ ✅ **DONE** (2026-02-12) — 2,303 → 10 files (loader + 10 children)
12. ~~**`_wizard.html`** — setup wizard monolith~~ ✅ **DONE** (2026-02-12) — 2,116 → 6 files (loader + 6 children)
13. ~~**`_audit.html`** — audit tab monolith~~ ✅ **DONE** (2026-02-12) — 1,382 → 5 files (loader + 5 children)

---

## Documentation Deliverables

Each split produces a **header docstring** in every new file:

```python
"""
Admin API — Backup archive operations (export, list, preview, download, upload).

Split from routes_backup.py. Uses the shared backup_bp blueprint from
routes_backup_core.py.

Functions:
    api_export      — Create backup archive from selected paths
    api_list        — List backups in .backup/ directory
    api_preview     — Preview archive contents (for selective restore)
    api_download    — Download a backup archive
    api_upload      — Upload a backup archive
"""
```

```html
<!-- 
  Content Tab JS — Archive Actions Module
  
  Split from _content.html. All functions operate on backup archives
  in the Archive panel.
  
  DOM elements this module touches:
    #archive-wipe-modal        — managed by archiveShowWipeModal()
    #archive-restore-modal     — managed by archiveDoRestoreFrom()
    #archive-delete-modal      — managed by archiveDeleteBackup()
    #archive-crypto-modal      — managed by archiveToggleCrypto()
    #archive-rename-modal      — managed by archiveRenameBackup()
    #archive-release-modal     — managed by archiveUploadToRelease()
  
  Depends on: _content_init.html (state vars), _content_archive.html (archiveLoadList)
-->
```

---

## Verification Checklist (per split)

- [ ] New files include complete header docstrings
- [ ] All function references resolve (grep for cross-references)
- [ ] Blueprint route prefixes unchanged
- [ ] Jinja2 includes produce identical HTML output
- [ ] No duplicate function names across split files
- [ ] `server.py` registration unchanged (same blueprint names)
- [ ] Existing tests still pass (if any)

---

## What This Fixes (for AI sessions)

1. **AI only needs to read 1 file** to understand a domain, not grep through 4,011 lines
2. **File headers declare DOM ownership** — no more blind edits to managed elements
3. **Dependency chains are explicit** — "depends on: _content_init.html"
4. **Natural context windows** — 500-line files fit entirely in AI context
5. **Section comments become file boundaries** — harder to lose your place
