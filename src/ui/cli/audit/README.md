# CLI Domain: Audit — Plan-Based Tool Installation

> **4 files · 381 lines · 3 commands · Group: `controlplane audit`**
>
> Manages automated tool installation through a plan-based execution engine.
> Each tool has a multi-step recipe (shell commands, downloads, builds);
> the CLI resolves the right plan for the current OS/arch, executes steps
> one-by-one with progress reporting, and persists state so failed installs
> can be resumed from where they stopped.
>
> Core services: `core/services/tool_install`, `core/services/audit/l0_detection.py`

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                         controlplane audit                          │
│                                                                      │
│  install ─────► plans ─────► resume                                  │
│  (new run)      (list)       (continue)                              │
└──────────┬──────────────────────────────┬────────────────────────────┘
           │                              │
           ▼                              ▼
┌─────────────────────┐     ┌──────────────────────────┐
│  resolve_install_plan│     │  resume_plan(plan_id)    │
│  (tool, os_profile) │     │  (load from plan_state)  │
└──────────┬──────────┘     └────────────┬─────────────┘
           │                              │
           ▼                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     execute_plan_step(step)                         │
│                                                                      │
│  Step types:  shell │ download │ build │ verify │ service_start      │
│  Each step:   run → check ok → save state → next                    │
│  On failure:  save state → exit(1) → user runs resume               │
└──────────────────────────────────────────────────────────────────────┘
```

### Lifecycle of an Installation

1. **User runs** `controlplane audit install <tool>`
2. **OS detection** — `_detect_os()` returns distro, arch, package manager
3. **Plan resolution** — `resolve_install_plan(tool, profile)` picks the right
   recipe variant for the OS/arch combination
4. **Already-installed check** — if `plan["already_installed"]` is true, done
5. **Step-by-step execution** — each step gets `execute_plan_step(step)`:
   - Returns `{ok: true}` → print OK, save state, continue
   - Returns `{skipped: true}` → print SKIP, continue
   - Returns `{ok: false}` → print FAILED, save state, exit
   - Throws exception → print CRASHED, save state, exit
6. **On failure** — the plan (ID, tool name, completed steps, remaining steps)
   is persisted to disk via `save_plan_state()`
7. **Resume** — `controlplane audit resume <plan_id>` loads the saved state,
   skips already-completed steps, continues from the failure point

### Plan State Machine

```
┌──────────┐      step OK      ┌──────────┐      all done     ┌──────┐
│  running │ ───────────────► │  running │ ──────────────── ► │ done │
└──────────┘                   └──────────┘                    └──────┘
      │                              │
      │ step FAILED / CRASH          │ step FAILED / CRASH
      ▼                              ▼
┌──────────┐                   ┌──────────┐
│  failed  │  ◄──── resume ── │  failed  │
└──────────┘                   └──────────┘
```

States are persisted as JSON files. The `plans` command reads these files to
list any pending/paused/failed installations.

---

## Commands

### `controlplane audit install [TOOL]`

Install a tool via the plan-based engine.

```bash
# List all available tools (grouped by category)
controlplane audit install --list

# List in machine-readable format
controlplane audit install --list --json

# Dry-run — show the plan without executing
controlplane audit install docker --dry-run

# Execute the installation
controlplane audit install docker

# With sudo password for privileged steps
controlplane audit install docker --sudo-password "mypass"
# or via environment variable:
SUDO_PASSWORD=mypass controlplane audit install docker
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `TOOL` | argument | (none) | Tool ID from TOOL_RECIPES |
| `--list` | flag | off | List available tools instead of installing |
| `--dry-run` | flag | off | Show plan steps without executing |
| `--sudo-password` | string | `$SUDO_PASSWORD` | Password for steps that need sudo |
| `--json` | flag | off | JSON output (works with `--list` and `--dry-run`) |

**Dry-run output example:**

