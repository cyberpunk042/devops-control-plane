# Git Operations UI — Implementation Plan

> **Status:** Implemented — all 5 phases complete
> **Created:** 2026-03-03
> **Implemented:** 2026-03-03
> **Scope:** Backend git ops, commit modal overhaul, sync/push/pull flows,
>            dashboard "Integration Status" with quick actions

---

## 0. Current State — Full Trace

### 0.1 Backend: `src/core/services/git/ops.py`

**What exists:**

| Function | What it does | Gap |
|----------|-------------|-----|
| `git_status(root)` | Returns branch, commit, dirty, staged/modified/untracked arrays (capped 20), ahead/behind, last_commit, remote_url | No diff content per file |
| `git_log(root, n)` | Returns recent commits (hash, short_hash, message, author, date) | No body/description |
| `git_commit(root, message, files)` | Stages files (or all), commits | Works fine |
| `git_pull(root, rebase)` | `git pull [--rebase]` | No conflict detection, no stash integration |
| `git_push(root, force)` | `git push [--force-with-lease]`, auto-set-upstream | No dirty check |
| `run_git(*args, cwd)` | Low-level subprocess runner | Foundation for new ops |

**What's missing:**

| Function needed | Purpose |
|----------------|---------|
| `git_diff(root)` | Per-file diff output for the commit modal preview |
| `git_diff_file(root, path)` | Single file diff (for expandable view) |
| `git_stash(root, message)` | `git stash push -m <msg>` |
| `git_stash_pop(root)` | `git stash pop` |
| `git_stash_list(root)` | `git stash list` |
| `git_merge_status(root)` | Detect merge/rebase conflicts, list conflicted files |
| `git_merge_abort(root)` | `git merge --abort` |
| `git_checkout_file(root, path, theirs/ours)` | Resolve single file conflict |

### 0.2 Routes: `src/ui/web/routes/integrations/git.py`

**What exists:**

| Route | Method | Handler |
|-------|--------|---------|
| `/git/status` | GET | `git_status()` |
| `/git/log` | GET | `git_log()` |
| `/git/commit` | POST | `git_commit()` |
| `/git/pull` | POST | `git_pull()` |
| `/git/push` | POST | `git_push()` |
| `/ledger/resolve-conflict` | POST | `ledger_resolve_conflict()` |
| `/ledger/sync-status` | GET | `ledger_sync_status()` |

**What's missing:**

| Route | Method | Purpose |
|-------|--------|---------|
| `/git/diff` | GET | Full diff summary (stat + per-file) |
| `/git/diff/file` | GET | Single file diff content |
| `/git/stash` | POST | Stash working changes |
| `/git/stash/pop` | POST | Pop latest stash |
| `/git/stash/list` | GET | List stash entries |
| `/git/merge-status` | GET | Conflict state + conflicted files |
| `/git/merge/abort` | POST | Abort merge/rebase in progress |
| `/git/checkout-file` | POST | Resolve single file (ours/theirs) |

### 0.3 Frontend: `src/ui/web/templates/scripts/integrations/_git.html`

**What exists:**

- `loadGitCard()` — renders status grid, changes summary, last commit, actions toolbar
- `gitCommitModal()` — opens a **minimal** modal with ONE text input for commit message
- `doGitCommit()` — calls `/git/commit` POST with message, toasts result
- `gitPull()` — fire-and-forget with toast
- `gitPush()` — fire-and-forget with toast
- `gitLogModal()` — shows recent commits in a data table

**What's wrong:**

1. **Commit modal** has no file list, no diff preview, no conventional commits guidance
2. **Push** fires without checking for uncommitted changes
3. **Pull** fires without checking for dirty state, no stash option
4. **No sync flow** that orchestrates commit → push
5. **No conflict resolution UI**

### 0.4 Dashboard: `_tab_dashboard.html` + `_dashboard.html`

**What exists:**

- "🚀 Integration Progress" card with `loadSetupProgress()`
- Renders integration rows (git, docker, github, cicd, k8s, terraform, pages, dns)
- Each row: status icon (✅ 🔶 ⬜) + icon + label + status text + "Set up →" button
- Progress bar at top showing % complete

