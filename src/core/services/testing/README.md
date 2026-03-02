# Testing Domain

> **3 files · 857 lines · Test framework detection, inventory, execution, and coverage.**
>
> Detects test frameworks (pytest, unittest, Jest, Vitest, Go test, Cargo test),
> inventories test files with function counts, runs tests with
> structured result parsing, coverage analysis, and generates test
> templates and coverage configurations.

---

## How It Works

### Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│ Two files, three operation tiers                                    │
│                                                                      │
│  ops.py  — DETECT tier                                              │
│  ──────  Framework detection, coverage tool detection,              │
│          test file counting, function counting                      │
│                                                                      │
│  run.py  — OBSERVE + FACILITATE tiers                               │
│  ──────  Test inventory, execution, coverage,                       │
│          template generation, config generation                     │
│                                                                      │
│  Split rationale: ops.py is fast (file checks only, feeds the      │
│  DevOps tab card). run.py is expensive (subprocess execution,      │
│  called on user request).                                           │
└────────────────────────────────────────────────────────────────────┘
```

### Testing Status Pipeline

```
testing_status(root)
     │
     ├── Detect test frameworks (6 built-in):
     │     └── For each framework in _FRAMEWORK_MARKERS:
     │           └── _detect_framework(root, name, marker)
     │                 │
     │                 ├── Check config files:
     │                 │     ├── For each cf in marker["config_files"]:
     │                 │     │     ├── (root / cf).is_file()?
     │                 │     │     └── If config_key: search for key in file content
     │                 │     └── Record as detected_by: ["pyproject.toml (pytest section)"]
     │                 │
     │                 ├── Check test directories:
     │                 │     ├── For each dir in marker["dirs"]:
     │                 │     │     └── rglob("*") → match test_pattern against filenames
     │                 │     └── Record first directory with test files as test_dir
     │                 │
     │                 └── Return {name, detected_by, test_dir, stack} (or None)
     │
     ├── Detect coverage tools (4 built-in):
     │     └── For each tool in _COVERAGE_CONFIGS:
     │           └── _detect_coverage_tool(root, name, config)
     │                 ├── Check config files
     │                 ├── Search for config_key in file content
     │                 └── Return {name, config, stack} (or None)
     │
     ├── Count tests:
     │     └── _count_tests(root, frameworks)
     │           │
     │           ├── Walk all source files (.py, .js, .ts, .go, .rs):
     │           │     └── Skip _SKIP_DIRS
     │           │
     │           ├── For each file:
     │           │     ├── Match test_pattern → test file (count functions, classes)
     │           │     └── No match → source file
     │           │
     │           ├── Function counting (per framework):
     │           │     ├── pytest:  def test_\w+
     │           │     ├── jest:    it('...') / test('...')
     │           │     ├── go:      func Test\w+
     │           │     └── rust:    #[test]
     │           │
     │           └── Compute test_ratio: test_files / source_files
     │
     ├── Check missing tools:
     │     └── Map frameworks → tool IDs → check_required_tools()
     │           ├── pytest/unittest → "pytest"
     │           ├── jest → "jest"
     │           ├── vitest → "vitest"
     │           ├── go_test → "go"
     │           └── cargo_test → "cargo"
     │
     └── Return {has_tests, frameworks, coverage_tools,
                  stats, missing_tools}
```

### Test Inventory

```
test_inventory(root)
     │
     ├── Call testing_status(root) → get detected frameworks
     │
     ├── For each framework:
     │     ├── Get marker from _FRAMEWORK_MARKERS
     │     │
     │     ├── Scan directories (marker["dirs"]):
     │     │     └── rglob("*") → match test_pattern
     │     │
     │     ├── For each matching test file:
     │     │     ├── Skip _SKIP_DIRS
     │     │     ├── Deduplicate (across frameworks sharing same files)
     │     │     ├── Read content:
     │     │     │     ├── Count functions via func_pattern.findall()
     │     │     │     ├── Count classes via class_pattern.findall()
     │     │     │     └── Count lines
     │     │     └── Record {path, functions, classes, lines, framework}

     │
     ├── Sort by function count (descending)
     │
     └── Return {files, total_files, total_functions}
