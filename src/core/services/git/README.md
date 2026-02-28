# Git Domain

> The interface between the control plane and Git/GitHub.
> Everything that touches `git` or `gh` CLI goes through here —
> auth detection, repository operations, GitHub API queries,
> device-flow authentication, and remote management.

---

## Why This Exists

Before this domain folder, git operations were spread across three
flat files in `core/services/`: `git_ops.py` (330 lines), `git_auth.py`
(511 lines), and `git_gh_ops.py` (952 lines). The last one was a
single-responsibility violation — it mixed GitHub API queries, multiple
authentication strategies (token, terminal, PTY device-flow), and
repository/remote management in one file.

The split follows a natural boundary: **what kind of thing are you doing?**

- Talking to local git? → `ops.py`
- Managing SSH/HTTPS auth state? → `auth.py`
- Querying GitHub's API? → `gh_api.py`
- Logging into GitHub? → `gh_auth.py`
- Creating repos or managing remotes? → `gh_repo.py`

---

## How It Works

### The Two CLIs

This domain wraps two distinct command-line tools:

1. **`git`** — local repository operations. Always available if the
   project has a `.git/` directory. No network access needed for most
   operations (status, log, commit).

2. **`gh`** — GitHub's CLI. Optional. Requires authentication. Used
   for PRs, Actions, repo creation, and visibility management.

Both are invoked through the low-level runners in `ops.py`:
`run_git()` and `run_gh()`. These are the **only** place in the
codebase where `subprocess.run(["git", ...])` or
`subprocess.run(["gh", ...])` should appear for git operations.

### Authentication Flow

Auth is the most nuanced part. The control plane needs git network
access (push, pull, sync) but runs as a web server — there's no
interactive terminal for passphrase prompts.

```
User opens admin panel
       │
       ▼
  check_auth()  ← instant, no network call for SSH
       │
       ├── SSH remote + agent has keys  → ok: true
       ├── SSH remote + no agent keys   → needs: "ssh_passphrase"
       ├── HTTPS remote + ls-remote ok  → ok: true
       └── HTTPS remote + 401/403      → needs: "https_credentials"
```

When `needs` is set, the frontend shows an unlock prompt. The user
provides their passphrase (SSH) or token (HTTPS), which gets passed
to `add_ssh_key()` or `add_https_credentials()`. After that,
`git_env()` returns the right environment variables for all
subsequent subprocess calls.

**Key design decision:** Auth state is cached at module level for the
server's lifetime. Once the SSH agent has the key, it stays loaded.
This means the user unlocks once per server start, not once per
operation.

### GitHub Authentication — Three Strategies

GitHub auth (`gh_auth.py`) offers three modes because different
deployment scenarios need different approaches:

1. **Token mode** — Non-interactive. The user pastes a GitHub PAT,
   it gets piped to `gh auth login --with-token`. Works from the
   web UI without any terminal.

2. **Interactive terminal mode** — Spawns a terminal window running
   `gh auth login`. The user answers prompts manually. Works when
   the machine has a display.

3. **Device flow mode** — The sophisticated one. Spawns `gh` in a
   PTY, auto-answers the interactive prompts, extracts the one-time
   code and verification URL, and returns them to the web UI. The
   user opens the GitHub URL in their browser, enters the code, and
   the PTY process detects completion. No terminal window needed.

---

## File Map

```
git/
├── __init__.py     Public API re-exports
├── ops.py          Low-level runners + porcelain git operations
├── auth.py         SSH/HTTPS auth detection and agent management
├── gh_api.py       GitHub API queries (status, PRs, Actions, user, repo info)
├── gh_auth.py      GitHub CLI authentication (token, terminal, device flow)
└── gh_repo.py      GitHub repo creation/visibility + git remote management
```

### `ops.py` — The Foundation (300 lines)

Everything starts here. Two runners, one slug helper, five operations.

| Function | What It Does |
|----------|-------------|
| `run_git()` | Wraps `subprocess.run(["git", ...])` with timeout and capture |
| `run_gh()` | Wraps `subprocess.run(["gh", ...])` with graceful `FileNotFoundError` handling |
| `repo_slug()` | Extracts `owner/repo` from the origin remote URL (SSH or HTTPS) |
| `git_status()` | Branch, dirty state, staged/modified/untracked counts, ahead/behind, last commit |
| `git_log()` | Recent commit history (capped at 50) |
| `git_commit()` | Stage + commit with message |
| `git_pull()` | Pull with optional rebase |
| `git_push()` | Push with auto `--set-upstream` on first push |

### `auth.py` — Auth State Machine (510 lines)

Manages the SSH agent lifecycle and HTTPS credential storage.
Module-level state (`_ssh_agent_env`, `_auth_ok`) persists for the
server's lifetime.

