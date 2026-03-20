# Compat V2 — Full Problem Identification & Real Solutions

> This document identifies every problem in the compat-v2 commit — both the 37 spec
> documents AND the 22 new source files AND the 11 modified files. Then identifies
> the real solutions using the program's existing systems.

---

## Part 1: The Root Problem

37 spec documents were written. 22 new source files were implemented. 11 existing files
were modified. Across ALL of this:

**37 specs: 1 reference to any program system** (one mention of "mediator" in spec 13).
Zero references to: index.scan, WorkQueue, ScanView, ParserRegistry, compute_code_floor,
posture.modules, get_mediator, dispatch, peek, yield_check.

**22 new source files: 0 references to any program system.** Not the mediator. Not the
index. Not the WorkQueue. Not the parser registry. Not yield checkpoints. Nothing.

The entire compat-v2 system — from spec to implementation — was designed and built as
if the program's infrastructure did not exist. Every system that makes this program fast
and smart was ignored. The specs designed a parallel universe. The code implemented it.

---

## Part 2: What the Program Has (verified from source)

These are the systems that exist and MUST be used:

### The Mediator (62 nodes, 5 domains)
- Centralized data routing engine — single source of truth for all computed data
- `get()` with TTL, per-path compute locks, lazy cascade invalidation
- `peek()` — never blocks, never triggers computation
- `dispatch()` — background recompute via WorkQueue
- `subscribe()` — live events → SSE bridge
- Persistence: atomic JSON shards, hydration <100ms on restart
- Cache hit: <1ms. Cascade: <5ms for 62 nodes

### The WorkQueue (priority-aware, size-weighted)
- 6 priority levels: CRITICAL(0) through BACKGROUND(5)
- CRITICAL bypasses capacity limits — web requests never wait
- WeightedSemaphore: size-weighted admission (1=light, 3=heavy)
- Cooperative yielding: `current_yield_check()` — background workers pause for web requests
- `submit_and_wait()` for synchronous web paths
- Batch tracking with group completion callbacks

### The Index (incremental, delta-driven)
- `index.scan`: 38ms full project walk, per-file mtime
- `index.delta`: 1ms diff — knows EXACTLY which files changed
- `index.symbols`: incremental parse. Cold ~30s, warm ~60ms/file (500x faster)
- `index.view`: ScanView with O(1) lookups by extension, filename, directory
- `index.classify`: language/framework detection in 5ms
- Yield checkpoints every 10 files
- Persistent accumulators across get() calls

### The Parser Registry (11 parsers, per-file mtime cache)
- Extension-based routing to correct language parser
- Per-file mtime cache — only re-parses changed files
- `parse_tree()` with yield checkpoints and cache eviction
- Python parser: full AST (imports, symbols, metrics) in ONE walk per file

### compute_code_floor() (module_intel.py)
- 13 regex patterns, compiled once, one pass per file
- String/comment stripping to avoid false positives
- `__future__` annotations awareness
- Results flow through mediator: posture.modules → posture.full → posture.summary

---

## Part 3: Spec-Level Problems (01–37)

Every spec document that describes a component which the program already has — but the
spec designs a new one from scratch instead of using it.

### Spec 01 — System Architecture
- Section 3: Draws a 6-layer architecture diagram. The mediator is not in it. The index
  is not in it. The WorkQueue is not in it. The program's data flow
  (Index → Detect → DevOps → Posture) is not referenced.
- Section 3.2: Designs "Language Backends" with their own AST parser, import resolver,
  and code emitter. The program already has a ParserRegistry with 11 parsers, a
  PythonParser that extracts imports/symbols/metrics, and an incremental symbol index.
- Section 4.1: Data flow diagram shows a standalone pipeline with no mediator involvement.
  Analysis results are computed and returned, not cached or persisted.
- Section 6: "What Gets Replaced" — lists compute_code_floor, handle_scan_incompatible_features,
  and 15 other existing functions as things to REPLACE. Should have listed them as things
  to INTEGRATE WITH.
