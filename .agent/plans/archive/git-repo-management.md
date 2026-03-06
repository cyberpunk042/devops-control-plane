# Git & GitHub Repository Management — Implementation Plan

> **Status:** Draft — awaiting review
> **Created:** 2026-03-03
> **Scope:** Rename, remotes, visibility, history management, server lifecycle, streaming output

---

## 1. Current State

### What already exists in the backend (`gh_repo.py`)

| Function | Status |
|----------|--------|
| `gh_repo_create()` | ✅ Exists — create repo + set as origin |
| `gh_repo_set_visibility()` | ✅ Exists — toggle public ↔ private |
| `gh_repo_set_default_branch()` | ✅ Exists — change default branch on GH |
| `git_remotes()` | ✅ Exists — list all remotes + URLs |
| `git_remote_add()` | ✅ Exists — add remote (idempotent) |
| `git_remote_remove()` | ✅ Exists — remove remote |
| `git_remote_rename()` | ✅ Exists — rename remote |
| `git_remote_set_url()` | ✅ Exists — change remote URL |

### What's completely missing

| Feature | What's needed |
|---------|---------------|
| `gh_repo_rename()` | `gh repo rename <name> --yes` |
| `git_gc()` | `git gc` / `git gc --aggressive` |
| `git_repack()` | `git repack -a -d` |
| `git_history_reset()` | Orphan branch → commit → force push |
| `git_filter_repo()` | Scrub specific paths from all commits (installed via tool install system) |
| Flask routes for `gh_repo.py` | **None** of the existing functions have API routes |
| Server lifecycle API | Restart, reload, PID detection |
| Streaming subprocess output | SSE-based streaming for long ops |
| Tool recipe: `git-filter-repo` | Add to `core/system.py` recipes using `_PIP + ['install', 'git-filter-repo']` pattern (same as `jc`, `supervisor`) |

### UI situation

- **Git card:** Has commit, pull, push, sync, stash, diff, log. No remote management.
- **GitHub card:** Has PR list, action runs, workflows, envs, secrets. Has "Reconfigure" button but **no rename, no visibility toggle**, no remote management.

### Current project state

```
Remote: git@github.com:cyberpunk042/devops-control-plane.git
Folder: /home/jfortin/devops-control-plane
gh CLI: ✓ installed
git gc: ✓ available
git-filter-repo: ✗ not installed
bfg: ✗ not installed
```

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         UI (Browser)                             │
│                                                                  │
│  Git Card                    │  GitHub Card                      │
│  ┌──────────────────────┐    │  ┌──────────────────────────┐     │
│  │ Remotes management   │    │  │ Rename repository        │     │
│  │ Add / Change / Remove│    │  │ Toggle visibility        │     │
│  │ History management   │    │  │ Default branch           │     │
│  │ GC / Repack / Reset  │    │  │ Create new repo          │     │
│  └──────────────────────┘    │  └──────────────────────────┘     │
│                              │                                    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │         "Project Rename" Wizard (modal)                  │    │
│  │  Step 1: New name → GH Rename → Update remote URL       │    │
│  │  Step 2: Detect folder mismatch → Offer mv              │    │
│  │  Step 3: Server restart with new CWD                     │    │
│  │  Output: Streaming SSE log                               │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  Server Lifecycle Bar (global)                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ [🔄 Restart Server]  [Status: Running]  [PID: 12345]    │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
         │                  │                    │
         ▼ API              ▼ API                ▼ SSE
┌──────────────────────────────────────────────────────────────────┐
│                      Flask Routes Layer                          │
│                                                                  │
│  /api/git/remotes              GET    list remotes               │
│  /api/git/remote/add           POST   add/update remote          │
│  /api/git/remote/remove        POST   remove remote              │
│  /api/git/remote/set-url       POST   change URL                 │
│  /api/git/remote/rename        POST   rename remote               │
│  /api/git/gc                   POST   git gc                     │
│  /api/git/history-reset        POST   orphan + force push        │
│  /api/git/filter-repo          POST   scrub paths from history   │
│                                                                  │
│  /api/gh/repo/rename           POST   gh repo rename             │
│  /api/gh/repo/visibility       POST   set public/private         │
│  /api/gh/repo/default-branch   POST   set default branch         │
│  /api/gh/repo/create           POST   create new repo            │
│                                                                  │
│  /api/server/status            GET    PID, uptime, CWD           │
│  /api/server/restart           POST   graceful restart           │
│                                                                  │
│  /api/events (SSE)             GET    stream:* events             │
└──────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Core Services Layer                            │
│                                                                  │
│  git/gh_repo.py  — ✅ mostly exists, add rename + gc             │
│  git/ops.py      — ✅ exists, add gc/repack/history-reset        │
│  server/lifecycle.py — NEW: restart, PID, status                 │
│  event_bus.py    — ✅ exists, add stream:* events                │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Phase Breakdown

