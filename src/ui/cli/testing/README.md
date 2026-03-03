# CLI Domain: Testing — Frameworks, Coverage, Inventory & Generation

> **4 files · 345 lines · 6 commands + 1 subgroup · Group: `controlplane testing`**
>
> Test lifecycle management: detect test frameworks and coverage tools,
> inventory test files with per-file function counts, run tests with
> structured result output (pass/fail/skip/duration), analyze code
> coverage with per-file breakdown, and generate test templates and
> coverage configuration per stack.
>
> Core service: `core/services/testing/ops.py` (re-exported via
> `testing_ops.py`)

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                       controlplane testing                          │
│                                                                      │
│  ┌── Detect ──┐  ┌── Observe ──────────────┐  ┌── Generate ──────┐ │
│  │ status     │  │ inventory               │  │ generate         │ │
│  └────────────┘  │ run [-k KEY] [--file]   │  │  template MODULE │ │
│                   │ coverage                │  │  coverage-config │ │
│                   └─────────────────────────┘  └──────────────────┘ │
└──────────┬──────────────────────┬──────────────────┬──────────────┘
           │                      │                  │
           ▼                      ▼                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  core/services/testing/ops.py (via testing_ops.py)  │
│                                                                      │
│  testing_status(root)              → frameworks[], coverage_tools[] │
│                                       stats{files, functions, ratio}│
│  test_inventory(root)              → files[], total_files, total_fn │
│  run_tests(root, verbose, file, kw)→ ok, passed, failed, errors,   │
│                                       skipped, duration, failures[] │
│  test_coverage(root)               → ok, coverage_percent, files[] │
│  generate_test_template(root, mod, stack) → file data              │
│  generate_coverage_config(root, stack)    → file data              │
└──────────────────────────────────────────────────────────────────────┘
```

### Framework Detection

The `status` command detects test frameworks by examining project
configuration and file structure:

```
testing_status(root)
├── Detect frameworks:
│   ├── pytest: pyproject.toml [tool.pytest] or conftest.py
│   ├── jest: package.json scripts.test or jest.config.*
│   ├── go test: *_test.go files
│   └── (other frameworks per stack)
├── Detect coverage tools:
│   ├── coverage/pytest-cov: pyproject.toml [tool.coverage]
│   ├── istanbul/c8: package.json, nyc config
│   └── (per stack)
├── Compute stats:
│   ├── Count test files, test functions, test classes
│   ├── Count source files
│   └── Compute test/source ratio
└── Return: frameworks[], coverage_tools[], stats{}
```

### Test/Source Ratio

The test ratio is a key health metric displayed with color coding:

| Ratio | Color | Meaning |
|-------|-------|---------|
| ≥ 30% | green | Good test coverage |
| ≥ 10% | yellow | Needs improvement |
| < 10% | red | Critically under-tested |

### Test Running

The `run` command wraps the framework's test runner with structured
output. It supports three filtering modes:

```
run                           → run all tests
run --file tests/test_x.py    → run one test file
run -k "test_login"           → run tests matching keyword
```

### Coverage Analysis

Coverage shows both the aggregate percentage and a per-file breakdown
sorted by lowest coverage first:

```
coverage_percent = 75%
files (sorted ascending by cover):
├── src/utils.py              → 42% (12 uncovered)
├── src/core/engine.py        → 58% (8 uncovered)
├── src/api/routes.py         → 89% (3 uncovered)
└── src/main.py               → 95% (1 uncovered)
```

Color thresholds: ≥80% green, ≥60% yellow, <60% red.

---

## Commands

### `controlplane testing status`

Show detected test frameworks, coverage tools, and statistics.

```bash
controlplane testing status
controlplane testing status --json
```

**Output example:**

```
🧪 Testing Status:

   Frameworks:
      ✅ pytest (python)
         Detected by: pyproject.toml, conftest.py
         Test dir: tests/

   Coverage tools:
      ✅ coverage (config: pyproject.toml)

   Statistics:
      Test files:     24
      Test functions: 187
      Test classes:   12
      Source files:   89
      Test/source:    27%
```

**No tests detected:**

```
❌ No tests detected!
   Generate test templates: controlplane testing generate template <module>
