# Chunk 9: Test Suites & Execution Plans → Git (Ledger)

> **Status**: Planning — Solution analysis
> **Created**: 2026-03-10
> **Parent**: `scripts-system.md` — cross-cutting infrastructure
> **Depends on**: Ledger infrastructure (exists ✅), CDP test storage (exists ✅), Plan storage (exists ✅)

---

## 0. The User's Words (Verbatim)

> "I should be able to add tests to git, to the ledge / published / shared."

> "Same for exec plan.."

> "We will need to follow the standard pattern using the .ledge folder
> moving the data from .state to .ledge appropriatelly and adapting the
> infirastructue through and through."

> "a tests you dont share you Add to Git or Remove From Git"

> "this is a test not a trace, there is a nuance in the logic and UX"

> "when we update tests script or execution plan we will need to actually
> say when its outdated to update the Git version because the ledge is not
> the same branch so we need to manage it via the UI intuitively. The user
> will then be able to trigger the new commit and sync to the ledge."

---

## 1. Why This Is Different From Trace Sharing

Traces and tests are fundamentally different artifacts. The ledger pattern
is the same infrastructure, but the semantics, lifecycle, and UX diverge.

### Trace: An Observation

A trace is an **immutable recording** of something that happened. You
record it, it's done, you share it so others can see what happened. It's
a historical artifact. Nobody edits a trace after recording.

- **Share** = "let others see this recording"
- **Unshare** = "hide this from others"
- **The data doesn't change** after creation
- **Primary use case**: visibility, debugging, forensics

### Test Suite: A Living Artifact

A test suite is a **reusable, editable, executable specification**. It's
code. It evolves. Multiple people use it. CI runs it. When you "add it
to git" you're version-controlling a piece of your test infrastructure.

- **Add to Git** = "this test is part of the project now, version-control it"
- **Remove from Git** = "pull this back to local-only, it's not ready / not needed"
- **The data CHANGES** — steps are edited, assertions refined, variables added
- **Primary use case**: collaboration, CI/CD, reproducibility, shared standards
- **Edits happen locally** — the user syncs to git when ready
- **The UI shows when the git version is outdated** compared to local edits

### Execution Plan: Same as Test Suite

An execution plan composes test suites and scripts into a workflow. Same
semantics as test suites — it's a living artifact that belongs in version
control when it's ready.

### Key Differences in Behavior

| Aspect | Trace (share/unshare) | Test/Plan (add to git / remove from git) |
|--------|----------------------|------------------------------------------|
| **Terminology** | "Share" / "Unshare" | "Add to Git" / "Remove from Git" |
| **Mutability** | Immutable after recording | Editable at any time |
| **After adding to git** | Data never changes | Edits stay local until user syncs |
| **Source of truth** | Whichever copy has `shared=True` | `.state/` = working copy, `.ledger/` = committed version |
| **Edit flow** | N/A | Edit → save to `.state/` → UI shows "outdated" → user triggers Sync to Git |
| **Dirty detection** | N/A | Compare `updated_at` (local) vs `git_updated_at` (last committed) |
| **CI/CD relevance** | Archive/history | Active — CI pulls ledger and runs the committed version |
| **Mental model** | "Others can see this" | "This is in version control — I commit when ready" |

---

## 2. Current State Audit — Every Layer

### 2.1 Test Suite Storage (`storage.py`)

**File**: `src/core/services/cdp_test/storage.py` (181 lines)

| Function | What it does | Where it writes |
|----------|-------------|-----------------|
| `_suites_dir()` | Returns `.state/cdp-tests/suites/` | `.state/` only |
| `list_suites()` | Scans `.state/cdp-tests/suites/*.json` | Reads `.state/` only |
| `get_suite()` | Reads `.state/cdp-tests/suites/<id>.json` | Reads `.state/` only |
| `save_suite()` | Writes to `.state/cdp-tests/suites/<id>.json` | Writes `.state/` only |
| `delete_suite()` | Deletes `.state/cdp-tests/suites/<id>.json` | Deletes from `.state/` only |

**Gap**: No `.ledger/` awareness. No `shared`/`in_git` field. No merge logic.

### 2.2 Test Suite Model (`models.py`)

**File**: `src/core/services/cdp_test/models.py` (686 lines)

`TestSuite` dataclass has NO field for git status. No `in_git`, no `shared`,
nothing. It doesn't know whether it's local-only or in version control.

**Gap**: Need a field to track git status.

