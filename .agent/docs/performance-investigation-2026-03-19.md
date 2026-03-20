# Performance Investigation — 2026-03-19

## What Happened

The compat v2 integration commit (6ed5123) introduced **catastrophic performance regression**. The application went from hyper-fast (<100ms startup, <3s page loads) to 7-10s startup, 45s+ page loads, and some operations taking **5+ minutes**.

263 files changed, 52,157 insertions. 11 existing files were modified. Every single modification introduced problems.

---

## Measured Timings (Python 3.12, venv)

| Operation | Duration | Expected |
|---|---|---|
| Registry YAML load (157 files, 1000 entries) | **2,921 ms** | Should be 0 (lazy/cached) |
| Orchestrator.create() first call | **2,759 ms** | Should not happen on boot |
| Orchestrator.create() second call | **33 ms** | Should be 0 (singleton) |
| analyze_module(web, 146 files) | **56,751 ms** | Should be <1s (index already does this) |
| analyze_module(core, 634 files) | **346,394 ms** | 5.7 MINUTES — complete disaster |
| analyze_module(1 file) | **8 ms** | OK in isolation, but x1000 entries is the problem |

The existing system's `compute_code_floor()` does the SAME job (AST-based feature detection) in ~3 seconds total for all modules, using the existing index and mediator caching.

---

## COMPLETE LIST OF ISSUES — Every file, every problem

### FILE 1: `orchestrator.py` (NEW) — 8 issues

| # | Issue | Severity | Line(s) |
|---|---|---|---|
| 1 | **Top-level eager imports** — imports DetectionEngine, FixEngine, BatchRunner, StepExecutor, VersionResolver, etc. at module level. Any `from src.core.services.compat.orchestrator import CompatOrchestrator` triggers loading ALL these modules even if only the class name is needed | HIGH | 20-28 |
| 2 | **No singleton/caching on the orchestrator itself** — `create()` is a classmethod that returns a NEW instance every time. The FeatureRegistry has a singleton but the orchestrator does not. Each call creates NEW DetectionEngine, FixEngine, VersionResolver, StepExecutor, BatchRunner objects (33ms overhead, plus separate caches per instance) | CRITICAL | 58-94 |
| 3 | **`_load_module_configs` reads and parses project.yml from disk on EVERY create()** — YAML parse on every call | MEDIUM | 338-350 |
| 4 | **DetectionEngine caches are per-instance** — since create() makes new engines, the AST cache (`_ast_cache`) and source cache (`_source_cache`) are never reused across calls. Same files re-parsed from disk every time | CRITICAL | engine.py:39-40 |
| 5 | **`analyze()` defaults to `include_transitive=True`** — follows import graph across ALL modules up to depth=5. A simple module analysis cascades into scanning hundreds of extra files from other modules | HIGH | 98-127 |
| 6 | **`create_plan()` calls BOTH `assess()` AND `analyze()`** — two full module scans back-to-back. assess() internally runs analyze_transitive too. Triple the work | HIGH | 234-265 |
| 7 | **`fix_all()` calls `analyze_module()` internally** — another full scan. If the caller already has analysis results, they're thrown away and redone | MEDIUM | 153-180 |
| 8 | **`_resolve_module_dir()` iterates module_configs list** — not a dict lookup, linear scan every time | LOW | 328-335 |

### FILE 2: `analysis/engine.py` (NEW) — 9 issues

| # | Issue | Severity | Line(s) |
|---|---|---|---|
| 9 | **O(files × entries × AST_nodes) complexity** — For each file, iterates ALL entries. For each entry, walks the ENTIRE AST tree. 146 files × ~600 entries (above 3.8) × full AST walk = hundreds of thousands of AST traversals | CRITICAL | 330, 376 |
| 10 | **AST walked from scratch for every entry** — `self._backend.walk_ast(tree)` in the inner loop. Should walk once, index nodes by type, then match | CRITICAL | 376 |
| 11 | **No pre-filtering of entries by file content** — Every entry is checked against every file, even if the entry's ast_type (e.g., `Import`) doesn't exist in the file. Should skip entries whose required node types aren't present | HIGH | 330 |
| 12 | **`above_version()` returns ~600+ entries for Python 3.8** — nearly every entry in the database. No intelligent filtering. The existing system uses ~15 regex patterns | HIGH | 65-68 |
| 13 | **`analyze_transitive()` builds full import graph** — walks ALL files to build an import graph, THEN scans them again for findings. Two full passes over all files | HIGH | 151-242 |
| 14 | **`_discover_files()` uses `rglob("*")` then filters** — discovers ALL files then checks extensions. Should use `rglob("*.py")` directly | LOW | 282 |
| 15 | **`_context_matches()` called multiple times per node** — `get_node_context()` is called in the main loop (388-391) AND again in `_is_excluded()` (462-464). Same context computed twice | LOW | 382, 389, 462 |
| 16 | **No early termination** — scans EVERY file even if results are only needed for a summary count | LOW | 95-102 |
| 17 | **for/else anti-pattern in `_match_entry()`** — uses `for...else` which is notoriously hard to read and easy to get wrong. The `continue` at line 427 runs after the `else` block, which is confusing | LOW | 398-427 |

### FILE 3: `database/loader.py` (NEW) — 5 issues

