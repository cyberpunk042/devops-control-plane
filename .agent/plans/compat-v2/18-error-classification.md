# 18 — Error Classification Taxonomy

> **Document**: 18 of 37
> **Milestone**: M8 — Fix system
> **Status**: Draft

---

## 1. Purpose

Every compatibility failure has a TYPE. The error classification taxonomy provides a structured way to categorize failures so the system can:
- Route to the correct fix strategy
- Show the user meaningful error messages
- Aggregate statistics ("15 import errors, 3 syntax errors")
- Prioritize fixes (runtime crashes before style issues)

---

## 2. Top-Level Categories

```
COMPAT_ERROR
├── IMPORT_ERROR          — Feature causes ImportError / ModuleNotFoundError
├── SYNTAX_ERROR          — Feature causes SyntaxError (file won't parse)
├── RUNTIME_ERROR         — Feature causes error at runtime (AttributeError, TypeError)
├── TYPE_ERROR            — Feature causes type checking failures
├── DEPRECATION_WARNING   — Feature is deprecated, works but will be removed
├── BEHAVIORAL_CHANGE     — Feature changes behavior between versions (silent breakage)
└── DEPENDENCY_ERROR      — External package doesn't support target version
```

### 2.1 IMPORT_ERROR

Feature requires importing a module or name that doesn't exist in the target version.

| Sub-type | Example | Error on target |
|----------|---------|----------------|
| `missing_module` | `import tomllib` on 3.8 | `ModuleNotFoundError: No module named 'tomllib'` |
| `missing_name` | `from datetime import UTC` on 3.8 | `ImportError: cannot import name 'UTC' from 'datetime'` |
| `missing_submodule` | `from collections.abc import Buffer` on 3.11 | `ImportError` |

Fix strategies: `add_backport_import`, `replace_import`, `wrap_in_try_except`

### 2.2 SYNTAX_ERROR

Feature uses syntax that the target version's parser doesn't understand.

| Sub-type | Example | Error on target |
|----------|---------|----------------|
| `match_case` | `match x: case 1:` | `SyntaxError` on < 3.10 |
| `walrus_operator` | `if (n := len(x)):` | `SyntaxError` on < 3.8 |
| `positional_only` | `def f(x, /):` | `SyntaxError` on < 3.8 |
| `except_star` | `except* ValueError:` | `SyntaxError` on < 3.11 |
| `type_statement` | `type Alias = int` | `SyntaxError` on < 3.12 |
| `union_type_runtime` | `int \| str` in runtime context | `TypeError` on < 3.10 |
| `fstring_nested` | `f"{x:{y}}"` nested f-string | `SyntaxError` on < 3.12 |

Fix strategies: `manual` (match/case), `rewrite_expression` (walrus), `add_future_import` (annotations)

### 2.3 RUNTIME_ERROR

Code parses fine but crashes when executed because a feature doesn't exist at runtime.

| Sub-type | Example | Error on target |
|----------|---------|----------------|
| `missing_method` | `s.removeprefix("x")` | `AttributeError: 'str' object has no attribute 'removeprefix'` |
| `missing_builtin` | `min(a, b)` (Go 1.21 builtin on 1.18) | Compile error |
| `missing_attribute` | `datetime.UTC` | `AttributeError` |
| `unsupported_operator` | `dict_a \| dict_b` | `TypeError: unsupported operand type(s) for \|: 'dict' and 'dict'` |

Fix strategies: `rewrite_expression`, `rewrite_method_call`, `replace_attribute`

### 2.4 TYPE_ERROR

Feature causes type checking failures (mypy, pyright, tsc, etc.) but may work at runtime.

| Sub-type | Example | Error |
|----------|---------|-------|
| `type_union_syntax` | `x: int \| str` annotation | mypy error on < 3.10 (without __future__) |
| `builtin_generic` | `x: list[int]` annotation | mypy error on < 3.9 (without __future__) |
| `type_alias` | `type Alias = int` | mypy error on < 3.12 |
| `paramspec` | `P = ParamSpec("P")` | Not available in typing on < 3.10 |

Fix strategies: `add_future_import`, `rewrite_annotation`, `add_backport_import` (typing_extensions)

### 2.5 DEPRECATION_WARNING

Feature is deprecated — works now but will be removed in a future version.

| Sub-type | Example | Warning |
|----------|---------|---------|
| `deprecated_module` | `import imp` (use `importlib`) | `DeprecationWarning` |
| `deprecated_function` | `asyncio.get_event_loop()` without running loop | `DeprecationWarning` in 3.10+ |
| `deprecated_type` | `typing.Optional` (use `X \| None`) | Not a warning, but a convention |

Fix strategies: `replace_import`, `rewrite_expression`, `manual`

### 2.6 BEHAVIORAL_CHANGE

Feature changes behavior between versions WITHOUT raising an error. Most dangerous — silent breakage.

| Sub-type | Example | Behavior change |
|----------|---------|----------------|
| `dict_ordering` | `dict` iteration order | Guaranteed insertion order in 3.7+, random before |
| `string_formatting` | `str.format_map` edge cases | Changed behavior in certain versions |
| `exception_chaining` | `raise X from Y` defaults | Changed in various versions |
| `closure_capture` | Rust 2021 closure capture | 2021 captures fields, 2018 captures whole struct |

Fix strategies: Usually `manual` — behavioral changes need human review.