### 2.3 Execution Plan Storage (`plan_storage.py`)

**File**: `src/core/services/scripts/plan_storage.py` (186 lines)

| Function | What it does | Where it writes |
|----------|-------------|-----------------|
| `_plans_dir()` | Returns `.state/cdp-plans/plans/` | `.state/` only |
| `list_plans()` | Scans `.state/cdp-plans/plans/*.json` | Reads `.state/` only |
| `get_plan()` | Reads `.state/cdp-plans/plans/<id>.json` | Reads `.state/` only |
| `save_plan()` | Writes to `.state/cdp-plans/plans/<id>.json` | Writes `.state/` only |
| `delete_plan()` | Deletes `.state/cdp-plans/plans/<id>.json` | Deletes from `.state/` only |

**Gap**: Same as suites — no ledger awareness.

### 2.4 Execution Plan Model (`plans.py`)

**File**: `src/core/services/scripts/plans.py` (419 lines)

`ExecutionPlan` dataclass has NO field for git status.

**Gap**: Same as suites.

### 2.5 Suite Routes (`suites.py`)

**File**: `src/ui/web/routes/cdp_test/suites.py` (254 lines)

Standard CRUD. No share/add-to-git endpoints. All ops go through `storage.py`
which only touches `.state/`.

**Gap**: Need "add to git" / "remove from git" endpoints. Save operations for
in-git suites need to commit to ledger.

### 2.6 Plan Routes (`crud.py`)

**File**: `src/ui/web/routes/plans/crud.py` (178 lines)

Standard CRUD. Same gaps as suites.

### 2.7 Frontend — Suites UI (`_cdp_test.html`)

The suite list shows suites from the API. No git status indicator. No
"Add to Git" button. No visual distinction between local and git suites.

**Gap**: Git status badge, action buttons, visual treatment.

### 2.8 Frontend — Plans UI (`_plans.html`)

Same as suites frontend. No git awareness.

### 2.9 Ledger Infrastructure (EXISTS ✅)

**Files**:
- `src/core/services/ledger/worktree.py` (1161 lines) — full git plumbing
- `src/core/services/ledger/ledger_ops.py` (259 lines) — business logic
- `src/core/services/ledger/__init__.py` — public API

The infrastructure supports: `ensure_worktree()`, `ledger_add_and_commit()`,
`push_ledger_branch()`, `pull_ledger_branch()`, `_safe_rebase()`.

**No gap**: This is ready. We use it as-is.

### 2.10 Established Pattern (Traces)

**File**: `src/core/services/trace/trace_recorder.py` (721 lines)

The trace system proves the pattern works:
- `save_trace()` → `.state/traces/<id>/`
- `share_trace()` → copies to `.ledger/traces/<id>/`, commits
- `unshare_trace()` → flips flag, commits
- `list_traces()` → merges both directories, ledger authoritative
- `get_trace()` → checks ledger first, then local
- `delete_trace()` → hidden list so deleted traces don't reappear on pull
- Background push via `threading.Thread(target=push_ledger_branch, ...)`

**We follow the same infrastructure pattern** but with the semantic
differences described in §1.

---

## 3. Data Model Changes

### 3.1 TestSuite — Add `in_git` + `git_updated_at` Fields

```python
# In TestSuite dataclass (models.py)
in_git: bool = False                # True = has a version in the ledger branch
git_updated_at: str = ""            # ISO timestamp of the LAST commit to ledger
                                    # When updated_at > git_updated_at, the git
                                    # version is outdated and the UI shows it
```

Why `in_git` and not `shared`:
- The user literally said "Add to Git" not "Share"
- It's a test. It's code. You put code in git.
- `shared` implies social. `in_git` implies version control.

Why `git_updated_at`:
- This tracks WHEN the suite was last synced to the ledger.
- The local `updated_at` advances on every save.
- When `updated_at > git_updated_at`, the local copy has uncommitted changes.
- The UI uses this to show "outdated" and offer a "Sync to Git" button.
- When the user triggers sync, `git_updated_at` is set to `updated_at`.

This field is persisted in the JSON. **Edits always go to `.state/` only.**
The `.ledger/` copy is only updated when the user explicitly triggers a
sync. This gives the user control over when their changes become visible
to others — real version control semantics.

### 3.2 ExecutionPlan — Add `in_git` + `git_updated_at` Fields

