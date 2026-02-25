# L5 Orchestration — Plan Lifecycle

> Composes L2 (resolve) + L4 (execute).
> Plan lifecycle: create → execute → persist → resume.
> These are the entry points external code calls.

---

## Files

### `orchestrator.py` — Execution Coordinators

**Functions:**
| Function | What it does |
|----------|-------------|
| `install_tool(tool, sudo_password)` | Single-call convenience: resolve + execute |
| `execute_plan_dag(plan, sudo_password)` | Execute plan respecting DAG ordering |
| `execute_plan_step(step, sudo_password)` | Execute one step via type dispatch |
| `execute_plan(plan, sudo_password)` | Execute plan linearly (step by step) |

```python
from src.core.services.tool_install.orchestration.orchestrator import install_tool

# Resolves plan, executes all steps, returns aggregate result
result = install_tool("cargo-audit", sudo_password="...")
# → {"ok": True, "steps": [...], "elapsed_ms": 45000}
```

### How `execute_plan_step` dispatches:

```
step["type"]
    ↓
┌─────────────────────────────┐
│ "packages"  → _execute_package_step       │
│ "repo_setup"→ _execute_repo_step          │
│ "tool"      → _execute_command_step       │
│ "verify"    → _execute_verify_step        │
│ "config"    → _execute_config_step        │
│ "service"   → _execute_service_step       │
│ ... 14 types total ...                    │
└─────────────────────────────┘
```

### DAG Execution

`execute_plan_dag` uses `domain/dag.py` to:
1. Add implicit dependencies (PM lock constraints)
2. Validate the DAG (no cycles, no missing deps)
3. Execute ready steps in parallel
4. Wait for each step to complete before unlocking dependents

This enables parallel downloads, parallel builds for independent tools,
while preventing two `apt-get install` calls from running simultaneously
(which would deadlock on dpkg lock).

---

## Plan Lifecycle

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
    execute_plan_dag()              ← L5: continue from last completed step
```
