# Git Domain

> **6 files · 1,874 lines · The interface between the control plane and Git/GitHub.**
>
> Everything that touches `git` or `gh` CLI goes through here —
> auth detection, repository operations, GitHub API queries,
> device-flow authentication, and remote management.

---

## How It Works

The Git domain is split across 6 files, each handling a distinct concern:

```
┌──────────────────────────────────────────────────────────────┐
│                       git/                                     │
│                                                                │
│  ops.py ─── low-level runners + porcelain git operations       │
│    │                                                           │
│    ├── run_git(*args, cwd=)  ← every module uses this          │
│    ├── run_gh(*args, cwd=)   ← every gh_*.py module uses this  │
│    ├── repo_slug(root)       ← owner/repo from remote URL      │
│    │                                                           │
│    ├── git_status()          ← branch, dirty, ahead/behind     │
│    ├── git_log()             ← recent commits                  │
│    ├── git_commit()          ← stage + commit                  │
│    ├── git_pull()            ← pull from remote                │
│    └── git_push()            ← push to remote (auto-upstream)  │
│                                                                │
│  auth.py ─── SSH + HTTPS credential management                 │
│    ├── check_auth()          ← "can we talk to the remote?"    │
│    ├── add_ssh_key()         ← unlock SSH key with passphrase  │
│    ├── add_https_credentials()  ← store PAT/token              │
│    ├── git_env()             ← env dict with ssh-agent vars    │
│    └── is_auth_ok()          ← session auth state              │
│                                                                │
│  gh_api.py ── GitHub API queries via gh CLI                     │
│    ├── gh_status()           ← version, auth, repo slug        │
│    ├── gh_pulls()            ← open pull requests              │
│    ├── gh_actions_runs()     ← workflow run history            │
│    ├── gh_actions_dispatch() ← trigger workflow                │
│    ├── gh_actions_workflows()← list available workflows        │
│    ├── gh_user()             ← authenticated user info         │
│    └── gh_repo_info()        ← repo details (visibility, etc)  │
│                                                                │
│  gh_auth.py ── GitHub CLI authentication                       │
│    ├── gh_auth_login()       ← token / interactive / device    │
│    ├── gh_auth_logout()      ← deauth                          │
│    ├── gh_auth_token()       ← extract current token           │
│    ├── gh_auth_device_start()← PTY device flow start           │
│    └── gh_auth_device_poll() ← poll for device flow completion │
│                                                                │
│  gh_repo.py ── GitHub repo + remote management                 │
│    ├── gh_repo_create()      ← create repo + add remote        │
│    ├── gh_repo_set_visibility()  ← public/private toggle       │
│    ├── gh_repo_set_default_branch()  ← change default branch   │
│    ├── git_remotes()         ← list all remotes                │
│    ├── git_remote_add()      ← add/update remote (idempotent)  │
│    ├── git_remote_remove()   ← remove remote                   │
│    ├── git_remote_rename()   ← rename remote                   │
│    └── git_remote_set_url()  ← change remote URL               │
└──────────────────────────────────────────────────────────────┘
```

---

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

#### SSH Auth State Machine

```
           ┌───────────────────┐
           │   INITIAL          │
           │  (no testing yet)  │
           └────────┬──────────┘
                    │  check_auth()
                    ▼
        ┌───────────────────────┐
        │  DETECT REMOTE TYPE   │
        │  git remote get-url   │
        └───────┬───────┬───────┘
                │       │
           SSH  │       │  HTTPS
                ▼       ▼
    ┌──────────────┐  ┌──────────────┐
    │ CHECK AGENT   │  │ LS-REMOTE    │
    │ ssh-add -l    │  │ git ls-remote│
    │ (local only)  │  │ (network)    │
    └───┬──────┬───┘  └──┬──────┬───┘
        │      │          │      │
     keys?  no keys?   ok?   401/403?
        │      │          │      │
        ▼      ▼          ▼      ▼
   ┌────────┐ ┌────────┐ ┌────────┐ ┌────────────────┐
   │ AUTH OK │ │ NEEDS  │ │ AUTH OK│ │ NEEDS           │
   │         │ │ SSH    │ │        │ │ HTTPS           │
   │         │ │ PASS   │ │        │ │ CREDENTIALS     │
   └─────────┘ └───┬───┘ └────────┘ └────────┬───────┘
                    │                          │
                    ▼                          ▼
            add_ssh_key(pass)          add_https_credentials(token)
                    │                          │
                    ▼                          ▼
            ┌────────────┐             ┌────────────┐
            │ Start agent │             │ git cred   │
            │ ssh-add key │             │ approve    │
            └──────┬─────┘             └──────┬─────┘
                   │                          │
                   └────────────┬─────────────┘
                                ▼
                         ┌────────────┐
                         │  AUTH OK    │
                         │ (session)   │
                         └────────────┘
```