**What needs to change:**

- Rename "Integration Progress" → "Integration Status"
- Each integration row gains a **quick actions slot** on the right
- Git row: branch name, dirty/clean, ⬆️ Push / ⬇️ Pull / 🔄 Sync
- GitHub row: PR badge, last run status
- Ready integrations show **operational info**, not just "Ready" ✅

---

## 1. Phase 1 — Backend: New Git Operations

### 1.1 `git/ops.py` — New Functions

#### 1.1.1 `git_diff(project_root)` — Diff Summary

Returns a list of changed files with their diff stat and status.

```python
def git_diff(project_root: Path) -> dict:
    """Per-file diff summary for staged + unstaged changes.

    Returns:
        {
            "files": [
                {
                    "path": "src/foo.py",
                    "status": "M",          # M=modified, A=added, D=deleted, ?=untracked, R=renamed
                    "staged": True,         # in index
                    "insertions": 12,
                    "deletions": 3,
                },
                ...
            ],
            "total_insertions": ...,
            "total_deletions": ...,
        }
    """
```

**Implementation approach:**

1. Run `git diff --cached --numstat` for staged files
2. Run `git diff --numstat` for unstaged modified files
3. Run `git status --porcelain` for untracked files
4. Merge into unified list, marking each file as staged/unstaged
5. For renamed files, parse the `R` status to show old → new path

#### 1.1.2 `git_diff_file(project_root, path, staged=False)` — Single File Diff

```python
def git_diff_file(project_root: Path, path: str, *, staged: bool = False) -> dict:
    """Full diff content for a single file.

    Returns:
        {
            "path": "src/foo.py",
            "diff": "--- a/src/foo.py\n+++ b/src/foo.py\n@@ ...",
            "is_binary": False,
            "is_new": False,
        }
    """
```

**Implementation:**

- `git diff --cached -- <path>` if staged
- `git diff -- <path>` if unstaged
- For untracked files: read file content and format as "new file" diff
- Detect binary with `git diff --numstat` (binary shows `-` for insertions/deletions)

#### 1.1.3 `git_stash(project_root, message)` — Stash

```python
def git_stash(project_root: Path, message: str | None = None) -> dict:
    """Stash working directory changes.

    Returns:
        {"ok": True, "ref": "stash@{0}", "message": "..."}
        or {"error": "Nothing to stash"} if worktree is clean.
    """
```

#### 1.1.4 `git_stash_pop(project_root)` — Pop Stash

```python
def git_stash_pop(project_root: Path) -> dict:
    """Pop the most recent stash.

    Returns:
        {"ok": True}
        or {"error": "...", "conflicts": True} if pop causes conflicts.
    """
```

#### 1.1.5 `git_stash_list(project_root)` — List Stashes

```python
def git_stash_list(project_root: Path) -> dict:
    """List stash entries.

    Returns:
        {"stashes": [{"ref": "stash@{0}", "message": "...", "date": "..."}]}
    """
```

#### 1.1.6 `git_merge_status(project_root)` — Conflict Detection

```python
def git_merge_status(project_root: Path) -> dict:
    """Detect ongoing merge/rebase and list conflicted files.

    Returns:
        {
            "in_progress": True/False,
            "type": "merge" | "rebase" | None,
            "conflicted_files": ["src/foo.py", ...],
            "ours_branch": "main",
            "theirs_branch": "origin/main",
        }
    """
```

**Implementation:**

- Check `.git/MERGE_HEAD` exists → merge in progress
- Check `.git/rebase-merge/` or `.git/rebase-apply/` → rebase in progress
- Run `git diff --name-only --diff-filter=U` for conflicted files

#### 1.1.7 `git_merge_abort(project_root)` — Abort Merge

```python
def git_merge_abort(project_root: Path) -> dict:
    """Abort a merge or rebase in progress.

    Returns {"ok": True} or {"error": "..."}.
    """
```

#### 1.1.8 `git_checkout_file(project_root, path, strategy)` — Resolve File

