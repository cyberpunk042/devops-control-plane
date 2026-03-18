# E9 Chunk 1 — Intelligent Checklist Generation System

> Replaces the hardcoded 5-item generic list with context-aware per-module checklists.
> Architecture: `.agent/docs/E9-checklist-automation-architecture.md`
> Status: READY FOR EXECUTION

---

## What Changes

| Before | After |
|--------|-------|
| POST /posture/module-plan creates 5 hardcoded steps | POST /posture/module-plan calls generator, creates N context-aware steps |
| All modules get the same checklist | Each module gets steps based on its floor, deps, code, strategy, files |
| Steps have no ID | Steps have `id` field: `automation_id:suffix` |
| No recipe data | JSON recipe for Python (language-agnostic schema) |

---

## Execution Steps

### Step 1: Model change — add `id` to ModuleVersionPlanStep

**File:** `src/core/models/project.py` (line 42)

Add `id: str = ""` field to `ModuleVersionPlanStep`:

```python
class ModuleVersionPlanStep(BaseModel):
    id: str = ""          # automation_id:suffix or custom:suffix
    label: str
    description: str = ""
    done: bool = False
```

**Impact:** Backward compatible — existing plans without `id` get `""` default.
Must also check that the PATCH (toggle done) and DELETE (remove step) endpoints
still work with the new field. They match by index, so no breakage expected.

The POST /posture/module-plan-step (add custom step) endpoint needs to generate
a `custom:{uuid4_short}` id for user-added steps.

---

### Step 2: Create service directory + context builder

**Create:** `src/core/services/module_upgrade/__init__.py`
**Create:** `src/core/services/module_upgrade/context.py`

`__init__.py` — Public API:
```python
from .generator import generate_checklist
```

`context.py` — Build `UpgradeContext` dataclass from module state:
- Call `load_project()` to get ModuleRef (strategy, floor_source)
- Call `detect_runtime_constraint()` for current floor + source
- Call `compute_dependency_floor()` for deps_floor
- Call `compute_code_floor()` for code_floor, features, has_future
- Call `compute_effective_floor()` for effective
- Call `compute_verdict()` for verdict
- Check file existence in module dir (pyproject.toml, setup.py, etc.)
- Determine direction: target > current = upgrade, target < current = downgrade

All imports are lazy (inside function body) — follows project pattern.

---

### Step 3: Create condition evaluator

**Create:** `src/core/services/module_upgrade/evaluator.py`

Single function: `evaluate_condition(condition: dict, ctx: UpgradeContext) -> bool`

14 operators (all AND'd within a condition dict):
- `always`, `has_file`, `not_has_file`
- `floor_source_in`, `floor_source_is`
- `has_deps_floor`, `has_code_floor`, `has_future_import`
- `strategy_is`, `verdict_is`
- `target_gte`, `target_lt`, `current_lt`, `current_gte`

Version comparisons use tuple parsing (same pattern as `_ver_tuple` in module_intel).

---

### Step 4: Create Python recipe JSON

**Create:** `src/core/services/module_upgrade/data/recipes/python.json`

Full recipe with `upgrade` and `downgrade` step arrays.
Each step: `label`, `description`, `category`, `automatable`, `automation_id`, `risk`, `condition`.
Labels use `{target}`, `{current}`, `{language}` placeholders.

See architecture doc section 6 for complete schema.

**Create:** `src/core/services/module_upgrade/data/recipes/_common.json`

Common tail steps (test + verify) appended after language-specific steps.
Deduplicated by `automation_id` to avoid duplicates if language recipe already
includes them.

---

### Step 5: Create generator

**Create:** `src/core/services/module_upgrade/generator.py`

`generate_checklist(module_name, target, project_root) -> list[dict]`

Flow:
1. Build `UpgradeContext` via `context.py`
2. Load recipe JSON for `ctx.language` (fall back to _common only)
3. Select `upgrade` or `downgrade` array based on `ctx.direction`
4. For each step template: evaluate condition → if true, interpolate labels → append
5. Append common tail steps (deduplicate by automation_id)
6. Generate step IDs: `{automation_id}:{uuid4_short}` (or `manual:{uuid4_short}` if no automation_id)
7. Return list of dicts: `[{"id": "...", "label": "...", "description": "...", "done": False}]`

---

### Step 6: Wire generator into plan creation endpoint

**File:** `src/ui/web/routes/posture.py` (lines 918-924)

Replace the hardcoded 5-item list:

```python
# BEFORE (lines 918-924):
"checklist": [
    {"label": f"Verify all dependencies support Python ≥{target_floor}"},
    {"label": f"Update requires-python to ≥{target_floor}"},
    {"label": "Update CI test matrix"},
    {"label": f"Run full test suite on Python {target_floor}"},
    {"label": "Remove compatibility shims if any"},
],

# AFTER:
from src.core.services.module_upgrade import generate_checklist
checklist_steps = generate_checklist(module_name, target_floor, project_root)
# ... use checklist_steps in the plan dict
```

The endpoint still saves to project.yml the same way — the data shape is identical
(list of dicts with label, description, done). The only new field is `id`.

---

### Step 7: Wire `id` into custom step endpoint

**File:** `src/ui/web/routes/posture.py` — POST /posture/module-plan-step

When user adds a custom step, generate `id: "custom:{uuid4_short}"`.

---

### Step 8: Create README

**Create:** `src/core/services/module_upgrade/README.md`

Document:
- Service purpose and architecture
- JSON recipe schema (all fields explained)
- Condition operator reference (all 14 operators)
- How to add a new language recipe
- Context fields available for interpolation
- Step ID format

---

## Files Summary

| Action | File | Est. Lines |
|--------|------|-----------|
| EDIT | `src/core/models/project.py` | +1 (add id field) |
| CREATE | `src/core/services/module_upgrade/__init__.py` | ~10 |
| CREATE | `src/core/services/module_upgrade/context.py` | ~80 |
| CREATE | `src/core/services/module_upgrade/evaluator.py` | ~60 |
| CREATE | `src/core/services/module_upgrade/generator.py` | ~80 |
| CREATE | `src/core/services/module_upgrade/data/recipes/python.json` | ~160 |
| CREATE | `src/core/services/module_upgrade/data/recipes/_common.json` | ~30 |
| EDIT | `src/ui/web/routes/posture.py` | ~10 (replace hardcoded list) |
| EDIT | `src/ui/web/routes/posture.py` | ~3 (custom step id) |
| CREATE | `src/core/services/module_upgrade/README.md` | ~100 |

**Total new code:** ~420 lines + ~100 lines docs
**Total edits:** ~14 lines changed in existing files

---

## Verification

After implementation:
1. Create a plan for a Python module → should get context-aware steps (not the old 5)
2. Steps should have `id` fields in project.yml
3. Custom-added steps should get `custom:xxxx` ids
4. Module with pyproject.toml gets "Update requires-python" step
5. Module without pyproject.toml but with setup.py gets "Update setup.py" step
6. Module with deps_floor gets dep compatibility steps
7. Module with __future__ imports + target >= 3.10 gets "Remove __future__" step
8. Upgrade direction gets upgrade steps, downgrade gets downgrade steps
9. Existing plans (without id) still load and work (backward compat)