#### SSH Agent Management

When the user provides a passphrase:

1. **Check inherited agent** — if `SSH_AUTH_SOCK` is set and `ssh-add -l`
   shows keys, use it as-is.
2. **Start managed agent** — spawn `ssh-agent -s`, parse `SSH_AUTH_SOCK`
   and `SSH_AGENT_PID` from output.
3. **Add key** — use `SSH_ASKPASS` environment variable to pipe the
   passphrase non-interactively to `ssh-add`.
4. **Export env** — `git_env()` returns the combined environment so all
   subsequent `run_git()` calls inherit the agent.

**The ASKPASS trick:**

```bash
# SSH_ASKPASS requires DISPLAY to be set
# and must point to a script that echoes the passphrase
cat > /tmp/askpass.sh << 'EOF'
#!/bin/sh
echo "$SSH_PASSPHRASE"
EOF
chmod +x /tmp/askpass.sh

# Then
DISPLAY=:0 SSH_ASKPASS=/tmp/askpass.sh SSH_PASSPHRASE=<pass> ssh-add <key>
```

This is the only way to provide a passphrase to `ssh-add` without
an interactive terminal. The temp file is cleaned up after use.

#### HTTPS Credential Flow

For HTTPS remotes, credentials are provided via `git credential approve`:

```
echo "protocol=https\nhost=github.com\nusername=x\npassword=<token>"
  | git credential approve
```

This stores the token in whatever credential helper is configured
(`store`, `cache`, `osxkeychain`, etc.). The control plane does NOT
set the credential helper — it uses whatever the user has configured.

### GitHub CLI Device Flow Authentication

`gh_auth.py` handles three login modes:

| Mode | Trigger | How It Works |
|------|---------|-------------|
| **Token** | `token="ghp_…"` | Pipes to `gh auth login --with-token` — instant |
| **Interactive** | `auto_drive=True` | Spawns terminal with bash script driving `gh auth login` |
| **Device flow** | `gh_auth_device_start()` | PTY-based async flow — returns code + URL |

#### Device Flow PTY Architecture

The device flow is the most complex — it uses a pseudo-terminal to
capture `gh auth login` output without a real terminal:

```
Web UI ──→ POST /api/git/auth/device-start
                │
                ▼
           gh_auth_device_start()
                │
                ├── 1. Spawn PTY: openpty() + fork()
                │      └── child: exec("gh auth login -h github.com -p https -w")
                │
                ├── 2. Read PTY master fd for up to 30s
                │      └── looking for "XXXX-XXXX" (user code)
                │          and "https://github.com/login/device"
                │
                ├── 3. Store session: _device_sessions[session_id] = {
                │          "pid": child_pid,
                │          "master_fd": fd,
                │          "started": timestamp,
                │      }
                │
                └── 4. Return {user_code, verification_url, session_id}

Web UI shows code + link ──→ User opens URL and enters code

Web UI ──→ POST /api/git/auth/device-poll?session_id=…
                │
                ▼
           gh_auth_device_poll(session_id)
                │
                ├── 1. Read PTY buffer (MUST drain to prevent gh from blocking)
                │
                ├── 2. Check if child process has exited
                │      ├── exit 0 → read output for "Logged in as …"
                │      │            return {complete: true, user: "jfortin"}
                │      ├── exit ≠ 0 → return {error: "Device flow failed"}
                │      └── still running → return {complete: false}
                │
                └── 3. Auto-cleanup: sessions > 10min are reaped
```

