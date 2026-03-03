# Trace Routes — Session Recording, Replay & Sharing API

> **4 files · 340 lines · 9 endpoints · Blueprint: `trace_bp` · Prefix: `/api`**
>
> Three sub-domains under a single blueprint:
>
> 1. **Recording** — start and stop recording sessions, list active
>    recordings (3 endpoints)
> 2. **Queries** — list saved traces, get a single trace, get events
>    (3 endpoints)
> 3. **Sharing** — share via git/ledger, unshare, update metadata,
>    delete (4 endpoints)
>
> Backed by `core/services/trace/` (833 lines across 3 modules):
> - `trace_recorder.py` (720 lines) — recording engine + persistence
> - `models.py` (70 lines) — Pydantic trace/event models
> - `__init__.py` (43 lines) — re-exports

---

## How It Works

### Recording Lifecycle

```
POST /api/trace/start
     Body: { name: "Deploy v2.1", classification: "deployment" }
     │
     ▼
start_recording(root, name="Deploy v2.1", classification="deployment")
     │
     ├── Generate trace_id (UUID)
     ├── Create in-memory recording session
     ├── Start capturing events:
     │   └── API calls, action results, timestamps
     │
     └── Return: { trace_id: "abc-123-..." }

[... user performs actions, events are captured ...]

POST /api/trace/stop
     Body: { trace_id: "abc-123-...", save: true }
     │
     ▼
stop_recording("abc-123-...")
     │
     ├── Finalize recording:
     │   ├── Calculate duration
     │   ├── Count events
     │   └── Generate auto_summary
     │
     ├── save=true? → save_trace(root, trace)
     │   └── Write to .state/traces/<trace_id>.json
     │
     └── Return:
         {
             trace_id: "abc-123-...",
             name: "Deploy v2.1",
             event_count: 15,
             duration_s: 142.5,
             auto_summary: "Deployed to k8s, updated 3 services",
             saved: true
         }
```

### Query Pipelines

```
GET /api/trace/list?n=20
     │
     ▼
list_traces(root, n=20)
     │
     ├── Read .state/traces/*.json
     ├── Sort by created_at (newest first)
     ├── Limit to n results
     │
     └── Return:
         { traces: [{ trace_id, name, classification, created_at,
                       duration_s, event_count, shared, auto_summary }] }

GET /api/trace/get?trace_id=abc-123
     │
     ▼
get_trace(root, "abc-123")
     │
     ├── Read .state/traces/abc-123.json
     ├── Parse into Pydantic model
     │
     └── Return: { trace: { ...full trace with metadata... } }
         or 404: { error: "Trace not found" }

GET /api/trace/events?trace_id=abc-123
     │
     ▼
get_trace_events(root, "abc-123")
     │
     ├── Read events from trace file
     │
     └── Return:
         { trace_id: "abc-123", events: [
             { type: "api_call", endpoint: "/k8s/apply", ts: "...", result: {...} },
             { type: "action", action: "deploy", ts: "...", result: {...} }
         ]}
```

### Sharing Pipelines

```
POST /api/trace/share
     Body: { trace_id: "abc-123", thread_id: "general" }
     │
     ▼
share_trace(root, "abc-123")
     │
     ├── Mark trace as shared in metadata
     │
     ├── Post to chat:
     │   └── post_trace_to_chat(root, trace, thread_id="general")
     │       (so it appears in Content → Chat view)
     │
     ├── Push asynchronously (if git auth OK):
     │   └── threading.Thread → push_ledger_branch(root)
     │       (daemon thread, non-blocking)
     │
     └── Return: { trace_id: "abc-123", shared: true }

POST /api/trace/unshare
     Body: { trace_id: "abc-123" }
     │
     ▼
unshare_trace(root, "abc-123")
     │
     ├── Mark trace as local-only
     ├── Push flag change asynchronously
     │
     └── Return: { trace_id: "abc-123", shared: false }

POST /api/trace/update
     Body: { trace_id: "abc-123", name: "New Name", classification: "debugging" }
     │
     ▼
update_trace(root, "abc-123", name="New Name", classification="debugging")
     │
     └── Return: { trace_id: "abc-123", updated: true }

POST /api/trace/delete
     Body: { trace_id: "abc-123" }
     │
     ▼
delete_trace(root, "abc-123")
     │
     ├── Remove .state/traces/abc-123.json
     │   (ledger copy stays if previously shared)
     │
     └── Return: { trace_id: "abc-123", deleted: true }
```

---

## File Map

```
routes/trace/
├── __init__.py     19 lines — blueprint + 3 sub-module imports
├── recording.py    93 lines — start, stop, active (3 endpoints)
├── queries.py      81 lines — list, get, events (3 endpoints)
├── sharing.py     147 lines — share, unshare, update, delete (4 endpoints)
└── README.md               — this file
```

Core business logic: `core/services/trace/` (833 lines across 3 modules).

---

## Per-File Documentation

### `__init__.py` — Blueprint Definition (19 lines)

```python
trace_bp = Blueprint("trace", __name__)

from . import recording, queries, sharing  # register routes
```

### `recording.py` — Session Recording (93 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `trace_start()` | POST | `/trace/start` | Start recording |
| `trace_stop()` | POST | `/trace/stop` | Stop recording + optionally save |
| `trace_active()` | GET | `/trace/active` | List in-progress recordings |

**Start accepts optional metadata:**

```python
trace_id = start_recording(root, name=name, classification=classification)
```

**Stop returns full summary:**

```python
return jsonify({
    "trace_id": trace.trace_id,
    "name": trace.name,
    "event_count": trace.event_count,
    "duration_s": trace.duration_s,
    "auto_summary": trace.auto_summary,
    "saved": do_save,
})
```

