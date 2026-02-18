# Chat @-Reference System — Full Spec

> **Status:** Draft — awaiting review
> **Parent:** `chat-ui-spec.md`
> **Created:** 2026-02-18

---

## 0. Purpose

The @-reference system lets users link chat messages to any entity in the
control plane: runs, commits, files, media, releases, etc. Each reference
type has its own domain, its own data shape, and its own UX requirements.

This spec defines **all 12 types** — their backend data, frontend rendering,
search behavior, and selection UX.

---

## 1. Architecture

### 1.1 Flow

```
User types "@" in compose box
  → Phase 1: Show 12 category tiles (type picker)
  → User picks a type (click or types "@commit:")
  → Phase 2: Immediately fetch items for that type
  → Show rich item list with type-specific rendering
  → User types more to filter within type
  → User picks an item (click, Enter, Tab)
  → Insert "@type:id" into textarea, close popup
```

### 1.2 Layers

```
Frontend popup (_content_chat_refs.html)
  ├── Phase 1: category picker (12 tiles with icons)
  └── Phase 2: item list per type
        ├── Each type has its own row renderer
        ├── Each type shows different metadata fields
        └── Some types have special UX (media preview, file tree, etc.)

API (/api/chat/refs/autocomplete)
  └── Returns list[dict] — each dict has type-specific fields
        ├── Always: { ref, type, label }
        └── Per-type: detail, icon, status, preview_url, etc.

Backend (chat_refs.py)
  └── autocomplete() dispatches to per-type autocompleters
        └── Each returns list[dict] with rich metadata
```

### 1.3 Response Contract (API)

```json
{
  "type": "commit",
  "suggestions": [
    {
      "ref": "@commit:abc1234",
      "label": "Fixed login redirect",
      "detail": "JohnDoe · 2h ago",
      "icon": "📝"
    }
  ]
}
```

Every suggestion MUST have: `ref`, `label`, `detail`, `icon`.
Types MAY add extra fields for richer UX (e.g. `preview_url` for media).

---

## 2. The 12 Reference Types

---

### 2.1 `@run:` — Ledger Run

**Domain:** Recorded execution (detect, apply, generate, scaffold, etc.)
**Entity:** `src.core.services.ledger.models.Run`
**Backend source:** `list_runs(project_root, n=50)`

| Field on entity | Maps to | Example |
|---|---|---|
| `run_id` | `ref` → `"@run:run_20260217T120000Z_detect_a1b2"` | |
| `type` + `subtype` | Part of `label` | `"detect"`, `"k8s:apply"` |
| `summary` | `label` | `"Scanned 20 stacks, all healthy"` |
| `status` | Badge in `detail` | `"ok"` / `"failed"` / `"partial"` |
| `started_at` | Relative time in `detail` | `"2h ago"` |
| `user` | In `detail` | `"JohnDoe"` |

**Popup row rendering:**
```
🚀  detect — "Scanned 20 stacks, all healthy"
    ✅ ok · JohnDoe · 2h ago                     run_20260217...
```

**Search:** Filter by `run_id` prefix OR keyword match in `summary` or `type`.

**Status badge colors:**
- `ok` → green ✅
- `failed` → red ❌
- `partial` → orange ⚠️

---

### 2.2 `@thread:` — Chat Thread

**Domain:** Conversation threads in the chat system
**Entity:** `src.core.services.chat.models.Thread`
**Backend source:** `list_threads(project_root)`

| Field | Maps to | Example |
|---|---|---|
| `thread_id` | `ref` | `"@thread:thread_20260217T120000Z_c3d4"` |
| `title` | `label` | `"Deploy v1.2"` |
| `tags` | Badges in `detail` | `["deploy", "staging"]` |
| `created_at` | Relative time in `detail` | `"1h ago"` |
| `created_by` | In `detail` | `"JohnDoe"` |
| `anchor_run` | Badge if present | `"🔗 run_xxx"` |

**Popup row rendering:**
```
💬  Deploy v1.2
    🏷 deploy · staging · JohnDoe · 1h ago       thread_20260217...
```

**Search:** Filter by `thread_id` prefix OR keyword in `title` or `tags`.

---

### 2.3 `@trace:` — Session Trace

**Domain:** Recorded debugging/deployment/config sessions
**Entity:** `src.core.services.trace.models.SessionTrace`
**Backend source:** `list_traces(project_root, n=50)`

| Field | Maps to | Example |
|---|---|---|
| `trace_id` | `ref` | `"@trace:trace_20260217T120000Z_e5f6"` |
| `name` | `label` | `"Config audit"` |
| `classification` | Badge in `detail` | `"config"` / `"deployment"` / `"debugging"` |
| `auto_summary` | Secondary in `detail` | `"Checked 15 configs, 2 warnings"` |
| `started_at` | Relative time | `"3h ago"` |
| `event_count` | Minor count | `"12 events"` |

