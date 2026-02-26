# Domain: Parallel Execution

> ⚠️ **PHASE LABELS MAY BE STALE** — As of 2026-02-25, code has evolved far beyond
> what the phase roadmaps suggest. Many features labeled "Phase 4-8 future" are
> ALREADY IMPLEMENTED. See `audit-domain-docs.md` and `audit-missing-pieces.md`
> for the verified truth. Code is the source of truth, not these phase labels.


> This document catalogs concurrent step execution for the tool
> install system: DAG-based plan format, depends_on for dependency
> edges, independent steps running in parallel, progress tracking
> for multiple concurrent streams, and the Phase 8 evolution path.
>
> SOURCE DOCS: scope-expansion §2.17 (parallel step execution),
>              domain-choices §step dependencies (depends_on),
>              domain-restart §plan engine state machine

---

## Overview

### Current model (Phase 2): LINEAR

```
step1 → step2 → step3 → step4 → done
```

Every step waits for the previous one. Even if step2 and step3
are completely independent.

### Future model (Phase 8): DAG

```
step1 ──► step2 ──┐
     └──► step3 ──┤──► step5
          step4 ──┘
```

Steps 2, 3, 4 can run in parallel — all depend only on step1.
Step 5 waits for 2, 3, and 4 to complete.

### Phase plan

| Phase | Execution model |
|-------|----------------|
| Phase 2 | Linear only. Steps execute sequentially. |
| Phase 3 | Linear. `depends_on` field exists but ignored. |
| Phase 8 | DAG execution. Parallel dispatch. Progress tracking. |

---

## DAG Plan Format

### depends_on field

```python
"steps": [
    {"id": "deps",    "label": "Install system deps",
     "command": ["apt-get", "install", "-y", "build-essential"],
     "needs_sudo": True},

    {"id": "ruff",    "label": "Install ruff",
     "command": ["pip", "install", "ruff"],
     "depends_on": ["deps"]},

    {"id": "black",   "label": "Install black",
     "command": ["pip", "install", "black"],
     "depends_on": ["deps"]},

    {"id": "mypy",    "label": "Install mypy",
     "command": ["pip", "install", "mypy"],
     "depends_on": ["deps"]},

    {"id": "verify",  "label": "Verify all tools",
     "command": ["bash", "-c", "ruff --version && black --version && mypy --version"],
     "depends_on": ["ruff", "black", "mypy"]},
]
```

### Rules

| Rule | Description |
|------|------------|
| No `depends_on` | Step depends on the PREVIOUS step (linear fallback) |
| `depends_on: []` | Step has no dependencies — runs immediately |
| `depends_on: ["X"]` | Step runs after X completes successfully |
| `depends_on: ["X", "Y"]` | Step runs after BOTH X and Y complete |
| Cycles | Forbidden — detected at plan validation |

---

## Dependency Resolution

### Finding ready steps

```python
def get_ready_steps(steps: list[dict],
                     completed: set[str],
                     running: set[str]) -> list[dict]:
    """Find steps that are ready to execute."""
    ready = []
    for step in steps:
        sid = step["id"]
        if sid in completed or sid in running:
            continue
        deps = step.get("depends_on", [])
        if all(d in completed for d in deps):
            ready.append(step)
    return ready
```

### DAG validation

```python
def validate_dag(steps: list[dict]) -> list[str]:
    """Validate plan DAG. Returns list of errors."""
    errors = []
    ids = {s["id"] for s in steps}

    for step in steps:
        for dep in step.get("depends_on", []):
            if dep not in ids:
                errors.append(
                    f"Step '{step['id']}' depends on unknown step '{dep}'"
                )

    # Cycle detection (topological sort)
    if _has_cycle(steps):
        errors.append("Plan contains dependency cycle")

    return errors


def _has_cycle(steps: list[dict]) -> bool:
    """Detect cycles using Kahn's algorithm."""
    in_degree = {s["id"]: 0 for s in steps}
    adjacency = {s["id"]: [] for s in steps}

    for step in steps:
        for dep in step.get("depends_on", []):
            adjacency[dep].append(step["id"])
            in_degree[step["id"]] += 1

    queue = [sid for sid, deg in in_degree.items() if deg == 0]
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return visited != len(steps)
```

