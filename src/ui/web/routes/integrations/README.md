# Integrations Routes — Git, GitHub, Remotes & Terminal API

> **7 files · 514 lines · 21 endpoints · Blueprint: `integrations_bp` · Prefix: `/api`**
>
> The largest route package. Five sub-domains under a single blueprint:
>
> 1. **Git operations** — status, log, commit, pull, push (5 endpoints)
> 2. **GitHub observation** — status, pull requests, Actions runs,
>    Actions dispatch, workflows, user, repo info (7 endpoints)
> 3. **GitHub authentication** — login (token, interactive, auto-drive),
>    logout, token extract, device flow start/poll, terminal poll (6 endpoints)
> 4. **GitHub repo management** — create repo, set visibility, set
>    default branch (3 endpoints)
> 5. **Git remote management** — list, add, remove, rename, set-url
>    (5 endpoints via `remotes.py`, sharing route prefix with `git.py`)
> 6. **Terminal status** — terminal emulator availability (1 endpoint)
>
> All delegate through a backward-compat shim (`git_ops.py`) to four
> core service modules:
> - `git/ops.py` (301 lines) — git commands
> - `git/gh_api.py` (230 lines) — GitHub queries
> - `git/gh_auth.py` (537 lines) — GitHub auth flows
> - `git/gh_repo.py` (236 lines) — repo + remote management
> - `terminal_ops.py` (351 lines) — terminal detection + spawn

---

## How It Works

### Request Flow

```
Frontend
│
├── integrations/_git.html ──────── Git panel
│   ├── GET  /api/git/status        (cached)
│   ├── GET  /api/git/log
│   ├── POST /api/git/commit
│   ├── POST /api/git/pull          (@requires_git_auth)
│   └── POST /api/git/push          (@requires_git_auth)
│
├── integrations/_github.html ───── GitHub panel
│   ├── GET  /api/integrations/gh/status  (cached)
│   ├── GET  /api/gh/pulls                (cached)
│   ├── GET  /api/gh/actions/runs         (cached)
│   ├── GET  /api/gh/actions/workflows    (cached)
│   ├── POST /api/gh/actions/dispatch
│   ├── GET  /api/gh/user
│   └── GET  /api/gh/repo/info
│
├── auth/_gh_auth.html ──────────── GitHub auth panel
│   ├── POST /api/gh/auth/login
│   ├── POST /api/gh/auth/logout
│   ├── GET  /api/gh/auth/token
│   ├── POST /api/gh/auth/device
│   ├── GET  /api/gh/auth/device/poll
│   └── GET  /api/gh/auth/terminal/poll
│
├── integrations/setup/_git.html ── Remote management
│   ├── GET  /api/git/remotes
│   ├── POST /api/git/remote/add
│   ├── POST /api/git/remote/remove
│   ├── POST /api/git/remote/rename
│   └── POST /api/git/remote/set-url
│
├── integrations/setup/_github.html ── Repo management
│   ├── POST /api/gh/repo/create
│   ├── POST /api/gh/repo/visibility
│   └── POST /api/gh/repo/default-branch
│
└── globals/_ops_modal.html ─────── Terminal status
    └── GET  /api/ops/terminal/status
     │
     ▼
routes/integrations/                   ← HTTP layer (this package)
├── __init__.py   — blueprint definition
├── git.py        — git operations
├── github.py     — GitHub observation
├── gh_auth.py    — GitHub authentication
├── gh_repo.py    — GitHub repo management
├── remotes.py    — git remote management
└── terminal.py   — terminal availability
     │
     ▼
core/services/git/                     ← Business logic
├── ops.py      (301 lines) — run_git, run_gh, status, log, commit, pull, push
├── gh_api.py   (230 lines) — gh_status, pulls, actions, user, repo_info
├── gh_auth.py  (537 lines) — login, logout, token, device flow
└── gh_repo.py  (236 lines) — create, visibility, remotes

core/services/terminal_ops.py (351 lines)
└── terminal_status, spawn_terminal, detect_terminal
```

### Git Status Pipeline (Cached)

```
GET /api/git/status?bust=1
     │
     ▼
devops_cache.get_cached(root, "git", lambda: git_ops.git_status(root))
     │
     ├── Cache HIT → return cached status
     └── Cache MISS → git_ops.git_status(root)
         │
         ├── git rev-parse --abbrev-ref HEAD → branch name
         ├── git status --porcelain=v2 -b → dirty files + tracking
         │   Parse:
         │   ├── # branch.oid → commit hash
         │   ├── # branch.head → branch name
         │   ├── # branch.upstream → upstream ref
         │   ├── # branch.ab → ahead/behind counts
         │   ├── 1 .M ... → modified file (unstaged)
         │   ├── 1 M. ... → modified file (staged)
         │   └── ? ... → untracked file
         │
         ├── git stash list → stash count
         │
         └── Return:
             {
                 branch, commit_hash,
                 upstream, ahead, behind,
                 dirty_count, untracked_count,
                 staged: [{path, status}],
                 unstaged: [{path, status}],
                 untracked: [paths],
                 stash_count,
                 has_remote
             }
```

### Git Commit Pipeline

