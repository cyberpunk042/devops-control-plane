# CLI Domain: Quality — Lint, Typecheck, Test, Format & Config Generation

> **1 file · 222 lines · 8 commands + 1 subgroup · Group: `controlplane quality`**
>
> Multi-tool code quality management: detect quality tools (linters,
> type-checkers, test runners, formatters), run checks by tool,
> category, or all at once with auto-fix support, and generate
> configuration files per stack. Includes convenience aliases for
> common categories (lint, typecheck, test, format).
>
> Core service: `core/services/quality/ops.py` (re-exported via
> `quality_ops.py`)

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                       controlplane quality                          │
│                                                                      │
│  ┌── Detect ─┐  ┌──── Run ──────────────────┐  ┌── Generate ─────┐ │
│  │ status    │  │ check [-t TOOL] [-c CAT]  │  │ generate config │ │
│  └───────────┘  │       [--fix] [--json]    │  │   STACK [--write]│ │
│                  │                            │  └─────────────────┘ │
│                  │  Convenience aliases:      │                      │
│                  │    lint [--fix]            │                      │
│                  │    typecheck               │                      │
│                  │    test                    │                      │
│                  │    format [--fix]          │                      │
│                  └────────────────────────────┘                      │
└──────────┬─────────────────────┬──────────────────┬────────────────┘
           │                     │                  │
           ▼                     ▼                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     core/services/quality/ops.py                    │
│                                                                      │
│  quality_status(root, stack_names) → has_quality, tools[] by cat   │
│  quality_run(root, tool, cat, fix) → results[], passed/total      │
│  generate_quality_config(root, stack) → files[]                    │
└──────────────────────────────────────────────────────────────────────┘
```

### Stack-Aware Detection

The `status` command is unique among CLI domains: it uses
`_detect_stack_names()` to discover what stacks (python, node, go, etc.)
the project uses. This helper runs the full module detection pipeline:

```
_detect_stack_names(root)
├── load_project(project.yml)
├── discover_stacks(stacks/)
├── detect_modules(project, root, stacks)
├── Extract unique effective_stack from each module
└── Return: ["python", "node", ...]
```

The stack names are passed to `quality_status()` so it knows which
tools to look for (ruff/mypy for Python, eslint/tsc for Node, etc.).

### Tool Categories

Quality tools are organized into four categories:

| Category | Icon | Tools (examples) |
|----------|------|-------------------|
| lint | 🔎 | ruff, eslint, golangci-lint |
| typecheck | 📐 | mypy, tsc, pyright |
| test | 🧪 | pytest, jest, go test |
| format | ✨ | black, prettier, gofmt |

### Check Command Architecture

The `check` command is the workhorse. It accepts three targeting modes:

```
check                     → run ALL available tools
check -c lint             → run all tools in the "lint" category
check -t ruff             → run only "ruff"
check -c lint --fix       → run linters with auto-fix
```

The four convenience commands (`lint`, `typecheck`, `test`, `format`)
are thin wrappers that invoke `check` with pre-set `category`:

```python
def lint(ctx, fix):
    ctx.invoke(check, category="lint", fix=fix, tool=None, as_json=False)
```

This means all quality execution goes through a single code path.

### Multi-File Config Generation

The `generate config` command produces **multiple files** per stack
(e.g., Python might generate `pyproject.toml` changes + `.pre-commit-config.yaml`).
It iterates `result["files"]` like K8s manifest generation.

---

## Commands

### `controlplane quality status`

Show detected quality tools grouped by category.

```bash
controlplane quality status
controlplane quality status --json
```

**Output example:**

```
🔍 Quality Tools:

   🔎 Lint:
      ✅ ruff (pyproject.toml)
      ✅ eslint (.eslintrc.json)

   📐 Typecheck:
      ✅ mypy (pyproject.toml)
      ❌ tsc

   🧪 Test:
      ✅ pytest (pyproject.toml)

   ✨ Format:
      ✅ black (pyproject.toml)
```

---

### `controlplane quality check`

Run quality checks — all tools, by category, or specific tool.

```bash
# Run all quality tools
controlplane quality check