```
📋 Install plan for docker:
   Steps: 4

   1. [shell] Update package index 🔒
      $ sudo apt-get update
   2. [shell] Install prerequisites 🔒
      $ sudo apt-get install -y ca-certificates curl gnupg
   3. [shell] Add Docker GPG key 🔒
      $ sudo install -m 0755 -d /etc/apt/keyrings && ...
   4. [shell] Install Docker Engine 🔒
      $ sudo apt-get install -y docker-ce docker-ce-cli
```

**Execution output example:**

```
⚡ Installing docker...

   [1/4] Update package index... OK (2340ms)
   [2/4] Install prerequisites... OK (12850ms)
   [3/4] Add Docker GPG key... OK (320ms)
   [4/4] Install Docker Engine... OK (18200ms)

✅ docker installed successfully
```

**Failure output example:**

```
⚡ Installing pytorch...

   [1/3] Detect CUDA version... OK (150ms)
   [2/3] Install PyTorch with CUDA 12.1... FAILED
         pip install returned exit code 1

❌ Installation failed at step 2
   Plan ID: a1b2c3d4-e5f6-7890-abcd-1234567890ef
   Resume:  controlplane audit resume a1b2c3d4-e5f6-7890-abcd-1234567890ef
```

---

### `controlplane audit plans`

Show pending, paused, or failed installation plans.

```bash
controlplane audit plans
controlplane audit plans --json
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--json` | flag | off | JSON output |

**Output example:**

```
📋 Pending plans (2):

   ❌ pytorch              [2/3] a1b2c3d4-e5f6-7890-abcd-1234567890ef
   ⏸️ terraform            [1/5] fedcba98-7654-3210-fedc-ba9876543210
```

**Status icons:**

| Icon | Status | Meaning |
|------|--------|---------|
| ❌ | `failed` | A step returned an error |
| ⏸️ | `paused` | User interrupted execution |
| 🔄 | `running` | Execution in progress (stale if process died) |

---

### `controlplane audit resume PLAN_ID`

Resume a paused or failed installation plan from where it stopped.

```bash
controlplane audit resume a1b2c3d4-e5f6-7890-abcd-1234567890ef

# With sudo password
controlplane audit resume a1b2c3d4 --sudo-password "mypass"
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `PLAN_ID` | argument | (required) | The plan ID from `plans` output |
| `--sudo-password` | string | `$SUDO_PASSWORD` | Password for sudo steps |
| `--json` | flag | off | JSON output |

**Output example:**

```
⚡ Resuming pytorch (2/3 done)...

   [3/3] Install PyTorch with CUDA 12.1... OK (45200ms)

✅ pytorch installation resumed and completed
```

**Error handling:**

- If the plan ID is not found, exits with error
- If the plan is already completed (`status: done`), exits with error
- If a step fails during resume, state is saved again for another resume

---

## File Map

```
cli/audit/
├── __init__.py     35 lines — group definition, _resolve_project_root helper,
│                              sub-module imports (install, plans, resume)
├── install.py     185 lines — install command (list mode, dry-run, execution loop)
├── plans.py        40 lines — plans command (list pending/failed plans)
├── resume.py      121 lines — resume command (continue from saved state)
└── README.md               — this file
```

**Total: 381 lines of Python across 4 files.**

---

## Per-File Documentation

### `__init__.py` — Group definition (35 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `_resolve_project_root(ctx)` | helper | Reads `config_path` from Click context; falls back to `find_project_file()` then `Path.cwd()` |
| `audit()` | Click group | Defines the `audit` group with help text |
| `from . import install, plans, resume` | import | Registers all sub-commands with the group |

**Pattern note:** `_resolve_project_root` is defined here but only used by
sub-modules via `from . import _resolve_project_root`. In practice, `plans.py`
does not use it (it lists global plan state, not per-project).

---

### `install.py` — Install a tool via plan (185 lines)

The largest file in this domain. Contains three distinct execution paths
within a single command function.

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `install()` | Click command | Dispatches to list mode, dry-run mode, or execution mode |

**Internal flow:**

```
install()
├── list_tools=True or no TOOL arg?
│   ├── as_json → dump TOOL_RECIPES as JSON list
│   └── interactive → group by category, print formatted table
│
├── dry_run=True?
│   ├── as_json → dump full plan dict
│   └── interactive → print step list with sudo markers (🔒)
│
└── Execute mode
    ├── _detect_os()                    → system profile
    ├── resolve_install_plan(tool, profile) → step list
    ├── already_installed?              → early return
    ├── for each step:
    │   ├── execute_plan_step(step, sudo_password)
    │   ├── ok?      → print OK + timing, save state
    │   ├── skipped? → print SKIP
    │   └── failed?  → print FAILED, save state, break
    └── success? → save state as "done"
        failed?  → print plan_id + resume hint, exit(1)
