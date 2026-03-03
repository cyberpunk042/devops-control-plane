# Quality Routes — Code Quality, Lint, Typecheck, Test & Format API

> **3 files · 117 lines · 7 endpoints · Blueprint: `quality_bp` · Prefix: `/api`**
>
> Two sub-domains under a single blueprint:
>
> 1. **Status (read-only)** — detect quality tools relevant to the
>    project's stacks (1 endpoint, cached)
> 2. **Actions (mutations)** — run quality checks, lint, typecheck,
>    test, format, and generate config files (6 endpoints)
>
> Supports 15+ quality tools across 5 stacks:
> Python (ruff, mypy, pytest, black, ruff-format),
> JavaScript/TypeScript (eslint, prettier, tsc, jest),
> Go (golangci-lint, go test), Rust (clippy, cargo test).
>
> Backed by `core/services/quality/ops.py` (531 lines).

---

## How It Works

### Quality Status Pipeline (Cached)

```
GET /api/quality/status?bust=1
     │
     ▼
devops_cache.get_cached(root, "quality", _compute)
     │
     ├── Cache HIT → return cached status
     └── Cache MISS → _compute()
         │
         ├── _get_stack_names()
         │   └── Read detected stacks from wizard/project config
         │       e.g. ["python", "typescript"]
         │
         ├── quality_status(root, stack_names=["python", "typescript"])
         │   │
         │   ├── For each of 15+ _QUALITY_TOOLS:
         │   │   ├── _tool_matches_stack(tool, stack)
         │   │   │   → Is this tool relevant for the project's stacks?
         │   │   ├── shutil.which(cli) → cli_available?
         │   │   ├── Scan for config files → config_found?
         │   │   └── Collect: { id, name, category, cli_available,
         │   │                  config_found, config_file, relevant,
         │   │                  install_hint }
         │   │
         │   ├── Summarize by category:
         │   │   { lint: 2, typecheck: 1, test: 1, format: 2 }
         │   │
         │   └── Return:
         │       { tools: [...], categories: {...}, has_quality: true }
         │
         └── Cached result
```

### Quality Check Pipeline (Generic Runner)

```
POST /api/quality/check  { tool: "ruff", fix: true }
     │
     ├── @run_tracked("validate", "validate:quality")
     │
     ▼
quality_ops.quality_run(root, tool="ruff", fix=True)
     │
     ├── Resolve target tools:
     │   ├── tool="ruff"?  → run only ruff
     │   ├── category="lint"? → run all lint-category tools
     │   └── neither? → run all available tools
     │
     ├── For each resolved tool:
     │   ├── fix=True + fix_args? → run fix_args
     │   │   e.g. ["ruff", "check", "--fix", "."]
     │   └── fix=False → run run_args
     │       e.g. ["ruff", "check", "."]
     │
     │   ├── Capture: return code, stdout, stderr
     │   └── Record: { tool, passed, return_code, stdout, stderr, fixable }
     │
     └── Return:
         { ok: true, results: [{tool, passed, ...}], all_passed: bool }
```

### Category-Specific Shortcuts

```
POST /api/quality/lint       { fix: false }
→ quality_run(root, category="lint", fix=False)
→ Runs: ruff, eslint, golangci-lint, clippy (whichever are available)

POST /api/quality/typecheck
→ quality_run(root, category="typecheck")
→ Runs: mypy, tsc (whichever are available)

POST /api/quality/test
→ quality_run(root, category="test")
→ Runs: pytest, jest, go test, cargo test

POST /api/quality/format     { fix: true }
→ quality_run(root, category="format", fix=True)
→ Runs: black/ruff-format, prettier (auto-fix mode)
```

### Config Generation Pipeline

```
POST /api/quality/generate/config  { stack: "python" }
     │
     ├── @run_tracked("generate", "generate:quality_config")
     │
     ▼
quality_ops.generate_quality_config(root, "python")
     │
     ├── Look up stack → relevant tools
     ├── For each tool:
     │   └── Generate appropriate config file content
     │       e.g. pyproject.toml with [tool.ruff], [tool.mypy], etc.
     │
     └── Return:
         { ok: true, files: [{path, content, reason}] }
```