```python
# In ExecutionPlan dataclass (plans.py)
in_git: bool = False                # True = has a version in the ledger branch
git_updated_at: str = ""            # ISO timestamp of the LAST commit to ledger
```

Same semantics as TestSuite.

### 3.3 TestRunResult / PlanRunResult — NO Change

Run results are **ephemeral local artifacts**. They record what happened
on THIS machine. They don't go to git. They stay in `.state/`.

If a team wants shared test results, that's a different feature (test
reporting / CI dashboard) — not this scope.

---

## 4. Storage Layer Changes

### 4.1 Ledger Paths

Following the established structure inside `.ledger/`:

```
.ledger/
    audits/                    # ← existing (audit snapshots)
    traces/                    # ← existing (shared traces)
    chat/                      # ← existing (chat threads)
    cdp-tests/                 # ← NEW
        suites/
            <suite-id>.json    # TestSuite JSON (same format as .state)
    cdp-plans/                 # ← NEW
        plans/
            <plan-id>.json     # ExecutionPlan JSON (same format as .state)
```

The directory names mirror `.state/` paths for consistency.

### 4.2 New Functions — Suite Git Ops

**File**: `src/core/services/cdp_test/storage.py` (extend existing)

```python
# ── Ledger paths ───────────────────────────────────────────

def _ledger_suites_dir(project_root: Path) -> Path:
    """Return the suites directory in the ledger worktree."""
    return worktree_path(project_root) / "cdp-tests" / "suites"

def _hidden_suites_file(project_root: Path) -> Path:
    """Path to the hidden suites list (.state/cdp-tests/suites_hidden.json)."""
    return project_root / ".state" / "cdp-tests" / "suites_hidden.json"


# ── Add to Git ─────────────────────────────────────────────

def add_suite_to_git(project_root: Path, suite_id: str) -> bool:
    """Add a test suite to git (ledger branch).

    This is the FIRST commit. Takes the current local version and
    commits it to the ledger.

    1. Load suite from local storage (.state/)
    2. Set in_git = True, git_updated_at = updated_at
    3. Write to .ledger/cdp-tests/suites/<id>.json
    4. Update local copy with in_git = True, git_updated_at
    5. Commit to ledger branch

    Returns True if successful, False if suite not found.
    """


# ── Sync to Git ────────────────────────────────────────────

def sync_suite_to_git(project_root: Path, suite_id: str) -> bool:
    """Sync local changes to the ledger (commit updated version).

    Called when the user explicitly triggers "Sync to Git" in the UI
    after editing an in-git suite locally.

    1. Load suite from local storage (.state/)
    2. Verify in_git == True
    3. Set git_updated_at = updated_at
    4. Write to .ledger/cdp-tests/suites/<id>.json
    5. Update local copy with new git_updated_at
    6. Commit to ledger branch

    Returns True if successful, False if not found or not in git.
    """


# ── Remove from Git ────────────────────────────────────────

def remove_suite_from_git(project_root: Path, suite_id: str) -> bool:
    """Remove a test suite from git (ledger branch).

    1. Load suite
    2. Set in_git = False, git_updated_at = ""
    3. Delete from .ledger/cdp-tests/suites/
    4. Update local copy with in_git = False
    5. Commit the deletion to ledger branch

    Returns True if successful, False if not found.
    """
```

### 4.3 Modified Functions — Suite CRUD (Git-Aware)

The existing CRUD functions need to become git-aware.

**CRITICAL DESIGN DECISION**: Edits do NOT auto-commit. The `.state/` copy
is the working copy. The `.ledger/` copy is updated ONLY when the user
explicitly triggers "Add to Git" or "Sync to Git".

**`save_suite()`** — Always writes to `.state/` ONLY:

```
save_suite(project_root, suite):
    # Always and ONLY write to .state (working copy)
    suite.updated_at = now()
    write to .state/cdp-tests/suites/<id>.json

    # NEVER touch .ledger/ here.
    # If suite.in_git and updated_at > git_updated_at,
    # the list API will report git_dirty=True and the
    # UI will show "Sync to Git" button.
```

**`list_suites()`** — Merge both sources, compute dirty status:

```
list_suites(project_root):
    seen = {}
    hidden = load_hidden_suites()

    # 1. Scan LOCAL first (the working copies)
    for file in .state/cdp-tests/suites/*.json:
        data = load(file)
        if data.id not in hidden:
            summary = make_summary(data)
            # Dirty detection: local has changes not yet in git
            if data.in_git and data.updated_at > data.git_updated_at:
                summary["git_dirty"] = True
            else:
                summary["git_dirty"] = False
            seen[data.id] = summary

    # 2. Scan LEDGER (for suites from other machines not yet in .state/)
    ledger_dir = .ledger/cdp-tests/suites/
    if ledger_dir.exists():
        for file in ledger_dir/*.json:
            data = load(file)
            if data.id not in seen and data.id not in hidden:
                summary = make_summary(data)
                summary["git_dirty"] = False  # ledger is the committed version
                seen[data.id] = summary

    return sorted(seen.values(), by updated_at desc)
```

Note: Local first because `.state/` is the working copy. When a suite
exists locally AND in the ledger, the local version is what the user is
working with. The ledger scan only picks up suites added by OTHER machines
that were pulled but don't have a local working copy yet.

**`get_suite()`** — Local first (working copy):

```
get_suite(project_root, suite_id):
    # Local first (user's working copy)
    local_path = .state/cdp-tests/suites/<id>.json
    if local_path.exists():
        return load(local_path)

    # Fall back to ledger (pulled from another machine, no local edit yet)
    ledger_path = .ledger/cdp-tests/suites/<id>.json
    if ledger_path.exists():
        return load(ledger_path)

    return None
```

Note: This is DIFFERENT from traces, where ledger is checked first because
the ledger copy is the authoritative shared state. For tests, `.state/` is
the working copy — the user may have local edits not yet synced to git.
When they GET a suite, they want THEIR latest version.

**`delete_suite()`** — Delete from both, hidden list for synced:

```
delete_suite(project_root, suite_id):
    deleted = False

    # Delete local copy
    if .state/<id>.json exists:
        delete it
        deleted = True

    # Delete ledger copy
    if .ledger/<id>.json exists:
        delete it
        commit deletion
        deleted = True

    # Add to hidden list (prevents reappearing on pull)
    if deleted:
        add to suites_hidden.json

    return deleted
```

### 4.4 New Functions — Plan Git Ops

**File**: `src/core/services/scripts/plan_storage.py` (extend existing)

Exact same pattern as suites:
- `_ledger_plans_dir(project_root)`
- `_hidden_plans_file(project_root)`
- `add_plan_to_git(project_root, plan_id)`
- `sync_plan_to_git(project_root, plan_id)`
- `remove_plan_from_git(project_root, plan_id)`
- Modified `save_plan()` — writes `.state/` ONLY (not ledger)
- Modified `list_plans()` — merge both, compute `git_dirty`
- Modified `get_plan()` — local first (working copy)
- Modified `delete_plan()` — both + hidden list

### 4.5 Run Results — NO Change

`list_results()`, `get_result()`, `save_result()` stay local-only.
They keep reading/writing to `.state/` exclusively.

---

## 5. API Route Changes

### 5.1 Suite Routes — New Endpoints

**File**: `src/ui/web/routes/cdp_test/suites.py`

```
POST /cdp-test/suites/add-to-git
    Body: { "suite_id": "..." }
    → Calls add_suite_to_git()
    → Background push if auth ok
    → Returns { "ok": true, "suite_id": "...", "in_git": true }

POST /cdp-test/suites/sync-to-git
    Body: { "suite_id": "..." }
    → Calls sync_suite_to_git()
    → Background push if auth ok
    → Returns { "ok": true, "suite_id": "...", "in_git": true, "git_dirty": false }

POST /cdp-test/suites/remove-from-git
    Body: { "suite_id": "..." }
    → Calls remove_suite_from_git()
    → Background push if auth ok
    → Returns { "ok": true, "suite_id": "...", "in_git": false }
```

### 5.2 Existing Suite Routes — Behavior Change

The existing routes already call `save_suite()` / `list_suites()` / etc.
from storage.py. Since we're modifying those storage functions:

- `GET /cdp-test/suites` — now returns suites from both sources, each
  with `in_git` and `git_dirty` in the summary data
- `PUT /cdp-test/suites/<id>` — saves to `.state/` only (NO auto-commit).
  The next list call will show `git_dirty=True` if the suite is in git.
- `DELETE /cdp-test/suites/<id>` — handles both locations

### 5.3 Plan Routes — New Endpoints

**File**: `src/ui/web/routes/plans/crud.py`

```
POST /plans/add-to-git
    Body: { "plan_id": "..." }
    → Same pattern as suites

POST /plans/sync-to-git
    Body: { "plan_id": "..." }
    → Same pattern as suites

POST /plans/remove-from-git
    Body: { "plan_id": "..." }
    → Same pattern as suites
```

