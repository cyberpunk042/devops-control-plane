# 28 — Edge Case Framework Spec

> **Document**: 28 of 37
> **Milestone**: M9 — Language modules & edge cases
> **Status**: Draft

---

## 1. Purpose

Edge cases are patterns that LOOK like a feature usage but should NOT be flagged, or patterns that ARE a feature usage but in a context that changes how they should be handled. V1 had zero edge case handling — every regex match was treated equally.

The edge case framework provides:
- A structured way to document and test edge cases per feature
- Exclusion rules integrated into the detection engine
- Special handling rules for context-dependent findings
- A test suite proving each edge case is handled correctly

Target: **100+ documented, tested edge cases** across all languages.

---

## 2. Edge Case Categories

### 2.1 False Positive Exclusions

Patterns that LOOK like the feature but ARE NOT:

| Category | Example | Why it's false |
|----------|---------|---------------|
| Inside strings | `"datetime.UTC is cool"` | String content, not code |
| Inside comments | `# Use datetime.UTC` | Comment, not code |
| Inside docstrings | `"""Uses datetime.UTC"""` | Documentation, not code |
| Different scope | `UTC = "my constant"` shadows import | Local variable, not the feature |
| Different module | `from my_utils import UTC` | Not `datetime.UTC` |
| Test assertions | `assert hasattr(datetime, "UTC")` | Testing for feature existence |
| Conditional availability | `getattr(datetime, "UTC", None)` | Safely handles missing feature |

**AST-based detection eliminates most string/comment false positives automatically.** The AST doesn't include comments or string literals as executable nodes. But scope confusion and similar-name-different-module still need exclusion rules.

### 2.2 Context-Dependent Findings

Patterns that ARE the feature but need different handling based on context:

| Context | Example | Handling |
|---------|---------|----------|
| `TYPE_CHECKING` block | `if TYPE_CHECKING: from datetime import UTC` | Skip — never executed |
| `try/except ImportError` | `try: from datetime import UTC except ImportError: ...` | Info — already handled |
| `sys.version_info` gate | `if sys.version_info >= (3,11): from datetime import UTC` | Info — already handled |
| Annotation-only (with `__future__`) | `def foo(x: int \| str)` with `__future__` | Safe — deferred evaluation |
| Annotation in runtime context | `isinstance(x, int \| str)` | Error — even with `__future__` |
| Build-tagged file (Go) | `//go:build go1.21` | Skip — won't compile on older |
| `#[cfg]` guarded (Rust) | `#[cfg(feature = "nightly")]` | Skip — conditionally compiled |
| `--enable-preview` (Java) | Preview feature with flag | Warning — not stable |

### 2.3 Transform Edge Cases

Patterns where the fix transform needs special handling:

| Case | Example | Special handling |
|------|---------|-----------------|
| Complex receiver | `get_data().removeprefix("x")` | Introduce temp variable |
| Multiple usages in one line | `f(UTC, UTC)` | Replace both |
| Aliased import | `from datetime import UTC as utc` | Track alias |
| Re-exported name | `from module import UTC; __all__ = ["UTC"]` | Fix re-export too |
| Mixed imports | `from datetime import datetime, UTC, timezone` | Only replace UTC |
| Nested scope | `def f(): UTC = local; return UTC` | Don't replace local var |
| Decorator usage | `@requires_utc` | May reference imported name |
| Default argument | `def f(tz=UTC):` | Replace default value |
| Class attribute | `class Config: tz = UTC` | Replace class-level usage |
| Comprehension scope | `[x for x in UTC]` | Likely wrong but handle |

---

## 3. Edge Case Data Model

### 3.1 Per-feature edge cases

Each feature database entry can have an `edge_cases` list:

