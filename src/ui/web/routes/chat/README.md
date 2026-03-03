# Chat Routes — Thread & Messaging API

> **5 files · 581 lines · 12 endpoints · Blueprint: `chat_bp` · Prefix: `/api`**
>
> Thin HTTP wrappers over `src.core.services.chat.*`.
> These routes power the project's built-in chat system: threaded conversations,
> message CRUD with optional encryption, @-reference resolution for entity linking
> (runs, traces, tools), and git-backed push/pull sync to share chat across clones.
> No business logic lives here — every handler delegates to core and applies
> background sync patterns.

---

## How It Works

### Request Flow

```
Frontend (scripts/content/)
│
├── _chat.html        → /chat/threads, /send, /delete-message, /update-message
├── _chat.html        → /chat/threads/create, /delete-thread, /move-message
├── _chat.html        → /chat/poll (auto-poll loop)
├── _chat.html        → /chat/sync (manual push/pull)
└── _chat_refs.html   → /chat/refs/resolve, /chat/refs/autocomplete
     │
     ▼
routes/chat/                                  ← HTTP layer (this package)
├── __init__.py    — blueprint definition
├── threads.py     — list, create, delete threads
├── messages.py    — list, send, delete, update, move messages
├── refs.py        — @-reference resolve + autocomplete
└── sync.py        — push/pull sync + combined polling
     │
     ▼
core/services/chat/                           ← Business logic (no HTTP)
├── chat_ops.py      — thread/message CRUD on JSONL files
├── chat_refs.py     — @-reference resolution (runs, traces, tools)
├── chat_crypto.py   — message-level encryption/decryption
└── __init__.py      — re-exports all public functions
```

### Background Sync Architecture

```
                    READ path                 WRITE path
                    ─────────                 ──────────
              chat_messages()              chat_send()
              chat_threads()               chat_thread_create()
                    │                      chat_move_message()
                    │                            │
                    ▼                            ▼
            ┌─── bg pull ───┐          ┌─── bg push ───┐
            │ daemon thread │          │ daemon thread  │
            │ non-blocking  │          │ non-blocking   │
            └───────────────┘          └────────────────┘
                    │                            │
                    ▼                            ▼
            pull_chat(root)              push_chat(root)
                    │                            │
                    ▼                            ▼
            git pull (ledger           git push (ledger
            worktree branch)           worktree branch)
```

**Pattern:** Every read triggers a background pull. Every write triggers
a background push. Both operations are:
- **Non-blocking** — local data returned immediately, sync happens in daemon thread
- **Non-fatal** — if remote or auth fails, response still succeeds with local data
- **Auth-gated** — skipped entirely if `is_auth_ok()` returns False

### Message Encryption Round-Trip

```
User sends encrypted message
     │
     ▼
chat_send() receives {text: "...", encrypt: true}
     │
     ▼
send_message() stores: {"text": "ENC:aes256:iv:ciphertext...", "flags": {"encrypted": true}}
                                   │ (on disk — JSONL file)
     │
     ▼
Route decrypts before returning:
  decrypt_text(msg.text, root) → "Original plaintext"
     │
     ▼
Response: {"text": "Original plaintext", "flags": {"encrypted": true}}
            ↑ client sees plaintext        ↑ flag preserved for UI badge
```

The client always sees plaintext. The file always stores ciphertext.
If the key is unavailable at response time, the encrypted text falls through.

### @-Reference System

```
User types: @run:run_20260217_detect_a1b2
     │
     ├── autocomplete: /chat/refs/autocomplete?prefix=@run:run_2026
     │   → [{label: "run_20260217_detect_a1b2", type: "run", ...}, ...]
     │
     └── resolve: /chat/refs/resolve?ref=@run:run_20260217_detect_a1b2
         → {type: "run", id: "run_20260217...", label: "...", status: "pass"}
```

References link chat messages to project entities. The frontend
renders them as clickable badges that navigate to the referenced entity.

---

## File Map

```
routes/chat/
├── __init__.py     20 lines  — blueprint definition + sub-module imports
├── messages.py    282 lines  — message list, send, delete, update flags, move/copy
├── threads.py     114 lines  — thread list (with message_count), create, delete
├── sync.py        108 lines  — combined poll (pull+threads+messages) + manual sync
├── refs.py         57 lines  — @-reference resolve + autocomplete
└── README.md                 — this file
```

---

## Per-File Documentation

### `__init__.py` — Blueprint Definition (20 lines)