---

## Execution Engine

### Parallel dispatcher

```python
import asyncio

async def execute_plan_parallel(plan: dict,
                                 on_progress: Callable) -> dict:
    """Execute a plan with parallel step support."""
    steps = plan["steps"]
    completed: set[str] = set()
    failed: set[str] = set()
    running: dict[str, asyncio.Task] = {}

    while len(completed) + len(failed) < len(steps):
        # Find steps ready to run
        ready = get_ready_steps(steps, completed, set(running.keys()))

        # Dispatch ready steps
        for step in ready:
            if step["id"] not in running:
                task = asyncio.create_task(_run_step(step))
                running[step["id"]] = task
                on_progress(step["id"], "started")

        if not running:
            break  # Deadlock — no steps can run

        # Wait for ANY running step to complete
        done, _ = await asyncio.wait(
            running.values(),
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in done:
            # Find which step completed
            step_id = _find_step_id(task, running)
            del running[step_id]

            if task.result()["ok"]:
                completed.add(step_id)
                on_progress(step_id, "done")
            else:
                failed.add(step_id)
                on_progress(step_id, "failed")

    return {
        "completed": list(completed),
        "failed": list(failed),
        "skipped": [s["id"] for s in steps
                    if s["id"] not in completed and s["id"] not in failed],
    }
```

### Failure propagation

When a step fails, steps that depend on it are SKIPPED:

```
step1 ──► step2 ──► step4   (step2 fails)
     └──► step3 ──► step5

Result:
  step1: ✅ done
  step2: ❌ failed
  step3: ✅ done
  step4: ⏭️ skipped (depends on failed step2)
  step5: ✅ done (depends only on step3)
```

---

## When Parallelism Helps

### Good candidates for parallel execution

| Scenario | Steps | Speedup |
|----------|-------|---------|
| Multiple pip installs | `pip install A`, `pip install B` | 2x (IO-bound) |
| pip + apt concurrent | `pip install X` while `apt install Y` | Significant |
| Build from source + download | `make` while downloading data | Full overlap |
| Multiple cargo installs | `cargo install A`, `cargo install B` | 2x (CPU-bound) |

### Poor candidates (must stay sequential)

| Scenario | Why sequential |
|----------|---------------|
| apt-get install A, apt-get install B | apt holds dpkg lock — can't parallel |
| dnf install A, dnf install B | dnf holds RPM lock |
| pip install with deps | Dependency resolution conflicts |
| Service start → verify | Verify needs service running |
| Config write → service restart | Restart needs config written |
| Install → add to group | Group needs package installed |

### Lock-aware scheduling

```python
# Some package managers hold exclusive locks
PM_LOCKS = {
    "apt": "/var/lib/dpkg/lock",
    "dnf": "/var/cache/dnf/metadata_lock.pid",
    "pacman": "/var/lib/pacman/db.lck",
    "snap": "/run/snapd/lock",
}

def _can_parallel(step_a: dict, step_b: dict) -> bool:
    """Check if two steps can run in parallel."""
    # Same PM lock → sequential
    lock_a = _get_pm_lock(step_a)
    lock_b = _get_pm_lock(step_b)
    if lock_a and lock_b and lock_a == lock_b:
        return False

    # Both need sudo → may conflict on password prompt
    if step_a.get("needs_sudo") and step_b.get("needs_sudo"):
        return False  # Phase 8: handle with session caching

    return True
```

---

## Progress Tracking

### Multi-stream progress

```
┌─ Install Plan (3/5 steps) ──────────────────────┐
│                                                    │
│ ✅ Install system deps           done   (12s)     │
│ 🔄 Install ruff                  running ━━━━━━░░ │
│ 🔄 Install black                 running ━━░░░░░░ │
│ 🔄 Install mypy                  running ━━━━━░░░ │
│ ⏳ Verify all tools              waiting          │
│                                                    │
│ ⏱️ Elapsed: 45s  │  ETA: ~30s                     │
└────────────────────────────────────────────────────┘
```

