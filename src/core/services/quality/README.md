# Quality Domain

> **2 files · 540 lines · Multi-stack code quality tool detection and execution.**
>
> Detects, configures, and runs 16 quality tools across 5 stacks
> (Python, Node/TypeScript, Go, Rust) in 4 categories (lint, typecheck,
> test, format). Provides unified results with auto-fix support and
> configuration file generation.

---

## How It Works

### Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│ Single module, three operation tiers                                │
│                                                                      │
│  ops.py — DETECT + OBSERVE + FACILITATE tiers                       │
│  ──────                                                              │
│  DETECT   — quality_status (which tools are installed/configured)   │
│  OBSERVE  — quality_run, quality_lint, quality_typecheck, etc.      │
│  FACILITATE — generate_quality_config (create config files)         │
│                                                                      │
│  Pattern: Registry-driven. All tool knowledge is in                 │
│  _QUALITY_TOOLS dict, not spread across functions.                  │
└────────────────────────────────────────────────────────────────────┘
```

### Quality Status Pipeline

```
quality_status(root, *, stack_names=None)
     │
     ├── Iterate _QUALITY_TOOLS registry (16 tools):
     │     │
     │     ├── Check CLI availability:
     │     │     └── shutil.which(tool["cli"]) → bool
     │     │
     │     ├── Check config file presence:
     │     │     └── For each file in tool["config_files"]:
     │     │           └── (project_root / cf).is_file()
     │     │     └── Record first match as config_file
     │     │
     │     ├── Determine relevance:
     │     │     ├── If stack_names provided:
     │     │     │     └── _tool_matches_stack(tool, stack)
     │     │     │           └── stack_name == s
     │     │     │               OR stack_name.startswith(s + "-")
     │     │     │               OR stack_name.startswith(s)
     │     │     └── If stack_names=None → relevant=True (show all)
     │     │
     │     ├── Filter:
     │     │     └── Skip tool if not relevant AND no config found
     │     │
     │     └── Build tool_info dict:
     │           └── {id, name, category, cli_available,
     │                config_found, config_file, relevant, install_hint}
     │
     ├── Count categories:
     │     └── For available + relevant tools:
     │           └── {lint: N, typecheck: N, test: N, format: N}
     │
     ├── Check missing tools:
     │     └── check_required_tools(["ruff", "mypy", "pytest", "black",
     │                               "eslint", "prettier"])
     │
     └── Return {tools, categories, has_quality, missing_tools}
```

### Quality Run Pipeline

```
quality_run(root, *, tool=None, category=None, fix=False)
     │
     ├── Select tools to run:
     │     ├── tool="ruff"      → Single tool from registry
     │     ├── category="lint"  → All tools with category=="lint"
     │     └── Neither          → Run all available tools
     │
     ├── If unknown tool:
     │     └── Return {error: "Unknown tool: X", available: [...]}
     │
     ├── For each selected tool:
     │     │
     │     ├── Skip if CLI not available:
     │     │     └── shutil.which(spec["cli"]) → None → skip
     │     │
     │     ├── Select arguments:
     │     │     ├── fix=True AND spec has "fix_args" → spec["fix_args"]
     │     │     └── Otherwise → spec["run_args"]
     │     │
     │     ├── Execute via _run(args, cwd, timeout=120):
     │     │     └── subprocess.run(capture_output, text, timeout)
     │     │
     │     ├── Determine result:
     │     │     ├── passed = returncode == 0
     │     │     ├── fixable = has fix_args AND NOT passed AND NOT already fixing
     │     │     ├── stdout → truncated to 3000 chars
     │     │     └── stderr → truncated to 1000 chars
     │     │
     │     ├── Handle exceptions:
     │     │     ├── TimeoutExpired → {passed: False, exit_code: -1, stderr: "Timed out"}
     │     │     └── FileNotFoundError → skip tool entirely
     │     │
     │     └── Record {tool, name, category, passed, exit_code,
     │                  stdout, stderr, fixable}
     │
     └── Return {results[], all_passed, total, passed, failed}
