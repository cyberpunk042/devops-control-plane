# Compat V2 Remediation — Master Plan

> The compat-v2 commit (6ed5123) added 30,000+ lines across 37 spec documents,
> 22 new source files, and 11 modified files. The entire system was designed and
> built as a standalone parallel universe — zero references to the program's
> mediator, index, WorkQueue, ScanView, ParserRegistry, or any existing system.
>
> **The specs are wrong.** 37 documents, 1 reference to any program system.
> **The code is wrong.** 22 new files, 0 references to any program system.
> **The integration is wrong.** 11 modified files, all using anti-patterns.
>
> Everything must be refactored to use the program's existing systems.

---

## Investigation Documents

- `.agent/docs/performance-investigation-2026-03-19.md` — 58 issues identified, measured timings
- `.agent/docs/compat-v2-full-problem-identification.md` — spec + code + handler problems, real solutions

---

## Milestones

### M1 — Foundation: Registry & Orchestrator Into Mediator
`.agent/plans/compat-v2-remediation-M1-foundation.md`

Wire FeatureRegistry and CompatOrchestrator as mediator nodes. Replace all 6
`CompatOrchestrator.create()` call sites with mediator access. Delete `_cached.py`.
Pickle shard for <50ms warm start. BACKGROUND(5) dispatch on boot.

### M2 — Detection Engine: Use Program's AST Infrastructure
`.agent/plans/compat-v2-remediation-M2-detection-engine.md`

Rewrite analysis/engine.py to use ScanView for file discovery, ParserRegistry for
AST caching, inverted matching loop (walk once, index by type), yield checkpoints,
entry pre-filtering, incremental analysis via index.delta. Target: <3s for 146 files
(down from 57s).

### M3 — Analysis Caching: Results as Mediator Nodes
`.agent/plans/compat-v2-remediation-M3-analysis-caching.md`

Register `compat.analysis.{module}` as mediator nodes. TTL=None (event-driven),
persist=True, depends on index.scan. Handlers read cached results, never run
fresh analysis. Fix engine invalidates via bust_path() cascade.

### M4 — Handler Integration: Clean Up Every Modified File
`.agent/plans/compat-v2-remediation-M4-handlers.md`

Remove all try/except compat blocks from code_scanner.py. Restore handle_rescan_module.
Simplify mark-done logic. Fix double-apply bug. Share mark-done function between
executor.py and wizard.py. Clean up compat-fix endpoint and compat.py routes.

### M5 — Frontend: Fix Every JavaScript Problem
`.agent/plans/compat-v2-remediation-M5-frontend.md`

Fix hardcoded '3.8'. Remove double assess in plan creation. Remove setTimeout assess
from plan modal. Use mediator cascade instead of postureRescan(). Add loading states.

### M6 — WorkQueue: Heavy Operations Off the Request Thread
`.agent/plans/compat-v2-remediation-M6-workqueue.md`

All heavy compat operations go through WorkQueue. Analysis nodes with size=3.
Registry load at BACKGROUND(5). Web requests at CRITICAL. Cooperative yielding
ensures server stays responsive during background analysis.

### M7 — Single Source of Truth: Unify Feature Patterns
`.agent/plans/compat-v2-remediation-M7-single-source.md`

Compat database IS the source of truth. compute_code_floor() reads patterns from
registry. Remove 5 duplicated patterns from module_intel.py. Remove 7 hardcoded
patterns from test_env.py. Both fall back to hardcoded for CLI mode.

### M8 — Events & Lifecycle: State Machine Into EventBus + SSE
`.agent/plans/compat-v2-remediation-M8-events-lifecycle.md`

State transitions publish to EventBus. Fix events publish to EventBus. Batch
runner uses EventBus instead of custom SSE. Frontend subscribes for real-time
updates. No polling.

---

## Execution Order

```
M1 (foundation) → M2 (engine) → M3 (caching) → M4 (handlers)
                                                       ↓
                                 M5 (frontend) ← ← ← ←
                                       ↓
                  M6 (workqueue) → M7 (single source) → M8 (events)
```

M1 first — everything depends on the registry being in the mediator.
M2 before M3 — engine must be fast before caching makes sense.
M3 before M4 — handlers read from cache, cache must exist first.
M4 and M5 can partially overlap — backend and frontend cleanup.
M6 can start after M3 — WorkQueue integration for cached nodes.
M7 after M1+M2 — need registry in mediator and engine working.
M8 last — polish, real-time events.

---

## What This Does NOT Touch

- The compat YAML database entries (1000 entries, 157 files) — data is good, stays
- The schema.py data models — FeatureEntry, Detection, Fix, etc. — good design, stays
- The fix/engine.py transform logic — the actual fix operations are correct, stay
- The fix/rollback.py and fix/verifier.py — good patterns, stay
- The lifecycle/state_machine.py state design — PENDING/RUNNING/PASSED/etc is correct
- The edge_cases/ directory — test suites and context detection stay
- The database/version.py version comparison — correct, stays
- The database/validator.py — correct, stays
- The CLI (cli.py) — standalone tool, uses create() directly, no mediator needed

## What Gets Rewritten

- `analysis/engine.py` — file discovery, parsing, matching loop, caching (M2)
- `analysis/import_resolver.py` — use PythonParser ImportInfo + ScanView for file lookup + index.symbols for cross-module resolution instead of re-parsing files (M2)
- `analysis/version_resolver.py` — read cached analysis from mediator instead of calling analyze_module/analyze_transitive directly (M3)
- `analysis/dep_analyzer.py` — use mediator for PyPI cache instead of hand-rolled dict cache. Integrate with existing compute_dependency_floor() in module_intel.py which already does this job (M3)
- `orchestrator.py` — add create_from_registry(), remove create() from handler paths (M1)
- `database/registry.py` — add pickle serialization (M1)
- `database/loader.py` — pass language parameter, move imports outside of _parse_entry() (M1)
- `backends/base.py` — align with ParserRegistry's BaseParser interface where possible (M2)
- `backends/python_backend.py` — integrate with ParserRegistry, use shared walk/index (M2)
- `lifecycle/batch_runner.py` — use WorkQueue submit_batch() + EventBus instead of custom SSE (M6, M8)
- `lifecycle/plan_engine.py` — read cached analysis/assessment from mediator, no double scan (M3)
- `lifecycle/step_executor.py` — use mediator-cached analysis, add yield checkpoints, no direct analyze_module calls (M3, M6)
- `fix/verifier.py` — invalidate mediator cache (compat.analysis.*) after verification (M3)
- `routes/compat.py` — use mediator.get() everywhere (M1, M3, M6)

## What Gets Fixed in Existing Files

- `code_scanner.py` — remove 3 try/except blocks, use peek() (M4)
- `executor.py` — restore rescan, simplify mark-done (M4)
- `wizard.py` — use shared mark-done function (M4)
- `posture.py` — clean up compat-fix (M4)
- `_system_posture.html` — fix all 7 JS issues (M5)
- `module_intel.py` — read from registry, remove 5 patterns (M7)
- `test_env.py` — read from registry, keep fallback (M7)

## What Gets Deleted

- `_cached.py` — dead code, mediator is the cache (M1)
- `exploration_output.md` — rogue agent artifact (M1)