**Why PTY instead of subprocess?** `gh auth login -w` uses terminal
control codes (color, cursor movement, interactive prompts for scopes).
A plain `subprocess.PIPE` can't handle these — the process blocks waiting
for terminal capabilities. A PTY gives `gh` a real terminal to write to,
while we capture the output from the master fd.

---

## Key Data Shapes

### git_status response

```python
{
    "available": True,
    "branch": "main",
    "commit": "a1b2c3d",
    "dirty": True,
    "staged_count": 2,
    "modified_count": 3,
    "untracked_count": 1,
    "total_changes": 6,
    "staged": ["src/app.py", "README.md"],         # capped at 20
    "modified": ["src/config.py", "tests/test.py", "docs/guide.md"],
    "untracked": ["tmp/scratch.py"],
    "ahead": 2,            # commits ahead of upstream
    "behind": 0,           # commits behind upstream
    "last_commit": {
        "hash": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
        "short_hash": "a1b2c3d",
        "message": "feat: add dark mode support",
        "author": "Jean Fortin",
        "date": "2026-02-28T14:30:00-05:00",     # ISO 8601
    },
    "remote_url": "git@github.com:cyberpunk042/devops-control-plane.git",
    "missing_tools": [],                           # from check_required_tools
}
```

**Not a git repo:**
```python
{
    "error": "Not a git repository",
    "available": False,
    "missing_tools": [{"tool": "git", "installed": False, "message": "..."}],
}
```

### git_log response

```python
{
    "commits": [
        {
            "hash": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
            "short_hash": "a1b2c3d",
            "message": "feat: add dark mode support",
            "author": "Jean Fortin",
            "date": "2026-02-28T14:30:00-05:00",
        },
        # ... up to 50 entries (default: 10, max: 50)
    ],
}
```

### git_commit response

```python
# Success
{"ok": True, "hash": "abc1234", "message": "feat: dark mode"}

# No staged changes
{"error": "Nothing to commit (no staged changes)"}

# Empty message
{"error": "Commit message is required"}

# Git error
{"error": "Commit failed: <stderr>"}
```

### git_pull / git_push response

```python
# Success
{"ok": True, "output": "Already up to date."}

# Push failure → auto-sets upstream
{"ok": True, "output": "branch 'feature' set up to track 'origin/feature'."}

# Error
{"error": "Pull failed: <stderr>"}
```

### check_auth response

```python
# SSH — auth OK
{
    "ok": True,
    "remote_type": "ssh",
    "remote_url": "git@github.com:owner/repo.git",
    "needs": None,
    "ssh_key": "id_ed25519",
    "error": None,
}

# SSH — needs passphrase
{
    "ok": False,
    "remote_type": "ssh",
    "remote_url": "git@github.com:owner/repo.git",
    "needs": "ssh_passphrase",
    "ssh_key": "id_ed25519",
    "error": None,
}

# HTTPS — needs credentials
{
    "ok": False,
    "remote_type": "https",
    "remote_url": "https://github.com/owner/repo.git",
    "needs": "https_credentials",
    "ssh_key": None,
    "error": None,
}
```

### add_ssh_key response

```python
# Success
{"ok": True}

# Wrong passphrase
{"ok": False, "error": "Bad passphrase for key /home/user/.ssh/id_ed25519"}
```

### add_https_credentials response

```python
# Success
{"ok": True}

# Failure
{"ok": False, "error": "git credential approve failed: <stderr>"}
```

### gh_status response

```python
{
    "available": True,
    "version": "gh version 2.42.0 (2024-01-15)",
    "authenticated": True,
    "auth_detail": "Logged in to github.com account cyberpunk042 (keyring)",
    "repo": "cyberpunk042/devops-control-plane",
    "missing_tools": [],
}

# gh not installed
{
    "available": False,
    "error": "gh CLI not installed",
    "missing_tools": [{"tool": "gh", "installed": False, ...}],
}
```

### gh_pulls response