```

### Quality Config Generation

```
generate_quality_config(root, stack_name)
     │
     ├── Match stack to templates:
     │     │
     │     ├── python/python-*:
     │     │     ├── Generate ruff.toml (from _RUFF_CONFIG template):
     │     │     │     └── Adapt [tool.ruff] → [ruff] (standalone format)
     │     │     └── Generate mypy.ini (from _MYPY_CONFIG template)
     │     │
     │     ├── node/typescript:
     │     │     ├── Generate eslint.config.mjs (from _ESLINT_CONFIG)
     │     │     └── Generate .prettierrc (from _PRETTIER_CONFIG)
     │     │
     │     └── Other stack:
     │           └── Return {error: "No quality config templates for stack: X"}
     │
     ├── Wrap in GeneratedFile models:
     │     └── Each with overwrite: False (never overwrite existing configs)
     │
     └── Return {ok, files[], count}
```

---

## Architecture

```
             Routes (quality/)
             Metrics (quality probe)
                     │
                     │ imports
                     │
          ┌──────────▼──────────────────────────────┐
          │  quality/__init__.py                      │
          │  Public API — re-exports 7 functions      │
          │  quality_status · quality_run             │
          │  quality_lint · quality_typecheck          │
          │  quality_test · quality_format             │
          │  generate_quality_config                   │
          └──────────┬───────────────────────────────┘
                     │
                     ▼
                 ops.py
                 (All logic in one module)
                     │
                     ├── shutil.which()         ← CLI availability
                     ├── subprocess.run()       ← tool execution
                     ├── tool_requirements      ← missing_tools
                     └── GeneratedFile model    ← config generation

             quality_ops.py — backward-compat shim
```

### Dependency Rules

| Rule | Detail |
|------|--------|
| Single module | All 16 tools, detection, execution, generation in `ops.py` |
| No cross-service imports | Fully self-contained domain |
| No lazy imports needed | Only stdlib (`shutil`, `subprocess`) at module level |
| DataRegistry not used | Tool registry is hardcoded in `_QUALITY_TOOLS` dict |
| tool_requirements at query time | `check_required_tools` called inside `quality_status` |

---

## File Map

```
quality/
├── __init__.py        8 lines   — public API re-exports
├── ops.py           532 lines   — detection, execution, config gen
└── README.md                    — this file
```

---

## Per-File Documentation

### `ops.py` — Quality Operations (532 lines)

**Internal state:**

| Object | Type | Contents |
|--------|------|---------|
| `_QUALITY_TOOLS` | `dict[str, dict]` | 16 tool definitions (see registry below) |
| `_RUFF_CONFIG` | `str` | Python ruff.toml template (29 lines) |
| `_MYPY_CONFIG` | `str` | Python mypy.ini template (10 lines) |
| `_ESLINT_CONFIG` | `str` | Node eslint.config.mjs template (15 lines) |
| `_PRETTIER_CONFIG` | `str` | Node .prettierrc template (7 lines) |

**Private helpers:**

| Function | Parameters | What It Does |
|----------|-----------|-------------|
| `_run(args, cwd, timeout=120)` | `list, Path, int` | Subprocess wrapper: capture_output, text, timeout |
| `_tool_matches_stack(tool, stack)` | `dict, str` | Stack relevance: exact match or prefix match |

**Public API:**

| Function | Parameters | Returns |
|----------|-----------|---------|
| `quality_status(root, *, stack_names)` | `Path, list|None` | `{tools, categories, has_quality, missing_tools}` |
| `quality_run(root, *, tool, category, fix)` | `Path, str, str, bool` | `{results, all_passed, total, passed, failed}` |
| `quality_lint(root, *, fix)` | `Path, bool` | Shortcut → `quality_run(category="lint")` |
| `quality_typecheck(root)` | `Path` | Shortcut → `quality_run(category="typecheck")` |
| `quality_test(root)` | `Path` | Shortcut → `quality_run(category="test")` |
| `quality_format(root, *, fix)` | `Path, bool` | Shortcut → `quality_run(category="format")` |
| `generate_quality_config(root, stack)` | `Path, str` | `{ok, files, count}` or `{error}` |

---

## Key Data Shapes

### quality_status response

```python
{
    "tools": [
        {
            "id": "ruff",
            "name": "Ruff",
            "category": "lint",
            "cli_available": True,
            "config_found": True,
            "config_file": "pyproject.toml",
            "relevant": True,
            "install_hint": "pip install ruff",
        },
        {
            "id": "mypy",
            "name": "mypy",
            "category": "typecheck",
            "cli_available": True,
            "config_found": False,
            "config_file": "",
            "relevant": True,
            "install_hint": "pip install mypy",
        },
        # ... more tools matching detected stacks
    ],
    "categories": {
        "lint": 1,          # available + relevant tools per category
        "typecheck": 1,
        "test": 1,
        "format": 2,
    },
    "has_quality": True,    # at least one tool available + relevant
    "missing_tools": [],    # from check_required_tools
}
```

### quality_run response

```python
# All tools pass
{
    "results": [
        {
            "tool": "ruff",
            "name": "Ruff",
            "category": "lint",
            "passed": True,
            "exit_code": 0,
            "stdout": "All checks passed!",
            "stderr": "",
            "fixable": False,
        },
        {
            "tool": "mypy",
            "name": "mypy",
            "category": "typecheck",
            "passed": True,
            "exit_code": 0,
            "stdout": "Success: no issues found in 42 source files",
            "stderr": "",
            "fixable": False,
        },
    ],
    "all_passed": True,
    "total": 2,
    "passed": 2,
    "failed": 0,
}

