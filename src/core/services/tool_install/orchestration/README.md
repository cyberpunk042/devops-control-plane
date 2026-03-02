# L5 Orchestration — Plan Lifecycle

> **3 files · 994 lines · Composes L2 (resolve) + L4 (execute).**
>
> Plan lifecycle: create → execute → persist → resume.
> These are the entry points external code calls.
> No direct subprocess/filesystem access — delegates everything to L4.

---

## How It Works

### Execution Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ L5 ORCHESTRATION                                              │
│                                                               │
│  TWO EXECUTION MODES                                          │
│                                                               │
│  1. BLOCKING (API / CLI)                                      │
│     orchestrator.py                                           │
│     ├── install_tool()        — resolve + execute (one call)  │
│     ├── execute_plan()        — linear step-by-step           │
│     ├── execute_plan_dag()    — parallel (thread pool)        │
│     └── execute_plan_step()   — single step dispatch          │
│                                                               │
│  2. STREAMING (SSE / Web UI)                                  │
│     stream.py                                                 │
│     └── stream_step_execution() — yields event dicts          │
│         ├── step_start                                        │
│         ├── log (line-by-line subprocess output)              │
│         ├── step_done / step_failed                           │
│         ├── network_warning                                   │
│         └── done (with restart detection)                     │
│                                                               │
│  SHARED INVARIANTS                                            │
│  ├── Both persist plan state after every step                 │
│  ├── Both accumulate post_env across steps                    │
│  ├── Both delegate to L4 execute_plan_step() for dispatch     │
│  └── Both run failure analysis on step failures               │
└──────────────────────────────────────────────────────────────┘
```

### Plan Lifecycle

```
    resolve_install_plan()          ← L2: produce plan
           │
           ▼
    User reviews plan in UI
           │
           ▼
    execute_plan_dag()              ← L5: execute
    ├── save_plan_state(running)    ← L4: persist progress
    ├── step 1: execute + save
    ├── step 2: execute + save
    │   ├── FAILURE → _analyse_install_failure() → remediation
    │   └── INTERRUPT → plan saved, resumable
    ├── step N: execute + save
    └── save_plan_state(done)       ← L4: mark complete
           │
           ▼
    verify step confirms install    ← L4: exit 0 check
```

On interruption (browser close, network failure, system restart):

```
    list_pending_plans()            ← L4: find saved plans
           │
           ▼
    resume_plan(plan_id)            ← L4: load state
           │
           ▼
    stream_step_execution()         ← L5: continue from last completed step
```

### Step Dispatch Table

```
execute_plan_step(step)
    │
    step["type"]
    │
    ├── "packages"       → _execute_package_step()
    ├── "repo_setup"     → _execute_repo_step()
    ├── "tool"           → _execute_command_step()
    ├── "post_install"   → _execute_command_step()
    ├── "verify"         → _execute_verify_step()
    ├── "config"         → _execute_config_step()
    ├── "shell_config"   → _execute_shell_config_step()
    ├── "service"        → _execute_service_step()
    ├── "download"       → _execute_download_step()
    ├── "github_release" → _execute_github_release_step()
    ├── "source"         → _execute_source_step()     (from build_helpers)
    ├── "build"          → _execute_build_step()      (from build_helpers)
    ├── "install"        → _execute_install_step()
    ├── "cleanup"        → _execute_cleanup_step()
    └── "notification"   → _execute_notification_step()