Defines the `chat_bp` blueprint with no prefix (routes use `/chat/...`
which gets mounted at `/api` by the server). Imports all sub-modules
to trigger route registration.

```python
chat_bp = Blueprint("chat", __name__)

from . import threads, messages, refs, sync  # noqa: E402, F401
```

### `messages.py` — Message Operations (282 lines)

The largest file — handles all message CRUD plus the most complex
operation: cross-thread move/copy.

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `chat_messages()` | GET | `/chat/messages` | List messages (by thread or run) |
| `chat_send()` | POST | `/chat/send` | Send message (optional encryption) |
| `chat_delete_message()` | POST | `/chat/delete-message` | Delete message by ID |
| `chat_update_message()` | POST | `/chat/update-message` | Update publish/encrypt flags |
| `chat_move_message()` | POST | `/chat/move-message` | Move or copy message to another thread |

**`chat_messages()` — background pull + trace enrichment:**

```python
# 1. Background pull (non-blocking)
if is_auth_ok():
    threading.Thread(target=_bg_pull, args=(root,), daemon=True).start()

# 2. List from local (immediate)
messages = list_messages(root, thread_id=thread_id, run_id=run_id, n=n)

# 3. Trace enrichment
for m in messages:
    d = m.model_dump(mode="json")
    if d.get("trace_id") and d.get("source") == "trace":
        from src.core.services.trace import get_trace
        t = get_trace(root, d["trace_id"])
        d["trace_shared"] = t.shared if t else False   # <-- added field
```

Messages with `source: "trace"` get a `trace_shared` boolean, which
the UI uses to show/hide the "shared" badge on trace-linked messages.

**`chat_send()` — encryption + auto-push:**

```python
msg = send_message(root, text=text, thread_id=..., encrypt=body.get("encrypt", False), ...)

# Decrypt for response (disk stays encrypted)
result = msg.model_dump(mode="json")
if msg.flags.encrypted and msg.text.startswith("ENC:"):
    try:
        from src.core.services.chat.chat_crypto import decrypt_text
        result["text"] = decrypt_text(msg.text, root)
    except Exception:
        pass  # fall back to encrypted text

# Background push
if is_auth_ok():
    threading.Thread(target=_bg_push, args=(root,), daemon=True).start()
```

**`chat_move_message()` — cross-thread move/copy:**

The most complex endpoint. Moves or copies a message between threads
by creating a fresh message in the target (preserving all metadata)
and optionally deleting from source.

```python
# Find source message
msgs = list_messages(root, thread_id=src_thread, n=9999)
source_msg = next((m for m in msgs if m.id == msg_id), None)

# Create in target (fresh timestamp, preserved metadata)
new_msg = send_message(
    root, source_msg.text, user=source_msg.user,
    thread_id=tgt_thread, trace_id=source_msg.trace_id,
    source=source_msg.source, publish=source_msg.flags.publish,
    encrypt=False,  # Don't re-encrypt — text is already encrypted if it was
)

# Delete from source if move (not copy)
if delete_src:
    deleted = delete_message(root, thread_id=src_thread, message_id=msg_id)

# Push via ledger worktree
if is_auth_ok():
    from src.core.services.ledger.worktree import push_ledger_branch
    threading.Thread(target=push_ledger_branch, args=(root,), daemon=True).start()
```

### `threads.py` — Thread Management (114 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `chat_threads()` | GET | `/chat/threads` | List all threads with message counts |
| `chat_thread_create()` | POST | `/chat/threads/create` | Create a new thread |
| `chat_delete_thread()` | POST | `/chat/delete-thread` | Delete thread + all messages |

**Thread list enrichment:**

Each thread is enriched with `message_count` by counting lines in
the JSONL file — used by the UI for unread badges:

```python
from src.core.services.chat.chat_ops import _thread_dir
msg_file = _thread_dir(root, t.thread_id) / "messages.jsonl"
if msg_file.is_file():
    td["message_count"] = sum(1 for _ in msg_file.open("r", encoding="utf-8"))
else:
    td["message_count"] = 0
```

**Thread create — auto-push:**

```python
thread = create_thread(root, title=title, user=body.get("user", ""),
                       anchor_run=body.get("anchor_run") or None,
                       tags=body.get("tags") or [])

# Background push so other systems see the thread
if is_auth_ok():
    threading.Thread(target=_bg_push, args=(root,), daemon=True).start()
```

### `sync.py` — Sync & Polling (108 lines)

| Function | Method | Route | Auth | What It Does |
|----------|--------|-------|------|-------------|
| `chat_poll()` | POST | `/chat/poll` | `@requires_git_auth` | Pull + return threads + messages |
| `chat_sync()` | POST | `/chat/sync` | `@requires_git_auth` | Explicit push/pull/both |