# Some tools fail (fixable)
{
    "results": [
        {
            "tool": "ruff",
            "name": "Ruff",
            "category": "lint",
            "passed": False,
            "exit_code": 1,
            "stdout": "Found 3 errors.\nsrc/foo.py:12:1: F401 ...",
            "stderr": "",
            "fixable": True,  # has fix_args, failed, and not already fixing
        },
    ],
    "all_passed": False,
    "total": 1,
    "passed": 0,
    "failed": 1,
}

# Unknown tool
{"error": "Unknown tool: foobar", "available": ["ruff", "mypy", ...]}
```

### generate_quality_config response

```python
# Python stack
{
    "ok": True,
    "files": [
        {
            "path": "ruff.toml",
            "content": "# Ruff configuration — generated by DevOps Control Plane\n...",
            "overwrite": False,
            "reason": "Ruff linter/formatter configuration",
        },
        {
            "path": "mypy.ini",
            "content": "# mypy configuration — generated by ...\n[mypy]\npython_version = 3.12\n...",
            "overwrite": False,
            "reason": "mypy type-checker configuration",
        },
    ],
    "count": 2,
}

# Node stack
{
    "ok": True,
    "files": [
        {
            "path": "eslint.config.mjs",
            "content": "// ESLint flat config — generated by ...\nimport js from ...",
            "overwrite": False,
            "reason": "ESLint linter configuration (flat config)",
        },
        {
            "path": ".prettierrc",
            "content": "{\n  \"semi\": true,\n  ...\n}",
            "overwrite": False,
            "reason": "Prettier formatter configuration",
        },
    ],
    "count": 2,
}

# Unknown stack
{"error": "No quality config templates for stack: java"}
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| **Routes** | `routes/quality/` | Full API |
| **Metrics** | `metrics/ops.py` (_probe_quality) | `quality_status` |
| **Shims** | `quality_ops.py` | Backward-compat re-export |

---

## Dependency Graph

```
ops.py                          ← nearly standalone
   │
   ├── shutil (stdlib)          ← CLI availability (which)
   ├── subprocess (stdlib)      ← tool execution (run)
   ├── tool_requirements        ← check_required_tools (inside quality_status)
   └── models.template          ← GeneratedFile model (inside generate_quality_config)
```

Key: `tool_requirements` and `GeneratedFile` are imported
inside their respective functions — the module can be imported
at zero cost.

---

## Quality Tool Registry

### Tool Entry Shape

Each entry in `_QUALITY_TOOLS` follows this schema:

```python
{
    "name": str,                # Human display name
    "category": str,            # "lint" | "typecheck" | "test" | "format"
    "stacks": list[str],        # Matching stack names
    "cli": str,                 # Binary to shutil.which()
    "run_args": list[str],      # Default check command
    "fix_args": list[str],      # Auto-fix command (optional)
    "config_files": list[str],  # Config filenames to detect
    "install_hint": str,        # Human install instruction (optional)
}
```

### Python Tools (5 tools)