```

### Test Execution

```
run_tests(root, *, verbose=False, file_path=None, keyword=None)
     │
     ├── Build pytest command:
     │     ├── Base: python -m pytest -q --tb=short
     │     │
     │     ├── Options:
     │     │     ├── verbose=True → -v
     │     │     ├── file_path → appended as positional arg
     │     │     └── keyword → -k "keyword"
     │     │
     │     └── Note: currently hardcoded to pytest
     │           (Jest, Vitest, Go handled in future)
     │
     ├── Run subprocess (timeout: 120s)
     │     ├── TimeoutExpired → {"ok": False, "error": "Tests timed out..."}
     │     └── FileNotFoundError → {"ok": False, "error": "pytest not found"}
     │
     ├── Parse results:
     │     └── _parse_pytest_output(stdout + stderr, returncode)
     │           │
     │           ├── Regex parse summary line:
     │           │     └── "10 passed, 2 failed, 1 error, 3 skipped in 4.56s"
     │           │     ├── (\d+) passed   → passed count
     │           │     ├── (\d+) failed   → failed count
     │           │     ├── (\d+) error    → error count
     │           │     ├── (\d+) skipped  → skipped count
     │           │     └── in ([\d.]+)s   → duration
     │           │
     │           ├── Extract failure details:
     │           │     ├── Lines starting with "FAILED" → {name, output}
     │           │     └── Lines starting with "ERROR" → {name, output}
     │           │     └── Cap at 20 failures
     │           │
     │           └── Compute: total = passed + failed + errors + skipped
     │
     ├── Audit trail:
     │     └── _audit("🧪 Tests Run", ...)
     │
     └── Return {ok, passed, failed, errors, skipped, total,
                  duration_seconds, output, failures}
```

### Coverage Analysis

```
test_coverage(root)
     │
     ├── Strategy 1: pytest-cov (most common)
     │     ├── Run: python -m pytest --cov src --cov-report=term-missing -q --no-header --tb=no
     │     ├── If returncode ∈ {0, 1} AND "TOTAL" in output:
     │     │     └── _parse_coverage_output(output) → parsed
     │     └── Return {ok: True, tool: "pytest-cov", ...}
     │
     ├── Strategy 2: coverage.py (if .coverage file exists)
     │     ├── Check: (root / ".coverage").is_file()
     │     ├── Run: python -m coverage report
     │     ├── If returncode == 0 AND "TOTAL" in stdout:
     │     │     └── _parse_coverage_output(stdout) → parsed
     │     └── Return {ok: True, tool: "coverage.py", ...}
     │
     ├── Fallback: no coverage data
     │     └── Return {ok: False, tool: None, coverage_percent: None,
     │                  files: [], output: "No coverage data available..."}
     │
     └── Coverage output parsing:
           └── _parse_coverage_output(output)
                 ├── File regex: ^(\S+\.py)\s+(\d+)\s+(\d+)\s+(\d+)%
                 │     └── Extract {name, stmts, miss, cover} per file
                 ├── Total regex: ^TOTAL\s+(\d+)\s+(\d+)\s+(\d+)%
                 │     └── Extract coverage_percent
                 └── Return {coverage_percent, files, output}
```

### Test Template Generation

```
generate_test_template(root, module_name, stack="python")
     │
     ├── Python:
     │     ├── Convert module_name → PascalCase class name
     │     ├── Format _PYTEST_TEMPLATE with placeholders
     │     └── Output path: tests/test_{module_name}.py
     │
     ├── Node/TypeScript:
     │     ├── Format _JEST_TEMPLATE with module_name
     │     └── Output path: tests/{module_name}.test.ts
     │
     ├── Go:
     │     ├── Format _GO_TEST_TEMPLATE with package_name
     │     └── Output path: {module_name}/{module_name}_test.go
     │
     ├── Unknown stack:
     │     └── Return {error: "No test template for stack: X"}
     │
     ├── Wrap in GeneratedFile (overwrite: False)
     ├── Audit trail: _audit("📝 Test Template Generated", ...)
     │
     └── Return {ok, file: {path, content, reason, overwrite}}
```

### Coverage Config Generation

```
generate_coverage_config(root, stack="python")
     │
     ├── Python:
     │     ├── Generate [tool.coverage.run] + [tool.coverage.report]
     │     │     └── Includes source, omit, fail_under, exclude_lines
     │     └── Output path: pyproject.toml (append section)
     │
     ├── Node/TypeScript:
     │     ├── Generate .nycrc.json
     │     │     └── Includes include, exclude, reporter, thresholds
     │     └── Output path: .nycrc.json
     │
     ├── Unknown stack:
     │     └── Return {error: "No coverage config template for stack: X"}
     │
     └── Return {ok, file: {path, content, reason, overwrite: False}}