```
POST /api/git/commit  { message: "feat: add feature", files: ["src/foo.py"] }
     │
     ├── Validation: message must be non-empty → 400 if missing
     │
     ▼
git_ops.git_commit(root, "feat: add feature", files=["src/foo.py"])
     │
     ├── files specified?
     │   ├── YES → git add src/foo.py (selective staging)
     │   └── NO  → git add -A (stage everything)
     │
     ├── git commit -m "feat: add feature"
     │
     └── Return:
         ├── Success: { ok: true, hash: "abc1234", message: "feat: add feature" }
         └── Error:   { error: "nothing to commit" }
```

### Git Pull / Push Pipeline (Auth-Gated)

```
POST /api/git/pull  { rebase: true }
     │
     ├── @requires_git_auth
     │   ├── is_auth_ok()? YES → proceed
     │   └── NO → 401 + bus.publish("auth:needed") → auth modal
     │
     ├── @run_tracked("git", "git:pull")
     │
     ▼
git_ops.git_pull(root, rebase=True)
     │
     ├── Build args: ["pull"]
     │   └── rebase=True → ["pull", "--rebase"]
     ├── env=git_env()  (includes ssh-agent vars)
     └── Return: { ok: true } or { error: "..." }

POST /api/git/push  { force: true }
     │
     ├── Same auth gate + tracking
     │
     ▼
git_ops.git_push(root, force=True)
     │
     ├── Build args: ["push"]
     │   └── force=True → ["push", "--force-with-lease"]
     ├── env=git_env()
     └── Return: { ok: true } or { error: "..." }
```

### GitHub Auth Login Pipeline (Three Modes)

```
POST /api/gh/auth/login
     │
     ├── Mode 1: Token (non-interactive)
     │   Body: { token: "ghp_abc123..." }
     │   │
     │   └── gh auth login --with-token
     │       stdin: "ghp_abc123..."
     │       │
     │       └── On success:
     │           ├── Invalidate cache: "github", "wiz:detect"
     │           └── Return: { ok: true, authenticated: true }
     │
     ├── Mode 2: Interactive terminal (auto_drive)
     │   Body: { auto_drive: true }
     │   │
     │   ├── _build_auto_drive_script()
     │   │   Creates bash script that:
     │   │   1. Writes signal file (.gh-auth-result) → { status: "running" }
     │   │   2. Runs: gh auth login -h github.com -p https -w
     │   │   3. Captures device code from stdout
     │   │   4. Updates signal file → { status: "code_ready", code: "XXXX-XXXX" }
     │   │   5. Waits for auth completion
     │   │   6. Updates signal file → { status: "success" }
     │   │
     │   ├── spawn_terminal_script() → opens terminal window
     │   └── Return: { ok: true, terminal: true, signal_file: "/tmp/..." }
     │
     └── Mode 3: Interactive terminal (default)
         Body: {} or { mode: "interactive" }
         │
         └── spawn_terminal("gh auth login")
             └── Return: { ok: true, terminal: true }

On successful token auth → HTTP 200
On terminal spawn       → HTTP 200 (but auth is async)
On error                → HTTP 400
```

### GitHub Device Flow Pipeline (PTY-Based)

```
POST /api/gh/auth/device  →  Start flow
     │
     ▼
gh_auth.gh_auth_device_start(root)
     │
     ├── Spawn PTY (pseudo-terminal):
     │   gh auth login -h github.com -p https -w
     │
     ├── Read PTY output (up to 15s):
     │   Watch for patterns:
     │   ├── "one-time code" → extract "XXXX-XXXX"
     │   └── "https://github.com/login/device" → extract URL
     │
     ├── Store session in _device_sessions dict:
     │   { pid, fd, user_code, verification_url, started_at }
     │
     └── Return:
         { ok: true, session_id: "uuid",
           user_code: "XXXX-XXXX",
           verification_url: "https://github.com/login/device" }

     ↓ User enters code in browser ↓

GET /api/gh/auth/device/poll?session=uuid  →  Check completion
     │
     ▼
gh_auth.gh_auth_device_poll("uuid", root)
     │
     ├── Drain PTY buffer (prevent blocking)
     │
     ├── Check if process exited:
     │   ├── Exit 0 → { complete: true, authenticated: true }
     │   │   ├── Invalidate cache: "github", "wiz:detect"
     │   │   └── Cleanup session
     │   │
     │   ├── Exit ≠ 0 → { complete: true, authenticated: false }
     │   └── Still running → { ok: true, complete: false }
     │
     └── Stale session cleanup (>10 min old)
```

### GitHub Terminal Auth Poll Pipeline

```
GET /api/gh/auth/terminal/poll  →  Poll signal file
     │
     ├── Read /tmp/.gh-auth-result (written by auto-drive script)
     │
     ├── Status: "running"    → { status: "running" }
     ├── Status: "code_ready" → { status: "code_ready", code: "XXXX-XXXX" }
     │   │
     │   └── Also runs: gh auth status
     │       ├── Exit 0 → auth succeeded! Update signal file → "success"
     │       │   Invalidate cache: "github", "wiz:detect"
     │       └── Exit ≠ 0 → return code_ready + debug info
     │
     ├── Status: "success"    → { status: "success" }
     │   Invalidate cache: "github", "wiz:detect"
     │
     └── Status: "failed"     → { status: "failed" }
```

### GitHub Observation Pipeline (Cached)

