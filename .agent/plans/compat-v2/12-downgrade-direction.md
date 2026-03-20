# 12 — Downgrade Direction Spec

> **Document**: 12 of 37
> **Milestone**: M7 — Direction & constraint resolution
> **Status**: Draft

---

## 1. Purpose

Downgrade direction handles moving a module to an OLDER language version. The user needs their code to run on an older runtime — wider compatibility, older production environments, legacy system support.

This is the direction that exposed all of v1's bugs. `datetime.UTC` is a 3.11 feature. Downgrading to 3.8 means removing it. V1 failed to detect it, failed to fix it, and auto-marked the step as done.

---

## 2. What Downgrade Does

### 2.1 Incompatibility categories

When downgrading from Python 3.11 to 3.8, the system identifies:

| Category | Example | Action |
|----------|---------|--------|
| Runtime features | `from datetime import UTC` | Error — crashes on 3.8. Must replace. |
| Syntax features | `match x: case 1:` | Error — syntax error on 3.8. Must rewrite. |
| Annotation features | `def foo(x: int \| str)` | Fixable — add `__future__` import |
| Builtin methods | `s.removeprefix("x")` | Error — AttributeError on 3.8. Must rewrite. |
| Stdlib modules | `import tomllib` | Error — ModuleNotFoundError on 3.8. Must use backport. |
| Type hint syntax | `list[int]`, `dict[str, Any]` | Fixable — add `__future__` or use `typing.List` |

### 2.2 Severity — everything is error

Unlike upgrade (where most findings are `info`), downgrade findings are almost always `error`:

| Category | Severity | Why |
|----------|----------|-----|
| Runtime features | `error` | ImportError / AttributeError at runtime |
| Syntax features | `error` | SyntaxError — file won't parse |
| Stdlib modules | `error` | ModuleNotFoundError at import time |
| Builtin methods | `error` | AttributeError at runtime |
| Annotation features | `warning` | Fixable with `__future__`, not a crash |
| Type hint in comment | `info` | Not executed, just documentation |

---

## 3. Downgrade Analysis

### 3.1 What the engine looks for

When analyzing for downgrade (e.g., 3.11 → 3.8), the engine queries:

```python
entries = registry.above_version("python", "3.8")
# Returns all entries with introduced > 3.8:
#   3.9: removeprefix, removesuffix, dict |, type hint generics
#   3.10: match/case, union type X | Y, parenthesized context managers
#   3.11: datetime.UTC, StrEnum, tomllib, except*, ExceptionGroup
#   3.12: type statement, override decorator
#   3.13: ...
```

For each entry, the detection engine scans the module's AST for matches.

### 3.2 Annotation vs Runtime distinction

This is critical for Python and must be handled precisely:

**Annotation context** — type hints that are NOT evaluated at runtime:
```python
from __future__ import annotations

def foo(x: int | str) -> list[int]:  # Annotation-only — not evaluated
    pass
```
With `__future__` annotations, these are strings at runtime. No crash on 3.8.

**Runtime context** — code that IS evaluated:
```python
isinstance(x, int | str)        # Runtime — crashes on 3.8
list[int]()                     # Runtime — crashes on 3.8
print(int | str)                # Runtime — crashes on 3.8
```

The detection engine must distinguish these contexts:
1. Parse the file's AST
2. Check if `from __future__ import annotations` is present
3. If yes: annotation-only usages are NOT errors (skip or mark as `info`)
4. Runtime usages are ALWAYS errors regardless of `__future__`

### 3.3 Transitive analysis

Same as document 04 — follow import chains to find incompatibilities in dependencies:

```
src/ui/web/routes/backup/archive.py
  → imports src.core.models.action
    → src.core.models.action has "from datetime import UTC" (3.11+)
    → Finding: transitive, source_module=core, imported_by=archive.py
```

---

## 4. Downgrade Fix Strategies

### 4.1 Replace import with backport

```yaml
# tomllib → tomli
fix:
  strategy: add_backport_import
  transforms:
    - type: replace_import
      find:
        import_module: tomllib
      replace:
        import_statement: "import tomli as tomllib"
  backport:
    package: tomli
    min_version: "1.0.0"
```

### 4.2 Replace import and all usages

