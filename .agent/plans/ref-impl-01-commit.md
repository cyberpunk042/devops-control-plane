# @commit: — Implementation Plan (Ref Type #1)

> **Status:** Draft — awaiting review
> **Parent:** `chat-refs-spec.md`
> **Created:** 2026-02-18
> **Includes:** Foundation contract change (list[str] → list[dict])

---

## 0. Current State — Full Trace

### 0.1 User types `@` in compose textarea

**File:** `_content_chat_refs.html`

1. `chatOnInput(textarea)` fires on every keystroke
2. Calls `chatCheckRefTrigger(text, cursorPos)`
3. Scans backwards from cursor to find `@`
4. If found → extracts `prefix` (e.g. `"@"`, `"@com"`, `"@commit:"`, `"@commit:abc"`)
5. If prefix is just `"@"` → shows hardcoded type hints (Phase 1)
6. If prefix has a colon → calls `chatFetchAutocomplete(prefix)` with 300ms debounce

### 0.2 API call

**File:** `_content_chat_refs.html`

```
GET /api/chat/refs/autocomplete?prefix=@commit:
```

### 0.3 Backend processes request

**File:** `routes_chat.py` → `chat_autocomplete()`

1. Reads `prefix` from query string
2. Calls `autocomplete(prefix, project_root)`
3. Returns `{"suggestions": results}` — currently `results` is `list[str]`

**File:** `chat_refs.py` → `autocomplete(prefix, project_root)`

1. Strips `@` → `"commit:"`
2. Splits on `:` → `ref_type = "commit"`, `partial_id = ""`
3. Dispatches to `_autocomplete_commits("", project_root)`

**File:** `chat_refs.py` → `_autocomplete_commits(partial_id, project_root)`

```python
r = subprocess.run(
    ["git", "-C", str(project_root), "log", "-20", "--format=%h"],
    capture_output=True, text=True, timeout=5,
)
hashes = r.stdout.strip().splitlines()
matches = [
    f"@commit:{h}" for h in hashes
    if h.startswith(partial_id) or not partial_id
]
return matches[:20]
```

**Problem:** `--format=%h` returns ONLY the short hash. No message, no author,
no date. The response is `["@commit:abc1234", "@commit:def5678", ...]`.

### 0.4 Frontend receives response

**File:** `_content_chat_refs.html`

1. `chatFetchAutocomplete()` receives `{"suggestions": ["@commit:abc1234", ...]}`
2. Calls `chatRenderRefPopup(suggestions)`
3. Renders each suggestion as a flat `<div>` with just the raw string
4. User sees: `@commit:abc1234` — no context, no way to know which commit

### 0.5 User clicks a suggestion

1. `chatInsertRef(ref)` is called
2. The raw string `"@commit:abc1234"` is inserted into the textarea
3. Popup closes

**Summary of what's broken:**
- Backend throws away all metadata — returns only hashes
- Frontend renders flat strings — no two-line layout
- No keyword search — only hash prefix matching
- First type-picker click inserts text and closes popup (Phase 1 → dead end)

---

## 1. Changes Required

### 1.1 Foundation: Contract Change

**This is a one-time change that affects the entire autocomplete pipeline.**
**Done here with @commit: as the first type.**

#### 1.1.1 `chat_refs.py` — `autocomplete()` return type

**Current:** Returns `list[str]`
**New:** Returns `list[dict]`

Every dict MUST have:
```python
{
    "ref": "@commit:abc1234",     # the actual @-reference to insert
    "label": "Fixed login redirect",  # primary display text
    "detail": "JohnDoe · 2 hours ago", # secondary line
    "icon": "📝",                 # emoji icon for the type
}
```

Types MAY add extra keys (e.g. `status`, `preview_url`, `encrypted`).

#### 1.1.2 `routes_chat.py` — response shape

**Current:**
```python
return jsonify({"suggestions": results})
# results = ["@commit:abc1234", ...]
```

**New:**
```python
return jsonify({"suggestions": results})
# results = [{"ref": "...", "label": "...", "detail": "...", "icon": "📝"}, ...]
```

The route code itself doesn't change — it's the content of `results` that changes.
But we should document that `suggestions` is now `list[dict]`.

#### 1.1.3 Backward compatibility for old types

During the transition, some types will still return `list[str]` until they're
upgraded. The frontend MUST handle both:
- If `suggestion` is a string → render it as-is (legacy)
- If `suggestion` is a dict → use rich rendering

This lets us upgrade types one at a time without breaking anything.

#### 1.1.4 `chat_refs.py` — `_VALID_TYPES` and `_REF_PATTERN`

Add new types that will be implemented later:

```python
_VALID_TYPES = frozenset({
    "run", "thread", "trace", "user",
    "commit", "branch", "audit", "code",
    "doc", "media", "release", "file",   # NEW
})

_REF_PATTERN = re.compile(
    r"@(run|thread|trace|user|commit|branch|audit|code"
    r"|doc|media|release|file):([A-Za-z0-9_\-/.]+)"
)
```