- Section 8: Migration strategy says "v1 code is NOT modified" in Phase 1. The commit
  modified v1 code extensively (code_scanner.py, executor.py, wizard.py, posture.py).

### Spec 02 — Feature Database Schema
- Designs a YAML-based database with its own loader, its own registry, its own singleton.
  The mediator already has persistence (JSON shards + hydration). The database should be
  a mediator node, not a standalone singleton.
- No mention of how the database integrates with the existing `_RUNTIME_FEATURES` and
  `_ANNOTATION_FEATURES` lists in module_intel.py — treats them as replacements, not
  as sources to unify.

### Spec 03 — AST Detection Engine
- Section 4.1: Designs its own "FileDiscovery" class. The program has ScanView with O(1)
  lookups by extension. `ScanView.files_with_ext("py")` returns all Python files instantly.
  `ScanView.files_in_dir("src/ui/web", recursive=True)` returns all files in a module.
- Section 4.2: Designs its own "ASTCache" with mtime-based invalidation. The ParserRegistry
  already has per-file mtime caching. The index already has incremental symbol parsing
  with delta-driven invalidation.
- Section 7.2: "Each file's AST is walked once per feature entry." This is the O(files ×
  entries) design. With 500 files and 200 entries = 100,000 walk operations. The spec
  acknowledges this but estimates "~100ms" based on "~10ns per comparison." The real
  measurement: 57 SECONDS for 146 files. The estimate was wrong by 570x.
- Section 7.3: "Don't persist cache across sessions — disk cache adds complexity for
  minimal gain." The mediator persists everything, hydrates in <100ms. Not using it
  is throwing away free performance.
- Section 9: "Integration Points" — lists Feature Database, Import Chain Resolver, Fix
  Engine, Lifecycle. Does NOT list: mediator, index, WorkQueue, ScanView, parser registry,
  compute_code_floor, posture.modules. Zero integration with the program.

### Spec 04 — Import Chain Resolver
- Designs its own import graph builder. The PythonParser already extracts all imports
  (internal, external, relative, stdlib) in its ONE-walk parse. The index.symbols node
  already tracks all symbols across the project incrementally.
- Does not use index.delta to know which files changed — re-walks everything.

### Spec 06 — Step Lifecycle State Machine
- Designs a state machine (PENDING/RUNNING/PASSED/FAILED/NEEDS_ATTENTION/BLOCKED).
  This is good design. But it does not integrate with the mediator's event system
  (subscribe/publish). State transitions should publish events that the SSE bridge
  picks up for real-time UI updates. Instead, it's a standalone object.

### Spec 08 — Project-Wide Analysis
- Designs project-wide scanning. The index already does project-wide scanning in 38ms
  with delta-driven incremental updates. The spec builds its own parallel project scanner.

### Spec 09 — Batch Execution
- Designs its own batch runner with SSE events. The WorkQueue already has batch tracking
  with group completion callbacks. The mediator has dispatch() for background computation.
  The existing wizard.py batch system already streams SSE. All three were ignored.

### Spec 29 — Multi-Language Plugin Architecture
- Designs a plugin system for language backends. The ParserRegistry IS a plugin system —
  11 parsers registered by extension, extensible via register(). The spec does not
  reference it.

### Spec 30 — API Endpoint Design
- Designs 20+ endpoints under /api/compat/. None of them use mediator.get() for cached
  results. None use dispatch() for background computation. None use peek() for non-blocking
  reads. Every endpoint runs fresh computation synchronously.

### Spec 31 — Web UI Integration
- Designs frontend JavaScript that calls /api/compat/ endpoints. Does not mention SSE
  subscription for live updates (the program already has SSE via mediator subscribe + EventBus).
  Does not mention loading states for long operations.

### Spec 36 — Migration Plan
- Says "v1 code is NOT modified (except critical bug fixes)." The commit modified
  code_scanner.py (298 lines added), executor.py (95 lines changed), wizard.py (58 lines
  changed), posture.py (135 lines added), _system_posture.html (412 lines added).