```yaml
edge_cases:
  - id: python.datetime_utc.type_checking_block
    category: context_dependent
    description: "UTC imported inside TYPE_CHECKING block"
    handling: exclude      # "exclude" | "downgrade_severity" | "special_transform"
    severity_override: null  # null (excluded) or "info"
    detection_modifier:
      context: type_checking_block
      action: skip
    test:
      input: |
        from typing import TYPE_CHECKING
        if TYPE_CHECKING:
            from datetime import UTC
        def foo(x: 'UTC') -> None: pass
      expected_findings: 0
      expected_fix: null    # No fix needed

  - id: python.datetime_utc.try_except_import
    category: context_dependent
    description: "UTC imported with try/except fallback"
    handling: downgrade_severity
    severity_override: info
    detection_modifier:
      context: try_except_block
      action: downgrade_to_info
    test:
      input: |
        try:
            from datetime import UTC
        except ImportError:
            from datetime import timezone
            UTC = timezone.utc
      expected_findings: 1
      expected_severity: info  # Not error — already handled
      expected_fix: null       # No fix needed — code already handles it

  - id: python.datetime_utc.aliased_import
    category: transform_edge_case
    description: "UTC imported with alias"
    handling: special_transform
    test:
      before: |
        from datetime import UTC as utc_tz
        now = datetime.now(utc_tz)
      after: |
        from datetime import timezone
        now = datetime.now(timezone.utc)
      notes: "Must track alias 'utc_tz' and replace all its usages"

  - id: python.datetime_utc.mixed_import
    category: transform_edge_case
    description: "UTC imported alongside other names"
    handling: special_transform
    test:
      before: |
        from datetime import datetime, UTC, timezone
        now = datetime.now(UTC)
      after: |
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
      notes: "Only remove UTC from names list, keep datetime and timezone"

  - id: python.datetime_utc.version_gate
    category: context_dependent
    description: "UTC inside sys.version_info check"
    handling: exclude
    test:
      input: |
        import sys
        if sys.version_info >= (3, 11):
            from datetime import UTC
        else:
            from datetime import timezone
            UTC = timezone.utc
      expected_findings: 0

  - id: python.datetime_utc.getattr_safe
    category: false_positive
    description: "Safe attribute access via getattr"
    handling: exclude
    test:
      input: |
        import datetime
        utc = getattr(datetime, "UTC", datetime.timezone.utc)
      expected_findings: 0
      notes: "getattr with default handles missing attribute safely"
```

### 3.2 Cross-feature edge cases

Some edge cases span multiple features:

```yaml
cross_feature_edge_cases:
  - id: python.future_annotations_and_runtime
    description: "__future__ annotations makes type hints safe but not runtime usages"
    affects:
      - python.typing.union_pipe
      - python.typing.builtin_generics
    test:
      input: |
        from __future__ import annotations
        def foo(x: int | str) -> list[int]:      # SAFE — annotation
            if isinstance(x, int | str):           # UNSAFE — runtime
                return [x]
            return list[int]()                     # UNSAFE — runtime
      expected_findings: 2  # Only runtime usages
      expected_at_lines: [3, 5]

  - id: python.star_import_unknown_names
    description: "Star imports make name origin unknown"
    affects: all_python_import_features
    test:
      input: |
        from some_module import *
        now = datetime.now(UTC)   # Is UTC from datetime or from some_module?
      expected_findings: 0        # Cannot determine origin — don't flag
      expected_warnings: 1        # Warn about unresolvable star import
```

---

## 4. Edge Case Detection Integration

### 4.1 Exclusion rules in the matcher

The feature matcher applies edge case exclusion rules during matching:

```python
def match_feature(self, tree, rule, edge_cases):
    findings = []
    for node in ast.walk(tree):
        if not self._node_matches(node, rule):
            continue

        # Check exclusion edge cases
        excluded = False
        severity_override = None
        for ec in edge_cases:
            if ec.handling == "exclude":
                if self._matches_context(node, ec.detection_modifier):
                    excluded = True
                    break
            elif ec.handling == "downgrade_severity":
                if self._matches_context(node, ec.detection_modifier):
                    severity_override = ec.severity_override

        if excluded:
            continue

        finding = self._make_finding(node, rule)
        if severity_override:
            finding.severity = severity_override
        findings.append(finding)

    return findings
```

### 4.2 Context detection helpers