```

---

## File Map

```
orchestration/
├── __init__.py        12 lines  — re-exports 4 top-level coordinator functions
├── orchestrator.py   671 lines  — blocking: install_tool, execute_plan, execute_plan_dag
├── stream.py         311 lines  — streaming: SSE event generator for web UI
└── README.md                    — this file
```

---

## Per-File Documentation

### `__init__.py` — Re-exports (12 lines)

Re-exports the 4 top-level coordinator functions:

```python
from src.core.services.tool_install.orchestration import (
    execute_plan, execute_plan_dag, execute_plan_step, install_tool
)
```

### `orchestrator.py` — Blocking Execution Coordinators (671 lines)

The main entry points for tool installation. External code calls these.

| Function | What It Does |
|----------|-------------|
| `execute_plan_step(step, ...)` | Dispatch single step by `step["type"]` to the matching L4 executor |
| `execute_plan(plan, ...)` | Execute plan linearly (step-by-step in order). Accumulates `post_env`, handles backup, remediation. |
| `execute_plan_dag(plan, ...)` | Execute plan with DAG-aware parallelism (ThreadPoolExecutor). PM lock safety. Progress callback. |
| `install_tool(tool, ...)` | Single-call convenience: resolve plan + execute all steps. Backward-compatible wrapper. |

**`execute_plan_step()` dispatch logic:**

Maps `step["type"]` to the corresponding L4 executor function (14 types).
Also handles:
- `backup_before` → `_backup_before_step()` before risky steps
- `env_overrides` → passed through for PATH-modified environments
- Rollback type → `_execute_rollback()` for undo operations

**`execute_plan()` lifecycle:**

1. Save plan state as "running"
2. For each step:
   - Execute via `execute_plan_step()`
   - Accumulate `post_env` into env_overrides for subsequent steps
   - On failure: run `_analyse_install_failure()` → emit remediation
   - Save plan state after each step
3. Mark plan state as "done" or "failed"
4. Detect restart needs → return restart actions

**`execute_plan_dag()` parallel execution:**

1. `_add_implicit_deps()` — PM lock constraints
2. `_validate_dag()` — cycle detection
3. Loop until all done or failure:
   - `_get_ready_steps()` — find steps with satisfied dependencies
   - `_enforce_parallel_safety()` — one PM at a time
   - Submit ready steps to `ThreadPoolExecutor`
   - Collect results, track completed/failed sets
4. Save final state

**`install_tool()` backward-compatible wrapper:**

1. Recipe lookup → `resolve_install_plan()`
2. If plan has errors → return error
3. `execute_plan()` → return aggregate result
4. Special handling: `override_command` for non-recipe installs

### `stream.py` — SSE Event Generator (311 lines)

Streaming executor used by the web UI's SSE endpoints.
Yields event dicts — no Flask dependency inside this module.

| Function | What It Does |
|----------|-------------|
| `stream_step_execution(...)` | Core step loop yielding SSE event dicts. Used by both execute and resume routes. |
| `_save_state(plan_id, tool, status, ...)` | Fire-and-forget state persistence after each step |

**SSE event types:**

| Event Type | Payload | When Emitted |
|------------|---------|-------------|
| `step_start` | `{step, label, total}` | Before each step executes |
| `log` | `{step, line}` | Each line of subprocess output (tool/post_install) |
| `step_done` | `{step, elapsed_ms}` or `{step, skipped, message}` | Step completed or skipped |
| `step_failed` | `{step, error}` or `{step, error, needs_sudo}` | Step failed |
| `network_warning` | `{registry, url, error, proxy_detected}` | Pre-flight network issues |
| `done` | `{ok, plan_id, message, restart, remediation}` | All steps finished or fatal failure |

**Streaming vs non-streaming steps:**

| Step Types | Mode | Why |
|-----------|------|-----|
| `tool`, `post_install` | Streaming (`_run_subprocess_streaming`) | Live line-by-line output for cargo/pip builds |
| All others | Blocking (`execute_plan_step`) | Short-lived; stdout emitted after completion |

**Failure handling:**

1. Save plan state as "failed"
2. Check `needs_sudo` → emit sudo prompt event
3. Run `_analyse_install_failure()` for tool/post_install steps
4. Build verify-specific remediation for verify steps
5. Yield `done` event with remediation data

**Restart detection (end of successful execution):**

1. `detect_restart_needs()` → check for PATH/service/kernel/GPU changes
2. `_batch_restarts()` → convert to service steps + notifications
3. Include in `done` event as `restart` + `restart_actions`

---

## Dependency Graph

```
__init__.py          ← re-exports from orchestrator.py only

