# Chat UI — Implementation Plan

> **Status:** Ready for implementation
> **Depends on:** Phase 1B (SCP Chat core) — ✅ complete, 137/137 tests passing
> **Parent:** `phase1-spec.md` → Step 15+ ("Web routes/UI")
> **Created:** 2026-02-17

---

## 0. Objective

Add a **💬 Chat** sub-tab to the Content Vault tab that surfaces the
SCP Chat system (threads, messages, @-references, encryption) through
the existing web admin panel.

**Design thesis:** Follow the Archive precedent — Chat gets its own panel
rendered into `#content-browser`, with its own hash routing, state vars,
and JS modules. No new top-level tab (Chat is *content* — conversation
records stored on the ledger branch alongside docs/media/archives).

---

## 1. Architecture Overview

### 1.1 Layer Map

```
┌──────────────────────────────────────────────────────┐
│  Browser (JS)                                        │
│  _content_chat.html      ← panel rendering, compose  │
│  _content_chat_refs.html ← @-autocomplete popup      │
│  _content_init.html      ← state vars (add chat)     │
│  _content_nav.html       ← mode routing (add chat)   │
│  _tab_content.html       ← sub-tab button (add chat) │
│  _content.html           ← loader (add includes)     │
└────────────┬─────────────────────────────────────────┘
             │ fetch('/api/chat/...')
             ▼
┌──────────────────────────────────────────────────────┐
│  Flask (routes_chat.py)                              │
│  chat_bp = Blueprint("chat", url_prefix="/api")      │
│  /api/chat/threads       ← list threads              │
│  /api/chat/threads/create ← create thread            │
│  /api/chat/messages      ← list messages by thread   │
│  /api/chat/send          ← send message              │
│  /api/chat/refs/resolve  ← resolve an @-reference    │
│  /api/chat/refs/autocomplete ← autocomplete prefix   │
│  /api/chat/sync          ← push + pull               │
└────────────┬─────────────────────────────────────────┘
             │ calls
             ▼
┌──────────────────────────────────────────────────────┐
│  Core (existing, Phase 1B)                           │
│  src/core/services/chat/                             │
│    chat_ops.py    ← list_threads, list_messages,     │
│                      send_message, create_thread,    │
│                      push_chat, pull_chat            │
│    chat_refs.py   ← parse_refs, resolve_ref,         │
│                      autocomplete                    │
│    models.py      ← ChatMessage, Thread              │
└──────────────────────────────────────────────────────┘
```

### 1.2 Data Flow

```
User types message → compose box
  → JS calls POST /api/chat/send
    → routes_chat.py → chat_ops.send_message()
      → git notes (if run_id) + thread JSONL (if thread_id)
    → returns ChatMessage JSON
  → JS prepends message to message list (optimistic append)

User loads thread list → renderChatPanel()
  → JS calls GET /api/chat/threads
    → routes_chat.py → chat_ops.list_threads()
  → JS renders thread sidebar

User clicks thread → chatSelectThread(thread_id)
  → JS calls GET /api/chat/messages?thread_id=X
    → routes_chat.py → chat_ops.list_messages()
  → JS renders message list
  → URL hash updated: #content/chat/thread_id
```

---

## 2. API Routes

### File: `src/ui/web/routes_chat.py` (NEW)

```python
chat_bp = Blueprint("chat", __name__, url_prefix="/api")
```

| Method | Route | Handler | Core function | Notes |
|--------|-------|---------|---------------|-------|
| GET | `/chat/threads` | `chat_threads()` | `list_threads(root)` | Returns `{threads: [...]}` newest-first |
| POST | `/chat/threads/create` | `chat_thread_create()` | `create_thread(root, title, user, anchor_run, tags)` | Body: `{title, anchor_run?, tags?[]}` |
| GET | `/chat/messages` | `chat_messages()` | `list_messages(root, thread_id, run_id, n)` | Query: `thread_id`, `run_id`, `n` |
| POST | `/chat/send` | `chat_send()` | `send_message(root, text, thread_id, run_id, encrypt, source)` | Body: `{text, thread_id?, run_id?, encrypt?, source?}` |
| GET | `/chat/refs/resolve` | `chat_resolve_ref()` | `resolve_ref(ref, root)` | Query: `ref=@run:xxx` |
| GET | `/chat/refs/autocomplete` | `chat_autocomplete()` | `autocomplete(prefix, root)` | Query: `prefix=@run:` |
| POST | `/chat/sync` | `chat_sync()` | `push_chat(root)` + `pull_chat(root)` | Body: `{action: "push"\|"pull"\|"both"}` |

