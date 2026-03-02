# Content — Front-End Scripts

> **14 files · 6,945 lines · The entire Content Vault tab.**
>
> This domain owns the Content tab — a multi-mode content management
> system with four operating modes: **Docs** (document browser), **Media**
> (gallery view), **Archive** (backup/restore/release management), and
> **Chat** (threaded conversations with @-references). It also handles
> encrypted file operations, file preview/edit, and GitHub Release
> artifact management.

---

## How It Works

### Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│ dashboard.html                                                      │
│                                                                      │
│  {% include 'partials/_tab_content.html' %}              ← HTML     │
│  {% include 'scripts/content/_content.html' %}           ← JS      │
│                                                                      │
│  _content.html wraps all 13 module files in a single <script>.     │
│  All functions share the same scope — no IIFEs.                    │
└────────────────────────────────────────────────────────────────────┘
```

### Module Loading Order

```
_content.html                       ← Loader (38 lines)
    │
    ├── _init.html                   ← State vars, constants, category maps
    ├── _nav.html                    ← Tab load, folder bar, mode switch, hash nav
    ├── _archive.html                ← Archive panel layout + folder tree
    ├── _archive_modals.html         ← Wipe, restore, upload, delete, rename modals
    ├── _archive_actions.html        ← Mark, release upload, list, browse actions
    ├── _chat.html                   ← Chat panel, threads, messages, compose, polling
    ├── _chat_refs.html              ← @-reference autocomplete, embed
    ├── _browser.html                ← File listing, search, gallery, Pages integration
    ├── _actions.html                ← Create, encrypt, decrypt, delete file actions
    ├── _preview.html                ← File preview (plaintext, markdown, image, video, audio)
    ├── _preview_enc.html            ← Encrypted file preview + key prompt + edit
    ├── _upload.html                 ← Enc key setup, markdown renderer, upload helpers
    └── _modal_preview.html          ← Modal file preview (DOM transplant)
```

### Four Content Modes

```
 ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
 │   Docs   │   │  Media   │   │ Archive  │   │   Chat   │
 │   📄     │   │  🖼️     │   │   📦     │   │   💬     │
 │          │   │          │   │          │   │          │
 │ File     │   │ Gallery  │   │ Folder   │   │ Thread   │
 │ list     │   │ grid     │   │ tree     │   │ sidebar  │
 │ + search │   │ + search │   │ + backup │   │ + msgs   │
 │ + filter │   │ + filter │   │ + export │   │ + refs   │
 │ + cat.   │   │ + hover  │   │ + import │   │ + polls  │
 │          │   │          │   │ + wipe   │   │          │
 └──────────┘   └──────────┘   └──────────┘   └──────────┘
       │               │               │               │
       ├───────────────┴───────────────┘               │
       │         ↕ Preview panel                        │
       │    (shared between docs/media/archive)         │
       │         ↕ File actions                         │
       │    (encrypt, decrypt, delete, rename)          │
       │                                                │
       └──────── content-browser ──────── content-chat-panel
```

Each mode filters files by category:

| Mode | Categories Shown |
|------|----------------|
| **docs** | document, code, script, config, data, other, encrypted |
| **media** | image, video, audio, encrypted |
| **archive** | all categories |
| **chat** | N/A — separate panel |

### URL Hash Navigation

The content tab syncs its state to the URL hash:

```
#content                          → default (load first folder)
#content/docs/path/to/folder      → docs mode, specific folder
#content/media/path/to/folder     → media mode, specific folder
#content/archive/path             → archive mode, specific folder
#content/chat                     → chat mode, thread list
#content/chat/thread-id           → chat mode, specific thread
#content/docs/file.md@preview     → file preview (rendered)
#content/docs/file.md@edit        → file edit (Monaco)
#content/docs/file.md@raw         → file raw view
```

### File Preview Pipeline

```
contentPreviewFile(path, name)
    │
    ├── GET /api/content/preview?path=X
    │
    ├── Type detection:
    │     ├── image → <img> tag with max-height
    │     ├── video → <video> with canPlay check or download link
    │     ├── audio → <audio> with controls
    │     ├── markdown → renderMarkdown() + link handlers
    │     ├── text → raw <pre> or Monaco editor
    │     └── binary → download link
    │
    ├── Release status check:
    │     ├── orphaned → warning bar with re-upload/clean buttons
    │     ├── stale/failed → warning bar
    │     └── normal → release badge ☁️
    │
    ├── Pages integration:
    │     └── If .md/.mdx → resolve Pages preview link
    │
    └── Toggle bar: Preview | Raw | Edit
```

### Encrypted File Preview Pipeline

```
contentPreviewEncrypted(path, name, overrideKey)
    │
    ├── POST /api/content/preview-encrypted { path, key? }
    │
    ├── 403 (wrong_key / needs_key):
    │     └── Render key prompt UI (input + unlock button)
    │           └── contentTryEncPreviewKey() → retry
    │
    ├── Success:
    │     ├── image → <img> from temporary URL
    │     ├── video → <video> from temporary URL
    │     ├── audio → <audio> from temporary URL
    │     ├── markdown → renderMarkdown() + edit bar
    │     ├── text → raw/edit (Monaco) with save/discard
    │     └── binary → download + raw hex view
    │
    └── Rename/Move actions available for encrypted files