```python
def _is_in_type_checking_block(self, node, tree) -> bool:
    """Check if node is inside 'if TYPE_CHECKING:' block."""

def _is_in_try_except(self, node, tree) -> bool:
    """Check if node is inside a try/except block."""

def _is_in_version_gate(self, node, tree) -> bool:
    """Check if node is inside 'if sys.version_info >= ...' block."""

def _is_annotation_context(self, node, tree) -> bool:
    """Check if node is in a type annotation (not runtime)."""

def _is_runtime_context(self, node, tree) -> bool:
    """Check if node is in runtime code (not annotation)."""

def _has_future_annotations(self, tree) -> bool:
    """Check if file has 'from __future__ import annotations'."""

def _is_in_getattr(self, node, tree) -> bool:
    """Check if node is inside a getattr() call with default."""
```

These helpers work by walking UP the AST from the matched node to check parent contexts.

---

## 5. Edge Case Test Suite

### 5.1 Structure

```
tests/
├── edge_cases/
│   ├── python/
│   │   ├── test_type_checking_exclusion.py
│   │   ├── test_try_except_handling.py
│   │   ├── test_version_gate_exclusion.py
│   │   ├── test_future_annotations.py
│   │   ├── test_star_imports.py
│   │   ├── test_aliased_imports.py
│   │   ├── test_complex_receivers.py
│   │   ├── test_scope_tracking.py
│   │   └── test_mixed_imports.py
│   ├── javascript/
│   │   ├── test_transpiler_awareness.py
│   │   ├── test_polyfill_detection.py
│   │   ├── test_esm_vs_commonjs.py
│   │   └── test_tsconfig_target.py
│   ├── go/
│   │   ├── test_build_tags.py
│   │   ├── test_vendored_code.py
│   │   └── test_generated_files.py
│   ├── rust/
│   │   ├── test_cfg_guards.py
│   │   ├── test_feature_gates.py
│   │   └── test_proc_macros.py
│   └── ...
```

### 5.2 Test format

Each test loads a code snippet, runs detection, and asserts the expected findings:

```python
def test_type_checking_exclusion():
    """UTC inside TYPE_CHECKING should not be flagged."""
    code = '''
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from datetime import UTC
'''
    findings = detect(code, "python", target="3.8")
    assert len(findings) == 0

def test_try_except_downgrade():
    """UTC in try/except should be info, not error."""
    code = '''
try:
    from datetime import UTC
except ImportError:
    from datetime import timezone
    UTC = timezone.utc
'''
    findings = detect(code, "python", target="3.8")
    assert len(findings) == 1
    assert findings[0].severity == "info"

def test_aliased_import_fix():
    """Fix should handle aliased UTC import."""
    before = '''
from datetime import UTC as utc_tz
now = datetime.now(utc_tz)
'''
    after = fix(before, "python.stdlib.datetime_utc")
    assert "utc_tz" not in after
    assert "timezone.utc" in after
```

### 5.3 Coverage target

| Language | Edge cases documented | Edge cases tested |
|----------|----------------------|-------------------|
| Python | 40+ | 40+ |
| JavaScript/TypeScript | 20+ | 20+ |
| Go | 10+ | 10+ |
| Rust | 10+ | 10+ |
| Ruby | 5+ | 5+ |
| Java | 5+ | 5+ |
| C# | 5+ | 5+ |
| PHP | 5+ | 5+ |
| Elixir | 3+ | 3+ |
| **Total** | **103+** | **103+** |

---

## 6. Adding New Edge Cases

When a user reports a false positive or a fix failure:

1. Identify the feature entry and the edge case pattern
2. Create an edge case entry in the feature's `edge_cases` list
3. Add a test case proving the edge case is handled
4. Run validation — existing tests must still pass
5. Submit PR — CI validates

This is the feedback loop that makes the system improve over time. Every bug report becomes a documented, tested edge case.

---

## 7. Integration Points

### 7.1 With Feature Database (Document 02)
- Edge cases are FIELDS on feature entries
- Cross-feature edge cases are separate entries

### 7.2 With Detection Engine (Document 03)
- Exclusion rules applied during matching
- Context helpers integrated into the matcher

### 7.3 With Fix Engine (Document 05)
- Transform edge cases define special handling for specific code patterns
- The fix engine checks for edge case transforms before applying the default

### 7.4 With Test Plan (Document 35)
- Edge case test suite is part of the overall test plan
- CI runs all edge case tests on every change