**Popup row rendering:**
```
📋  Config audit
    🏷 config · "Checked 15 configs" · 12 events · 3h ago
```

**Search:** Filter by `trace_id` prefix OR keyword in `name` / `classification`.

---

### 2.4 `@commit:` — Git Commit

**Domain:** Git commit history
**Entity:** Raw git data (no Pydantic model)
**Backend source:** `git log -30 --format=<fields>`

| Field (from git) | Maps to | Example |
|---|---|---|
| `short_hash` | `ref` → `"@commit:abc1234"` | |
| `subject` (first line of message) | `label` | `"Fixed login redirect"` |
| `author_name` | In `detail` | `"JohnDoe"` |
| `author_date_relative` | In `detail` | `"2 hours ago"` |

**Popup row rendering:**
```
📝  abc1234  Fixed login redirect
             JohnDoe · 2 hours ago
```

**Current backend bug:** `git log --format=%h` — returns hash ONLY, no message.
**Fix:** Change to `git log --format=%h%x00%s%x00%an%x00%ar` and parse fields.

**Search:** Filter by hash prefix OR keyword in commit message.

---

### 2.5 `@branch:` — Git Branch

**Domain:** Git branches
**Entity:** Raw git data
**Backend source:** `git branch --format=<fields>` + `git log -1`

| Field | Maps to | Example |
|---|---|---|
| `name` | `ref` → `"@branch:feature/chat-ui"` | |
| `name` | `label` | `"feature/chat-ui"` |
| Last commit `subject` | In `detail` | `"Add compose box"` |
| Last commit `relative date` | In `detail` | `"30m ago"` |

**Popup row rendering:**
```
🔀  feature/chat-ui
    "Add compose box" · 30m ago
```

**Current backend:** Returns name only, no last commit context.
**Fix:** `git for-each-ref --sort=-committerdate --format=...  refs/heads/`

**Search:** Filter by branch name prefix.

---

### 2.6 `@audit:` — Audit Log Entry

**Domain:** Append-only audit trail of all operations
**Entity:** `src.core.persistence.audit.AuditEntry`
**Backend source:** `AuditWriter(project_root).read_recent(n=50)`

| Field | Maps to | Example |
|---|---|---|
| `operation_id` | `ref` → `"@audit:op_20260217_xxx"` | |
| `operation_type` | Part of `label` | `"detect"` / `"automate"` / `"scaffold"` |
| `automation` | `label` | `"Stack detection"` |
| `status` | Badge | `"ok"` / `"failed"` / `"partial"` |
| `timestamp` | Relative time | `"2h ago"` |
| `actions_total` | Minor | `"12 actions"` |

**Popup row rendering:**
```
📊  detect — Stack detection
    ✅ ok · 12 actions · 2h ago                  op_20260217...
```

**Search:** Filter by `operation_id` prefix OR keyword in `operation_type` / `automation`.

---

### 2.7 `@user:` — User

**Domain:** People who have interacted with the project
**Entity:** Git authors (deduplicated)
**Backend source:** `git log --format=%an | sort -u`

| Field | Maps to | Example |
|---|---|---|
| `name` | `ref` → `"@user:JohnDoe"` | |
| `name` | `label` | `"JohnDoe"` |
| Commit count (optional) | `detail` | `"42 commits"` |

**Popup row rendering:**
```
👤  JohnDoe
    42 commits
```

**Current backend:** Stubbed — echoes input.
**Fix:** `git log --format=%an` → deduplicate → return known users.

**Search:** Filter by name prefix, case-insensitive.

---

### 2.8 `@code:` — Source Code Files

**Domain:** Project source files tracked in git (src/, scripts, configs)
**Entity:** File path from `git ls-files`
**Backend source:** `git ls-files` filtered by partial path

**NOT content vault files** — these are the actual project source code.

| Field | Maps to | Example |
|---|---|---|
| `path` (relative) | `ref` → `"@code:src/core/services/chat/chat_ops.py"` | |
| `filename` | `label` | `"chat_ops.py"` |
| `directory` | In `detail` | `"src/core/services/chat/"` |
| `extension` | Icon hint | `.py` → 🐍, `.yaml` → ⚙️, `.sh` → 🔧 |

**Popup row rendering:**
```
💻  chat_ops.py
    src/core/services/chat/                      .py
```

**Current backend:** Completely stubbed.
**Fix:** Use `git ls-files` with optional grep filter.

**Search:** Filter by filename or path fragment. Server-side (could be thousands of files).

**Extension-based icons:**
- `.py` → 🐍
- `.js/.ts` → 📜
- `.yaml/.yml` → ⚙️
- `.md` → 📝
- `.sh` → 🔧
- `.json` → 📋
- `.css/.html` → 🎨
- Other → 📄