```

### Chat Polling System

```
_chatStartPoll()
    │
    ├── Set base interval (5s)
    ├── Start idle tracker (activity listener)
    │
    └── setInterval:
          │
          ├── Check auth: if !_gitAuthStatus.ok → prompt once
          ├── Show sync indicator
          │
          ├── POST /api/chat/poll { thread_id, n }
          │     ├── Sync threads
          │     ├── Sync messages
          │     └── Detect trace-status changes
          │
          ├── If messages changed:
          │     └── Re-render + scroll to bottom
          │
          └── Idle detection:
                ├── Activity → reset to _CHAT_POLL_BASE (5s)
                ├── 2 min idle → interval *= 2
                └── Max interval: 60s
```

### @-Reference Autocomplete System

```
chatCheckRefTrigger(text, cursorPos)
    │
    ├── Find @ before cursor
    │
    ├── Phase 1: Category Grid
    │     ├── 📝 Audit
    │     ├── 📌 Commit
    │     ├── 🔑 Secret
    │     ├── 📦 Release
    │     ├── 📁 File
    │     └── 🚀 Run
    │
    ├── Phase 2: Item List
    │     ├── GET /api/chat/refs/autocomplete?prefix=@type:partial
    │     ├── Render items (renderers per type)
    │     │     ├── Commits: hash + message + detail
    │     │     ├── Files: icon + path
    │     │     └── Generic: code display
    │     ├── Keyboard nav (↑↓, Enter, Escape, Tab)
    │     └── Click to insert
    │
    └── chatInsertRef(text)
          ├── Replace @trigger with @type:value
          └── Close popup + refocus input
```

### Archive System

```
Content Mode: Archive
    │
    ├── Folder tree (recursive, from /api/backup/folders)
    │     ├── Project Root
    │     └── Nested folders with collapse/expand
    │
    ├── Existing backups list (per folder)
    │     ├── Local .tar.gz / .tar.gz.enc files
    │     ├── Release badges (☁️ uploaded / ⏳ uploading / ❌ failed)
    │     ├── Git-tracked marker (🔗)
    │     └── Actions: Restore / Delete / Upload to Release / Browse
    │
    ├── Upload/Import panel
    │     ├── File input → upload → preview validation
    │     └── Preview shows file list + sizes
    │
    ├── Export/Backup panel
    │     ├── File tree with checkboxes + type filters
    │     ├── Select/deselect by category
    │     ├── Custom backup name
    │     ├── Encryption option
    │     └── Actions: Backup selected / Wipe selected
    │
    └── Modals: Wipe / Restore / Delete / Release / Rename / Crypto
```

---

## File Map

```
content/
├── _content.html           Loader — includes all 12 modules (38 lines)
├── _init.html              State vars, constants, category maps (59 lines)
├── _nav.html               Tab load, folder bar, mode switch, hash nav (436 lines)
├── _browser.html           File listing, search, gallery, Pages integration (688 lines)
├── _actions.html           Create, encrypt, decrypt, delete actions (415 lines)
├── _preview.html           File preview: markdown, image, video, audio, text (340 lines)
├── _preview_enc.html       Encrypted preview + rename/move/close/save (515 lines)
├── _upload.html            Enc key setup, markdown renderer, upload helpers (592 lines)
├── _modal_preview.html     Modal file preview (DOM transplant technique) (128 lines)
├── _archive.html           Archive panel layout + folder tree (625 lines)
├── _archive_modals.html    Wipe, restore, upload, delete, rename modals (564 lines)
├── _archive_actions.html   Mark, release upload, list, browse actions (443 lines)
├── _chat.html              Chat panel, threads, messages, compose, polling (1,160 lines)
├── _chat_refs.html         @-reference autocomplete + embed system (956 lines)
└── README.md               This file
```

---

## Per-File Documentation

### `_content.html` — Loader (38 lines)

Pure Jinja2 include orchestrator. Documents the module index and
assembles all 12 modules into a single `<script>` scope.

### `_init.html` — State & Categories (59 lines)

**State Variables:**

| Variable | Type | Purpose |
|----------|------|---------|
| `contentCurrentMode` | `string` | Active mode: `'docs'`, `'media'`, `'archive'`, `'chat'` |
| `contentFolders` | `Array` | Configured content folders (from project config) |
| `contentCurrentPath` | `string` | Currently browsed folder path |
| `contentLoaded` | `boolean` | Whether tab has been loaded |
| `encKeyConfigured` | `boolean` | Whether CONTENT_VAULT_ENC_KEY is set |
| `_contentCategoryFilters` | `Object` | Mode → category → boolean filter state |
| `_contentLastRenderData` | `Object` | Cached data for re-render without API call |
| `_contentMediaShowAll` | `boolean` | Recursive media listing toggle |
| `_chatThreads` | `Array` | Loaded thread list |
| `_chatSelectedThread` | `string` | Currently selected thread ID |
| `_chatMessages` | `Array` | Messages in current thread |
| `_chatLoaded` | `boolean` | Thread list loaded flag |
| `_chatSourceFilter` | `string` | Thread filter: `'all'`, `'manual'`, `'trace'`, `'system'` |
| `_chatSortNewest` | `boolean` | Sort order for messages |

**Constants:**

| Constant | What It Contains |
|----------|----------------|
| `CATEGORY_MODES` | Maps each mode → allowed category list |
| `CATEGORY_ICONS` | Category → emoji (🖼️, 🎬, 📄, etc.) |
| `CATEGORY_COLORS` | Category → hex color for badges/indicators |

### `_nav.html` — Navigation & Mode Switch (436 lines)

| Function | What It Does |
|----------|-------------|
| `loadContentTab(subParts)` | Entry point — detect folders, check enc key, select initial folder |
| `renderContentEmpty(suggestions)` | Empty state with quick-create folder buttons |
| `renderContentFolderBar()` | Folder dropdown + explore all option + mode buttons |
| `contentToggleExploreAll(enabled)` | Toggle "explore all" — fetches all project folders or reverts to configured only |
| `contentLoadFolder(folderPath)` | Load folder contents → render files, sync folder selector, update hash |
| `contentSwitchMode(mode)` | Switch between docs/media/archive/chat modes with cleanup and folder carry-over |
| `_archiveCleanup()` | Close all archive modals + stop release upload poll timer |
| `contentUpdateHash()` | Sync URL hash with current state (mode, folder, preview path) |
| `contentApplySubNav(subParts)` | Restore state from URL hash on page load/navigation |
| `contentRefresh()` | Force reload entire tab (clear contentLoaded) |

### `_browser.html` — File Browser & Gallery (688 lines)

**Feature: File List + Gallery Rendering**

```
renderContentFiles(data, folderPath)
    │
    ├── docs mode:
    │     ├── Build breadcrumb trail
    │     ├── Inject View Site button (if Pages segment matches)
    │     ├── Category filter pills (toggle visibility per type)
    │     ├── Folders first (clickable → contentLoadFolder)
    │     └── Files: icon + name + category badge + release badge + actions
    │
    └── media mode:
          ├── Gallery grid (thumbnails with lazy loading)
          ├── Hover overlay: filename + type + release badge
          └── Click → contentPreviewFile
