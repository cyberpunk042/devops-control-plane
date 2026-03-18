# E9 — Intelligent Checklist & Automation Engine: Architecture

> Milestone: 2 chunks
> Chunk 1: Intelligent per-case checklist generation
> Chunk 2: Upgrade/downgrade automation engine
> Status: DECISIONS LOCKED — ready for execution planning

---

## Table of Contents

1. [What We're Building](#1-what-were-building)
2. [Decisions (Locked)](#2-decisions-locked)
3. [Existing Infrastructure Inventory](#3-existing-infrastructure-inventory)
4. [Domain Boundaries & SRP](#4-domain-boundaries--srp)
5. [Design Patterns](#5-design-patterns)
6. [JSON Recipe Format](#6-json-recipe-format)
7. [Condition Evaluator](#7-condition-evaluator)
8. [Step ID Scheme](#8-step-id-scheme)
9. [Plan Creation Flow](#9-plan-creation-flow)
10. [Chunk 1: Checklist Generation System](#10-chunk-1-checklist-generation-system)
11. [Chunk 2: Automation Engine](#11-chunk-2-automation-engine)
12. [Data Flow Architecture](#12-data-flow-architecture)
13. [Reuse Map](#13-reuse-map)
14. [Risk Analysis](#14-risk-analysis)

---

## 1. What We're Building

### The Problem

Today, when a user creates a version plan (e.g., "upgrade Python floor from 3.8 to 3.12"),
the checklist is a **hardcoded generic list**. The user manually types steps.

This is wrong because:
1. **The platform already KNOWS** what needs to change — declared floor, deps floor,
   code floor, effective floor, stack requires, project config
2. **Many steps are automatable** — editing pyproject.toml, checking dep compatibility,
   scanning for version-specific code features

### The Vision

```
                    MODULE STATE
                    (intelligence layer)
                         │
                         ▼
              ┌─────────────────────┐
              │  CHECKLIST GENERATOR │ ← Chunk 1
              │  (per-case recipes)  │
              └──────────┬──────────┘
                         │
                    CHECKLIST
                  (structured steps)
                         │
                         ▼
              ┌─────────────────────┐
              │  AUTOMATION ENGINE   │ ← Chunk 2
              │  (execute/assist)    │
              └─────────────────────┘
```

**Chunk 1** generates the RIGHT checklist for each module's specific situation.
**Chunk 2** can execute some of those steps automatically.

---

## 2. Decisions (Locked)

All architectural decisions from discussion, finalized:

| # | Question | Decision |
|---|----------|----------|
| 1 | Where does it live? | **New service** `src/core/services/module_upgrade/` — clean SRP |
| 2 | Recipe format? | **JSON** — consistent with module_lifecycle.json and tool recipes |
| 3 | How does plan creation work? | **Generator IS plan creation** — replaces the current hardcoded generic list. When user creates a plan, the generator produces the checklist. User can edit after. |
| 4 | Semi-auto diff display? | **Same modal** — inline diffs, no additional modal stacking |
| 5 | Category granularity? | **6 categories** — config, deps, code, test, ci, verify. Enough for now. |
| 6 | Recipe versioning? | **No** — always use latest recipe. No versioning overhead. |
| 7 | Direction detection? | **Automatic** — target > current = upgrade, target < current = downgrade |
| 8 | Step ID in project.yml? | **Yes** — `id` field with format `{automation_id}:{suffix}`. Custom steps use `custom:{suffix}`. |
| 9 | Automation metadata in project.yml? | **Only the `id` field** — all other automation metadata (automatable, risk, category) is runtime-only, looked up from recipe via id prefix |
| 10 | Language coverage? | **Python first** — but architecture is language-agnostic from day 1. Adding a language = adding a JSON file, zero code changes to generator. |

---

## 3. Existing Infrastructure Inventory

### What We Already Have (and will reuse)

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXISTING INFRASTRUCTURE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  MODULE INTELLIGENCE (bridges/module_intel.py)                  │
│  ├── compute_dependency_floor()    — per-module dep analysis    │
│  ├── compute_code_floor()          — feature detection + floor  │
│  ├── compute_effective_floor()     — max(declared, deps, code)  │
│  ├── compute_verdict()             — gap/could_lower/consistent │
│  ├── is_deferral_expired()         — date parsing + comparison  │
│  ├── is_plan_overdue()             — deadline tracking          │
│  └── is_plan_met()                 — target vs current check    │
│                                                                 │
│  DETECTION SERVICE (detection.py)                               │
│  ├── detect_runtime_constraint()   — 3-tier floor hierarchy     │
│  ├── detect_language()             — stack → language mapping   │
│  └── detect_modules()              — full module discovery      │
│                                                                 │
│  PROJECT CONFIG (models/project.py + config/loader.py)          │
│  ├── ModuleVersionPlan             — target + date + checklist  │
│  ├── ModuleVersionPlanStep         — id + label + desc + done   │
│  ├── ModuleDeferral                — until + reason             │
│  └── load_project() / save         — YAML round-trip           │
│                                                                 │
│  STACK DEFINITIONS (data/stacks/*/stack.yml)                    │
│  ├── requires[]                    — min_version per adapter    │
│  ├── detection rules               — file patterns             │
│  └── capabilities[]                — available commands         │
│                                                                 │
│  TOOL INSTALL (reuse patterns, not the system)                  │
│  ├── subprocess_runner.py          — safe subprocess execution  │
│  ├── step_executors.py             — dispatcher pattern         │
│  └── handler_matching.py           — cascade condition matching │
│                                                                 │
│  FRONTEND (templates/scripts/globals/)                          │
│  ├── Modal system                  — stacking, replace:false    │
│  ├── Step indicator                — modalSteps() with ✓/●/○   │
│  ├── Admonition system             — _adm() with 6 types       │
│  ├── Collapsible sections          — .rem-section pattern       │
│  └── Plan modal                    — checklist with checkboxes  │
│                                                                 │
│  MEDIATOR (services/mediator/)                                  │
│  ├── posture.modules node          — TTL=60s, persist=True      │
│  └── put() with cascade            — clean invalidation API     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Domain Boundaries & SRP

### Four Separate Concerns

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  INTELLIGENCE (what IS)           PLANNING (what SHOULD we do)      │
│  ─────────────────────           ──────────────────────────────     │
│  module_intel.py (existing)       module_upgrade/generator.py (NEW) │
│  ├── dependency floor             ├── recipe selection              │
│  ├── code floor                   ├── condition evaluation          │
│  ├── effective floor              ├── step materialization          │
│  ├── verdict                      └── label interpolation           │
│  └── decision dates                                                 │
│                                                                     │
│  DETECTION (what EXISTS)          EXECUTION (DO it)                 │
│  ──────────────────────          ──────────────                     │
│  detection.py (existing)          module_upgrade/automation/ (NEW)  │
│  ├── runtime constraint           ├── config file editing           │
│  ├── language detection           ├── dep compatibility checking    │
│  └── module discovery             ├── code pattern scanning         │
│                                   └── verification + rescan         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### New Service Structure

```
src/core/services/module_upgrade/
├── __init__.py                           ← public API: generate_checklist()
├── generator.py                          ← Chunk 1: context → recipe → checklist
├── context.py                            ← UpgradeContext builder
├── evaluator.py                          ← condition evaluator (reads JSON rules)
├── data/
│   ├── recipes/
│   │   ├── python.json                   ← Python upgrade/downgrade steps
│   │   ├── node.json                     ← (future)
│   │   ├── go.json                       ← (future)
│   │   ├── rust.json                     ← (future)
│   │   └── _common.json                  ← shared steps (rescan, verify)
│   └── _meta.json                        ← recipe registry metadata
├── automation/                           ← Chunk 2
│   ├── __init__.py
│   ├── config_editor.py                  ← file mutations
│   ├── dep_checker.py                    ← compatibility queries
│   ├── code_scanner.py                   ← extended analysis
│   └── executor.py                       ← dispatch + execute
└── README.md                             ← schema docs, how to add languages
```

**SRP rules:**
- `generator.py` — ONLY generates step lists. Does NOT execute.
- `evaluator.py` — ONLY evaluates JSON conditions against context. No generation.
- `data/recipes/*.json` — ONLY data. No logic.
- `automation/*.py` — ONLY execute steps. No generation. (Chunk 2)

---

## 5. Design Patterns

### Pattern 1: JSON Recipe with Structured Conditions

Recipes are JSON data files (like module_lifecycle.json). Conditions are structured
rules, NOT lambdas. The Python evaluator reads the rules and returns true/false.

### Pattern 2: Context Object

```python
@dataclass
class UpgradeContext:
    """Everything the generator needs to produce a checklist."""
    module_name: str
    language: str
    current_floor: str
    target_floor: str
    direction: str                 # "upgrade" | "downgrade"
    floor_source: str              # "module" | "stack" | "project"
    strategy: str                  # "latest" | "compatibility"
    verdict: str                   # "gap" | "could_lower" | "consistent"
    deps_floor: str | None
    code_floor: str | None
    code_features: list[str]
    effective_floor: str
    has_future_import: bool
    module_path: str
    project_root: Path
    # File presence (detected at context build time)
    has_pyproject: bool
    has_setup_py: bool
    has_requirements_txt: bool
    has_setup_cfg: bool
```

Built by `context.py` which calls into existing intelligence (module_intel, detection).

### Pattern 3: Conditional Step Inclusion

```
FOR EACH template IN recipe[direction]:
    IF evaluator.evaluate(template.condition, context) IS TRUE:
        step = interpolate(template, context)
        checklist.append(step)
APPEND common tail steps (rescan, verify)
```

Same pattern as handler_matching.py `_collect_all_options()` — collect everything
that matches, don't early-exit.

### Pattern 4: Automation Handler Registry (Chunk 2)

```python
AUTOMATION_HANDLERS = {
    "edit_pyproject_requires_python": handle_edit_pyproject,
    "check_dep_compat_pypi":         handle_dep_compat,
    "scan_code_features":            handle_code_scan,
    "rescan_module":                 handle_rescan,
}
```

Each handler has `preview()` and `execute()` modes. Semi-auto shows diff inline
in the same modal, user confirms before execution.

---

## 6. JSON Recipe Format

### Schema

```json
{
  "_meta": {
    "language": "python",
    "description": "Python module upgrade/downgrade recipes",
    "config_files": ["pyproject.toml", "setup.py", "setup.cfg"]
  },
  "upgrade": [
    {
      "label": "Update requires-python in pyproject.toml",
      "description": "Change >={current} to >={target}",
      "category": "config",
      "automatable": true,
      "automation_id": "edit_pyproject_requires_python",
      "risk": "low",
      "condition": {
        "has_file": "pyproject.toml",
        "floor_source_in": ["module", "project"]
      }
    },
    {
      "label": "Update python_requires in setup.py",
      "description": "Change >={current} to >={target}",
      "category": "config",
      "automatable": true,
      "automation_id": "edit_setup_py_python_requires",
      "risk": "low",
      "condition": {
        "has_file": "setup.py",
        "not_has_file": "pyproject.toml"
      }
    },
    {
      "label": "Check dependency compatibility with {language} {target}",
      "description": "Query PyPI for Requires-Python of each dependency",
      "category": "deps",
      "automatable": true,
      "automation_id": "check_dep_compat_pypi",
      "risk": "low",
      "condition": {
        "has_deps_floor": true
      }
    },
    {
      "label": "Update incompatible dependencies",
      "description": "Find compatible versions for deps that don't support {target}",
      "category": "deps",
      "automatable": false,
      "automation_id": "update_deps_interactive",
      "risk": "medium",
      "condition": {
        "has_deps_floor": true
      }
    },
    {
      "label": "Audit code for {current}→{target} breaking changes",
      "description": "Scan source for version-specific patterns",
      "category": "code",
      "automatable": true,
      "automation_id": "scan_breaking_changes",
      "risk": "low",
      "condition": {
        "always": true
      }
    },
    {
      "label": "Remove unnecessary __future__ annotations imports",
      "description": "Safe to remove when target >= 3.10",
      "category": "code",
      "automatable": true,
      "automation_id": "remove_future_annotations",
      "risk": "low",
      "condition": {
        "has_future_import": true,
        "target_gte": "3.10"
      }
    },
    {
      "label": "Modernize type hints (use builtin generics)",
      "description": "Replace typing.List/Dict with list/dict",
      "category": "code",
      "automatable": false,
      "automation_id": "modernize_type_hints",
      "risk": "medium",
      "condition": {
        "strategy_is": "latest",
        "target_gte": "3.9"
      }
    },
    {
      "label": "Run test suite against {language} {target}",
      "description": "Verify all tests pass on the target version",
      "category": "test",
      "automatable": false,
      "automation_id": "",
      "risk": "low",
      "condition": {
        "always": true
      }
    },
    {
      "label": "Update CI pipeline version matrix",
      "description": "Add/require {language} {target} in CI config",
      "category": "ci",
      "automatable": false,
      "automation_id": "update_ci_matrix",
      "risk": "medium",
      "condition": {
        "always": true
      }
    },
    {
      "label": "Re-scan module and verify new floor",
      "description": "Confirm the platform detects the updated floor",
      "category": "verify",
      "automatable": true,
      "automation_id": "rescan_module",
      "risk": "low",
      "condition": {
        "always": true
      }
    }
  ],
  "downgrade": [
    {
      "label": "Update requires-python in pyproject.toml",
      "description": "Change >={current} to >={target} to widen compatibility",
      "category": "config",
      "automatable": true,
      "automation_id": "edit_pyproject_requires_python",
      "risk": "low",
      "condition": {
        "has_file": "pyproject.toml"
      }
    },
    {
      "label": "Scan for features not available in {language} {target}",
      "description": "Find code patterns that require newer versions",
      "category": "code",
      "automatable": true,
      "automation_id": "scan_incompatible_features",
      "risk": "low",
      "condition": {
        "always": true
      }
    },
    {
      "label": "Add __future__ annotations import where needed",
      "description": "Enable PEP 604/585 syntax on older Python",
      "category": "code",
      "automatable": true,
      "automation_id": "add_future_annotations",
      "risk": "low",
      "condition": {
        "target_lt": "3.10"
      }
    },
    {
      "label": "Replace incompatible syntax with backport patterns",
      "description": "Manual rewrite of match/case, except*, walrus operator etc.",
      "category": "code",
      "automatable": false,
      "automation_id": "",
      "risk": "high",
      "condition": {
        "has_code_floor": true
      }
    },
    {
      "label": "Check all dependencies support {language} {target}",
      "description": "Verify Requires-Python of all deps includes {target}",
      "category": "deps",
      "automatable": true,
      "automation_id": "check_dep_compat_pypi",
      "risk": "low",
      "condition": {
        "always": true
      }
    },
    {
      "label": "Run test suite against {language} {target}",
      "description": "Verify all tests pass on the target version",
      "category": "test",
      "automatable": false,
      "automation_id": "",
      "risk": "low",
      "condition": {
        "always": true
      }
    },
    {
      "label": "Re-scan module and verify new floor",
      "description": "Confirm the platform detects the updated floor",
      "category": "verify",
      "automatable": true,
      "automation_id": "rescan_module",
      "risk": "low",
      "condition": {
        "always": true
      }
    }
  ]
}
```

### Label Interpolation

Recipe JSON uses placeholders: `{target}`, `{current}`, `{language}`

Generator does simple `str.format()`:
```
"Check dependency compatibility with {language} {target}"
→ "Check dependency compatibility with Python 3.12"
```

### Common Steps (`_common.json`)

Steps that apply to ALL languages (appended after language-specific steps):

```json
{
  "_meta": {
    "description": "Common steps appended to all language recipes"
  },
  "upgrade_tail": [
    {
      "label": "Run test suite against {language} {target}",
      "category": "test",
      "automatable": false,
      "automation_id": "",
      "risk": "low",
      "condition": { "always": true }
    },
    {
      "label": "Re-scan module and verify new floor",
      "category": "verify",
      "automatable": true,
      "automation_id": "rescan_module",
      "risk": "low",
      "condition": { "always": true }
    }
  ],
  "downgrade_tail": [
    {
      "label": "Run test suite against {language} {target}",
      "category": "test",
      "automatable": false,
      "automation_id": "",
      "risk": "low",
      "condition": { "always": true }
    },
    {
      "label": "Re-scan module and verify new floor",
      "category": "verify",
      "automatable": true,
      "automation_id": "rescan_module",
      "risk": "low",
      "condition": { "always": true }
    }
  ]
}
```

NOTE: If a language recipe already includes test/verify steps, the generator
deduplicates by automation_id to avoid duplicate steps.

---

## 7. Condition Evaluator

### Supported Operators

All conditions in an object are AND'd. To express OR, duplicate the step with
different conditions (same pattern as tool recipes with multiple methods).

| Operator | Type | Meaning | Example |
|----------|------|---------|---------|
| `always` | bool | Unconditional (always true) | `true` |
| `has_file` | str | File exists in module directory | `"pyproject.toml"` |
| `not_has_file` | str | File does NOT exist in module dir | `"setup.py"` |
| `floor_source_in` | list[str] | Floor came from one of these sources | `["module", "project"]` |
| `floor_source_is` | str | Floor came from exactly this source | `"stack"` |
| `has_deps_floor` | bool | Module has a dependency floor | `true` |
| `has_code_floor` | bool | Module has a code floor | `true` |
| `has_future_import` | bool | Module uses `__future__` annotations | `true` |
| `strategy_is` | str | Version strategy matches | `"latest"` |
| `verdict_is` | str | Consistency verdict matches | `"gap"` |
| `target_gte` | str | Target version >= X | `"3.10"` |
| `target_lt` | str | Target version < X | `"3.10"` |
| `current_lt` | str | Current floor < X | `"3.9"` |
| `current_gte` | str | Current floor >= X | `"3.9"` |

### Evaluator Implementation

```python
def evaluate_condition(condition: dict, ctx: UpgradeContext) -> bool:
    """Evaluate a structured condition dict against an UpgradeContext.

    All keys in the condition dict are AND'd together.
    Returns True if ALL conditions pass.
    """
    for key, value in condition.items():
        if key == "always":
            continue  # always true
        elif key == "has_file":
            if not (ctx.project_root / ctx.module_path / value).exists():
                return False
        elif key == "not_has_file":
            if (ctx.project_root / ctx.module_path / value).exists():
                return False
        elif key == "floor_source_in":
            if ctx.floor_source not in value:
                return False
        elif key == "floor_source_is":
            if ctx.floor_source != value:
                return False
        elif key == "has_deps_floor":
            if bool(ctx.deps_floor) != value:
                return False
        elif key == "has_code_floor":
            if bool(ctx.code_floor) != value:
                return False
        elif key == "has_future_import":
            if ctx.has_future_import != value:
                return False
        elif key == "strategy_is":
            if ctx.strategy != value:
                return False
        elif key == "verdict_is":
            if ctx.verdict != value:
                return False
        elif key == "target_gte":
            if not _ver_gte(ctx.target_floor, value):
                return False
        elif key == "target_lt":
            if _ver_gte(ctx.target_floor, value):
                return False
        elif key == "current_lt":
            if _ver_gte(ctx.current_floor, value):
                return False
        elif key == "current_gte":
            if not _ver_gte(ctx.current_floor, value):
                return False
        else:
            # Unknown operator — skip (forward compatibility)
            pass
    return True
```

### Adding New Operators

To add a new condition operator:
1. Add the key to this table
2. Add the elif branch in `evaluate_condition()`
3. Use it in recipe JSON

No changes to generator, context, or any other file.

---

## 8. Step ID Scheme

### Format: `{automation_id}:{unique_suffix}`

Each step saved to project.yml gets an `id` field. The prefix before `:` matches
the `automation_id` from the recipe, enabling runtime re-linking.

```yaml
# project.yml
modules:
  - name: api-gateway
    path: services/api-gateway
    stack: python-fastapi
    version_plan:
      target: "3.12"
      date: "Q3 2026"
      checklist:
        - id: "edit_pyproject_requires_python:a1b2"
          label: "Update requires-python in pyproject.toml"
          done: false
        - id: "check_dep_compat_pypi:c3d4"
          label: "Check dependency compatibility with Python 3.12"
          done: true
        - id: "custom:e5f6"
          label: "Get team sign-off on migration"
          done: false
```

### Model Change

```python
class ModuleVersionPlanStep(BaseModel):
    id: str = ""          # automation_id:suffix or custom:suffix
    label: str
    description: str = ""
    done: bool = False
```

One new field. The `id` is the bridge between the plan (team decision in project.yml)
and the automation engine (platform knowledge in recipe JSON).

### Runtime Re-Linking

When the plan modal loads and wants to show automation controls:
1. Read step `id` from project.yml
2. Split on `:` → `automation_id = id.split(":")[0]`
3. If `automation_id` is in `AUTOMATION_HANDLERS` → step is automatable, show button
4. If `automation_id` is `"custom"` or `""` → manual step, no automation button
5. Look up `category`, `risk`, `automatable` from recipe JSON by matching `automation_id`

This means automation metadata is NEVER stored in project.yml — it's always
derived at runtime from the recipe. Recipe evolves freely without migration.

---

## 9. Plan Creation Flow

### Current (broken)

```
User clicks "Create Plan"
    ↓
Modal asks: target version + deadline
    ↓
Saves plan with HARDCODED GENERIC checklist
    ↓
User manually adds/edits steps
```

### New (intelligent)

```
User clicks "Create Plan"
    ↓
Modal asks: target version + deadline
    ↓
POST /api/posture/module-plan
  { module: "api-gateway", target: "3.12", date: "Q3 2026" }
    ↓
Backend:
  1. Build UpgradeContext from module intelligence
  2. Determine direction (upgrade vs downgrade)
  3. Load language recipe JSON
  4. Evaluate conditions → filter applicable steps
  5. Interpolate labels with {target}, {current}, {language}
  6. Generate step IDs (automation_id:random_suffix)
  7. Save plan + generated checklist to project.yml
    ↓
Response includes the full generated checklist
    ↓
Plan modal shows the intelligent checklist
User can add/remove/edit/reorder steps afterward
```

The generator IS plan creation. Not an addon. Not a separate button.

---

## 10. Chunk 1: Checklist Generation System

### Public API

```python
# src/core/services/module_upgrade/__init__.py

def generate_checklist(
    module_name: str,
    target: str,
    project_root: Path,
) -> list[dict]:
    """Generate a context-aware upgrade/downgrade checklist for a module.

    Returns list of step dicts ready for ModuleVersionPlanStep creation:
      [{"id": "...", "label": "...", "description": "...", "done": False}, ...]
    """
```

### What the Generator Consumes (all existing)

```
generate_checklist(module_name, target, project_root)
    │
    ├── load_project()                → ModuleRef (strategy, floor_source)
    ├── detect_runtime_constraint()   → current floor, floor_source
    ├── compute_dependency_floor()    → deps_floor
    ├── compute_code_floor()          → code_floor, features, has_future
    ├── compute_effective_floor()     → effective floor
    ├── compute_verdict()             → gap/could_lower/consistent
    ├── check module dir for files    → has_pyproject, has_setup_py, etc.
    ├── load recipe JSON for language → step templates
    └── evaluate conditions           → filtered, interpolated steps
```

All data already exists. The generator is a CONSUMER of existing intelligence.

### Files for Chunk 1

| File | Purpose | Lines (est.) |
|------|---------|-------------|
| `__init__.py` | Public API, `generate_checklist()` entry point | ~30 |
| `context.py` | Build `UpgradeContext` from module state | ~80 |
| `evaluator.py` | Evaluate JSON condition dicts | ~60 |
| `generator.py` | Load recipe, filter steps, interpolate, return | ~80 |
| `data/recipes/python.json` | Python upgrade/downgrade steps | ~150 |
| `data/recipes/_common.json` | Shared tail steps | ~30 |
| `README.md` | Schema docs, how to add languages | ~100 |

Plus model change: add `id: str = ""` to `ModuleVersionPlanStep`.
Plus route change: `POST /posture/module-plan` calls generator instead of saving generic list.

---

## 11. Chunk 2: Automation Engine

### Step Executor Dispatch

```
POST /api/posture/module-step-execute
  { module: "api-gateway", step_id: "edit_pyproject_requires_python:a1b2",
    mode: "preview" | "execute" }
    ↓
  Extract automation_id from step_id prefix
    ↓
  Build UpgradeContext (same as generator)
    ↓
  Dispatch: AUTOMATION_HANDLERS[automation_id](context, step, mode)
    ↓
  mode="preview" → return changes/diff inline (same modal)
  mode="execute" → perform changes, mark step done in project.yml
```

### Automation Handlers

| automation_id | What it does | Mode |
|---------------|-------------|------|
| `edit_pyproject_requires_python` | Edit requires-python field | auto |
| `edit_setup_py_python_requires` | Edit setup.py python_requires | auto |
| `check_dep_compat_pypi` | Query PyPI Requires-Python per dep | auto |
| `update_deps_interactive` | Show alternatives, user picks | semi-auto |
| `scan_breaking_changes` | Scan code for version-breaking patterns | auto |
| `scan_incompatible_features` | Scan for features above target | auto |
| `remove_future_annotations` | Remove __future__ imports (when safe) | auto |
| `add_future_annotations` | Add __future__ imports where needed | auto |
| `modernize_type_hints` | Replace typing.X with builtins | semi-auto |
| `update_ci_matrix` | Detect + edit CI config | semi-auto |
| `rescan_module` | Invalidate + recompute posture | auto |

### Files for Chunk 2

| File | Purpose | Lines (est.) |
|------|---------|-------------|
| `automation/__init__.py` | Handler registry | ~20 |
| `automation/executor.py` | Dispatch + execute + mark done | ~60 |
| `automation/config_editor.py` | Edit pyproject.toml, setup.py, etc. | ~120 |
| `automation/dep_checker.py` | PyPI compatibility queries | ~100 |
| `automation/code_scanner.py` | Extended code analysis | ~100 |

Plus route: `POST /posture/module-step-execute` endpoint.
Plus frontend: automation buttons on plan modal steps, inline diff display.

---

## 12. Data Flow Architecture

```
                    ┌─────────────┐
                    │ project.yml │
                    │  (source of │
                    │   truth for │
                    │  decisions) │
                    └──────┬──────┘
                           │ load_project()
                           ▼
┌──────────────┐    ┌─────────────┐    ┌──────────────────┐
│  detection   │───▶│   module    │───▶│    GENERATOR      │
│  service     │    │   intel     │    │  (Chunk 1)        │
│              │    │             │    │                    │
│ • 3-tier     │    │ • deps flr  │    │ • load recipe JSON │
│   hierarchy  │    │ • code flr  │    │ • eval conditions  │
│ • language   │    │ • effective │    │ • interpolate      │
│ • constraint │    │ • verdict   │    │ • generate IDs     │
└──────────────┘    └─────────────┘    └────────┬─────────┘
                                                │
                                         step dicts[]
                                                │
                                    ┌───────────┴───────────┐
                                    ▼                       ▼
                             ┌──────────┐            ┌──────────┐
                             │ project  │            │ EXECUTOR  │
                             │   .yml   │            │(Chunk 2)  │
                             │  save as │            │           │
                             │  Plan    │            │ • preview │
                             │ Steps    │            │ • execute │
                             │ (id+label│            │ • mark    │
                             │  +done)  │            │   done    │
                             └──────────┘            └──────────┘
```

---

## 13. Reuse Map

```
EXISTING                              REUSED IN
────────────────────────────────────  ──────────────────────────────────
module_intel.compute_*()              Context building (generator input)
module_intel._scan_module_imports()   Automation: dep compatibility check
module_intel.compute_code_floor()     Automation: code feature scan
detection.detect_runtime_constraint() Context building (floor_source)
subprocess_runner._run_subprocess()   Automation: shell commands (chunk 2)
handler_matching cascade pattern      Condition evaluation design
_adm() admonition helper              Plan modal step guidance
_remSection() collapsible sections    Plan modal category grouping
ModuleVersionPlanStep model           Generated steps (+ id field)
posture.py module-plan endpoint       Now calls generator instead of generic
m.put("posture.modules", cascade)     Post-execution invalidation
```

---

## 14. Risk Analysis

### What Could Go Wrong

| Risk | Mitigation |
|------|------------|
| Generator wrong for edge cases | Conditions tested per-language, conservative defaults |
| Automation breaks config files | Preview mode, atomic writes, backup before edit |
| PyPI queries slow/fail | Cache in .state/, timeout + graceful fallback |
| Recipe JSON maintenance | Pure data, easy to update without code changes |
| Custom steps lost on regeneration | Steps are only generated at plan CREATION, not on every load |
| Automation creates inconsistent state | Each step atomic, rescan at end verifies |
| project.yml schema bloat | Only `id` field added, all other metadata is runtime |

### What We're NOT Building

- **No automatic execution without user consent** — semi-auto always shows preview
- **No CI integration** — detect CI files but don't trigger pipelines
- **No cross-module dependency tracking** — each module planned independently
- **No rollback system** — user reverts via git if automation goes wrong
- **No live monitoring** — verify after changes, not during

---

## Adding a New Language (Future)

To add support for a new language (e.g., Node.js):

1. Create `data/recipes/node.json` following the schema above
2. Use existing condition operators (or add new ones to evaluator.py)
3. Add automation handlers in `automation/` if needed (Chunk 2)
4. That's it. Zero changes to generator.py, context.py, or evaluator.py.

The architecture is language-agnostic by design. The generator doesn't know
or care what language it's generating for — it loads the right JSON, evaluates
conditions, interpolates labels, and returns steps.