**`@requires_git_auth` decorator:** These are the only endpoints in the
chat package that require authentication. The decorator checks SSH key
availability before allowing the call — if auth is not configured, it
returns a 401 with a helpful message.

**`chat_poll()` — the primary frontend polling endpoint:**

Does three things in one HTTP round-trip:

```python
# 1. Pull from remote (non-fatal)
pulled = False
try:
    pulled = pull_chat(root)
except Exception:
    pass

# 2. List threads with message_count enrichment
threads = list_threads(root)
thread_data = []
for t in threads:
    td = t.model_dump(mode="json")
    # ... message_count enrichment (same as chat_threads)
    thread_data.append(td)

# 3. List messages for the requested thread
messages = []
if thread_id:
    msgs = list_messages(root, thread_id=thread_id, n=n)
    # ... trace enrichment (same as chat_messages)
```

**Why one combined endpoint instead of three calls:**
The frontend auto-polls every 5 seconds. Three separate round-trips
(pull + threads + messages) would triple the request rate.

**`chat_sync()` — manual sync with action control:**

```python
body = request.get_json(silent=True) or {}
action = body.get("action", "both")  # "push", "pull", or "both"

if action in ("push", "both"):
    pushed = push_chat(root)
if action in ("pull", "both"):
    pulled = pull_chat(root)
```

### `refs.py` — @-Reference System (57 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `chat_resolve_ref()` | GET | `/chat/refs/resolve` | Resolve `@type:id` to entity metadata |
| `chat_autocomplete()` | GET | `/chat/refs/autocomplete` | Autocomplete partial reference |

**Reference format:** `@type:id`

| Reference Type | Example | Resolves To |
|---------------|---------|------------|
| `@run:` | `@run:run_20260217_detect_a1b2` | Run metadata (status, duration, tool) |
| `@trace:` | `@trace:tr_a1b2c3` | Trace metadata (shared status, events) |
| `@tool:` | `@tool:docker` | Tool metadata (installed version, status) |

**Autocomplete flow:**

```python
prefix = request.args.get("prefix", "")  # e.g. "@run:run_2026"
results = autocomplete(prefix, root)     # → [{label, type, id}, ...]
return jsonify({"suggestions": results})
```

Returns an empty `suggestions` array (not an error) when prefix is empty.

---

## Dependency Graph

```
__init__.py     ← defines chat_bp, imports all sub-modules

messages.py
├── chat_bp               ← from __init__
├── chat.send_message     ← core CRUD
├── chat.list_messages    ← core CRUD
├── chat.delete_message   ← core CRUD
├── chat.update_message_flags ← core CRUD
├── chat.pull_chat        ← core sync
├── chat.push_chat        ← core sync
├── chat_crypto.decrypt_text  ← lazy import for response decryption
├── trace.get_trace       ← lazy import for trace enrichment
├── git_auth.is_auth_ok   ← auth gate for background sync
└── ledger.worktree.push_ledger_branch ← lazy import for move-message push

threads.py
├── chat_bp               ← from __init__
├── chat.list_threads     ← core CRUD
├── chat.create_thread    ← core CRUD
├── chat.delete_thread    ← core CRUD
├── chat.push_chat        ← core sync
├── chat.chat_ops._thread_dir ← for message_count enrichment
└── git_auth.is_auth_ok   ← auth gate

sync.py
├── chat_bp               ← from __init__
├── chat.list_messages    ← core CRUD
├── chat.list_threads     ← core CRUD
├── chat.pull_chat        ← core sync
├── chat.push_chat        ← core sync
├── chat.chat_ops._thread_dir ← for message_count enrichment
├── trace.get_trace       ← for trace enrichment
├── requires_git_auth     ← from ui.web.helpers (decorator)
└── helpers.project_root  ← from ui.web.helpers

refs.py
├── chat_bp               ← from __init__
├── chat.resolve_ref      ← core reference resolution
├── chat.autocomplete     ← core autocomplete
└── helpers.project_root  ← from ui.web.helpers
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `chat_bp`, registers on Flask app |
| Frontend | `scripts/content/_chat.html` | `/threads`, `/send`, `/delete-message`, `/update-message`, `/move-message`, `/threads/create`, `/delete-thread`, `/poll`, `/sync` |
| Frontend | `scripts/content/_chat_refs.html` | `/refs/resolve`, `/refs/autocomplete` |
| Frontend | `scripts/_debugging.html` | Chat endpoints for debug inspection |

---

## Service Delegation Map

```
Route Handler              →   Core Service Function
──────────────────────────────────────────────────────────
chat_threads()             →   chat.list_threads()
                           +   chat_ops._thread_dir() (message_count)