# Run specific category
controlplane quality check -c lint
controlplane quality check -c typecheck

# Run specific tool
controlplane quality check -t ruff
controlplane quality check -t mypy

# Auto-fix mode
controlplane quality check -c lint --fix

# JSON output
controlplane quality check --json
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-t/--tool` | string | (none) | Specific tool to run |
| `-c/--category` | choice | (none) | Category: lint, typecheck, test, format |
| `--fix` | flag | off | Auto-fix where supported |
| `--json` | flag | off | JSON output |

**Output example (all pass):**

```
✅ ruff (lint)
✅ mypy (typecheck)
✅ pytest (test)
✅ black (format)

✅ 4/4 passed
```

**Output example (failures):**

```
✅ ruff (lint)
❌ mypy (typecheck)
   src/main.py:42: error: Incompatible types in assignment
   src/core/config.py:15: error: Missing return statement
   ... (8 more lines)
✅ pytest (test)
✅ black (format)
   💡 Auto-fixable: run with --fix

❌ 3/4 passed
```

**Failure output cap:** Shows at most 15 lines of tool output per
failed check. If more, shows `"... (N more lines)"`.

---

### `controlplane quality lint`

Convenience alias for `check -c lint`.

```bash
controlplane quality lint
controlplane quality lint --fix
```

---

### `controlplane quality typecheck`

Convenience alias for `check -c typecheck`.

```bash
controlplane quality typecheck
```

---

### `controlplane quality test`

Convenience alias for `check -c test`.

```bash
controlplane quality test
```

---

### `controlplane quality format`

Convenience alias for `check -c format`.

```bash
controlplane quality format
controlplane quality format --fix
```

---

### `controlplane quality generate config STACK`

Generate quality configuration files for a specific stack.

```bash
controlplane quality generate config python
controlplane quality generate config python --write
controlplane quality generate config node --write
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `STACK` | argument | (required) | Stack name (python, node, go, etc.) |
| `--write` | flag | off | Write files to disk |

---

## File Map

```
cli/quality/
├── __init__.py    222 lines — group definition + 8 commands
│                              + generate subgroup + helpers
└── README.md               — this file
```

**Total: 222 lines of Python in 1 file.**

---

## Per-File Documentation

### `__init__.py` — Group + all commands (222 lines)

**Groups:**

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `quality()` | Click group | Top-level `quality` group |
| `generate()` | Click group | `quality generate` subgroup |

**Commands:**

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `status(ctx, as_json)` | command | Detect quality tools, group by category |
| `check(ctx, tool, category, fix, as_json)` | command | Run quality checks (main runner) |
| `lint(ctx, fix)` | command | Convenience → `check(category="lint")` |
| `typecheck(ctx)` | command | Convenience → `check(category="typecheck")` |
| `test(ctx)` | command | Convenience → `check(category="test")` |
| `fmt(ctx, fix)` | command (`format`) | Convenience → `check(category="format")` |
| `gen_config(ctx, stack_name, write)` | command (`generate config`) | Generate quality configs per stack |

**Helpers:**

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `_resolve_project_root(ctx)` | helper | Reads `config_path` from context, falls back to `find_project_file()` |
| `_detect_stack_names(root)` | helper | Runs full module detection pipeline → unique stack names |

**Code organization within the file:**

```python
# Helpers                        lines 16-43
# ── Detect ──    (status)       lines 51-93
# ── Run ──       (check + 4 convenience)  lines 96-178
# ── Facilitate ── (generate)    lines 181-222
```

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `quality_status` | `quality.ops` | Tool detection by category |
| `quality_run` | `quality.ops` | Tool execution with filtering |
| `generate_quality_config` | `quality.ops` | Config file generation |
| `write_generated_file` | `docker_ops` | Shared file writer |
| `load_project` | `config.loader` | Project configuration loading |
| `discover_stacks` | `config.stack_loader` | Stack definition loading |
| `detect_modules` | `detection` | Module detection for stack names |

**Status grouping logic:** Tools are grouped by category using a
`dict[str, list[dict]]` accumulator. Categories are displayed in a
fixed order: lint → typecheck → test → format. Each category gets
a dedicated icon for visual scanning.