### Phase 1: Backend Ops — New git/gh operations

**New functions in `git/ops.py`:**

```python
def git_gc(project_root: Path, *, aggressive: bool = False) -> dict:
    """Run git gc to optimize the repo."""
    args = ["gc"]
    if aggressive:
        args.append("--aggressive")
    r = run_git(*args, cwd=project_root, timeout=300)  # gc can be slow
    ...

def git_repack(project_root: Path) -> dict:
    """Repack objects for better compression."""
    r = run_git("repack", "-a", "-d", "--depth=250", "--window=250",
                cwd=project_root, timeout=300)
    ...

def git_history_reset(
    project_root: Path,
    message: str = "Initial commit (history reset)",
) -> dict:
    """Reset git history to a single commit.

    Process:
    1. Create orphan branch (temp-reset)
    2. Add all files
    3. Commit with message
    4. Delete old branch (main/master)
    5. Rename temp → old branch name
    6. Force push to remote
    """
    ...

def git_filter_repo(
    project_root: Path,
    *,
    paths_to_remove: list[str] | None = None,
    invert_paths: bool = False,
    force: bool = False,
) -> dict:
    """Scrub specific files/paths from entire git history.

    Requires `git-filter-repo` (pip install git-filter-repo).
    Wraps `git filter-repo --path <path> --invert-paths [--force]`.

    Use cases:
    - Remove accidentally committed secrets
    - Strip large binaries from history
    - Clean sensitive data from all commits

    Returns:
        {"ok": True, "removed_paths": [...], "output": "..."}
        {"ok": False, "error": "git-filter-repo not installed"}
    """
    # Check availability via shutil.which
    # If missing → return tool name so the UI can trigger install
    # via the existing /api/tools/install endpoint
    if not shutil.which("git-filter-repo"):
        return {"ok": False, "error": "git-filter-repo not installed",
                "tool_name": "git-filter-repo"}  # UI calls install API
    ...
```

**New tool recipe in `core/system.py`:**

```python
# Added next to the existing "git" recipe
"git-filter-repo": {
    "label": "git-filter-repo (history rewriting)",
    "category": "system",
    "cli": "git-filter-repo",
    "install": {
        "_default": _PIP + ["install", "git-filter-repo"],
    },
    "needs_sudo": {"_default": False},
    "install_via": {"_default": "pip"},
    "requires": {"binaries": ["git"]},
    "verify": ["git-filter-repo", "--version"],
},
```

**New function in `git/gh_repo.py`:**

```python
def gh_repo_rename(project_root: Path, new_name: str) -> dict:
    """Rename the GitHub repository.

    Uses `gh repo rename <new_name> --yes`.
    After rename, GitHub auto-redirects old URLs.
    Also updates the local git remote URL to match.

    Returns:
        {"ok": True, "old_name": ..., "new_name": ..., "new_url": ...}
    """
    ...
```

### Phase 2: API Routes — Expose all gh_repo.py + new ops

**New file: `src/ui/web/routes/integrations/gh_repo_routes.py`**

Routes to create:
- `POST /api/gh/repo/rename` — `{ "new_name": "devops-solution-control-plane" }`
- `POST /api/gh/repo/visibility` — `{ "visibility": "public" | "private" }`
- `POST /api/gh/repo/default-branch` — `{ "branch": "main" }`
- `POST /api/gh/repo/create` — `{ "name": "...", "private": true, "description": "..." }`

**New routes in `integrations/git.py` (or new sub-module):**
- `GET  /api/git/remotes` — list all remotes
- `POST /api/git/remote/add` — `{ "name": "origin", "url": "..." }`
- `POST /api/git/remote/remove` — `{ "name": "origin" }`
- `POST /api/git/remote/set-url` — `{ "name": "origin", "url": "..." }`
- `POST /api/git/remote/rename` — `{ "old_name": "origin", "new_name": "upstream" }`
- `POST /api/git/gc` — `{ "aggressive": false }`
- `POST /api/git/history-reset` — `{ "message": "..." }`
- `POST /api/git/filter-repo` — `{ "paths": ["secrets.env", "*.pem"], "force": false }`

All destructive operations should require `@requires_git_auth` and `@run_tracked`.

