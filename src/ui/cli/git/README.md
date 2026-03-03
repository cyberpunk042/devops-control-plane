# CLI Domain: Git — Local Git Operations & GitHub Actions

> **3 files · 306 lines · 9 commands + 1 subgroup · Group: `controlplane git`**
>
> Two concern areas: local Git operations (status, log, commit, pull,
> push) and GitHub API operations via `gh` CLI (list PRs, list/trigger
> workflow runs, list workflows). The `gh` subgroup provides runtime
> GitHub Actions interaction, complementing `cli/ci`'s static workflow
> analysis and generation.
>
> Core service: `core/services/git/ops.py` (re-exported via `git_ops.py`)

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                         controlplane git                            │
│                                                                      │
│  ┌── Local Git ────────────┐   ┌── GitHub (gh subgroup) ──────────┐ │
│  │ status                  │   │ gh pulls                         │ │
│  │ log [-n N]              │   │ gh runs [-n N]                   │ │
│  │ commit MESSAGE [-f ..]  │   │ gh dispatch WORKFLOW [--ref]     │ │
│  │ pull [--rebase]         │   │ gh workflows                     │ │
│  │ push [--force]          │   │                                   │ │
│  └────────────┬────────────┘   └───────────────┬──────────────────┘ │
│               │                                │                    │
└───────────────┼────────────────────────────────┼────────────────────┘
                │                                │
                ▼                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   core/services/git/ops.py (via git_ops.py)         │
│                                                                      │
│  Local Git:                                                          │
│    git_status(root)                → branch, dirty, ahead/behind    │
│    git_log(root, n)                → commits[] with hash, msg, etc  │
│    git_commit(root, msg, files)    → hash, message                  │
│    git_pull(root, rebase)          → output                         │
│    git_push(root, force)           → output                         │
│                                                                      │
│  GitHub (via gh CLI subprocess):                                    │
│    gh_pulls(root)                  → pulls[] with number, title     │
│    gh_actions_runs(root, n)        → runs[] with status, conclusion │
│    gh_actions_dispatch(root, wf)   → dispatched workflow + ref      │
│    gh_actions_workflows(root)      → workflows[] with name, state   │
└──────────────────────────────────────────────────────────────────────┘
```

### Two Domains, One Group

The git group splits cleanly into two sub-modules:

```
core.py    → local git operations (run directly via git commands)
github.py  → GitHub API operations (delegated through gh CLI)
```

Local git commands work with the repository on disk. GitHub commands
require the `gh` CLI to be installed and authenticated. The `gh`
subgroup is nested: `controlplane git gh <command>`.

### Relationship to `cli/ci`

```
┌─── cli/ci ────────────────────┐    ┌─── cli/git ────────────────────┐
│ Static analysis of YAML files │    │ Runtime GitHub API operations  │
│ • ci status (detect providers)│    │ • git gh runs (live run list)  │
│ • ci workflows (parse YAML)  │    │ • git gh dispatch (trigger)    │
│ • ci coverage (module check)  │    │ • git gh workflows (list)      │
│ • ci generate (create YAML)  │    │ • git gh pulls (PR list)       │
└───────────────────────────────┘    └────────────────────────────────┘
         FILES on disk                         GITHUB API
```

`cli/ci` works with **workflow YAML files on disk**.
`cli/git gh` works with **live GitHub Actions via the API**.

### Error Handling

Local git commands check for `error` key in result.
GitHub commands check for `available` key (gh CLI must be installed).

```
result = gh_pulls(root)
├── available=true  → show PRs
├── available=false → "❌ Not available" + exit(1)
└── (no pulls)      → "No open pull requests."
```

---

## Commands

### `controlplane git status`

Show git status: branch, dirty state, ahead/behind, file counts.

```bash
controlplane git status
controlplane git status --json
```

**Output example:**

```
🌿 main @ a1b2c3d
   State: dirty
   ↑ ahead 2  ↓ behind 0
   Staged: 3
   Modified: 5
   Untracked: 1
   Last: fix: resolve DNS lookup timeout (jfortin, 2026-03-01)
```

**Clean state:**

```
🌿 main @ a1b2c3d
   State: clean
```

---

### `controlplane git log`

Show recent commit history.

```bash
controlplane git log
controlplane git log -n 5
controlplane git log --json
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-n` | int | 10 | Number of commits to show |
| `--json` | flag | off | JSON output |

**Output example:**

```
  a1b2c3d  fix: resolve DNS lookup timeout
         jfortin — 2026-03-01
  d4e5f6g  feat: add CI coverage command
         jfortin — 2026-02-28