| ID | Name | Category | CLI | Run Args | Fix Args |
|----|------|----------|-----|----------|----------|
| `ruff` | Ruff | lint | `ruff` | `ruff check .` | `ruff check --fix .` |
| `mypy` | mypy | typecheck | `mypy` | `mypy src/ --ignore-missing-imports` | — |
| `pytest` | pytest | test | `pytest` | `pytest --tb=short -q` | — |
| `black` | Black | format | `black` | `black --check .` | `black .` |
| `ruff-format` | Ruff Format | format | `ruff` | `ruff format --check .` | `ruff format .` |

### Node/TypeScript Tools (5 tools)

| ID | Name | Category | CLI | Run Args | Fix Args |
|----|------|----------|-----|----------|----------|
| `eslint` | ESLint | lint | `eslint` | `npx eslint .` | `npx eslint --fix .` |
| `prettier` | Prettier | format | `prettier` | `npx prettier --check .` | `npx prettier --write .` |
| `tsc` | TypeScript Compiler | typecheck | `tsc` | `npx tsc --noEmit` | — |
| `jest` | Jest | test | `jest` | `npx jest --passWithNoTests` | — |
| `vitest` | Vitest | test | `vitest` | `npx vitest run` | — |

### Go Tools (3 tools)

| ID | Name | Category | CLI | Run Args |
|----|------|----------|-----|----------|
| `go-vet` | go vet | lint | `go` | `go vet ./...` |
| `golangci-lint` | golangci-lint | lint | `golangci-lint` | `golangci-lint run` |
| `go-test` | go test | test | `go` | `go test -race -count=1 ./...` |

### Rust Tools (3 tools)

| ID | Name | Category | CLI | Run Args | Fix Args |
|----|------|----------|-----|----------|----------|
| `clippy` | Clippy | lint | `cargo` | `cargo clippy -- -D warnings` | — |
| `rustfmt` | rustfmt | format | `cargo` | `cargo fmt -- --check` | `cargo fmt` |
| `cargo-test` | cargo test | test | `cargo` | `cargo test` | — |

---

## Tool Category Matrix

| Category | Purpose | Python | Node/TS | Go | Rust |
|----------|---------|--------|---------|-----|------|
| **lint** | Static analysis | ruff | eslint | go-vet, golangci-lint | clippy |
| **typecheck** | Type safety | mypy | tsc | — | — |
| **test** | Run test suites | pytest | jest, vitest | go-test | cargo-test |
| **format** | Code formatting | black, ruff-format | prettier | — | rustfmt |

---

## Config Files Per Tool

| Tool | Config Files Checked |
|------|---------------------|
| **ruff** | `ruff.toml`, `.ruff.toml`, `pyproject.toml` |
| **mypy** | `mypy.ini`, `.mypy.ini`, `pyproject.toml`, `setup.cfg` |
| **pytest** | `pytest.ini`, `pyproject.toml`, `setup.cfg`, `conftest.py` |
| **black** | `pyproject.toml` |
| **ruff-format** | `ruff.toml`, `.ruff.toml`, `pyproject.toml` |
| **eslint** | `.eslintrc.js`, `.eslintrc.cjs`, `.eslintrc.json`, `.eslintrc.yml`, `.eslintrc.yaml`, `eslint.config.js`, `eslint.config.mjs` |
| **prettier** | `.prettierrc`, `.prettierrc.json`, `.prettierrc.yml`, `.prettierrc.js`, `prettier.config.js` |
| **tsc** | `tsconfig.json` |
| **jest** | `jest.config.js`, `jest.config.ts`, `jest.config.json` |
| **vitest** | `vitest.config.ts`, `vitest.config.js`, `vite.config.ts` |
| **go-vet** | *(none — always available with Go)* |
| **golangci-lint** | `.golangci.yml`, `.golangci.yaml`, `.golangci.toml` |
| **go-test** | *(none — always available with Go)* |
| **clippy** | *(none — included with Rust toolchain)* |
| **rustfmt** | `rustfmt.toml`, `.rustfmt.toml` |
| **cargo-test** | *(none — always available with Cargo)* |

---

## Install Hints

| Tool | Install Hint |
|------|-------------|
| `ruff` | `pip install ruff` |
| `mypy` | `pip install mypy` |
| `pytest` | `pip install pytest` |
| `black` | `pip install black` |
| `eslint` | `npm install -D eslint` |
| `prettier` | `npm install -D prettier` |
| `jest` | `npm install -D jest` |
| `vitest` | `npm install -D vitest` |
| `tsc` | `npm install -D typescript` |
| `golangci-lint` | *(Go install — long URL)* |
| `clippy` | *(included with Rust toolchain)* |
| `rustfmt` | *(included with Rust toolchain)* |