---

### 2.9 `@doc:` — Content Vault Documents

**Domain:** Documentation files in content vault folders (docs/, guides/, specs/)
**Entity:** Files in doc-category content folders
**Backend source:** `detect_content_folders()` → filter doc category → `list_folder_contents()`

| Field | Maps to | Example |
|---|---|---|
| `path` (relative) | `ref` → `"@doc:docs/ARCHITECTURE.md"` | |
| `filename` | `label` | `"ARCHITECTURE.md"` |
| `folder` | In `detail` | `"docs/"` |
| `size` | In `detail` | `"8.4 KB"` |
| `encrypted` | Badge | 🔐 if `.enc` |

**Popup row rendering:**
```
📄  ARCHITECTURE.md
    docs/ · 8.4 KB
```

```
📄  secrets-guide.md.enc                         🔐
    docs/ · 1.2 KB
```

**Search:** Filter by filename. Server-side listing of content vault doc folders.

---

### 2.10 `@media:` — Content Vault Media

**Domain:** Images, videos, audio in content vault media folders
**Entity:** Files in media-category content folders
**Backend source:** `detect_content_folders()` → filter media category → `list_folder_contents()`

| Field | Maps to | Example |
|---|---|---|
| `path` (relative) | `ref` → `"@media:media/screenshots/login.png"` | |
| `filename` | `label` | `"login.png"` |
| `folder` | In `detail` | `"media/screenshots/"` |
| `size` | In `detail` | `"124 KB"` |
| `mime_type` | Icon | image → 🖼, video → 🎬, audio → 🎵 |
| `preview_url` | **Image thumbnail** | `/api/content/raw?path=...` |

**Popup row rendering (with preview):**
```
┌──────┐
│ thumb│  login.png
│      │  media/screenshots/ · 124 KB
└──────┘
```

**This is where real UX matters:** For image files, the popup row shows a small
thumbnail preview loaded from the content API. For video/audio, show an icon
with format info. The user should SEE the media to pick the right one.

**Preview URL:** Already exists — `/api/content/raw?path=<relative_path>` serves
raw file content. For images, the popup can use this as an `<img>` src.

**Search:** Filter by filename.

**MIME-based icons:**
- `image/*` → 🖼 (+ thumbnail preview)
- `video/*` → 🎬
- `audio/*` → 🎵
- Other → 📎

---

### 2.11 `@release:` — GitHub Release Assets

**Domain:** Files uploaded to the `content-vault` GitHub Release
**Entity:** GitHub Release asset metadata
**Backend source:** `list_release_assets(project_root)` from `content_release_sync.py`

| Field | Maps to | Example |
|---|---|---|
| `asset_name` | `ref` → `"@release:backup_20260217.tar.gz"` | |
| `asset_name` | `label` | `"backup_20260217.tar.gz"` |
| `size` | In `detail` (formatted) | `"45.2 MB"` |
| Sync status | Badge | synced ✅ / orphaned ⚠️ / remote-only 📥 |

**Popup row rendering:**
```
📦  backup_20260217.tar.gz
    ✅ synced · 45.2 MB
```

**Note:** This calls `gh release view` which requires network + gh CLI.
Should cache results. Show "gh CLI required" if not available.

**Search:** Filter by asset name prefix.

---

### 2.12 `@file:` — Universal File Search (umbrella)

**Domain:** Cross-searches code + docs + media in one query
**Entity:** Mixed — results from all three file sources
**Backend source:** Merges results from `@code:`, `@doc:`, `@media:` autocompleters

| Field | Maps to | Example |
|---|---|---|
| `path` | `ref` → uses the specific type prefix | `"@code:..."`, `"@doc:..."`, `"@media:..."` |
| `filename` | `label` | `"deploy.sh"` |
| Source type | Badge | `code` / `doc` / `media` |

**Popup row rendering:**
```
💻  deploy.sh              scripts/          (code)
📄  deployment.md          docs/guides/      (doc)
🖼  deploy-diagram.png     media/            (media)
```

**Behavior:** When user picks an item from `@file:` results, the inserted ref
uses the **specific type** prefix, not `@file:`. So picking a doc inserts
`@doc:docs/deployment.md`, not `@file:docs/deployment.md`.

`@file:` is a **search convenience**, not a stored ref type.

**Search:** By filename fragment — delegates to all three file autocompleters,
deduplicates, and returns mixed results sorted by relevance.

---

## 3. UX Flow

### 3.1 Phase 1: Category Picker

When user types `@` with nothing after it (or just `@` followed by no colon):