**Check result display:** For each tool result, shows pass/fail icon
+ name + category. On failure, shows tool output (stdout or stderr,
whichever is available). If output exceeds 15 lines, truncates with
count. If the tool supports auto-fix, shows a `💡 Auto-fixable` hint.

**Convenience commands use `ctx.invoke`:** The four convenience commands
(`lint`, `typecheck`, `test`, `format`) delegate to `check` via
Click's `ctx.invoke()`. This is a standard Click pattern for command
aliases that avoids duplicating the check logic.

---

## Dependency Graph

```
__init__.py
├── click                        ← click.group, click.command
├── core.config.loader           ← find_project_file, load_project (lazy)
├── core.config.stack_loader     ← discover_stacks (lazy)
├── core.services.detection      ← detect_modules (lazy)
├── core.services.quality.ops    ← quality_status, quality_run,
│                                   generate_quality_config (all lazy)
└── core.services.docker_ops     ← write_generated_file (lazy)
```

Single file, but has the highest import surface among CLI domains
because `_detect_stack_names()` needs the full detection pipeline.

---

## Consumers

### Who registers this CLI group

| Layer | Module | What It Does |
|-------|--------|-------------|
| CLI entry | `src/main.py:457` | `from src.ui.cli.quality import quality` |

### Who also uses the same core service

| Layer | Module | Core Service Used |
|-------|--------|------------------|
| Web routes | `routes/quality/status.py` | `quality.ops` (status) |
| Web routes | `routes/quality/actions.py` | `quality.ops` (run, fix) |
| Core | `metrics/ops.py:291` | `quality_status` (tool availability probe) |

---

## Design Decisions

### Why convenience commands exist alongside `check`

Most users think in terms of "lint my code" or "run tests", not
"run a quality check filtered by category". The convenience commands
(`lint`, `typecheck`, `test`, `format`) match this mental model
while keeping a single implementation behind the scenes.

### Why `format` is named `fmt` internally

Python's `format` is a builtin function. To avoid shadowing, the
Click command function is named `fmt` but registered as `"format"`:
`@quality.command("format")`.

### Why `status` needs the detection pipeline

Quality tools are stack-dependent. You can't know to look for ruff
without knowing the project has Python modules. The detection pipeline
discovers stacks, and the quality service uses that to filter its
tool database.

### Why `check` output shows 15 lines max

Quality tool output (especially test runners) can be hundreds of
lines. 15 lines is enough to see the first few errors and understand
the pattern. Full output is available via `--json` or by running
the tool directly.

### Why `generate config` produces multiple files

A Python quality setup involves multiple files: `pyproject.toml`
(ruff + mypy + pytest config), `.pre-commit-config.yaml`, and
possibly `.editorconfig`. Generating them as separate files lets
the user selectively adopt tools.

### Why the convenience commands don't have `--json`

They're convenience aliases for quick interactive use. Users who
need JSON output should use `quality check -c lint --json` directly.

---

## JSON Output Examples

### `quality status --json`

```json
{
  "has_quality": true,
  "tools": [
    {
      "name": "ruff",
      "category": "lint",
      "cli_available": true,
      "config_found": true,
      "config_file": "pyproject.toml"
    },
    {
      "name": "mypy",
      "category": "typecheck",
      "cli_available": true,
      "config_found": true,
      "config_file": "pyproject.toml"
    },
    {
      "name": "pytest",
      "category": "test",
      "cli_available": true,
      "config_found": true,
      "config_file": "pyproject.toml"
    }
  ]
}
```

### `quality check --json`

```json
{
  "all_passed": false,
  "passed": 3,
  "total": 4,
  "results": [
    {
      "name": "ruff",
      "category": "lint",
      "passed": true,
      "fixable": false,
      "stdout": "",
      "stderr": ""
    },
    {
      "name": "mypy",
      "category": "typecheck",
      "passed": false,
      "fixable": false,
      "stdout": "Found 2 errors in 2 files",
      "stderr": ""
    }
  ]
}
```