```python
{
    "available": True,
    "pulls": [
        {
            "number": 42,
            "title": "feat: add dark mode support",
            "author": {"login": "cyberpunk042"},
            "createdAt": "2026-02-28T14:30:00Z",
            "url": "https://github.com/owner/repo/pull/42",
            "headRefName": "feature/dark-mode",
            "state": "OPEN",
        },
    ],
}
```

### gh_actions_runs response

```python
{
    "available": True,
    "runs": [
        {
            "databaseId": 12345,
            "name": "CI",
            "status": "completed",
            "conclusion": "success",
            "createdAt": "2026-02-28T14:30:00Z",
            "updatedAt": "2026-02-28T14:35:00Z",
            "url": "https://github.com/owner/repo/actions/runs/12345",
            "headBranch": "main",
            "event": "push",
        },
    ],
}
```

### gh_actions_dispatch response

```python
# Success
{"ok": True, "workflow": "ci.yml", "ref": "main"}

# Error
{"error": "Dispatch failed: workflow not found"}
{"error": "No GitHub remote configured"}
```

### gh_user response

```python
{
    "available": True,
    "login": "cyberpunk042",
    "name": "Jean Fortin",
    "avatar_url": "https://avatars.githubusercontent.com/u/...",
    "html_url": "https://github.com/cyberpunk042",
}
```

### gh_repo_info response

```python
{
    "available": True,
    "slug": "cyberpunk042/devops-control-plane",
    "name": "devops-control-plane",
    "owner": "cyberpunk042",
    "visibility": "PRIVATE",
    "is_private": True,
    "is_fork": False,
    "description": "DevOps control plane with web admin panel",
    "default_branch": "main",
    "url": "https://github.com/cyberpunk042/devops-control-plane",
    "ssh_url": "git@github.com:cyberpunk042/devops-control-plane.git",
    "homepage_url": "",
}
```

### gh_repo_create response

```python
# Success
{
    "ok": True,
    "message": "Repository created: cyberpunk042/my-project",
    "name": "cyberpunk042/my-project",
    "private": True,
    "url": "https://github.com/cyberpunk042/my-project",
}

# Error
{"error": "Failed to create repository: repository already exists"}
```

### gh_auth_device_start response

```python
# Success
{
    "ok": True,
    "session_id": "abc123def456",
    "user_code": "XXXX-XXXX",
    "verification_url": "https://github.com/login/device",
}

# Error
{"ok": False, "error": "Failed to start device flow: <detail>"}
```

### gh_auth_device_poll response

```python
# Complete — user authorized
{
    "ok": True,
    "complete": True,
    "user": "cyberpunk042",
}

# Still waiting — user hasn't entered code yet
{
    "ok": True,
    "complete": False,
}

# Session expired or error
{
    "ok": False,
    "error": "Session not found or expired",
}
```

### git_remotes response

```python
{
    "available": True,
    "remotes": [
        {
            "name": "origin",
            "fetch": "git@github.com:cyberpunk042/devops-control-plane.git",
            "push": "git@github.com:cyberpunk042/devops-control-plane.git",
        },
    ],
}
```

---

## Architecture

```
                CLI (ui/cli/git.py)
                Routes (routes/git/)
                       │
                       │ imports
                       │
            ┌──────────▼──────────┐
            │  git_ops.py         │  backward-compat shim
            │  (re-exports all)   │  → imports from git/
            └──────────┬──────────┘
                       │
            ┌──────────▼──────────────────────────┐
            │  git/__init__.py                     │
            │  Public API — re-exports all symbols │
            └────┬──────┬──────┬──────┬──────┬────┘
                 │      │      │      │      │
        ┌────────┘      │      │      │      └────────┐
        ▼               ▼      │      ▼               ▼
     ops.py         auth.py    │   gh_api.py      gh_repo.py
     (runners +     (SSH +     │   (queries)      (repo mgmt +
      porcelain)    HTTPS)     │                   remotes)
        ▲               │      │      │
        │               │      │      │
        └───────────────┼──────┼──────┘
      ops.run_git,      │      │
      ops.run_gh,       ▼      ▼
      ops.repo_slug  gh_auth.py
                     (login, logout,
                      token, device flow)
```

