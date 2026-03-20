# 32 — CLI Integration

> **Document**: 32 of 37
> **Milestone**: M10 — Integration & UX
> **Status**: Draft

---

## 1. Overview

The CLI provides command-line access to the compat system. It can either call the API (when the web server is running) or call the engine directly (for standalone use).

---

## 2. Commands

```
controlplane compat <subcommand>

Subcommands:
  analyze       Analyze a module for version compatibility
  assess        Pre-plan assessment (is target achievable?)
  plan          Manage version plans
  fix           Apply fixes
  validate-db   Validate the feature database
  features      Browse/search the feature database
```

### 2.1 controlplane compat analyze

```
$ controlplane compat analyze web --target 3.8 --direction downgrade

Analyzing module 'web' (src/ui/web)...
Target: Python 3.8 (downgrade)
Scanned: 127 files in 0.45s

15 incompatible features found:

  ❌ datetime.UTC (3.11+) — 14 files (13 transitive from core, 1 direct)
     Auto-fixable: replace UTC → timezone.utc

  ❌ enum.StrEnum (3.11+) — 1 file (transitive from core)
     Manual fix required

Code floor: 3.11 (datetime.UTC)
Dependency floor: 3.8 (all deps compatible)
Effective floor: 3.11

Target 3.8 achievable after fixing 15 findings.
Blocked by module 'core' (14 transitive findings).
Recommended: run 'controlplane compat plan core --target 3.8' first.
```

Options:
```
--target VERSION    Target version (required)
--direction DIR     "downgrade" or "upgrade" (default: downgrade)
--transitive        Include transitive analysis (default: true)
--no-transitive     Skip transitive analysis
--format FORMAT     Output format: text (default), json, csv
--output FILE       Write output to file instead of stdout
```

### 2.2 controlplane compat assess

```
$ controlplane compat assess web --target 3.8

Version Change Assessment
Module: web (src/ui/web)
Direction: downgrade 3.11 → 3.8

Achievable: YES (after fixing dependencies)

Code fixes needed: 15 (14 auto, 1 manual)
Dependency changes: 0
Blocking modules: core

Fix order:
  1. core (14 auto-fixes + 1 manual)
  2. web (1 auto-fix)

Estimated effort: ~16 minutes

Create plan? [y/N]
```

### 2.3 controlplane compat plan

```
$ controlplane compat plan create web --target 3.8
Created version plan for 'web' targeting Python 3.8
9 steps generated. Run 'controlplane compat plan show web' to view.

$ controlplane compat plan show web
Version Plan: web → Python 3.8 (downgrade)

  1. ✅ Scan for incompatible features            passed
  2. ✅ Add __future__ annotations (3 files)      passed
  3. ⚠️  Fix incompatible code (15 findings)      needs_attention
  4. ○  Verify fixes                              pending
  5. ○  Check dependencies                        pending
  6. ○  Update config                             pending
  7. ○  Set up test environment                   pending
  8. ○  Run compatibility tests                   pending
  9. ○  Re-scan and confirm                       pending

Progress: 2/9 passed

$ controlplane compat plan run web
Running remaining steps...
[3/9] Fix incompatible code... ⚠️ 15 findings — fix with 'compat fix'
Stopped: step needs attention.

$ controlplane compat plan run web --step 3
Executing step 3: Fix incompatible code...
[same output as individual step execution]

$ controlplane compat plan delete web
Deleted version plan for 'web'.

$ controlplane compat plan rollback web
Rolling back all changes from web's version plan...
Restored 3 files to pre-plan state.
```

### 2.4 controlplane compat fix

