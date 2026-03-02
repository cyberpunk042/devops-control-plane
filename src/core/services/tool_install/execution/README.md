# L4 Execution — System Writers

> **12 files · 3,610 lines · All side effects live here and ONLY here.**
>
> Subprocess calls, file writes, config modifications, plan/chain state persistence.
> Every other layer is read-only. L4 is where the system is actually mutated.

---

## How It Works

### Execution Flow

```
PLAN (from L5 Orchestrator)
     │
     ▼
step_executors — dispatch by step["type"]
     │
     │  ┌──────── packages ──────── _execute_package_step()
     │  ├──────── repo_setup ────── _execute_repo_step()
     │  ├──────── tool ──────────── _execute_command_step()
     │  ├──────── post_install ──── _execute_command_step()
     │  ├──────── verify ────────── _execute_verify_step()
     │  ├──────── config ────────── _execute_config_step()
     │  ├──────── shell_config ──── _execute_shell_config_step()
     │  ├──────── service ───────── _execute_service_step()
     │  ├──────── download ──────── _execute_download_step()
     │  ├──────── github_release ── _execute_github_release_step()
     │  ├──────── source ────────── _execute_source_step()
     │  ├──────── build ─────────── _execute_build_step()
     │  ├──────── install ───────── _execute_install_step()
     │  ├──────── cleanup ───────── _execute_cleanup_step()
     │  └──────── notification ──── _execute_notification_step()
     │
     ▼
subprocess_runner._run_subprocess() / _run_subprocess_streaming()
     │
     ▼
SYSTEM (apt, cargo, pip, npm, git, systemctl, ...)
```

### State Persistence

```
plan_state.py     chain_state.py
     │                  │
     ▼                  ▼
.state/install_plans/  .state/remediation_chains/
     │                  │
     ├─ {plan_id}.json  ├─ {chain_id}.json
     ├─ archive/        └─ archive/
     └─ (pending/done)      (completed/cancelled)

Both use the same pattern:
  create → save → resume → archive
  with sensitive field redaction (passwords stripped)
```

---

## File Map

```
execution/
├── __init__.py            60 lines  — re-exports all execution functions
├── step_executors.py     994 lines  — 14 step type dispatchers + rollback
├── build_helpers.py      633 lines  — autotools/cmake/cargo build plans
├── chain_state.py        381 lines  — remediation chain lifecycle + persistence
├── offline_cache.py      318 lines  — airgapped install cache system
├── tool_management.py    254 lines  — update_tool, remove_tool
├── subprocess_runner.py  234 lines  — single subprocess bottleneck (blocking + streaming)
├── plan_state.py         219 lines  — plan state save/load/resume/cancel/archive
├── script_verify.py      215 lines  — curl|bash safety (download → hash → execute)
├── download.py           141 lines  — GitHub release resolution + checksum verification
├── config.py              97 lines  — template rendering + shell config generation
├── backup.py              64 lines  — pre-step timestamped backups
└── README.md                        — this file
```

---

## Per-File Documentation

### `__init__.py` — Re-exports (60 lines)

Re-exports all public and private symbols from all execution modules:

```python
from src.core.services.tool_install.execution import (
    _run_subprocess, _execute_package_step, save_plan_state, update_tool
)
```

### `step_executors.py` — Step Type Dispatchers (994 lines)

The largest execution file. 14 step type executors + rollback handler.
Each takes a step dict plus keyword args and returns a result dict.

| Executor | Step Type | What It Does |
|----------|-----------|-------------|
| `_execute_package_step` | `packages` | apt-get/dnf/brew install (skips already-installed) |
| `_execute_repo_step` | `repo_setup` | Add PPA, import GPG key, add repo source |
| `_execute_command_step` | `tool`, `post_install` | Run command (with curl|bash safety interception) |
| `_execute_verify_step` | `verify` | Check tool exists on PATH + exit code 0 |
| `_execute_config_step` | `config` | Write/append/ensure_line/template on config files |
| `_execute_shell_config_step` | `shell_config` | Add PATH/env lines to .bashrc/.zshrc (idempotent) |
| `_execute_service_step` | `service` | systemctl/openrc/initd start/stop/restart/enable |
| `_execute_download_step` | `download` | Download with resume, disk check, checksum verify |
| `_execute_github_release_step` | `github_release` | Download + extract GitHub release binary |
| `_execute_install_step` | `install` | `make install` / `cmake --install` in build dir |
| `_execute_cleanup_step` | `cleanup` | Remove build artifacts (non-fatal on failure) |
| `_execute_notification_step` | `notification` | Pass-through message to frontend (always succeeds) |
| `_execute_rollback` | (rollback) | Best-effort undo of completed steps |

