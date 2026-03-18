# E10 Chunk 2 — Subprocess Operations

> Package manager commands with streaming output.
> Depends on: Chunk 1 complete.
> Architecture: `.agent/docs/E10-wizard-automation-architecture.md`
> Status: READY FOR PLANNING

---

## What This Chunk Delivers

Steps like "Run go mod tidy", "Run bundle update", "Run composer update" become
automatable. The user sees a preview (what command will run), confirms, then the
command streams its output live in the plan modal preview area.

---

## Execution Steps

### Step 1: Create subprocess_ops.py

**File:** `src/core/services/module_upgrade/automation/subprocess_ops.py`

Handlers that execute package manager commands using `_run_subprocess_streaming`.

Functions:
- `handle_run_go_mod_tidy(ctx, mode)` — `go mod tidy` in module dir
- `handle_run_bundle_update(ctx, mode)` — `bundle update` in module dir
- `handle_run_composer_update(ctx, mode)` — `composer update` in module dir
- `handle_run_dotnet_restore(ctx, mode)` — `dotnet restore` in module dir
- `handle_run_mix_deps_get(ctx, mode)` — `mix deps.get` in module dir

Each handler:
- Preview mode: shows the command that will run, the working directory, estimated time
- Execute mode: runs command via `_run_subprocess`, captures output, returns result
- CWD is set to module directory (not project root)
- Checks if the binary exists before running (which/shutil.which)
- Returns stdout/stderr in result for the frontend to display

### Step 2: Add subprocess steps to recipes

Update recipe JSON files to include package manager steps as automatable:

- `go.json`: "Run go mod tidy" → `automation_id: "run_go_mod_tidy"`
- `ruby.json`: "Run bundle update if needed" → `automation_id: "run_bundle_update"`
- `php.json`: "Run composer update" → `automation_id: "run_composer_update"`
- `dotnet.json`: "Run dotnet restore" → `automation_id: "run_dotnet_restore"`
- `elixir.json`: "Run mix deps.get" → `automation_id: "run_mix_deps_get"`

### Step 3: Update handler registry + validate

---

## Files Summary

| Action | File | Est. Lines |
|--------|------|-----------|
| CREATE | `automation/subprocess_ops.py` | ~180 |
| EDIT | 5 recipe JSON files | ~5 lines each |
| EDIT | `automation/__init__.py` | +10 |

**Total new code:** ~190 lines