### Phase 3: Server Lifecycle

**The problem:**
The server IS the running process. Rename `mv` means the CWD changes.
Restart means the process must exit and re-launch.

**Solution — inspired by continuity-orchestrator's Docker restart pattern:**

1. **`/api/server/status`** — returns PID, uptime, CWD, port
2. **`/api/server/restart`** — graceful restart:
   - Server writes a `.restart-signal` file with new CWD (if changed)
   - Server sends SSE event `server:restarting`
   - Frontend shows "Server restarting..." with auto-reconnect
   - Server exits with code 42 (special restart code)
   - The shell wrapper (`manage.sh` or a new wrapper) catches exit 42 and re-launches

3. **Wrapper script enhancement (`manage.sh web`):**

```bash
# Restart loop
while true; do
    "$PYTHON" -m "$CLI_MODULE" web "$@"
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 42 ]; then
        # Check for .restart-signal which may contain new CWD
        if [ -f ".restart-signal" ]; then
            NEW_CWD=$(cat .restart-signal)
            rm -f .restart-signal
            if [ -n "$NEW_CWD" ] && [ -d "$NEW_CWD" ]; then
                cd "$NEW_CWD"
                echo "  🔄 Restarting in: $NEW_CWD"
            fi
        fi
        echo "  🔄 Server restarting..."
        continue
    fi
    break
done
```

4. **Frontend auto-reconnect:**
   - SSE `_onReady` already detects server restarts and shows a toast
   - On `server:restarting` event, the frontend should:
     - Show a "Restarting server..." overlay
     - Poll for reconnection
     - On reconnect, full page reload to pick up any CWD changes