```
$ controlplane compat fix web --feature python.stdlib.datetime_utc
Fixing datetime.UTC in module 'web'...
  ✅ src/ui/web/routes/metrics/health.py — fixed, verified

1/1 files fixed and verified.

$ controlplane compat fix core --all
Fixing all auto-fixable findings in module 'core'...
  ✅ src/core/models/action.py — fixed, verified
  ✅ src/core/models/state.py — fixed, verified
  ... 12 more
  ❌ src/core/engine/executor.py — StrEnum fix failed, rolled back

13/14 files fixed. 1 failed (manual fix required).

$ controlplane compat fix core --file src/core/engine/executor.py --feature python.stdlib.strenum
No auto-fix available for StrEnum. Manual instructions:
  Option 1: pip install backports.strenum
    from backports.strenum import StrEnum
  Option 2: Define a base class
    class StrEnum(str, Enum): pass
```

### 2.5 controlplane compat validate-db

```
$ controlplane compat validate-db

Validating feature database...

Python (200 entries):
  ✅ 199 passed
  ❌ 1 failed: python.stdlib.strenum
     test.after still matches detection

JavaScript (250 entries):
  ✅ 250 passed

Go (100 entries):
  ✅ 100 passed

... (all languages)

Total: 1009/1010 passed, 1 failed
```

Options:
```
--language LANG    Validate only one language
--entry ID         Validate a specific entry
--verbose          Show each test case result
```

### 2.6 controlplane compat features

```
$ controlplane compat features --language python --above 3.8

Features above Python 3.8:

  3.9:
    str.removeprefix        builtins    auto-fixable
    str.removesuffix        builtins    auto-fixable
    dict merge (|)          builtins    auto-fixable
    builtin generics        typing      auto-fixable (__future__)

  3.10:
    match/case              syntax      manual
    union type (X | Y)      typing      auto-fixable (__future__)
    parenthesized contexts  syntax      auto-fixable

  3.11:
    datetime.UTC            stdlib      auto-fixable
    tomllib                 stdlib      auto-fixable (backport: tomli)
    StrEnum                 stdlib      auto-fixable (backport)
    except*                 syntax      manual

  3.12:
    type statement          syntax      auto-fixable

Total: 14 features above 3.8 (10 auto-fixable, 4 manual)

$ controlplane compat features search "optional chaining"

  js.es2020.optional_chaining
    Language: JavaScript
    Introduced: ES2020
    Fix: rewrite_expression (auto-fixable)
```

---

## 3. Direct vs API Mode

### 3.1 Direct mode (default)

CLI calls engine directly — no HTTP, no web server needed:

```python
# CLI direct mode
from src.core.services.compat.analysis.engine import DetectionEngine
from src.core.services.compat.database.registry import FeatureRegistry

registry = FeatureRegistry.load()
engine = DetectionEngine(registry, backend_factory)
result = engine.analyze_module(module_dir, language, target)
```

### 3.2 API mode

CLI calls the web API — useful when web server is already running:

```
$ controlplane compat analyze web --target 3.8 --api http://localhost:8000
```

Same output, different data source. API mode is optional.

---

## 4. Output Formats

### 4.1 Text (default)
Human-readable terminal output with colors and icons.

### 4.2 JSON
Machine-readable JSON output for scripting:
```
$ controlplane compat analyze web --target 3.8 --format json
{"ok": true, "findings": [...], "summary": {...}}
```

### 4.3 CSV
For spreadsheet export:
```
$ controlplane compat analyze web --target 3.8 --format csv
feature_id,file,line,severity,fix_available
python.stdlib.datetime_utc,src/core/models/action.py,11,error,true
```

---

## 5. Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success — no issues found or all fixes applied |
| 1 | Issues found (findings exist) |
| 2 | Fix failures (some fixes failed verification) |
| 3 | Validation failures (database entries invalid) |
| 4 | Error (invalid input, module not found, etc.) |

---

## 6. Integration Points

### 6.1 With API (Document 30)
- API mode calls the same endpoints as web UI
- Direct mode uses engine directly

### 6.2 With Engine
- Direct mode instantiates engine components
- Same code paths as API, just no HTTP layer

### 6.3 With CI/CD
- `controlplane compat analyze --format json` for CI scripts
- Exit code 1 can fail a CI pipeline if findings exist
- `controlplane compat validate-db` runs in CI on database changes