```
GET /api/integrations/gh/status  (cache key: "github")
     │
     ▼
git_ops.gh_status(root)
     │
     ├── shutil.which("gh") → available?
     ├── gh --version → version string
     ├── gh auth status → authenticated?
     ├── repo_slug(root) → "owner/repo"
     └── check_required_tools(["gh"]) → missing tools

GET /api/gh/pulls  (cache key: "gh-pulls")
     │
     ▼
git_ops.gh_pulls(root)
     │
     └── gh pr list --json number,title,author,createdAt,url,headRefName,state
         --limit 10 -R owner/repo

GET /api/gh/actions/runs  (cache key: "gh-runs")
     │
     ▼
git_ops.gh_actions_runs(root, n=10)
     │
     └── gh run list --json databaseId,name,status,conclusion,...
         --limit N -R owner/repo

GET /api/gh/actions/workflows  (cache key: "gh-workflows")
     │
     ▼
git_ops.gh_actions_workflows(root)
     │
     └── gh workflow list --json id,name,state -R owner/repo

POST /api/gh/actions/dispatch  { workflow: "ci.yml", ref: "main" }
     │
     ▼
git_ops.gh_actions_dispatch(root, "ci.yml", ref="main")
     │
     ├── ref not provided? → git rev-parse --abbrev-ref HEAD
     └── gh workflow run ci.yml --ref main -R owner/repo
```

### Remote Management Pipeline

```
GET /api/git/remotes
     │
     ▼
git_ops.git_remotes(root)
     │
     └── git remote -v
         Parse: "origin\thttps://github.com/user/repo.git (fetch)"
         → { name: "origin", fetch: "https://...", push: "https://..." }

POST /api/git/remote/add  { name: "upstream", url: "https://..." }
     │
     ▼
git_ops.git_remote_add(root, "upstream", "https://...")
     │
     ├── git remote add upstream https://...
     │   ├── Success → { ok: true }
     │   └── "already exists" → git remote set-url (idempotent)
     └── Return: { ok: true, message: "..." }

POST /api/git/remote/remove  { name: "upstream" }
POST /api/git/remote/rename  { old_name: "upstream", new_name: "backup" }
POST /api/git/remote/set-url { name: "origin", url: "git@github.com:..." }
```

### GitHub Repo Management Pipeline

```
POST /api/gh/repo/create
     Body: { name: "my-project", private: true, description: "...", add_remote: true }
     │
     ▼
git_ops.gh_repo_create(root, "my-project", private=True, ...)
     │
     ├── gh repo create my-project --private --description "..."
     │   --source=. --remote=origin --push
     │
     └── Return: { ok: true, name, private, url }

POST /api/gh/repo/visibility  { visibility: "public" }
     │
     ▼
git_ops.gh_repo_set_visibility(root, "public")
     │
     ├── repo_slug(root) → "owner/repo"
     └── gh repo edit owner/repo --visibility=public

POST /api/gh/repo/default-branch  { branch: "main" }
     │
     ▼
git_ops.gh_repo_set_default_branch(root, "main")
     │
     └── gh repo edit owner/repo --default-branch=main
```

---

## File Map

```
routes/integrations/
├── __init__.py     22 lines — blueprint definition + 6 sub-module imports
├── git.py          81 lines — 5 git operation endpoints
├── github.py       90 lines — 7 GitHub observation endpoints
├── gh_auth.py     172 lines — 6 GitHub auth endpoints
├── gh_repo.py      61 lines — 3 repo management endpoints
├── remotes.py      74 lines — 5 remote management endpoints
├── terminal.py     14 lines — 1 terminal status endpoint
└── README.md                — this file
```

Core business logic:
- `git/ops.py` (301 lines) — git subprocess runners + operations
- `git/gh_api.py` (230 lines) — GitHub CLI queries
- `git/gh_auth.py` (537 lines) — GitHub auth (3 modes + device flow)
- `git/gh_repo.py` (236 lines) — repo creation + remote management
- `terminal_ops.py` (351 lines) — terminal detection + spawn

Backward-compat shim: `git_ops.py` (48 lines, re-exports all).

---

## Per-File Documentation

### `__init__.py` — Blueprint Definition (22 lines)

```python
integrations_bp = Blueprint("integrations", __name__)

from . import git, github, gh_auth, gh_repo, remotes, terminal  # register all
```

### `git.py` — Git Operations (81 lines)

| Function | Method | Route | Auth | Tracked | Cached | What It Does |
|----------|--------|-------|------|---------|--------|-------------|
| `git_status()` | GET | `/git/status` | No | No | ✅ `"git"` | Branch, dirty files, ahead/behind |
| `git_log()` | GET | `/git/log` | No | No | No | Recent commit history |
| `git_commit()` | POST | `/git/commit` | No | ✅ `git:commit` | No | Stage + commit changes |
| `git_pull()` | POST | `/git/pull` | ✅ | ✅ `git:pull` | No | Pull from remote |
| `git_push()` | POST | `/git/push` | ✅ | ✅ `git:push` | No | Push to remote |

**Pull and push use `@requires_git_auth`** — if SSH key needs a
passphrase or HTTPS token is missing, the decorator returns 401
and publishes `auth:needed` on the EventBus to trigger the auth modal.

**Commit uses the `files` parameter for selective staging:**

```python
data = request.get_json(silent=True) or {}
message = data.get("message", "").strip()
files = data.get("files")  # None → stage all, list → selective
result = git_ops.git_commit(_project_root(), message, files=files)
```

### `github.py` — GitHub Observation (90 lines)