### Dependency Rules

| Rule | Detail |
|------|--------|
| `ops.py` is the foundation | Provides `run_git`, `run_gh`, `repo_slug` |
| `auth.py` imports from `ops` | Uses `run_git` for git commands |
| `gh_api.py` imports from `ops` | Uses `run_gh`, `run_git`, `repo_slug` |
| `gh_auth.py` imports from `ops` | Uses `run_gh`, `run_git`, `repo_slug` |
| `gh_repo.py` imports from `ops` | Uses `run_gh`, `run_git`, `repo_slug` |
| No circular imports | All imports point toward `ops.py` |

---

## File Map

```
git/
├── __init__.py      Public API re-exports (62 lines)
├── ops.py           Low-level runners + porcelain git operations (301 lines)
├── auth.py          SSH + HTTPS credential management (511 lines)
├── gh_api.py        GitHub API queries via gh CLI (230 lines)
├── gh_auth.py       GitHub CLI authentication + device flow (537 lines)
├── gh_repo.py       GitHub repo + remote management (236 lines)
└── README.md        This file
```

---

## Per-File Documentation

### `ops.py` — Runners + Porcelain (301 lines)

**Low-level runners:**

| Function | What It Runs | Default Timeout |
|----------|-------------|----------------|
| `run_git(*args, cwd, timeout, check)` | `git <args>` | 15s |
| `run_gh(*args, cwd, timeout, stdin)` | `gh <args>` | 30s |
| `repo_slug(project_root)` | `git remote get-url origin` | 15s |

`run_gh` has special error handling: if `gh` is not found (`FileNotFoundError`),
it returns a synthetic `CompletedProcess` with `returncode=127` and a
descriptive stderr instead of raising an exception.

**Remote URL parsing (`repo_slug`):**

```python
# SSH format:  git@github.com:owner/repo.git → owner/repo
# HTTPS format: https://github.com/owner/repo.git → owner/repo
# Other hosts: None
```

**Porcelain operations:**

| Function | What It Does | Audited |
|----------|-------------|---------|
| `git_status(root)` | Branch, dirty state, ahead/behind, staged/modified/untracked files, last commit | No |
| `git_log(root, n)` | Recent commit history (max 50, default 10) | No |
| `git_commit(root, message, files)` | Stage files + commit | No |
| `git_pull(root, rebase)` | Pull from remote (optional rebase) | No |
| `git_push(root, force)` | Push to remote (auto-sets upstream if needed, uses `--force-with-lease`) | No |

**`git_status()` implementation:**

1. `git rev-parse --abbrev-ref HEAD` → branch name
2. `git rev-parse --short HEAD` → commit hash
3. `git status --porcelain` → staged/modified/untracked (porcelain v1)
4. `git rev-list --left-right --count HEAD...@{u}` → ahead/behind
5. `git log -1 --format=%H%n%h%n%s%n%an%n%aI` → last commit details
6. `git remote get-url origin` → remote URL

**Porcelain v1 parsing:**

```
 M src/app.py          ← wt='M' → modified
A  README.md           ← idx='A' → staged
?? tmp/scratch.py      ← wt='?' → untracked
MM src/config.py       ← both staged AND modified
D  old_file.py         ← idx='D' → staged (deleted)
```

**Push auto-upstream:** If push fails with "no upstream branch",
the function automatically retries with `--set-upstream origin <branch>`.

### `auth.py` — SSH + HTTPS Credential Management (511 lines)