```

**Message truncation:** Commit messages are truncated at 70 characters
in the non-JSON display.

---

### `controlplane git commit MESSAGE`

Stage and commit changes.

```bash
# Commit all changes
controlplane git commit "fix: resolve timeout"

# Commit specific files
controlplane git commit "docs: update README" -f README.md -f docs/setup.md
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `MESSAGE` | argument | (required) | Commit message |
| `-f/--files` | string (multiple) | (all) | Specific files to stage |

**Output example:**

```
✅ Committed: a1b2c3d
   Message: fix: resolve timeout
```

---

### `controlplane git pull`

Pull from remote.

```bash
controlplane git pull
controlplane git pull --rebase
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--rebase` | flag | off | Pull with rebase instead of merge |

**Output truncation:** Shows first 200 characters of git output.

---

### `controlplane git push`

Push to remote.

```bash
controlplane git push
controlplane git push --force
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--force` | flag | off | Force push (with lease) |

---

### `controlplane git gh pulls`

List open pull requests.

```bash
controlplane git gh pulls
controlplane git gh pulls --json
```

**Output example:**

```
📋 Open PRs (2):
   #42 feat: add DNS record generation
      feature/dns-gen — jfortin
   #41 fix: backup encryption path
      fix/backup-enc — contributor
```

---

### `controlplane git gh runs`

List recent workflow runs.

```bash
controlplane git gh runs
controlplane git gh runs -n 5
controlplane git gh runs --json
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-n` | int | 10 | Number of runs to show |

**Output example:**

```
⚡ Workflow runs (3):
   ✅ CI [main]
   ⏳ Deploy [feature/dns-gen]
   ❌ Lint [fix/backup-enc]
```

**Status icons:**

| Icon | Meaning |
|------|---------|
| ✅ | completed (success) |
| ⏳ | in_progress |
| ⬜ | queued |
| ❌ | failure |
| ❓ | unknown |

---

### `controlplane git gh dispatch WORKFLOW`

Trigger a workflow via repository dispatch.

```bash
controlplane git gh dispatch ci.yml
controlplane git gh dispatch deploy.yml --ref staging
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `WORKFLOW` | argument | (required) | Workflow filename |
| `--ref` | string | (current branch) | Branch to dispatch on |

---

### `controlplane git gh workflows`

List available GitHub Actions workflows.

```bash
controlplane git gh workflows
controlplane git gh workflows --json
```

**Output example:**

```
⚙️  Workflows (3):
   ✅ CI [active]
   ✅ Deploy [active]
   ⏸️  Legacy Build [disabled_inactivity]
```

---

## File Map

```
cli/git/
├── __init__.py     35 lines — group definition, _resolve_project_root,
│                              sub-module imports (core, github)
├── core.py        141 lines — status, log, commit, pull, push
├── github.py      130 lines — gh subgroup (pulls, runs, dispatch, workflows)
└── README.md               — this file
```

**Total: 306 lines of Python across 3 files.**

---

## Per-File Documentation

### `__init__.py` — Group definition (35 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `_resolve_project_root(ctx)` | helper | Reads `config_path` from context, falls back to `find_project_file()` |
| `git()` | Click group | Top-level `git` group |
| `from . import core, github` | import | Registers sub-modules |

---

### `core.py` — Local Git commands (141 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `status(ctx, as_json)` | command | Branch, dirty state, ahead/behind, file counts, last commit |
| `log(ctx, count, as_json)` | command | Recent commit history (N commits) |
| `commit(ctx, message, files)` | command | Stage specified or all files, create commit |
| `pull(ctx, rebase)` | command | Pull from remote (optional rebase) |
| `push(ctx, force)` | command | Push to remote (optional force with lease) |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `git_status` | `git_ops` | Repository status |
| `git_log` | `git_ops` | Commit history |
| `git_commit` | `git_ops` | Staging + committing |
| `git_pull` | `git_ops` | Remote pull |
| `git_push` | `git_ops` | Remote push |

**Status display richness:** The `status` command shows up to 8 fields:
branch, commit hash, dirty/clean state, ahead/behind counts, staged
count, modified count, untracked count, and last commit summary. Each
is conditionally displayed (zero values are hidden).

**Output truncation:** `pull` and `push` truncate output to 200
characters. `log` truncates commit messages to 70 characters. `status`
truncates last commit message to 60 characters.

---

### `github.py` — GitHub CLI commands (130 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `gh()` | Click group | `git gh` subgroup |
| `pulls(ctx, as_json)` | command | List open pull requests via `gh pr list` |
| `runs(ctx, count, as_json)` | command | List recent workflow runs via `gh run list` |
| `dispatch(ctx, workflow, ref)` | command | Trigger workflow dispatch via `gh workflow run` |
| `workflows(ctx, as_json)` | command | List workflows via `gh workflow list` |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `gh_pulls` | `git_ops` | PR listing |
| `gh_actions_runs` | `git_ops` | Run listing |
| `gh_actions_dispatch` | `git_ops` | Workflow triggering |
| `gh_actions_workflows` | `git_ops` | Workflow listing |

**Run status icon mapping:** The `runs` command maps both `conclusion`
and `status` fields to icons. It checks `conclusion` first (completed
runs), falling back to `status` (in-progress/queued). This handles
the GitHub API's two-field status representation.

---

## Dependency Graph

```
__init__.py
├── click                     ← click.group
├── core.config.loader        ← find_project_file (lazy)
└── Imports: core, github