| Function | Method | Route | Cached | What It Does |
|----------|--------|-------|--------|-------------|
| `gh_status_extended()` | GET | `/integrations/gh/status` | ✅ `"github"` | Version, auth status, repo slug |
| `gh_pulls()` | GET | `/gh/pulls` | ✅ `"gh-pulls"` | Open pull requests |
| `gh_actions_runs()` | GET | `/gh/actions/runs` | ✅ `"gh-runs"` | Recent workflow runs |
| `gh_actions_dispatch()` | POST | `/gh/actions/dispatch` | No | Trigger a workflow |
| `gh_actions_workflows()` | GET | `/gh/actions/workflows` | ✅ `"gh-workflows"` | Available workflows |
| `gh_user()` | GET | `/gh/user` | No | Authenticated user info |
| `gh_repo_info()` | GET | `/gh/repo/info` | No | Repository details |

**Note the mixed route prefixes:** `/integrations/gh/status` vs
`/gh/pulls`. The `/integrations/` prefix was added for the detailed
status endpoint to avoid collision with simpler status checks. The
other routes use the shorter `/gh/` prefix.

**Actions dispatch requires explicit workflow name:**

```python
workflow = data.get("workflow", "")
if not workflow:
    return jsonify({"error": "Missing 'workflow' field"}), 400
```

### `gh_auth.py` — GitHub Authentication (172 lines)

| Function | Method | Route | Tracked | What It Does |
|----------|--------|-------|---------|-------------|
| `gh_auth_logout()` | POST | `/gh/auth/logout` | ✅ `setup:gh_logout` | Logout from gh CLI |
| `gh_auth_login()` | POST | `/gh/auth/login` | ✅ `setup:gh_login` | Authenticate (3 modes) |
| `gh_auth_token_route()` | GET | `/gh/auth/token` | No | Extract current token |
| `gh_auth_device_start_route()` | POST | `/gh/auth/device` | ✅ `setup:gh_device_flow` | Start device code flow |
| `gh_auth_device_poll_route()` | GET | `/gh/auth/device/poll` | No | Poll device flow |
| `gh_auth_terminal_poll_route()` | GET | `/gh/auth/terminal/poll` | No | Poll terminal auth script |

**Login cache invalidation — happens on three success paths:**

1. Token login success (immediate, in `gh_auth_login`)
2. Device flow poll success (async, in `gh_auth_device_poll_route`)
3. Terminal poll success (async, in `gh_auth_terminal_poll_route`)

All three invalidate both `"github"` and `"wiz:detect"` cache keys
to ensure the dashboard reflects the new auth state.

**Terminal poll live-checks gh auth status:**

When the signal file shows `code_ready`, the endpoint doesn't just
return it — it also runs `gh auth status` to detect if the user
already completed the browser auth but the script hasn't caught up:

```python
if data.get("status") == "code_ready":
    result = subprocess.run(["gh", "auth", "status"], ...)
    if result.returncode == 0:
        # Auth succeeded! Update signal file
        data = {"status": "success", "ts": data.get("ts", "")}
        signal_file.write_text(_json.dumps(data))
```

### `gh_repo.py` — GitHub Repo Management (61 lines)

| Function | Method | Route | Tracked | What It Does |
|----------|--------|-------|---------|-------------|
| `gh_repo_create()` | POST | `/gh/repo/create` | ✅ `setup:gh_repo` | Create new GitHub repo |
| `gh_repo_set_visibility()` | POST | `/gh/repo/visibility` | ✅ `setup:gh_visibility` | Change public/private |
| `gh_repo_set_default_branch()` | POST | `/gh/repo/default-branch` | ✅ `setup:gh_default_branch` | Change default branch |

**Repo creation with auto-remote:**

The create endpoint passes `--source=. --remote=origin --push` to
the `gh` CLI, meaning it sets the current directory as the source,
adds the new repo as `origin`, and pushes existing commits in one
atomic operation.

### `remotes.py` — Git Remote Management (74 lines)

| Function | Method | Route | Tracked | What It Does |
|----------|--------|-------|---------|-------------|
| `git_remotes()` | GET | `/git/remotes` | No | List all remotes |
| `git_remote_add()` | POST | `/git/remote/add` | ✅ `setup:git_remote` | Add remote (idempotent) |
| `git_remote_remove()` | POST | `/git/remote/remove` | ✅ `destroy:git_remote` | Remove remote |
| `git_remote_rename()` | POST | `/git/remote/rename` | ✅ `setup:git_remote_rename` | Rename remote |
| `git_remote_set_url()` | POST | `/git/remote/set-url` | ✅ `setup:git_remote_url` | Change remote URL |

**Idempotent remote add:**

```python
# Core service: if remote already exists, update URL instead of failing
r = run_git("remote", "add", name, url, cwd=project_root)
if "already exists" in err.lower():
    r2 = run_git("remote", "set-url", name, url, ...)
    return {"ok": True, "message": f"Remote '{name}' updated → {url}"}
```

**Note: `remove` is tracked as `destroy:git_remote`** — it's the
only destructive action in the domain, reflected in the tracker
category.

### `terminal.py` — Terminal Status (14 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `ops_terminal_status()` | GET | `/ops/terminal/status` | Terminal emulator availability |

**Lazy import — the only dependency loads at call time:**

```python
@integrations_bp.route("/ops/terminal/status")
def ops_terminal_status():
    from src.core.services.terminal_ops import terminal_status
    return jsonify(terminal_status())
```

The core service smoke-tests real terminal emulators (gnome-terminal,
xterm, kitty, x-terminal-emulator) and reports which are working,
broken, or installable via apt.