```

---

## Architecture

```
             Routes (testing/)
             Audit (l2_risk.py)
                     │
                     │ imports
                     │
          ┌──────────▼──────────────────────────────┐
          │  testing/__init__.py                      │
          │  Public API — re-exports 6 functions      │
          │  testing_status · test_inventory           │
          │  test_coverage · run_tests                 │
          │  generate_test_template                    │
          │  generate_coverage_config                  │
          └──────────┬───────────────────────────────┘
                     │
            ┌────────┴────────┐
            │                 │
            ▼                 ▼
         ops.py            run.py
         (detection,        (inventory,
          status,            coverage,
          counting)          execution,
            │                generation)
            │                  │
            ├── audit_helpers  ├── audit_helpers
            └── tool_req       ├── subprocess (pytest, coverage)
                               ├── ops._FRAMEWORK_MARKERS
                               ├── ops._SKIP_DIRS
                               ├── ops.testing_status
                               └── GeneratedFile model

          testing_ops.py — backward-compat shim
          testing_run.py — backward-compat shim
```

### Dependency Rules

| Rule | Detail |
|------|--------|
| `ops.py` re-exports from `run.py` | Backward compat at bottom |
| `run.py` imports from `ops.py` | Shares `_FRAMEWORK_MARKERS`, `_SKIP_DIRS`, `testing_status` |
| Both use `audit_helpers` | `make_auditor("testing")` for activity log |
| No cross-service imports | Self-contained domain |
| `GeneratedFile` import is lazy | Inside template generation functions only |

---

## File Map

```
testing/
├── __init__.py        8 lines   — public API re-exports
├── ops.py           333 lines   — detection, status, counting
├── run.py           516 lines   — inventory, coverage, execution, generation
└── README.md                    — this file
```

---

## Per-File Documentation

### `ops.py` — Testing Detection (333 lines)

**Constants:**

| Constant | Type | Contents |
|----------|------|---------|
| `_SKIP_DIRS` | `frozenset` | 17 directories excluded from scanning |
| `_FRAMEWORK_MARKERS` | `dict[str, dict]` | 6 framework definitions (see registry) |
| `_COVERAGE_CONFIGS` | `dict[str, dict]` | 4 coverage tool definitions |
| `_audit` | `Callable` | `make_auditor("testing")` |

**Private helpers:**

| Function | Parameters | What It Does |
|----------|-----------|-------------|
| `_detect_framework(root, name, marker)` | `Path, str, dict` | Check if framework configured → `{name, detected_by, test_dir, stack}` |
| `_detect_coverage_tool(root, name, config)` | `Path, str, dict` | Check if coverage tool configured → `{name, config, stack}` |
| `_count_tests(root, frameworks)` | `Path, list[dict]` | Count test files, functions, classes, source files |

**Public API:**

| Function | Parameters | Returns |
|----------|-----------|---------|
| `testing_status(root)` | `Path` | `{has_tests, frameworks, coverage_tools, stats, missing_tools}` |

### `run.py` — Testing Execution (516 lines)

**Constants:**

| Constant | Type | Contents |
|----------|------|---------|
| `_PYTEST_TEMPLATE` | `str` | Python test template (22 lines) |
| `_JEST_TEMPLATE` | `str` | Jest test template (13 lines) |
| `_GO_TEST_TEMPLATE` | `str` | Go test template (12 lines) |
| `_audit` | `Callable` | `make_auditor("testing")` |

**Private helpers:**

| Function | Parameters | What It Does |
|----------|-----------|-------------|
| `_parse_pytest_output(output, rc)` | `str, int` | Extract `{passed, failed, errors, skipped, duration, failures}` |
| `_parse_coverage_output(output)` | `str` | Extract `{coverage_percent, files[], output}` |

**Public API:**

| Function | Parameters | Returns |
|----------|-----------|---------|
| `test_inventory(root)` | `Path` | `{files, total_files, total_functions}` |
| `test_coverage(root)` | `Path` | `{ok, tool, coverage_percent, files, output}` |
| `run_tests(root, *, verbose, file_path, keyword)` | `Path, bool, str|None, str|None` | `{ok, passed, failed, ...}` |
| `generate_test_template(root, module, stack)` | `Path, str, str` | `{ok, file: {...}}` |
| `generate_coverage_config(root, stack)` | `Path, str` | `{ok, file: {...}}` |

---

## Key Data Shapes

### testing_status response

```python
{
    "has_tests": True,
    "frameworks": [
        {
            "name": "pytest",
            "detected_by": [
                "pyproject.toml (pytest section)",
                "tests/ directory",
            ],
            "test_dir": "tests",
            "stack": "python",
        },
    ],
    "coverage_tools": [
        {
            "name": "pytest-cov",
            "config": "pyproject.toml",
            "stack": "python",
        },
    ],
    "stats": {
        "test_files": 12,
        "test_functions": 87,
        "test_classes": 5,
        "source_files": 42,
        "test_ratio": 0.29,          # test_files / source_files
        "test_file_paths": [
            "tests/test_auth.py",
            "tests/test_config.py",
            # ... up to 500 paths
        ],
    },
    "missing_tools": [],
}
```

### test_inventory response

```python
{
    "files": [
        {
            "path": "tests/test_auth.py",
            "functions": 15,    # def test_... count
            "classes": 2,       # class Test... count
            "lines": 230,
            "framework": "pytest",
        },
        {
            "path": "tests/test_config.py",
            "functions": 8,
            "classes": 1,
            "lines": 140,
            "framework": "pytest",
        },
    ],
    "total_files": 12,
    "total_functions": 87,          # sum of all functions
}
```

Note: Files are sorted by `functions` count descending — most
substantial test files appear first.

### run_tests response

```python
# All tests pass
{
    "ok": True,
    "passed": 87,
    "failed": 0,
    "errors": 0,
    "skipped": 3,
    "total": 90,
    "duration_seconds": 4.56,
    "output": "87 passed, 3 skipped in 4.56s",
    "failures": [],
}

