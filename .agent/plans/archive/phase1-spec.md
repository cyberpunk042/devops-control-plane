# Phase 1 — Infrastructure Spec

> **Status:** Active analysis — narrowing to implementation-ready specs.
> **Source of truth:** `TECHNOLOGY_SPEC.md` + `PROJECT_SCOPE.md`
> **Parent:** `alpha-milestones2.md`
> **Created:** 2026-02-17

---

## Phase 1 Overview

Phase 1 builds the **infrastructure** that Phase 2 and 3 consume.
Three sub-phases, each depending on the previous:

```
1A. Git-Native Ledger ──→ 1B. SCP Chat ──→ 1C. Session Tracing
    (storage)                (messaging)       (recording)
```

---

---

# 1A. GIT-NATIVE LEDGER SYSTEM — DETAILED SPEC

---

## 1A.1 Problem Statement

Today, operational history lives in two places:
- `.state/audit.ndjson` — local, ephemeral, not version-controlled
- `.state/audit_activity.json` — local, ephemeral, UI-facing activity log

Both are **local-only files** that:
- Are lost if `.state/` is gitignored or deleted
- Cannot be shared across machines or team members
- Cannot be referenced from commits or tags
- Have no relationship to the code they were generated against

**1A solves this** by creating a git-native storage layer for operational
data that:
- Lives in the repository (pushable, pullable)
- Does not pollute the main code history
- Has stable, referenceable handles (tags)
- Can hold arbitrary artifacts (logs, reports, diffs)

---

## 1A.2 Existing Code Inventory

### What We Build On

| Component | File | What It Does | What We Reuse |
|-----------|------|-------------|---------------|
| `run_git()` | `src/core/services/git_ops.py:31` | Low-level `subprocess.run` wrapper for git CLI | The subprocess pattern, cwd handling, timeout |
| `run_gh()` | `src/core/services/git_ops.py:48` | Low-level wrapper for `gh` CLI | Not needed for 1A |
| `GitAdapter` | `src/adapters/vcs/git.py` | Adapter protocol for git (status, commit, push, log, branch, diff, init) | Architecture pattern (but 1A is a core service, not an adapter) |
| `AuditWriter` | `src/core/persistence/audit.py` | Append-only NDJSON writer/reader | The audit model — **1A runs alongside this, not replacing it** |
| `AuditEntry` | `src/core/persistence/audit.py:28` | Pydantic model for audit log entries | Schema reference — run metadata is similar |
| `save_state()` | `src/core/persistence/state_file.py` | Atomic JSON write (temp + rename) | Not directly, but the atomic-write discipline applies |
| Event bus | `src/core/services/event_bus.py` | In-process pub/sub, SSE to clients | Ledger writes can publish events |

### What Does NOT Exist Yet

| Need | Description |
|------|-------------|
| Worktree management | `git worktree add/remove` for the dedicated `.scp-ledger` directory |
| Orphan branch creation | Creating `scp-ledger` as an orphan branch (no shared history with main) |
| Git notes operations | `git notes add`, `git notes append`, `git notes show`, under a custom ref |
| Annotated tag creation | `git tag -a` with JSON-structured messages |
| Tag listing/filtering | `git tag -l 'scp/run/*'` with metadata parsing |
| `.scp-ledger` in `.gitignore` | The worktree directory must be gitignored in the main repo |

---

## 1A.3 Architecture Decision: Dedicated Worktree

**Question:** How do we write to `scp-ledger` without disturbing the user's
working tree (they're on `main`, we can't `git checkout scp-ledger`)?

### **Decision: Dedicated Worktree at `.scp-ledger/`**

Use `git worktree add` to create a **persistent secondary worktree** for
the `scp-ledger` branch at `.scp-ledger/` (project root). This directory
is gitignored in the main repo.

```
# Bootstrap (one-time, idempotent):
git fetch origin scp-ledger:scp-ledger 2>/dev/null || true
git worktree add -B scp-ledger .scp-ledger scp-ledger

# Write to the ledger (normal file I/O):
mkdir -p .scp-ledger/ledger/runs/<run_id>
cp run.json .scp-ledger/ledger/runs/<run_id>/run.json

# Commit without disturbing the user's branch:
git -C .scp-ledger add ledger/runs/<run_id>/run.json
git -C .scp-ledger commit -m "ledger: run <run_id>"

# Before push — rebase to avoid conflicts:
git -C .scp-ledger pull --rebase origin scp-ledger
git -C .scp-ledger push origin scp-ledger
```