core.py
├── click                     ← click.command
└── core.services.git_ops     ← git_status, git_log, git_commit,
                                 git_pull, git_push (all lazy)

github.py
├── click                     ← click.group, click.command
└── core.services.git_ops     ← gh_pulls, gh_actions_runs,
                                 gh_actions_dispatch,
                                 gh_actions_workflows (all lazy)
```

Both sub-modules import exclusively from `git_ops`. No cross-module
imports, no cross-domain imports.

---

## Consumers

### Who registers this CLI group

| Layer | Module | What It Does |
|-------|--------|-------------|
| CLI entry | `src/main.py:450` | `from src.ui.cli.git import git` |

### Who also uses the same core service

| Layer | Module | Core Service Used |
|-------|--------|------------------|
| Web routes | `routes/git/` | `git_ops` (status, log, PRs, runs, dispatch) |
| Core | `metrics/ops.py:48` | `git_status` (health probe) |
| Core | `wizard/helpers.py:92` | `gh_status` (wizard GitHub detection) |
| Core | `wizard/helpers.py:139` | `gh_user` (wizard user identity) |
| Core | `wizard/helpers.py:148` | `gh_repo_info` (wizard repo detection) |
| Core | `wizard/helpers.py:157` | `git_remotes` (wizard remote detection) |

---

## Design Decisions

### Why local git and GitHub API are in the same group

From the user's perspective, `git` and `gh` are related workflows:
commit → push → check PR → watch run. Grouping them under one CLI
group (`controlplane git`) keeps the mental model simple. The `gh`
subgroup provides the namespace boundary.

### Why `gh` is a subgroup (not flat commands)

All GitHub API commands require `gh` CLI authentication. Nesting them
under `git gh` signals this dependency and separates them from local
git commands that work offline. It also avoids name collisions
(e.g., `git workflows` vs `ci workflows`).

### Why `commit` takes `--files` as multiple options (not variadic args)

The commit message is the main argument. Using `-f` for files keeps
the interface clean: `git commit "message" -f file1 -f file2`. Making
files variadic would conflict with the required message argument.

### Why `push --force` exists

Force-push is needed after interactive rebase, fixup commits, or
history rewriting. The `--force` flag uses `--force-with-lease` under
the hood (in the core service) to prevent overwriting others' work.

### Why `pull` and `push` show truncated output

Git pull/push output can be verbose (object counting, delta compression,
branch tracking info). 200 characters is enough to confirm success or
see the first error. Users needing full output can use `git` directly.

### Why `dispatch` doesn't have `--json`

Dispatching a workflow is a fire-and-forget action. The only useful
output is "dispatched successfully" + which workflow + which ref.
JSON wrapping this adds no value over the structured text output.

---

## JSON Output Examples

### `git status --json`

```json
{
  "available": true,
  "branch": "main",
  "commit": "a1b2c3d",
  "dirty": true,
  "ahead": 2,
  "behind": 0,
  "staged_count": 3,
  "modified_count": 5,
  "untracked_count": 1,
  "last_commit": {
    "message": "fix: resolve DNS lookup timeout",
    "author": "jfortin",
    "date": "2026-03-01T14:30:00Z"
  }
}
```

### `git gh runs --json`

```json
{
  "available": true,
  "runs": [
    {
      "name": "CI",
      "status": "completed",
      "conclusion": "success",
      "headBranch": "main"
    },
    {
      "name": "Deploy",
      "status": "in_progress",
      "conclusion": null,
      "headBranch": "feature/dns-gen"
    }
  ]
}
```

### `git gh workflows --json`

```json
{
  "available": true,
  "workflows": [
    {"name": "CI", "state": "active"},
    {"name": "Deploy", "state": "active"},
    {"name": "Legacy Build", "state": "disabled_inactivity"}
  ]
}
```
