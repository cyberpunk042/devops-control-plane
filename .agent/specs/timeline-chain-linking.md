# Timeline Chain Linking — Spec

> Status: SPEC — awaiting user review
>
> Problem: The chain infrastructure exists (chain_id, chain_role,
> chain_parent_ref on TimelineEntry) but operation_id gets lost at two
> critical points in the pipeline. This breaks all cross-source linking.

---

## Root cause: operation_id is lost at the scan layer

`operation_id` is created in `executor.py`, flows through the execution
pipeline, and is persisted in `audit.ndjson` (cli_ops). But when the
mediator subscriber records scan activity, it does NOT pass `operation_id`
to `record_scan_activity()`. The same gap exists in audit staging and
ledger tag creation.

```
executor.py → operation_id created          ✅
  → audit.ndjson                            ✅ (operation_id preserved)
  → current.json                            ✅ (operation_id preserved)
  → mediator scans fire                     ...
    → record_scan_activity()                ❌ (operation_id NOT passed)
    → stage_audit()                         ❌ (operation_id NOT stored)
    → ledger tag creation                   ❌ (operation_id NOT embedded)
```

---

## The three chain types

### 1. Operation chain

A CLI operation (test, lint, audit) is a single logical unit that
produces events across multiple subsystems.

```
CLI: "quality test" (op-20260314-143015-a1b2c3)
  │
  ├─ cli_ops entry (ORIGIN)              ← audit.ndjson, has operation_id
  ├─ scan: audit:scores computed (STEP)  ← audit_activity.json, MISSING operation_id
  ├─ scan: audit:system computed (STEP)  ← audit_activity.json, MISSING operation_id
  ├─ staging: snapshot created (STEP)    ← pending_audits.json, MISSING operation_id
  └─ ledger: audit committed (TERMINAL)  ← scp/audit/* tag, MISSING operation_id
```

**Linking key**: `operation_id`
**What's broken**: Everything after cli_ops drops `operation_id`.

### 2. Commit chain

A git commit can trigger CI runs and test runs.

```
GIT: fix: bugs (2e046a5)                 ← git log, has commit hash
  ├─ CI: pipeline run (STEP)             ← scp/run/* tag, has code_ref=2e046a5
  └─ TESTS: test suite (STEP)            ← scp/run/* tag, has code_ref=2e046a5
```

**Linking key**: `commit hash` = `code_ref`
**What's broken**: The wiring exists (ledger_runs adapter sets
`chain_id = code_ref`, `chain_parent_ref = code_ref`) but no ledger
run tags exist in the repo yet. When they do, this chain will work
automatically.

### 3. Chat thread chain (working)

```
CHAT: thread created (ORIGIN)
  ├─ message 1 (STEP, chain_parent_ref=thread_id)
  ├─ message 2 (STEP, chain_parent_ref=thread_id)
  └─ message 3 (STEP, chain_parent_ref=thread_id)
```

**Linking key**: `thread_id`
**Status**: Working. Only real chains in the system.

---

## Fix plan: thread operation_id through the pipeline

### Layer 1 — Operation context (global, set by executor)

The executor creates the operation_id. We need a way for downstream
code (mediator subscribers, audit staging) to access it without
threading it through every function call.

**Approach**: Thread-local or module-level operation context.

```python
# src/core/engine/operation_context.py (new)

_current_operation_id: str | None = None

def set_operation_id(op_id: str | None) -> None:
    global _current_operation_id
    _current_operation_id = op_id

def get_operation_id() -> str | None:
    return _current_operation_id
```

**Set in executor.py** at the start of `execute_plan()`:
```python
from src.core.engine.operation_context import set_operation_id
set_operation_id(plan.operation_id)
# ... execute ...
set_operation_id(None)  # clear after
```

This makes `operation_id` available to any code running during the
operation — including mediator resolvers and subscribers — without
changing every function signature in the call chain.

### Layer 2 — Scan activity recording

**File**: `src/core/services/mediator/subscribers/activity.py`

`record_scan_activity()` needs to include `operation_id` in the
entry's detail/context when an operation is active.

```python
from src.core.engine.operation_context import get_operation_id

def _on_computed(event):
    ...
    op_id = get_operation_id()
    record_scan_activity(
        _project_root, card_key, status, elapsed_s, data, error_msg,
        operation_id=op_id,  # new parameter
    )
```

The `record_scan_activity` function writes to `audit_activity.json`.
Add `operation_id` to the entry dict when present:

```python
entry = {
    "ts": ts, "iso": iso, "card": card_key, ...
}
if operation_id:
    entry["operation_id"] = operation_id
```