### Why This Works

- **User stays on whatever branch they're on** — `git -C .scp-ledger`
  operates in the worktree's own context, not the main worktree
- **No staging/index changes in the main worktree** — the worktree has
  its own index file
- **No "dirty repo" effect** — `.scp-ledger/` is in `.gitignore`
- **Normal file I/O** — `mkdir`, `open()`, `write()`, `json.dump()` — no
  git plumbing complexity
- **Concurrency safety** — `pull --rebase` before push handles the common
  case of concurrent writers on different machines
- **Persistent** — the worktree stays in place between operations, no
  create/remove overhead on every write

### Why Not Git Plumbing

Git plumbing (`hash-object → mktree → commit-tree → update-ref`) would
also work but adds substantial complexity for tree construction and
merging. The worktree approach gives us the same isolation with far
simpler code — we just write files and commit.

### `.gitignore` Entry

```
# SCP Ledger worktree (Phase 1A)
.scp-ledger/
```

---

## 1A.4 Data Model

### Run

A **Run** represents a single significant operation that was executed.

```python
class Run(BaseModel):
    """A recorded execution run."""

    run_id: str                          # e.g. "run_2026-02-17T204500_k8s-apply"
    type: str                            # operation type: "detect", "apply", "generate", etc.
    subtype: str = ""                    # more specific: "k8s:apply", "vault:unlock", etc.
    status: Literal["ok", "failed", "partial"] = "ok"
    user: str = ""                       # from git config user.name or system
    code_ref: str = ""                   # commit SHA that was HEAD at run time
    started_at: str                      # ISO 8601
    ended_at: str                        # ISO 8601
    duration_ms: int = 0
    environment: str = ""
    modules_affected: list[str] = Field(default_factory=list)
    summary: str = ""                    # one-line human summary
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### Run Events (JSONL)

Each run can have a stream of fine-grained events:

```jsonl
{"seq":1,"ts":"...","type":"adapter:execute","adapter":"shell","action_id":"...","status":"ok","duration_ms":142}
{"seq":2,"ts":"...","type":"adapter:execute","adapter":"git","action_id":"...","status":"ok","duration_ms":50}
{"seq":3,"ts":"...","type":"run:complete","summary":"Applied 3 K8s resources"}
```

### Ledger Branch Layout

```
scp-ledger (orphan branch)
└── ledger/
    └── runs/
        └── <run_id>/
            ├── run.json        # Run model (metadata)
            └── events.jsonl    # Event stream (optional, can be empty)
```

Artifacts (reports, diffs, generated files) are a **future extension** — not
in the 1A scope. The structure supports them (`artifacts/` dir) but we don't
write them yet.

### Run Anchor Tags

```
refs/tags/scp/run/<run_id>
  ├── Type: annotated tag
  ├── Target: the commit on main that was HEAD at run time
  ├── Message: JSON string of the Run model (compact, single-line)
  └── Tagger: git config user.name / user.email
```

---

## 1A.5 Service API

### File: `src/core/services/ledger/worktree.py`

Worktree and git operations for the ledger. Uses `git -C` to operate
in the `.scp-ledger` directory without touching the main worktree.

```python
def _run_ledger_git(
    *args: str,
    project_root: Path,
    timeout: int = 15,
) -> subprocess.CompletedProcess[str]:
    """Run a git command in the .scp-ledger worktree.

    Equivalent to: git -C <project_root>/.scp-ledger <args>
    """

def _run_main_git(
    *args: str,
    project_root: Path,
    timeout: int = 15,
) -> subprocess.CompletedProcess[str]:
    """Run a git command in the main repo (for tags, notes, fetch)."""