---

## File Map

```
routes/quality/
├── __init__.py     18 lines — blueprint + 2 sub-module imports
├── status.py       25 lines — 1 cached endpoint
├── actions.py      74 lines — 6 action endpoints
└── README.md                — this file
```

Core business logic: `core/services/quality/ops.py` (531 lines).

---

## Per-File Documentation

### `__init__.py` — Blueprint Definition (18 lines)

```python
quality_bp = Blueprint("quality", __name__)

from . import status, actions  # register routes
```

### `status.py` — Detection Endpoint (25 lines)

| Function | Method | Route | Cached | What It Does |
|----------|--------|-------|--------|-------------|
| `quality_status()` | GET | `/quality/status` | ✅ `"quality"` | Detect available quality tools |

**Stack-aware detection:**

```python
def _compute() -> dict:
    stack_names = _get_stack_names()  # from helpers — reads detected stacks
    return quality_ops.quality_status(root, stack_names=stack_names)
```

The `stack_names` parameter filters tools to only those relevant
for the project (e.g. Python projects won't see eslint results).

### `actions.py` — Quality Action Endpoints (74 lines)

| Function | Method | Route | Tracked | What It Does |
|----------|--------|-------|---------|-------------|
| `quality_check()` | POST | `/quality/check` | ✅ `validate:quality` | Generic runner (tool/category/all) |
| `quality_lint()` | POST | `/quality/lint` | ✅ `validate:lint` | Lint only |
| `quality_typecheck()` | POST | `/quality/typecheck` | ✅ `validate:typecheck` | Type-check only |
| `quality_test()` | POST | `/quality/test` | ✅ `test:quality` | Tests only |
| `quality_format()` | POST | `/quality/format` | ✅ `format:quality` | Format check/fix |
| `quality_generate_config()` | POST | `/quality/generate/config` | ✅ `generate:quality_config` | Generate tool configs |

**The `/quality/check` endpoint is the most flexible — it accepts
both `tool` and `category` parameters, plus a `fix` flag:**

```python
result = quality_ops.quality_run(
    _project_root(),
    tool=data.get("tool"),            # optional: specific tool
    category=data.get("category"),    # optional: lint/typecheck/test/format
    fix=data.get("fix", False),       # optional: auto-fix mode
)
```

**Lint and format support `fix` mode:**

```python
# Check only:
POST /quality/lint   { fix: false }  → ruff check .
POST /quality/format { fix: false }  → black --check .

# Auto-fix:
POST /quality/lint   { fix: true }   → ruff check --fix .
POST /quality/format { fix: true }   → black .
```

---

## Dependency Graph

```
__init__.py
└── Imports: status, actions

status.py
├── quality.ops    ← quality_status (eager)
├── helpers        ← project_root, get_stack_names (eager)
└── devops.cache   ← get_cached (lazy, inside handler)

actions.py
├── quality.ops    ← quality_run, quality_lint, quality_typecheck,
│                   quality_test, quality_format, generate_quality_config (eager)
├── run_tracker    ← @run_tracked (eager)
└── helpers        ← project_root (eager)
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `quality_bp`, registers at `/api` |
| DevOps card | `scripts/devops/_quality.html` | `/quality/status` (cached detection) |
| Health probe | `metrics/ops._probe_quality` | `quality` cache key |

---

## Data Shapes

### `GET /api/quality/status` response

```json
{
    "tools": [
        {
            "id": "ruff",
            "name": "Ruff",
            "category": "lint",
            "cli_available": true,
            "config_found": true,
            "config_file": "pyproject.toml",
            "relevant": true,
            "install_hint": "pip install ruff"
        },
        {
            "id": "mypy",
            "name": "Mypy",
            "category": "typecheck",
            "cli_available": true,
            "config_found": true,
            "config_file": "pyproject.toml",
            "relevant": true,
            "install_hint": "pip install mypy"
        },
        {
            "id": "eslint",
            "name": "ESLint",
            "category": "lint",
            "cli_available": false,
            "config_found": false,
            "config_file": null,
            "relevant": false,
            "install_hint": "npm install -D eslint"
        }
    ],
    "categories": {
        "lint": 1,
        "typecheck": 1,
        "test": 1,
        "format": 1
    },
    "has_quality": true
}
```

### `POST /api/quality/check` request + response

```json
// Request (specific tool):
{ "tool": "ruff", "fix": false }

// Request (by category):
{ "category": "lint" }

// Response:
{
    "ok": true,
    "results": [
        {
            "tool": "ruff",
            "passed": false,
            "return_code": 1,
            "stdout": "Found 3 errors",
            "stderr": "",
            "fixable": true
        }
    ],
    "all_passed": false
}
```

### `POST /api/quality/generate/config` request + response

```json
// Request:
{ "stack": "python" }

// Response:
{
    "ok": true,
    "files": [
        {
            "path": "pyproject.toml",
            "content": "[tool.ruff]\nline-length = 120\n...",
            "reason": "Ruff linter configuration"
        },
        {
            "path": "pyproject.toml",
            "content": "[tool.mypy]\nstrict = true\n...",
            "reason": "Mypy type-checker configuration"
        }
    ]
}
```

---

## Advanced Feature Showcase

### 1. Stack-Aware Tool Filtering

Detection filters tools by the project's detected stacks:

```python
_tool_matches_stack(tool, stack_name)
# Python project → shows ruff, mypy, pytest, black
# TypeScript project → shows eslint, prettier, tsc, jest
# Both → shows all relevant tools
```

### 2. Fix Mode for Lint and Format

Both lint and format endpoints accept a `fix` flag that switches
between check-only and auto-fix modes:

```
fix=false → ruff check .       (report issues)
fix=true  → ruff check --fix . (fix issues in-place)
```

### 3. Generic vs Category-Specific Endpoints

`/quality/check` is the generic runner that accepts any combination
of `tool`, `category`, and `fix`. The category-specific endpoints
(`/lint`, `/typecheck`, `/test`, `/format`) are convenience
shortcuts that pre-fill the `category` parameter.

### 4. Config Generation per Stack

`/quality/generate/config` creates ready-to-use configuration files
tailored to a specific stack — developers get lint/type/test/format
config in one click.

---

## Design Decisions

### Why every action is tracked

Quality actions produce observable side-effects (console output,
file changes in fix mode). Each gets a distinct tracker tag:
`validate:quality`, `validate:lint`, `validate:typecheck`,
`test:quality`, `format:quality`, `generate:quality_config`.
This enables the activity log to show which quality checks ran.

### Why status uses get_stack_names from helpers

The stack detection logic lives in the web helpers layer because
it may come from wizard state, project config, or auto-detection.
Rather than duplicating this in the core service, the route passes
the resolved stack names as a parameter.

### Why category shortcuts exist alongside the generic endpoint

The generic `/quality/check` is programmatically flexible but
requires the frontend to know about categories. The named shortcuts
(`/lint`, `/typecheck`, `/test`, `/format`) give the UI simple,
semantic one-click buttons.

---

## Coverage Summary

| Capability | Endpoint | Method | Tracked | Cached |
|-----------|----------|--------|---------|--------|
| Quality status | `/quality/status` | GET | No | ✅ `"quality"` |
| Quality check | `/quality/check` | POST | ✅ `validate:quality` | No |
| Lint | `/quality/lint` | POST | ✅ `validate:lint` | No |
| Typecheck | `/quality/typecheck` | POST | ✅ `validate:typecheck` | No |
| Test | `/quality/test` | POST | ✅ `test:quality` | No |
| Format | `/quality/format` | POST | ✅ `format:quality` | No |
| Generate config | `/quality/generate/config` | POST | ✅ `generate:quality_config` | No |