chat_thread_create()       →   chat.create_thread()
                           +   push_chat() (bg)
chat_delete_thread()       →   chat.delete_thread()
chat_messages()            →   chat.list_messages()
                           +   pull_chat() (bg)
                           +   trace.get_trace() (enrichment)
chat_send()                →   chat.send_message()
                           +   chat_crypto.decrypt_text() (response)
                           +   push_chat() (bg)
chat_delete_message()      →   chat.delete_message()
chat_update_message()      →   chat.update_message_flags()
                           +   chat_crypto.decrypt_text() (response)
chat_move_message()        →   chat.list_messages() (find source)
                           +   chat.send_message() (create in target)
                           +   chat.delete_message() (optional)
                           +   ledger.push_ledger_branch() (bg)
chat_poll()                →   pull_chat() + list_threads() + list_messages()
chat_sync()                →   push_chat() + pull_chat()
chat_resolve_ref()         →   chat.resolve_ref()
chat_autocomplete()        →   chat.autocomplete()
```

---

## Data Shapes

### `/api/chat/threads` response

```json
{
    "threads": [
        {
            "thread_id": "t_20260217_security",
            "title": "Security Discussion",
            "created_at": "2026-02-17T14:30:00Z",
            "user": "admin",
            "anchor_run": "run_20260217_audit_a1b2",
            "tags": ["security", "audit"],
            "message_count": 42
        }
    ]
}
```

### `/api/chat/send` request

```json
{
    "text": "Found a CVE in the base image — see @run:run_20260217_audit_a1b2",
    "thread_id": "t_20260217_security",
    "encrypt": true,
    "publish": false,
    "source": "manual"
}
```

### `/api/chat/send` response (encrypted message, decrypted in response)

```json
{
    "id": "m_20260217_143000_a1b2",
    "text": "Found a CVE in the base image — see @run:run_20260217_audit_a1b2",
    "user": "admin",
    "timestamp": "2026-02-17T14:30:00Z",
    "thread_id": "t_20260217_security",
    "source": "manual",
    "flags": {
        "encrypted": true,
        "publish": false
    }
}
```

### `/api/chat/poll` response

```json
{
    "pulled": true,
    "threads": [
        {
            "thread_id": "t_20260217_security",
            "title": "Security Discussion",
            "message_count": 42
        }
    ],
    "messages": [
        {
            "id": "m_...",
            "text": "Found a CVE...",
            "user": "admin",
            "source": "trace",
            "trace_id": "tr_a1b2c3",
            "trace_shared": true
        }
    ]
}
```

### `/api/chat/move-message` request + response

```json
// POST body
{
    "source_thread_id": "t_general",
    "message_id": "m_20260217_143000_a1b2",
    "target_thread_id": "t_security",
    "delete_source": true
}

// Response
{
    "new_message_id": "m_20260217_150000_c3d4",
    "deleted_source": true,
    "target_thread_id": "t_security"
}
```

### `/api/chat/refs/resolve` response

```json
{
    "type": "run",
    "id": "run_20260217_detect_a1b2",
    "label": "detect — 2026-02-17 14:30",
    "status": "pass",
    "duration_seconds": 45
}
```

### `/api/chat/refs/autocomplete` response

```json
{
    "suggestions": [
        {"label": "run_20260217_detect_a1b2", "type": "run", "id": "run_20260217_detect_a1b2"},
        {"label": "run_20260217_audit_c3d4", "type": "run", "id": "run_20260217_audit_c3d4"}
    ]
}
```

---

## Advanced Feature Showcase

### 1. Background Sync with Auth Gating

Every read/write endpoint fires a background daemon thread for sync,
but ONLY if git authentication is verified:

```python
# messages.py — pattern repeated in threads.py
if is_auth_ok():
    def _bg_pull(r):
        try:
            pull_chat(r)
        except Exception:
            pass     # non-fatal: local data wins
    threading.Thread(target=_bg_pull, args=(root,), daemon=True).start()
```

Without `is_auth_ok()`, the thread would hang on SSH passphrase prompt.

### 2. Encrypted Message Transparency

The service stores ciphertext but the response returns plaintext.
Multiple endpoints share this pattern:

```python
# messages.py — send and update both use this
result = msg.model_dump(mode="json")
if msg.flags.encrypted and msg.text.startswith("ENC:"):
    try:
        from src.core.services.chat.chat_crypto import decrypt_text
        result["text"] = decrypt_text(msg.text, root)
    except Exception:
        pass  # key unavailable → client sees "ENC:..." raw