def ensure_worktree(project_root: Path) -> Path:
    """Ensure the .scp-ledger worktree exists and is attached.

    Steps:
      1. Fetch scp-ledger from origin (ignore if no remote or no branch)
      2. If scp-ledger branch doesn't exist locally, create it as orphan
      3. If .scp-ledger/ dir doesn't exist, `git worktree add -B scp-ledger .scp-ledger scp-ledger`
      4. Ensure .scp-ledger is in .gitignore

    Idempotent — safe to call on every operation.
    Returns the worktree path (.scp-ledger/).
    """

def worktree_path(project_root: Path) -> Path:
    """Return the worktree directory path: <project_root>/.scp-ledger"""

# ── Tag operations (run from main repo) ─────────────────────

def create_run_tag(
    project_root: Path,
    tag_name: str,
    target_sha: str,
    *,
    message: str,
) -> None:
    """Create an annotated tag in the main repo."""

def list_run_tags(project_root: Path) -> list[str]:
    """List tags matching 'scp/run/*'."""

def read_tag_message(project_root: Path, tag_name: str) -> str:
    """Read the message of an annotated tag."""

# ── Notes operations (run from main repo) ────────────────────

def notes_append(
    project_root: Path,
    ref: str,
    target: str,
    content: str,
) -> None:
    """Append content to a git note under the given ref."""

def notes_show(
    project_root: Path,
    ref: str,
    target: str,
) -> str | None:
    """Read a git note from a target object, or None."""
```

### File: `src/core/services/ledger/ledger_ops.py`

Business logic for ledger operations. Uses `worktree.py`.

```python
def ensure_ledger(project_root: Path) -> Path:
    """Ensure ledger worktree is ready. Returns worktree path.

    Calls ensure_worktree(). Idempotent.
    """

def record_run(
    project_root: Path,
    run: Run,
    events: list[dict] | None = None,
) -> str:
    """Record a run to the ledger.

    1. ensure_ledger()
    2. mkdir -p .scp-ledger/ledger/runs/<run_id>/
    3. Write run.json (json.dump)
    4. Write events.jsonl (if events provided)
    5. git -C .scp-ledger add + commit
    6. Create annotated tag: scp/run/<run_id> → current HEAD on main

    Returns the run_id.
    """

def list_runs(project_root: Path, *, n: int = 20) -> list[Run]:
    """List recent runs by reading scp/run/* annotated tags.

    Parses tag messages (compact JSON).
    Returns newest-first, limited to n.
    """

def get_run(project_root: Path, run_id: str) -> Run | None:
    """Get a single run's metadata from its tag."""

def get_run_events(project_root: Path, run_id: str) -> list[dict]:
    """Read events.jsonl from .scp-ledger/ledger/runs/<run_id>/.

    Direct file read from the worktree (no git show needed).
    """

def push_ledger(project_root: Path) -> bool:
    """Push scp-ledger branch and scp/run/* tags to origin.

    Steps:
      1. git -C .scp-ledger pull --rebase origin scp-ledger
      2. git -C .scp-ledger push origin scp-ledger
      3. git push origin 'refs/tags/scp/run/*'

    Returns True if push succeeded.
    """

def pull_ledger(project_root: Path) -> bool:
    """Pull scp-ledger branch and scp/run/* tags from origin.

    Steps:
      1. git -C .scp-ledger pull --rebase origin scp-ledger
      2. git fetch origin 'refs/tags/scp/run/*:refs/tags/scp/run/*'

    Returns True if pull succeeded.
    """
```

### File: `src/core/services/ledger/__init__.py`

Re-exports the public API.

---

## 1A.6 Integration Points

### With Existing Audit Log

The audit log (`.state/audit.ndjson`) continues to exist. The ledger is
additive. The integration is:

```
Operation happens
  ├──→ AuditWriter.write(entry)           # local, always, fast
  └──→ ledger_ops.record_run(run, events) # git, selective, slightly slower
