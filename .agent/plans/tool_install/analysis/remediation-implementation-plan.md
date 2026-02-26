# Remediation Model — Implementation Plan

> **Status:** R1-R7 complete (core pipeline done). R6 (recipe on_failure data) is incremental.
> **Created:** 2026-02-25
> **Depends on:** `remediation-model.md` (architecture design)

---

## Scope

Implement the layered remediation model from `remediation-model.md`.
Every file touched, every function changed, every new file created,
ordered by dependency — nothing can be built before its prerequisites.

---

## Touch Point Inventory

### What exists today

| File | Lines | What it does | What changes |
|------|-------|-------------|--------------|
| `data/recipes.py` | 5175 | 296 tool recipes, pure data | Add `on_failure` to ~30 recipes |
| `data/recipe_schema.py` | 212 | Schema validator | Add `on_failure`, option schema |
| `detection/install_failure.py` | 250 | 5 hardcoded patterns → remediation | Replace with thin cascade dispatcher |
| `detection/recipe_deps.py` | 27 | Resolves system packages | Unchanged |
| `domain/error_analysis.py` | 147 | Build failure patterns (headers, libs, OOM) | Patterns migrate to handlers data |
| `resolver/plan_resolution.py` | 618 | Produces install plans | Add `resolve_install_plan_with_method()` |
| `resolver/method_selection.py` | 197 | Picks install method | Unchanged |
| `resolver/dependency_collection.py` | 151 | Walks dep tree depth-first | Unchanged |
| `orchestration/orchestrator.py` | 650 | Executes plans, handles failures | Update failure path to use new cascade |
| `execution/plan_state.py` | 220 | Save/load/resume plan state | Extend for remediation chain state |
| `ui/web/routes_audit.py` | 1762 | API routes (SSE, remediate) | New endpoint, update done_event shape |
| `ui/web/templates/scripts/_globals.html` | 3304 | JS remediation modal | Update modal for availability, breadcrumbs |

### New files

| File | Purpose | Layer |
|------|---------|-------|
| `data/remediation_handlers.py` | METHOD_FAMILY_HANDLERS, INFRA_HANDLERS, BOOTSTRAP_HANDLERS | L0 Data |
| `domain/handler_matching.py` | `_matches()`, `_collect_all_options()` | L1 Domain |
| `domain/remediation_planning.py` | `_build_remediation_response()`, `_compute_availability()` | L1 Domain |

---

## Implementation Phases

### Phase R1: Handler Data (L0 — no dependencies)

**Goal:** Create the remediation handler registries as pure data.

#### R1.1 — Create `data/remediation_handlers.py`

New file. Contains three constants:

```
METHOD_FAMILY_HANDLERS: dict[str, list[dict]]
  - pip:      PEP 668, missing pip
  - cargo:    rustc mismatch, gcc bug, missing C lib
  - npm:      EACCES, missing npm
  - apt:      stale index, locked
  - dnf:      no match
  - yum:      (same patterns as dnf)
  - snap:     snapd unavailable
  - brew:     formula not found
  - _default: missing curl, missing git

INFRA_HANDLERS: list[dict]
  - network offline, blocked (proxy/TLS)
  - disk full
  - no sudo, wrong password, permission denied
  - OOM (exit 137)
  - timeout

BOOTSTRAP_HANDLERS: list[dict]
  - no package manager
  - no shell
```

Each handler follows the shape from remediation-model.md §3.1:
`{pattern, failure_id, category, label, description, options: [...]}`

Each option follows: `{id, label, description, icon, recommended, strategy, ...}`

**Availability is NOT computed here** — it's computed at runtime by
domain/remediation_planning.py. The data is static.

Also contains:

```
LIB_TO_PACKAGE_MAP: dict[str, dict[str, str]]
  Maps C library names to package names by family:
  {"ssl": {"debian": "libssl-dev", "rhel": "openssl-devel", ...}}
```

**Estimated size:** ~200-250 lines.
**Depends on:** Nothing (pure data).
**Test:** Import succeeds, all handler patterns are valid regex,
all option IDs are unique per handler, all strategies valid.

#### R1.2 — Update `data/recipe_schema.py`