### 1.2 `@commit:` Backend Changes

#### 1.2.1 `_autocomplete_commits()` — rich data

**Current git command:**
```
git log -20 --format=%h
```

**New git command:**
```
git log -30 --format=%h%x00%s%x00%an%x00%ar
```

`%x00` = null byte separator (safe — can't appear in commit messages)
- `%h` = short hash
- `%s` = subject (first line of commit message)
- `%an` = author name
- `%ar` = author date, relative ("2 hours ago")

**Parsing:**
```python
for line in r.stdout.strip().splitlines():
    parts = line.split("\x00")
    if len(parts) < 4:
        continue
    short_hash, subject, author, date_rel = parts[0], parts[1], parts[2], parts[3]
    # ...build dict
```

**Keyword search:**
If `partial_id` contains non-hex characters → it's a search term, not a hash prefix.
Use `git log --grep=<partial_id>` instead of prefix matching.

```python
def _autocomplete_commits(partial_id: str, project_root: Path) -> list[dict]:
    import subprocess

    is_hash_prefix = all(c in "0123456789abcdef" for c in partial_id) if partial_id else True

    if partial_id and not is_hash_prefix:
        # Keyword search in commit messages
        cmd = [
            "git", "-C", str(project_root), "log", "-30",
            "--grep", partial_id, "-i",
            "--format=%h%x00%s%x00%an%x00%ar",
        ]
    else:
        # Hash prefix match or empty (show recent)
        cmd = [
            "git", "-C", str(project_root), "log", "-30",
            "--format=%h%x00%s%x00%an%x00%ar",
        ]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return []
    except Exception:
        return []

    results = []
    for line in r.stdout.strip().splitlines():
        parts = line.split("\x00")
        if len(parts) < 4:
            continue
        short_hash, subject, author, date_rel = parts
        # Hash prefix filter (only if searching by hash)
        if partial_id and is_hash_prefix and not short_hash.startswith(partial_id):
            continue
        results.append({
            "ref": f"@commit:{short_hash}",
            "label": subject,
            "detail": f"{author} · {date_rel}",
            "icon": "📝",
            "hash": short_hash,
        })
        if len(results) >= _MAX_SUGGESTIONS:
            break

    return results
```

#### 1.2.2 Resolver — already works

`_resolve_commit()` already returns full metadata:
```python
{"type": "commit", "id": ..., "exists": True,
 "hash": ..., "short_hash": ..., "message": ..., "author": ..., "date": ...}
```
No changes needed to the resolver.

### 1.3 Frontend Changes

#### 1.3.1 Two-Phase Popup (Foundation)

**Phase 1 — Category Picker:**

Static HTML grid, no API call. Shown when user types `@` with nothing after:

```
┌────────────────────────────────────────────────┐
│  🚀 Run      💬 Thread   📋 Trace    📝 Commit │
│  🔀 Branch   📊 Audit    👤 User     💻 Code   │
│  📄 Doc      🖼 Media    📦 Release  📁 File   │
└────────────────────────────────────────────────┘
```

Each tile click:
1. Inserts `@<type>:` into the textarea (replaces partial)
2. Transitions popup to Phase 2
3. Immediately fires API call with `prefix=@<type>:`

**Phase 2 — Item List:**

Shown after type is selected. Contains:
- Header: type icon + type name + × button (back to Phase 1)
- Search input (the textarea text after `:` acts as filter)
- Scrollable item list with per-type row rendering
- Loading spinner during fetch

**State variables needed:**
```javascript
var _refPhase = 0;        // 0=closed, 1=categories, 2=items
var _refType = '';        // selected type in phase 2
var _refItems = [];       // current suggestions (list of dicts)
var _refActiveIdx = -1;   // keyboard nav index
```

#### 1.3.2 Commit Row Renderer

Each type will have its own row renderer function. For `@commit:`:

```javascript
function chatRefRenderCommit(item) {
    // item = { ref, label, detail, icon, hash }
    //
    //  📝  abc1234  Fixed login redirect
    //              JohnDoe · 2 hours ago
    //
    var div = document.createElement('div');
    div.className = 'chat-ref-item';
    div.setAttribute('data-ref', item.ref);

    var line1 = document.createElement('div');
    line1.className = 'chat-ref-item-label';

    var hashSpan = document.createElement('span');
    hashSpan.className = 'chat-ref-hash';
    hashSpan.textContent = item.hash;

    var msgSpan = document.createElement('span');
    msgSpan.textContent = ' ' + item.label;

    line1.appendChild(document.createTextNode(item.icon + '  '));
    line1.appendChild(hashSpan);
    line1.appendChild(msgSpan);

    var line2 = document.createElement('div');
    line2.className = 'chat-ref-item-detail';
    line2.textContent = item.detail;

    div.appendChild(line1);
    div.appendChild(line2);

    return div;
}
```

#### 1.3.3 Generic Item Renderer (fallback)

For types not yet upgraded (still returning strings), and as a base:

```javascript
function chatRefRenderGeneric(item) {
    if (typeof item === 'string') {
        // Legacy: plain string
        var div = document.createElement('div');
        div.className = 'chat-ref-item';
        div.setAttribute('data-ref', item);
        div.textContent = item;
        return div;
    }
    // Rich dict: use label + detail
    var div = document.createElement('div');
    div.className = 'chat-ref-item';
    div.setAttribute('data-ref', item.ref);

    var line1 = document.createElement('div');
    line1.className = 'chat-ref-item-label';
    line1.textContent = item.icon + '  ' + item.label;

    var line2 = document.createElement('div');
    line2.className = 'chat-ref-item-detail';
    line2.textContent = item.detail;

    div.appendChild(line1);
    div.appendChild(line2);

    return div;
}
```

#### 1.3.4 Renderer Dispatch

```javascript
var _refRenderers = {
    'commit': chatRefRenderCommit,
    // future: 'run': chatRefRenderRun, etc.
};

function chatRefRenderItem(item, type) {
    var renderer = _refRenderers[type] || chatRefRenderGeneric;
    return renderer(item);
}
```

### 1.4 CSS Changes

```css
/* ── Ref popup — Phase 1: Category grid ────────────────── */
.chat-ref-popup { ... }  /* positioned above textarea */
.chat-ref-categories { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
.chat-ref-category { ... }  /* tile with icon + label, hover state */

/* ── Ref popup — Phase 2: Item list ────────────────────── */
.chat-ref-header { ... }  /* type icon + name + close btn */
.chat-ref-items { max-height: 300px; overflow-y: auto; }
.chat-ref-item { padding: 8px 12px; cursor: pointer; border-radius: var(--radius-sm); }
.chat-ref-item:hover, .chat-ref-item.chat-ref-active { background: var(--bg-card-hover); }
.chat-ref-item-label { font-size: 0.85rem; color: var(--text-primary); }
.chat-ref-item-detail { font-size: 0.75rem; color: var(--text-muted); margin-top: 2px; }
.chat-ref-hash { font-family: var(--font-mono); color: var(--accent); font-weight: 600; }
.chat-ref-loading { ... }  /* spinner */
```

---

## 2. Files Touched

| File | Action | What |
|------|--------|------|
| `src/core/services/chat/chat_refs.py` | MODIFY | `_VALID_TYPES`, `_REF_PATTERN`, `autocomplete()` return type, `_autocomplete_commits()` full rewrite |
| `src/ui/web/routes_chat.py` | VERIFY | No code change needed — already passes through `results` |
| `src/ui/web/templates/scripts/_content_chat_refs.html` | REWRITE | Two-phase popup, commit renderer, keyboard nav |
| `src/ui/web/static/css/admin.css` | ADD | Ref popup CSS (categories grid, item rows, hash styling) |

---

## 3. Edge Cases

| Case | Handling |
|------|---------|
| No commits in repo | Return empty list → popup shows "No commits found" |
| `partial_id` has mixed hex/non-hex | Treat as keyword search (grep commit messages) |
| Commit message very long | CSS `text-overflow: ellipsis` on label, single line |
| User types `@commit:` then backspaces to `@commit` then `@com` | Phase 2 → Phase 2 (re-fetch) → Phase 1 (filter categories) |
| User types `@commit:` and immediately types more | Debounce 300ms, then fetch with filter |
| Git timeout | Return empty list → popup shows "Timed out" |
| Non-git repo | Return empty list |

---

## 4. Testing

```bash
# Backend test — verify rich output
curl 'http://localhost:8000/api/chat/refs/autocomplete?prefix=@commit:'
# Expected: {"suggestions": [{"ref": "@commit:abc1234", "label": "...", "detail": "...", "icon": "📝", "hash": "abc1234"}, ...]}

# Keyword search test
curl 'http://localhost:8000/api/chat/refs/autocomplete?prefix=@commit:fix'
# Expected: only commits with "fix" in message

# Hash prefix test
curl 'http://localhost:8000/api/chat/refs/autocomplete?prefix=@commit:abc'
# Expected: only commits with hash starting "abc"

# Frontend test
# 1. Type @ → see 12-tile grid
# 2. Click 📝 Commit → see recent commits with messages
# 3. Type "fix" after colon → filtered results
# 4. Arrow down → highlight moves
# 5. Enter → inserts @commit:abc1234 into textarea
# 6. Esc → closes popup
```

---

## 5. Definition of Done

- [ ] `_autocomplete_commits()` returns `list[dict]` with `ref`, `label`, `detail`, `icon`, `hash`
- [ ] Keyword search works (non-hex partial → `git log --grep`)
- [ ] API returns rich objects
- [ ] Typing `@` shows 12-tile category grid
- [ ] Clicking Commit tile → Phase 2 with commit list showing messages
- [ ] Keyboard nav works (arrows, enter, esc)
- [ ] Clicking item inserts `@commit:<hash>` into textarea
- [ ] Backward compat: old types (still returning strings) still render
- [ ] CSS follows design system tokens