```

### 3. Thread List Message Count Enrichment

Thread objects from the service don't include message counts (they're
stored in separate JSONL files). The route enriches in-flight:

```python
# threads.py — also duplicated in sync.py chat_poll()
from src.core.services.chat.chat_ops import _thread_dir
msg_file = _thread_dir(root, t.thread_id) / "messages.jsonl"
td["message_count"] = sum(1 for _ in msg_file.open("r", encoding="utf-8"))
```

This accesses a private function (`_thread_dir`) from core — a
pragmatic choice over adding a public API for a simple line count.

### 4. Combined Polling Endpoint

`chat_poll()` does pull + threads + messages in one call. The frontend
polls this every 5s during active chat:

```python
# sync.py — three operations, one HTTP call
pulled = pull_chat(root)                          # 1. sync
thread_data = [enrich(t) for t in list_threads(root)]  # 2. threads
messages = [enrich(m) for m in list_messages(...)]     # 3. messages
return jsonify({"pulled": pulled, "threads": thread_data, "messages": messages})
```

### 5. Cross-Thread Message Move with Metadata Preservation

Move creates a new message preserving the original's identity
(user, source, trace_id, flags) but with a fresh timestamp:

```python
# messages.py — move preserves everything except timestamp and ID
new_msg = send_message(
    root, source_msg.text,
    user=source_msg.user,         # preserved
    thread_id=tgt_thread,         # new target
    trace_id=source_msg.trace_id, # preserved
    source=source_msg.source,     # preserved
    publish=source_msg.flags.publish,  # preserved
    encrypt=False,  # Don't re-encrypt — text already encrypted if it was
)
```

---

## Design Decisions

### Why messages.py is the largest file (282 lines)

Messages have the most complex operations: send (with encryption +
auto-push), move/copy (find source → create in target → delete
original → push via ledger), and update flags (with decrypt round-trip).
Splitting by operation (send.py, move.py, etc.) would scatter the
shared patterns (auth gate, bg push, decrypt round-trip).

### Why move-message creates a fresh message instead of file surgery

Chat messages live in JSONL files (one per thread). Moving a message
between threads means modifying two separate files. Rather than
editing JSONL directly (risky: partial writes, corruption), the route
creates a fresh message in the target and deletes from source.
JSONL files stay append-only.

### Why sync endpoints use @requires_git_auth but other endpoints don't

Read/write endpoints (messages, threads) work fine without remote —
they operate on local files. Background sync is a nice-to-have that
silently skips if auth isn't available. But `/chat/poll` and
`/chat/sync` are explicitly about remote operations — if auth isn't
configured, they should fail clearly rather than silently succeed
with local-only data.

### Why trace enrichment is lazy-imported

`from src.core.services.trace import get_trace` is inside the loop
body, not at module level. This avoids importing the entire trace
module when no trace-linked messages exist — trace is only needed
when a message has `source: "trace"`.

### Why message_count uses line counting instead of a service API

The core chat service stores messages in JSONL (one JSON object per
line). Counting lines is O(n) but fast for any reasonable chat history.
Adding a dedicated `count_messages()` API to core would add a function
that does the same thing — `sum(1 for _ in file)`. The route accesses
`_thread_dir()` directly as a pragmatic shortcut.

---

## Coverage Summary

| Capability | Endpoints | File | Auth Required |
|-----------|-----------|------|---------------|
| Thread CRUD | 3 (list, create, delete) | `threads.py` | No |
| Message CRUD | 3 (list, send, delete) | `messages.py` | No |
| Message flags | 1 (update publish/encrypt) | `messages.py` | No |
| Cross-thread move | 1 (move/copy with metadata) | `messages.py` | No |
| Combined poll | 1 (pull + threads + messages) | `sync.py` | Yes (`@requires_git_auth`) |
| Manual sync | 1 (push/pull/both) | `sync.py` | Yes (`@requires_git_auth`) |
| @-reference resolve | 1 | `refs.py` | No |
| @-reference autocomplete | 1 | `refs.py` | No |
| Background sync | All read/write endpoints | `messages.py`, `threads.py` | Conditional (`is_auth_ok()`) |
| Encryption transparency | send, update | `messages.py` | No |
| Trace enrichment | messages, poll | `messages.py`, `sync.py` | No |