### Registration

In `server.py`:
```python
from .routes_chat import chat_bp
app.register_blueprint(chat_bp, url_prefix="/api")
```

---

## 3. Frontend Structure

### 3.1 Files Modified

| File | Change |
|------|--------|
| `_tab_content.html` | Add `💬 Chat` button to `.content-modes` |
| `_content_init.html` | Add chat state vars |
| `_content_nav.html` | Add `"chat"` to mode routing in `contentSwitchMode()` and `contentApplySubNav()` |
| `_content.html` | Add `{% include %}` for chat JS modules |

### 3.2 Files Created

| File | Purpose |
|------|---------|
| `_content_chat.html` | Main chat panel: thread list + message list + compose box |
| `_content_chat_refs.html` | @-reference autocomplete popup logic |

### 3.3 State Variables (in `_content_init.html`)

```javascript
// ── Chat mode state ────────────────────────────────
let _chatThreads = [];           // loaded threads
let _chatSelectedThread = null;  // current thread_id
let _chatMessages = [];          // messages in current thread
let _chatLoaded = false;         // thread list loaded?
let _chatComposeText = '';       // compose buffer
```

### 3.4 Hash Routing

```
#content/chat                    → chat panel, General thread selected
#content/chat/<thread_id>        → chat panel, specific thread selected
```

Handled by `contentApplySubNav()` and `contentUpdateHash()`.

---

## 4. UI Layout Spec

### 4.1 Panel Structure

When `contentCurrentMode === 'chat'`, render into `#content-browser`:

```html
<div class="chat-panel" style="display:flex;gap:1rem;height:calc(100vh - 220px)">

  <!-- LEFT: Thread sidebar -->
  <div class="chat-sidebar" style="width:280px;min-width:220px;flex-shrink:0;
       display:flex;flex-direction:column;gap:0.5rem">

    <!-- Toolbar -->
    <div style="display:flex;align-items:center;gap:0.5rem">
      <input type="text" id="chat-thread-search" placeholder="Search threads…"
             oninput="chatFilterThreads(this.value)" />
      <button onclick="chatShowNewThread()">+ New</button>
      <button onclick="chatSync('both')" title="Sync">🔄</button>
    </div>

    <!-- Thread list (scrollable) -->
    <div id="chat-thread-list" style="flex:1;overflow-y:auto">
      <!-- rendered by chatRenderThreadList() -->
    </div>
  </div>

  <!-- RIGHT: Message area -->
  <div class="chat-main" style="flex:1;display:flex;flex-direction:column;min-width:0">

    <!-- Thread header -->
    <div id="chat-thread-header">
      <!-- title, tags, anchor_run badge -->
    </div>

    <!-- Filter/sort bar -->
    <div id="chat-filter-bar">
      <!-- [All] [manual] [trace] [system]  |  Sort: [newest] [oldest] -->
    </div>

    <!-- Messages (scrollable, newest at bottom) -->
    <div id="chat-messages" style="flex:1;overflow-y:auto">
      <!-- rendered by chatRenderMessages() -->
    </div>

    <!-- Compose box -->
    <div id="chat-compose" style="border-top:1px solid var(--border-subtle);
         padding:0.75rem">
      <div style="position:relative">
        <textarea id="chat-compose-input" rows="2"
                  placeholder="Type a message… Use @ for references"
                  oninput="chatOnInput(this)"
                  onkeydown="chatOnKeydown(event)"></textarea>
        <!-- @-autocomplete popup (rendered by _content_chat_refs.html) -->
        <div id="chat-ref-popup" style="display:none;position:absolute;bottom:100%">
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:0.5rem;margin-top:0.5rem">
        <label style="display:flex;align-items:center;gap:0.3rem;font-size:0.8rem;
               color:var(--text-muted);cursor:pointer">
          <input type="checkbox" id="chat-encrypt-cb"> 🔒 Encrypt
        </label>
        <span style="flex:1"></span>
        <button class="btn btn-primary btn-sm" onclick="chatSendMessage()">
          📤 Send
        </button>
      </div>
    </div>
  </div>
</div>
```

### 4.2 Thread List Item

```
┌────────────────────────────────┐
│ 📌 General                    │  ← pinned, always first
│    3 messages · 2m ago         │
├────────────────────────────────┤
│ 💬 Deploy v1.2                │  ← title
│    🏷️ deploy · 5 msgs · 1h    │  ← tags, count, relative time
├────────────────────────────────┤
│ 📋 Config audit trace         │  ← trace-linked title
│    🔗 run_xxx · 2 msgs · 3h   │  ← anchor_run badge
└────────────────────────────────┘
```