---

## Generated Config Examples

### Python — `ruff.toml`

```toml
# Ruff configuration — generated by DevOps Control Plane

[ruff]
target-version = "py312"
line-length = 100

[lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "N",    # pep8-naming
    "UP",   # pyupgrade
    "B",    # flake8-bugbear
    "SIM",  # flake8-simplify
    "RUF",  # ruff-specific
]
ignore = [
    "E501",   # line too long (handled by formatter)
]

[lint.isort]
known-first-party = ["src"]

[format]
quote-style = "double"
indent-style = "space"
```

### Python — `mypy.ini`

```ini
[mypy]
python_version = 3.12
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false
ignore_missing_imports = true
check_untyped_defs = true
```

### Node — `eslint.config.mjs`

```javascript
import js from "@eslint/js";

export default [
  js.configs.recommended,
  {
    rules: {
      "no-unused-vars": "warn",
      "no-undef": "error",
    },
  },
  {
    ignores: ["node_modules/", "dist/", "build/"],
  },
];
```

### Node — `.prettierrc`

```json
{
  "semi": true,
  "singleQuote": false,
  "tabWidth": 2,
  "trailingComma": "es5",
  "printWidth": 100
}
```

---

## Run Modes

| Mode | Parameter | Behavior |
|------|-----------|----------|
| Single tool | `tool="ruff"` | Run only Ruff |
| Category | `category="lint"` | Run all lint tools |
| Fix (single) | `tool="ruff", fix=True` | Run Ruff with auto-fix args |
| Fix (category) | `category="format", fix=True` | Run all formatters with fix args |
| Default | *(none)* | Run all available tools |

---

## Output Truncation

Tool output is truncated to prevent oversized responses:

| Stream | Max chars | Why |
|--------|-----------|-----|
| `stdout` | 3,000 | Enough for ~60 lint errors |
| `stderr` | 1,000 | Errors are typically shorter |

The truncation is applied **after** `strip()` so trailing whitespace
doesn't count toward the limit.

---

## Error Handling

| Function | Can Fail? | Error Shape |
|----------|----------|-------------|
| `quality_status` | No | Always returns `{tools, categories, ...}` |
| `quality_run` | Partially | Individual tools may fail, result always returned |
| `quality_*` shortcuts | No | Delegate to `quality_run` |
| `generate_quality_config` | Unknown stack | `{"error": "No quality config templates for stack: X"}` |

Per-tool error handling during `quality_run`:

| Exception | Behavior |
|-----------|----------|
| `subprocess.TimeoutExpired` | Tool recorded as `{passed: False, exit_code: -1, stderr: "Timed out"}` |
| `FileNotFoundError` | Tool silently skipped (CLI disappeared between check and run) |

---

## Stack Matching Logic

A tool is considered relevant for a stack if:

```python
def _tool_matches_stack(tool: dict, stack_name: str) -> bool:
    for s in tool.get("stacks", []):
        if stack_name == s or stack_name.startswith(s + "-") or stack_name.startswith(s):
            return True
    return False
```

This prefix matching means:
- Stack `"python-flask"` matches tools with `stacks: ["python"]`
- Stack `"typescript"` matches tools with `stacks: ["node", "typescript"]`
- Stack `"python"` matches tools with `stacks: ["python"]`

When `stack_names=None` is passed to `quality_status`, all tools
are returned (relevant=True) — useful for showing the full registry
in the UI.

---

## Backward Compatibility

One shim file remains at the services root:

```python
# quality_ops.py
from src.core.services.quality.ops import *  # noqa
```

This shim allows old import paths to continue working
during the migration to the package structure.

---

## Advanced Feature Showcase

### 1. Registry-Driven Tool Detection — 16 Tools from One Dict

All tool knowledge is centralized in `_QUALITY_TOOLS`:

```python
# ops.py — quality_status (lines 228-259)

for tool_id, spec in _QUALITY_TOOLS.items():
    cli_available = shutil.which(spec["cli"]) is not None

    # Check config files — first match wins
    config_found = False
    config_file = ""
    for cf in spec.get("config_files", []):
        if (project_root / cf).is_file():
            config_found = True
            config_file = cf
            break

    # Stack relevance filtering
    relevant = True
    if stack_names:
        relevant = any(_tool_matches_stack(spec, s) for s in stack_names)

    # Only include if relevant OR has config on disk
    if not relevant and not config_found:
        continue

    tools.append({
        "id": tool_id, "name": spec["name"],
        "category": spec["category"],
        "cli_available": cli_available,
        "config_found": config_found, "config_file": config_file,
        "relevant": relevant,
        "install_hint": spec.get("install_hint", ""),
    })
```

The registry acts as a single source of truth — adding a new tool
is one dict entry. The detection loop is generic: it doesn't know
what "ruff" or "cargo" are, it just checks the spec's `cli`,
`config_files`, and `stacks` keys. This means 16 tools share
exactly one detection code path.

### 2. Fix-Mode Argument Switching — Check vs Auto-Fix

A single `fix` flag toggles between check and repair:

```python
# ops.py — quality_run (lines 330-333)

if fix and spec.get("fix_args"):
    args = spec["fix_args"]
else:
    args = spec["run_args"]
```

Examples of the switching:
- `ruff`: `["ruff", "check", "."]` → `["ruff", "check", "--fix", "."]`
- `black`: `["black", "--check", "."]` → `["black", "."]`
- `prettier`: `["npx", "prettier", "--check", "."]` → `["npx", "prettier", "--write", "."]`
- `mypy`: `["mypy", "src/", ...]` → same (no `fix_args` → flag ignored)

Tools without `fix_args` (mypy, tsc, pytest, go-vet, clippy, tests)
are unaffected — the `spec.get("fix_args")` returns falsy and the
regular `run_args` are used regardless of the `fix` flag.

### 3. Prefix-Based Stack Matching — Fuzzy Stack Relevance

Stack matching uses three conditions in priority order:

```python
# ops.py — _tool_matches_stack (lines 199-204)

def _tool_matches_stack(tool: dict, stack_name: str) -> bool:
    for s in tool.get("stacks", []):
        if (stack_name == s                    # exact: "python" == "python"
            or stack_name.startswith(s + "-")  # prefix+dash: "python-flask"
            or stack_name.startswith(s)):      # prefix: "typescript" starts with "type"
            return True
    return False
```

This means a tool with `stacks: ["python"]` matches stacks named
`"python"`, `"python-flask"`, `"python-django"`, etc. And a tool with
`stacks: ["node", "typescript"]` matches both `"node"` and `"typescript"`
ecosystems. The third condition (`startswith(s)`) catches sub-variants
without a dash separator.

### 4. Three-Way Tool Selection — Single, Category, or All

`quality_run` supports three selection modes:

```python
# ops.py — quality_run (lines 311-324)

if tool:
    # Mode 1: Specific tool by ID
    spec = _QUALITY_TOOLS.get(tool)
    if spec:
        tools_to_run.append((tool, spec))
    else:
        return {"error": f"Unknown tool: {tool}",
                "available": list(_QUALITY_TOOLS.keys())}

elif category:
    # Mode 2: All tools in a category
    for tid, spec in _QUALITY_TOOLS.items():
        if spec["category"] == category:
            tools_to_run.append((tid, spec))

else:
    # Mode 3: All registered tools
    for tid, spec in _QUALITY_TOOLS.items():
        tools_to_run.append((tid, spec))
```

Unknown tool IDs return an error with the full available list — the
UI can use this for autocomplete. Category mode runs all 16 tools
filtered to one of 4 categories. Default mode runs everything,
skipping tools whose CLI is missing.

### 5. Fixable Flag Logic — Three-Predicate Guard

The `fixable` field tells the UI whether to show a "Fix" button:

```python
# ops.py — quality_run (line 348)

"fixable": has_fix and not passed and not fix,
```

Three conditions must all be true:
1. `has_fix` — tool has `fix_args` defined (e.g., ruff has them, mypy doesn't)
2. `not passed` — tool reported errors (no point fixing if clean)
3. `not fix` — we're in check mode (if already fixing, don't offer fix again)

This prevents the UI from showing "Fix" for tools that can't fix
(mypy), tools that already pass (clean code), or when the user just
ran a fix (avoid fix loops).