Add to valid fields for tool recipes:
```python
_TOOL_FIELDS |= {"on_failure"}
```

Add validation logic for `on_failure`:
- Must be a list of dicts
- Each dict must have: pattern, failure_id, category, label, options
- Each option must have: id, label, strategy, icon
- Strategy must be in VALID_STRATEGIES
- Pattern must be valid regex

**Estimated changes:** ~40 lines added.
**Depends on:** Nothing.
**Test:** Existing test_resolver_coverage.py passes (no recipes have on_failure yet).

---

### Phase R2: Domain Logic (L1 — depends on R1)

**Goal:** The matching and planning functions, pure logic.

#### R2.1 — Create `domain/handler_matching.py`

Functions:

```python
def _matches(handler: dict, stderr: str, exit_code: int) -> bool:
    """Check if a handler's pattern+exit_code matches the failure."""
    # Regex match on pattern (case-insensitive)
    # Exit code match if specified
    # detect_fn dispatch if specified

def _collect_all_options(
    tool_id: str,
    method: str,
    stderr: str,
    exit_code: int,
) -> tuple[list[dict], list[dict]]:
    """Cascade through all layers, collect matching handlers + their options.

    Returns:
        (matched_handlers, merged_options)
        Options are deduplicated by id, ordered by:
        recipe > method_family > infra > bootstrap
    """
    # 1. recipe["on_failure"] handlers
    # 2. METHOD_FAMILY_HANDLERS[method]
    # 3. INFRA_HANDLERS
    # 4. BOOTSTRAP_HANDLERS
    # Collect ALL matching, don't stop at first
    # Deduplicate options by id (first occurrence wins)
```

**Estimated size:** ~80-100 lines.
**Depends on:** R1.1 (handler data), TOOL_RECIPES (existing).
**Test:** Unit tests with synthetic stderr → verify correct handlers match,
priority order respected, deduplication works.

#### R2.2 — Create `domain/remediation_planning.py`

Functions:

```python
def _compute_availability(
    option: dict,
    recipe: dict,
    system_profile: dict,
) -> tuple[str, str | None, list[str] | None]:
    """Compute availability state for a single option.

    Returns:
        (state, reason, unlock_deps)
        state: "ready" | "locked" | "impossible"
    """
    # Checks:
    # - install_dep: is the dep recipe present? is the binary on PATH?
    # - switch_method: does the recipe have that method?
    # - install_packages: does the family have packages defined?
    # - retry_with_modifier: always ready
    # - manual: always ready

def _build_remediation_response(
    tool_id: str,
    step_idx: int,
    step_label: str,
    exit_code: int,
    stderr: str,
    method: str,
    system_profile: dict,
    chain: dict | None = None,
) -> dict:
    """Build the full backend response for the UI.

    Calls _collect_all_options, computes availability for each,
    sorts by recommendation, adds chain context and fallback actions.

    Returns the shape defined in remediation-model.md §6.
    """

def _compute_step_count(option: dict, system_profile: dict) -> int:
    """Estimate how many steps an option will take to execute."""
```

**Estimated size:** ~150-200 lines.
**Depends on:** R2.1 (handler matching), R1.1 (handler data), plan_resolution (existing).
**Test:** Given a failure scenario (tool, method, stderr, exit_code, profile),
verify the response shape matches §6, availability computed correctly,
options ordered correctly.

---

### Phase R3: Escalation Chain (L4 — depends on R2)

**Goal:** Chain state tracking, persistence, save/resume.

#### R3.1 — Create or extend chain state management

Two options:
- **Option A:** Extend `execution/plan_state.py` with chain functions
- **Option B:** New file `execution/chain_state.py`

**Decision: Option B** — separate concerns. Plan state is for install plans.
Chain state is for remediation chains. Different lifecycle, different shape.

New file `execution/chain_state.py`:

```python
def create_chain(tool_id: str, plan: dict, failed_step_idx: int) -> dict:
    """Create a new escalation chain for a failed install."""
    # Returns chain dict with chain_id, original_goal, empty stack

def escalate_chain(chain: dict, failure_id: str, chosen_option_id: str) -> dict:
    """Push a new escalation level onto the chain stack."""
    # Increment depth, add entry with status "pending"

def de_escalate_chain(chain: dict) -> dict | None:
    """Pop the top level (mark done), return the now-current level."""
    # If stack empty → original goal can retry

def save_chain(chain: dict) -> Path:
    """Persist chain state to disk."""
    # .state/remediation_chains/{chain_id}.json

def load_chain(chain_id: str) -> dict | None:
    """Load a chain from disk."""

def list_pending_chains() -> list[dict]:
    """Find all chains with status != done/cancelled."""

def cancel_chain(chain_id: str) -> bool:
    """Cancel a chain."""

def get_chain_breadcrumbs(chain: dict) -> list[dict]:
    """Build the breadcrumb trail for the UI."""
```

**Estimated size:** ~150-180 lines.
**Depends on:** Nothing (pure state management).
**Test:** Create chain → escalate → escalate → de-escalate → de-escalate →
chain empty. Save/load roundtrip. Max depth enforcement. Cycle detection.

---

### Phase R4: Dispatcher Refactor (L3 — depends on R2)

**Goal:** Replace install_failure.py's hardcoded patterns with the cascade.

#### R4.1 — Refactor `detection/install_failure.py`

The current `_analyse_install_failure(tool, cli, stderr)` becomes:

```python
def _analyse_install_failure(
    tool: str,
    cli: str,
    stderr: str,
    *,
    exit_code: int = 1,
    method: str = "",
    system_profile: dict | None = None,
) -> dict | None:
    """Cascade through handler layers and return structured remediation.

    Now a thin dispatcher that delegates to domain layer.
    Backward compatible — old callers pass (tool, cli, stderr) and
    get a response in the existing shape. New callers pass method +
    system_profile and get the full §6 response.
    """
```

**Key constraint:** Backward compatibility. The existing callers in
orchestrator.py and routes_audit.py pass `(tool, cli, stderr)`. The new
signature adds optional kwargs. If method/system_profile are not provided,
the function falls back to the old flat response shape.

**Migration path:**
1. Update the signature (backward compatible)
2. Internal: delegate to `_build_remediation_response()` when new args present
3. Legacy path: keep working for old callers
4. Update callers one by one (R5)

**Estimated changes:** ~100 lines total (current 250 → ~100 new dispatcher + imports).
**Depends on:** R2 (domain logic).
**Test:** Same patterns match as before. New callers get the §6 shape.

#### R4.2 — Migrate `domain/error_analysis.py` patterns

The build failure patterns (missing header, missing C lib, OOM, compiler
not found, permission denied) are currently isolated in error_analysis.py.

They need to become entries in METHOD_FAMILY_HANDLERS or INFRA_HANDLERS:
- Missing header → method-family handler for "source"/"make"
- Missing C lib → method-family handler for "cargo"/"source" (already there)
- OOM → infra handler (already there as exit_code 137)
- Compiler not found → method-family handler for "source"/"make"
- Permission denied → infra handler (already there)

**After migration:** error_analysis.py keeps only `_parse_build_progress()`
(which is about progress parsing, not failure analysis). The failure
patterns live in remediation_handlers.py.

**Estimated changes:** Move ~80 lines of patterns to handlers data, remove
from error_analysis.py.
**Depends on:** R1.1 (handler data exists to receive them).

---

### Phase R5: Integration (L5 — depends on R3, R4)

**Goal:** Wire everything together in the orchestration and API layers.

#### R5.1 — Update `orchestration/orchestrator.py`

The failure path in `execute_plan()` (lines 253-302) currently calls
`_analyse_install_failure(tool, cli, stderr)` with 3 args.

**Change to:**
```python
remediation = _analyse_install_failure(
    tool, plan.get("cli", tool),
    result.get("stderr", ""),
    exit_code=result.get("exit_code", 1),
    method=step.get("method", ""),
    system_profile=system_profile,  # passed through from caller
)
```

This requires `system_profile` to be available in `execute_plan()`.
Currently it's not passed in. **Add it as a parameter:**

```python
def execute_plan(plan, *, sudo_password="", start_from=0, system_profile=None):
```

**Estimated changes:** ~15 lines.
**Depends on:** R4.1 (new dispatcher signature).