### SSE events for parallel steps

```python
# Each step sends its own SSE stream
# Frontend multiplexes by step_id

def sse_event(step_id: str, event_type: str, data: str):
    return f"data: {json.dumps({
        'step_id': step_id,
        'type': event_type,     # 'started' | 'output' | 'done' | 'failed'
        'data': data,
    })}\n\n"
```

### Frontend multiplexing

```javascript
// Track multiple concurrent steps
const stepStates = {};

eventSource.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    const {step_id, type, data} = msg;

    if (type === 'started') {
        stepStates[step_id] = {status: 'running', output: ''};
        updateUI(step_id, 'running');
    } else if (type === 'output') {
        stepStates[step_id].output += data;
        updateStepLog(step_id, data);
    } else if (type === 'done') {
        stepStates[step_id].status = 'done';
        updateUI(step_id, 'done');
    } else if (type === 'failed') {
        stepStates[step_id].status = 'failed';
        updateUI(step_id, 'failed');
    }
};
```

---

## Resource Limits

### Concurrency limits

```python
MAX_PARALLEL_STEPS = 4     # Don't overwhelm the system
MAX_PARALLEL_DOWNLOADS = 2 # Bandwidth sharing
MAX_PARALLEL_BUILDS = 1    # CPU-intensive (unless high core count)

# Dynamic based on system
import os
cpu_count = os.cpu_count() or 2
MAX_PARALLEL_BUILDS = max(1, cpu_count // 4)
```

### Memory awareness

```python
# Don't run multiple large builds in parallel
def _memory_ok_for_parallel(steps: list[dict]) -> bool:
    total_mem_needed = sum(
        s.get("estimated_memory_mb", 100) for s in steps
    )
    available_mb = _get_available_memory_mb()
    return total_mem_needed < available_mb * 0.8  # 80% threshold
```

---

## Linear Fallback

### Phase 2 compatibility

When `depends_on` is absent, steps execute linearly:

```python
def _add_implicit_deps(steps: list[dict]) -> list[dict]:
    """Add implicit linear dependencies when depends_on is absent."""
    for i, step in enumerate(steps):
        if "depends_on" not in step and i > 0:
            step["depends_on"] = [steps[i - 1]["id"]]
    return steps
```

### Opt-in parallelism

Parallelism is EXPLICIT. A step without `depends_on` runs
linearly. To enable parallelism, the recipe author must
specify `depends_on` with the actual dependencies.

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| All steps depend on each other | Fully linear, no parallelism | Works correctly (DAG degrades to chain) |
| Circular dependency | Plan can't execute | Cycle detection at validation |
| Parallel sudo calls | Password prompt conflict | Serialize sudo steps or cache password |
| Parallel steps + restart | Which step triggers restart? | Batch: restart after all parallel steps done |
| One parallel step fails | Others still running | Let running steps finish, skip dependents |
| Resource exhaustion | OOM or CPU overload | Concurrency limits (MAX_PARALLEL) |
| apt lock conflict | Second apt call fails | PM lock detection prevents parallel |
| Mixed risk levels in parallel | Confirmation for one blocks others | Confirm all before dispatching any |
| SSE multiplexing | Frontend complexity | step_id tags in every event |

---

## Traceability

| Topic | Source |
|-------|--------|
| Linear → DAG evolution | scope-expansion §2.17 |
| depends_on field | scope-expansion §2.17 (plan format) |
| Step IDs | scope-expansion §2.17 (step1, step2, etc.) |
| Phase 8 target | scope-expansion §Phase 8 |
| Plan engine states | domain-restart §state machine |
| SSE streaming | tool_install.py (current SSE pattern) |
| apt lock file | domain-package-managers §apt |
| Resource detection | domain-hardware-detect §RAM, CPU |