---

## Dependency Graph

```
__init__.py
└── Imports: git, github, gh_auth, gh_repo, remotes, terminal

git.py
├── git_ops           ← git_status, git_log, git_commit, git_pull, git_push (eager)
├── devops.cache      ← get_cached (eager)
├── run_tracker       ← @run_tracked (eager)
└── helpers           ← requires_git_auth, project_root (eager)

github.py
├── git_ops           ← gh_status, gh_pulls, gh_actions_*, gh_user, gh_repo_info (eager)
├── devops.cache      ← get_cached (eager)
├── run_tracker       ← @run_tracked (eager)
└── helpers           ← project_root (eager)

gh_auth.py
├── git_ops           ← gh_auth_login, gh_auth_logout, gh_auth_token,
│                       gh_auth_device_start, gh_auth_device_poll (eager)
├── run_tracker       ← @run_tracked (eager)
├── devops.cache      ← invalidate (lazy, on success)
├── subprocess        ← direct use in terminal_poll (live gh auth status check)
└── helpers           ← project_root (eager)

gh_repo.py
├── git_ops           ← gh_repo_create, gh_repo_set_visibility,
│                       gh_repo_set_default_branch (eager)
├── run_tracker       ← @run_tracked (eager)
└── helpers           ← project_root (eager)

remotes.py
├── git_ops           ← git_remotes, git_remote_add/remove/rename/set_url (eager)
├── run_tracker       ← @run_tracked (eager)
└── helpers           ← project_root (eager)

terminal.py
└── terminal_ops      ← terminal_status (lazy, inside handler)
```

**Core service structure:**