### 4.3 Message Bubble

```
┌──────────────────────────────────────────┐
│ 👤 JohnDoe           📋 trace    2m ago  │  ← user, source badge, relative time
│──────────────────────────────────────────│
│ Deployed staging. See @run:run_xxx and   │  ← text, @refs rendered as links
│ @commit:abc123 for details.              │
│──────────────────────────────────────────│
│ 🔗 @run:run_xxx  🔗 @commit:abc123      │  ← parsed refs as clickable chips
│ 🔐 encrypted                            │  ← encryption badge (if applicable)
└──────────────────────────────────────────┘
```

### 4.4 @-Reference Autocomplete

When user types `@` in the compose box:

```
┌─ Autocomplete ──────────────────────┐
│ 🔍 @run:                             │
│   @run:run_20260217_detect_a1b2     │
│   @run:run_20260217_k8s-apply_c3d4  │
│   @thread:thread_20260217_e5f6      │
│   @commit:abc1234                   │
│   (arrow keys to select, Enter)     │
└─────────────────────────────────────┘
```

---

## 5. Integration Points

### 5.1 With Content Vault Navigation

The chat mode follows the **Archive precedent**:
- `contentSwitchMode('chat')` hides folder bar + breadcrumb
- Calls `renderChatPanel()` which replaces `#content-browser`
- `contentUpdateHash()` writes `#content/chat` or `#content/chat/<thread_id>`
- `contentApplySubNav(['chat', thread_id])` restores state from hash

### 5.2 With Existing Content Upload Button

Upload button is hidden in chat mode (same as archive mode):
```javascript
if (uploadBtn) uploadBtn.style.display = (mode === 'media' || mode === 'docs') ? '' : 'none';
```

### 5.3 With Event Bus (future — SSE real-time)

Phase 1 scope does NOT include real-time SSE push. Messages appear on
refresh or on send (optimistic append). The EventBus infrastructure
exists and can be wired for Phase 2.

### 5.4 Cross-References to Other Tabs

@-references can link to entities in other tabs:
- `@run:` → could navigate to a run detail (future)
- `@commit:` / `@branch:` → informational only (tooltip/popup)
- `@audit:` → links to audit log entry
- `@code:` → could navigate to Content tab file preview

For Phase 1, refs are rendered as clickable chips that show a
resolve popup (tooltip with entity metadata from `/api/chat/refs/resolve`).

---

## 6. Implementation Steps

### Step 1: API Routes (`routes_chat.py` + registration)

**Files:**
- CREATE `src/ui/web/routes_chat.py`
- MODIFY `src/ui/web/server.py` (add import + register_blueprint)

**Deliverable:** All 7 API endpoints working, testable via curl.

**Details:**
```python
# routes_chat.py — thin wrappers around chat_ops / chat_refs

@chat_bp.route("/chat/threads")
def chat_threads():
    root = _project_root()
    threads = list_threads(root)
    return jsonify({
        "threads": [t.model_dump(mode="json") for t in threads]
    })

@chat_bp.route("/chat/threads/create", methods=["POST"])
def chat_thread_create():
    root = _project_root()
    body = request.get_json(silent=True) or {}
    thread = create_thread(
        root,
        title=body.get("title", ""),
        user=body.get("user", ""),
        anchor_run=body.get("anchor_run"),
        tags=body.get("tags", []),
    )
    return jsonify(thread.model_dump(mode="json"))

@chat_bp.route("/chat/messages")
def chat_messages():
    root = _project_root()
    thread_id = request.args.get("thread_id")
    run_id = request.args.get("run_id")
    n = request.args.get("n", 50, type=int)
    messages = list_messages(root, thread_id=thread_id, run_id=run_id, n=n)
    return jsonify({
        "messages": [m.model_dump(mode="json") for m in messages]
    })

@chat_bp.route("/chat/send", methods=["POST"])
def chat_send():
    root = _project_root()
    body = request.get_json(silent=True) or {}
    msg = send_message(
        root,
        text=body.get("text", ""),
        thread_id=body.get("thread_id"),
        run_id=body.get("run_id"),
        encrypt=body.get("encrypt", False),
        source=body.get("source", "manual"),
    )
    return jsonify(msg.model_dump(mode="json"))

@chat_bp.route("/chat/refs/resolve")
def chat_resolve_ref():
    root = _project_root()
    ref = request.args.get("ref", "")
    result = resolve_ref(ref, root)
    return jsonify(result or {"error": "not_found"})

@chat_bp.route("/chat/refs/autocomplete")
def chat_autocomplete():
    root = _project_root()
    prefix = request.args.get("prefix", "")
    results = autocomplete(prefix, root)
    return jsonify({"suggestions": results})

@chat_bp.route("/chat/sync", methods=["POST"])
def chat_sync():
    root = _project_root()
    body = request.get_json(silent=True) or {}
    action = body.get("action", "both")
    pushed = pulled = False
    if action in ("push", "both"):
        pushed = push_chat(root)
    if action in ("pull", "both"):
        pulled = pull_chat(root)
    return jsonify({"pushed": pushed, "pulled": pulled})
```