```

**Feature: Search (local → recursive escalation)**

```
contentFilterListByName(query)
    │
    ├── Short query (≤2 chars or no glob): instant DOM filter
    │     └── Show/hide existing rows by text match
    │
    └── Long query or glob pattern: debounced recursive API
          └── _doRecursiveListSearch(q)
                ├── GET /api/content/list?path=X&recursive=true&search=Q
                ├── Render results in floating overlay
                └── Each result: full path + click → preview
```

| Mode | Local Search | Recursive Search |
|------|-------------|------------------|
| docs | Instant DOM filter | Debounced API (`?recursive=true`) |
| media | Instant DOM filter (`.media-gallery-item`) | Debounced API → overlay grid |

| Function | What It Does |
|----------|-------------|
| `releaseBadge(f, compact)` | Render release status badge (☁️ uploaded, ⏳ uploading, ❌ failed, ⚠️ orphaned) |
| `_ensureSegmentsCache()` | One-shot GET `/api/pages/segments` → cache for View Site button |
| `_injectViewSiteButton(breadcrumbEl, folderPath)` | Add "Open Site" / "Build & View" button if path matches a Pages segment |
| `contentToggleCategoryFilter(category)` | Toggle category pill on/off, re-render from `_contentLastRenderData` (no API) |
| `contentToggleMediaShowAll(checked)` | Toggle recursive media listing, reload current folder |
| `_matchesGlob(name, query)` | Glob-style file name matching — `*` = wildcard, case-insensitive |
| `contentFilterListByName(query)` | Docs search: instant DOM filter, escalates to recursive API on long query |
| `_doRecursiveListSearch(q)` | Recursive search for docs mode — overlay with matching results |
| `contentFilterMediaByName(query)` | Media search: instant DOM filter on `.media-gallery-item` |
| `_doRecursiveMediaSearch(q)` | Recursive search overlay for media gallery |
| `renderContentFiles(data, folderPath)` | Main renderer — categorized file rows (docs) or thumbnail grid (media) |

### `_actions.html` — File Actions (415 lines)

Every destructive action follows the same **modal → confirm** pattern:

```
contentXxxFile(path, ...)      ← opens modal with preview + options
    │
    ├── Populate modal: path, name, checkboxes (release cleanup, etc.)
    ├── Show modal
    │
    └── contentDoXxxConfirm()   ← user clicks confirm button
          ├── Disable button + show spinner
          ├── POST /api/content/xxx
          ├── Success → close modal + toast + reload folder
          └── Error → show error in modal status area