### Specs 19–27 — Language-specific specs
- Each designs its own parser. The ParserRegistry already has parsers for Python, JS/TS,
  Go, Rust, C, CSS, Config, Template, JVM. The compat backends duplicate this.

---

## Part 4: Code-Level Problems (22 new files)

### `orchestrator.py` — The root of all evil
**What it does**: Creates CompatOrchestrator with fresh engines on every call.
**What it should do**: Be a mediator node. One instance, cached, shared.
**Program system ignored**: Mediator (get/peek/persist), per-path compute locks.

### `analysis/engine.py` — O(files × entries × nodes)
**What it does**: For each file, for each entry (~600), walks the entire AST.
**What it should do**: Walk AST once per file, index nodes by type, match entries against
the index. Use ScanView for file discovery. Use parser registry mtime cache. Add yield
checkpoints every 10 files.
**Program systems ignored**: ScanView, ParserRegistry mtime cache, yield checkpoints,
index.delta for incremental analysis.

### `database/loader.py` — 2.9s cold load
**What it does**: Opens 157 YAML files, parses each with yaml.safe_load, constructs
15,000 nested dataclass objects.
**What it should do**: Be a mediator node with persistence. First load parses YAML and
persists to shard. Every subsequent load hydrates from shard in <100ms.
**Program systems ignored**: Mediator persistence, hydration.

### `database/registry.py` — Standalone singleton
**What it does**: Singleton pattern keyed on entries_dir path. Loads all 10 languages.
**What it should do**: Be a mediator node (TTL=inf, persist=True). Load only needed
languages. Results available via mediator.get("compat.registry").
**Program systems ignored**: Mediator singleton pattern (which is better — per-path
compute locks, cascade, persistence, hydration).

### `backends/python_backend.py` — Duplicate parser
**What it does**: Implements its own AST parsing, node walking, context detection.
**What it should do**: Use the existing PythonParser from the parser registry. The
PythonParser already parses files, extracts imports, detects symbols, handles context.
The compat-specific node matching (detection rules) can extend the existing parser,
not replace it.
**Program systems ignored**: ParserRegistry, PythonParser, per-file mtime cache.

### `analysis/import_resolver.py` — Duplicate import graph
**What it does**: Builds import graph by re-parsing files for import statements.
**What it should do**: Use the PythonParser's import extraction (already done in ONE
walk). Use index.symbols for cross-module symbol resolution. Use ScanView for file
lookup.
**Program systems ignored**: PythonParser ImportInfo, index.symbols, ScanView.

### `fix/engine.py` — No mediator integration
**What it does**: Applies fixes, verifies them. Good functionality.
**What it should do**: After applying fixes, invalidate relevant mediator nodes
(posture.modules, compat.analysis.*) so the cache reflects the changes. Publish events
via mediator subscribe so the frontend knows fixes were applied.
**Program systems ignored**: Mediator invalidation, event publishing.

### `lifecycle/batch_runner.py` — Duplicate batch system
**What it does**: Runs steps in sequence with SSE events.
**What it should do**: Use the WorkQueue for step execution. Steps submitted as WorkItems
with appropriate priority (HIGH for user-initiated, NORMAL for batch). Batch tracking
via WorkQueue.submit_batch() with on_complete callback.
**Program systems ignored**: WorkQueue, priority levels, weighted semaphore, yield checkpoints.

### `lifecycle/plan_engine.py` — No caching
**What it does**: Generates plans from analysis results. Calls assess() + analyze()
back-to-back (double scan).
**What it should do**: Read cached analysis from mediator. Generate plan from cached
data. Cache the plan itself as a mediator node.
**Program systems ignored**: Mediator caching for analysis results and plans.

### `lifecycle/step_executor.py` — Duplicate executor
**What it does**: Executes individual steps, parallel to the existing executor.py.
**What it should do**: Extend the existing executor.py, not duplicate it. Or at minimum,
share the step execution interface so both systems can coexist.
**Program systems ignored**: Existing step execution infrastructure.