**config step actions:**

| Action | Description |
|--------|-------------|
| `write` | Overwrite file entirely |
| `append` | Append content |
| `ensure_line` | Add line if not present (grep first) |
| `template` | Validate inputs → render `{var}` → validate output → write |

### `build_helpers.py` — Build-from-Source (633 lines)

Generates build plans for autotools, cmake, and cargo-git projects.
Validates toolchain and resource requirements before starting.

| Function | What It Does |
|----------|-------------|
| `_validate_toolchain(requires)` | Check build tools on PATH (gcc, cmake, etc.) → `{ok, missing, suggestion}` |
| `_check_build_resources(disk, ram, dir)` | Check disk/RAM availability for build |
| `_substitute_build_vars(cmd, vars)` | Replace `{nproc}`, `{build_dir}` etc. in commands |
| `_substitute_install_vars(cmd, profile, ...)` | Replace `{arch}`, `{os}`, `{version}` in install commands |
| `_autotools_plan(recipe, profile, dir)` | Generate ./configure → make → make install steps |
| `_cmake_plan(recipe, profile, dir)` | Generate cmake -B → cmake --build → cmake --install steps |
| `_cargo_git_plan(recipe, profile)` | Generate single cargo install --git step |
| `_build_tarball_download_cmd(url, dest)` | Build download+extract command (curl → wget → python3 fallback) |
| `_execute_source_step(step)` | Obtain source: git clone, tarball download, or local path |
| `_execute_build_step(step)` | Run build with parallel jobs, progress parsing, failure analysis |

### `chain_state.py` — Remediation Chain Lifecycle (381 lines)

Manages escalation chains when remediation itself fails.
Example: "Install ruff → needs pipx → pipx apt failed → ..."

| Function | What It Does |
|----------|-------------|
| `create_chain(tool_id, plan, failed_step)` | Start new chain at depth 0 with empty escalation stack |
| `escalate_chain(chain, failure_id, option_id, option)` | Push escalation level (with cycle and depth-3 guard) |
| `de_escalate_chain(chain)` | Pop top level (fix succeeded) → return to parent |
| `mark_chain_executing(chain)` | Set current top-of-stack status to "executing" |
| `mark_chain_failed(chain, error)` | Set current top-of-stack status to "failed" |
| `mark_chain_done(chain)` | Mark entire chain as done (original goal completed) |
| `cancel_chain(chain_id)` | Cancel chain by ID |
| `get_breadcrumbs(chain)` | Build UI breadcrumb trail: 🎯 Install ruff → 🔓 Install pipx → ... |
| `save_chain(chain)` | Persist to `.state/remediation_chains/{chain_id}.json` |
| `load_chain(chain_id)` | Load from disk (restores sets) |
| `list_pending_chains()` | Find all active (non-done, non-cancelled) chains |
| `archive_chain(chain_id)` | Move completed chain to archive/ subdirectory |

**Safety guards:**
- `MAX_CHAIN_DEPTH = 3` — prevents infinite escalation
- Cycle detection — refuses to escalate if tool already in chain stack

### `offline_cache.py` — Airgapped Install Cache (318 lines)

Pre-downloads all artifacts needed by a plan for offline installation.