```

| Function | What It Does |
|----------|-------------|
| `contentCreateFolder(name)` | Create new folder → POST `/content/create-folder` → reload file list |
| `contentEncryptFile(path, hasRelease, fromPreview)` | Open encrypt modal — shows release artifact checkbox if applicable |
| `contentDoEncryptConfirm()` | POST `/content/encrypt` with optional release artifact re-upload |
| `contentDecryptFile(path, hasRelease, fromPreview)` | Open decrypt modal — warns about release artifact invalidation |
| `contentDoDecryptConfirm()` | POST `/content/decrypt` → reload to show decrypted file |
| `contentDeleteFile(path, name, fromPreview, hasRelease)` | Open delete modal — checkbox for "also delete release artifact" |
| `contentDoDeleteConfirm()` | POST `/content/delete` + optional release artifact cleanup |
| `contentDeleteRelease(path, name)` | Open release-only delete modal (file stays, artifact removed) |
| `contentDoDeleteReleaseConfirm()` | POST `/backup/delete-release` for the file's artifact |
| `contentUploadToRelease(path)` | Start release upload → POST `/content/upload-release` → poll |
| `_pollUploadStatus(fileId, path)` | 2s interval poll of `/content/release-status/:id` until done/error |
| `contentFixOrphanedRelease(path, name)` | Open orphan fix modal — "re-upload" or "clean sidecar" |
| `contentDoReuploadOrphan()` | Re-upload the file to GitHub Release to fix orphan |
| `contentDoCleanOrphan()` | Remove stale `.release.json` sidecar without touching GitHub |

### `_preview.html` — File Preview (340 lines)

**State:**

| Variable | Type | Purpose |
|----------|------|---------|
| `previewRawMode` | `boolean` | Raw view active — default `true` |
| `previewEditMode` | `boolean` | Monaco editor active |
| `previewOrigContent` | `string` | Snapshot for edit discard |
| `previewCurrentPath` | `string` | Currently previewed file path |
| `previewCurrentName` | `string` | Currently previewed file name |
| `previewCurrentHasRelease` | `boolean` | File has GitHub Release artifact |
| `previewIsText` | `boolean` | File is text/markdown (editable) |

| Function | What It Does |
|----------|-------------|
| `_attachPreviewLinkHandlers(container)` | Delegated click handlers for anchor + doc links in markdown |
| `contentPreviewFile(path, name, hasRelease)` | Main preview — fetch, render by type, show actions |
| `contentSetPreviewMode(mode)` | Switch between preview/raw/edit views |

### `_preview_enc.html` — Encrypted Preview + File Modals (515 lines)

This file contains both the encrypted preview system AND the shared
file modal handlers (rename, move, close, save) used by all preview types.

| Function | What It Does |
|----------|-------------|
| `contentPreviewEncrypted(path, name, overrideKey)` | Decrypt + preview with key management |
| `contentTryEncPreviewKey(path, name)` | Retry decryption with user-entered key |
| `contentSetEncPreviewMode(mode)` | Switch preview/raw/edit for encrypted content |
| `contentSaveEncEdit()` | Save encrypted edit → re-encrypt → POST `/content/save-encrypted` |
| `contentDiscardEncEdit()` | Discard encrypted edit, revert to preview |
| `contentSaveEdit()` | Save plain file edit → POST `/content/save` |
| `contentDiscardEdit()` | Discard plain file edit, revert to preview |
| `contentRenameFile(path, name, hasRelease)` | Open rename modal (works for any file) |
| `contentDoRenameConfirm()` | Execute rename + optional release artifact update |
| `contentMoveFile(path, name)` | Open move modal with folder drill-down |
| `_ctMoveSelectFolder(folderPath)` | Drill into subfolder in move modal |
| `contentDoMoveConfirm()` | Execute move → POST `/content/move` |
| `contentDeleteFromPreview()` | Delete file while in preview view |
| `contentEncryptFromPreview()` | Encrypt file from preview (with unsaved guard) |
| `contentClosePreview()` | Close preview → dispose Monaco → return to file list |

### `_upload.html` — Upload & Helpers (592 lines)

**Feature: Upload Pipeline**

```
contentDoUpload(files)
    │
    ├── Show progress UI (bar + percentage + speed)
    ├── XHR POST /api/content/upload (multipart)
    │     ├── onprogress → update bar
    │     └── onload → check response
    │
    ├── If image → poll optimize status:
    │     ├── GET /api/content/optimize-status/:id
    │     ├── Show "Optimizing..." with spinner
    │     └── Complete → update size display
    │
    ├── If encKeyConfigured + user checked encrypt:
    │     └── POST /api/content/encrypt (auto-encrypt after upload)
    │
    ├── If user checked "upload to release":
    │     └── contentUploadToRelease(path) → poll release status
    │
    └── Success → toast + reload folder
```

**Feature: Encryption Key Setup**

Renders inline UI for first-time encryption key configuration:
- Generate random 256-bit key (server-side)
- Paste existing key (from another instance or backup)
- Key is stored server-side in `.content_vault_key` (not in browser)

| Function | What It Does |
|----------|-------------|
| `contentEncKeySetup()` | Render key setup UI inside content panel (generate/paste options) |
| `contentGenerateKey()` | POST `/content/setup-enc-key` with `generate=true` → save + toast |
| `contentSaveEncKey()` | POST `/content/setup-enc-key` with user-pasted key → validate + save |
| `renderMarkdown(md)` | Markdown → HTML: headings with anchors, bold, italic, fenced code, links, lists, tables |
| `_slugify(text)` | Heading text → URL-safe anchor ID (nested inside `renderMarkdown`) |
| `formatFileSize(bytes)` | `1234567` → `"1.18 MB"` — human-readable file size |
| `contentToggleTranslate(btn)` | Inject/remove Google Translate widget on preview content |
| `contentCancelUpload()` | Abort in-flight XHR + cancel server-side optimize job + release upload |
| `contentShowUpload()` | Toggle upload zone visibility — closes preview if open |
| `contentInitDragDrop()` | Wire dragover/dragleave/drop events on `#content-dropzone` |
| `contentUploadFiles(event)` | Handle `<input type="file">` change → delegate to `contentDoUpload` |
| `contentDoUpload(files)` | Full pipeline: XHR multipart upload + progress + optimize + release + encrypt |

### `_modal_preview.html` — Modal Preview (128 lines)

Uses a DOM transplant technique — moves `#content-browser` into a
modal overlay, calls the existing preview functions, then moves it
back on close.

| Function | What It Does |
|----------|-------------|
| `openFileInModal(filePath)` | Open file preview inside a modal (from anywhere in the app) |
| `_modalPreviewClose()` | Rescue `#content-browser` back + close modal |
| `_modalPreviewRestore()` | Restore `#content-browser` to original parent + original HTML |
| `_modalPreviewGoToContent()` | Close modal + switch to Content tab with file open |