### 5.4 Existing Plan Routes — Same Behavior

Same as suites — `save_plan()` writes `.state/` only, `list_plans()`
merges both and reports `git_dirty`.

---

## 6. Frontend Changes

### 6.1 Suite List — Git Status Indicator

Each suite in the list shows its git status:

- **Local only**: no badge (or subtle `💻 Local` label)
- **In Git**: `📁 In Git` badge (or git icon)

The `in_git` field comes from the list API response.

### 6.2 Suite Actions — Add/Remove Buttons

Per-suite action area:

- If `in_git === false`: show **"Add to Git"** button
- If `in_git === true`: show **"Remove from Git"** button (with confirmation)

The button calls the appropriate API endpoint and refreshes the list.

### 6.3 Plan List — Same Treatment

Same visual indicators and action buttons as suites.

### 6.4 Git Status States

A suite/plan can be in one of three visual states:

| State | `in_git` | `git_dirty` | Badge | Available Actions |
|-------|----------|-------------|-------|-------------------|
| **Local only** | `false` | N/A | none (or subtle `Local` label) | "Add to Git" |
| **In Git — synced** | `true` | `false` | `✅ In Git` | "Remove from Git" |
| **In Git — outdated** | `true` | `true` | `⚠️ Git Outdated` | **"Sync to Git"**, "Remove from Git" |

The "outdated" state is the key UX innovation. It tells the user:
"You've made local changes that haven't been committed to git yet."

### 6.5 UX Flows

**When adding to git** (first time):
- Immediate visual feedback: badge appears, button switches
- Toast: "✅ Suite 'Login Flow' added to git"
- No extra confirmation needed — it's a safe, reversible action
- `git_updated_at` is set = `updated_at` → `git_dirty = false`

**When editing an in-git suite**:
- Save works normally → writes to `.state/` only
- The suite's `updated_at` advances past `git_updated_at`
- Next time the list loads, `git_dirty = true`
- The UI shows the ⚠️ badge and "Sync to Git" button
- The user can keep editing and sync when ready
- **No auto-commit. The user controls when to commit.**

**When syncing to git** (user-triggered):
- User clicks "Sync to Git"
- Current `.state/` version is copied to `.ledger/` and committed
- `git_updated_at` is set = `updated_at` → `git_dirty = false`
- Badge switches from ⚠️ to ✅
- Toast: "✅ Suite 'Login Flow' synced to git"
- Background push if auth ok

**When removing from git**:
- Confirmation dialog: "Remove 'Login Flow' from git? It will become local-only."
- The suite data is NOT deleted — it stays in `.state/` as local
- `in_git = false`, `git_updated_at = ""`
- `.ledger/` copy is deleted, deletion committed
- Toast: "Suite 'Login Flow' removed from git"

**When deleting an in-git suite**:
- Confirmation mentions git: "Delete 'Login Flow'? This will also remove it from git."
- Deletion removes from both `.state/` and `.ledger/`, commits deletion
- Hidden list prevents reappearance on pull

---

## 7. What We Do NOT Build

| Not in scope | Why |
|-------------|-----|
| Conflict resolution for suites/plans | Ledger uses `_safe_rebase()` which handles this generically. If a real conflict occurs, the existing ledger conflict resolution UI handles it. |
| Pull/push UI specific to tests | The existing ledger push/pull infrastructure handles this. Chat sync already auto-pulls the ledger branch. |
| Git history viewer for suites | Future enhancement. The data is in git, `git log` works, but no UI. |
| Diff viewer for suite changes | Future enhancement. |
| Branch-per-feature for tests | Overkill. Single `ledger` branch is sufficient. |
| Selective import from git | When you pull, you get everything. No cherry-picking. |
| Run results to git | Run results are ephemeral local artifacts. |

---

## 8. Execution Order

Each step is one change, independently testable.

### Phase 1: Models (foundation — no behavior change)

**9a-1**: Add `in_git: bool = False` and `git_updated_at: str = ""` to `TestSuite` in `models.py`
- Update `to_dict()` and `from_dict()` to include both fields
- **Verify**: Existing suites still load (fields default to False/"")

**9a-2**: Add `in_git: bool = False` and `git_updated_at: str = ""` to `ExecutionPlan` in `plans.py`
- Update `to_dict()` and `from_dict()` to include both fields
- **Verify**: Existing plans still load