```yaml
# from datetime import UTC → from datetime import timezone + timezone.utc
fix:
  strategy: replace_import_and_usages
  transforms:
    - type: replace_import_name
      find:
        import_module: datetime
        import_name: UTC
      replace:
        import_name: timezone
    - type: replace_usage
      find:
        name: UTC
        origin: import
      replace:
        expression: "timezone.utc"
```

### 4.3 Add `__future__` import

```yaml
# For annotation-only features (X | Y in annotations, list[int] in annotations)
fix:
  strategy: add_future_import
  transforms:
    - type: add_import
      import_statement: "from __future__ import annotations"
      position: top
```

Only applicable when ALL usages of the feature in the file are annotation-only. If any usage is runtime, this fix is insufficient — the runtime usage needs a different fix.

### 4.4 Rewrite expression

```yaml
# s.removeprefix(p) → s[len(p):] if s.startswith(p) else s
fix:
  strategy: rewrite_expression
  transforms:
    - type: rewrite_method_call
      find:
        method: removeprefix
      replace:
        template: "{receiver}[len({arg}):]  if {receiver}.startswith({arg}) else {receiver}"
```

### 4.5 Wrap in try/except (conditional backport)

```yaml
# Support both stdlib and backport
fix:
  strategy: wrap_in_try_except
  transforms:
    - type: conditional_import
      find:
        import_module: tomllib
      replace:
        try_import: "import tomllib"
        except_import: "import tomli as tomllib"
        except_type: ModuleNotFoundError
```

This keeps compatibility with BOTH versions — the code works on 3.11+ (stdlib) and 3.8-3.10 (backport).

### 4.6 Manual rewrite (no auto-fix)

```yaml
# match/case → if/elif
fix:
  strategy: manual
  manual_instructions: |
    match/case statements must be manually rewritten as if/elif chains.

    Before:
      match command:
          case "quit":
              return quit()
          case "hello":
              return greet()
          case _:
              return unknown()

    After:
      if command == "quit":
          return quit()
      elif command == "hello":
          return greet()
      else:
          return unknown()

    Structural pattern matching (destructuring) requires more complex rewriting.
```

---

## 5. Downgrade Plan Steps

A typical downgrade plan:

```
Module: core
Direction: downgrade (3.11 → 3.8)

1. Scan for incompatible features                    [analysis]
   → Find all features above 3.8

2. Add __future__ annotations (N files)              [transform]
   → Fix annotation-only features

3. Fix datetime.UTC (14 files)                       [transform]
   → Replace import + usages

4. Fix tomllib (2 files)                             [transform]
   → Add backport import

5. Fix StrEnum (1 file)                              [manual]
   → Cannot auto-fix — user rewrites

6. Verify fixes                                      [verification]
   → Re-detect, syntax check, import check

7. Check dependency compatibility                    [analysis]
   → Verify all pip packages support 3.8

8. Update pyproject.toml                             [config]
   → Change requires-python

9. Set up test environment (Python 3.8 venv)         [test]

10. Run compatibility tests                          [test]
    → Verify on actual 3.8 runtime

11. Re-scan and confirm                              [analysis]
    → Final verification — 0 findings
```

### 5.1 Step ordering for downgrade

Order matters more in downgrade than upgrade:

1. **`__future__` imports FIRST** — many annotation features become safe after this
2. **Import fixes** — fix imports before fixing usage
3. **Expression rewrites** — depends on imports being correct
4. **Manual fixes** — user handles these
5. **Verification** — after all auto-fixes
6. **Dependency check** — separate from code check
7. **Config updates** — after code is compatible
8. **Testing** — final validation on target runtime

---

## 6. Downgrade-Specific Edge Cases

### 6.1 Feature used in both annotation and runtime context

```python
from __future__ import annotations

def foo(x: int | str) -> None:      # Annotation — safe with __future__
    if isinstance(x, int | str):     # Runtime — NOT safe, crashes on 3.8
        pass
```

The engine must detect that `int | str` is used in BOTH contexts. `__future__` fixes the annotation usage but NOT the runtime usage. The finding should show:
- Annotation usages: fixed by `__future__`
- Runtime usages: need separate fix (`isinstance(x, (int, str))`)

### 6.2 Star imports hiding features

```python
from some_module import *
# Did some_module export datetime.UTC? We don't know.
```

Star imports make it impossible to know exactly what names are available. The engine should:
- Warn about star imports from project modules
- Try to resolve `__all__` from the imported module if possible
- If unresolvable, flag as "potential incompatibility — cannot verify"