### `_archive.html` — Archive Panel (625 lines)

| Function | What It Does |
|----------|-------------|
| `renderArchivePanel()` | Full archive panel: folder tree + backups + upload + export |
| `_flattenPaths(nodes)` | Flatten nested folder tree into path list (nested) |
| `_renderFolderTree(nodes, depth)` | Recursive folder tree renderer with collapse/expand (nested) |
| `_archiveRefreshName()` | Update backup name input with auto-generated timestamp name |
| `archiveSwitchFolder(folder)` | Select folder in tree → reload list + file tree |
| `_archiveBuildTypeFilters(counts)` | Build category filter pills from file type counts |
| `archiveFilterByTypes()` | Apply category filters to file tree checkboxes |
| `archiveRefreshTree()` | Refresh folder-specific file tree (for export) |
| `archiveRenderTreeNodes(nodes, depth)` | Recursive file tree renderer with checkboxes |
| `archiveToggleDir(rowEl)` | Toggle directory expand/collapse in file tree |
| `archiveDirCheck(cb)` | Propagate checkbox state to all children in directory |
| `archiveSelectAll(state)` | Select/deselect all file checkboxes |
| `archiveUpdateCount()` | Update "N selected" counter in export section |
| `archiveGetSelectedPaths()` | Collect all checked file paths |
| `archiveDoExport()` | Execute backup export → POST `/backup/create` |

### `_archive_modals.html` — Archive Modals (564 lines)

| Function | What It Does |
|----------|-------------|
| `archiveShowWipeModal()` | Show wipe confirmation (with CONFIRM for root) |
| `archiveDoWipe()` | Execute wipe → POST `/backup/wipe` |
| `archivePreviewUpload(input)` | Upload archive → validate → show preview |
| `archiveDoRestoreFrom(backupPath)` | Open restore modal → preview file list + options |
| `archiveDoRestoreFromModal()` | Execute restore → POST `/backup/restore` with dec/enc/wipe options |
| `_restoreWipeChanged()` | Toggle CONFIRM input visibility when wipe checkbox changes |
| `archiveDeleteBackup(backupPath, hasRelease)` | Show delete confirmation modal |
| `archiveDoDeleteConfirm()` | POST `/backup/delete` (with release cleanup option) |
| `archiveToggleCrypto(backupPath, shouldEncrypt, hasRelease)` | Show encrypt/decrypt-in-place modal |
| `archiveDoCryptoConfirm()` | Execute encrypt or decrypt → POST `/backup/encrypt-archive` or `/decrypt-archive` |
| `archiveRenameBackup(backupPath, currentName, hasRelease)` | Show rename modal for backup archive |
| `archiveDoRenameConfirm()` | POST `/backup/rename` |

### `_archive_actions.html` — Archive Actions (443 lines)

| Function | What It Does |
|----------|-------------|
| `archiveMarkSpecial(backupPath, isTracked)` | Toggle git-tracked status → POST `/backup/mark-special` |
| `archiveDeleteRelease(backupPath)` | Delete release artifact only (reuses delete modal) |
| `archiveUploadToRelease(backupPath)` | Show release upload modal |
| `archiveDoUploadRelease()` | Execute release upload with progress polling |
| `_pollReleaseStatus()` | Poll upload progress bar → done/failed |
| `archiveLoadList()` | Load backup list for selected folder → render cards |
| `archiveBrowseBackup(backupPath, bkId)` | Browse archive contents inline (expand card) |
| `archiveDoSelectiveRestore(backupPath, bkId)` | Restore selected files from browsed archive |
| `archiveDoImportFrom(backupPath)` | Import archive contents → POST `/backup/restore` |
| `_archiveConfirmAction(title, bodyHtml)` | Generic confirmation modal for archive actions |
| `_archiveConfirmResult(ok)` | Handle confirm/cancel from generic action modal |

### `_chat.html` — Chat Panel (1,160 lines)

The largest file. Contains the complete chat subsystem with 9 features.

**Data Shapes:**

```javascript
// Thread object (from GET /chat/threads)
{
  thread_id: "abc-123",
  title: "Deployment Notes",
  tags: ["deploy", "staging"],
  created_by: "admin",
  created_at: "2026-02-20T14:30:00Z",
  message_count: 42,
  anchor_run: null          // optional — linked run ID
}

// Message object (from GET /chat/messages)
{
  id: "msg-456",
  text: "Deployed v2.1 — see @trace:abc123",
  user: "admin",
  hostname: "prod-1",
  ts: "2026-02-20T14:35:00Z",
  source: "manual",          // manual | trace | system
  trace_id: null,            // set for trace-source messages
  trace_shared: false,       // git-shared status
  flags: {
    encrypted: false,
    publish: true
  }
}
```

**Feature 1: Polling + Idle Detection**

```
_chatStartPoll()
    ├── Base: 5s interval
    ├── Idle > 30s: double interval (max 60s)
    ├── Activity detected: reset to 5s
    └── Auth check: if SSH not unlocked → prompt once, skip poll
```