### Phase 2: Storage — Suite Git Operations

**9b-1**: Add ledger path helpers + hidden list helpers to `storage.py`
- `_ledger_suites_dir()`, `_hidden_suites_file()`, `_get_hidden_suites()`, `_add_hidden_suite()`
- Import worktree functions
- **Verify**: Helpers return correct paths, no behavior change

**9b-2**: Implement `add_suite_to_git()`
- Load from local, set `in_git=True`, `git_updated_at=updated_at`
- Write to `.ledger/`, update local, commit
- **Verify**: Suite in both locations, `in_git=True`, `git_dirty=False`

**9b-3**: Implement `sync_suite_to_git()`
- Load from local, verify `in_git=True`
- Set `git_updated_at=updated_at`, write to `.ledger/`, update local, commit
- **Verify**: `.ledger/` copy matches local, `git_dirty=False`

**9b-4**: Implement `remove_suite_from_git()`
- Set `in_git=False`, `git_updated_at=""`, delete from `.ledger/`, update local, commit
- **Verify**: Suite only in `.state/`, `in_git=False`

**9b-5**: Modify `list_suites()` to merge both + compute `git_dirty`
- Scan local first (working copy), then ledger (for suites from other machines)
- Compute `git_dirty` from `updated_at > git_updated_at` when `in_git=True`
- Add `in_git` and `git_dirty` to summary dict
- **Verify**: List shows suites from both, with correct git status

**9b-6**: Modify `get_suite()` to check local first
- `.state/` first (working copy), then `.ledger/` (pulled from other machine)
- **Verify**: Local edits are returned even when ledger has older version

**9b-7**: Modify `save_suite()` — NO ledger writes
- Confirm it writes `.state/` only, does NOT touch `.ledger/`
- `updated_at` advances, `git_updated_at` stays → `git_dirty` becomes True
- **Verify**: Edit in-git suite → save → `updated_at > git_updated_at`

**9b-8**: Modify `delete_suite()` to handle both + hidden list
- Delete from both locations, add to hidden list, commit if was in ledger
- **Verify**: Delete an in-git suite → gone from both, hidden list updated

### Phase 3: Storage — Plan Git Operations

**9c-1** through **9c-8**: Same sequence as 9b-1 through 9b-8, applied to
`plan_storage.py` for `ExecutionPlan`.

### Phase 4: API Routes

**9d-1**: Add `POST /cdp-test/suites/add-to-git` route
- Calls `add_suite_to_git()`, background push
- **Verify**: POST returns `in_git: true`, suite appears in `.ledger/`

**9d-2**: Add `POST /cdp-test/suites/sync-to-git` route
- Calls `sync_suite_to_git()`, background push
- **Verify**: POST returns `git_dirty: false`, `.ledger/` matches local

**9d-3**: Add `POST /cdp-test/suites/remove-from-git` route
- Calls `remove_suite_from_git()`, background push
- **Verify**: POST returns `in_git: false`, suite removed from `.ledger/`

**9d-4**: Add `POST /plans/add-to-git` route
- Same pattern for plans

**9d-5**: Add `POST /plans/sync-to-git` route
- Same pattern for plans

**9d-6**: Add `POST /plans/remove-from-git` route
- Same pattern for plans

### Phase 5: Frontend

**9e-1**: Suite list — show three-state git status badge
- Local only: no badge
- In Git (synced): `✅ In Git`
- In Git (outdated): `⚠️ Git Outdated`
- **Verify**: Badges reflect actual state

**9e-2**: Suite list — action buttons per state
- Local only: "Add to Git" button
- In Git (synced): "Remove from Git" button
- In Git (outdated): **"Sync to Git"** button + "Remove from Git" button
- Confirmation dialog for "Remove from Git"
- **Verify**: Buttons appear/disappear correctly, API calls work

**9e-3**: Plan list — same three-state badge
- Same as 9e-1 for plans

**9e-4**: Plan list — same action buttons
- Same as 9e-2 for plans

---

## 9. File Map

| Step | Files Modified | Files Created |
|------|---------------|---------------|
| 9a-1 | `src/core/services/cdp_test/models.py` | — |
| 9a-2 | `src/core/services/scripts/plans.py` | — |
| 9b-1..8 | `src/core/services/cdp_test/storage.py` | — |
| 9c-1..8 | `src/core/services/scripts/plan_storage.py` | — |
| 9d-1..3 | `src/ui/web/routes/cdp_test/suites.py` | — |
| 9d-4..6 | `src/ui/web/routes/plans/crud.py` | — |
| 9e-1..2 | `src/ui/web/templates/scripts/integrations/_cdp_test.html` | — |
| 9e-3..4 | `src/ui/web/templates/scripts/integrations/_plans.html` | — |