### Layer 3 — Audit staging

**File**: `src/core/services/audit_staging.py`

`stage_audit()` creates snapshot dicts for pending audits. Include
`operation_id` when present:

```python
from src.core.engine.operation_context import get_operation_id

def stage_audit(...):
    op_id = get_operation_id()
    snapshot = {
        "snapshot_id": snapshot_id,
        "card_key": card_key,
        ...
    }
    if op_id:
        snapshot["operation_id"] = op_id
```

### Layer 4 — Ledger tag creation

**File**: `src/core/services/ledger/ledger_ops.py`

When creating `scp/audit/*` tags, embed `operation_id` from the
snapshot data into the tag message:

```python
tag_message = json.dumps({
    "snapshot_id": snapshot_data.get("snapshot_id"),
    "card_key": snapshot_data.get("card_key"),
    "status": snapshot_data.get("status"),
    "iso": snapshot_data.get("iso"),
    "summary": snapshot_data.get("summary"),
    "operation_id": snapshot_data.get("operation_id"),  # new
})
```

### Layer 5 — Timeline adapters read the links

With operation_id flowing through all layers, the adapters can
set chain_id properly:

**ScanActivityAdapter** (`scan_activity.py`):
```python
op_id = raw.get("operation_id")
if op_id:
    chain_id = op_id
    chain_role = ChainRole.STEP
    chain_parent_ref = op_id
```

**LedgerAuditsAdapter** (`ledger_audits.py`):
```python
op_id = tag_data.get("operation_id")
if op_id:
    chain_id = op_id
    chain_role = ChainRole.TERMINAL
    chain_parent_ref = op_id
```

**CliOpsAdapter** (`cli_ops.py`): Already works — sets
`chain_id = operation_id`, `chain_role = ORIGIN`.

### Layer 6 — Filter solo entries from chains

In `_build_chains()`, only include chains with 2+ members:

```python
result = [c for c in result if c["entry_count"] > 1]
```

This removes the 370+ solo git commits and cli_ops entries from
the Chains navigator. Only real multi-member chains appear.

### Layer 7 — Chain tree rendering

With real multi-member chains, render the Chains navigator as a
tree using `chain_parent_ref`:

```
▼ 📎 op-20260314 — test run          (4)
    ○ CLI: test run started           [ORIGIN]
      ├─ ○ SCAN: scores computed      [STEP]
      ├─ ○ SCAN: system computed      [STEP]
      └─ ● LEDGER: audit committed    [TERMINAL]

▼ 📎 thread_20260220 — wsl transport  (5)
    ○ CHAT: thread created            [ORIGIN]
      ├─ ○ message 1                  [STEP]
      ├─ ○ message 2                  [STEP]
      └─ ○ message 3                  [STEP]
```

---

## Execution order

| Step | Layer | Files | Scope |
|------|-------|-------|-------|
| 1 | Operation context | `src/core/engine/operation_context.py` (new), `executor.py` | Create module, set/clear in executor |
| 2 | Scan activity | `activity.py` subscriber, `record_scan_activity()` | Read context, pass operation_id, write to entry |
| 3 | Audit staging | `audit_staging.py` | Read context, store in snapshot |
| 4 | Ledger tags | `ledger_ops.py` | Embed operation_id in tag message |
| 5 | Adapters | `scan_activity.py`, `ledger_audits.py` | Read operation_id, set chain_id/role/parent_ref |
| 6 | Solo filter | `registrations/timeline.py` `_build_chains()` | Skip chains with entry_count == 1 |
| 7 | Chain rendering | `_timeline.html` `_tlNavRenderChains()` | Tree from chain_parent_ref |

Steps 1-5 are the infrastructure fix — threading operation_id through.
Step 6 is a one-liner that cleans up the chains navigator immediately.
Step 7 is the rendering that makes chains visually useful.

---

## What this unlocks

Once operation_id flows through the pipeline:

- **Operation chains** appear in the Chains navigator automatically.
  Every CLI operation that triggers scans and ledger commits becomes
  a visible chain with ORIGIN → STEP → TERMINAL structure.

- **Commit chains** will work when ledger run tags start being created.
  The code_ref linking is already wired in the adapters.

- **Cross-source navigation**: clicking a chain member in the navigator
  highlights the entry in the timeline list, showing the full lifecycle
  of an operation across local scans and shared ledger commits.

- **Debugging**: when an audit fails, the user can see the full chain
  from the CLI command that triggered it, through each scan step, to
  the final ledger commit (or failure point).