```

---

### `controlplane testing inventory`

List all test files with function counts, line counts, and framework.

```bash
controlplane testing inventory
controlplane testing inventory --json
```

**Output example:**

```
📋 Test Inventory (24 files, 187 functions):

   🧪 tests/test_config.py                     12 tests   240 lines  [pytest]
   🧪 tests/test_engine.py                     28 tests   560 lines  [pytest]
   🧪 tests/test_utils.py                       8 tests   120 lines  [pytest]
   📄 tests/conftest.py                          0 tests    45 lines  [pytest]
```

**Icons:** `🧪` for files with tests, `📄` for files with 0 tests
(fixtures, conftest, helpers).

---

### `controlplane testing run`

Run tests with structured result output.

```bash
controlplane testing run
controlplane testing run --file tests/test_config.py
controlplane testing run -k "test_login"
controlplane testing run -v
controlplane testing run --json
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--file` | string | (none) | Run specific test file |
| `-k` | string | (none) | Run tests matching keyword |
| `-v` | flag | off | Verbose output |
| `--json` | flag | off | JSON output |

**Output example (all pass):**

```
🧪 Running tests...
✅ 187 passed in 4.2s
```

**Output example (failures):**

```
🧪 Running tests...
❌ 3 failed, 1 error(s), 183 passed in 5.8s
   Skipped: 2

   Failures:
      ❌ test_login_invalid_password
      ❌ test_session_timeout
      ❌ test_rate_limit

```

**Failure display cap:** Shows at most 10 individual failures.

---

### `controlplane testing coverage`

Run tests with coverage and show per-file report.

```bash
controlplane testing coverage
controlplane testing coverage --json
```

**Output example:**

```
📊 Running coverage...
📊 Coverage: 75% (tool: coverage)

   Lowest coverage:
      src/utils.py                                  42% (12 uncovered)
      src/core/engine.py                            58% (8 uncovered)
      src/api/routes.py                             89% (3 uncovered)
      src/main.py                                   95% (1 uncovered)
```

**Per-file display cap:** Shows at most 10 files (sorted by lowest
coverage first).

---

### `controlplane testing generate template MODULE`

Generate a test template for a specific module.

```bash
controlplane testing generate template auth
controlplane testing generate template auth --stack python --write
controlplane testing generate template api --stack node --write
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `MODULE` | argument | (required) | Module name to generate tests for |
| `--stack` | string | python | Stack (python, node, go) |
| `--write` | flag | off | Write to disk |

---

### `controlplane testing generate coverage-config`

Generate coverage configuration.

```bash
controlplane testing generate coverage-config
controlplane testing generate coverage-config --stack python --write
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--stack` | string | python | Stack (python, node) |
| `--write` | flag | off | Write to disk |

---

## File Map

```
cli/testing/
├── __init__.py     35 lines — group definition, _resolve_project_root,
│                              sub-module imports (detect, observe, generate)
├── detect.py       64 lines — status command (framework + coverage detection)
├── observe.py     168 lines — inventory, run, coverage commands
├── generate.py     78 lines — generate subgroup (template, coverage-config)
└── README.md               — this file
```

**Total: 345 lines of Python across 4 files.**

---

## Per-File Documentation

### `__init__.py` — Group definition (35 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `_resolve_project_root(ctx)` | helper | Reads `config_path` from context, falls back to `find_project_file()` |
| `testing()` | Click group | Top-level `testing` group |
| `from . import detect, observe, generate` | import | Registers sub-modules |

---

### `detect.py` — Framework detection (64 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `status(ctx, as_json)` | command | Detect frameworks, coverage tools, compute test stats |

**Core service import (lazy):**

| Import | From | Used For |
|--------|------|----------|
| `testing_status` | `testing_ops` | Framework and tool detection |

**Framework display:** Each framework shows name, stack, detection
method, and test directory. Uses `detected_by` list (e.g.,
`pyproject.toml, conftest.py`) to show why the framework was identified.

**Test ratio coloring:** ≥30% green, ≥10% yellow, <10% red. This
uses `stats.test_ratio` which is computed by the core service.

---

### `observe.py` — Inventory, run, coverage (168 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `inventory(ctx, as_json)` | command | List test files with per-file stats |
| `run_tests(ctx, file_path, keyword, verbose, as_json)` | command (`run`) | Execute tests with structured results |
| `coverage(ctx, as_json)` | command | Run coverage analysis with per-file breakdown |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `test_inventory` | `testing_ops` | Test file enumeration |
| `run_tests` | `testing_ops` | Test execution |
| `test_coverage` | `testing_ops` | Coverage analysis |

