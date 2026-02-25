# Tier 4 — Advanced Features Analysis

> **Created: 2026-02-24 (evening)**
>
> Pre-implementation analysis for Tier 4.

---

## Scope Assessment

From the status doc, Tier 4 contains:

| # | Feature | Complexity | Domain Docs |
|---|---------|-----------|-------------|
| 9 | DAG execution engine | HIGH | Phase 8 §DAG Execution Engine |
| 10 | State persistence | MEDIUM | domain-restart §State Persistence |
| 11 | Frontend phases 5–8 | HIGH | Multiple docs |

### Reality Check

**Item 11 (Frontend)** is HTML/JS/CSS — completely different domain
from this backend Python session. It also has broad dependencies across
the whole UI codebase. **Deferred** — it's a multi-day effort.

**Items 9 and 10** are pure backend Python in `tool_install.py`.
They fit our pattern perfectly.

---

## What To Implement

### Phase A: State Persistence (simpler, high leverage)

State persistence is the foundation that DAG execution needs. If a
plan pauses on restart, state must be saved. This also enables
`start_from` resume in the existing `execute_plan()`.

**Functions to implement:**

| Function | Purpose |
|----------|---------|
| `_plan_state_dir()` | Resolve and create `~/.local/share/devops-control-plane/plans/` |
| `save_plan_state(plan_id, state)` | Write plan state JSON to disk |
| `load_plan_state(plan_id)` | Load plan state from disk |
| `list_pending_plans()` | Find paused/pending plans |
| `cancel_plan(plan_id)` | Mark a plan as cancelled |
| `archive_plan(plan_id)` | Move completed/cancelled plan to archive |

**State schema** (from domain-restart §State Persistence):

```python
{
    "plan_id": "uuid-...",
    "tool": "docker",
    "status": "paused",       # created|running|paused|done|failed|cancelled
    "started_at": "ISO8601",
    "paused_at": "ISO8601",
    "pause_reason": "session_restart",
    "current_step": 4,
    "steps": [...],           # Full step list with per-step status
    "inputs": {...},          # User-provided values
    "system_profile_snapshot": {...},
}
```

### Phase B: DAG Execution Engine

Adds parallel execution capability on top of the existing linear
`execute_plan()`.

**Functions to implement:**

| Function | Purpose |
|----------|---------|
| `_add_implicit_deps(steps)` | Add linear deps for steps without `depends_on` |
| `_validate_dag(steps)` | Check for cycles, missing refs |
| `_get_ready_steps(steps, completed, running)` | Find steps whose deps are all done |
| `_enforce_parallel_safety(steps)` | Prevent same-PM conflicts |
| `execute_plan_dag(plan, ...)` | Main DAG executor |

**Key design from Phase 8 spec:**
- Steps get IDs (auto-generated if missing)
- `depends_on` is optional — steps without it get implicit linear deps
- Package manager steps can't run in parallel (lock conflicts)
- The existing `execute_plan_step()` is reused — DAG is just orchestration

### Phase C: Wire Restart Detection into execute_plan

Currently `execute_plan()` doesn't check `restart_required` on steps.
It should:
1. After executing a step with `restart_required`, save state and pause
2. Return `{ok: false, paused: true, pause_reason: "..."}` 
3. On resume, load state and continue from `current_step`

---

## Implementation Order

1. **Phase A: State Persistence** (~120 lines)
   - Pure file I/O, no dependencies, enables everything else
   
2. **Phase B: DAG Engine** (~150 lines)  
   - Depends on Phase A for state saves during execution
   - Builds on existing `execute_plan_step()` 
   
3. **Phase C: Restart Wire-up** (~40 lines)
   - Modify `execute_plan()` to save state on restart_required
   - Small change, high value

---

## Deferred

| Item | Reason |
|------|--------|
| Frontend phases 5–8 | Different domain (HTML/JS), multi-day effort |
| Data pack recipes (28) | Needs multi-select UI from frontend |
| Async parallel execution | Spec shows `asyncio` but our current execution is synchronous. Use threading for now. |

---

## Traceability

| This analysis | References |
|---------------|-----------|
| State persistence format | domain-restart §State Persistence |
| Plan state machine | domain-restart §Plan Engine State Machine |
| DAG execution | Phase 8 §DAG Execution Engine |
| Parallel safety | Phase 8 §_enforce_parallel_safety |
| Step IDs and depends_on | Phase 8 §Plan Format Extension |