# Some tests fail
{
    "ok": False,
    "passed": 80,
    "failed": 5,
    "errors": 2,
    "skipped": 3,
    "total": 90,
    "duration_seconds": 8.12,
    "output": "...\nFAILED tests/test_auth.py::test_login - AssertionError\n...",
    "failures": [
        {"name": "tests/test_auth.py::test_login - AssertionError", "output": ""},
        {"name": "tests/test_config.py::test_load - KeyError", "output": ""},
    ],
}

# Error cases
{"ok": False, "error": "Tests timed out after 120 seconds"}
{"ok": False, "error": "pytest not found"}
```

Note: `failures` is capped at 20 entries to prevent oversized responses.

### test_coverage response

```python
# Success
{
    "ok": True,
    "tool": "pytest-cov",
    "coverage_percent": 78.0,
    "files": [
        {"name": "src/core/auth.py", "stmts": 42, "miss": 3, "cover": 93},
        {"name": "src/core/config.py", "stmts": 87, "miss": 12, "cover": 86},
        {"name": "src/ui/web/app.py", "stmts": 150, "miss": 45, "cover": 70},
    ],
    "output": "Name                  Stmts   Miss  Cover\n...\nTOTAL                   279     60    78%",
}

# No coverage data
{
    "ok": False,
    "tool": None,
    "coverage_percent": None,
    "files": [],
    "output": "No coverage data available. Run tests with --cov first.",
}
```

### generate_test_template response

```python
# Python
{
    "ok": True,
    "file": {
        "path": "tests/test_my_module.py",
        "content": "\"\"\"Tests for my-module...\"\"\"\n\nimport pytest\n\nclass TestMyModule:\n...",
        "overwrite": False,
        "reason": "Test template for my-module (python)",
    },
}

# Unknown stack
{"error": "No test template for stack: java"}
```

### generate_coverage_config response

```python
# Python
{
    "ok": True,
    "file": {
        "path": "pyproject.toml",
        "content": "# Coverage configuration...\n[tool.coverage.run]\nsource = [\"src\"]\n...",
        "overwrite": False,
        "reason": "Python coverage configuration (append to pyproject.toml)",
    },
}

# Node
{
    "ok": True,
    "file": {
        "path": ".nycrc.json",
        "content": "{\n  \"all\": true,\n  ...\n}",
        "overwrite": False,
        "reason": "NYC/Istanbul coverage configuration",
    },
}
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| **Routes** | `routes/testing/` | Full API |
| **Audit** | `audit/l2_risk.py` | `testing_status` |
| **Shims** | `testing_ops.py` | Backward-compat re-export of `ops.py` |
| **Shims** | `testing_run.py` | Backward-compat re-export of `run.py` |

---

## Dependency Graph

```
ops.py                              ← detection layer
   │
   ├── audit_helpers.make_auditor   ← activity log (module level)
   ├── tool_requirements            ← check_required_tools (inside testing_status)
   └── run.py (re-export)           ← backward compat at bottom

run.py                              ← execution layer
   │
   ├── ops._FRAMEWORK_MARKERS      ← framework registry (module level)
   ├── ops._SKIP_DIRS              ← skip directories (module level)
   ├── ops.testing_status           ← detection results (module level)
   ├── audit_helpers.make_auditor   ← activity log (module level)
   ├── subprocess (pytest, coverage) ← test execution
   └── models.template.GeneratedFile ← output model (lazy, inside functions)
```

Key: `run.py` imports from `ops.py` at module level (not lazy)
because it needs the framework registry for inventory scanning.
`GeneratedFile` is imported lazily inside template functions.

---

## Test Framework Registry

### Framework Entry Shape

Each entry in `_FRAMEWORK_MARKERS` follows this schema:

