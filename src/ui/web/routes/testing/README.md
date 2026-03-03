# Testing Routes — Test Framework Detection, Execution & Coverage API

> **3 files · 106 lines · 5 endpoints · Blueprint: `testing_bp` · Prefix: `/api`**
>
> Two sub-domains under a single blueprint:
>
> 1. **Status (read-only)** — detect test frameworks, list test files
>    with function counts (2 endpoints, 1 cached)
> 2. **Actions (mutations)** — run tests, run with coverage, generate
>    test templates (3 endpoints)
>
> Backed by `core/services/testing/ops.py` (332 lines).

---

## How It Works

### Testing Status Pipeline (Cached)

```
GET /api/testing/status?bust=1
     │
     ▼
devops_cache.get_cached(root, "testing", lambda: testing_ops.testing_status(root))
     │
     ├── Cache HIT → return cached status
     └── Cache MISS → testing_status(root)
         │
         ├── Scan for test frameworks:
         │   ├── pytest → conftest.py, pytest.ini, [tool.pytest.ini_options]
         │   ├── unittest → test_*.py files with unittest imports
         │   ├── jest → jest.config.js, package.json jest section
         │   ├── mocha → .mocharc.yml, mocha in devDependencies
         │   ├── go test → *_test.go files
         │   └── cargo test → #[cfg(test)] modules
         │
         ├── For each detected framework:
         │   ├── CLI available? (shutil.which)
         │   ├── Config found?
         │   ├── Test file count
         │   └── Test function count (parsed from source)
         │
         └── Return:
             {
                 frameworks: [{id, name, cli_available, config_found,
                               test_files, test_count}],
                 has_tests: true,
                 total_tests: 42
             }
```

### Test Inventory Pipeline

```
GET /api/testing/inventory
     │
     ▼
testing_ops.test_inventory(root)
     │
     ├── Walk source tree for test files:
     │   ├── test_*.py, *_test.py, *_test.go
     │   ├── *.test.js, *.test.ts, *.spec.js, *.spec.ts
     │   └── tests/ directory
     │
     ├── Parse each file for test functions:
     │   ├── Python → def test_*, class Test*
     │   ├── JS/TS → describe(), it(), test()
     │   ├── Go → func Test*(t *testing.T)
     │   └── Rust → #[test] fn
     │
     └── Return:
         {
             files: [{path, framework, functions: ["test_login", "test_logout"]}],
             total_files: 8,
             total_functions: 42
         }
```

### Test Execution Pipeline

```
POST /api/testing/run
     Body: { verbose: true, file: "tests/test_auth.py", keyword: "login" }
     │
     ├── @run_tracked("test", "test:run")
     │
     ▼
testing_ops.run_tests(root, verbose=True, file_path="tests/test_auth.py", keyword="login")
     │
     ├── Auto-detect framework (or use detected from status)
     │
     ├── Build command:
     │   ├── pytest → pytest [-v] [file_path] [-k keyword]
     │   ├── jest → npx jest [--verbose] [file_path] [-t keyword]
     │   ├── go → go test [-v] [-run keyword] ./...
     │   └── cargo → cargo test [keyword] [-- --nocapture]
     │
     ├── Execute with timeout
     │
     └── Return:
         { ok: true, passed: 10, failed: 2, skipped: 1,
           output: "...", return_code: 1 }
```

### Coverage Pipeline

```
POST /api/testing/coverage
     │
     ├── @run_tracked("test", "test:coverage")
     │
     ▼
testing_ops.test_coverage(root)
     │
     ├── Framework-specific coverage:
     │   ├── pytest → pytest --cov --cov-report=json
     │   ├── jest → npx jest --coverage --coverageReporters=json-summary
     │   ├── go → go test -coverprofile=coverage.out ./...
     │   └── cargo → cargo tarpaulin --out json
     │
     └── Return:
         { ok: true, coverage_percent: 78.5, output: "..." }
```

### Test Template Generation Pipeline

```
POST /api/testing/generate/template
     Body: { module: "src.core.services.auth", stack: "python" }
     │
     ├── @run_tracked("generate", "generate:test_template")
     │
     ▼
testing_ops.generate_test_template(root, "src.core.services.auth", stack="python")
     │
     ├── Analyze module:
     │   └── Parse functions and classes in the target module
     │
     ├── Generate test file:
     │   # Python → tests/test_auth.py with pytest fixtures
     │   # JS → __tests__/auth.test.js with describe/it blocks
     │
     └── Return:
         { ok: true, path: "tests/test_auth.py", content: "..." }
```

---

## File Map

```
routes/testing/
├── __init__.py     18 lines — blueprint + 2 sub-module imports
├── status.py       30 lines — 2 read-only endpoints
├── actions.py      58 lines — 3 action endpoints
└── README.md                — this file
```

Core business logic: `core/services/testing/ops.py` (332 lines).

---

## Per-File Documentation

### `__init__.py` — Blueprint Definition (18 lines)

```python
testing_bp = Blueprint("testing", __name__)

from . import status, actions  # register routes
```

### `status.py` — Read-Only Endpoints (30 lines)

