---
description: Audit and fix tool remediation coverage — recipes, deps, handlers, per-system availability
---

# Tool Remediation Audit Workflow

## The test

Everything is validated by a single script. Run it to see the current state:

```bash
# Quick run — errors only
// turbo
.venv/bin/python -m tests.test_remediation_coverage

# Verbose — include warnings (missing labels, system package notes)
// turbo
.venv/bin/python -m tests.test_remediation_coverage --verbose

# Full — errors + warnings + coverage suggestions (missing methods per system)
// turbo
.venv/bin/python -m tests.test_remediation_coverage --verbose --suggest
```

File: `tests/test_remediation_coverage.py`

---

## What the test checks

| Check | What it validates | File(s) |
|-------|-------------------|---------|
| **1. Recipe completeness** | Every recipe has `cli`, `label`, install methods | `data/recipes.py` |
| **2. Dep coverage** | Every dep in handlers is resolvable (has recipe or is system pkg) | `data/remediation_handlers.py`, `domain/remediation_planning.py` |
| **3. Handler option validity** | `switch_method` targets exist, `install_packages` covers families | `data/remediation_handlers.py` |
| **4. Scenario availability** | No false impossibles across ALL system presets | `dev_scenarios.py`, all presets |
| **5. Missing tools** | Expected common tools have recipes | `data/recipes.py` |
| **6. Method coverage** | Tools with pkg mgr methods cover all systems (--suggest only) | `data/recipes.py` |

## System presets tested

| Preset | Family | Pkg Mgr | Arch | Notes |
|--------|--------|---------|------|-------|
| `debian_12` | debian | apt | x86_64 | |
| `ubuntu_2204` | debian | apt | x86_64 | |
| `raspbian_arm` | debian | apt | aarch64 | Raspberry Pi |
| `fedora_39` | rhel | dnf | x86_64 | |
| `alpine_318` | alpine | apk | x86_64 | |
| `opensuse_15` | suse | zypper | x86_64 | |
| `macos_14` | macos | brew | arm64 | Apple Silicon |
| `arch_latest` | arch | pacman | x86_64 | |

---

## How to fix issues

### `recipe/<tool>: missing or placeholder cli field`

Open `src/core/services/tool_install/data/recipes.py`, find the tool entry,
set `"cli"` to the actual binary name (e.g. `"cli": "ruff"`).

### `recipe/<tool>: NO install methods at all`

Either:
- Add install methods if the tool is installable
- Add `"_not_installable": True` to the recipe if it's config/data (e.g. `docker-daemon-config`)

### `missing/<tool>: expected tool has no recipe`

Add a recipe entry in `data/recipes.py`. Use existing recipes as templates.
The test's `EXPECTED_TOOLS` set defines what tools should exist.

### `dep/<dep>: impossible — No recipe for '<dep>'`

The dep is referenced in a handler `strategy: install_dep` but has no recipe
and isn't resolvable as a system package. Either add a recipe or fix the handler.

### `scenario/<preset>/<id>/<opt>: FALSE IMPOSSIBLE`

A remediation option is showing as "impossible" when it should be ready or locked.
Trace the option's strategy and fix the underlying cause (missing method in recipe,
missing packages for the family, etc).

### Coverage suggestions (`--suggest`)

These are not errors — they show tools that have some pkg mgr methods but could
have more. For example, a tool with only `brew` could also have `apt`, `dnf`, etc.
Address these incrementally, prioritizing commonly used tools.

---

## Process for fixing a batch

1. Run the test: `.venv/bin/python -m tests.test_remediation_coverage`
2. Pick a category of issues (e.g. all missing `cli` fields for Python tools)
3. Fix the issues in the relevant data file
4. Re-run the test to verify fixes didn't break anything
5. Repeat until the test passes clean