| Function | What It Does |
|----------|-------------|
| `check_auth()` | Non-destructive auth probe — returns what the user needs to provide |
| `add_ssh_key()` | Starts ssh-agent, adds key via `SSH_ASKPASS` (no terminal needed) |
| `add_https_credentials()` | Stores token via `git credential approve` |
| `git_env()` | Returns `os.environ` merged with ssh-agent vars — pass to all subprocess calls |
| `is_auth_ok()` | Quick boolean: has auth been verified this session? |

### `gh_api.py` — GitHub Queries (229 lines)

Read-only queries against the GitHub API via `gh`. All return dicts
with an `available` boolean, so the UI can degrade gracefully when
gh isn't installed or auth is missing.

| Function | What It Does |
|----------|-------------|
| `gh_status()` | Version, auth status, repo slug |
| `gh_pulls()` | Open PRs (number, title, author, branch, URL) |
| `gh_actions_runs()` | Recent workflow runs (status, conclusion, branch) |
| `gh_actions_dispatch()` | Trigger a workflow run |
| `gh_actions_workflows()` | List available workflows |
| `gh_user()` | Authenticated user (login, name, avatar) |
| `gh_repo_info()` | Repo details (visibility, description, default branch, fork status) |

### `gh_auth.py` — GitHub Login (536 lines)

The complexity here comes from the device flow — it's a PTY-based
state machine that answers interactive prompts, parses ANSI-stripped
output, and manages background processes.

| Function | What It Does |
|----------|-------------|
| `gh_auth_login()` | Three-mode dispatcher (token / interactive / auto-drive) |
| `gh_auth_logout()` | Logout with auto-confirm |
| `gh_auth_token()` | Extract the current auth token from gh |
| `gh_auth_device_start()` | Start PTY device flow, return one-time code + URL |
| `gh_auth_device_poll()` | Check if user completed browser auth (drains PTY buffer) |

### `gh_repo.py` — Repo & Remote Management (235 lines)

GitHub repo lifecycle and local git remote CRUD. Straightforward
wrappers around `gh repo` and `git remote` commands.

| Function | What It Does |
|----------|-------------|
| `gh_repo_create()` | Create repo on GitHub + set as origin |
| `gh_repo_set_visibility()` | Toggle public/private |
| `gh_repo_set_default_branch()` | Change default branch on GitHub |
| `git_remotes()` | List all remotes with fetch/push URLs |
| `git_remote_add()` | Add remote (idempotent — updates if exists) |
| `git_remote_remove()` | Remove remote (idempotent — no-op if absent) |
| `git_remote_rename()` | Rename a remote |
| `git_remote_set_url()` | Change a remote's URL |

---

## Dependency Graph

```
ops.py  ←── gh_api.py     uses run_git, run_gh, repo_slug
   ↑    ←── gh_auth.py    uses run_gh
   ↑    ←── gh_repo.py    uses run_git, run_gh, repo_slug
   ↑
auth.py      standalone — uses subprocess directly, no ops.py dependency
```

`ops.py` is the foundation that all `gh_*.py` files import from.
`auth.py` is fully independent — it manages SSH/HTTPS auth concerns
that are orthogonal to the git command runners.

---

## Backward Compatibility

The old import paths still work via thin shim files at the original
locations. These exist so we don't break every consumer at once:

- `services/git_ops.py` → re-exports from all `git/` submodules
- `services/git_auth.py` → re-exports from `git/auth.py`
- `services/git_gh_ops.py` → re-exports from `git/gh_api.py` + `git/gh_auth.py` + `git/gh_repo.py`

New code should import from `src.core.services.git` or its submodules:

```python
# From the package (most convenient)
from src.core.services.git import git_status, check_auth, gh_pulls

# From a specific submodule (when you want to be explicit)
from src.core.services.git.ops import run_git
from src.core.services.git.auth import git_env
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| **Routes** | `routes_integrations.py` | `git_ops` module (status, PRs, actions) |
| **Routes** | `routes_git_auth.py` | `check_auth`, `add_ssh_key`, `add_https_credentials`, `is_auth_ok` |
| **Routes** | `routes_devops.py` | `git_ops` module |
| **Routes** | `routes_trace.py`, `routes_chat.py` | `is_auth_ok` |
| **CLI** | `ui/cli/git.py` | All porcelain ops + GitHub queries |
| **Services** | `wizard_ops.py` | `gh_status`, `gh_user`, `gh_repo_info`, `git_remotes` |
| **Services** | `metrics_ops.py` | `git_status` |
| **Services** | `ledger/worktree.py` | `git_env`, `is_auth_ok` |
