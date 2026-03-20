# 11 — Upgrade Direction Spec

> **Document**: 11 of 37
> **Milestone**: M7 — Direction & constraint resolution
> **Status**: Draft

---

## 1. Purpose

Upgrade direction handles moving a module to a NEWER language version. The user wants to modernize their code — use new features, remove old workarounds, adopt new APIs.

This is the opposite of downgrade. In downgrade, you REMOVE new features. In upgrade, you ADD them and REMOVE backports/workarounds that are no longer needed.

---

## 2. What Upgrade Does

### 2.1 Modernization opportunities

When upgrading from Python 3.8 to 3.11, the system identifies:

| Category | Example | Action |
|----------|---------|--------|
| New syntax available | `match/case` | Info — you CAN now use this |
| Backports removable | `import tomli as tomllib` → `import tomllib` | Fix — remove backport, use stdlib |
| Workarounds removable | `s[len(p):] if s.startswith(p) else s` → `s.removeprefix(p)` | Fix — simplify code |
| `__future__` removable | `from __future__ import annotations` | Fix — no longer needed (if target >= 3.10) |
| Deprecated features | `typing.Optional` → `X \| None` | Warning — should modernize |
| Removed features | `collections.MutableMapping` | Error — must change |

### 2.2 Direction field in entries

Every feature database entry has a `direction` field:

```yaml
# Downgrade entry — feature must be REMOVED when going to older version
- id: python.stdlib.datetime_utc
  direction: downgrade
  introduced: "3.11"
  fix:
    strategy: replace_import_and_usages  # Remove UTC, use timezone.utc

# Upgrade entry — backport can be REMOVED when going to newer version
- id: python.stdlib.tomllib_backport
  direction: upgrade
  introduced: "3.11"
  detection:
    primary:
      ast_type: Import
      match:
        names_contains: tomli
    alternatives:
      - ast_type: ImportFrom
        match:
          module: tomli
  fix:
    strategy: replace_import
    transforms:
      - type: replace_import_statement
        find:
          import_pattern: "import tomli as tomllib"
        replace:
          import_statement: "import tomllib"
      - type: replace_import_statement
        find:
          import_pattern: "from tomli import"
        replace:
          import_prefix: "from tomllib import"

# Both directions — feature has fixes for both upgrade and downgrade
- id: python.typing.union_syntax
  direction: both
  introduced: "3.10"
  fix_downgrade:
    strategy: add_future_import  # Add __future__ for older Python
  fix_upgrade:
    strategy: rewrite_expression  # Modernize Optional[X] → X | None
```

---

## 3. Upgrade Analysis

### 3.1 What the engine looks for

When analyzing for upgrade (e.g., 3.8 → 3.11), the engine searches for:

1. **Backport imports** — packages that are backports of stdlib modules
   ```python
   import tomli as tomllib        # → can use stdlib tomllib now
   from backports.strenum import StrEnum  # → can use enum.StrEnum now
   ```

2. **Compatibility workarounds** — verbose code that has a simpler modern form
   ```python
   # Workaround for no removeprefix
   s[len(p):] if s.startswith(p) else s  # → s.removeprefix(p)
   ```

3. **try/except backport patterns**
   ```python
   try:
       import tomllib
   except ModuleNotFoundError:
       import tomli as tomllib    # → just import tomllib
   ```

4. **`__future__` imports** — no longer needed when target is high enough
   ```python
   from __future__ import annotations  # → removable if target >= 3.10
   ```

5. **Deprecated APIs** — still work but should be updated
   ```python
   from typing import Optional     # → X | None
   from typing import Union        # → X | Y
   from typing import List, Dict   # → list, dict
   ```

6. **Removed APIs** — will break on new version
   ```python
   from collections import MutableMapping  # → from collections.abc
   ```

### 3.2 Severity levels for upgrade

| Category | Severity | Meaning |
|----------|----------|---------|
| Removed APIs | `error` | Code WILL break on new version |
| Deprecated APIs | `warning` | Code works but should be modernized |
| Backport removable | `info` | Can simplify, not required |
| Workaround removable | `info` | Can simplify, not required |
| `__future__` removable | `info` | Can remove, not required |
| New syntax available | `info` | Informational only |

### 3.3 Analysis result for upgrade

```
Module: core
Direction: upgrade (3.8 → 3.11)

Errors (must fix — code will break):
  (none for this example)

Warnings (should fix — deprecated):
  ⚠️ 23× typing.Optional → X | None
  ⚠️ 15× typing.List/Dict → list/dict

Info (can fix — simplification):
  ℹ️ 2× tomli backport → stdlib tomllib
  ℹ️ 1× try/except tomli → import tomllib
  ℹ️ 45× __future__ annotations → removable
  ℹ️ 3× removeprefix workaround → str.removeprefix()
```