#### R5.2 — Update `routes_audit.py` SSE plan execution

The SSE endpoint at line ~1190 currently:
1. Calls `_analyse_install_failure(tool, cli, stderr)` → gets old shape
2. Attaches `remediation` to done_event
3. UI reads `event.remediation.options` (old flat shape)

**Change to:**
1. Call with new args (method, exit_code, system_profile)
2. Response comes in §6 shape (failure + options + chain)
3. Create or escalate chain if one exists
4. Attach the full response to done_event

**Also:** The system_profile needs to be available in the SSE handler.
Currently the plan resolution already calls `_detect_system_profile()`.
Pass that result through to execution.

**New endpoint** for user choice:
```python
@audit_bp.route("/audit/remediate-choice", methods=["POST"])
def audit_remediate_choice():
    """User picked a remediation option. Execute or escalate."""
    body = request.get_json(silent=True) or {}
    chain_id = body.get("chain_id")
    option_id = body.get("chosen_option_id")
    # ...
```

**Estimated changes:** ~80 lines modified, ~60 lines new endpoint.
**Depends on:** R3.1 (chain state), R4.1 (new dispatcher).

#### R5.3 — Add chain push on SSE connect

When the UI connects to the SSE stream (server → client), push any
pending remediation chains:

```python
# On connect or on server startup message stream:
pending = list_pending_chains()
for chain in pending:
    yield _sse({"type": "pending_chain", "chain": chain})
```

This fits into the existing SSE general message stream. The UI picks
up `type: "pending_chain"` events and shows the remediation modal.

**Estimated changes:** ~15 lines.
**Depends on:** R3.1 (chain state).

---

### Phase R6: Recipe Data (L0 — depends on R1.2 for schema)

**Goal:** Add `on_failure` to the ~30 recipes that need it.

These are the recipes with tool-specific failure modes that the
generic handlers (method-family, infra) don't cover:

| Recipe | Failure | Handler needed |
|--------|---------|----------------|
| opencv | Missing libopencv-dev | install_packages (specific headers) |
| pytorch | CUDA driver conflict | manual (driver installation) |
| tensorflow | CUDA/cuDNN mismatch | switch_method (cpu build) |
| docker-ce | conflicts with podman | install_dep (remove podman first) |
| docker-ce | repo not configured | add_repo |
| cuda-toolkit | driver version mismatch | manual |
| nvidia-smi | kernel module missing | manual |
| ghc | version conflicts on system haskell | switch_method |
| protoc | architecture detection wrong | manual |
| ... | ... | ... |

**Estimated:** ~30 recipes × ~10 lines each = ~300 lines of on_failure data.
**Depends on:** R1.2 (schema validates on_failure).
**Test:** Existing test_resolver_coverage.py passes, schema validation passes.

---

### Phase R7: UI Update (Frontend — depends on R5)

**Goal:** Update the remediation modal to show availability, breadcrumbs, locking.

#### R7.1 — Update `_showRemediationModal()`

The current modal (`_globals.html` lines 798-910) renders flat options.
Needs to:

1. Show `availability` state per option (ready, locked, impossible)
2. Locked options show 🔒 icon + lock_reason + "Unlock" button
3. Impossible options greyed out with `impossible_reason`
4. Recommended option highlighted (already partially there)
5. Breadcrumb trail at top of modal (new)
6. Risk badges (low/medium/high) per option

**Not a rewrite** — evolution of existing modal.

#### R7.2 — Handle chain events

In the SSE event handler (lines ~1711-1718):
- `event.remediation` → now has §6 shape
- `event.type === "pending_chain"` → restore modal from chain state
- On option click: POST to `/api/audit/remediate-choice`
- On unlock click: POST choice with locked option → backend escalates

**Estimated JS changes:** ~150 lines modified, ~50 lines new.
**Depends on:** R5.2 (new API shape).

---

## Dependency Graph