| Function | What It Does |
|----------|-------------|
| `_chatCleanup()` | Hide ref popup + stop poll/idle tracker on view exit |
| `_chatOnActivity()` | Reset `_chatLastActivity` timestamp on mouse/key/click/scroll |
| `_chatStartIdleTracker()` | Attach 4 activity listeners + 30s idle-check interval |
| `_chatStopIdleTracker()` | Detach all activity listeners + clear idle-check interval |
| `_chatTraceStatusChanged(newMsgs, oldMsgs)` | Compare trace `shared` flags between poll cycles to detect changes |
| `_chatStartPoll()` | Start combined poll: POST `/chat/poll` → threads + messages in one request |
| `_chatStopPoll()` | Clear poll interval |

**Feature 2: Thread Management**

| Function | What It Does |
|----------|-------------|
| `renderChatPanel()` | Full layout: thread sidebar + conversation area + compose + modals |
| `chatLoadThreads()` | GET `/chat/threads` → render list; auto-select General on first load |
| `chatRenderThreadList(threads)` | Render threads with unseen badges, tag pills, delete buttons |
| `chatFilterThreads(query)` | Instant client-side filter by title or tag |
| `chatSelectThread(threadId)` | Mark seen → update header → load messages → start poll |
| `_chatGetSeenCounts()` | Read `{threadId: count}` from localStorage |
| `_chatMarkThreadSeen(threadId)` | Write current `message_count` to localStorage |
| `chatShowNewThread()` | Open new-thread modal, focus title input |
| `chatCloseNewThread()` | Close new-thread modal |
| `chatCreateThread()` | POST `/chat/threads/create` with title + tags → select new thread |
| `chatConfirmDeleteThread(threadId, threadTitle)` | Show delete modal with CONFIRM input + disabled button |
| `_chatDeleteThreadValidate()` | Enable delete button only when input === "CONFIRM" |
| `chatDoDeleteThread(threadId)` | POST `/chat/delete-thread` → clear selection → reload list |

**Feature 3: Message Rendering**

| Function | What It Does |
|----------|-------------|
| `chatLoadMessages(threadId)` | GET `/chat/messages?thread_id=X&n=100` → render + start poll |
| `chatRenderMessages()` | Apply source filter + sort → render bubbles → auto-scroll |
| `_chatRenderBubble(msg)` | Single bubble: avatar, user@host, source/enc/publish badges, action buttons, body |
| `_chatRenderBody(msg, displayText)` | Trace messages: rich card with share button + event timeline; others: passthrough |
| `_chatToggleTraceShare(btn, traceId)` | Toggle trace shared status → POST `/trace/share` or `/unshare` → update badge |
| `_chatLoadTraceEvents(btn, traceId)` | Inline expand: GET `/trace/events` → group by domain → collapsible timeline |

**Feature 4: Message Actions**

| Function | What It Does |
|----------|-------------|
| `chatMoveToThread(msgId)` | Open move/copy modal → list other threads as radio options |
| `_chatMoveClose()` | Close move/copy modal |
| `_chatMoveConfirm()` | POST `/chat/move-message` with delete_source flag (move vs copy) |
| `chatConfirmDelete(msgId)` | Show delete confirmation via `modalOpen()` |
| `chatDoDelete(msgId)` | POST `/chat/delete-message` → re-select thread to refresh |
| `chatTogglePublish(msgId, newValue)` | Toggle 🌐 published flag → POST `/chat/update-message` → re-render |
| `chatToggleEncrypt(msgId, newValue)` | Toggle 🔐 encrypted flag → POST `/chat/update-message` → re-render |

**Feature 5: Compose + Send**

| Function | What It Does |
|----------|-------------|
| `chatOnInput(textarea)` | Auto-grow textarea (max 200px) + trigger `chatCheckRefTrigger` |
| `chatOnKeydown(event)` | Ctrl+Enter → send; delegate other keys to `chatRefKeydown` |
| `chatSendMessage()` | POST `/chat/send` with text + thread + encrypt + publish flags |

**Feature 6: Filters, Sort, Sync**

| Function | What It Does |
|----------|-------------|
| `chatFilterBySource(source)` | Filter messages: all / 👤 manual / 📋 trace / ⚙️ system |
| `chatToggleSort()` | Flip `_chatSortNewest` + re-render with new order |
| `chatSync(action)` | Manual git sync → POST `/chat/sync` → reload threads |

**Feature 7: Utilities**

| Function | What It Does |
|----------|-------------|
| `_chatRelativeTime(isoString)` | ISO → "just now" / "5m ago" / "2h ago" / "3d ago" / date string |
| `chatToggleEncryptHint(on)` | Yellow border + 🔐 placeholder on compose when encrypt checked |

### `_chat_refs.html` — @-Reference Autocomplete (956 lines)

Two-phase popup system with per-type rendering, media embedding, and modal detail views.

**Feature: Autocomplete Flow**

```
chatCheckRefTrigger(text, cursorPos)
    │
    ├── Detect '@' before cursor
    │
    ├── Phase 1: Category Grid
    │     _chatRefShowCategories(filter)
    │     ├── 📝 Audit   📌 Commit   🔑 Secret
    │     ├── 📦 Release  📁 File     🚀 Run
    │     └── Keyboard: ↑↓ to navigate, Enter to select
    │
    ├── Phase 2: Item List
    │     _chatRefSelectCategory(type) → _chatRefFetchItems(type, partial)
    │     ├── GET /api/chat/refs/autocomplete?prefix=@type:partial
    │     ├── Audit items: 3 sections (Saved → Log browse → Unsaved)
    │     ├── Non-audit: flat list with pre-embedded labels
    │     ├── Folder refs end with '/' → drill deeper (no insert)
    │     └── Click or Enter → chatInsertRef(ref)
    │
    └── Embedding: @type:id or @type:id{embedded label · detail}
```