| Function | What It Does |
|----------|-------------|
| `get_cache_dir()` | Resolve cache directory (`~/.cache/devops-cp/install-cache`) |
| `cache_plan(plan, cache_dir)` | Walk plan steps, download all artifacts to cache |
| `load_cached_artifacts(tool, cache_dir)` | Load manifest for a cached tool |
| `install_from_cache(step, cached_artifact)` | Modify step to use local file instead of downloading |
| `clear_cache(tool, cache_dir)` | Clear cache for one tool or all |
| `cache_status(cache_dir)` | Report cached tools + sizes |
| `_download_to_cache(url, dest, checksum, timeout)` | Download URL with optional checksum verification |

### `tool_management.py` — Tool Lifecycle (254 lines)

Update and remove operations for installed tools.

| Function | What It Does |
|----------|-------------|
| `update_tool(tool, sudo_password)` | Update via recipe's update command map. Records before/after versions. |
| `remove_tool(tool, sudo_password)` | Remove via recipe's remove map → UNDO_COMMANDS → binary deletion fallback |

**Update flow:** Recipe lookup → resolve method → record version → run command → record new version → audit log
**Remove resolution:** 1) Recipe `remove` map, 2) UNDO_COMMANDS by install method, 3) Binary deletion

### `subprocess_runner.py` — Command Execution (234 lines)

The **single bottleneck** for ALL subprocess calls. Two modes:

| Function | Mode | What It Does |
|----------|------|-------------|
| `_run_subprocess(cmd, ...)` | Blocking | `subprocess.run()` → returns `{ok, stdout, stderr, elapsed_ms}` |
| `_run_subprocess_streaming(cmd, ...)` | Streaming | `Popen` + live line yield → `{line}` then `{done, ok, exit_code}` |

**Security invariants (both modes):**
- `sudo -S -k` — password via stdin, cached credentials invalidated every time
- Password NEVER appears in command args
- Password NEVER logged or written to disk
- Wrong password detection via stderr parsing

**Streaming mode** merges stdout+stderr into one stream (cargo writes
compilation progress to stderr, not stdout).

### `plan_state.py` — Plan Persistence (219 lines)

Saves plan execution state to disk for resumability.

| Function | What It Does |
|----------|-------------|
| `_plan_state_dir()` | Resolve state dir: `.state/install_plans/` → fallback `~/.local/share/` |
| `save_plan_state(state)` | Write to disk with password redaction |
| `load_plan_state(plan_id)` | Load from disk (returns None if missing/corrupt) |
| `list_pending_plans()` | Find plans with status paused/running/failed |
| `cancel_plan(plan_id)` | Mark plan as cancelled |
| `resume_plan(plan_id)` | Load, skip completed steps, return remaining |
| `archive_plan(plan_id)` | Move to archive/ subdirectory |

### `script_verify.py` — curl|bash Safety (215 lines)

Intercepts curl-pipe-bash commands, downloads the script first,
verifies SHA256 hash, then executes the local copy.

| Function | What It Does |
|----------|-------------|
| `is_curl_pipe_command(command)` | Detect `bash -c "curl ... \| bash"` pattern |
| `extract_script_url(command)` | Extract the download URL from curl command |
| `download_and_verify_script(url, sha256, timeout)` | Download to tempfile → compute hash → verify → return path |
| `rewrite_curl_pipe_to_safe(command, script_path)` | Rewrite to `bash /tmp/verified.sh [args]` |
| `cleanup_script(path)` | Delete the temp script |

### `download.py` — Download Utilities (141 lines)

GitHub release resolution and checksum verification.

| Function | What It Does |
|----------|-------------|
| `_verify_checksum(path, expected)` | Verify file hash (`sha256:abc...`, `sha1:...`, `md5:...`) |
| `_resolve_github_release_url(repo, ...)` | Fetch GitHub API → find matching asset by arch/os pattern |

### `config.py` — Template Rendering (97 lines)

Template rendering with built-in variables and shell config generation.

| Function | What It Does |
|----------|-------------|
| `_render_template(template, inputs)` | Replace `{var}` with built-in + user inputs. Builtins: user, home, arch, distro, nproc |
| `_shell_config_line(shell_type, ...)` | Generate bash/zsh/fish export line for PATH or env var |

### `backup.py` — Pre-Step Backup (64 lines)

Creates timestamped backups before risky modifications.