```
┌─ Reference type ──────────────────────────────────────┐
│                                                        │
│  🚀 Run       💬 Thread    📋 Trace     📝 Commit     │
│  🔀 Branch    📊 Audit     👤 User      💻 Code       │
│  📄 Doc       🖼 Media     📦 Release   📁 File       │
│                                                        │
└────────────────────────────────────────────────────────┘
```

Clicking a tile or typing the type name (e.g., `@commit`) transitions to Phase 2.

### 3.2 Phase 2: Item List

After selecting a type (or typing `@commit:`), immediately fetch items:

```
┌─ @commit: ─────────────────── ×  ──────────────────────┐
│ 🔍 [search within commits...]                          │
│                                                         │
│ 📝  abc1234  Fixed login redirect                       │
│              JohnDoe · 2 hours ago                      │
│                                                         │
│ 📝  def5678  Add K8s manifest generator                 │
│              JaneSmith · 1 day ago                      │
│                                                         │
│ 📝  111aaaa  Bump version to 0.4.0                      │
│              CI Bot · 3 days ago                         │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

- Header shows selected type with back button (×) to return to Phase 1
- Optional inline search field for filtering within the type
- Items rendered per-type (see §2)
- Arrow keys navigate, Enter/click selects
- Esc or × goes back to Phase 1

### 3.3 Keyboard Flow

| Input | Action |
|-------|--------|
| `@` | Show Phase 1 (category picker) |
| `@com` | Filter categories → show only matching ("commit") |
| `@commit:` | Enter Phase 2 for commits |
| `@commit:abc` | Phase 2 with search filter "abc" |
| Arrow keys | Navigate items in Phase 2 |
| Enter / Tab | Insert selected item |
| Esc | Phase 2 → Phase 1 → close |
| Backspace past `@` | Close popup |

---

## 4. Implementation Order

### Phase A: Backend — Rich autocomplete responses (chat_refs.py)

1. Change `autocomplete()` return type from `list[str]` to `list[dict]`
2. Update each per-type autocompleter to return rich metadata
3. Add new types: `@doc:`, `@media:`, `@release:`, `@file:`
4. Implement real `@code:` via `git ls-files`
5. Implement real `@user:` via `git log --format=%an`
6. Add keyword search (not just ID prefix match) per type
7. Update API route to pass through rich objects

### Phase B: Frontend — Two-phase popup (_content_chat_refs.html)

1. Phase 1: Category grid (12 tiles)
2. Phase 2: Rich item list with per-type row rendering
3. Keyboard navigation (arrows, enter, esc, back)
4. Media preview thumbnails
5. Inline search within type
6. Status badges and source-colored icons

### Phase C: CSS — Popup styling (admin.css)

1. Category grid layout
2. Item rows with two-line layout (label + detail)
3. Preview thumbnail sizing
4. Active/hover states
5. Type-specific badge colors

---

## 5. Backend Changes Required

### 5.1 chat_refs.py — Modified

- `_VALID_TYPES`: Add `doc`, `media`, `release`, `file`
- `_REF_PATTERN`: Update regex to include new types
- `autocomplete()`: Return `list[dict]` instead of `list[str]`
- Each `_autocomplete_*`: Return dicts with `ref`, `label`, `detail`, `icon`
- New: `_autocomplete_code()` — real implementation via `git ls-files`
- New: `_autocomplete_docs()` — content vault doc folders
- New: `_autocomplete_media()` — content vault media folders  
- New: `_autocomplete_releases()` — GitHub Release assets
- New: `_autocomplete_files()` — umbrella search
- New: `_autocomplete_users()` — git authors deduped
- Modify: `_autocomplete_commits()` — include message, author, date
- Modify: `_autocomplete_branches()` — include last commit info
- Modify: `_autocomplete_runs()` — include summary, type, status
- Modify: `_autocomplete_threads()` — include title, tags
- Modify: `_autocomplete_traces()` — include name, classification

### 5.2 routes_chat.py — Modified

- Update response format: `{"type": "commit", "suggestions": [...]}`
  where each suggestion is a dict, not a string.

### 5.3 Resolvers — Add new types

- `_resolve_doc()` — check file exists in content vault
- `_resolve_media()` — check file exists + return preview URL
- `_resolve_release()` — check asset exists on release

---

## 6. Risks

| Risk | Mitigation |
|------|-----------|
| `git ls-files` slow on large repos | Limit to 30 results, server-side filter |
| `list_release_assets` requires network + gh CLI | Cache results for 30s, graceful fallback |
| Media preview images large | Use CSS max-height thumbnail sizing (40px), browser handles resize |
| Too many content vault files | Server-side filter by filename fragment, limit 20 |
| Breaking existing `autocomplete()` return type | Frontend and API change together in same PR |

---

*Each type is its own domain. Each gets its own rendering. No shortcuts.*