```python
def git_checkout_file(
    project_root: Path, path: str, strategy: str
) -> dict:
    """Resolve a single conflicted file.

    Args:
        strategy: "ours" | "theirs"

    Returns {"ok": True} or {"error": "..."}.
    """
```

### 1.2 Routes: `integrations/git.py` — New Endpoints

```python
@integrations_bp.route("/git/diff")
def git_diff_route():
    """Per-file diff summary."""
    return jsonify(git_ops.git_diff(_project_root()))


@integrations_bp.route("/git/diff/file")
def git_diff_file_route():
    """Single file diff content."""
    path = request.args.get("path", "")
    staged = request.args.get("staged", "") == "1"
    if not path:
        return jsonify({"error": "path is required"}), 400
    return jsonify(git_ops.git_diff_file(_project_root(), path, staged=staged))


@integrations_bp.route("/git/stash", methods=["POST"])
@requires_git_auth
@run_tracked("git", "git:stash")
def git_stash_route():
    """Stash working directory changes."""
    data = request.get_json(silent=True) or {}
    message = data.get("message")
    result = git_ops.git_stash(_project_root(), message=message)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/stash/pop", methods=["POST"])
@requires_git_auth
@run_tracked("git", "git:stash-pop")
def git_stash_pop_route():
    """Pop the most recent stash."""
    result = git_ops.git_stash_pop(_project_root())
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/stash/list")
def git_stash_list_route():
    """List stash entries."""
    return jsonify(git_ops.git_stash_list(_project_root()))


@integrations_bp.route("/git/merge-status")
def git_merge_status_route():
    """Detect merge/rebase in progress."""
    return jsonify(git_ops.git_merge_status(_project_root()))


@integrations_bp.route("/git/merge/abort", methods=["POST"])
@run_tracked("git", "git:merge-abort")
def git_merge_abort_route():
    """Abort merge/rebase in progress."""
    result = git_ops.git_merge_abort(_project_root())
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/git/checkout-file", methods=["POST"])
@run_tracked("git", "git:checkout-file")
def git_checkout_file_route():
    """Resolve a single conflicted file."""
    data = request.get_json(silent=True) or {}
    path = data.get("path", "").strip()
    strategy = data.get("strategy", "").strip()
    if not path or strategy not in ("ours", "theirs"):
        return jsonify({"error": "path and strategy (ours|theirs) required"}), 400
    result = git_ops.git_checkout_file(_project_root(), path, strategy)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)
```

### 1.3 Backward Compatibility Shim

Add to `src/core/services/git_ops.py` (the shim file):
```python
from src.core.services.git.ops import (  # noqa: F401
    git_diff,
    git_diff_file,
    git_stash,
    git_stash_pop,
    git_stash_list,
    git_merge_status,
    git_merge_abort,
    git_checkout_file,
)
```

---

## 2. Phase 2 — Commit Modal Overhaul

### 2.1 Current Flow (what's broken)

```
gitCommitModal()
    → modalOpen({ title, body: text_input, footerButtons })
    → doGitCommit()
        → api('/git/commit', { message })
        → toast + reload card
```

**Problems:**
- No file list — user has no idea what they're committing
- No diff preview — can't review changes
- No conventional commits guidance
- No selective staging — always commits ALL

### 2.2 New Flow

```
gitCommitModal()
    1. Open wide modal with loading spinner
    2. Fetch /git/diff → get file list with stats
    3. Render two-panel layout:
       Left panel: File tree with checkboxes + change counts
       Right panel: Commit message area + conventional commits help
    4. Click a file → fetch /git/diff/file → show inline diff below file tree

doGitCommit()
    1. Collect checked files (or "all" if none unchecked)
    2. Validate commit message format
    3. POST /git/commit with { message, files }
    4. Toast + reload card
```

### 2.3 Modal Layout