```
git_ops.py (48 lines) — backward compatibility shim
└── Re-exports everything from:
    ├── git/ops.py (301 lines)
    │   ├── run_git()        — subprocess runner for git
    │   ├── run_gh()         — subprocess runner for gh CLI
    │   ├── repo_slug()      — extract owner/repo from remote
    │   ├── git_status()     — branch, dirty files, ahead/behind
    │   ├── git_log()        — recent commits (--pretty=format)
    │   ├── git_commit()     — stage + commit (selective or all)
    │   ├── git_pull()       — pull (optional rebase)
    │   └── git_push()       — push (optional force-with-lease)
    │
    ├── git/gh_api.py (230 lines)
    │   ├── gh_status()            — version + auth + repo slug
    │   ├── gh_pulls()             — open PRs (gh pr list --json)
    │   ├── gh_actions_runs()      — workflow runs (gh run list --json)
    │   ├── gh_actions_dispatch()  — trigger workflow (gh workflow run)
    │   ├── gh_actions_workflows() — list workflows (gh workflow list --json)
    │   ├── gh_user()              — authenticated user (gh api user)
    │   └── gh_repo_info()         — repo details (gh repo view --json)
    │
    ├── git/gh_auth.py (537 lines)
    │   ├── gh_auth_logout()       — gh auth logout
    │   ├── gh_auth_login()        — 3-mode login (token/interactive/auto-drive)
    │   ├── _build_auto_drive_script() — signal-file bash script
    │   ├── gh_auth_token()        — extract token from gh CLI
    │   ├── gh_auth_device_start() — PTY-based device flow
    │   ├── gh_auth_device_poll()  — poll PTY for completion
    │   └── _cleanup_stale_sessions() — >10min session cleanup
    │
    └── git/gh_repo.py (236 lines)
        ├── gh_repo_create()           — create + auto-remote
        ├── gh_repo_set_visibility()   — public/private toggle
        ├── gh_repo_set_default_branch() — change default branch
        ├── git_remote_remove()        — idempotent remove
        ├── git_remotes()              — list with fetch/push URLs
        ├── git_remote_add()           — add (or update if exists)
        ├── git_remote_rename()        — rename remote
        └── git_remote_set_url()       — change URL
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `integrations_bp`, registers at `/api` prefix |
| Git panel | `scripts/integrations/_git.html` | `/git/status`, `/git/log`, `/git/commit`, `/git/pull`, `/git/push` |
| GitHub panel | `scripts/integrations/_github.html` | `/integrations/gh/status`, `/gh/pulls`, `/gh/actions/*` |
| CICD panel | `scripts/integrations/_cicd.html` | `/gh/actions/runs`, `/gh/actions/workflows` |
| GH auth panel | `scripts/auth/_gh_auth.html` | `/gh/auth/login`, `/gh/auth/logout`, `/gh/auth/device` |
| Auth modal | `scripts/globals/_auth_modal.html` | `/gh/auth/device/poll`, `/gh/auth/terminal/poll` |
| Ops modal | `scripts/globals/_ops_modal.html` | `/ops/terminal/status` |
| Git setup | `scripts/integrations/setup/_git.html` | `/git/remotes`, `/git/remote/*` |
| GH setup | `scripts/integrations/setup/_github.html` | `/gh/repo/create`, `/gh/repo/visibility`, `/gh/repo/default-branch` |
| Wizard | `scripts/wizard/_integrations.html` | `/integrations/gh/status`, `/gh/auth/login` |
| Wizard steps | `scripts/wizard/_steps.html` | `/gh/auth/device`, `/gh/auth/device/poll` |
| Secrets init | `scripts/secrets/_init.html` | `/integrations/gh/status` (check GH availability) |
| Secrets render | `scripts/secrets/_render.html` | `/gh/user` (display authenticated user) |
| Env card | `scripts/devops/_env.html` | `/integrations/gh/status` (GH token availability) |

---

## Service Delegation Map

```
Route Handler                 →   Core Service Function
──────────────────────────────────────────────────────────────────────────
git_status()                  →   git/ops.git_status(root)
git_log()                     →   git/ops.git_log(root, n=N)
git_commit()                  →   git/ops.git_commit(root, msg, files=...)
git_pull()                    →   git/ops.git_pull(root, rebase=bool)
git_push()                    →   git/ops.git_push(root, force=bool)

gh_status_extended()          →   git/gh_api.gh_status(root)
gh_pulls()                    →   git/gh_api.gh_pulls(root)
gh_actions_runs()             →   git/gh_api.gh_actions_runs(root, n=N)
gh_actions_dispatch()         →   git/gh_api.gh_actions_dispatch(root, workflow, ref)
gh_actions_workflows()        →   git/gh_api.gh_actions_workflows(root)
gh_user()                     →   git/gh_api.gh_user(root)
gh_repo_info()                →   git/gh_api.gh_repo_info(root)

gh_auth_logout()              →   git/gh_auth.gh_auth_logout(root)
gh_auth_login()               →   git/gh_auth.gh_auth_login(root, token, auto_drive)
gh_auth_token_route()         →   git/gh_auth.gh_auth_token(root)
gh_auth_device_start_route()  →   git/gh_auth.gh_auth_device_start(root)
gh_auth_device_poll_route()   →   git/gh_auth.gh_auth_device_poll(session_id, root)
gh_auth_terminal_poll_route() →   (reads signal file directly + subprocess)

gh_repo_create()              →   git/gh_repo.gh_repo_create(root, name, ...)
gh_repo_set_visibility()      →   git/gh_repo.gh_repo_set_visibility(root, visibility)
gh_repo_set_default_branch()  →   git/gh_repo.gh_repo_set_default_branch(root, branch)

git_remotes()                 →   git/gh_repo.git_remotes(root)
git_remote_add()              →   git/gh_repo.git_remote_add(root, name, url)
git_remote_remove()           →   git/gh_repo.git_remote_remove(root, name)
git_remote_rename()           →   git/gh_repo.git_remote_rename(root, old, new)
git_remote_set_url()          →   git/gh_repo.git_remote_set_url(root, name, url)

ops_terminal_status()         →   terminal_ops.terminal_status()
```

---

## Data Shapes

### `GET /api/git/status` response

```json
{
    "branch": "main",
    "commit_hash": "a1b2c3d",
    "upstream": "origin/main",
    "ahead": 2,
    "behind": 0,
    "dirty_count": 3,
    "untracked_count": 1,
    "staged": [
        { "path": "src/foo.py", "status": "modified" }
    ],
    "unstaged": [
        { "path": "src/bar.py", "status": "modified" },
        { "path": "src/baz.py", "status": "deleted" }
    ],
    "untracked": ["new_file.txt"],
    "stash_count": 1,
    "has_remote": true
}
```

### `GET /api/git/log?n=3` response

```json
{
    "ok": true,
    "commits": [
        {
            "hash": "a1b2c3d",
            "short_hash": "a1b2c3d",
            "author": "user",
            "email": "user@example.com",
            "date": "2026-03-02T15:30:00",
            "message": "feat: add new feature"
        }
    ]
}
```

### `POST /api/git/commit` request + response

```json
// Request:
{ "message": "feat: add feature", "files": ["src/foo.py"] }

// Response (success):
{ "ok": true, "hash": "a1b2c3d", "message": "feat: add feature" }

// Response (error):
{ "error": "nothing to commit, working tree clean" }
```

### `POST /api/git/pull` request + response

```json
// Request:
{ "rebase": true }

// Response:
{ "ok": true }
```

### `POST /api/git/push` request + response

```json
// Request:
{ "force": true }

// Response:
{ "ok": true }
```

### `GET /api/integrations/gh/status` response

```json
{
    "available": true,
    "version": "gh version 2.45.0 (2026-01-15)",
    "authenticated": true,
    "auth_detail": "Logged in to github.com account user (keyring)\n...",
    "repo": "user/my-project",
    "missing_tools": []
}
```

### `GET /api/integrations/gh/status` response (gh not installed)

```json
{
    "available": false,
    "error": "gh CLI not installed",
    "missing_tools": [
        { "name": "gh", "purpose": "GitHub CLI", "install": "apt install gh" }
    ]
}
```

### `GET /api/gh/pulls` response

```json
{
    "available": true,
    "pulls": [
        {
            "number": 42,
            "title": "Add documentation",
            "author": { "login": "contributor" },
            "createdAt": "2026-03-01T10:00:00Z",
            "url": "https://github.com/user/repo/pull/42",
            "headRefName": "docs-update",
            "state": "OPEN"
        }
    ]
}
```

### `GET /api/gh/actions/runs?n=5` response

```json
{
    "available": true,
    "runs": [
        {
            "databaseId": 12345,
            "name": "CI",
            "status": "completed",
            "conclusion": "success",
            "createdAt": "2026-03-02T14:00:00Z",
            "updatedAt": "2026-03-02T14:05:00Z",
            "url": "https://github.com/user/repo/actions/runs/12345",
            "headBranch": "main",
            "event": "push"
        }
    ]
}
```

### `POST /api/gh/actions/dispatch` request + response

```json
// Request:
{ "workflow": "ci.yml", "ref": "main" }

// Response:
{ "ok": true, "workflow": "ci.yml", "ref": "main" }
```

### `GET /api/gh/user` response

```json
{
    "available": true,
    "login": "jfortin",
    "name": "J Fortin",
    "avatar_url": "https://avatars.githubusercontent.com/u/12345?v=4",
    "html_url": "https://github.com/jfortin"
}
```

### `GET /api/gh/repo/info` response

```json
{
    "available": true,
    "slug": "user/my-project",
    "name": "my-project",
    "owner": "user",
    "visibility": "PRIVATE",
    "is_private": true,
    "is_fork": false,
    "description": "A DevOps control plane",
    "default_branch": "main",
    "url": "https://github.com/user/my-project",
    "ssh_url": "git@github.com:user/my-project.git",
    "homepage_url": ""
}
```

### `POST /api/gh/auth/login` — token mode response

```json
{ "ok": true, "authenticated": true }
```

### `POST /api/gh/auth/login` — auto-drive response

```json
{
    "ok": true,
    "terminal": true,
    "signal_file": "/tmp/.gh-auth-result"
}
```

### `POST /api/gh/auth/device` response

```json
{
    "ok": true,
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "user_code": "ABCD-1234",
    "verification_url": "https://github.com/login/device"
}
```

### `GET /api/gh/auth/device/poll?session=...` — waiting response

```json
{ "ok": true, "complete": false }
```

### `GET /api/gh/auth/device/poll?session=...` — complete response

```json
{ "complete": true, "authenticated": true }
```

### `GET /api/gh/auth/terminal/poll` — code ready response

```json
{
    "status": "code_ready",
    "code": "ABCD-1234",
    "url": "https://github.com/login/device",
    "_debug_gh_rc": -999,
    "_debug_gh_err": ""
}
```

### `POST /api/gh/repo/create` request + response

```json
// Request:
{ "name": "my-new-repo", "private": true, "description": "My project", "add_remote": true }

// Response:
{
    "ok": true,
    "message": "Repository created: my-new-repo",
    "name": "my-new-repo",
    "private": true,
    "url": "https://github.com/user/my-new-repo"
}
```

### `GET /api/git/remotes` response

```json
{
    "available": true,
    "remotes": [
        {
            "name": "origin",
            "fetch": "https://github.com/user/repo.git",
            "push": "https://github.com/user/repo.git"
        },
        {
            "name": "upstream",
            "fetch": "https://github.com/original/repo.git",
            "push": "https://github.com/original/repo.git"
        }
    ]
}
```

### `GET /api/ops/terminal/status` response

```json
{
    "has_working": true,
    "working": [
        { "name": "gnome-terminal", "label": "GNOME Terminal" }
    ],
    "broken": [
        { "name": "xterm", "label": "xterm", "reason": "Failed smoke test" }
    ],
    "installable": [
        { "name": "kitty", "label": "Kitty", "description": "Modern GPU-accelerated terminal", "apt_package": "kitty" }
    ]
}
```

---

## Advanced Feature Showcase

### 1. Three-Mode GitHub Authentication

The login endpoint supports three distinct auth flows:

```python
# Mode 1: Token — non-interactive, for web UI token paste
{ "token": "ghp_..." }
→ gh auth login --with-token (stdin: token)

# Mode 2: Auto-drive — spawns terminal with signal-file protocol
{ "auto_drive": true }
→ builds bash script → spawn_terminal_script()
→ signal file read by /gh/auth/terminal/poll

# Mode 3: Default — spawns interactive terminal
{} or { "mode": "interactive" }
→ spawn_terminal("gh auth login")
```

### 2. PTY-Based Device Flow

The device flow uses a real pseudo-terminal to capture the
one-time code from `gh auth login -w`:

```python
# Core service spawns gh inside a PTY
pid, fd = pty.fork()
if pid == 0:  # child
    os.execvp("gh", ["gh", "auth", "login", "-h", "github.com", "-p", "https", "-w"])

# Parent reads PTY output until code appears
while True:
    data = os.read(fd, 1024)
    if "one-time code" in text:
        code = extract_code(text)
        break
```

This avoids requiring a browser redirect — the user gets the code
in the web UI and enters it at github.com/login/device.

### 3. Triple Cache Invalidation on Auth Success

All three auth flow endpoints invalidate the same two cache keys:

```python
devops_cache.invalidate(root, "github")    # refresh GH status card
devops_cache.invalidate(root, "wiz:detect")  # refresh wizard detection
```

This ensures the dashboard immediately reflects the new auth state
regardless of which flow completed first.

### 4. Force-with-Lease for Safety

Push uses `--force-with-lease` instead of `--force`:

```python
# Core service: force=True → --force-with-lease (not --force)
args = ["push"]
if force:
    args.append("--force-with-lease")
```

This is safer than `--force` because it only overwrites the remote
if the local tracking ref matches — preventing accidental history
rewrite when someone else has pushed.

### 5. Idempotent Remote Add

Adding a remote that already exists updates the URL instead of failing:

```python
r = run_git("remote", "add", name, url, ...)
if "already exists" in err.lower():
    run_git("remote", "set-url", name, url, ...)
    return {"ok": True, "message": f"Remote '{name}' updated → {url}"}
```

### 6. Terminal Smoke Testing

The terminal status endpoint doesn't just check `shutil.which()` —
it actually spawns the terminal with a no-op command:

```python
# Run: gnome-terminal -- bash -c "exit 0"
# Wait 2 seconds
# Check: did the process crash? → broken
# Check: did it survive? → working
```

This catches cases where a terminal binary exists but is broken
(missing display server, incompatible version, etc.).

### 7. Signal File Protocol

The auto-drive auth flow uses a JSON signal file to bridge between
a background bash script and the web UI's polling endpoint:

```
Script writes:  { "status": "running" }        → browser shows "Authenticating..."
Script writes:  { "status": "code_ready",
                  "code": "ABCD-1234" }         → browser shows code
Poll detects:   gh auth status → exit 0         → browser shows "Success!"
Script writes:  { "status": "success" }         → browser confirms
```

### 8. Repo Slug Extraction

All GitHub API calls first extract the `owner/repo` slug from
the git remote:

```python
def repo_slug(project_root):
    url = run_git("remote", "get-url", "origin", ...)
    # "https://github.com/user/repo.git" → "user/repo"
    # "git@github.com:user/repo.git"     → "user/repo"
```

If no slug can be extracted, endpoints return
`{ "available": false, "error": "No GitHub remote configured" }`.

---

## Design Decisions

### Why all git sub-domains share one blueprint

All are "integrations" — connections between the local project and
external services (git remote, GitHub API, terminal emulators).
Splitting into separate blueprints would fragment the URL namespace
(`/api/git/`, `/api/gh/`, `/api/ops/`) without adding routing benefit.
The single blueprint keeps registration simple.

### Why pull/push require auth but commit doesn't

`git commit` is a local operation — no network call, no credentials
needed. `git pull` and `git push` contact the remote, requiring
valid SSH or HTTPS credentials. The `@requires_git_auth` decorator
gates only the network operations.

### Why GitHub observation endpoints are cached

Pull requests, action runs, and workflows don't change on every
request. Caching with the devops cache (bust-on-demand) reduces
GitHub API rate limit consumption. The `?bust=1` parameter allows
forced refresh when the user explicitly requests it.

### Why device flow uses PTY instead of shell

`gh auth login -w` is designed for interactive terminals — it writes
the device code and URL to stdout, then waits for user confirmation.
A PTY (pseudo-terminal) lets the web server capture this output
programmatically while the `gh` process believes it's running in an
interactive terminal.

### Why the terminal poll does a live gh auth check

The auto-drive bash script runs asynchronously in a terminal window.
There's a race condition: the user might complete the browser auth
before the script detects it. The live `gh auth status` check in
the polling endpoint catches this race and updates the signal file.

### Why remote add is idempotent

During initial project setup, the wizard may try to add `origin`
when it already exists (common with `git clone`). Making `add`
idempotent (update URL if exists) prevents confusing errors and
keeps the setup wizard flow smooth.

---

## Coverage Summary

| Capability | Endpoint | Method | Auth | Tracked | Cached |
|-----------|----------|--------|------|---------|--------|
| Git status | `/git/status` | GET | No | No | ✅ `"git"` |
| Git log | `/git/log` | GET | No | No | No |
| Git commit | `/git/commit` | POST | No | ✅ `git:commit` | No |
| Git pull | `/git/pull` | POST | ✅ | ✅ `git:pull` | No |
| Git push | `/git/push` | POST | ✅ | ✅ `git:push` | No |
| GH status | `/integrations/gh/status` | GET | No | No | ✅ `"github"` |
| GH pulls | `/gh/pulls` | GET | No | No | ✅ `"gh-pulls"` |
| GH action runs | `/gh/actions/runs` | GET | No | No | ✅ `"gh-runs"` |
| GH dispatch | `/gh/actions/dispatch` | POST | No | ✅ `ci:gh_dispatch` | No |
| GH workflows | `/gh/actions/workflows` | GET | No | No | ✅ `"gh-workflows"` |
| GH user | `/gh/user` | GET | No | No | No |
| GH repo info | `/gh/repo/info` | GET | No | No | No |
| GH logout | `/gh/auth/logout` | POST | No | ✅ `setup:gh_logout` | No |
| GH login | `/gh/auth/login` | POST | No | ✅ `setup:gh_login` | No |
| GH token | `/gh/auth/token` | GET | No | No | No |
| GH device start | `/gh/auth/device` | POST | No | ✅ `setup:gh_device_flow` | No |
| GH device poll | `/gh/auth/device/poll` | GET | No | No | No |
| GH terminal poll | `/gh/auth/terminal/poll` | GET | No | No | No |
| Repo create | `/gh/repo/create` | POST | No | ✅ `setup:gh_repo` | No |
| Repo visibility | `/gh/repo/visibility` | POST | No | ✅ `setup:gh_visibility` | No |
| Repo default branch | `/gh/repo/default-branch` | POST | No | ✅ `setup:gh_default_branch` | No |
| List remotes | `/git/remotes` | GET | No | No | No |
| Add remote | `/git/remote/add` | POST | No | ✅ `setup:git_remote` | No |
| Remove remote | `/git/remote/remove` | POST | No | ✅ `destroy:git_remote` | No |
| Rename remote | `/git/remote/rename` | POST | No | ✅ `setup:git_remote_rename` | No |
| Set remote URL | `/git/remote/set-url` | POST | No | ✅ `setup:git_remote_url` | No |
| Terminal status | `/ops/terminal/status` | GET | No | No | No |