**Feature: Ref Click → Detail Modal**

```
chatRefClick(refType, refId)
    │
    ├── thread → chatSelectThread(refId)
    ├── code/doc/file → openFileInModal(refId)
    ├── media → chatRefClickMedia → openFileInModal
    ├── release → resolve → show download/local links
    ├── audit → resolve → _renderAuditData (recursive)
    └── others → resolve → _chatRefOpenModal (generic key/value)
```

**Renderers:**

| Function | What It Does |
|----------|-------------|
| `_chatRefRenderCommit(item)` | Commit: `a1b2c3d4` hash badge + message + author line |
| `_chatRefRenderGeneric(item)` | Generic: icon + label + detail line + status badge |
| `_chatRefRenderItem(item, type)` | Dispatch to commit renderer or generic based on type |

**Autocomplete Engine:**

| Function | What It Does |
|----------|-------------|
| `chatCheckRefTrigger(text, cursorPos)` | Detect `@` in textarea → decide phase 1 or phase 2 |
| `_chatRefShowCategories(filter)` | Phase 1: render 6-tile category grid with optional text filter |
| `_chatRefSelectCategory(type)` | Inject `@type:` prefix into textarea → fetch items |
| `_chatRefFetchItems(type, partialId)` | GET autocomplete API → render items or "no matches" |
| `_chatRefRenderItems(popup, suggestions, type, typeLabel)` | Build item list — audit: 3-section split; others: flat with pre-embed |
| `_renderAuditItems(items, sectionLabel)` | Nested: render audit items into section with header (nested in `_chatRefRenderItems`) |
| `_chatRefGoBack()` | Strip `@type:` from textarea → show category grid again |
| `chatRefKeydown(event)` | ↑↓ navigate, Tab/Enter select, Escape back/dismiss |
| `_chatRefPickSelected()` | Execute current selection: category pick or ref insertion |
| `_chatRefUpdateHighlight()` | Add/remove `chat-ref-active` class + scroll into view |
| `chatInsertRef(ref)` | Replace `@...` in textarea with ref; if folder → drill, else close popup |
| `_chatRefHidePopup()` | Hide popup + reset all phase/type/suggestion state |

**Embedding + Click Handlers:**

| Function | What It Does |
|----------|-------------|
| `_chatEmbedRefs(escapedText)` | Parse `@type:id{...}` in message HTML → clickable chips + inline media embeds |
| `_chatRefShortLabel(refType, refId)` | Truncate: commits → 8 chars, paths → filename, threads → 16 chars |
| `chatRefClick(refType, refId)` | Per-type click: thread → select, file → modal, release → resolve, etc. |
| `chatRefClickMedia(refId)` | Shortcut: open media file in modal preview |
| `_row(k, v, tag)` | Helper: `<div>key: value</div>` row for ref detail modals |
| `_renderAuditData(obj, depth)` | Recursive object renderer — arrays, nested objects, primitives (max 50 items) |
| `_chatRefOpenModal(rt, ri, d)` | Build per-type detail modal: commit, branch, trace, run, audit, user, release |

---

## Dependency Graph

```
_init.html                     ← standalone state + constants
    ↑
_nav.html                      ← uses all state, orchestrates mode switching
    ↑
_browser.html                  ← uses contentFolders, CATEGORY_*
    ↑
_actions.html                  ← uses encKeyConfigured, contentLoadFolder
    ↑
_preview.html                  ← uses contentCurrentPath, contentUpdateHash
    ↑
_preview_enc.html              ← uses preview state, renderMarkdown
    ↑
_upload.html                   ← provides renderMarkdown, contentEncKeySetup
    ↑
_modal_preview.html            ← uses contentPreviewFile, contentPreviewEncrypted
    ↑
_archive.html                  ← uses _archiveSelectedFolder, archiveLoadList
    ↑
_archive_modals.html           ← uses archiveGetSelectedPaths, archiveRefreshTree
    ↑
_archive_actions.html          ← uses _archiveSelectedFolder, archiveLoadList
    ↑
_chat.html                     ← uses _chatThreads, _chatMessages, _chatSelectedThread
    ↑
_chat_refs.html                ← uses chatInsertRef trigger, compose input
```

### External Dependencies

```
globals/_api.html              ← api(), apiPost(), esc(), toast()
globals/_auth_modal.html       ← modalOpen(), modalClose()
globals/_tabs.html             ← switchTab()
globals/_install.html          ← installWithPlan()
_boot.html                     ← ensureGitAuth(), _gitAuthStatus
auth/_auth_banner.html         ← _ensureAuthResolve
```

---

## Consumers

### Tab Loading

| File | How |
|------|-----|
| `dashboard.html` (line 68) | `{% include 'scripts/content/_content.html' %}` |
| `_tabs.html` (line 88) | `loadContentTab(subParts)` — called on content tab switch |

### Cross-Tab Consumers

| Consumer | What It Calls | When |
|----------|-------------|------|
| Wizard `_nav.html` | `contentLoaded = false` | After finish (invalidate) |
| Secrets tab | `contentLoaded = false` | After secret changes |
| `_modal_preview.html` | `openFileInModal(filePath)` | Preview from any tab |

### API Endpoints Used