```
┌──────────────────────────────────────────────────────────────┐
│  💾 Commit Changes                                    [Close]│
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─ Changed Files ───────────────────────────────────────┐   │
│  │ ☑ What to commit:  [All]  [Staged only]  [None]       │   │
│  │                                                        │   │
│  │  STAGED (3)                                            │   │
│  │  ☑ 🟢 src/ui/web/static/css/admin.css    +42  -3      │   │
│  │  ☑ 🟢 src/ui/web/templates/_nav.html      +8  -4      │   │
│  │  ☑ 🟢 src/ui/web/templates/_tabs.html    +22  -1      │   │
│  │                                                        │   │
│  │  MODIFIED (2)                                          │   │
│  │  ☑ 🟡 src/core/services/git/ops.py       +15  -0      │   │
│  │  ☑ 🟡 README.md                           +3  -1      │   │
│  │                                                        │   │
│  │  UNTRACKED (1)                                         │   │
│  │  ☑ ⬜ src/new_file.py                    +45  -0      │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─ Diff Preview (click a file above) ───────────────────┐   │
│  │  admin.css — 42 insertions, 3 deletions               │   │
│  │  ─────────────────────────────────────────────────     │   │
│  │  @@ -1196,6 +1196,48 @@                              │   │
│  │   .nav-controls {                                      │   │
│  │  +    /* Mobile tab menu elements */                   │   │
│  │  +    .tabs-menu-chevron { ... }                       │   │
│  │   }                                                   │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─ Commit Message ──────────────────────────────────────┐   │
│  │  Type: [feat ▾]  Scope: [ optional scope ]            │   │
│  │  ┌──────────────────────────────────────────────────┐  │   │
│  │  │ feat(ui): add mobile navigation menu             │  │   │
│  │  └──────────────────────────────────────────────────┘  │   │
│  │  💡 Following Conventional Commits                     │   │
│  │     format: <type>(<scope>): <description>             │   │
│  │     Learn more → conventionalcommits.org               │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  3 staged, 2 modified, 1 untracked        [Cancel] [Commit] │
└──────────────────────────────────────────────────────────────┘
```

### 2.4 Conventional Commits Component

**Type prefix dropdown** with descriptions:

| Type | Label | Description |
|------|-------|-------------|
| `feat` | Feature | A new feature |
| `fix` | Bug Fix | A bug fix |
| `docs` | Documentation | Documentation only changes |
| `style` | Style | Formatting, semicolons, etc |
| `refactor` | Refactor | Neither fixes nor adds features |
| `test` | Tests | Adding or correcting tests |
| `chore` | Chore | Maintenance tasks |
| `ci` | CI | CI/CD configuration changes |
| `build` | Build | Build system or dependencies |
| `perf` | Performance | Performance improvements |

**Auto-format behavior:**
- When type dropdown changes → update the message input prefix
- When scope is filled → insert `(<scope>)` into message
- Example: type=`feat`, scope=`ui`, description=`add mobile nav`
  → message = `feat(ui): add mobile nav`
- Link text: "Following [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) format"

### 2.5 Diff Viewer Component

**Requirements:**
- Rendered as syntax-highlighted `<pre>` block
- Lines starting with `+` colored green
- Lines starting with `-` colored red
- `@@` hunk headers colored blue/purple
- Max height with scroll
- File header showing path + stat (+N, -N)

**CSS classes:**
```css
.git-diff-viewer { ... }
.git-diff-line { ... }
.git-diff-line.addition { color: var(--success); background: hsla(142, 76%, 36%, 0.08); }
.git-diff-line.deletion { color: var(--error); background: hsla(0, 84%, 60%, 0.08); }
.git-diff-line.hunk { color: var(--accent); font-weight: 600; }
.git-diff-line.context { color: var(--text-muted); }
```

---

## 3. Phase 3 — Sync / Push / Pull Intelligence

### 3.1 Sync Flow

**Trigger:** New "🔄 Sync" button in Git card + Dashboard Git row

```
gitSync()
    1. Fetch /git/status
    2. If dirty:
       a. Open commit modal (Phase 2 version)
       b. Wait for commit completion (callback)
       c. Continue to step 3
    3. Fetch /git/status again (fresh after commit)
    4. If behind > 0:
       a. Pull first (toast "Pulling...")
       b. If pull conflicts → show conflict resolution UI (Phase 4)
       c. If pull ok → continue
    5. If ahead > 0:
       a. Push (toast "Pushing...")
    6. Toast "Synced! ✅"
    7. Reload git card
```