| Function | Method | Route | Cached | What It Does |
|----------|--------|-------|--------|-------------|
| `testing_status()` | GET | `/testing/status` | ✅ `"testing"` | Detect test frameworks + stats |
| `testing_inventory()` | GET | `/testing/inventory` | No | List test files + functions |

### `actions.py` — Action Endpoints (58 lines)

| Function | Method | Route | Tracked | What It Does |
|----------|--------|-------|---------|-------------|
| `testing_run()` | POST | `/testing/run` | ✅ `test:run` | Execute tests |
| `testing_coverage()` | POST | `/testing/coverage` | ✅ `test:coverage` | Tests with coverage |
| `testing_generate_template()` | POST | `/testing/generate/template` | ✅ `generate:test_template` | Generate test file |

**Test run supports three filtering options:**

```python
result = testing_ops.run_tests(
    root,
    verbose=data.get("verbose", False),      # detailed output
    file_path=data.get("file"),              # specific file
    keyword=data.get("keyword"),             # filter by name
)
```

**Template generation requires module and optional stack:**

```python
result = testing_ops.generate_test_template(
    root, module,
    stack=data.get("stack", "python"),  # default: python
)
```

---

## Dependency Graph

```
__init__.py
└── Imports: status, actions

status.py
├── testing.ops   ← testing_status, test_inventory (eager)
├── helpers       ← project_root (eager)
└── devops.cache  ← get_cached (lazy, inside handler)

actions.py
├── testing.ops   ← run_tests, test_coverage, generate_test_template (eager)
├── run_tracker   ← @run_tracked (eager)
└── helpers       ← project_root (eager)
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `testing_bp`, registers at `/api` |
| DevOps card | `scripts/devops/_testing.html` | `/testing/status` (cached), `/testing/run` |

---

## Data Shapes

### `GET /api/testing/status` response

```json
{
    "frameworks": [
        {
            "id": "pytest",
            "name": "pytest",
            "cli_available": true,
            "config_found": true,
            "test_files": 8,
            "test_count": 42
        }
    ],
    "has_tests": true,
    "total_tests": 42
}
```

### `GET /api/testing/inventory` response

```json
{
    "files": [
        {
            "path": "tests/test_auth.py",
            "framework": "pytest",
            "functions": ["test_login", "test_logout", "test_token_refresh"]
        },
        {
            "path": "tests/test_config.py",
            "framework": "pytest",
            "functions": ["test_load_yaml", "test_defaults"]
        }
    ],
    "total_files": 2,
    "total_functions": 5
}
```

### `POST /api/testing/run` request + response

```json
// Request:
{ "verbose": true, "file": "tests/test_auth.py", "keyword": "login" }

// Response:
{
    "ok": true,
    "passed": 1,
    "failed": 0,
    "skipped": 0,
    "output": "tests/test_auth.py::test_login PASSED",
    "return_code": 0
}
```

### `POST /api/testing/coverage` response

```json
{
    "ok": true,
    "coverage_percent": 78.5,
    "output": "TOTAL    2345   506    78%"
}
```

### `POST /api/testing/generate/template` request + response

```json
// Request:
{ "module": "src.core.services.auth", "stack": "python" }

// Response:
{
    "ok": true,
    "path": "tests/test_auth.py",
    "content": "import pytest\nfrom src.core.services.auth import ...\n\ndef test_...():\n    ..."
}
```

---

## Advanced Feature Showcase

### 1. Test Filtering Trifecta

`/testing/run` supports three independent filters that combine:

```json
{ "file": "tests/test_auth.py" }           // run one file
{ "keyword": "login" }                      // match test name
{ "file": "tests/test_auth.py", "keyword": "login" }  // both
```

### 2. Module-Aware Template Generation

`/testing/generate/template` introspects the target module
to generate test stubs that match actual function signatures:

```python
# If module has: def authenticate(username, password) -> Token
# Generated test: def test_authenticate(): ...
```

### 3. Multi-Framework Support

The same API works across Python, JavaScript, Go, and Rust
without the frontend needing to know which framework is active.

---

## Design Decisions

### Why inventory is not cached

Test files change frequently during development. Caching the
inventory would hide newly created or deleted test files.

### Why coverage is a separate endpoint from run

Coverage runs are slower (instrumentation overhead) and produce
different output (coverage percentage). Keeping them separate
lets the UI offer a "Run Tests" vs "Run with Coverage" choice
without complicating the parameters.

### Why generate/template requires module name

Auto-generating tests for the entire project would produce
hundreds of stubs. Targeting a specific module keeps the output
focused and useful.

---

## Coverage Summary

| Capability | Endpoint | Method | Tracked | Cached |
|-----------|----------|--------|---------|--------|
| Test status | `/testing/status` | GET | No | ✅ `"testing"` |
| Test inventory | `/testing/inventory` | GET | No | No |
| Run tests | `/testing/run` | POST | ✅ `test:run` | No |
| Run coverage | `/testing/coverage` | POST | ✅ `test:coverage` | No |
| Generate template | `/testing/generate/template` | POST | ✅ `generate:test_template` | No |