| Endpoint | Used By | Purpose |
|----------|---------|---------|
| `GET /api/content/folders` | `_nav.html` | Detect configured content folders |
| `GET /api/content/enc-key-status` | `_nav.html` | Check if encryption key is configured |
| `GET /api/content/list` | `_browser.html` | List folder contents (with recursive option) |
| `GET /api/content/preview` | `_preview.html` | Fetch file preview data |
| `POST /api/content/preview-encrypted` | `_preview_enc.html` | Decrypt + preview |
| `POST /api/content/save` | `_preview.html` | Save edited file |
| `POST /api/content/save-encrypted` | `_preview_enc.html` | Save encrypted edit |
| `POST /api/content/encrypt` | `_actions.html` | Encrypt file |
| `POST /api/content/decrypt` | `_actions.html` | Decrypt file |
| `POST /api/content/create` | `_actions.html` | Create file/folder |
| `DELETE /api/content/delete` | `_actions.html` | Delete file |
| `POST /api/content/rename` | `_preview.html` | Rename/move file |
| `POST /api/content/upload` | `_upload.html` | Upload file |
| `POST /api/content/upload-encrypted` | `_upload.html` | Upload + encrypt |
| `POST /api/content/setup-enc-key` | `_upload.html` | Generate/save enc key |
| `GET /api/content/release-status/:id` | `_actions.html` | Poll upload status |
| `POST /api/backup/upload-release` | `_actions.html`, `_archive_actions.html` | Upload to GitHub Release |
| `POST /api/backup/delete-release` | `_actions.html`, `_archive_actions.html` | Delete release artifact |
| `GET /api/backup/list` | `_archive_actions.html` | List backups per folder |
| `GET /api/backup/folders` | `_archive.html` | Folder tree for archive |
| `GET /api/backup/preview` | `_archive_modals.html` | Preview archive contents |
| `POST /api/backup/wipe` | `_archive_modals.html` | Wipe selected files |
| `POST /api/backup/restore` | `_archive_modals.html` | Restore from backup |
| `POST /api/backup/delete` | `_archive_modals.html` | Delete backup archive |
| `POST /api/backup/rename` | `_archive_modals.html` | Rename backup |
| `POST /api/backup/mark-special` | `_archive_actions.html` | Toggle git-tracked |
| `POST /api/backup/export` | `_archive.html` | Export backup archive |
| `POST /api/backup/encrypt-archive` | `_archive_modals.html` | Encrypt backup in-place |
| `POST /api/backup/decrypt-archive` | `_archive_modals.html` | Decrypt backup in-place |
| `GET /api/chat/threads` | `_chat.html` | Load thread list |
| `POST /api/chat/threads` | `_chat.html` | Create thread |
| `DELETE /api/chat/threads/:id` | `_chat.html` | Delete thread |
| `GET /api/chat/messages` | `_chat.html` | Load messages |
| `POST /api/chat/messages` | `_chat.html` | Send message |
| `POST /api/chat/poll` | `_chat.html` | Combined sync + threads + messages |
| `GET /api/chat/refs/autocomplete` | `_chat_refs.html` | @-reference autocomplete |
| `GET /api/pages/segments` | `_browser.html` | Pages segment cache for View Site |

---

## Design Decisions

### Why is `_chat.html` 1,160 lines?

Chat contains the complete threaded messaging subsystem: thread
sidebar, message rendering with trace links, compose area, adaptive
polling with idle detection, source filtering, sort toggling, and
sync indicators. These are all tightly coupled to a single panel's
lifecycle — splitting would scatter state management across files
with no modularity benefit.

### Why DOM transplant for modal preview?

`openFileInModal(filePath)` moves the `#content-browser` element
from the Content tab into a modal overlay, then moves it back on
close. This reuses the exact same preview code (zero duplication)
while allowing file previews from any context in the application.
The alternative — duplicating preview logic in a modal — would
create a maintenance burden across two rendering paths.

### Why idle-adaptive polling for chat?

Fixed-interval polling wastes bandwidth when the user walks away.
The idle tracker detects mouse/keyboard/scroll activity and doubles
the poll interval after 2 minutes of inactivity (up to 60s max).
Any user activity immediately resets to the base 5-second interval.
This reduces unnecessary API calls by ~90% for idle sessions.

### Why does the markdown renderer live in `_upload.html`?

The markdown renderer (`renderMarkdown()`) is a shared utility used
by multiple files (`_preview.html`, `_preview_enc.html`, `_chat.html`).
It lives in `_upload.html` because the file also contains other
content utilities and was the first consumer. Moving it to `_init.html`
or a separate helpers file would be cleaner but wasn't worth the
churn — all files share the same script scope.

### Why category-based mode filtering?

Files are auto-categorized by the backend (image, video, code, etc.).
The mode → category mapping (`CATEGORY_MODES`) determines which files
appear in which mode. This means adding a new mode only requires
defining its category list — no rendering code changes.

### Why separate `_archive_modals.html` from `_archive.html`?

The archive panel layout and tree rendering (`_archive.html`) are
conceptually distinct from the modal flows (wipe confirmation,
restore options, delete confirmation). Keeping modals in their own
file prevents `_archive.html` from growing past comprehension while
keeping related modal code together.

### Why does the @-reference system use a two-phase popup?

Phase 1 (category grid) prevents the user from making a network
request before specifying what type of reference they want. This
reduces API calls and narrows the result set. Phase 2 fetches
items for the selected type with the partial ID for server-side
filtering. The UX is similar to IDE autocomplete — broad → narrow.