### 3.2 Smart Push

**Trigger:** Existing "⬆️ Push" button

```
gitPush()  (enhanced)
    1. Fetch /git/status
    2. If dirty:
       a. Confirm dialog: "You have uncommitted changes. Commit first?"
       b. If yes → open commit modal with callback → then push
       c. If no → just push what's committed
    3. If ahead === 0:
       a. Toast "Nothing to push — already up to date"
       b. Return
    4. Push (with SSH auth gate via ensureGitAuth)
    5. Toast result + reload card
```

### 3.3 Smart Pull

**Trigger:** Existing "⬇️ Pull" button

```
gitPull()  (enhanced)
    1. Fetch /git/status
    2. If dirty:
       a. Confirm dialog: "You have local changes. Stash them before pulling?"
       b. If yes:
          i. POST /git/stash
          ii. Toast "Changes stashed"
          iii. Set _pullStashed = true
       c. If no:
          i. Warn "Pull may fail or create conflicts"
          ii. Continue anyway
    3. POST /git/pull (with ensureGitAuth)
    4. If pull returns error with conflict indicators:
       a. Show merge conflict UI (Phase 4)
       b. Return
    5. If _pullStashed:
       a. POST /git/stash/pop
       b. If stash pop conflicts:
          i. Toast "Stash pop had conflicts — resolve manually"
          ii. Show conflict UI
       c. Else: toast "Changes restored from stash"
    6. Toast "Pull complete" + reload card
```

---

## 4. Phase 4 — Merge Conflict Resolution UI

### 4.1 Trigger

Conflict UI activates when:
- `gitPull()` returns an error containing "conflict" or "CONFLICT"
- `git_stash_pop()` returns `{"error": "...", "conflicts": True}`
- Or: user visits integrations tab while `.git/MERGE_HEAD` exists

### 4.2 Conflict Modal Layout

```
┌──────────────────────────────────────────────────────────────┐
│  ⚠️ Merge Conflicts                                   [Close]│
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Merging: origin/main → main                                 │
│  X conflicted files need resolution                          │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  ⚠️ src/core/services/git/ops.py                       │   │
│  │     [Accept Ours] [Accept Theirs] [View Diff]           │   │
│  │                                                         │   │
│  │  ⚠️ src/ui/web/static/css/admin.css                     │   │
│  │     [Accept Ours] [Accept Theirs] [View Diff]           │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  [Abort Merge]                              [Mark Resolved]  │
└──────────────────────────────────────────────────────────────┘
```

### 4.3 Resolution Actions

| Action | API call | Effect |
|--------|----------|--------|
| Accept Ours | `POST /git/checkout-file {path, strategy: "ours"}` | Keep local version |
| Accept Theirs | `POST /git/checkout-file {path, strategy: "theirs"}` | Accept remote version |
| View Diff | `GET /git/diff/file?path=...&staged=0` | Show three-way diff preview |
| Abort Merge | `POST /git/merge/abort` | Cancel the entire merge/rebase |
| Mark Resolved | `POST /git/commit {message: "Merge ..."}` | Commit the resolution |

---

## 5. Phase 5 — Dashboard "Integration Status" with Quick Actions

### 5.1 Rename

- HTML: "🚀 Integration Progress" → "🚀 Integration Status"
- JS: Update comment `// ── 3. Integration Progress` → `// ── 2. Integration Status`
- Internal label in progress bar: "Integration progress" → "Integration status"

### 5.2 Integration Row Structure (new)

Each integration row changes from:

```
[status_icon] [int_icon] [label]  [status_text] [Setup button if not ready]
```

To:

```
[status_icon] [int_icon] [label]  [live_info]  [quick_actions]  [status_text]
```

Where `live_info` and `quick_actions` depend on the integration type and state.

### 5.3 Git Row — Live Info + Quick Actions

**When status = "ready":**
```
✅ 🔀 Git   main · Clean              [🔄 Sync]  [⬆️ 2]  Ready
✅ 🔀 Git   main · 3 changes          [💾] [🔄 Sync]  3 changes
✅ 🔀 Git   main · ↓2 behind          [⬇️ Pull]  Behind
```