---

### Step 2: Content Tab Integration (sub-tab button + nav routing)

**Files:**
- MODIFY `_tab_content.html` — add 💬 Chat sub-tab button
- MODIFY `_content_init.html` — add chat state vars
- MODIFY `_content_nav.html` — add `"chat"` to mode routing
- MODIFY `_content.html` — add `{% include %}` directives

**Deliverable:** Clicking 💬 Chat shows a loading placeholder in the
browser area. Hash routing `#content/chat` works.

**Details for `_tab_content.html`:**
```html
<!-- Add after the archive button -->
<button class="content-mode" data-mode="chat"
        onclick="contentSwitchMode('chat')">💬 Chat</button>
```

**Details for `_content_nav.html` — `contentSwitchMode()`:**
```javascript
// Add alongside archive block:
} else if (mode === 'chat') {
    document.getElementById('content-folder-bar').style.display = 'none';
    document.getElementById('content-breadcrumb').style.display = 'none';
    renderChatPanel();
}
```

**Details for `_content_nav.html` — `contentApplySubNav()`:**
```javascript
// In the mode validation list:
if (['docs', 'media', 'archive', 'chat'].includes(mode)) { ... }

// Add chat handling after archive handling:
if (contentCurrentMode === 'chat') {
    document.getElementById('content-folder-bar').style.display = 'none';
    document.getElementById('content-breadcrumb').style.display = 'none';
    if (subParts.length >= 2) {
        _chatSelectedThread = subParts.slice(1).join('/');
    }
    renderChatPanel();
    return;
}
```

**Details for `_content_nav.html` — `contentUpdateHash()`:**
```javascript
// Add before archive block:
if (contentCurrentMode === 'chat') {
    const parts = ['content', 'chat'];
    if (_chatSelectedThread) parts.push(_chatSelectedThread);
    history.replaceState(null, '', `#${parts.join('/')}`);
    return;
}
```

---

### Step 3: Chat Panel — Thread List + Message List

**Files:**
- CREATE `src/ui/web/templates/scripts/_content_chat.html`

**Deliverable:** Full thread sidebar + message panel rendering. Selecting
a thread loads and displays messages. General thread auto-selected.

**Key functions:**
- `renderChatPanel()` — renders full chat layout into `#content-browser`
- `chatLoadThreads()` — fetches threads from API, renders sidebar
- `chatRenderThreadList(threads)` — generates thread list HTML
- `chatSelectThread(thread_id)` — loads messages for a thread
- `chatRenderMessages(messages)` — generates message bubble HTML
- `chatFilterThreads(query)` — client-side thread title search
- `_chatRelativeTime(isoString)` — "2m ago" / "1h ago" formatting

---

### Step 4: Chat Panel — Compose + Send

**Files:**
- MODIFY `_content_chat.html` (same file, compose section)

**Deliverable:** User can type and send messages. Messages appear
immediately (optimistic append). Encryption toggle works.

**Key functions:**
- `chatSendMessage()` — reads compose input, calls POST /api/chat/send,
  prepends message to list
- `chatOnKeydown(event)` — Ctrl+Enter to send
- `chatOnInput(textarea)` — auto-grow + trigger @-autocomplete

---

### Step 5: @-Reference Autocomplete

**Files:**
- CREATE `src/ui/web/templates/scripts/_content_chat_refs.html`

**Deliverable:** Typing `@` in compose box shows autocomplete popup.
Arrow keys navigate, Enter inserts. Refs in rendered messages are
clickable and show resolve tooltip.

**Key functions:**
- `chatCheckRefTrigger(text, cursorPos)` — detect if user is typing a ref
- `chatFetchAutocomplete(prefix)` — calls GET /api/chat/refs/autocomplete
- `chatRenderRefPopup(suggestions)` — renders popup
- `chatInsertRef(ref)` — inserts selected ref into compose text
- `chatRefChipClick(ref)` — click handler for ref chips in messages,
  calls `/api/chat/refs/resolve` and shows tooltip