### `queries.py` — Read-Only Queries (81 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `trace_list()` | GET | `/trace/list` | List saved traces (paginated) |
| `trace_get()` | GET | `/trace/get` | Get single trace by ID |
| `trace_events()` | GET | `/trace/events` | Get events for a trace |

**All three use Pydantic `.model_dump(mode="json")` for serialization.**

### `sharing.py` — Share & Manage (147 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `trace_share()` | POST | `/trace/share` | Share via git + post to chat |
| `trace_unshare()` | POST | `/trace/unshare` | Mark as local-only |
| `trace_update()` | POST | `/trace/update` | Update name/classification |
| `trace_delete()` | POST | `/trace/delete` | Delete from local storage |

**Share has the most complex flow:**

```python
# 1. Mark as shared
ok = share_trace(root, trace_id)

# 2. Post to team chat
post_trace_to_chat(root, trace, thread_id=thread_id)

# 3. Push to remote asynchronously (daemon thread)
if is_auth_ok():
    threading.Thread(target=push_ledger_branch, args=(root,), daemon=True).start()
```

---

## Dependency Graph

```
__init__.py
└── Imports: recording, queries, sharing

recording.py
├── trace ← start_recording, stop_recording, save_trace, active_recordings (eager)
└── helpers ← project_root (eager)

queries.py
├── trace ← get_trace, get_trace_events, list_traces (eager)
└── helpers ← project_root (eager)

sharing.py
├── trace ← share_trace, unshare_trace, update_trace, delete_trace (eager)
├── git_auth ← is_auth_ok (eager — for push decision)
├── trace.trace_recorder ← get_trace, post_trace_to_chat (lazy — inside handler)
├── ledger.worktree ← push_ledger_branch (lazy — inside handler, background thread)
└── helpers ← project_root (eager)
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `trace_bp`, registers at `/api` |
| Debugging tab | `scripts/_debugging.html` | All trace endpoints |
| Chat | `scripts/content/_chat.html` | Shared traces appear in chat |

---

## Data Shapes

### `GET /api/trace/list?n=5` response

```json
{
    "traces": [
        {
            "trace_id": "abc-123-def-456",
            "name": "Deploy v2.1",
            "classification": "deployment",
            "created_at": "2026-03-02T15:30:00",
            "duration_s": 142.5,
            "event_count": 15,
            "shared": true,
            "auto_summary": "Applied 3 K8s manifests, updated 2 Helm releases"
        }
    ]
}
```

### `POST /api/trace/start` request + response

```json
// Request:
{ "name": "Debugging auth flow", "classification": "debugging" }

// Response:
{ "trace_id": "xyz-789-..." }
```

### `POST /api/trace/stop` response

```json
{
    "trace_id": "xyz-789-...",
    "name": "Debugging auth flow",
    "event_count": 8,
    "duration_s": 95.3,
    "auto_summary": "Ran 3 quality checks, updated 2 configs",
    "saved": true
}
```

### `GET /api/trace/events?trace_id=abc-123` response

```json
{
    "trace_id": "abc-123",
    "events": [
        {
            "type": "api_call",
            "endpoint": "/k8s/apply",
            "method": "POST",
            "ts": "2026-03-02T15:30:05",
            "result": { "ok": true }
        },
        {
            "type": "action",
            "action": "deploy:k8s",
            "ts": "2026-03-02T15:30:10",
            "duration_ms": 3200,
            "result": { "ok": true }
        }
    ]
}
```

---

## Advanced Feature Showcase

### 1. Background Ledger Push

When sharing a trace, the git push runs in a **daemon thread**
so the API responds immediately without waiting for the push:

```python
threading.Thread(target=push_ledger_branch, args=(root,), daemon=True).start()
```

### 2. Cross-Feature Integration (Trace → Chat)

Sharing a trace also posts it to the team chat, creating
a cross-reference between the Debugging tab and Content → Chat:

```python
post_trace_to_chat(root, trace, thread_id=thread_id)
```

### 3. Conditional Git Push

The push only happens if git auth is available — no error
if the user hasn't configured SSH credentials:

```python
if is_auth_ok():
    # push in background
```

### 4. Delete vs Unshare Semantics

- **Delete** removes the local file (`.state/traces/<id>.json`).
  Ledger copy persists if shared.
- **Unshare** marks as local-only but keeps the local file.
  Both require separate actions for full removal.

### 5. Auto-Summary Generation

When a recording stops, the engine generates a human-readable
summary of what happened during the session based on captured events.

---

## Design Decisions

### Why no caching on trace endpoints

Traces are user-generated, infrequently queried data. The file
count is small enough that reading from `.state/traces/` is fast.
Caching would add complexity without meaningful performance gain.

### Why sharing uses POST, not PATCH

Sharing modifies the trace's state and triggers side-effects
(chat post, git push). POST communicates "action with side-effects"
more clearly than PATCH.

### Why all handlers have try/except

Trace operations involve filesystem I/O, git operations, and
inter-service calls (chat, ledger). Any of these can fail for
external reasons. The blanket exception handling ensures the API
always returns JSON, never an HTML error page.

---

## Coverage Summary

| Capability | Endpoint | Method | Tracked | Cached |
|-----------|----------|--------|---------|--------|
| Start recording | `/trace/start` | POST | No | No |
| Stop recording | `/trace/stop` | POST | No | No |
| Active recordings | `/trace/active` | GET | No | No |
| List traces | `/trace/list` | GET | No | No |
| Get trace | `/trace/get` | GET | No | No |
| Get events | `/trace/events` | GET | No | No |
| Share trace | `/trace/share` | POST | No | No |
| Unshare trace | `/trace/unshare` | POST | No | No |
| Update trace | `/trace/update` | POST | No | No |
| Delete trace | `/trace/delete` | POST | No | No |