**Implementation:**
- On `loadSetupProgress()`, when building the Git row:
  - Fetch git status from cache (`cardCached('git')`) — already loaded by Integrations tab
  - If cached data available → render live branch/dirty/ahead/behind info + action buttons
  - If not cached → just show the standard row (don't block dashboard load)

**Quick action buttons:**
| Condition | Buttons |
|-----------|---------|
| Clean + ahead > 0 | `⬆️ Push (N)` |
| Clean + behind > 0 | `⬇️ Pull` |
| Dirty | `💾 Commit` → opens commit modal |
| Any state | `🔄 Sync` |

### 5.4 GitHub Row — Live Info

**When status = "ready":**
```
✅ 🐙 GitHub   cyberpunk042/devops-control-plane   [↗]  Ready
```

- Show repo slug from cached GitHub data
- Link icon → opens repo in new tab

### 5.5 Other integration rows stay as-is

Docker, CI/CD, K8s, Terraform, Pages, DNS — no quick actions for now.
They keep their current behavior: status icon + "Set up →" if not ready.

### 5.6 Data Flow

```
loadSetupProgress()
    1. Fetch /project/status (or use cache) — same as before
    2. For git row specifically:
       a. Check cardCached('git') — already loaded if user visited Integrations
       b. If not cached: fire a background fetch and update the row when ready
    3. Render integration rows with action slots
    4. Git row includes inline action buttons that call gitSync(), gitPush(), etc.
```

---

## 6. File Change Inventory

### Phase 1 — Backend

| File | Action | What |
|------|--------|------|
| `src/core/services/git/ops.py` | ADD | `git_diff`, `git_diff_file`, `git_stash`, `git_stash_pop`, `git_stash_list`, `git_merge_status`, `git_merge_abort`, `git_checkout_file` |
| `src/core/services/git_ops.py` | MODIFY | Add new imports to backward compat shim |
| `src/ui/web/routes/integrations/git.py` | MODIFY | Add 8 new route handlers |

### Phase 2 — Commit Modal

| File | Action | What |
|------|--------|------|
| `src/ui/web/templates/scripts/integrations/_git.html` | REWRITE `gitCommitModal()` + `doGitCommit()` | Two-panel modal with file list, diff viewer, conventional commits |
| `src/ui/web/static/css/admin.css` | ADD | Diff viewer CSS, commit modal file list CSS, conventional commits helper CSS |

### Phase 3 — Sync / Push / Pull

| File | Action | What |
|------|--------|------|
| `src/ui/web/templates/scripts/integrations/_git.html` | REWRITE `gitPull()`, `gitPush()` | Add pre-checks, stash flow, commit-first flow |
| `src/ui/web/templates/scripts/integrations/_git.html` | ADD | New `gitSync()` function |

### Phase 4 — Conflict Resolution

| File | Action | What |
|------|--------|------|
| `src/ui/web/templates/scripts/integrations/_git.html` | ADD | `gitConflictModal()`, `doResolveFile()`, `doAbortMerge()` |
| `src/ui/web/static/css/admin.css` | ADD | Conflict modal CSS |

### Phase 5 — Dashboard Integration Status

| File | Action | What |
|------|--------|------|
| `src/ui/web/templates/partials/_tab_dashboard.html` | MODIFY | Rename "Integration Progress" → "Integration Status" |
| `src/ui/web/templates/scripts/_dashboard.html` | MODIFY | Rewrite `loadSetupProgress()` — add live info + action buttons for git row |

---

## 7. Execution Order

**Must be sequential — each phase depends on the previous:**

```
Phase 1 (Backend)
    └─→ Phase 2 (Commit Modal)  ← needs /git/diff, /git/diff/file
           └─→ Phase 3 (Sync/Push/Pull)  ← needs commit modal as building block
                  └─→ Phase 4 (Conflict Resolution)  ← needs /git/merge-status, etc.
                  └─→ Phase 5 (Dashboard)  ← needs gitSync/gitPush/gitPull functions
```

Phase 4 and Phase 5 can happen in parallel after Phase 3.

---

## 8. Edge Cases

| Case | Handling |
|------|----------|
| Very large diff (>1000 lines) | Truncate to 500 lines with "showing first 500 lines" notice |
| Binary file changed | Show "binary file — cannot display diff" instead of diff content |
| No remote configured | Sync/Push/Pull disabled with "No remote" tooltip |
| SSH auth required | Use existing `ensureGitAuth()` gate before push/pull/sync |
| Detached HEAD | Show commit hash instead of branch name, disable push |
| Empty commit message | Validate before sending — disable Commit button until message exists |
| Stash pop conflicts | Show conflict UI same as merge conflicts |
| Merge already in progress | Auto-show conflict modal when opening git card |
| User unchecks all files | Disable commit button, show "select at least one file" |
| Untracked file diff | Show entire file content as additions (all green) |
| Commit during rebase | Block with message "resolve rebase first" |

---

## 9. Testing Plan

### 9.1 Backend API Tests

```bash
# Diff summary
curl http://localhost:8000/api/git/diff
# Expected: {"files": [{path, status, staged, insertions, deletions}...]}

# Single file diff
curl 'http://localhost:8000/api/git/diff/file?path=src/foo.py&staged=0'
# Expected: {"path": "...", "diff": "...", "is_binary": false}

# Stash
curl -X POST http://localhost:8000/api/git/stash -d '{"message": "test"}'
# Expected: {"ok": true, "ref": "stash@{0}"}

# Stash list
curl http://localhost:8000/api/git/stash/list
# Expected: {"stashes": [{"ref": "...", "message": "...", "date": "..."}]}

# Stash pop
curl -X POST http://localhost:8000/api/git/stash/pop
# Expected: {"ok": true}

# Merge status (when no conflict exists)
curl http://localhost:8000/api/git/merge-status
# Expected: {"in_progress": false, "type": null, "conflicted_files": []}
```

### 9.2 Frontend UI Tests

```
1. Edit 3 files → open commit modal
   - See 3 files listed with +/- stats
   - Click a file → see diff preview expand
   - Select "feat" type, type scope "ui" → message formats correctly
   - Click Commit → modal closes, card updates

2. Dirty state → click Sync
   - Commit modal opens first
   - After commit → auto-pushes
   - Card refreshes to show "Clean"

3. Behind remote → click Pull with dirty state
   - "Stash changes?" dialog appears
   - Yes → stash → pull → pop stash
   - Card refreshes

4. Merge conflict during pull
   - Conflict modal appears
   - Click "Accept Theirs" on one file
   - Click "Accept Ours" on another
   - Click "Mark Resolved"
   - Merge completes

5. Dashboard Git row
   - Shows branch + dirty count
   - Click Sync → full flow executes
   - Row updates after completion
```

---

## 10. Definition of Done

### Phase 1
- [x] All 8 new backend functions implemented in `git/ops.py`
- [x] All 8 new routes registered in `integrations/git.py`
- [x] Backward compat shim updated
- [ ] All curl tests pass

### Phase 2
- [x] Commit modal shows file list with checkboxes + diff stats
- [x] Click file → expandable diff viewer
- [x] Conventional commits: type dropdown, optional scope, auto-format message
- [x] Link to conventionalcommits.org visible
- [x] Selective file commit works (pass `files` array)
- [x] Diff viewer has syntax-colored +/- lines

### Phase 3
- [x] `gitSync()` orchestrates dirty check → commit → pull → push
- [x] `gitPush()` warns about uncommitted changes
- [x] `gitPull()` offers stash when dirty
- [x] Stash pop happens automatically after pull
- [x] All flows show progress toasts

### Phase 4
- [x] Conflict modal shows conflicted file list
- [x] Accept Ours / Accept Theirs resolves individual files
- [x] Abort Merge cancels the operation
- [x] View Diff shows file diff
- [x] After resolving all files → commit resolution

### Phase 5
- [x] Dashboard card renamed "Integration Status"
- [x] Git row shows branch + dirty/clean + quick action buttons
- [x] Sync/Push/Pull buttons work directly from dashboard
- [x] Other integration rows unchanged