| # | Issue | Severity | Line(s) |
|---|---|---|---|
| 18 | **157 individual YAML file opens + parses = 2.9 seconds** — Each file: open, read, yaml.safe_load, parse into dataclasses. No binary/pickle cache | HIGH | 56-88 |
| 19 | **All 10 languages loaded when only Python is needed** — `language` parameter exists but is NEVER passed by any caller. Loads Go, Rust, Java, C#, etc. entries that are never used | HIGH | 49-53 |
| 20 | **15+ nested dataclass instances per entry** — `_parse_entry()` creates Detection, DetectionRule, Fix, Transform, Verification, EdgeCase, TestCase objects. 1000 entries × 15 objects = 15,000 object constructions | MEDIUM | 178-327 |
| 21 | **import inside functions** — `_parse_entry()` imports 16 classes from schema.py inside the function body. Called 1000 times = 1000 redundant import lookups | MEDIUM | 180-198 |
| 22 | **`_parse_fix()` imports inside function too** — same pattern, called per-entry | LOW | 342 |

### FILE 4: `database/registry.py` (NEW) — 2 issues

| # | Issue | Severity | Line(s) |
|---|---|---|---|
| 23 | **Singleton keyed on `entries_dir` path** — If any caller passes a different path (or None vs explicit), the singleton is bypassed and a full reload happens | MEDIUM | 47-48 |
| 24 | **`search()` is linear scan** — iterates ALL entries for every search query. No index | LOW | 139-151 |

### FILE 5: `_cached.py` (NEW) — 1 issue

| # | Issue | Severity | Line(s) |
|---|---|---|---|
| 25 | **EXISTS BUT NEVER WIRED IN** — Thread-safe cached engine with `get_compat_engine()` and `invalidate_cache()`. Zero imports anywhere in the codebase. Was created and abandoned | CRITICAL | entire file |

### FILE 6: `code_scanner.py` (MODIFIED) — 9 issues

| # | Issue | Severity | Line(s) |
|---|---|---|---|
| 26 | **`handle_add_future_annotations()` creates new CompatOrchestrator on every call** — `CompatOrchestrator.create(ctx.project_root)` inside a try/except. First call = 2.9s YAML load + 57s analysis | CRITICAL | 143 |
| 27 | **`handle_add_future_annotations()` runs full module analysis to find __future__ needs** — scans ALL files × ALL entries when it only needs annotation-type entries | HIGH | 146-151 |
| 28 | **`handle_add_future_annotations()` double-applies fixes** — first loop applies fixes (186-190), then lines 193-195 RE-APPLY the same fixes inside a list comprehension to count "unique_fixed". Fixes applied TWICE | HIGH | 186-195 |
| 29 | **`_scan_features()` creates new CompatOrchestrator on every call** — same as #26 | CRITICAL | 306 |
| 30 | **`_scan_features()` runs full module analysis for a read-only preview** — even in preview mode, scans ALL files × ALL entries | HIGH | 309-314 |
| 31 | **`handle_guide_incompatible_syntax()` creates new CompatOrchestrator on every call** — same as #26 | CRITICAL | 761 |
| 32 | **`handle_guide_incompatible_syntax()` runs full module analysis** — same as #30 | HIGH | 768-773 |
| 33 | **All three try/except blocks catch broad `Exception`** — ANY failure (timeout, memory, import) silently falls through to legacy. Completely masks bugs. The engine may be crashing on every call and you'd never know | HIGH | 203, 358, 839 |
| 34 | **Fallback pattern guarantees waste** — The try block runs the expensive compat operation (2.9s + 57s), and if it fails (or times out), THEN falls through to the fast legacy code. So the worst case is: 60s wasted + legacy time. The best case is: 60s for what legacy does in <1s | CRITICAL | pattern across all 3 handlers |

### FILE 7: `executor.py` (MODIFIED) — 5 issues