| Section | Functions | Purpose |
|---------|-----------|---------|
| **Detection** | `detect_remote_type(root)` | SSH vs HTTPS from remote URL |
| **Detection** | `get_remote_url(root)` | Raw remote URL |
| **Detection** | `find_ssh_key()` | Find primary key in `~/.ssh/` |
| **Detection** | `key_has_passphrase(key_path)` | Check if key is encrypted |
| **Auth check** | `check_auth(project_root)` | Full auth state assessment |
| **Auth check** | `_agent_has_keys()` | Does ssh-agent have loaded keys? |
| **Auth check** | `_classify_error(stderr, ...)` | Map git errors → user needs |
| **SSH agent** | `_detect_existing_agent()` | Find running agent in env |
| **SSH agent** | `_start_ssh_agent()` | Spawn new ssh-agent |
| **SSH agent** | `add_ssh_key(root, passphrase)` | Add key with passphrase |
| **HTTPS** | `add_https_credentials(root, token)` | Store via git credential |
| **Env** | `git_env()` | Get env dict with agent vars |
| **State** | `is_auth_ok()` | Session auth verified? |
| **State** | `is_auth_tested()` | Auth tested at all this session? |

**SSH key detection priority:**
1. `~/.ssh/id_ed25519`
2. `~/.ssh/id_rsa`
3. `~/.ssh/id_ecdsa`
4. `~/.ssh/id_dsa`

**Error classification rules:**

| Pattern in stderr | Classification |
|-------------------|---------------|
| `passphrase` / `Permission denied (publickey)` | `needs: "ssh_passphrase"` |
| `Host key verification failed` | `needs: "ssh_passphrase"` |
| `Authentication failed` / `401` / `403` | `needs: "https_credentials"` |
| `Could not resolve host` | `error: "Network unreachable"` |

### `gh_api.py` — GitHub API Queries (230 lines)

| Function | gh CLI Command | Return Shape |
|----------|---------------|-------------|
| `gh_status(root)` | `gh --version` + `gh auth status` | `{available, version, authenticated, auth_detail, repo}` |
| `gh_pulls(root)` | `gh pr list --json ...` | `{available, pulls: [{number, title, author, ...}]}` |
| `gh_actions_runs(root, n)` | `gh run list --json ... --limit N` | `{available, runs: [{databaseId, name, status, ...}]}` |
| `gh_actions_dispatch(root, workflow, ref)` | `gh workflow run <wf> --ref <ref>` | `{ok, workflow, ref}` |
| `gh_actions_workflows(root)` | `gh workflow list --json ...` | `{available, workflows: [{id, name, state}]}` |
| `gh_user(root)` | `gh api user --jq ...` | `{available, login, name, avatar_url, html_url}` |
| `gh_repo_info(root)` | `gh repo view <slug> --json ...` | `{available, slug, name, owner, visibility, ...}` |

All `gh_api` functions check for `repo_slug()` first — if there's no
GitHub remote configured, they return `{available: false, error: ...}`
immediately without making any API calls.

### `gh_auth.py` — GitHub CLI Authentication (537 lines)

Three login modes (see above). Device flow uses PTY spawning, session
tracking, and periodic polling with auto-cleanup.

| Function | What It Does |
|----------|-------------|
| `gh_auth_login(root, token, hostname, auto_drive)` | Login via token, interactive terminal, or device flow |
| `gh_auth_logout(root)` | `gh auth logout --hostname github.com` |
| `gh_auth_token(root)` | `gh auth token` → extract current PAT |
| `gh_auth_device_start(root)` | Spawn PTY, capture user code + URL |
| `gh_auth_device_poll(session_id, root)` | Check if device flow completed |
| `_build_auto_drive_script(root, hostname)` | Generate bash script for terminal-based login |
| `_cleanup_stale_sessions()` | Reap device sessions > 10 minutes old |

**Module-level state:**

| Object | Type | Purpose |
|--------|------|---------|
| `_device_sessions` | `dict[str, dict]` | Active device flow sessions (pid, master_fd, timestamp) |

### `gh_repo.py` — Repository + Remote Management (236 lines)

| Function | What It Does | Idempotent |
|----------|-------------|-----------|
| `gh_repo_create(root, name, private, description, add_remote)` | Create new repo + push | No |
| `gh_repo_set_visibility(root, visibility)` | `gh repo edit --visibility=...` | Yes |
| `gh_repo_set_default_branch(root, branch)` | `gh repo edit --default-branch=...` | Yes |
| `git_remotes(root)` | `git remote -v` → parsed list | N/A |
| `git_remote_add(root, name, url)` | Add remote, update if exists | ✅ Yes |
| `git_remote_remove(root, name)` | Remove remote | ✅ Yes (no-op if missing) |
| `git_remote_rename(root, old, new)` | Rename remote | No |
| `git_remote_set_url(root, name, url)` | Change remote URL | Yes |