### 6.3 Dynamic feature usage

```python
getattr(datetime, "UTC", None)  # Safe — handles missing attribute
```

This is a SAFE pattern — the code already handles the possibility that `UTC` doesn't exist. The engine should NOT flag this. Detection rule should exclude `getattr` patterns.

### 6.4 Conditional version checks already in place

```python
import sys
if sys.version_info >= (3, 11):
    from datetime import UTC
else:
    from datetime import timezone
    UTC = timezone.utc
```

The code already handles both versions. The engine should NOT flag this. Detection rule should exclude code inside `sys.version_info` checks.

### 6.5 Type stubs and .pyi files

`.pyi` files (type stubs) are NOT executed. They should be scanned differently:
- Syntax features (match/case) → still an error (file won't parse)
- Runtime features (datetime.UTC) → NOT an error (file is never imported at runtime)
- Annotation features → NOT an error (stubs are all annotations)

### 6.6 Tests using new features

Test files might intentionally use new features to test compatibility:

```python
# test_compat.py
def test_datetime_utc_available():
    """Verify UTC is available on this Python version."""
    from datetime import UTC  # Intentional — testing the feature
```

The engine should allow excluding test directories or specific files from downgrade analysis. Configurable per plan.

---

## 7. Multi-Language Downgrade Patterns

### 7.1 JavaScript

Downgrading from ES2022 to ES2018:
- Remove optional chaining `?.` → `&&` chains
- Remove nullish coalescing `??` → ternary with null check
- Remove `Array.at()` → bracket access with length calculation
- Remove top-level `await` → wrap in async IIFE
- Remove class private fields `#x` → WeakMap pattern or underscore convention

### 7.2 Go

Downgrading from Go 1.21 to 1.18:
- Remove `slices.Sort` → `sort.Slice`
- Remove builtin `min`/`max` → custom helper functions
- Remove `log/slog` → `log` or third-party logger
- Remove `maps.Keys` → manual loop

### 7.3 Rust

Downgrading from edition 2021 to 2018:
- Adjust closure captures (2021 captures fields, 2018 captures whole struct)
- Remove `IntoIterator` for arrays usage
- Replace `or_patterns` with separate match arms

### 7.4 Java

Downgrading from Java 17 to 11:
- Replace `record` → manual class with fields, constructor, equals, hashCode
- Replace pattern matching `instanceof` → cast after instanceof check
- Replace switch expressions → switch statements
- Replace text blocks → string concatenation
- Replace sealed classes → abstract classes with documented constraints

### 7.5 Ruby

Downgrading from Ruby 3.2 to 2.7:
- Remove pattern matching → if/case chains
- Remove `Data` class → `Struct`
- Remove endless methods → regular method definitions
- Remove shorthand hash → explicit key-value pairs

### 7.6 C#

Downgrading from C# 12 to 8:
- Replace `record` → manual class
- Replace global usings → per-file usings
- Replace file-scoped namespaces → block-scoped
- Replace primary constructors → constructor + fields
- Replace collection expressions → initializer syntax

### 7.7 PHP

Downgrading from PHP 8.2 to 7.4:
- Remove union types → phpdoc annotations
- Remove named arguments → positional arguments
- Remove `match` → `switch`
- Remove enums → class constants or libraries
- Remove readonly → manual enforcement
- Remove fibers → callbacks or libraries

### 7.8 Elixir

Downgrading from Elixir 1.15 to 1.11:
- Remove stepped ranges → `Enum.take_every`
- Remove `then/1` → `case` or anonymous function
- Remove `dbg/1` → `IO.inspect`
- Remove `Duration` → manual time calculations

---

## 8. Integration Points

### 8.1 With Feature Database (Document 02)
- Entries with `direction: downgrade` or `direction: both`
- Downgrade-specific fix: `fix` or `fix_downgrade` field

### 8.2 With Detection Engine (Document 03)
- Engine queries `registry.above_version(language, target)`
- Context-aware matching (annotation vs runtime)

### 8.3 With Upgrade Direction (Document 11)
- Inverse relationship
- Bidirectional entries share detection, different fixes

### 8.4 With Import Resolver (Document 04)
- Transitive incompatibilities are the primary use case
- "Your module is clean but your dependencies aren't"

### 8.5 With Verification (Document 07)
- Re-detection must confirm the feature is truly gone
- Import check should use the TARGET Python version's venv, not the system Python