---

## 10. Cross-References

| Reference | Location |
|-----------|----------|
| Ledger infrastructure | `src/core/services/ledger/worktree.py` (1161 lines) |
| Ledger ops | `src/core/services/ledger/ledger_ops.py` (259 lines) |
| Trace sharing (reference pattern) | `src/core/services/trace/trace_recorder.py` (721 lines) |
| Trace share routes (reference) | `src/ui/web/routes/trace/sharing.py` (148 lines) |
| Git auth check | `src/core/services/git_auth.py` — `is_auth_ok()` |
| Suite models | `src/core/services/cdp_test/models.py` (686 lines) |
| Suite storage | `src/core/services/cdp_test/storage.py` (181 lines) |
| Suite routes | `src/ui/web/routes/cdp_test/suites.py` (254 lines) |
| Plan models | `src/core/services/scripts/plans.py` (419 lines) |
| Plan storage | `src/core/services/scripts/plan_storage.py` (186 lines) |
| Plan routes | `src/ui/web/routes/plans/crud.py` (178 lines) |
| Suite UI | `src/ui/web/templates/scripts/integrations/_cdp_test.html` (4590 lines) |
| Plans UI | `src/ui/web/templates/scripts/integrations/_plans.html` (2786 lines) |
| .gitignore | `.gitignore` (line 31: `.state/`) |

---

## 11. Edge Cases & Scenarios

### 11.1 Pull from Another Machine (Suite Appears in Ledger Only)

When the ledger branch is pulled (via chat auto-sync or manual pull), suites
committed by OTHER machines appear in `.ledger/cdp-tests/suites/`. These
suites have NO local copy in `.state/`.

**How it works**:
- `list_suites()` scans `.state/` first, then `.ledger/`. Since there's no
  local copy, the suite is picked up from the ledger scan.
- `get_suite()` checks local first (miss), then ledger (hit). Returns the
  ledger version.
- The UI renders it with `in_git=True`, `git_dirty=False` — it's in git and
  in sync (because the ledger IS the only version).
- **First edit**: When the user opens this suite, edits it, and saves:
  - `save_suite()` writes to `.state/cdp-tests/suites/<id>.json`
  - This creates the local working copy
  - `updated_at` advances past `git_updated_at`
  - Next list → `git_dirty=True` → UI shows "Sync to Git"

No special handling needed — the existing merge logic handles it naturally.

### 11.2 Both Local and Ledger Exist (Normal Workflow)