---

## Backward Compatibility

| Old path | Re-exports from |
|----------|----------------|
| `services/git_ops.py` | `git/` — all public functions |

```python
# ✅ New (package-level import)
from src.core.services.git import git_status, check_auth, gh_pulls

# ⚠️ Legacy shim — still works, avoid in new code
from src.core.services.git_ops import git_status
```

---

## Consumers

| Consumer | What It Uses |
|----------|-------------|
| **Routes** `routes/git/` | All functions — status, log, commit, pull, push, auth, GitHub API, device flow |
| **CLI** `ui/cli/git.py` | `git_status`, `git_log`, `git_commit`, `git_push`, `git_pull`, `check_auth` |
| **Wizard** `wizard/helpers.py` | `git_status` (repository detection) |
| **Metrics** `metrics/ops.py` | `git_status`, `gh_status` (health probes) |
| **K8s validate** `k8s_validate.py` | `git_status` (cross-domain validation) |
| **Chat sync** `routes/chat/` | `check_auth`, `git_env`, `git_pull`, `git_push`, `git_commit` |

---

## API Endpoints

| Route | Method | Purpose | Module |
|-------|--------|---------|--------|
| `/api/git/status` | GET | Repository status | `ops` |
| `/api/git/log` | GET | Recent commits | `ops` |
| `/api/git/commit` | POST | Stage + commit | `ops` |
| `/api/git/pull` | POST | Pull from remote | `ops` |
| `/api/git/push` | POST | Push to remote | `ops` |
| `/api/git/auth/check` | GET | Auth state check | `auth` |
| `/api/git/auth/ssh/add` | POST | Unlock SSH key | `auth` |
| `/api/git/auth/https/add` | POST | Store HTTPS credentials | `auth` |
| `/api/git/auth/device/start` | POST | Start device flow | `gh_auth` |
| `/api/git/auth/device/poll` | POST | Poll device flow | `gh_auth` |
| `/api/git/auth/login` | POST | GitHub CLI login (token/interactive) | `gh_auth` |
| `/api/git/auth/logout` | POST | GitHub CLI logout | `gh_auth` |
| `/api/git/github/status` | GET | GitHub CLI status | `gh_api` |
| `/api/git/github/pulls` | GET | Open pull requests | `gh_api` |
| `/api/git/github/actions/runs` | GET | Workflow run history | `gh_api` |
| `/api/git/github/actions/dispatch` | POST | Trigger workflow | `gh_api` |
| `/api/git/github/actions/workflows` | GET | List workflows | `gh_api` |
| `/api/git/github/user` | GET | Authenticated user info | `gh_api` |
| `/api/git/github/repo` | GET | Repository info | `gh_api` |
| `/api/git/github/repo/create` | POST | Create new repo | `gh_repo` |
| `/api/git/github/repo/visibility` | POST | Toggle visibility | `gh_repo` |
| `/api/git/github/repo/default-branch` | POST | Change default branch | `gh_repo` |
| `/api/git/remotes` | GET | List all remotes | `gh_repo` |
| `/api/git/remotes/add` | POST | Add/update remote | `gh_repo` |
| `/api/git/remotes/remove` | POST | Remove remote | `gh_repo` |
| `/api/git/remotes/rename` | POST | Rename remote | `gh_repo` |
| `/api/git/remotes/set-url` | POST | Change remote URL | `gh_repo` |

---

## Dependency Graph

```
ops.py  ← foundation (subprocess, json, shutil, pathlib)
  ▲
  │  run_git, run_gh, repo_slug
  │
  ├── auth.py       (+ subprocess, os, tempfile, pathlib)
  ├── gh_api.py      (+ json, shutil, pathlib)
  ├── gh_auth.py     (+ os, pty, select, time, uuid, pathlib)
  └── gh_repo.py     (+ pathlib)
```

**External dependencies:**