```

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `_detect_os` | `audit.l0_detection` | Get OS distro, arch, package manager |
| `TOOL_RECIPES` | `tool_install` | Dictionary of all available tool recipes |
| `resolve_install_plan` | `tool_install` | Turn tool name + OS profile into step list |
| `execute_plan_step` | `tool_install` | Run a single installation step |
| `save_plan_state` | `tool_install` | Persist plan progress to disk |

**Sudo handling:** Steps with `step["sudo"] = True` require a password.
The password is passed via `--sudo-password` flag or `SUDO_PASSWORD` env var.
If a step fails with `result["needs_sudo"]`, the CLI hints the user to
provide the password.

---

### `plans.py` — List pending plans (40 lines)

The smallest file. Reads persisted plan state files and displays them.

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `list_plans()` | Click command (`plans`) | Loads all pending plans, displays status/tool/progress |

**Core service imports (lazy):**

| Import | From | Used For |
|--------|------|----------|
| `list_pending_plans` | `tool_install` | Scan plan state directory, return non-"done" plans |

**Output format:** Each plan shows:
- Status icon (❌/⏸️/🔄)
- Tool name (left-aligned, 20 chars)
- Progress `[completed/total]`
- Plan ID (UUID)

---

### `resume.py` — Resume a failed plan (121 lines)

Mirrors the execution loop in `install.py` but starts from saved state
rather than resolving a fresh plan.

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `resume()` | Click command | Load saved plan state, execute remaining steps |

**Core service imports (lazy):**

| Import | From | Used For |
|--------|------|----------|
| `resume_plan` | `tool_install` | Load plan state by ID, compute remaining steps |
| `execute_plan_step` | `tool_install` | Run a single step (same as install.py) |
| `save_plan_state` | `tool_install` | Update state after each step (same as install.py) |

**Difference from install.py:**
- `resume_plan()` returns `completed_count` and `original_total` from the
  saved state, so the progress display shows the original numbering
  (e.g., `[3/5]` not `[1/3]`)
- The loop iterates only over remaining steps, not all steps
- On success, the final `save_plan_state()` sets status to `"done"`

---

## Dependency Graph

```
__init__.py
├── click                      ← click.group
├── core.config.loader         ← find_project_file (lazy, in _resolve_project_root)
└── Imports: install, plans, resume

install.py
├── click                      ← click.command, click.option, click.argument
├── audit.l0_detection         ← _detect_os (lazy)
├── tool_install               ← TOOL_RECIPES, resolve_install_plan,
│                                execute_plan_step, save_plan_state (all lazy)
└── uuid                       ← uuid4 (lazy, only in execute mode)

plans.py
├── click                      ← click.command, click.option
└── tool_install               ← list_pending_plans (lazy)

resume.py
├── click                      ← click.command, click.option, click.argument
└── tool_install               ← resume_plan, execute_plan_step,
                                  save_plan_state (all lazy)