```

**What triggers a run record?** Not every audit entry becomes a run. Only
"significant" operations. The significance decision is made by the caller
(the engine, a use case, or the web route), not by the ledger service.

Examples of operations that create runs:
- Wizard completion (generated manifests, Dockerfiles, etc.)
- K8s apply / Terraform plan+apply
- Vault lock/unlock/export
- Git commit+push
- Backup create/restore
- Detection scan (full)

Examples that do NOT create runs:
- Cache hit
- SSE heartbeat
- Status poll
- Individual API calls (unless part of a larger operation)

### With Event Bus

```python
# In record_run():
bus.publish("ledger:run", key=run.run_id, data={
    "type": run.type,
    "status": run.status,
    "summary": run.summary,
})
```

This lets the UI show a "Run recorded" notification in real-time.

### With Phase 1B (Chat) — Future

SCP Chat will attach messages to run tags using git notes. The ledger
provides the tag objects that chat messages attach to.

---

## 1A.7 Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| `.scp-ledger/` not in `.gitignore` | Medium | `ensure_worktree()` checks and adds to `.gitignore` automatically |
| Worktree left in broken state (interrupted commit) | Medium | `ensure_worktree()` validates worktree health on startup; recreate if detached |
| scp-ledger branch conflicts on pull | Medium | `pull --rebase` before push. Conflicts only if two machines write the same run_id (timestamp + random suffix prevents this) |
| Tag namespace collision | Low | `scp/run/<run_id>` where run_id = `<ISO-timestamp>_<type>_<4-char-random>`. Collision astronomically unlikely |
| User deletes `.scp-ledger/` directory | Low | `ensure_worktree()` recreates it. Branch still exists. Tags still exist. Only the local worktree checkout is lost |
| User deletes scp-ledger branch | Low | `ensure_worktree()` recreates it as orphan. Runs in tags survive (tags are independent of branches). Historical ledger data on the branch is lost but can be re-fetched if origin exists |
| `.git` directory size growth | Medium | Events.jsonl is compact. Artifacts are future scope. Monitor size. Consider `git gc` reminders |
| Worktree breaks `git status` | None | Git is worktree-aware — `git status` in the main worktree ignores `.scp-ledger/` completely (it has its own `.git` link) |

---

## 1A.8 Acceptance Criteria

### Must Have (1A is not done without these)

- [ ] `ensure_worktree()` creates `scp-ledger` orphan branch + `.scp-ledger/` worktree if missing
- [ ] `ensure_worktree()` adds `.scp-ledger/` to `.gitignore` if not already there
- [ ] `record_run()` writes `run.json` + optional `events.jsonl` to `.scp-ledger/`
      via normal file I/O, commits via `git -C .scp-ledger`
- [ ] `record_run()` creates annotated tag `scp/run/<run_id>` pointing to
      current HEAD on main
- [ ] `list_runs()` returns runs from tags, newest-first
- [ ] `get_run()` reads a single run's metadata from its tag
- [ ] `get_run_events()` reads events.jsonl from `.scp-ledger/ledger/runs/<id>/`
- [ ] `push_ledger()` pushes branch + tags to origin
- [ ] `pull_ledger()` pulls branch + tags from origin
- [ ] All functions return errors gracefully (no exceptions to callers)
- [ ] Works in a repo with no remote (push/pull skip gracefully)
- [ ] Works in a fresh repo (no commits yet — deferred until first commit)
- [ ] Unit tests for worktree/tag/notes helpers (isolated git repo in tmp)
- [ ] Integration test: ensure_worktree → record_run → list_runs → get_run → verify

### Nice to Have (can defer to 1A.1)

- [ ] `delete_run()` removes a tag + its ledger data
- [ ] `prune_runs()` removes runs older than N days
- [ ] CLI commands: `scp ledger list`, `scp ledger show <run_id>`
- [ ] Web route: `GET /api/ledger/runs`

---

## 1A.9 File Layout

```
src/core/services/ledger/
├── __init__.py            # Re-exports: record_run, list_runs, get_run, etc.
├── worktree.py            # Worktree management, git -C helpers, tag/notes ops
├── ledger_ops.py          # Business logic: ensure_ledger, record, list, get, push, pull
└── models.py              # Run model (Pydantic)

tests/
└── core/
    └── services/
        └── ledger/
            ├── test_worktree.py
            └── test_ledger_ops.py