| Module | Uses |
|--------|------|
| `ops.py` | `subprocess`, `json`, `shutil`, `pathlib` |
| `auth.py` | `subprocess`, `os`, `tempfile`, `pathlib`, `audit_helpers` |
| `gh_api.py` | `json`, `shutil`, `pathlib` |
| `gh_auth.py` | `os`, `pty`, `select`, `time`, `uuid`, `pathlib`, `audit_helpers` |
| `gh_repo.py` | `pathlib` only |

No third-party dependencies. The entire git domain operates with
stdlib only.

---

## Error Handling Patterns

Two consistent patterns across all functions:

```python
# Pattern 1: "available" flag (observe/query functions)
{"available": False, "error": "gh CLI not installed"}
{"available": True, "pulls": [...]}

# Pattern 2: "ok" or "error" (act/mutate functions)
{"error": "Commit message is required"}
{"ok": True, "hash": "abc1234", "message": "feat: dark mode"}
```

**`run_gh` graceful degradation:** If `gh` CLI is not installed,
`run_gh` catches `FileNotFoundError` and returns a synthetic
`CompletedProcess(returncode=127)` instead of crashing. This lets
callers handle the absence uniformly.

**Auth classification:** `_classify_error()` maps raw git/ssh stderr
patterns to actionable user needs (`ssh_passphrase`, `https_credentials`)
rather than exposing raw error messages.

---

## Design Decisions

### Why is `auth.py` independent of `ops.py`?

`auth.py` manages SSH agent and HTTPS credential state — this is
subprocess work (`ssh-agent`, `ssh-add`, `git credential approve`)
but it doesn't use the `run_git()` wrapper. The auth process needs
direct control over environment variables, stdin piping, and
temporary file creation that the simplified `run_git()` API doesn't
expose. Keeping them separate also means auth state management can
be tested without a git repository.

### Why PTY for device flow instead of subprocess?

`gh auth login -w` uses terminal control codes (ANSI colors, cursor
movement, interactive scope selection). A plain `subprocess.PIPE`
causes `gh` to block waiting for terminal capabilities that don't
exist. A pseudo-terminal (`pty.openpty()`) gives `gh` a real terminal
to write to while the control plane reads the master fd to capture
the one-time code. The trade-off: PTY management is complex (fd
lifecycle, process reaping, buffer draining) but it's the only
way to make the device flow work from a web server.

### Why module-level `_device_sessions` dict?

Device flow is inherently stateful and asynchronous — the user starts
a session, goes to a browser, enters a code, and comes back. The session
state (child PID, master fd, timestamp) must survive between HTTP requests.
A module-level dict is the simplest container. It's cleaned up by
`_cleanup_stale_sessions()` which reaps sessions older than 10 minutes.

### Why does `run_gh` catch FileNotFoundError?

Other runners (`run_git`, Docker's `run_docker`) don't do this because
git and Docker are always required. But `gh` is optional — a project
can use git without GitHub CLI. Catching the exception at the runner
level means every caller gets consistent behavior without individual
try/except blocks.

### Why does `git_push` auto-set upstream?

The most common push failure is "no upstream branch" on a new branch.
Rather than returning an error and forcing the user to figure out
`git push --set-upstream origin <branch>`, the function detects this
specific error and retries with the correct command. This makes the
web UI "push" button work on first push without extra steps.

### Why are observe functions not audited?

`git_status()`, `git_log()`, and all `gh_*` query functions don't
write audit entries because they're read-only and called frequently
(every dashboard refresh). Auditing them would flood the activity log
with noise. Only mutating operations (commit, push, pull, auth changes)
warrant audit entries.

### Why separate gh_api.py, gh_auth.py, and gh_repo.py?

These three modules have fundamentally different concerns:
- `gh_api.py` — read-only queries (PRs, runs, user info)
- `gh_auth.py` — authentication lifecycle (login, logout, device flow)
- `gh_repo.py` — repository mutations (create, visibility, remotes)

Combining them would create a 1,000+ line file mixing read-only queries
with PTY-based device flow logic. The separation also matches the route
structure — auth routes, API routes, and repo routes map 1:1 to the
service modules.