### `lifecycle/state_machine.py` — No events
**What it does**: Tracks step states. Good design (PENDING/RUNNING/PASSED/FAILED/etc).
**What it should do**: Publish state transitions via mediator subscribe/EventBus so the
SSE bridge picks them up. The frontend can get real-time step state updates without polling.
**Program systems ignored**: Mediator subscribe, EventBus, SSE bridge.

---

## Part 5: Modified File Problems (11 files)

### `code_scanner.py` — 3 try/except compat blocks
Each handler wraps compat engine calls in try/except with legacy fallback:
- Creates new orchestrator (2.9s first, 33ms after)
- Runs full module analysis (57s)
- Falls back to legacy (<1s) on any failure
- Double-applies fixes in handle_add_future_annotations

**Real solution**: Handlers should read cached compat data from mediator via peek().
If not available (compat engine hasn't loaded yet), use the legacy path. No try/except.
No creating orchestrators. No running analysis in handlers. The analysis is done in the
background via WorkQueue and results are in the mediator.

### `executor.py` — Compat analysis in handle_rescan_module
- Adds 60s compat analysis before mediator cache refresh
- `except Exception: pass` swallows failure
- Returns false "clean" when analysis crashes (remaining_findings=0)
- Mark-done logic expanded to 5 nested conditions

**Real solution**: handle_rescan_module does ONE thing: invalidate and recompute posture
via mediator. If compat analysis results exist in the mediator cache, they cascade-invalidate
automatically when posture.modules is invalidated. The handler doesn't run analysis.

### `wizard.py` — Copy-pasted mark-done logic
- Same 5-condition logic from executor.py duplicated
- Will drift when one is fixed and the other isn't

**Real solution**: One shared function for mark-done logic, called by both executor.py
and wizard.py.

### `posture.py` — posture_module_compat_fix
- Creates uncached orchestrator + full analysis to do one string replace
- Imports private function cross-module

**Real solution**: The fix endpoint should use the fix engine directly for the specific
finding, not re-analyze the entire module. Or use the mediator-cached analysis to find
the specific finding, then apply the fix.

### `_system_posture.html` — Blocking frontend calls
- Hardcoded target_version '3.8'
- Double assess calls in plan creation
- setTimeout assess on every plan modal open
- postureRescan() after fix

**Real solution**: Read target from module plan data. No pre-assess — the plan endpoint
handles it. No setTimeout assess. After fix, invalidate via mediator cascade, not full rescan.

### `module_intel.py` — 5 duplicated patterns
- datetime.UTC, StrEnum, tomllib, removeprefix, removesuffix added to _RUNTIME_FEATURES
- These duplicate entries in the compat database

**Real solution**: Single source of truth. Either the compat database feeds compute_code_floor
(enriching the pattern list from database entries), or compute_code_floor's patterns ARE
the database for the features it covers. Not both.

### `test_env.py` — 7 hardcoded compat patterns
- _COMPAT_PATTERNS duplicates database entries
- _detect_compat_failures scans test output with regex

**Real solution**: Compat patterns come from the database. _detect_compat_failures queries
the registry for feature patterns instead of hardcoding them.

---

## Part 6: The Real Solutions

The compat-v2 system has real value: 1000 entries with detection rules, fix strategies,
edge cases, severity, backports. The fix engine, verification loop, rollback, state machine
— these are good designs. The problem is not what was built. The problem is that it was
built as a standalone system instead of being wired into the program.

Every solution below uses what exists:

### S1: Registry as mediator node
The FeatureRegistry becomes `compat.registry` in the mediator. TTL=inf, persist=True
(pickle shard). First-ever load: 2.9s YAML parse in background (BACKGROUND priority via
WorkQueue dispatch). Persists to shard. Every subsequent start: hydrates in <50ms. The
registry is a sub-feature of posture — it loads dead last, only when capacity is free.

### S2: Detection engine uses ScanView + parser registry
File discovery: `ScanView.files_in_dir(module_dir, recursive=True)` filtered to
`ScanView.files_with_ext("py")`. O(1) lookup, no rglob.

AST parsing: Use ParserRegistry.parse_file() which has per-file mtime cache. File
parsed once, cached until mtime changes. Don't maintain a separate AST cache.

### S3: Detection loop inverted
Walk AST once per file. Build node-type index: `{Import: [n1,n2], ImportFrom: [n3], ...}`.
For each entry, look up `entry.detection.primary.ast_type` in the index. Check only
matching nodes. O(files × relevant_nodes) instead of O(files × entries × all_nodes).

Add yield checkpoints every 10 files using `current_yield_check()` + `YIELD_SLEEP`.

### S4: Analysis results as mediator nodes
Register `compat.analysis.{module_name}` as mediator nodes. TTL=60s (same as
posture.modules). Persist=True. Depends on index.scan (cascade when files change).
Any endpoint or handler that needs analysis reads from mediator cache — never runs
fresh analysis in a request handler.

### S5: Heavy operations via WorkQueue
`/api/compat/analyze` submits analysis to WorkQueue at HIGH priority (user clicked button).
`/api/compat/assess` same. Background refreshes use BACKGROUND(5) priority. Web requests
never blocked — CRITICAL tasks bypass capacity. Workers yield to web requests via
cooperative yielding.

### S6: Handlers use peek(), never create orchestrators
Every handler in code_scanner.py, executor.py, posture.py uses `mediator.peek("compat.orchestrator")`.
If None: legacy path. If available: use cached compat data from mediator. No try/except.
No CompatOrchestrator.create(). No analysis in handlers.

### S7: State machine publishes via EventBus
Step state transitions publish events: `mediator.subscribe("compat.step.*", callback)`.
The SSE bridge picks them up. Frontend gets real-time updates without polling.

### S8: Fix engine invalidates mediator
After applying fixes: `mediator.bust_path("compat.analysis.{module}")` with cascade.
This invalidates the cached analysis, posture.modules, posture.full, posture.summary.
Next request recomputes from the fixed files. No manual rescan needed.

### S9: compute_code_floor reads from compat database
Instead of hardcoded regex lists, compute_code_floor queries the compat registry for
Python entries and converts detection rules to its pattern format. One source of truth.
The 5 new patterns in module_intel.py and the 7 in test_env.py are removed.

### S10: Python backend extends ParserRegistry
The compat python_backend.py should extend PythonParser or use it for parsing, not
duplicate it. The compat-specific logic (node matching against detection rules) layers
on top of the existing parser infrastructure.

### S11: Import resolver uses existing infrastructure
Import graph built from PythonParser's ImportInfo (already extracted in one walk).
Cross-module resolution uses ScanView for file lookup and index.symbols for symbol resolution.
No re-parsing files that the parser registry already parsed.

### S12: All 37 specs rewritten
Every spec that designs a component the program already has must be rewritten to use the
existing component. The detection engine spec must reference ScanView, ParserRegistry,
yield checkpoints. The batch runner spec must reference WorkQueue. The API spec must
reference mediator.get(), dispatch(), peek(). The architecture spec must show the mediator
in the layer diagram.

---

## Part 7: Execution Order

1. **Rewrite the specs** — All 37 documents must reference the program's systems.
   No component is designed standalone. Every component uses mediator, index, WorkQueue,
   parser registry where applicable.

2. **Fix the foundation** — Wire FeatureRegistry into mediator. Wire orchestrator into
   mediator. Delete _cached.py.

3. **Fix the detection engine** — Invert the loop, use ScanView, use parser registry,
   add yield checkpoints. Cache results in mediator.

4. **Fix the handlers** — Replace all CompatOrchestrator.create() with mediator.peek().
   Remove try/except fallback pattern. Restore handler simplicity.

5. **Fix the frontend** — Remove blocking calls. Fix hardcoded version. Use mediator
   cascade instead of manual rescan.

6. **Fix the bugs** — Mark-done logic, double-apply, false positives, duplicated logic.

7. **Unify patterns** — Single source of truth from compat database to compute_code_floor.

8. **Connect events** — State machine → EventBus → SSE → frontend.