```

### Runtime Directory Layout (at project root)

```
<project_root>/
├── .scp-ledger/               # ← worktree (gitignored, persistent)
│   ├── .git                   # ← link back to main repo's .git/worktrees/
│   └── ledger/
│       └── runs/
│           ├── run_2026-02-17T204500_detect_a1b2/
│           │   ├── run.json
│           │   └── events.jsonl
│           └── run_2026-02-17T210800_k8s-apply_c3d4/
│               ├── run.json
│               └── events.jsonl
├── .gitignore                 # ← contains ".scp-ledger/"
├── .git/
│   └── worktrees/
│       └── .scp-ledger/       # ← git's worktree tracking
└── ... (rest of project)
```

---

---

# 1B. SCP CHAT — DETAILED SPEC

> **Depends on:** 1A (ledger branch, worktree, tags, git notes primitives)
> **Status:** Refined — ready to implement

---

## 1B.1 Problem Statement

Operational context is scattered:
- Commit messages are terse (one-line summaries)
- Audit logs are machine-generated (no human intent)
- Conversations about operations happen in Slack/Discord/email (not linked
  to the code or the operations)

**1B solves this** by providing an embedded messaging system that:
- Lives in the git repository (via git notes + ledger branch)
- Links messages to specific operations via run tags
- Supports threads for organized discussions
- Lets users choose what's public vs. private, encrypted vs. plaintext
- Can eventually bridge to Slack/Discord

---

## 1B.2 Storage Architecture (decided)

**Two storage locations, one pattern:**

| Message type | Where | Why |
|---|---|---|
| **Run-attached** | Git notes on `refs/notes/scp-chat` → target = annotated tag object for `scp/run/<run_id>` | Natural anchoring — message is literally attached to the operation's tag |
| **Thread / free-floating** | `.scp-ledger/chat/threads/<thread_id>/messages.jsonl` on the ledger branch | File I/O, same pattern as run storage, no synthetic objects |

**Thread metadata** lives at `.scp-ledger/chat/threads/<thread_id>/thread.json`.

No synthetic root objects. No ambiguity.

### Run-attached messages (git notes)

```
refs/notes/scp-chat                       ← notes ref
  └── note on tag scp/run/run_42          ← JSONL content
        line 1: {"id":"msg_01","text":"Deployed to staging","..."}
        line 2: {"id":"msg_02","text":"Health checks passed","..."}
```

### Thread messages (ledger branch files)

```
.scp-ledger/
├── ledger/runs/...                       ← 1A (existing)
└── chat/
    └── threads/
        └── <thread_id>/
            ├── thread.json               ← Thread metadata
            └── messages.jsonl            ← Messages in this thread
```

---

## 1B.3 Message Model

```python
class MessageFlags(BaseModel):
    """Per-message control flags."""

    publish: bool = False       # eligible for public rendering
    encrypted: bool = False     # text field is ENC:v1:...


class ChatMessage(BaseModel):
    """A single chat message."""

    id: str = ""                                 # msg_<timestamp>_<4char>
    ts: str = Field(default_factory=_now_iso)    # ISO 8601
    user: str = ""                               # git user.name
    text: str = ""                               # plaintext or ENC:v1:...
    thread_id: str | None = None                 # null = timeline, set = in thread
    run_id: str | None = None                    # attached to a run (tag anchor)
    source: Literal["manual", "trace", "system"] = "manual"
    flags: MessageFlags = Field(default_factory=MessageFlags)


class Thread(BaseModel):
    """A conversation thread."""

    thread_id: str = ""                          # thread_<timestamp>_<4char>
    title: str = ""
    created_at: str = Field(default_factory=_now_iso)
    created_by: str = ""
    anchor_run: str | None = None                # optional run anchor
    tags: list[str] = Field(default_factory=list)