```

All core service imports are **lazy** (inside the command function body, not
at module top level). This keeps `controlplane --help` fast since
`tool_install` pulls in heavy detection logic.

---

## Consumers

### Who registers this CLI group

| Layer | Module | What It Does |
|-------|--------|-------------|
| CLI entry | `src/main.py:465` | `from src.ui.cli.audit import audit` |
| CLI entry | `src/main.py:485` | `cli.add_command(audit)` |

### Who also uses the same core services

| Layer | Module | Core Service Used |
|-------|--------|------------------|
| Web routes | `routes/audit/tool_install.py` | `tool_install` (orchestrator, recipes, plan state) |
| Web routes | `routes/audit/analysis.py` | `audit.l0_detection`, `audit.scoring` |
| Core | `wizard/validate.py` | `TOOL_RECIPES` (validate wizard tool references) |
| Core | `dev_scenarios.py` | `remediation_handlers`, `remediation_planning` |
| Core | `tool_install/orchestration/` | `audit.l0_detection._detect_os` |

The web routes provide the same tool installation functionality but through
the HTTP API with streaming progress. The CLI and web routes both delegate
to the same `tool_install` core service.

---

## Design Decisions

### Why install has three modes in one command

**List**, **dry-run**, and **execute** are all `controlplane audit install`
with flags (`--list`, `--dry-run`, or no flag). This follows the principle
that a user starts with `--list` to browse, then `--dry-run` to preview,
then executes — all the same command, progressively less cautious.

Alternative considered: separate `audit list-tools`, `audit preview`, `audit install`.
Rejected because it fragments the workflow and requires the user to remember
three command names for what is conceptually one action.

### Why resume is a separate command (not `install --resume`)

Resume needs a `PLAN_ID` argument, not a tool name. Making it a flag on
`install` would create an awkward interface where the positional argument
changes meaning depending on flags. A separate command with clear semantics
(`resume <plan_id>`) is more discoverable.

### Why plans are persisted as JSON files

Plan state is saved to `~/.controlplane/plans/` as JSON. This avoids
needing a database for what is ephemeral state (plans are cleaned up
once done). JSON files are human-readable, debuggable, and can be
manually edited if state gets corrupted.

### Why all imports are lazy

`tool_install` imports `audit.l0_detection` which runs OS detection at
import time (calls `platform.system()`, reads `/etc/os-release`, etc.).
Lazy imports prevent this from running every time the user types
`controlplane --help`.

### Why plans.py doesn't use _resolve_project_root

Plan state is global (`~/.controlplane/plans/`), not per-project.
A user can install docker in project A, switch to project B, and
`controlplane audit plans` still shows the pending plan. This is
intentional — tool installation is system-wide.

### Why sudo password is also an env var

CI/CD environments can't type passwords interactively. The `SUDO_PASSWORD`
env var lets automation scripts pass the password without command-line
argument exposure in process listings.

---

## JSON Output Examples

### `audit install --list --json`

```json
[
  {"id": "docker", "label": "Docker Engine", "category": "containers"},
  {"id": "kubectl", "label": "Kubernetes CLI", "category": "containers"},
  {"id": "terraform", "label": "Terraform", "category": "iac"},
  {"id": "pytorch", "label": "PyTorch", "category": "ml"}
]
```

### `audit install docker --dry-run --json`

```json
{
  "tool": "docker",
  "already_installed": false,
  "steps": [
    {
      "id": "update-packages",
      "type": "shell",
      "label": "Update package index",
      "command": "sudo apt-get update",
      "sudo": true
    },
    {
      "id": "install-prereqs",
      "type": "shell",
      "label": "Install prerequisites",
      "command": "sudo apt-get install -y ca-certificates curl gnupg",
      "sudo": true
    }
  ]
}
```

### `audit plans --json`

```json
[
  {
    "plan_id": "a1b2c3d4-e5f6-7890-abcd-1234567890ef",
    "tool": "pytorch",
    "status": "failed",
    "current_step": 1,
    "completed_steps": [0],
    "steps": [...]
  }
]
```