### 2.7 DEPENDENCY_ERROR

External package doesn't support the target version.

| Sub-type | Example | Error |
|----------|---------|-------|
| `package_requires_higher` | `pydantic 2.x` requires `>=3.8` | Won't install on 3.7 |
| `package_no_compatible_version` | No version of package supports target | No fix — change package or target |
| `transitive_dependency` | Package's dependency requires higher version | Indirect incompatibility |

Fix strategies: Downgrade package, find alternative, raise target version

---

## 3. Classification Decision Tree

```
Is it an import that doesn't exist on target?
  YES → IMPORT_ERROR
  NO ↓

Does the code fail to PARSE on target?
  YES → SYNTAX_ERROR
  NO ↓

Does the code crash at RUNTIME on target?
  YES → RUNTIME_ERROR
  NO ↓

Does the code fail TYPE CHECKING on target?
  YES → TYPE_ERROR
  NO ↓

Is the feature DEPRECATED on the target?
  YES → DEPRECATION_WARNING
  NO ↓

Does the feature BEHAVE DIFFERENTLY on target?
  YES → BEHAVIORAL_CHANGE
  NO ↓

Is it an external package version issue?
  YES → DEPENDENCY_ERROR
  NO ↓

Not a compatibility issue.
```

### 3.1 Automatic classification

The detection engine classifies findings automatically based on the feature database entry:

```yaml
# Entry declares its error category
- id: python.stdlib.datetime_utc
  error_type: import_error
  error_subtype: missing_name
```

The engine doesn't need to guess — the entry tells it.

---

## 4. Severity Mapping

| Error type | Default severity (downgrade) | Default severity (upgrade) |
|-----------|------------------------------|----------------------------|
| IMPORT_ERROR | `error` | `info` (removable backport) |
| SYNTAX_ERROR | `error` | `info` (new syntax available) |
| RUNTIME_ERROR | `error` | `info` (can modernize) |
| TYPE_ERROR | `warning` | `info` |
| DEPRECATION_WARNING | `info` | `warning` |
| BEHAVIORAL_CHANGE | `warning` | `warning` |
| DEPENDENCY_ERROR | `error` | `info` |

### 4.1 Severity overrides

Entries can override the default severity:

```yaml
- id: python.stdlib.datetime_utc
  error_type: import_error
  severity: error               # Default for import_error anyway

- id: python.typing.optional_deprecated
  error_type: deprecation_warning
  severity: info                # Override — Optional still works fine
```

---

## 5. Error Message Templates

Each error type has a human-readable message template:

```python
_ERROR_MESSAGES = {
    "import_error.missing_module": (
        "Module '{feature}' is not available in {language} {target}. "
        "It was introduced in {introduced}."
    ),
    "import_error.missing_name": (
        "Cannot import '{name}' from '{module}' in {language} {target}. "
        "'{name}' was added in {introduced}."
    ),
    "syntax_error.match_case": (
        "match/case syntax requires {language} {introduced}+. "
        "Target {target} does not support this syntax."
    ),
    "runtime_error.missing_method": (
        "'{method}' method is not available on {type} in {language} {target}. "
        "It was added in {introduced}."
    ),
    "dependency_error.package_requires_higher": (
        "Package '{package}' {version} requires {language} {requires}. "
        "Target {target} is below this requirement."
    ),
}
```

### 5.1 Rich error display

The UI renders errors with:
- Error type icon (🔴 error, 🟡 warning, ℹ️ info)
- Human-readable message from template
- Source code line with the issue highlighted
- Fix availability indicator (🔧 auto-fixable, ⚠️ manual)
- Link to documentation/explanation

---

## 6. Statistics and Aggregation

### 6.1 Per-module summary

```python
@dataclass
class ErrorSummary:
    total: int
    by_type: dict[str, int]        # error_type → count
    by_severity: dict[str, int]    # severity → count
    by_fix_status: dict[str, int]  # "auto_fixable", "manual", "no_fix" → count

    def report(self) -> str:
        """Human-readable summary.

        Example:
        15 compatibility issues found:
          🔴 12 errors (10 auto-fixable, 2 manual)
          🟡 2 warnings
          ℹ️ 1 info
        """
```

### 6.2 Per-project summary

Aggregated across all modules:

```
Project Compatibility Summary (target: Python 3.8)
  core:     12 errors, 2 warnings, 0 info
  adapters: 0 errors, 0 warnings, 0 info
  cli:      0 errors, 0 warnings, 0 info
  web:      1 error, 0 warnings, 0 info
  ─────────────────────────────────────
  Total:    13 errors, 2 warnings, 0 info
            11 auto-fixable, 2 manual
```

---

## 7. Integration Points

### 7.1 With Feature Database (Document 02)
- Each entry declares `error_type` and `error_subtype`
- Severity defaults from error type, overridable per entry

### 7.2 With Detection Engine (Document 03)
- Findings carry the error classification
- Classification influences severity and display

### 7.3 With Lifecycle (Document 06)
- Error severity affects step state:
  - `error` findings → NEEDS_ATTENTION
  - `warning` findings → NEEDS_ATTENTION (configurable)
  - `info` findings → PASSED (informational, don't block)

### 7.4 With UI (Documents 30-31)
- Error type determines icon, color, message
- Aggregated statistics shown in plan modal
- Filtering by error type in findings list