```

**Dropped from model (deferred):** `refs` (@-references), `trace_id` (can be in
message text or metadata when needed).

---

## 1B.4 Encryption (decided)

**Key source:** `CONTENT_VAULT_ENC_KEY` from `.env` — same key used by the
content vault (`content_crypto.py`) and backups (`backup_common.py`).

Read via existing `get_enc_key(project_root)` from `src/core/services/backup_common.py`.

**Implementation:**
- Direct AES-256-GCM encryption of message text (not COVAULT envelope — too
  heavy for short strings)
- Key derivation: PBKDF2-SHA256 from `CONTENT_VAULT_ENC_KEY` with per-message
  random salt (same constants as `vault.py`)
- Format: `"ENC:v1:<base64-salt>:<base64-iv>:<base64-ciphertext+tag>"`
- If `CONTENT_VAULT_ENC_KEY` is not set and `encrypt=True` → error, don't
  silently skip
- If key is not available during list → encrypted messages show
  `text="[encrypted]"` with `flags.encrypted=True`

### File: `src/core/services/chat/chat_crypto.py`

```python
def encrypt_text(plaintext: str, project_root: Path) -> str:
    """Encrypt text using CONTENT_VAULT_ENC_KEY → 'ENC:v1:...' string."""

def decrypt_text(enc_text: str, project_root: Path) -> str:
    """Decrypt 'ENC:v1:...' string → plaintext. Raises ValueError if no key."""

def is_encrypted(text: str) -> bool:
    """Check if text is in ENC:v1:... format."""
```

---

## 1B.5 Service API

### File: `src/core/services/chat/chat_ops.py`

```python
def send_message(
    project_root: Path,
    text: str,
    *,
    user: str = "",
    thread_id: str | None = None,
    run_id: str | None = None,
    publish: bool = False,
    encrypt: bool = False,
    source: str = "manual",
) -> ChatMessage:
    """Send a message.

    Routing:
      - If run_id is set → writes JSONL line to git notes on the run's tag
      - If thread_id is set → appends to .scp-ledger/chat/threads/<id>/messages.jsonl
      - If both set → writes to both locations
      - If neither → creates/uses a 'general' thread

    Publishes chat:message event to event bus.
    """

def list_messages(
    project_root: Path,
    *,
    run_id: str | None = None,      # read from git notes
    thread_id: str | None = None,   # read from thread files
    n: int = 50,
) -> list[ChatMessage]:
    """List messages, newest-first.

    Auto-decrypts if CONTENT_VAULT_ENC_KEY is available.
    If key unavailable, encrypted messages have text='[encrypted]'.
    """

def create_thread(
    project_root: Path,
    title: str,
    *,
    user: str = "",
    anchor_run: str | None = None,
    tags: list[str] | None = None,
) -> Thread:
    """Create a new thread. Writes thread.json to ledger branch."""

def list_threads(project_root: Path) -> list[Thread]:
    """List all threads from .scp-ledger/chat/threads/*/thread.json."""

def push_chat(project_root: Path) -> bool:
    """Push refs/notes/scp-chat + ledger chat directory to origin."""

def pull_chat(project_root: Path) -> bool:
    """Pull refs/notes/scp-chat + ledger chat directory from origin."""
```

### File: `src/core/services/chat/chat_refs.py` (DEFERRED)

`@`-reference parsing and autocomplete are deferred to post-1B.

---

## 1B.6 File Layout

```
src/core/services/chat/
├── __init__.py          ← public API re-exports
├── models.py            ← ChatMessage, Thread, MessageFlags
├── chat_ops.py          ← send, list, thread CRUD, push/pull
└── chat_crypto.py       ← encrypt_text / decrypt_text using CONTENT_VAULT_ENC_KEY
```

---

## 1B.7 Acceptance Criteria

### Must Have

- [ ] `send_message()` with `run_id` writes JSONL to git notes on the run tag
- [ ] `send_message()` with `thread_id` writes JSONL to thread's messages.jsonl
- [ ] `list_messages(run_id=...)` reads from git notes
- [ ] `list_messages(thread_id=...)` reads from thread files
- [ ] `create_thread()` creates thread.json on ledger branch
- [ ] `list_threads()` scans .scp-ledger/chat/threads/*/thread.json
- [ ] `encrypt=True` encrypts text using `CONTENT_VAULT_ENC_KEY`
- [ ] `encrypt=True` errors if `CONTENT_VAULT_ENC_KEY` not set
- [ ] `publish=True` sets the flag (rendering is future scope)
- [ ] `push_chat()` / `pull_chat()` sync notes and thread files
- [ ] All functions handle missing refs/notes/files gracefully
- [ ] `chat:message` event published to event bus on send

### Nice to Have (defer)

- [ ] `@`-reference parsing and autocomplete (`chat_refs.py`)
- [ ] Web UI tab for chat
- [ ] CLI `chat send` / `chat list`
- [ ] Public rendering of published messages

---

---

# 1C. SESSION TRACING — DETAILED SPEC

> **Depends on:** 1A (ledger for trace storage) + 1B (chat for auto-messages)

---

## 1C.1 Problem Statement

Users perform multi-step operations in the UI (unlock vault → apply manifests →
commit → push). Today there's no way to:
- Know that these steps were part of the same logical operation
- Get a summary of what was done in a session
- Share a narrative about the session with others

**1C solves this** by providing opt-in recording that captures operations
into a structured trace, stores it on the ledger, and optionally generates
a chat message.

---

## 1C.2 Recording Model

```python
class TraceEvent(BaseModel):
    """A single event within a session trace."""
    seq: int
    ts: str
    type: str          # event bus type (e.g. "cache:done", "vault:unlock")
    target: str = ""   # what was acted on
    result: str = ""   # ok, failed, skipped
    duration_ms: int = 0
    detail: dict[str, Any] = Field(default_factory=dict)