| Function | What It Does |
|----------|-------------|
| `_backup_before_step(step, sudo_password)` | Copy `step["backup_before"]` paths to `PATH.bak.YYYYMMDD_HHMMSS` |

---

## Dependency Graph

```
__init__.py          ← re-exports from all modules below

step_executors.py
   ├── subprocess_runner._run_subprocess()
   ├── script_verify (is_curl_pipe_command, download_and_verify_script, ...)
   ├── detection.check_system_deps()      (L3 — for package skip optimization)
   ├── detection._detect_init_system()    (L3 — for service step dispatch)
   ├── detection.deep_detect()            (L3 — for download disk check)
   ├── domain.input_validation            (L1 — for template validation)
   ├── config._render_template()
   ├── config._shell_config_line()
   ├── backup._backup_before_step()
   └── download._resolve_github_release_url()

build_helpers.py
   ├── subprocess_runner._run_subprocess()
   ├── detection.detect_build_toolchain() (L3)
   ├── detection._read_available_ram_mb() (L3)
   └── detection._read_disk_free_mb()     (L3)

chain_state.py      ← standalone (json, pathlib, uuid)
offline_cache.py    ← subprocess, urllib (for downloads)
tool_management.py  ← data.recipes, data.undo_catalog, detection.tool_version, resolver.method_selection
plan_state.py       ← standalone (json, pathlib, uuid)
script_verify.py    ← standalone (hashlib, subprocess, tempfile)
download.py         ← standalone (hashlib, urllib, subprocess)
config.py           ← data.profile_maps._PROFILE_MAP
backup.py           ← subprocess_runner._run_subprocess()
```

---

## Key Data Shapes

### _run_subprocess() success

```python
{"ok": True, "stdout": "...", "elapsed_ms": 2340}
```

### _run_subprocess() failure

```python
{
    "ok": False,
    "error": "Command failed (exit 1)",
    "stderr": "E: Unable to locate package ...",
    "stdout": "",
    "elapsed_ms": 450,
}
```

### _run_subprocess() sudo needed

```python
{"ok": False, "needs_sudo": True, "error": "This step requires sudo."}
```

### save_plan_state() input

```python
{
    "plan_id": "550e8400-e29b-...",
    "tool": "cargo-audit",
    "status": "running",  # paused | running | done | failed | cancelled
    "steps": [...],
    "completed_steps": [0, 1, 2],
    "current_step": 3,
}
```

### chain escalation

```python
{
    "chain_id": "770e...",
    "original_goal": {"tool": "ruff", "failed_step_idx": 0},
    "escalation_stack": [
        {"failure_id": "pep668", "chosen_option_id": "install_pipx", "status": "executing"},
    ],
    "depth": 1,
    "tools_seen": {"ruff", "pipx"},  # cycle detection
}
```

---

## Design Decisions

### Why subprocess_runner is a single bottleneck

Every subprocess call goes through one function. This centralizes:
- Sudo handling (password via stdin, `-S -k`)
- Environment management (PATH, env_overrides)
- Timeout enforcement
- Error formatting
- Audit logging potential

Without this, sudo security invariants would need to be replicated
in every executor.

### Why streaming mode merges stdout+stderr

Cargo, Rust's package manager, writes compilation progress to stderr
(not stdout). If we separated the streams, the streaming UI would
miss all build progress. Merging via `stderr=STDOUT` gives a single
chronological stream that captures everything.

### Why chain_state has a depth-3 limit

Remediation chains can recurse: "Install ruff → needs pipx → pipx
needs apt → apt needs internet". Without a limit, this could recurse
infinitely. Depth 3 is sufficient for real-world scenarios while
preventing runaway escalation.

### Why plan_state redacts passwords

Plan state is persisted to disk as JSON. Password-type input values
(e.g., sudo password, database password for config templates) must
NEVER be written to disk in plaintext. The save function strips these
values to `***REDACTED***` before persistence.

### Why offline_cache exists

Airgapped environments (secure networks, production servers, CI
runners) can't download during installation. `cache_plan()` downloads
everything ahead of time, and `install_from_cache()` rewrites steps
to use local files. This makes "install at 3am from USB stick" possible.