```python
{
    "config_files": list[str],        # Config files to check
    "config_key": str,                # Key to search in config file (optional)
    "test_pattern": re.Pattern,       # Regex matching test filenames
    "function_pattern": re.Pattern,   # Regex extracting test function names
    "class_pattern": re.Pattern,      # Regex extracting test class names (optional)
    "dirs": list[str],                # Directories to scan for test files
    "stack": str,                     # Stack association
}
```

### Framework Matrix

| Framework | Config Files | Config Key | Test Pattern | Function Pattern | Class Pattern | Stack |
|-----------|-------------|-----------|-------------|-----------------|--------------|-------|
| **pytest** | `pyproject.toml`, `pytest.ini`, `setup.cfg`, `tox.ini` | `pytest` | `test_*.py`, `*_test.py` | `def test_\w+` | `class Test\w+` | python |
| **unittest** | *(none)* | — | `test_*.py` | `def test_\w+` | `class Test\w+` | python |
| **jest** | `jest.config.js`, `jest.config.ts`, `jest.config.mjs` | `jest` | `*.{test,spec}.{js,ts,jsx,tsx}` | `it\|test('...')` | — | node |
| **vitest** | `vitest.config.ts`, `vitest.config.js`, `vite.config.ts` | `vitest` | `*.{test,spec}.{js,ts,jsx,tsx}` | `it\|test('...')` | — | node |
| **go_test** | `go.mod` | — | `*_test.go` | `func Test\w+` | — | go |
| **cargo_test** | `Cargo.toml` | — | `*.rs` | `#[test]` | — | rust |

---

## Coverage Tool Registry

| Tool | Config Files | Config Key | Command | Stack |
|------|-------------|-----------|---------|-------|
| **coverage.py** | `.coveragerc`, `pyproject.toml`, `setup.cfg` | `coverage` | `python -m coverage report` | python |
| **pytest-cov** | `pyproject.toml`, `pytest.ini` | `pytest` | `python -m pytest --cov --cov-report=term-missing -q` | python |
| **istanbul/nyc** | `.nycrc`, `.nycrc.json`, `.nycrc.yml` | `nyc` | `npx nyc report` | node |
| **c8** | `vitest.config.ts` | `c8` | `npx c8 report` | node |

### Coverage Execution Strategy

The `test_coverage` function uses a waterfall strategy:

```
1. Try pytest-cov (most common)
   └── Success if returncode ∈ {0, 1} AND "TOTAL" in output
   └── Note: returncode=1 means tests failed but coverage ran

2. Try coverage.py report (if .coverage file exists)
   └── Requires prior `coverage run` execution
   └── Success if returncode == 0 AND "TOTAL" in output

3. Fallback
   └── Return {ok: False, output: "No coverage data available..."}
```

---

## Coverage Output Parsing

The `_parse_coverage_output` function extracts tabular data:

```
Name                    Stmts   Miss  Cover
-----------------------------------------
src/core/foo.py            42      3    93%
src/core/bar.py            87     12    86%
-----------------------------------------
TOTAL                     129     15    88%
```

**Regex patterns:**

| Pattern | Purpose | Example Match |
|---------|---------|--------------|
| `^(\S+\.py)\s+(\d+)\s+(\d+)\s+(\d+)%` | Per-file data | `src/core/foo.py  42  3  93%` |
| `^TOTAL\s+(\d+)\s+(\d+)\s+(\d+)%` | Grand total | `TOTAL  129  15  88%` |

Each file line is parsed into:

```python
{"name": "src/core/foo.py", "stmts": 42, "miss": 3, "cover": 93}
```

---

## Pytest Result Parsing

The `_parse_pytest_output` function parses the summary line:

```
= 10 passed, 2 failed, 1 error, 3 skipped in 4.56s =
```

A single compound regex with optional groups:

```python
r"(?:(\d+)\s+passed)?"
r"(?:,?\s*(\d+)\s+failed)?"
r"(?:,?\s*(\d+)\s+error)?"
r"(?:,?\s*(\d+)\s+skipped)?"
r"(?:.*?in\s+([\d.]+)s)?"
```

The regex matches partial summary lines (e.g., "10 passed in 1.0s"
with no failed/errors/skipped).

### Failure Extraction

Lines starting with `FAILED` or `ERROR` are extracted:

```
FAILED tests/test_auth.py::test_login - AssertionError
→ {"name": "tests/test_auth.py::test_login - AssertionError", "output": ""}
```

Capped at 20 failures to prevent oversized responses.

---

## Test Ratio Calculation

```
test_ratio = test_files / source_files
```

Source files are counted from the project root, excluding
skip dirs and test files. Extensions counted: `.py`, `.js`,
`.ts`, `.go`, `.rs`.