---

### Step 6: Thread Creation + Sync + Polish

**Files:**
- MODIFY `_content_chat.html` (new thread modal, sync, source filters)

**Deliverable:** New thread creation modal, push/pull sync, source
filter buttons (All/manual/trace/system), sort toggle (newest/oldest).

**Key functions:**
- `chatShowNewThread()` — opens inline modal for title + tags
- `chatCreateThread(title, tags)` — calls POST /api/chat/threads/create
- `chatSync(action)` — calls POST /api/chat/sync
- `chatFilterBySource(source)` — re-renders messages filtered by source
- `chatToggleSort()` — reverses message order

---

## 7. Styling Approach

All chat styles will use existing CSS custom properties (no new CSS file needed):

```
--bg-card, --bg-tertiary, --bg-inset        → panel backgrounds
--border-subtle, --border                    → dividers
--text-primary, --text-secondary, --text-muted → text hierarchy
--accent-primary, --accent-glow              → selected thread, send button
--error, --warning                           → error states
--radius-sm, --radius-md                     → border radius
--space-sm, --space-md, --space-lg           → spacing
```

Inline styles (consistent with existing archive/preview pattern).
No new CSS classes needed — matches existing admin panel conventions.

### Source Badge Colors

| Source | Color | Icon |
|--------|-------|------|
| `manual` | `--text-muted` (grey) | 👤 |
| `trace` | `#818cf8` (indigo) | 📋 |
| `system` | `#60a5fa` (blue) | ⚙️ |

---

## 8. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Chat threads directory doesn't exist yet (no threads created) | Low | `list_threads()` returns `[]` gracefully. UI shows empty state with "Start a conversation" prompt |
| Ledger worktree not initialized | Medium | `renderChatPanel()` wraps API call in try/catch, shows "Ledger not initialized — run a command first" |
| Large thread with many messages | Medium | `list_messages(n=50)` limits initial load. Add "Load more" button for pagination |
| @-autocomplete is slow (git operations) | Low | Debounce input (300ms). Show spinner in popup. Cache results for 5s |
| Encryption key not configured | Low | Encrypt checkbox disabled with tooltip "Set CONTENT_VAULT_ENC_KEY in .env" |
| Push/pull fails (no remote) | Low | `chat_sync()` returns `{pushed: false, pulled: false}`. Toast shows warning |

---

## 9. Acceptance Criteria

### Must Have

- [ ] 💬 Chat sub-tab button appears in Content Vault navigation
- [ ] Clicking Chat shows thread list (or empty state if no threads)
- [ ] Thread list shows title, message count, last activity time
- [ ] Clicking a thread loads its messages
- [ ] Messages display user, text, source badge, relative time
- [ ] Compose box sends messages to the selected thread
- [ ] Ctrl+Enter sends a message
- [ ] Encryption toggle works (🔒 checkbox)
- [ ] `@`-references in message text are rendered as clickable chips
- [ ] URL hash routing: `#content/chat` and `#content/chat/<thread_id>`
- [ ] New thread creation via modal (title + tags)
- [ ] Source filter (All / manual / trace / system)
- [ ] Push/pull sync button
- [ ] Error states handled gracefully (no unhandled exceptions)
- [ ] All 7 API endpoints return valid JSON

### Nice to Have (defer)

- [ ] SSE real-time message push (EventBus integration)
- [ ] Message search (full-text across all threads)
- [ ] Message editing / deletion
- [ ] File attachments
- [ ] Thread archival / pinning
- [ ] "Load more" pagination for messages
- [ ] @-reference navigation to other tabs (run detail, file preview)
- [ ] Typing indicator
- [ ] Unread message count badges

---

## 10. Implementation Order

```
Step 1: routes_chat.py + server.py registration     ← API layer
Step 2: _tab_content, _content_init, _content_nav    ← sub-tab wiring
Step 3: _content_chat.html (panel + threads + msgs)  ← core UI
Step 4: Compose + send (same file)                   ← interactivity
Step 5: _content_chat_refs.html (@-autocomplete)     ← enhancement
Step 6: New thread modal + sync + filters + polish   ← completeness
```

**Estimate:** Steps 1–4 deliver a functional chat tab. Steps 5–6 add polish.

---

*This plan covers the Web UI for Chat only. CLI commands (`scp chat send`,
`scp chat list`) and TUI integration are separate scopes.*