---

## Advanced Feature Showcase

### 1. curl|bash Safety Interception

```python
# script_verify.py — transparently replaces unsafe curl|bash
cmd = ["bash", "-c", "curl -fsSL https://sh.rustup.rs | sh -s -- -y"]

if is_curl_pipe_command(cmd):
    url = extract_script_url(cmd)                    # "https://sh.rustup.rs"
    result = download_and_verify_script(url, "abc...") # download → hash → verify
    if result["ok"]:
        safe_cmd = rewrite_curl_pipe_to_safe(cmd, result["path"])
        # → ["bash", "/tmp/devops_cp_script_xxx.sh", "-s", "--", "-y"]
        cleanup_script(result["path"])               # cleanup after execution
```

### 2. Config Template Pipeline

```python
# step_executors._execute_config_step() — 4-stage pipeline
# Action "template":
#   1. Validate inputs (_validate_input for each recipe input)
#   2. Render template (_render_template: {user} → "jfortin", {arch} → "amd64")
#   3. Validate output (_validate_output: parse as JSON/YAML/INI)
#   4. Write file + apply chmod/chown
```

### 3. Download with Resume + Disk Check + Checksum

```python
# step_executors._execute_download_step()
# 1. Check disk space: file_size < available × 0.9
# 2. Resume: if partial file exists, attempt HTTP Range header
# 3. Download via curl (with progress)
# 4. Verify checksum: sha256:abc123...
# 5. Extract if tarball (tar xzf)
```

### 4. Remediation Chain Breadcrumbs

```python
# chain_state.py — escalation tracking
chain = create_chain("ruff", plan, failed_step_idx=0)
escalate_chain(chain, "pep668", "install_pipx")
escalate_chain(chain, "apt_locked", "kill_dpkg")
breadcrumbs = get_breadcrumbs(chain)
# → [
#     {"type": "goal",  "label": "Install ruff",      "depth": 0},
#     {"type": "fix",   "label": "Install pipx",      "depth": 1},
#     {"type": "fix",   "label": "Kill dpkg lock",    "depth": 2},
# ]
```

### 5. Build Plan Generation (3 build systems)

```python
# build_helpers.py — autotools, cmake, cargo-git
steps = _autotools_plan(recipe, profile, "/tmp/build")
# → [
#     {"type": "build", "command": ["./configure", "--prefix=/usr/local"]},
#     {"type": "build", "command": ["make", "-j8"], "parallel": True},
#     {"type": "install", "command": ["make", "install"], "needs_sudo": True},
# ]

steps = _cmake_plan(recipe, profile, "/tmp/build")
# → cmake -B build → cmake --build build -j8 → cmake --install build
```

### 6. Multi-Init Service Management

```python
# step_executors._execute_service_step()
# Detects init system → dispatches to right command:
#   systemd → systemctl start/enable docker
#   openrc  → rc-service docker start + rc-update add docker
#   initd   → /etc/init.d/docker start
```

---

## Coverage Summary

| Capability | File | Scope |
|-----------|------|-------|
| Step types | `step_executors.py` | 14 types + rollback |
| Build systems | `build_helpers.py` | autotools, cmake, cargo-git |
| Chain management | `chain_state.py` | create/escalate/de-escalate, depth-3 limit, cycle guard |
| Offline install | `offline_cache.py` | Plan caching, artifact rewriting, cache status |
| Tool lifecycle | `tool_management.py` | Update (version tracking), remove (3-tier resolution) |
| Subprocess | `subprocess_runner.py` | Blocking + streaming, sudo security, env overrides |
| Plan state | `plan_state.py` | CRUD + resume + archive, password redaction |
| Script safety | `script_verify.py` | curl\|bash interception, SHA256 verification |
| Downloads | `download.py` | GitHub releases (API), checksum (sha256/sha1/md5) |
| Templates | `config.py` | 6 built-in vars, shell config (bash/zsh/fish) |
| Backups | `backup.py` | Timestamped cp -rp, non-fatal on failure |
| Init systems | `step_executors.py` | systemd, openrc, initd |