5. **Flask-side signal handling** (inspired by continuity-orchestrator's `server.py`):
   - Register `SIGTERM` and `SIGINT` handlers in `run_server()`
   - On signal: log shutdown, clean up SSE connections, flush event bus
   - Ensures graceful exit even when killed externally (e.g. by `--auto` mode's `stop_server`)

### Phase 3B: `./manage.sh web --auto` Dev Mode (spacebar live-reload)

**Reference implementation:** `system-course/scripts/build_site.sh auto`

The system-course project has a proven spacebar-driven interactive loop. We adapt this pattern for the devops-control-plane Flask server.

**How it works in system-course:**
1. `stty -echo -icanon min 0 time 10` — raw terminal, 1-second timeout
2. `dd bs=1 count=1` — reads single char, returns empty on timeout
3. Space detected → stop server → rebuild → restart → return to raw mode
4. `inotifywait` — background file watcher notifies of changes
5. Every 60s: periodic compact status refresh
6. Rich auto-mode banner: recent commits, uncommitted files, focus area, criticality

**Our adaptation — `./manage.sh web --auto`:**

```bash
# In manage.sh, when command is "web" and --auto is passed:
# 1. Start server in background
# 2. Enter raw terminal loop
# 3. Space → restart (SIGTERM + re-launch)
# 4. q/Q → graceful shutdown
# 5. File changes → show notification

# The key difference from system-course:
# - system-course stops/rebuilds/restarts a Docusaurus static build
# - We stop/restart a Flask server process (much simpler — no build step)
# - Restart = kill + re-launch the Python process
# - The frontend auto-reconnects via SSE _onReady()
```

**Implementation in `manage.sh`:**

```bash
web_auto() {
    local HOST="${HOST:-127.0.0.1}"
    local PORT="${PORT:-8000}"
    local REBUILD_COUNT=0
    local SERVER_PID=""

    # Start server in background
    start_server() {
        "$PYTHON" -m "$CLI_MODULE" web --host "$HOST" --port "$PORT" &
        SERVER_PID=$!
        sleep 1
    }

    stop_server() {
        if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
            kill "$SERVER_PID" 2>/dev/null
            wait "$SERVER_PID" 2>/dev/null || true
            SERVER_PID=""
        fi
    }

    cleanup() {
        stty sane 2>/dev/null || true
        stop_server
        echo ""
        ok "Server stopped."
        exit 0
    }
    trap cleanup INT TERM

    banner
    info "Auto mode — http://${HOST}:${PORT}"
    info "[ SPACE ] Restart server    [ q ] Quit    [ Ctrl+C ] Exit"
    echo ""

    start_server

    # Raw terminal mode
    stty -echo -icanon min 0 time 10 2>/dev/null || true

    while true; do
        char=$(dd bs=1 count=1 2>/dev/null) || true

        if [ -z "$char" ]; then
            # Timeout — could check file watcher here
            continue
        fi

        if [ "$char" = " " ]; then
            REBUILD_COUNT=$((REBUILD_COUNT + 1))
            stty sane 2>/dev/null || true
            echo ""
            info "🔄 Restart #${REBUILD_COUNT} — $(date +%H:%M:%S)"
            stop_server
            sleep 0.3
            start_server
            info "Server restarted."
            show_compact_status  # git status, file count, etc.
            stty -echo -icanon min 0 time 10 2>/dev/null || true
        fi

        if [ "$char" = "q" ] || [ "$char" = "Q" ]; then
            cleanup
        fi
    done
}
```

**What the frontend does on reconnect:**
- The SSE `_onReady` handler already detects server restarts (boot_id changes)
- It shows a toast: "Server reconnected"
- We add: if SSE disconnects, show a "Reconnecting…" overlay
- On reconnect, the overlay closes and cards auto-refresh via stale keys

**Rich context banner (optional, inspired by system-course):**
- On each spacebar press, show:
  - Restart #N at HH:MM:SS
  - Time since last restart
  - Uncommitted files count + delta
  - Whether a new commit happened since last restart

### Phase 4: Streaming Output for Long Operations

Long operations (gc, history-reset, rename) need real-time streaming to the UI.

**Backend pattern:**
- Use the existing `event_bus` to publish `stream:line` events
- Each operation gets a `stream_id` (e.g. `git-gc-1709500000`)
- The subprocess is run with `Popen` instead of `run`, reading stdout/stderr line by line
- Each line is published as `bus.publish("stream:line", stream_id=..., line=...)`
- End of stream: `bus.publish("stream:done", stream_id=..., exit_code=...)`

**Frontend pattern:**
- Modal or inline terminal panel
- Listens for `stream:line` events matching the `stream_id`
- Renders each line in a `<pre>` scrolled to bottom
- Shows success/error when `stream:done` arrives

### Phase 5: Project Rename Wizard

This is the high-level orchestration modal.

**Flow:**
1. User enters new project name (e.g. `devops-solution-control-plane`)
2. Pre-flight checks:
   - Is working tree clean? (warn if dirty)
   - Does `gh` CLI have auth?
   - What's the current GH repo name?
3. Step 1: **Rename on GitHub** — `gh repo rename <name> --yes`
4. Step 2: **Update git remote URL** — derive new URL from old pattern
5. Step 3: **Detect local folder mismatch**
   - Current: `/home/jfortin/devops-control-plane`
   - Expected: `/home/jfortin/devops-solution-control-plane`
   - If mismatch → show option to rename
6. Step 4: **Local folder rename** (if opted in)
   - Write `.restart-signal` with new path
   - `os.rename()` the folder
   - Trigger server restart via exit code 42
   - Frontend auto-reconnects after restart
7. Step 5: **Verify** — show new state (remote URL, folder, GH repo name)

**If user skips folder rename:**
- Everything still works — git doesn't care about folder names
- Just show a notice that the folder name doesn't match

### Phase 6: UI — Git Card Enhancements

Add to Git card action toolbar:
- **"Remotes"** button → opens modal showing all remotes with add/change/remove
- **"History"** button → opens modal with:
  - GC (optimize) — with aggressive option checkbox
  - Repack
  - Scrub Paths (`git-filter-repo`) — path input, availability gate, Install button if missing
  - History Reset — with confirmation ("This is destructive! Force push required.")

### Phase 7: UI — GitHub Card Enhancements

Add to GitHub card action toolbar:
- **"Rename"** button → opens Project Rename wizard (Phase 5)
- **"Visibility"** button → dropdown Public/Private with confirmation
- **"Default Branch"** button → input for branch name

### Phase 8: Visibility Toggle

Since `gh_repo_set_visibility()` already exists:

**Route:** `POST /api/gh/repo/visibility`
**UI:** Confirmation dialog:
```
⚠️ Change Repository Visibility

Current: PRIVATE
Change to: PUBLIC

This will make the repository visible to everyone on the internet.
Anyone can clone, fork, and view the source code.

[ Cancel ]  [ Make PUBLIC ]
```

---

## 4. Dependencies & Risk Matrix

| Component | Risk | Mitigation |
|-----------|------|------------|
| GitHub rename | Low — `gh repo rename` is well-tested | Auto-redirect means no breakage |
| Remote URL update | Low — idempotent `git remote set-url` | Pre-check with `git ls-remote` |
| Local folder `mv` | **HIGH** — running process CWD becomes invalid | Exit code 42 + wrapper restart loop |
| History reset | **HIGH** — destructive, irreversible | Triple confirmation + stream output |
| Server restart | Medium — SSE reconnection needed | Existing `_onReady` handles this |
| `git gc --aggressive` | Low but slow — can take minutes | Stream output + timeout=300 |
| `git-filter-repo` | Medium — requires pip install, destructive | Availability gate + Install button if missing + triple confirmation |

---

## 5. Implementation Order

1. **Phase 1** — Backend ops (new functions)
2. **Phase 2** — API routes (expose everything)
3. **Phase 3** — Server lifecycle (restart mechanism)
4. **Phase 3B** — `--auto` dev mode (spacebar live-reload)
5. **Phase 4** — Streaming output (SSE stream)
6. **Phase 6** — Git card UI (remotes + history)
7. **Phase 7** — GitHub card UI (rename button + visibility toggle)
8. **Phase 5** — Project Rename wizard (orchestration)
9. **Phase 8** — Visibility toggle UI

Phase 3 + 3B are the server lifecycle foundation.
Phase 3 + 4 are infrastructure that Phase 5 depends on.
Phases 6 + 7 can be done independently.
Phase 3B can be done independently anytime.

---

## 6. Files to Create / Modify

### New files
| File | What |
|------|------|
| `src/core/services/git/history.py` | `git_gc`, `git_repack`, `git_history_reset` |
| `src/ui/web/routes/integrations/gh_repo_routes.py` | Routes for gh_repo.py functions |
| `src/core/services/server_lifecycle.py` | PID, status, restart signal, folder mv |
| `src/ui/web/routes/server.py` | `/api/server/status`, `/api/server/restart` |

### Modified files
| File | What |
|------|------|
| `src/core/services/git/gh_repo.py` | Add `gh_repo_rename()` |
| `src/ui/web/routes/integrations/git.py` | Add remote management + gc routes |
| `src/ui/web/templates/scripts/integrations/_git.html` | Remotes modal + History modal |
| `src/ui/web/templates/scripts/integrations/_github.html` | Rename + Visibility actions |
| `src/ui/web/server.py` | Restart exit code handling |
| `manage.sh` | Restart loop wrapper for `web` command |
| `src/ui/web/templates/scripts/_event_stream.html` | `stream:line`, `stream:done`, `server:restarting` handlers |

---

## 7. Assumptions

1. The user's local environment always has `gh` CLI available
2. The `manage.sh web` wrapper can be enhanced with a restart loop
3. `os.rename()` on the project folder is safe if we immediately exit after
4. The SSE auto-reconnect pattern already works (existing `_onReady`)
5. `git-filter-repo` is installed via the tool install system — gated behind availability check in UI
6. Force push after history reset is acceptable (user confirms)

---

## 8. Reference Implementation

**system-course `build_site.sh auto`** — 1,187-line bash script providing:
- `stty` raw terminal mode with 1s `dd` timeout for keypress detection
- `inotifywait` background file watcher with change log buffering
- Rich auto-mode context banners (commits, uncommitted stats, focus area)
- Rebuild count + delta tracking between runs
- Periodic compact status refresh every 60s
- Segfault recovery (Rspack) with cache clearing + retry

Key adaptation: system-course rebuilds a Docusaurus static site (migration → build → inject → serve). We just kill + relaunch a Flask process — much simpler, same UX pattern.

---

## 9. Resolved Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Wrapper location | **`manage.sh`** | Already handles `web` command. `--auto` is just a flag. Separate script = unnecessary fragmentation. |
| 2 | History management scope | **Both: orphan reset + `git-filter-repo`** | Two different operations for two different use cases. Orphan reset = "nuke all history, start fresh" — for clean slates. `git-filter-repo` = "scrub specific files/paths from every commit" — for removing accidentally committed secrets, large binaries, sensitive data. Both are core DevOps operations. `git-filter-repo` is installed via the project's own tool install system: recipe in `core/system.py` using `_PIP + ['install', 'git-filter-repo']` (same pattern as `jc`, `supervisor`). UI checks availability; shows "Install" button if missing, which calls `/api/tools/install` — same flow as all other tool installs in the audit system. |
| 3 | Remote management | **All remotes** | `gh_repo.py` already has generic functions for any remote name. No reason to artificially restrict to `origin`. |
| 4 | Auto-mode trigger | **Spacebar only** | The point of `--auto` is developer-controlled restarts. Auto-restart = `use_reloader` (deliberately disabled). File watcher shows notifications, doesn't auto-restart. |
