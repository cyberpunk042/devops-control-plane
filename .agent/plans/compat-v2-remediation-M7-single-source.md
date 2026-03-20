# M7 — Single Source of Truth: Unify Feature Patterns

> The same features exist in 3 places: module_intel.py regex patterns, the compat YAML
> database, and test_env.py hardcoded patterns. This milestone unifies them. The compat
> database IS the source of truth. Everything else reads from it.

---

## What Exists Now (broken)

### Three copies of the same data:

**module_intel.py `_RUNTIME_FEATURES`** (13 patterns):
```python
("3.12", "type statement", r"^\s*type\s+\w+\s*[\[=]"),
("3.11", "except* (exception groups)", r"\bexcept\s*\*"),
("3.11", "datetime.UTC", r"\bdatetime\.UTC\b"),         # added in compat commit
("3.11", "enum.StrEnum", r"\bStrEnum\b"),               # added in compat commit
("3.11", "tomllib", r"\btomllib\b"),                     # added in compat commit
("3.10", "match/case", r"^\s*match\s+\w+.*:\s*$"),
("3.9", "str.removeprefix", r"\.removeprefix\("),        # added in compat commit
("3.9", "str.removesuffix", r"\.removesuffix\("),        # added in compat commit
...
```

**compat database** (1000 entries across 157 YAML files):
- `python.stdlib.datetime_utc` — same feature as "datetime.UTC" above
- `python.stdlib.strenum` — same as "enum.StrEnum"
- `python.stdlib.tomllib` — same as "tomllib"
- `python.builtins.str_removeprefix` — same as "str.removeprefix"
- `python.builtins.str_removesuffix` — same as "str.removesuffix"

**test_env.py `_COMPAT_PATTERNS`** (7 patterns):
```python
{"pattern": r"cannot import name 'UTC' from 'datetime'", "feature": "datetime.UTC", ...},
{"pattern": r"cannot import name 'StrEnum' from 'enum'", ...},
{"pattern": r"'str' object has no attribute 'removeprefix'", ...},
...
```

When a feature needs updating, it must be changed in all three places. They will drift.

---

## What M7 Delivers

### 1. compute_code_floor() reads from compat registry

Instead of hardcoded `_RUNTIME_FEATURES` and `_ANNOTATION_FEATURES`, compute_code_floor()
queries the compat registry for its patterns:

```python
def compute_code_floor(project_root, module_path, language):
    if language != "python":
        return None, []

    # Get patterns from compat registry (via mediator)
    patterns = _get_code_floor_patterns()

    # ... rest of scanning logic unchanged (regex-based, fast) ...
```

```python
def _get_code_floor_patterns():
    """Get runtime + annotation feature patterns.

    Reads from compat registry if available, falls back to hardcoded list.
    The compat registry is the source of truth.
    """
    try:
        from src.core.services.mediator import get_mediator
        m = get_mediator()
        reg_data = m.peek("compat.registry")
        if reg_data is not None:
            registry = reg_data["data"]
            return _convert_entries_to_patterns(registry)
    except Exception:
        pass

    # Fallback: hardcoded patterns (for CLI mode or before registry loads)
    return _RUNTIME_FEATURES_FALLBACK, _ANNOTATION_FEATURES_FALLBACK
```

```python
def _convert_entries_to_patterns(registry):
    """Convert compat database entries to regex patterns for compute_code_floor.

    Each entry has detection.primary.ast_type and match criteria.
    Convert the most common ones (Import, ImportFrom, Attribute, Call) to
    equivalent regex patterns.
    """
    runtime = []
    annotation = []

    for entry in registry.by_language("python"):
        # Only entries with severity error/warning (skip info)
        if entry.severity.value not in ("error", "warning"):
            continue

        # Convert AST detection to regex (best effort)
        regex = _entry_to_regex(entry)
        if regex:
            category = "annotation" if entry.category == "typing" else "runtime"
            pattern = (entry.introduced, entry.feature_name, regex)
            if category == "annotation":
                annotation.append(pattern)
            else:
                runtime.append(pattern)

    return runtime, annotation
```

The hardcoded `_RUNTIME_FEATURES` list stays as `_RUNTIME_FEATURES_FALLBACK` for CLI
mode and pre-registry-load fallback. But it is no longer the source of truth. The compat
database is.

### 2. Remove 5 duplicated patterns from module_intel.py

The 5 patterns added in the compat commit are removed from `_RUNTIME_FEATURES`:
- datetime.UTC
- enum.StrEnum
- tomllib
- str.removeprefix
- str.removesuffix

These come from the compat database now. The original 8 patterns (type statement,
except*, match/case, walrus, positional-only, f-strings) stay as the fallback.

### 3. test_env.py reads from compat database

`_detect_compat_failures()` queries the registry instead of hardcoded patterns:

```python
def _detect_compat_failures(output, target):
    """Scan test output for known compat failures using the compat database."""
    try:
        from src.core.services.mediator import get_mediator
        m = get_mediator()
        reg_data = m.peek("compat.registry")
        if reg_data is not None:
            registry = reg_data["data"]
            return _match_test_output(output, registry, target)
    except Exception:
        pass

    # Fallback: hardcoded patterns
    return _detect_compat_failures_legacy(output, target)
```

The `_COMPAT_PATTERNS` list stays as the legacy fallback. Not the source of truth.

---

## Files Changed

| File | Action |
|------|--------|
| `src/core/services/system_posture/bridges/module_intel.py` | Read patterns from registry, remove 5 added patterns, keep originals as fallback |
| `src/core/services/module_upgrade/automation/test_env.py` | Read compat patterns from registry, keep hardcoded as fallback |

---

## Verification

1. compute_code_floor() returns same results when registry is loaded vs fallback
2. Adding a new entry to the YAML database automatically appears in code floor detection
3. No duplicated feature definitions across files
4. CLI mode still works (uses fallback patterns — no mediator)