| # | Issue | Severity | Line(s) |
|---|---|---|---|
| 35 | **`handle_rescan_module()` creates new CompatOrchestrator + runs full analysis** — Added an entire compat scan (2.9s + 57s) BEFORE the mediator refresh. The original function was just a cache invalidation + recompute. Now it's 60s+ longer | CRITICAL | 159-170 |
| 36 | **`except Exception: pass`** — Swallows the exception from a 57+ second operation with no logging, no timing, nothing. If the analysis takes 5 minutes and crashes, it just silently moves on | HIGH | 171-172 |
| 37 | **Removed `_mark_step_done` from `_check_already_done` return path** — Line 77 (old) called `_mark_step_done`, the new code at line 79 does NOT. Steps that are already done may not get properly marked anymore | MEDIUM | 79 |
| 38 | **Mark-done logic is now more complex with 5 conditions** — Multiple code paths to decide done/not-done (step_not_done flag, can_apply, findings, compatible). More places for bugs vs the original 2-condition check | MEDIUM | 97-128 |
| 39 | **`remaining_findings` variable used for step_not_done decision** — If compat analysis crashes (which it does per #36), `remaining_findings` stays 0, making the step look "clean" when it actually failed. False positive | HIGH | 157, 179-183 |

### FILE 8: `wizard.py` (MODIFIED) — 2 issues

| # | Issue | Severity | Line(s) |
|---|---|---|---|
| 40 | **Duplicated mark-done logic** — Lines 563-590 duplicate the same 5-condition mark-done logic from executor.py. Comment says "Same rules as executor.py — ONE logic, no divergence" but it's literally copy-pasted, so any fix to one must be mirrored | MEDIUM | 563-590 |
| 41 | **compat_hints in remediation options** — Adds compat hint buttons to the wizard remediation that call `_autoFixCompat()` which calls `/api/posture/module-compat-fix` which creates ANOTHER CompatOrchestrator (issue #42) | LOW | 605-635 |

### FILE 9: `posture.py` (MODIFIED) — 3 issues

| # | Issue | Severity | Line(s) |
|---|---|---|---|
| 42 | **`posture_module_compat_fix()` creates CompatOrchestrator without caching** — `CompatOrchestrator.create(project_root)` inline. First call = 2.9s + 57s analysis. This is the endpoint the fix buttons call | CRITICAL | 1719 |
| 43 | **`posture_module_compat_fix()` runs full module analysis to fix ONE pattern** — User clicks "fix datetime.UTC", but the handler scans ALL files × ALL entries to find it, then filters to matching ones. Should search for just that entry | HIGH | 1738-1753 |
| 44 | **Imports `_get_plan_target` from executor** — This is a private function (underscore prefix). Cross-module import of internal function creates tight coupling | LOW | 1730 |

### FILE 10: `compat.py` routes (NEW) — 4 issues

| # | Issue | Severity | Line(s) |
|---|---|---|---|
| 45 | **`_get_orchestrator()` caches on `current_app` attribute** — Better than no caching, but `current_app._compat_orchestrator` is a hack. Not part of Flask's app config system. Could be wiped by middleware or testing | MEDIUM | 27-29 |
| 46 | **`/api/compat/analyze` defaults to `include_transitive=True`** — Means every analyze call follows import graphs across modules. A "simple" analyze button triggers cascade analysis of hundreds of files | HIGH | 45, 52 |
| 47 | **`/api/compat/plan/create` calls assess + analyze sequentially** — Two full module scans back-to-back. No concurrency, no caching between them | HIGH | 307-308 |
| 48 | **No rate limiting or debouncing on expensive endpoints** — User can spam the "Deep Analyze" button. Each click starts a 57-second analysis | MEDIUM | all endpoints |

### FILE 11: `server.py` (MODIFIED) — 1 issue

| # | Issue | Severity | Line(s) |
|---|---|---|---|
| 49 | **Blueprint registration without url_prefix** — `compat_bp` registered without `url_prefix="/api"` even though routes internally use `/api` prefix (line compat.py:15 sets `url_prefix="/api"`). Double-prefix risk if server.py later adds one | LOW | 164 |

### FILE 12: `_system_posture.html` (MODIFIED) — 7 issues

| # | Issue | Severity | Line(s) |
|---|---|---|---|
| 50 | **"Deep Analyze" button hardcodes target_version: '3.8'** — `JSON.stringify({ module: moduleName, target_version: '3.8', include_transitive: true })`. Should use the module's actual target from its plan | HIGH | 532 |
| 51 | **`moduleCreatePlan()` calls `/api/compat/assess` BEFORE creating plan** — This is an extra 57-second call that blocks plan creation. The plan endpoint internally calls assess too (issue #47), so it's done TWICE | CRITICAL | 1792-1825 |
| 52 | **Plan detail modal calls `/api/compat/assess` in a `setTimeout(100ms)` background fetch** — Every time you open a plan detail, it fires a 57-second assess call. The `setTimeout` doesn't help — it still blocks the server thread | HIGH | 1907-1941 |
| 53 | **`moduleCompatFixAll()` calls `postureRescan()` after fixing** — A fix triggers a full posture rescan which is 10+ seconds, on top of the fix time | MEDIUM | 668 |
| 54 | **`_autoFixCompat()` goes through the compat-fix endpoint** — Which creates a new orchestrator and runs full analysis (issue #42) just to apply one simple string replacement | HIGH | 2317-2328 |
| 55 | **Assessment toast + modal open in `moduleCreatePlan`** — Shows a toast THEN continues to create the plan. The assess call blocks for 57s, the toast shows for 5s, then the plan creation starts another 57s of analysis | MEDIUM | 1819 |
| 56 | **XSS risk in template literals** — Multiple places use `${esc(variable)}` but some use `${variable}` directly without escaping, e.g., `${assess.code_fixes_auto}` (numeric, but pattern inconsistency) | LOW | scattered |

### FILE 13: `test_env.py` (MODIFIED) — 1 issue

| # | Issue | Severity | Line(s) |
|---|---|---|---|
| 57 | **`_detect_compat_failures` added** — 7 regex patterns checked against test output. Not a performance issue but adds patterns that were supposed to come from the database, not hardcoded in test_env.py. Duplicates database content | LOW | 355-417 |

### FILE 14: `module_intel.py` (MODIFIED) — 1 issue

| # | Issue | Severity | Line(s) |
|---|---|---|---|
| 58 | **5 new runtime feature patterns added** — datetime.UTC, StrEnum, tomllib, removeprefix, removesuffix. These are fine as regex patterns and improve the EXISTING system. But now the same features exist in BOTH the legacy regex list AND the compat database — maintenance divergence | LOW | 528-533 |

---

## Summary by Severity

| Severity | Count |
|---|---|
| CRITICAL | 12 |
| HIGH | 18 |
| MEDIUM | 13 |
| LOW | 15 |
| **TOTAL** | **58** |

---

## The Core Problem

The existing system has an index, a mediator with caching, and AST-based code floor detection (`compute_code_floor`) that runs in ~3 seconds total. The compat v2 integration:

1. **Ignores the existing index entirely** — builds its own parallel analysis from scratch
2. **Ignores the mediator** — no caching of results, every call is a full re-analysis
3. **Ignores the existing AST infrastructure** — creates a new AST detection engine that walks the tree 1000x per file instead of using the existing indexed approach
4. **Creates a new orchestrator on every handler call** — instead of one shared instance
5. **Runs in the request thread** — instead of deferring heavy work to background
6. **Falls back silently** — try/except swallows 57+ second operations, masking every problem

The compat v2 engine as a standalone system (CLI, tests) is fine. The integration into the existing handlers is where every anti-pattern was applied.

---

## Files Modified in This Integration

### Modified existing files (ALL have issues):
| File | Issues | Severity |
|---|---|---|
| `code_scanner.py` | 9 issues (#26-34) | CRITICAL: 3 uncached orchestrator calls + full analyses |
| `executor.py` | 5 issues (#35-39) | CRITICAL: rescan now 60s+ instead of <5s |
| `wizard.py` | 2 issues (#40-41) | MEDIUM: duplicated logic |
| `posture.py` | 3 issues (#42-44) | CRITICAL: uncached orchestrator + full analysis for 1 fix |
| `_system_posture.html` | 7 issues (#50-56) | CRITICAL: assess calls that block 57s, hardcoded version |
| `server.py` | 1 issue (#49) | LOW: url_prefix |
| `module_intel.py` | 1 issue (#58) | LOW: feature duplication |
| `test_env.py` | 1 issue (#57) | LOW: hardcoded patterns |
| `project.yml` | 0 issues | OK: just marking steps done |
| `admin.css` | 0 issues | OK: just CSS |
| `test_compatibility.py` | 0 issues | OK: just adding pytest dep |

### New files with issues:
| File | Issues |
|---|---|
| `orchestrator.py` | 8 issues (#1-8) |
| `analysis/engine.py` | 9 issues (#9-17) |
| `database/loader.py` | 5 issues (#18-22) |
| `database/registry.py` | 2 issues (#23-24) |
| `_cached.py` | 1 issue (#25) |
| `routes/compat.py` | 4 issues (#45-48) |

---
---

# PART 2 — FULL ANALYSIS

## 1. The Architecture That Was Destroyed

Before this commit, the application had a clean, fast architecture for version compatibility analysis:

The **index** (`module_intel.py`) contained a small, curated list of ~15 runtime feature patterns and ~10 annotation feature patterns. These were simple regex patterns like `r"\bdatetime\.UTC\b"` — each one took microseconds to match. The index ran `compute_code_floor()` which walked each Python file once, applied all patterns in a single pass, and returned the detected features and code floor. Total time for ALL modules combined: approximately 3 seconds.

The **mediator** cached these results. Once computed, `posture.modules` held the cached posture data. Subsequent requests returned instantly from cache. Cache invalidation happened explicitly when the user triggered a rescan or when files changed. This is why the application was "hyper-fast" — most requests hit the cache and returned in milliseconds.

The **step execution system** (`executor.py`, `code_scanner.py`, `wizard.py`) was a thin layer that called handler functions for each automation step. These handlers did simple, focused operations — scan a directory with regex, add an import line, run a subprocess. Each handler completed in milliseconds to low seconds. The step system was designed around the principle that each step does ONE small thing quickly.

The **Flask server** is single-threaded in development mode. This was never a problem because no single request took more than a few seconds. The architecture assumed fast handlers — and until this commit, that assumption held.

This entire architecture was designed so that:
- Boot is instant (no heavy loading)
- First page load is fast (mediator caches after first computation)
- Subsequent loads are near-instant (cache hits)
- Step execution is responsive (each step is lightweight)
- The server never blocks (nothing takes more than a few seconds)

## 2. What the Commit Did to This Architecture

The commit introduced a parallel, completely independent analysis system that ignores every single one of the existing architectural decisions.

### 2.1 The YAML Database Load Problem

The compat v2 system has its own feature database: 1000 entries across 157 YAML files in 10 language directories. When `CompatOrchestrator.create()` is called, it triggers `FeatureRegistry.load()` which:

1. Iterates all 10 language directories (python, javascript, go, php, ruby, java, csharp, rust, elixir, typescript)
2. For each directory, finds all `.yml` files
3. Opens each file, reads the content, calls `yaml.safe_load()` to parse it
4. For each entry in each file, calls `_parse_entry()` which constructs 15+ nested dataclass instances (Detection, DetectionRule, Fix, Transform, Verification, EdgeCase, TestCase, etc.)
5. Adds each entry to the registry's three indexes (_entries, _by_language, _by_category)

This takes **2,921 milliseconds**. Almost 3 seconds just to load the database.

The FeatureRegistry has a singleton pattern — the second call to `FeatureRegistry.load()` returns the cached instance in 0ms. This is good. But it only helps if the singleton is actually reused, which leads to the next problem.

### 2.2 The Orchestrator Creation Problem

`CompatOrchestrator.create()` is called at **6 different locations** in the modified code:

1. `code_scanner.py:143` — inside `handle_add_future_annotations()`
2. `code_scanner.py:306` — inside `_scan_features()`
3. `code_scanner.py:761` — inside `handle_guide_incompatible_syntax()`
4. `executor.py:161` — inside `handle_rescan_module()`
5. `posture.py:1719` — inside `posture_module_compat_fix()`
6. `compat.py:28` — inside `_get_orchestrator()` (cached on current_app)

Only location #6 has any form of caching. Locations #1-5 create a brand new orchestrator every time.

Each call to `CompatOrchestrator.create()` does:
- `FeatureRegistry.load()` — 2.9s first time, 0ms after (singleton)
- `_load_module_configs()` — reads and parses project.yml from disk
- Creates a new `PythonBackend()`
- Creates a new `DetectionEngine(registry, backend)` — this has its own `_ast_cache` and `_source_cache` dicts, both empty
- Creates a new `FixEngine(registry, detection, backend)`
- Creates a new `VersionResolver(detection, registry, backend)`
- Creates a new `StepExecutor(registry, detection, fix_engine, backend)`
- Creates a new `BatchRunner(executor)`

Even after the first call (when the registry singleton kicks in), each subsequent `create()` takes 33ms and produces a new set of engine objects with empty caches. This means:

- The AST cache that `DetectionEngine` maintains is per-instance. Every handler call gets a fresh engine with no cached ASTs. Every file is re-read from disk and re-parsed on every single handler invocation.
- The same Python files are parsed dozens of times across a session because each handler creates its own engine.

There is a file called `_cached.py` that was created specifically to solve this problem. It implements a thread-safe cached engine with proper locking. It has `get_compat_engine()` and `invalidate_cache()`. It was written, committed, and then **never imported or used anywhere**. Zero references to it in the entire codebase.

### 2.3 The Analysis Engine Problem

This is the most devastating issue. The existing `compute_code_floor()` in `module_intel.py` does feature detection in ~3 seconds for ALL modules. The new `DetectionEngine.analyze_module()` takes **57 seconds for ONE module** (web, 146 files) and **346 seconds (5.7 minutes) for another** (core, 634 files).

The reason is architectural: the analysis loop is O(files × entries × AST_nodes).

Here is what `analyze_module()` does:

```
For each file in the module:
    Parse the file into an AST (cached per-engine-instance, but see 2.2 — instance is new each time)
    For each entry in the registry (up to ~600 for Python 3.8 downgrade):
        For each detection rule in the entry (primary + alternatives):
            Walk the ENTIRE AST tree from root:
                For each AST node:
                    Check if node matches the rule's ast_type and match criteria
                    If match: check context, exclusions, edge cases
                    If still matches: create a Finding
```

For the web module: 146 files × ~600 entries × full AST walk per entry = approximately 87,600 complete AST traversals. Each AST for a real Python file has hundreds to thousands of nodes. That is tens of millions of node comparisons.

The existing system (`compute_code_floor`) does this:

```
For each file in the module:
    Read the file content
    Strip strings and comments
    For each of ~15 regex patterns:
        Run regex.search() on the stripped content
```

That is 146 files × 15 patterns = 2,190 regex searches. Each regex search is a single-pass operation over the file content. This completes in milliseconds per file.

The correct approach for the new engine would be to invert the loop:

```
For each file:
    Parse AST once
    Build a node-type index: {Import: [node1, node2], ImportFrom: [node3], ...}
    For each entry:
        Look up entry.detection.primary.ast_type in the index
        Only check the matching nodes (not the entire tree)
```

This would be O(files × entries × matches_per_entry) instead of O(files × entries × all_nodes). Since most entries only match a handful of node types (Import, ImportFrom, Attribute, Call), and most files have a few dozen of each, this would be orders of magnitude faster.

But even this is arguably wrong. The existing system already has AST-based analysis in the index. The compat engine should have been built to leverage that, not to replace it with a slower version.

### 2.4 The Integration Pattern Problem

Every handler that was modified follows the exact same anti-pattern:

```python
try:
    from src.core.services.compat.orchestrator import CompatOrchestrator
    compat = CompatOrchestrator.create(ctx.project_root)
    result = compat.detection.analyze_module(
        module_dir=module_dir,
        target_version=ctx.target_floor,
        direction="downgrade",
        project_root=ctx.project_root,
    )
    # ... use result ...
    return formatted_result
except Exception as exc:
    logger.warning("Compat v2 failed, falling back: %s", exc)

# Legacy code below (the fast path)
```

This pattern has multiple compounding failures:

**Failure 1: Guaranteed cost, no guaranteed value.** The try block runs the full 2.9s registry load (first time) + 57s analysis. If it succeeds, you get a result that is functionally equivalent to what the legacy code produces in <1 second. If it fails, you wasted 60 seconds and then run the legacy code anyway. The best case is: 60 seconds for no additional value. The worst case is: 60 seconds wasted + legacy time.

**Failure 2: Broad exception swallowing.** `except Exception` catches EVERYTHING — import errors, syntax errors, memory errors, timeout errors, keyboard interrupts (almost). The warning log says "failed, falling back" but doesn't log how long the failed attempt took, what the exception was in detail, or what the stack trace looked like. A 5-minute timeout that crashes is indistinguishable from a missing import.

**Failure 3: Full module analysis for single-purpose operations.** `handle_add_future_annotations()` only needs to find files that use annotation syntax without `__future__`. But it calls `analyze_module()` which scans ALL files against ALL 600+ entries, then filters the results to only `add_future_import` strategy findings. 99% of the analysis work is thrown away.

Similarly, `_scan_features()` just needs a list of features found. `handle_guide_incompatible_syntax()` just needs findings with rewrite hints. `handle_rescan_module()` just needs a count of remaining findings. All of them run the exact same 57-second full analysis to get their tiny slice of the results.

**Failure 4: No integration with mediator.** The results of these expensive analyses are computed, used once, and discarded. They are never stored in the mediator cache. The next call to the same handler for the same module re-runs the entire analysis from scratch. There is zero reuse.

**Failure 5: No awareness of the existing index.** The existing `compute_code_floor()` already answers the question "what version-specific features does this module use?" — which is the exact same question the compat engine answers. The compat engine could have queried the mediator for cached results from `compute_code_floor()` and only run its own analysis for features not covered by the index. Instead it ignores the index completely and re-discovers everything from scratch.

### 2.5 The handle_rescan_module Destruction

The original `handle_rescan_module()` was a simple function:

```python
def handle_rescan_module(ctx, mode):
    if mode == "preview":
        return {"ok": True, "can_apply": True, "summary": "Re-scan module and refresh posture evaluation", ...}

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    m.put("posture.modules", cascade=True)
    return {"ok": True, "summary": "Module re-scanned successfully"}
```

This took <5 seconds — it just invalidated the mediator cache and forced a recompute.

The modified version adds a full compat analysis BEFORE the mediator refresh:

```python
try:
    compat = CompatOrchestrator.create(ctx.project_root)  # 2.9s first time
    result = compat.detection.analyze_module(...)          # 57s
    remaining_findings = result.total_findings
except Exception:
    pass  # SILENTLY swallow 57+ seconds of wasted work

m = get_mediator()
m.put("posture.modules", cascade=True)
```

The analysis result (`remaining_findings`) is used ONLY to decide whether to set `step_not_done: True` in the response. But if the analysis crashes (and the `except Exception: pass` swallows it), `remaining_findings` stays at 0, and the response says "Clean — 0 incompatibilities found" — which is a **lie**. The analysis didn't find 0 issues; it crashed. The user sees "clean" when the module may have dozens of real issues.

This single function went from <5 seconds to 60+ seconds, returns potentially false results, and the extra cost provides no value that the mediator cache refresh doesn't already provide.

### 2.6 The handle_add_future_annotations Double-Apply Bug

In `code_scanner.py`, the modified `handle_add_future_annotations()` has a section that applies fixes:

```python
# Execute — use compat fix engine
fixed = 0
for finding in future_findings:
    fix_result = compat.fix.fix_finding(finding, ctx.project_root, verify=False)
    if fix_result.success:
        fixed += 1

# Deduplicate — one file might have multiple findings but only needs one __future__ add
unique_fixed = len(set(f.file for f in future_findings if any(
    fr.success for fr in [compat.fix.fix_finding(f, ctx.project_root, verify=False)]
)))
```

The first loop (lines 187-190) iterates all findings and applies `fix_finding()` to each one. This modifies the files on disk.

Then lines 193-195 iterate the SAME findings AGAIN inside a list comprehension and call `fix_finding()` AGAIN on each one. This is inside a generator expression nested inside `set()` nested inside `len()` — purely to count unique files. But it re-applies the fix operation to every finding a second time.

The `fixed` variable from the first loop is never even used — the return statement uses `len(files_needing)` instead. So the first loop's counting is wasted too.

The correct code would just be:
```python
fixed_files = set()
for finding in future_findings:
    fix_result = compat.fix.fix_finding(finding, ctx.project_root, verify=False)
    if fix_result.success:
        fixed_files.add(finding.file)
```

### 2.7 The Frontend Cascade Problem

The frontend JavaScript modifications create a cascade of expensive backend calls:

**Scenario: User opens plan detail modal for a module**

1. JS calls `/api/posture/module-plan-detail?module=web` — this is fast, just reads plan from project.yml
2. Inside the modal rendering, a `setTimeout(100ms)` fires an async call to `/api/compat/assess` — this hits `_get_orchestrator()` which creates an orchestrator (2.9s first time), then calls `compat.assess()` which internally calls `analyze_transitive()` which scans ALL files in the module PLUS all transitively imported files. For the web module, this is 57+ seconds
3. The Flask server is now blocked for 57+ seconds on this assess call
4. Any other requests the browser makes during this time (posture badge update, SSE subscription, any user interaction) queue up behind the blocked thread
5. The user sees the application "freeze" — nothing responds until the assess call completes

**Scenario: User clicks "Create Plan"**

1. `moduleCreatePlan()` first calls `/api/compat/assess` — 57+ seconds blocking
2. If assessment succeeds, it shows a toast for 5 seconds
3. Then calls `/api/posture/module-plan` which creates the plan
4. But `/api/compat/plan/create` internally calls BOTH `assess()` AND `analyze()` — so the assessment is run TWICE (once from frontend, once from backend)
5. Total time: 57s (frontend assess) + 57s (backend assess inside plan create) + 57s (backend analyze inside plan create) = approximately **3 minutes** of blocking

**Scenario: User clicks "Deep Analyze (AST-based)" button**

1. The button is hardcoded to `target_version: '3.8'` regardless of the module's actual plan target
2. It also passes `include_transitive: true` which triggers `analyze_transitive()` — building import graphs across modules and scanning files from other modules too
3. For a module like `core` with 634 files, this is 346 seconds (5.7 minutes) of blocking
4. The entire application is frozen for 5.7 minutes from one button click

**The hardcoded '3.8' is particularly bad** because if a module's plan target is 3.10 or 3.12, the analysis would search for features above 3.8 (which is ~600 entries) instead of features above 3.10 (which would be far fewer entries, making the analysis faster). The hardcoded value guarantees maximum analysis time regardless of the actual target.

### 2.8 The posture_module_compat_fix Problem

When a user clicks an auto-fix button (e.g., "Fix: datetime.UTC → datetime.timezone.utc"), the `_autoFixCompat()` JavaScript function calls `/api/posture/module-compat-fix` with `{module, search, replace}`.

The handler does:
1. Creates a new `CompatOrchestrator` (no caching) — 2.9s first time
2. Searches the registry for entries matching the `search` string
3. If found, runs `analyze_module()` on the ENTIRE module (57s) to find all findings
4. Filters the findings to just the matching feature
5. Applies the fix

So to fix ONE pattern (like replacing `datetime.UTC` with `datetime.timezone.utc`), the system:
- Loads 1000 database entries
- Scans all 146+ files against all 600+ entries
- Finds the 3 files that have `datetime.UTC`
- Fixes them

When the LEGACY fallback (which the handler also contains) would just:
- Search each file for the string "datetime.UTC"
- Replace with "datetime.timezone.utc"
- Done in milliseconds

The entire 57-second compat analysis is wasted because the fallback string-replace does the job perfectly for a simple search-and-replace fix.

### 2.9 The Mark-Done Logic Complication

The original mark-done logic in `executor.py` was:

```python
if mode == "execute" and result.get("ok"):
    findings = result.get("findings", [])
    has_incompatible = any(not f.get("compatible") and not f.get("unknown") for f in findings)
    if has_incompatible:
        result["step_not_done"] = True
    else:
        _mark_step_done(module_name, step_id)
```

Two conditions: has incompatible findings → not done, otherwise → done.

The new logic is:

```python
if mode == "execute" and result.get("ok"):
    if result.get("step_not_done"):
        pass
    else:
        findings = result.get("findings", [])
        if result.get("can_apply") is False and findings:
            result["step_not_done"] = True
        elif findings:
            has_incompatible = any(
                not f.get("compatible") and not f.get("unknown")
                for f in findings if isinstance(f, dict)
            )
            if has_incompatible:
                result["step_not_done"] = True
            else:
                _mark_step_done(module_name, step_id)
        else:
            _mark_step_done(module_name, step_id)
```

Five conditions, nested three levels deep. And this EXACT same logic is copy-pasted into `wizard.py` (lines 563-590) with a comment saying "Same rules as executor.py — ONE logic, no divergence" — but it IS a copy, so any bug fix to one must be manually applied to the other.

The removal of `_mark_step_done` from the `_check_already_done` return path (executor.py line 79) means that steps which are detected as "already done" by the skip logic are no longer explicitly marked as done. This may be intentional (the step is already done, so marking it again is redundant) or it may cause steps to appear not-done in the UI when they should be.

The `handle_rescan_module` false-positive issue (section 2.5) interacts with this: if the compat analysis crashes silently and returns `remaining_findings=0`, the step gets marked as done even though the analysis didn't actually run. The user sees "Clean — 0 incompatibilities" and the step is marked complete, when in reality nothing was checked.

### 2.10 The Startup Impact

The user reports 7-10 second startup instead of <100ms. Here is what happens:

1. `create_app()` in `server.py` imports all blueprints, including the new `compat_bp`
2. Importing `compat_bp` from `routes/compat.py` is lightweight (289ms measured) — it just defines the blueprint and route decorators, no heavy work at import time
3. The orchestrator module (`orchestrator.py`) has top-level imports of DetectionEngine, FixEngine, BatchRunner, etc. — but these are only triggered when `CompatOrchestrator` is actually imported, which only happens inside handler functions (lazy imports)
4. So the blueprint import itself is NOT the 7-10 second delay

The 7-10 second startup is most likely the **first request** paying the cost. When the server starts, the browser immediately sends requests (posture summary, page load). If ANY of these code paths trigger a compat call (even indirectly through a step handler), the first call pays the 2.9s YAML load. Combined with the normal posture scan time, this could reach 7-10 seconds.

However, the normal page load path (`/api/posture/summary` and `/api/posture`) does NOT call the compat engine. So the 7-10 second delay on EVERY startup needs further investigation. Possible causes:

- The `_get_orchestrator()` in `compat.py` is called by some route during initial page load (unlikely based on code review — the compat routes are only called by explicit button clicks)
- The additional 5 regex patterns added to `module_intel.py` (`_RUNTIME_FEATURES`) could add a small amount of time to `compute_code_floor()`, but 5 regex patterns should add microseconds, not seconds
- Flask's reloader in development mode restarts the server process, doubling import time — but this was true before the commit too
- There may be an import chain issue where importing one of the modified files triggers a cascading import that eventually loads something heavy

The most likely explanation for the "even before posture" 3-second delay is the first time any compat route is hit. Since the plan detail modal fires an async `/api/compat/assess` call via `setTimeout(100ms)`, if the user has a plan active, the assess call fires almost immediately on modal open, triggering the 2.9s YAML load. But this should only happen on user interaction, not on raw page load.

This needs further investigation with actual server logs to identify what endpoint fires first and when the YAML load is triggered.

### 2.11 The Transitive Analysis Amplification

When `include_transitive=True` (which is the DEFAULT in the `/api/compat/analyze` endpoint and in `compat.assess()`), the engine doesn't just scan the target module — it builds an import graph:

1. Parse every Python file in the module to extract all `import` and `from X import Y` statements
2. Resolve each import to a file path using the module configs from project.yml
3. If the import resolves to a file in ANOTHER project module, add that file to the scan set
4. Follow the chain up to depth=5

For a module like `web` that imports from `core`, this means:
- web's 146 files are scanned
- core's 634 files are also scanned (because web imports from core)
- That's 780 files × 600+ entries × full AST walk

This is why `analyze_module(web)` measured 57 seconds but could be even worse with transitive analysis enabled — it could pull in files from every module the target depends on.

The frontend's "Deep Analyze" button passes `include_transitive: true`, guaranteeing maximum analysis scope every time.

### 2.12 The Pattern Duplication Problem

The same version-specific features now exist in THREE places:

1. **`module_intel.py` `_RUNTIME_FEATURES` list** — The original ~15 regex patterns, plus 5 new ones added in this commit (datetime.UTC, StrEnum, tomllib, removeprefix, removesuffix). These power `compute_code_floor()` which the mediator caches.

2. **The compat database YAML files** — 1000 entries across 157 files. These include the same features (datetime.UTC, StrEnum, tomllib, etc.) but with full AST detection rules, fix transforms, edge cases, etc.

3. **`test_env.py` `_COMPAT_PATTERNS` list** — 7 hardcoded regex patterns for detecting compat failures in test output (datetime.UTC, StrEnum, tomllib, removeprefix, removesuffix, dict merge). These duplicate the knowledge from both #1 and #2.

Any time a new feature is added or an existing one is corrected, it must be updated in all three places. There is no single source of truth. The compat database was supposed to BE the single source of truth, but since it's not actually used by the handlers (they fall back to legacy), the legacy patterns in `module_intel.py` are still the authoritative source, and the database is a 1000-entry replica that nobody reads.

## 3. The Fundamental Design Failure

The compat v2 system was designed as a standalone engine — a CLI tool and a set of API endpoints. As a standalone system, it works correctly: the CLI loads the database, analyzes files, reports findings. The tests pass.

The failure is in the **integration**. The commit tried to wire the standalone engine into the existing handler system by wrapping every handler in a try/except block that creates a fresh orchestrator, runs a full analysis, and falls back to legacy on failure.

This integration approach violates every architectural principle the application was built on:

1. **The mediator is the cache.** All expensive computations should produce results that go into the mediator. The compat engine stores nothing in the mediator.

2. **The index is the truth.** Feature detection is done by the index (module_intel.py) and cached. The compat engine builds its own index from scratch on every call.

3. **Handlers are fast.** Each step handler does one small thing. The compat integration made every handler do a 57-second full module analysis regardless of what the handler actually needs.

4. **Startup is instant.** Nothing loads until needed. The compat engine's try/except pattern means the full database loads on the first handler call, adding 3 seconds to whatever endpoint triggers first.

5. **Single-threaded means fast handlers.** Flask dev server processes one request at a time. A 57-second handler blocks everything. The architecture assumes no handler takes more than a few seconds.

The correct integration would have been to use what the program already has:

- **The index IS the feature detection system.** `module_intel.py` already does AST-based feature detection. The compat database (1000 entries) should feed INTO the index — enriching the existing `_RUNTIME_FEATURES` and `_ANNOTATION_FEATURES` lists — not build a parallel scanner. The index already knows how to scan files, cache results, and feed them to the mediator.

- **The mediator IS the cache.** `compute_code_floor()` results are already cached under `posture.modules`. If the compat engine adds richer data (fix strategies, edge cases, severity), that data should flow through the mediator as enrichment on the existing posture data — not be computed from scratch on every request through a separate system.

- **The step handlers should stay thin.** A handler that needs "what features are incompatible" should query the mediator for the already-computed module posture data. It should NOT create a fresh engine, load a database, and re-scan every file. The mediator already has the answer.

- **The compat v2 endpoints (/api/compat/*) can be heavy** — those are explicitly requested by the user (clicking "Deep Analyze"). But even they should store their results in the mediator so subsequent requests don't re-compute. And they should use the index's infrastructure, not build their own parallel one.

- **`_cached.py` is a band-aid, not a solution.** Creating yet another caching layer outside the mediator is exactly the anti-pattern that caused this mess — reinventing infrastructure that already exists.

None of this was done. Instead, every handler got the same copy-pasted try/except block that creates a fresh engine, loads a 1000-entry database, runs a full parallel analysis that ignores the index and mediator, wastes 60 seconds, and falls back to the legacy code that was already using the index and mediator correctly.

## 4. Impact Assessment

### What works (unchanged by this commit):
- `/api/posture/summary` — still fast, no compat involvement
- `/api/posture` — still works, uses existing index + mediator
- SSE subscription — still works
- CSS and basic UI rendering — still works

### What is degraded:
- **Application startup**: 7-10 seconds instead of <100ms (first request YAML load tax)
- **Step execution**: Every step handler now tries compat first (57s) before falling back to legacy (<1s)
- **Rescan module**: Was <5 seconds, now 60+ seconds (compat analysis + mediator refresh)
- **Plan creation from UI**: Now triggers two 57-second assess calls (frontend + backend) plus 57-second analysis
- **Plan detail modal**: Fires a background assess call on every open (57 seconds blocking)
- **Compat fix button**: 57-second analysis to do a simple string replacement
- **Any user interaction during analysis**: Queued behind the blocked request, application appears frozen

### What is broken:
- **`handle_rescan_module` returns false "clean" results** when compat analysis crashes (remaining_findings=0 because exception was swallowed)
- **`handle_add_future_annotations` applies fixes twice** (double `fix_finding()` calls)
- **`_cached.py` is dead code** — created, committed, never used
- **Hardcoded target_version '3.8'** in the Deep Analyze button — wrong for any module with a different target
- **Mark-done logic divergence** — same logic copy-pasted in executor.py and wizard.py, will inevitably drift

### What the user experiences:
- Type the command to start the app → 7-10 seconds before anything responds
- Open posture modal → works but slower than before
- Click any automation step → application freezes for 60+ seconds
- Click "Deep Analyze" → application freezes for 1-6 minutes depending on module size
- Click "Create Plan" → application freezes for 3+ minutes (two assess calls + one analyze)
- Click any compat fix button → application freezes for 60+ seconds for a millisecond operation
- During any freeze, nothing else responds — badge doesn't update, buttons don't work, page appears dead
