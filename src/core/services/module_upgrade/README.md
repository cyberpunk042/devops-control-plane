# Module Upgrade Service

Generates intelligent, context-aware checklists for module version upgrades and downgrades.

## Architecture

```
module_upgrade/
├── __init__.py          ← public API: generate_checklist()
├── context.py           ← UpgradeContext builder (collects module intelligence)
├── evaluator.py         ← JSON condition evaluator
├── generator.py         ← recipe loader + step materializer
├── data/
│   └── recipes/
│       ├── python.json  ← Python upgrade/downgrade steps
│       ├── _common.json ← shared tail steps (test, verify)
│       └── (future: node.json, go.json, rust.json, ...)
├── automation/          ← Chunk 2 (step executors, not yet implemented)
│   └── __init__.py
└── README.md
```

## How It Works

1. **Context building** (`context.py`): Gathers all module intelligence into an `UpgradeContext` dataclass — floors, verdict, strategy, file presence, direction.

2. **Recipe loading** (`generator.py`): Loads the JSON recipe for the module's language from `data/recipes/`.

3. **Condition evaluation** (`evaluator.py`): Each recipe step has a `condition` dict. The evaluator checks each condition against the context. All conditions in a dict are AND'd.

4. **Step materialization** (`generator.py`): Passing steps get their labels interpolated (`{target}`, `{current}`, `{language}`) and receive unique IDs.

5. **Common tail** (`_common.json`): Test and verify steps are appended if not already present in the language recipe (deduplicated by `automation_id`).

## Public API

```python
from src.core.services.module_upgrade import generate_checklist

steps = generate_checklist(
    module_name="api-gateway",
    target="3.12",
    project_root=Path("/path/to/project"),
)
# Returns: [{"id": "edit_pyproject_requires_python:a1b2", "label": "...", "description": "..."}, ...]
```

## JSON Recipe Schema

Each recipe file has this structure:

```json
{
  "_meta": {
    "language": "python",
    "description": "...",
    "config_files": ["pyproject.toml", "setup.py"]
  },
  "upgrade": [ ... step templates ... ],
  "downgrade": [ ... step templates ... ]
}
```

### Step Template Fields

| Field | Type | Description |
|-------|------|-------------|
| `label` | string | Step label (supports `{target}`, `{current}`, `{language}` placeholders) |
| `description` | string | Detailed description (supports same placeholders) |
| `category` | string | One of: `config`, `deps`, `code`, `test`, `ci`, `verify` |
| `automatable` | bool | Whether the automation engine can execute this step |
| `automation_id` | string | Handler key for the automation engine (empty for manual steps) |
| `risk` | string | Risk level: `low`, `medium`, `high` |
| `condition` | object | Structured condition dict (all keys AND'd) |

### Condition Operators

| Operator | Type | Description |
|----------|------|-------------|
| `always` | bool | Unconditional (always true) |
| `has_file` | string | File exists in module directory |
| `not_has_file` | string | File does NOT exist in module directory |
| `not_has_files` | list | ALL listed files must be absent in module directory |
| `floor_source_in` | list | Floor source is one of these values |
| `floor_source_is` | string | Floor source matches exactly |
| `has_deps_floor` | bool | Module has a dependency floor |
| `has_code_floor` | bool | Module has a code floor |
| `has_future_import` | bool | Module uses `from __future__ import annotations` |
| `strategy_is` | string | Version strategy matches (`latest` or `compatibility`) |
| `verdict_is` | string | Consistency verdict matches (`gap`, `could_lower`, `consistent`) |
| `target_gte` | string | Target version >= value |
| `target_lt` | string | Target version < value |
| `current_gte` | string | Current floor >= value |
| `current_lt` | string | Current floor < value |

## Step ID Format

Each generated step gets an `id` field: `{automation_id}:{8-char-hex}`

- Generated steps: `edit_pyproject_requires_python:a1b2c3d4`
- Manual steps (no automation): `manual:e5f6a7b8`
- User-added custom steps: `custom:c9d0e1f2`

The prefix before `:` maps to the automation handler registry (Chunk 2).

## Adding a New Language

1. Create `data/recipes/{language}.json` following the schema above
2. Add condition operators to `evaluator.py` if needed (usually not)
3. Map the language in `generator.py` `_LANGUAGE_TO_RECIPE` dict
4. That's it — zero changes to the generator logic or evaluator

## Context Fields

The `UpgradeContext` dataclass contains all data available for conditions and interpolation:

| Field | Source | Description |
|-------|--------|-------------|
| `module_name` | project.yml | Module name |
| `language` | detection.py | Detected language (python, javascript, go, ...) |
| `stack` | project.yml | Stack name (python-fastapi, node-express, ...) |
| `module_path` | project.yml | Relative path to module directory |
| `current_floor` | detection.py | Current declared floor (3-tier) |
| `target_floor` | user input | Target version for upgrade/downgrade |
| `direction` | computed | `upgrade` or `downgrade` |
| `floor_source` | detection.py | `module`, `stack`, or `project` |
| `deps_floor` | module_intel | Highest dep Requires-Python floor |
| `code_floor` | module_intel | Highest code feature version |
| `effective_floor` | module_intel | max(declared, deps, code) |
| `verdict` | module_intel | `consistent`, `gap`, `could_lower`, `unknown` |
| `strategy` | project.yml | `latest`, `compatibility`, or empty |
| `has_future_import` | code scan | Any file has `from __future__ import annotations` |
| `has_pyproject` | file check | pyproject.toml exists in module dir |
| `has_setup_py` | file check | setup.py exists in module dir |
| `has_*` | file check | Various config file presence flags |

## Dependencies

This service is a pure consumer of existing intelligence:
- `src.core.config.loader` — project config
- `src.core.services.detection` — runtime constraint, language detection
- `src.core.services.system_posture.bridges.module_intel` — deep analysis
- `src.core.config.stack_loader` — stack definitions

All imports are lazy (inside function bodies) to prevent circular chains.