class SessionTrace(BaseModel):
    """A recorded session."""
    trace_id: str
    name: str = ""
    classification: str = ""  # deployment, debugging, config, exploration
    started_at: str
    ended_at: str | None = None
    user: str = ""
    code_ref: str = ""         # HEAD at start
    events: list[TraceEvent] = Field(default_factory=list)
    auto_summary: str = ""
    audit_refs: list[str] = Field(default_factory=list)
```

---

## 1C.3 Service API

### File: `src/core/services/trace/trace_recorder.py`

```python
def start_recording(
    project_root: Path,
    *,
    name: str = "",
    classification: str = "",
    user: str = "",
) -> str:
    """Start recording. Returns trace_id. Subscribes to event bus."""

def stop_recording(trace_id: str) -> SessionTrace:
    """Stop recording. Generates auto-summary. Returns the trace."""

def save_trace(project_root: Path, trace: SessionTrace) -> None:
    """Save trace to ledger branch."""

def generate_summary(trace: SessionTrace) -> str:
    """Generate a one-line summary from trace events (deterministic)."""
```

---

## 1C.4 Acceptance Criteria

### Must Have

- [ ] `start_recording()` subscribes to event bus and captures events
- [ ] `stop_recording()` produces a `SessionTrace` with auto-summary
- [ ] `save_trace()` stores trace on ledger branch
- [ ] Multiple concurrent recordings supported
- [ ] Summary generation is deterministic (template-based, not AI)

### Nice to Have (defer)

- [ ] Auto-post trace summary as chat message
- [ ] UI toggle for recording
- [ ] Trace classification suggestions

---

---

# IMPLEMENTATION ORDER

```
Step 1: models.py (Run)            ← Pydantic model, no deps
Step 2: worktree.py                ← worktree setup, git -C helpers, tag/notes ops
Step 3: ledger_ops.py              ← uses Step 1 + 2 (ensure, record, list, get)
Step 4: Wire into event bus        ← publish ledger events
Step 5: push/pull (ledger_ops)     ← sync with origin
Step 6: ─── 1A COMPLETE ───

Step 7: chat models.py             ← Pydantic models for messages/threads
Step 8: chat_ops.py                ← uses worktree.py (notes), chat models
Step 9: chat encryption            ← integrate vault key for encrypt/decrypt
Step 10: ─── 1B COMPLETE (core) ───

Step 11: trace models.py           ← Pydantic model for traces
Step 12: trace_recorder.py         ← event bus subscriber, summary generator
Step 13: trace → ledger + chat     ← storage and message generation
Step 14: ─── 1C COMPLETE (core) ───

Steps 15+: CLI commands, Web routes/UI, @-autocomplete
```

**Start point:** Step 1 (`models.py`) — Pydantic model, zero
dependencies. Then Step 2 (`worktree.py`) — pure git CLI wrappers,
testable in an isolated tmp repo.

---

*This spec is Phase 1 only. Phase 2 (Wizard + Integrations) and Phase 3
(Visualization) specs will be written when Phase 1 is underway.*