orchestrator.py
   ├── resolver.plan_resolution.resolve_install_plan()  (L2)
   ├── domain.dag (_add_implicit_deps, _validate_dag, _get_ready_steps, _enforce_parallel_safety)  (L1)
   ├── domain.restart (detect_restart_needs, _batch_restarts)  (L1)
   ├── domain.risk (_infer_risk, _plan_risk)  (L1)
   ├── execution.step_executors (14 executor functions)  (L4)
   ├── execution.build_helpers (_execute_source_step, _execute_build_step)  (L4)
   ├── execution.plan_state (save_plan_state, load_plan_state)  (L4)
   ├── execution.subprocess_runner (_run_subprocess)  (L4)
   ├── execution.backup (_backup_before_step)  (L4)
   └── detection.install_failure (_analyse_install_failure)  (L3)

stream.py
   ├── orchestrator.execute_plan_step()  (local — lazy import)
   ├── execution.subprocess_runner._run_subprocess_streaming()  (L4)
   ├── execution.plan_state.save_plan_state()  (L4)
   ├── detection.install_failure._analyse_install_failure()  (L3)
   └── domain.restart (detect_restart_needs, _batch_restarts)  (L1)
```

---

## Key Data Shapes

### SSE step_start event

```python
{"type": "step_start", "step": 0, "label": "Install build dependencies", "total": 5}
```

### SSE log event

```python
{"type": "log", "step": 0, "line": "   Compiling cargo-audit v0.20.0"}
```

### SSE step_done event

```python
{"type": "step_done", "step": 0, "elapsed_ms": 2340}
```

### SSE done (success with restart)

```python
{
    "type": "done",
    "ok": True,
    "plan_id": "550e8400-e29b-...",
    "message": "rustup installed successfully",
    "steps_completed": 4,
    "restart": {
        "shell_restart": True,
        "service_restart": [],
        "reboot_required": False,
        "reasons": ["PATH was modified — restart shell"],
    },
    "restart_actions": [
        {"type": "notification", "message": "Restart your shell or run: source ~/.bashrc"},
    ],
}
```

### SSE done (failure with remediation)

```python
{
    "type": "done",
    "ok": False,
    "plan_id": "550e8400-e29b-...",
    "error": "Step 2 failed",
    "step": 1,
    "step_label": "Install cargo-audit",
    "remediation": {
        "reason": "Build failed: missing header <openssl/ssl.h>",
        "options": [
            {"label": "Install libssl-dev", "action": "remediate", "command": [...]},
            {"label": "Retry with sudo", "action": "retry"},
        ],
    },
}
```

### execute_plan_dag() result

```python
{
    "ok": True,
    "completed": ["step_0", "step_1", "step_2"],
    "elapsed_ms": 12340,
    "restart": {...},
}
```

### install_tool() result

```python
{
    "ok": True,
    "steps": [
        {"step": 0, "ok": True, "elapsed_ms": 450},
        {"step": 1, "ok": True, "elapsed_ms": 8200},
    ],
    "elapsed_ms": 8650,
}
```

---

## Design Decisions

### Why two execution modes (blocking + streaming)

The CLI and API need blocking execution (call → result). The web UI
needs streaming execution (SSE events for live progress display).
Rather than having the blocking mode wrap the streaming mode (which
would require accumulating all events), each mode is purpose-built
for its consumer.

### Why stream.py has no Flask dependency

`stream_step_execution()` yields plain dicts. The Flask route handler
wraps these in `data: {json}\n\n` for SSE format. This keeps stream.py
testable and reusable — it could work with any SSE transport
(WebSocket, stdio, etc.).

### Why DAG execution uses ThreadPoolExecutor

`execute_plan_dag()` runs independent steps in parallel using threads.
This is appropriate because steps are I/O-bound (subprocess calls,
network downloads). The GIL doesn't matter since the threads spend
most of their time waiting for subprocess completion. Thread count
is bounded by the number of ready steps.

### Why post_env is accumulated across steps

When a step installs to a non-standard path (e.g., `~/.cargo/bin`),
the `post_env` field adds that path to `$PATH`. Subsequent steps in
the same plan need this updated PATH to find the newly installed
binary. Without accumulation, a verify step after `rustup install`
wouldn't find `cargo` on PATH.

### Why streaming mode only streams tool/post_install steps

Package installs, service actions, and config writes are fast
(< 2 seconds). Streaming their output line-by-line would add
overhead without benefit. Tool installs (cargo, pip, npm builds)
can take minutes — streaming their output gives the user confidence
that progress is being made.

---

## Advanced Feature Showcase

### 1. SSE Streaming with Live Build Output

```python
# stream.py — tool/post_install steps use _run_subprocess_streaming
for chunk in _run_subprocess_streaming(cmd, ...):
    if chunk.get("done"):
        result = chunk  # final status
    elif "line" in chunk:
        yield {"type": "log", "step": i, "line": chunk["line"]}
        # Client receives: data: {"type":"log","step":0,"line":"Compiling ..."}