| Ratio | Interpretation |
|-------|---------------|
| 0.0 | No test files |
| 0.25 | One test file per 4 source files |
| 0.5 | One test file per 2 source files |
| 1.0 | Equal test and source files |
| >1.0 | More test files than source files |

The ratio is rounded to 2 decimal places and reported in
`testing_status().stats.test_ratio`.

---

## Keyword and File Filtering

### Keyword Filtering

```python
run_tests(root, keyword="test_login")
# → pytest -k "test_login"
```

This filters tests by name pattern, running only tests whose
names match the keyword expression. Supports pytest's `-k`
expression syntax (AND, OR, NOT).

### File Path Filtering

```python
run_tests(root, file_path="tests/test_auth.py")
# → pytest tests/test_auth.py
```

When `file_path` is provided, it is appended as a positional
argument to pytest. Only tests in that file are executed.

Both can be combined:

```python
run_tests(root, file_path="tests/test_auth.py", keyword="login")
# → pytest -q --tb=short tests/test_auth.py -k "login"
```

---

## Generated Template Examples

### Python — `tests/test_{module}.py`

```python
"""
Tests for my-module.

Auto-generated by DevOps Control Plane.
"""

from __future__ import annotations

import pytest


class TestMyModule:
    """Test suite for my-module."""

    def test_placeholder(self) -> None:
        """TODO: Replace with real test."""
        assert True

    def test_import(self) -> None:
        """Verify module can be imported."""
        # import my_module  # uncomment and adjust
        pass
```

### Node/TypeScript — `tests/{module}.test.ts`

```javascript
// Tests for my-module
// Auto-generated by DevOps Control Plane

describe('my-module', () => {
  test('placeholder', () => {
    expect(true).toBe(true);
  });

  test('imports correctly', () => {
    // const mod = require('./my-module');
    // expect(mod).toBeDefined();
  });
});
```

### Go — `{module}/{module}_test.go`

```go
package my_module

import "testing"

func TestPlaceholder(t *testing.T) {
    // TODO: Replace with real test
    if false {
        t.Error("placeholder")
    }
}
```

---

## Generated Coverage Config

### Python — `pyproject.toml` (append section)

```toml
[tool.coverage.run]
source = ["src"]
omit = [
    "*/tests/*",
    "*/__pycache__/*",
    "*/conftest.py",
]

[tool.coverage.report]
show_missing = true
fail_under = 80
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "if __name__ == .__main__.",
    "@overload",
]
```

### Node/TypeScript — `.nycrc.json`

```json
{
  "all": true,
  "include": ["src/**/*.{js,ts}"],
  "exclude": ["**/*.test.{js,ts}", "node_modules/**"],
  "reporter": ["text", "lcov"],
  "check-coverage": true,
  "branches": 80,
  "lines": 80,
  "functions": 80,
  "statements": 80
}
```

---

## Skipped Directories

Directories excluded from test file scanning:

```
.git          .venv         venv          node_modules
__pycache__   .mypy_cache   .ruff_cache   .pytest_cache
.tox          dist          build         .eggs
.terraform    .pages        htmlcov       .backup
state
```

---

## Backward Compatibility

Two shim files remain at the services root:

```python
# testing_ops.py
from src.core.services.testing.ops import *  # noqa

# testing_run.py
from src.core.services.testing.run import *  # noqa
```

These shims allow old import paths to continue working
during the migration to the package structure.

---

## Error Handling

| Function | Can Fail? | Error Shape |
|----------|----------|-------------|
| `testing_status` | No | Always returns result dict |
| `test_inventory` | No | Always returns `{files, total_files, total_functions}` |
| `run_tests` | Partially | `{"ok": False, "error": "..."}` for timeout/missing pytest |
| `test_coverage` | Partially | `{ok: False, tool: None}` when no coverage data |
| `generate_test_template` | Unknown stack | `{"error": "No test template for stack: X"}` |
| `generate_coverage_config` | Unknown stack | `{"error": "No coverage config template for stack: X"}` |

---

## Audit Trail

Both `run.py` functions that perform actions emit audit entries:

| Event | Action | Detail |
|-------|--------|--------|
| `🧪 Tests Run` | `executed` | `{file, keyword, verbose, passed, failed, errors}` |
| `📊 Coverage Run` | `executed` | `{tool, coverage}` |
| `📝 Test Template Generated` | `generated` | `{module, stack}` |

These entries appear in the activity log timeline.

---

## Advanced Feature Showcase

### 1. Config-Key-Aware Framework Detection — Smart Config File Parsing

Framework detection doesn't just check if `pyproject.toml` exists — it
searches for the framework-specific key inside the file:

```python
# ops.py — _detect_framework (lines 194-208)

for cfg_file in marker.get("config_files", []):
    path = project_root / cfg_file
    if path.is_file():
        config_key = marker.get("config_key")
        if config_key:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                if config_key in content:
                    detected_by.append(f"{cfg_file} ({config_key} section)")
            except OSError:
                pass
        else:
            detected_by.append(cfg_file)
```

A `pyproject.toml` that contains a `[tool.pytest.ini_options]` section
triggers pytest detection, but one without pytest config does not. This
prevents false positives on multi-purpose files — the same `pyproject.toml`
might configure ruff, mypy, and coverage without mentioning pytest at all.

### 2. Multi-Extension Test Counting — Five Languages in One Walk

Test files are counted across all source extensions in a single walk:

```python
# ops.py — _count_tests (lines 256-318)

# Walk ALL source extensions, then classify per-framework
for ext in (".py", ".js", ".ts", ".go", ".rs"):
    for f in project_root.rglob(f"*{ext}"):
        # Skip excluded directories
        skip = False
        for part in f.relative_to(project_root).parts:
            if part in _SKIP_DIRS:
                skip = True
                break
        if skip:
            continue

        # Test or source? Match against ALL detected frameworks
        is_test = False
        for fw in frameworks:
            marker = _FRAMEWORK_MARKERS.get(fw["name"], {})
            pattern = marker.get("test_pattern")
            if pattern and pattern.match(f.name):
                is_test = True
                break

        if is_test:
            test_files += 1
            # Count functions/classes using framework-specific regex
            content = f.read_text(...)
            test_functions += len(func_pattern.findall(content))
            test_classes += len(class_pattern.findall(content))
        else:
            source_files += 1
```

Each file is classified exactly once — a `.py` file matching `test_*.py`
is counted as a test file with its functions tallied, otherwise it's
counted as a source file. The `break` after the first framework match
prevents double-counting when pytest and unittest share the same pattern.

### 3. Regex-Based Pytest Summary Parsing — Compound Optional Groups

The summary line parser handles all possible pytest output formats:

```python
# run.py — _parse_pytest_output (lines 303-308)

summary_pattern = re.compile(
    r"(?:(\d+)\s+passed)?"
    r"(?:,?\s*(\d+)\s+failed)?"
    r"(?:,?\s*(\d+)\s+error)?"
    r"(?:,?\s*(\d+)\s+skipped)?"
    r"(?:.*?in\s+([\d.]+)s)?"
)
```

Every group is optional (`?`), so the regex matches:
- `"87 passed in 4.56s"` — no failures/errors/skipped
- `"5 failed, 3 error in 2.0s"` — no passed/skipped
- `"10 passed, 2 failed, 1 error, 3 skipped in 4.56s"` — everything

The optional comma-space prefix (`(?:,?\s*...)`) handles the separator
between groups. Group 5 captures the decimal duration. If no match is
found for a group, the count defaults to 0.

### 4. Waterfall Coverage Strategy — Two Tools, One API

Coverage analysis tries two tools in order with graceful fallback:

```python
# run.py — test_coverage (lines 130-191)

# Strategy 1: pytest-cov (runs tests and collects coverage)
result = subprocess.run(
    ["python", "-m", "pytest", "--cov", "src",
     "--cov-report=term-missing", "-q", "--no-header", "--tb=no"],
    cwd=str(project_root), timeout=120,
)
if result.returncode in (0, 1) and "TOTAL" in output:
    parsed = _parse_coverage_output(output)
    return parsed

# Strategy 2: coverage.py report (reads existing .coverage file)
if (project_root / ".coverage").is_file():
    result = subprocess.run(
        ["python", "-m", "coverage", "report"],
        cwd=str(project_root), timeout=30,
    )
    if result.returncode == 0 and "TOTAL" in result.stdout:
        parsed = _parse_coverage_output(result.stdout)
        return parsed

# Strategy 3: Fallback
return {"ok": False, "tool": None, "coverage_percent": None, ...}
```