After "Add to Git" + subsequent edits:
- `.state/<id>.json` — local working copy (user's latest edits)
- `.ledger/<id>.json` — last committed version
- `get_suite()` returns local (working copy)
- `list_suites()` returns local (skips ledger because `id` already seen)
- `git_dirty` computed from `updated_at > git_updated_at`

### 11.3 Duplicate an In-Git Suite

The existing `POST /cdp-test/suites/<id>/duplicate` creates a new suite with
a new UUID. The duplicate is LOCAL-ONLY regardless of the original's `in_git`
status. The duplicate's `in_git=False`, `git_updated_at=""`.

This is correct — a duplicate is a new artifact that hasn't been added to git.

### 11.4 Delete an In-Git Suite That Was Only Pulled (No Local Copy)

If the suite exists only in `.ledger/` (pulled from another machine, never
edited locally):
- `delete_suite()` checks `.state/` (doesn't exist) → no-op
- Checks `.ledger/` → exists → delete + commit deletion
- Add to hidden list → prevents reappearing on next pull

### 11.5 Concurrent Edits from Multiple Machines

Machine A and Machine B both have the same suite. Both edit and sync.
- Machine A syncs → commits to ledger
- Machine B syncs → commits to ledger → `_safe_rebase()` runs
- If the same file was changed, git rebase conflict may occur
- The existing ledger conflict resolution handles this generically
- **OUT OF SCOPE**: We don't build merge UI for suites. Git's rebase
  mechanism is sufficient with the existing `.ledger/` conflict handling.

### 11.6 Worktree Not Yet Bootstrapped

If `.ledger/` doesn't exist (first time, fresh clone):
- `add_suite_to_git()` calls `ensure_worktree()` first
- `list_suites()` checks `ledger_dir.exists()` before scanning
- No crash on missing worktree

### 11.7 Git Auth Not Available (SSH Not Unlocked)

All git *write* operations (push) are gated by `is_auth_ok()`.
- If auth is not ok, the commit happens LOCALLY on the ledger branch
  (inside `.ledger/`), but the background push is skipped.
- The commit will be pushed on the next successful push (chat sync,
  manual push, or next operation when auth is available).
- **No error shown to user** — the local commit succeeds. Push is
  best-effort background.

---

## 12. Serialization Detail

### 12.1 TestSuite — Exact Changes

**Fields to add** (in `models.py` dataclass):
```python
# After run_count field:
in_git: bool = False
git_updated_at: str = ""
```

**`to_dict()` changes** — add to the dict:
```python
"in_git": self.in_git,
"git_updated_at": self.git_updated_at,
```
Place after `"run_count"` line.

**`from_dict()` changes** — add to the `cls()` call:
```python
in_git=data.get("in_git", False),
git_updated_at=data.get("git_updated_at", ""),
```
Place after `run_count=` line.

**`list_suites()` summary changes** — add to the summary dict:
```python
"in_git": data.get("in_git", False),
"git_updated_at": data.get("git_updated_at", ""),
```
Note: `git_dirty` is COMPUTED in the modified `list_suites()`, not stored.

### 12.2 ExecutionPlan — Exact Changes

**Fields to add** (in `plans.py` dataclass):
```python
# After run_count field:
in_git: bool = False
git_updated_at: str = ""
```

**`to_dict()` changes** — add:
```python
"in_git": self.in_git,
"git_updated_at": self.git_updated_at,
```

**`from_dict()` changes** — add:
```python
in_git=data.get("in_git", False),
git_updated_at=data.get("git_updated_at", ""),
```

**`list_plans()` summary changes** — add:
```python
"in_git": data.get("in_git", False),
"git_updated_at": data.get("git_updated_at", ""),
```

---

## 13. Dependencies Needed (Per File)

### 13.1 `storage.py` (cdp_test) — New Imports

```python
from src.core.services.ledger.worktree import (
    ensure_worktree,
    ledger_add_and_commit,
    push_ledger_branch,
    worktree_path,
)
```

### 13.2 `plan_storage.py` (scripts) — New Imports

Same as above.

### 13.3 `suites.py` (routes) — New Imports

```python
from src.core.services.git_auth import is_auth_ok
from src.core.services.cdp_test.storage import (
    add_suite_to_git,
    sync_suite_to_git,
    remove_suite_from_git,
)
```
Also needs `threading` for background push.

### 13.4 `crud.py` (plan routes) — New Imports

```python
from src.core.services.git_auth import is_auth_ok
from src.core.services.scripts.plan_storage import (
    add_plan_to_git,
    sync_plan_to_git,
    remove_plan_from_git,
)
```
Also needs `threading` for background push.

---

## 14. Frontend — Exact Insertion Points

### 14.1 `_cdp_test.html` — `_cdpTestSuitesList()` Function

**Current location**: Lines 156-195
**Current per-suite row**: Lines 170-190

Changes needed:
1. **Badge**: After the suite name div (line 175), add a git status badge
   based on `s.in_git` and `s.git_dirty`
2. **Buttons**: In the action area (line 184-188), add "Add to Git" /
   "Sync to Git" / "Remove from Git" buttons based on state
3. **Delete confirmation**: If `s.in_git`, the delete confirmation should
   mention git

### 14.2 `_plans.html` — `_plansList()` Function

**Current location**: Lines 127-170
**Current per-plan row**: Lines 144-165

Same three changes as suites.

### 14.3 New JS Functions Needed

```javascript
// Suites
async function _cdpTestAddToGit(suiteId) { ... }     // POST /cdp-test/suites/add-to-git
async function _cdpTestSyncToGit(suiteId) { ... }     // POST /cdp-test/suites/sync-to-git
async function _cdpTestRemoveFromGit(suiteId) { ... } // POST /cdp-test/suites/remove-from-git (with confirm)

// Plans
async function _plansAddToGit(planId) { ... }         // POST /plans/add-to-git
async function _plansSyncToGit(planId) { ... }         // POST /plans/sync-to-git
async function _plansRemoveFromGit(planId) { ... }     // POST /plans/remove-from-git (with confirm)
```