### 6. Pyproject → Standalone Config Transformation

The ruff config template uses `[tool.ruff]` format (pyproject.toml
style) but generates standalone `ruff.toml`:

```python
# ops.py — generate_quality_config (lines 488-497)

files.append(
    GeneratedFile(
        path="ruff.toml",
        content=_RUFF_CONFIG.replace("[tool.ruff]", "[ruff]")
        .replace("[tool.ruff.lint]", "[lint]")
        .replace("[tool.ruff.lint.isort]", "[lint.isort]")
        .replace("[tool.ruff.format]", "[format]"),
        overwrite=False,
        reason="Ruff linter/formatter configuration",
    ).model_dump()
)
```

Why maintain the template in `[tool.ruff]` format? Because it
matches what developers see in `pyproject.toml` documentation. The
four `.replace()` calls strip the `tool.ruff.` prefix for standalone
format. This way the template is recognizable AND the output is valid.

### 7. Category Counting with Dual Predicate

Only tools that are both available AND relevant count toward categories:

```python
# ops.py — quality_status (lines 261-262)

if cli_available and relevant:
    categories[spec["category"]] = categories.get(spec["category"], 0) + 1
```

A tool that's installed but irrelevant to the current stack (e.g.,
`cargo` on a Python project) doesn't inflate the category count.
A tool that's relevant but missing (e.g., `ruff` not installed) also
doesn't count. The dashboard uses these counts to show "2 formatters
available" — both conditions ensure accuracy.

---

### Feature Coverage Summary

| Feature | Where | Complexity |
|---------|-------|-----------|
| Registry-driven 16-tool detection | `ops.py` `quality_status` | Single loop over `_QUALITY_TOOLS` dict |
| Fix-mode argument switching | `ops.py` `quality_run` | `fix_args` / `run_args` toggle |
| Prefix-based stack matching | `ops.py` `_tool_matches_stack` | Three-condition fuzzy match |
| Three-way tool selection | `ops.py` `quality_run` | Single / category / all modes |
| Three-predicate fixable flag | `ops.py` `quality_run` | `has_fix and not passed and not fix` |
| Pyproject → standalone config transform | `ops.py` `generate_quality_config` | Four `.replace()` calls |
| Dual-predicate category counting | `ops.py` `quality_status` | `cli_available and relevant` |

---

## Design Decisions

### Why 16 tools across 5 stacks?

Each language ecosystem has its own dominant quality tools.
Rather than abstracting over them with a generic interface,
the service maps each stack to its native tools, preserving
the tool-specific output, arguments, and configuration that
developers expect. A Go developer sees `golangci-lint` output,
not a normalized abstraction.

### Why fix mode as a flag?

Most quality tools support both check mode (report issues) and
fix mode (auto-repair). A single `fix=True` flag avoids
duplicating the entire run API. The service selects `fix_args`
or `run_args` based on this flag. Tools without `fix_args`
(like mypy) are unaffected by the flag.

### Why category shortcuts?

`quality_lint()` and `quality_format()` are zero-logic wrappers
around `quality_run(category=...)`. They exist because 90% of
usage targets a single category, and the short names are easier
to compose in routes, CLI, and UI buttons.

### Why subprocess with 120-second timeout?

Quality tools can hang on large codebases (especially `mypy` doing
type inference and `eslint` on monorepos). A 120-second timeout
prevents the server from blocking indefinitely. This is generous
enough for most projects while still protecting server responsiveness.

### Why hardcoded registry instead of DataRegistry?

Unlike API spec patterns (which change frequently), quality tools
are stable — new tools appear rarely, and each needs specific
argument handling. A hardcoded `_QUALITY_TOOLS` dict makes the
registry easily inspectable, testable, and versionable alongside
the code that consumes it.

### Why overwrite: False for generated configs?

Quality configurations are frequently customized by teams (e.g.,
specific ruff rules, custom eslint configs). Setting `overwrite: False`
prevents the generator from destroying these customizations.
The UI layer uses this flag to show a warning before overwriting.

### Why output truncation at 3000/1000 chars?

Quality tool output can be enormous (thousands of lint warnings).
Sending full output would bloat API responses and crash thin UI
renderers. The truncation limits were chosen empirically: 3000
chars covers ~60 lint errors (enough to see the pattern), and
1000 chars covers most stderr error messages.