Key detail: `returncode in (0, 1)` for pytest-cov. Return code 1
means tests failed, but coverage data was still collected. Only if
"TOTAL" is absent (meaning the coverage plugin wasn't loaded) does
the function fall through to strategy 2.

### 5. PascalCase Module Name Derivation — Smart Template Variables

Test templates derive class names from module names:

```python
# run.py — generate_test_template (lines 417-425)

if "python" in stack:
    class_name = "".join(
        w.title() for w in module_name.replace("-", "_").split("_")
    )
    module_import = module_name.replace("-", "_")
    content = _PYTEST_TEMPLATE.format(
        module_name=module_name,
        class_name=class_name,
        module_import=module_import,
    )
    path = f"tests/test_{module_name.replace('-', '_')}.py"
```

Transform chain:
- `"my-module"` → replace `-` → `"my_module"` → split `_` → `["my", "module"]` → title → `["My", "Module"]` → join → `"MyModule"`
- Path: `"tests/test_my_module.py"`
- Import: `my_module` (dashes replaced)

This ensures valid Python identifiers for both class names and import
paths, while preserving the original module name in docstrings.

### 6. Framework-to-Tool Deduplication — Dict-Based Unique Mapping

Detected frameworks are mapped to tool IDs for missing-tool checks:

```python
# ops.py — testing_status (lines 163-177)

_fw_tool_map = {
    "pytest": "pytest",
    "unittest": "pytest",   # pytest runs unittest too
    "jest": "jest",
    "vitest": "vitest",
    "go_test": "go",
    "cargo_test": "cargo",
}
tool_ids = list(dict.fromkeys(
    _fw_tool_map[fw["name"]]
    for fw in frameworks
    if fw["name"] in _fw_tool_map
))
```

`dict.fromkeys()` deduplicates while preserving order. If both pytest
and unittest are detected, the tool list contains `"pytest"` only once.
This prevents `check_required_tools` from reporting the same missing
tool twice.

### 7. Cross-Framework Path Deduplication — Shared File Prevention

When multiple frameworks match the same files, inventory deduplicates:

```python
# run.py — test_inventory (lines 49-74)

seen_paths: set[str] = set()

for fw in frameworks:
    # ... scan directories for test files ...
    for f in dir_path.rglob("*"):
        rel_path = str(f.relative_to(project_root))

        # Deduplicate across frameworks
        if rel_path in seen_paths:
            continue
        seen_paths.add(rel_path)

        # ... count functions, record file ...
```

A file like `tests/test_auth.py` might match both pytest's `test_*.py`
pattern and unittest's `test_*.py` pattern. Without deduplication, it
would appear twice in the inventory. The `seen_paths` set ensures each
file appears exactly once, attributed to the first matching framework.

---

### Feature Coverage Summary

| Feature | Where | Complexity |
|---------|-------|-----------|
| Config-key-aware detection | `ops.py` `_detect_framework` | Content search inside multi-purpose configs |
| Multi-extension test counting | `ops.py` `_count_tests` | 5 extensions × N frameworks in one walk |
| Compound pytest summary parsing | `run.py` `_parse_pytest_output` | 5 optional regex groups |
| Waterfall coverage strategy | `run.py` `test_coverage` | pytest-cov → coverage.py → fallback |
| PascalCase name derivation | `run.py` `generate_test_template` | Replace → split → title → join |
| Framework-to-tool deduplication | `ops.py` `testing_status` | `dict.fromkeys()` order-preserving unique |
| Cross-framework path deduplication | `run.py` `test_inventory` | `seen_paths` set across frameworks |

---

## Design Decisions

### Why detection separate from execution?

`ops.py` runs fast (file existence checks only) and feeds the
DevOps tab card. `run.py` is expensive (subprocess execution)
and called on user request. Splitting them ensures the dashboard
stays responsive without triggering unnecessary test runs every
time the card refreshes.

### Why regex-based function counting?

Parsing ASTs would require language-specific parsers (Python `ast`,
TypeScript compiler, Go parser, Rust `syn`). Regex patterns provide
good-enough accuracy for counting test functions across all 6
frameworks without adding heavy dependencies. The trade-off:
regex can't handle multiline function signatures or conditional
test definitions, but these are rare in practice.

### Why structured result parsing?

Raw test output varies wildly between frameworks. Parsing into
`{passed, failed, errors, skipped, failures[]}` provides a
consistent shape that the UI can render without framework-specific
rendering logic. The UI shows pass/fail counts, duration, and
a clickable failure list — all from one normalized dict.

### Why test template generation?

New modules often lack tests. Generating a starter template
with imports and test function stubs reduces the friction of
writing the first test. The template is stack-aware and uses
the correct test conventions (pytest classes, Jest describe/it,
Go Test functions).

### Why waterfall coverage strategy?

pytest-cov is tried first because it's the most common Python
coverage tool and can generate coverage data on the fly. If that
fails, the function falls back to coverage.py's `report` command
which reads a pre-existing `.coverage` file. This ensures the
function works whether the user ran `pytest --cov` or `coverage run`
previously.

### Why cap failures at 20?

A test run with hundreds of failures would produce an enormous
response that bloats the API and overwhelms the UI. Capping at
20 ensures the response stays manageable while still showing
enough failures to identify the pattern.

### Why hardcoded pytest in run_tests?

The `run_tests` function currently only supports pytest execution.
Jest, Vitest, and Go test are detected by `testing_status` but
not yet executable through `run_tests`. This is a known limitation —
pytest covers the primary use case (this project is Python), and
multi-framework execution is tracked for future work.