---

## 4. Upgrade Fix Strategies

### 4.1 Remove backport import

```yaml
strategy: replace_import
transforms:
  - type: replace_import_statement
    find:
      import_pattern: "import tomli as tomllib"
    replace:
      import_statement: "import tomllib"
```

Also: update `requirements.txt` / `pyproject.toml` to remove the backport dependency.

### 4.2 Remove try/except backport

```yaml
strategy: simplify_try_except_import
transforms:
  - type: unwrap_try_except
    find:
      try_import: "import tomllib"
      except_import: "import tomli as tomllib"
    replace:
      import_statement: "import tomllib"
```

Before:
```python
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
```

After:
```python
import tomllib
```

### 4.3 Remove `__future__` annotations

```yaml
strategy: remove_import
transforms:
  - type: remove_import_line
    find:
      import_statement: "from __future__ import annotations"
```

Only when target >= 3.10 (when PEP 604 and PEP 585 are natively supported).

### 4.4 Modernize type hints

```yaml
strategy: rewrite_expression
transforms:
  - type: rewrite_annotation
    find:
      annotation_type: Subscript
      annotation_value: Optional
    replace:
      template: "{inner} | None"
      extract:
        inner: subscript_slice
```

Before: `def foo(x: Optional[int]) -> Optional[str]:`
After: `def foo(x: int | None) -> str | None:`

### 4.5 Simplify workarounds

```yaml
strategy: rewrite_expression
transforms:
  - type: rewrite_conditional
    find:
      pattern: "{x}[len({p}):]  if {x}.startswith({p}) else {x}"
    replace:
      template: "{x}.removeprefix({p})"
```

Note: detecting workaround patterns is harder than detecting feature usage. The workaround might be written in many different ways. AST matching needs to be flexible — match the STRUCTURE, not exact formatting.

---

## 5. Upgrade Plan Steps

A typical upgrade plan:

```
Module: core
Direction: upgrade (3.8 → 3.11)

1. Scan for upgrade opportunities                    [analysis]
   → Find backports, workarounds, deprecated APIs

2. Remove backport imports (2 files)                 [transform]
   → tomli → tomllib

3. Simplify try/except backports (1 file)            [transform]
   → Unwrap conditional imports

4. Remove __future__ annotations (45 files)          [transform]
   → Only if target >= 3.10

5. Modernize type hints (38 files)                   [transform]
   → Optional → X | None, List → list, etc.

6. Simplify workarounds (3 files)                    [transform]
   → Verbose patterns → modern API calls

7. Update pyproject.toml requires-python             [config]
   → Change >=3.8 to >=3.11

8. Update CI matrix                                  [config]
   → Remove 3.8, 3.9, 3.10 from test matrix

9. Remove backport dependencies                      [config]
   → Remove tomli, backports.strenum from requirements

10. Run tests                                        [test]
    → Verify everything works on 3.11
```

### 5.1 Step ordering for upgrade

Upgrade steps have a different optimal order than downgrade:

1. **Analysis** first — know what to change
2. **Import changes** — fix imports before fixing usage
3. **Code modernization** — fix expressions, annotations
4. **Config updates** — update version constraints
5. **Dependency cleanup** — remove backport packages
6. **Testing** — verify everything works

---

## 6. Upgrade-Specific Edge Cases

### 6.1 Backport still needed for other targets

If the project supports MULTIPLE Python versions (e.g., 3.8 AND 3.11), removing a backport would break the 3.8 target. The system must check:

```python
def can_remove_backport(
    backport: str,
    current_floors: dict[str, str],  # module → current min version
    target_version: str,
) -> bool:
    """Check if a backport can be safely removed.

    Only remove if ALL modules that use it have a min version
    high enough that the stdlib version is available.
    """
```

### 6.2 Conditional imports that should stay conditional

Some try/except import patterns should NOT be simplified even on upgrade — they handle optional dependencies:

```python
try:
    import ujson as json    # Optional fast JSON
except ImportError:
    import json             # Stdlib fallback
```

This is NOT a backport pattern. The system must distinguish:
- Backport try/except (tomli/tomllib) → simplify on upgrade
- Optional dependency try/except (ujson/json) → keep as-is

Detection: check if the except branch imports from stdlib. If both try and except import the same logical module (just different implementations), it's likely a backport pattern.

### 6.3 `__future__` annotations may change runtime behavior

Removing `from __future__ import annotations` can change runtime behavior in code that inspects annotations at runtime:

```python
from __future__ import annotations

def foo(x: int | str) -> None:
    hints = get_type_hints(foo)  # Works with __future__
    # Without __future__ on 3.9, "int | str" is a runtime error
```

The system should:
- Only offer to remove `__future__` when target >= 3.10
- Warn if the file uses `get_type_hints()`, `typing.get_type_hints()`, or `__annotations__`
- Mark as `warning` severity, not `info`

### 6.4 Deprecated but not removed

`typing.Optional` works in Python 3.12. It's deprecated, not removed. The fix is a modernization, not a requirement. Severity should be `info` or `warning`, never `error`.

---

## 7. Upgrade vs Downgrade Feature Entry Differences

| Aspect | Downgrade | Upgrade |
|--------|-----------|---------|
| Detection target | New features TO REMOVE | Old patterns TO MODERNIZE |
| Fix direction | Replace new → old | Replace old → new |
| Severity default | `error` (will crash) | `info` (can simplify) |
| Required? | Yes (code breaks) | No (code still works) |
| Backport handling | ADD backport | REMOVE backport |
| `__future__` | ADD import | REMOVE import |
| Workarounds | ADD workaround | REMOVE workaround |

### 7.1 Bidirectional entries

Some entries have BOTH upgrade and downgrade fixes:

```yaml
- id: python.typing.union_syntax
  direction: both
  introduced: "3.10"

  fix_downgrade:
    strategy: add_future_import
    transforms:
      - type: add_import
        import_statement: "from __future__ import annotations"

  fix_upgrade:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_annotation
        find:
          annotation_type: Subscript
          annotation_value: Union
        replace:
          template: "{a} | {b}"
```

The engine selects the appropriate fix based on the plan's direction.

---

## 8. Multi-Language Upgrade Patterns

### 8.1 JavaScript/TypeScript

Upgrading from ES2018 to ES2022:
- Remove polyfills for `Array.prototype.flat`, `Object.fromEntries`
- Remove `@babel/plugin-proposal-optional-chaining` (now native)
- Simplify `.then()` chains → `await` (top-level await in ES2022)
- Remove `Array.prototype.at` polyfill

### 8.2 Go

Upgrading from Go 1.18 to 1.21:
- Replace manual `sort.Slice` → `slices.Sort`
- Replace manual `min`/`max` functions → builtin `min`/`max`
- Replace `sync.Map` patterns → `sync.Map` with generics
- Add `log/slog` for structured logging

### 8.3 Rust

Upgrading Rust edition 2018 → 2021:
- `dyn Trait` already required (from 2018)
- Closure capture changes (2021 captures individual fields)
- `IntoIterator` for arrays (2021)
- Remove manual `IntoIterator` impls for arrays

### 8.4 Java

Upgrading from Java 11 to 17:
- Remove Lombok `@Value` → `record`
- Replace `instanceof` + cast → pattern matching `instanceof`
- Replace `switch` statement → `switch` expression
- Use text blocks for multi-line strings
- Use sealed classes where appropriate

### 8.5 Ruby

Upgrading from Ruby 2.7 to 3.2:
- Use pattern matching (`case/in`)
- Use `Data` class (3.2)
- Replace `Struct` with `Data` where appropriate
- Use shorthand hash syntax (`{x:}`)

### 8.6 C#

Upgrading from C# 8 to 12:
- Replace class boilerplate → `record`
- Use `global using` directives
- Use file-scoped namespaces
- Use primary constructors
- Use collection expressions

### 8.7 PHP

Upgrading from PHP 7.4 to 8.2:
- Use union types
- Use named arguments
- Replace `switch` → `match`
- Use enums
- Use readonly properties/classes
- Use fibers for async

### 8.8 Elixir

Upgrading from Elixir 1.11 to 1.15:
- Use stepped ranges (`1..10//2`)
- Use `then/1` in pipes
- Use `dbg/1` for debugging
- Use `Duration` module

---

## 9. Integration Points

### 9.1 With Feature Database (Document 02)
- Entries have `direction: upgrade` or `direction: both`
- Upgrade-specific fix fields: `fix_upgrade`
- Backport registry entries (Document 17)

### 9.2 With Detection Engine (Document 03)
- Engine queries `registry.by_direction(language, "upgrade")`
- Matches backport patterns, workarounds, deprecated APIs

### 9.3 With Downgrade Direction (Document 12)
- Inverse relationship — what downgrade adds, upgrade removes
- Bidirectional entries share the same detection, different fixes

### 9.4 With Dependency Analysis (Document 14)
- Upgrade may allow removing backport packages from dependency list
- Must verify no other module still needs the backport