```

### 2. DAG-Aware Parallel Execution

```python
# orchestrator.py — execute_plan_dag()
# Step 0: apt install build-essential  ─┐
# Step 1: apt install libssl-dev        ─┤ (serial: same PM)
# Step 2: download source tarball       ─┤ (parallel: no PM conflict)
# Step 3: build (depends_on: [0,1,2])   ─┘

# _enforce_parallel_safety ensures only one apt step runs at a time
# _get_ready_steps finds steps whose deps are all complete
```

### 3. Post-Step Restart Detection

```python
# stream.py — after all steps complete
restart_needs = detect_restart_needs(
    {"tool": tool, "steps": steps}, completed_step_dicts
)
# → {"shell_restart": True, "service_restart": ["docker"], ...}

restart_actions = _batch_restarts(restart_needs)
# → [{"type": "notification", "message": "Restart your shell"}]

yield {"type": "done", "ok": True, "restart": restart_needs, "restart_actions": restart_actions}
```

### 4. Failure with Remediation Hints

```python
# stream.py — on step failure
remediation = _analyse_install_failure(
    tool, cli, stderr, exit_code=1, method="cargo", system_profile=profile
)
# → {"reason": "Missing openssl headers", "options": [...]}

yield {"type": "done", "ok": False, "remediation": remediation}
# Web UI shows: "Missing openssl headers" + action buttons
```

### 5. Resume from Interruption

```python
# stream.py — step_offset for resume
# If steps 0-2 were completed, step_offset=3
stream_step_execution(
    plan_id=plan_id,
    tool="ruff",
    steps=remaining_steps,    # only steps 3-5
    step_offset=3,            # client sees correct indices
)
# completed_steps starts as [0, 1, 2] — already done before resume
```

---

## Coverage Summary

| Capability | File | Scope |
|-----------|------|-------|
| Step dispatch | `orchestrator.py` | 14 step types + rollback |
| Linear execution | `orchestrator.py` | Sequential with env accumulation |
| DAG execution | `orchestrator.py` | Parallel via ThreadPoolExecutor, PM lock safety |
| Convenience wrapper | `orchestrator.py` | `install_tool()` — resolve + execute in one call |
| SSE streaming | `stream.py` | 6 event types, line-by-line subprocess output |
| Failure analysis | `stream.py` | Remediation hints for tool/post_install/verify failures |
| Restart detection | `stream.py` | Shell/service/reboot after successful completion |
| Plan persistence | `stream.py` | State saved after every step (fire-and-forget) |
| Resume support | `stream.py` | step_offset for correct indexing after resume |
| Network warnings | `stream.py` | Pre-flight registry reachability issues |