```
R1.1 (handler data) ─────────┐
                              ├─── R2.1 (matching) ──┐
R1.2 (schema update) ────────┘                       │
                                                     ├─── R2.2 (planning)
                                                     │
                              R3.1 (chain state) ────┤
                                                     │
                              R4.1 (dispatcher) ─────┤
                              R4.2 (migrate patterns)│
                                                     │
                              ┌──────────────────────┘
                              │
                              ├─── R5.1 (orchestrator)
                              ├─── R5.2 (routes_audit)
                              ├─── R5.3 (chain push)
                              │
R6 (recipe data) ─────────────┤
                              │
                              └─── R7.1 (modal update)
                                   R7.2 (chain events)
```

### Parallelizable work

| Can be done in parallel | Why |
|------------------------|-----|
| R1.1 + R1.2 | Both L0 data, no dependencies on each other |
| R3.1 + R2.1 | Chain state has no deps, matching needs only R1 |
| R4.2 + R6 | Pattern migration and recipe data are independent |

### Critical path

```
R1.1 → R2.1 → R2.2 → R4.1 → R5.2 → R7.1
```

This is 6 phases on the critical path. Each is focused (80-200 lines).

---

## Test Strategy

### Per-phase testing

| Phase | Test type | What |
|-------|----------|------|
| R1.1 | Unit | All patterns compile, option IDs unique, strategies valid |
| R1.2 | Unit | Schema validates on_failure correctly, rejects bad data |
| R2.1 | Unit | Synthetic stderr → correct handler matches, priority order |
| R2.2 | Unit | Given failure → correct response shape, availability computed |
| R3.1 | Unit | Chain create/escalate/de-escalate/save/load lifecycle |
| R4.1 | Unit | Backward compat (old callers), new callers get §6 shape |
| R5.x | Integration | Full flow: fail → cascade → options → chain state |
| R6 | Parametric | Existing test_resolver_coverage.py passes |
| R7.x | Manual | Modal renders correctly with all states |

### New test files

| File | Purpose |
|------|---------|
| `tests/tool_install/test_handler_matching.py` | R2.1 matching logic |
| `tests/tool_install/test_remediation_planning.py` | R2.2 response building |
| `tests/tool_install/test_chain_state.py` | R3.1 chain lifecycle |
| `tests/tool_install/test_remediation_cascade.py` | End-to-end cascade |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Breaking existing remediation flow | Medium | High | Backward compat in R4.1 |
| UI modal changes break existing UX | Medium | Medium | Evolutionary change, not rewrite |
| Chain state files accumulate | Low | Low | Archive/cleanup on completion |
| Handler patterns too broad (false positives) | Medium | Medium | Parametric test coverage |
| Circular remediation chains | Low | High | Cycle detection in R3.1 |

---

## Estimated Effort

| Phase | New lines | Changed lines | Files touched |
|-------|-----------|--------------|---------------|
| R1 | 290 | 40 | 2 new + 1 changed |
| R2 | 280 | 0 | 2 new |
| R3 | 170 | 0 | 1 new |
| R4 | 100 | 230 | 2 changed |
| R5 | 155 | 95 | 2 changed |
| R6 | 300 | 0 | 1 changed |
| R7 | 200 | 150 | 1 changed |
| Tests | 400 | 0 | 4 new |
| **Total** | **~1,895** | **~515** | **8 new + 7 changed** |

---

## Traceability

| Requirement | Design section | Implementation phase |
|------------|---------------|---------------------|
| Always multiple options | remediation-model §3.1 | R1.1, R2.2 |
| Availability states (ready/locked/impossible) | remediation-model §3.1 | R2.2 |
| Handler cascade (collect all, don't stop) | remediation-model §5.1 | R2.1 |
| Escalation chain with stack | remediation-model §5.3 | R3.1 |
| De-escalation (unwind stack) | remediation-model §5.4 | R3.1, R5.2 |
| Save/resume on reconnect | remediation-model §5.6 | R3.1, R5.3 |
| Backend response shape | remediation-model §6 | R2.2, R5.2 |
| Recipe on_failure field | remediation-model §4 | R1.2, R6 |
| Method-family shared handlers | remediation-model §3.4 | R1.1 |
| Infra/bootstrap handlers | remediation-model §3.5-3.6 | R1.1 |
| Backward compatibility | this plan §R4.1 | R4.1 |
| UI breadcrumbs + availability | remediation-model §6 | R7.1 |