**Inventory formatting:** Fixed-width columns: `path:<45`, `funcs:>3`,
`lines:>4`, `[framework]`.

**Run result fields:** `ok`, `passed`, `failed`, `errors`, `skipped`,
`duration_seconds`, `failures[]`. On failure, shows individual failure
names capped at 10.

**Coverage sorting:** Files are sorted ascending by coverage percentage
to show the weakest spots first. Shows at most 10 files.

---

### `generate.py` — Test generation (78 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `generate()` | Click group | `testing generate` subgroup |
| `gen_template(ctx, module_name, stack, write)` | command (`generate template`) | Generate test file for a module |
| `gen_coverage(ctx, stack, write)` | command (`generate coverage-config`) | Generate coverage config |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `generate_test_template` | `testing_ops` | Test file generation |
| `generate_coverage_config` | `testing_ops` | Coverage config generation |
| `write_generated_file` | `docker_ops` | Shared file writer |

---

## Dependency Graph

```
__init__.py
├── click                     ← click.group
├── core.config.loader        ← find_project_file (lazy)
└── Imports: detect, observe, generate

detect.py
├── click                     ← click.command
└── core.services.testing_ops ← testing_status (lazy)

observe.py
├── click                     ← click.command
└── core.services.testing_ops ← test_inventory, run_tests,
                                 test_coverage (all lazy)

generate.py
├── click                     ← click.group, click.command
├── core.services.testing_ops ← generate_test_template,
│                                generate_coverage_config (lazy)
└── core.services.docker_ops  ← write_generated_file (lazy)
```

---

## Consumers

### Who registers this CLI group

| Layer | Module | What It Does |
|-------|--------|-------------|
| CLI entry | `src/main.py:461` | `from src.ui.cli.testing import testing` |

### Who also uses the same core service

| Layer | Module | Core Service Used |
|-------|--------|------------------|
| Web routes | `routes/testing/status.py` | `testing.ops` (status, inventory) |
| Web routes | `routes/testing/actions.py` | `testing.ops` (run, coverage) |

---

## Design Decisions

### Why `run` and `coverage` are separate commands

Running tests and analyzing coverage use different tool flags and
produce different output. Combining them would require `--with-coverage`
flags and make the common case (just run tests) slower.

### Why coverage shows lowest-first

The most actionable information is which files need more tests. Showing
the lowest-coverage files first puts the most impactful improvements
at the top.

### Why inventory shows all files including 0-test ones

Files like `conftest.py` and `helpers.py` in test directories are
important context. They show test infrastructure (fixtures, factories)
even though they contain no test functions.

### Why `generate template` takes a module name, not a file path

Users think in terms of modules ("I want tests for auth") not file
paths ("I want tests for src/core/auth.py"). The module name is
resolved to the appropriate file paths by the core service.

### Why both generate commands default to `python` stack

The project itself is Python. For a Python-first tool, defaulting to
Python stack reduces friction for the primary use case.

---

## JSON Output Examples

### `testing status --json`

```json
{
  "has_tests": true,
  "frameworks": [
    {
      "name": "pytest",
      "stack": "python",
      "detected_by": ["pyproject.toml", "conftest.py"],
      "test_dir": "tests"
    }
  ],
  "coverage_tools": [
    {"name": "coverage", "config": "pyproject.toml"}
  ],
  "stats": {
    "test_files": 24,
    "test_functions": 187,
    "test_classes": 12,
    "source_files": 89,
    "test_ratio": 0.27
  }
}
```

### `testing run --json`

```json
{
  "ok": false,
  "passed": 183,
  "failed": 3,
  "errors": 1,
  "skipped": 2,
  "duration_seconds": 5.8,
  "failures": [
    {"name": "test_login_invalid_password"},
    {"name": "test_session_timeout"},
    {"name": "test_rate_limit"}
  ]
}
```

### `testing coverage --json`

```json
{
  "ok": true,
  "coverage_percent": 75.0,
  "tool": "coverage",
  "files": [
    {"name": "src/utils.py", "cover": 42, "miss": 12},
    {"name": "src/core/engine.py", "cover": 58, "miss": 8},
    {"name": "src/api/routes.py", "cover": 89, "miss": 3}
  ]
}
```
