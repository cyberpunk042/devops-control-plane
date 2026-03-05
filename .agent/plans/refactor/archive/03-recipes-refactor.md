# Refactor Plan: `recipes.py` → `recipes/` Package — ✅ COMPLETE

> **Scope**: `src/core/services/tool_install/data/recipes.py` (7,436 lines → 29 leaf files + 8 `__init__.py`)
> **Pattern**: Composite Registry with domain/onion sub-folders
> **Rule**: Every file ≤500 lines (≤700 exception for pure data)
> **Breaking changes**: Zero — `TOOL_RECIPES` stays at same import path
> **Completed**: 2026-02-28

---

## 1. Problem Statement

`recipes.py` is a 7,436-line file containing a single dict literal (`TOOL_RECIPES`)
with 300 tool definitions across 26 field types and 60+ category values.

### Why it must change

- Violates the ≤500/≤700 line rule by 10×
- Two conflicting organizational axes: Categories 1–12 group by install method,
  domain batches group by tool domain — inconsistent, confusing
- 29 tools in Categories 1–12 lack the `category` field entirely
- `_PIP` constant is duplicated (defined locally AND in `constants.py`)
- No domain boundaries — adding a tool means scrolling a 7,000-line file

### Why flat splitting is wrong

A naive split into 15 flat files ignores domain boundaries.
The onion/domain strategy means the sub-folder structure itself communicates
"what lives where" — a developer adding a K8s tool opens `recipes/devops/k8s.py`,
not `recipes/batch_k8s.py`. The hierarchy IS the documentation.

---

## 2. Current State

### File structure
```
data/
├── __init__.py          # re-exports TOOL_RECIPES (line 17-18)
├── constants.py         # _PIP, _IARCH_MAP, etc. (55 lines)
├── recipes.py           # 7,436 lines — THE TARGET
├── remediation_handlers.py
├── tool_failure_handlers.py
├── recipe_schema.py
└── ... (5 smaller files)
```

### How `TOOL_RECIPES` is consumed (every single consumer)

| Consumer | Access Pattern |
|----------|---------------|
| `detection/tool_version.py` | `.get(tool_id)`, `list(TOOL_RECIPES.keys())` |
| `detection/service_status.py` | `.get(pack_id)` |
| `detection/recipe_deps.py` | `.get(tool)` |
| `execution/step_executors.py` | (imports, uses via recipe param) |
| `execution/tool_management.py` | `.get(tool)` |
| `domain/remediation_planning.py` | `.get(tool_id)`, `.get(dep)` |
| `resolver/plan_resolution.py` | `.get(tool)`, `.get(tid)`, temporary mutation |
| `resolver/dependency_collection.py` | `.get(tool_id)` |
| `resolver/choice_resolution.py` | `.get(tool)` |
| `resolver/method_selection.py` | (imports, docstring ref) |
| `resolver/dynamic_dep_resolver.py` | `.get(dep)` |
| `orchestration/orchestrator.py` | (re-export consumer) |
| `ui/web/routes_audit.py` | `.get(tool_id)` |
| `ui/cli/audit.py` | `.get(tool_id)` |
| `core/services/wizard/validate.py` | `.get(tool_id)` |
| `core/services/tool_requirements.py` | `.get(tool_id)` |

**Every consumer does flat key lookup.** Nobody iterates by category
or section. The internal organization is invisible to consumers.

### `_PIP` constant

- Defined in `constants.py` line 13: `_PIP: list[str] = [sys.executable, "-m", "pip"]`
- ALSO defined in `recipes.py` line 15: identical duplication
- Used in ~50 recipe entries scattered across many domains
- **Fix**: Delete from `recipes.py`, import from `constants.py` in each sub-file

### Category field analysis

- 300 tools total
- 271 have `category` field, 29 do not (all in Categories 1–12)
- 60+ unique category values
- Category = tool's domain identity — the correct split axis

---

## 3. Target State

### Directory structure (as delivered)
```
data/
├── __init__.py              # unchanged — still imports TOOL_RECIPES from data.recipes
├── constants.py             # unchanged — _PIP lives here (single source of truth)
├── recipes/                 # Package replacing recipes.py (37 files)
│   ├── __init__.py          # Composite registry: merges all sub-dicts → TOOL_RECIPES
│   ├── README.md            # Full documentation with advanced feature showcase
│   │
│   ├── core/                # Core system tools (40 tools)
│   │   ├── __init__.py      # Merges: system + shell
│   │   ├── system.py        # system, compression, process, backup, utility (25)
│   │   └── shell.py         # shell, terminal (15)
│   │
│   ├── languages/           # Programming language ecosystems (109 tools)
│   │   ├── __init__.py      # Merges all 14 language files
│   │   ├── python.py        # python (15)
│   │   ├── node.py          # node, pages (15)
│   │   ├── rust.py          # rust, language (13)
│   │   ├── go.py            # go (6)
│   │   ├── jvm.py           # java, scala, kotlin (8)
│   │   ├── ruby.py          # ruby (3)
│   │   ├── php.py           # php (4)
│   │   ├── dotnet.py        # dotnet (4)
│   │   ├── elixir.py        # elixir (3)
│   │   ├── lua.py           # lua (3)
│   │   ├── zig.py           # zig (2)
│   │   ├── wasm.py          # wasm (3)
│   │   ├── haskell.py       # haskell (3)
│   │   ├── ocaml.py         # ocaml (3)
│   │   └── rlang.py         # rlang (2)
│   │
│   ├── devops/              # DevOps & infrastructure (53 tools)
│   │   ├── __init__.py      # Merges: k8s + cloud + containers + cicd + monitoring
│   │   ├── k8s.py           # k8s (11)
│   │   ├── cloud.py         # cloud, iac, hashicorp (17)
│   │   ├── containers.py    # container, virtualization (12)
│   │   ├── cicd.py          # cicd, git, scm (7)
│   │   └── monitoring.py    # monitoring (6)
│   │
│   ├── security/            # Security & crypto (16 tools)
│   │   ├── __init__.py      # Merges: scanners + crypto
│   │   ├── scanners.py      # security (11)
│   │   └── crypto.py        # crypto (5)
│   │
│   ├── network/             # Networking (17 tools)
│   │   ├── __init__.py      # Merges: network + dns + proxy + service_discovery
│   │   ├── network.py       # network (8)
│   │   ├── dns.py           # dns (3)
│   │   ├── proxy.py         # proxy (4)
│   │   └── service_discovery.py  # service_discovery (2)
│   │
│   ├── data_ml/             # Data, ML & databases (20 tools)
│   │   ├── __init__.py      # Merges: ml + databases + data_packs + gpu
│   │   ├── ml.py            # ml (6)
│   │   ├── databases.py     # database (5)
│   │   ├── data_packs.py    # data_pack (5)
│   │   └── gpu.py           # gpu (4)
│   │
│   └── specialized/         # Dev tools & niche (67 tools)
│       ├── __init__.py      # Merges: devtools + media_docs + config + build_tools
│       ├── devtools.py      # devtools, editors, testing, taskrunner, profiling, formatting (30)
│       ├── media_docs.py    # media, docs, messaging, logging, api, protobuf (22)
│       ├── config.py        # config templates (4)
│       └── build_tools.py   # cpp, embedded (11)
```

### How the Composite Registry works

Each leaf file exports a private partial dict:
```python
# data/recipes/languages/python.py
from src.core.services.tool_install.data.constants import _PIP

_PYTHON_RECIPES: dict[str, dict] = {
    "ruff": {
        "label": "Ruff",
        "category": "python",
        "install": {"_default": _PIP + ["install", "ruff"]},
        ...
    },
    ...
}
```

Each domain `__init__.py` merges its children:
```python
# data/recipes/languages/__init__.py
from src.core.services.tool_install.data.recipes.languages.python import _PYTHON_RECIPES
from src.core.services.tool_install.data.recipes.languages.node import _NODE_RECIPES
from src.core.services.tool_install.data.recipes.languages.rust import _RUST_RECIPES
# ...

_LANGUAGE_RECIPES: dict[str, dict] = {
    **_PYTHON_RECIPES,
    **_NODE_RECIPES,
    **_RUST_RECIPES,
    # ...
}
```

The top-level `recipes/__init__.py` merges all domains:
```python
# data/recipes/__init__.py
from src.core.services.tool_install.data.recipes.core import _CORE_RECIPES
from src.core.services.tool_install.data.recipes.languages import _LANGUAGE_RECIPES
from src.core.services.tool_install.data.recipes.devops import _DEVOPS_RECIPES
from src.core.services.tool_install.data.recipes.security import _SECURITY_RECIPES
from src.core.services.tool_install.data.recipes.network import _NETWORK_RECIPES
from src.core.services.tool_install.data.recipes.data_ml import _DATA_ML_RECIPES
from src.core.services.tool_install.data.recipes.specialized import _SPECIALIZED_RECIPES

TOOL_RECIPES: dict[str, dict] = {
    **_CORE_RECIPES,
    **_LANGUAGE_RECIPES,
    **_DEVOPS_RECIPES,
    **_SECURITY_RECIPES,
    **_NETWORK_RECIPES,
    **_DATA_ML_RECIPES,
    **_SPECIALIZED_RECIPES,
}
```

`data/__init__.py` changes ONE import line:
```python
# Before:
from src.core.services.tool_install.data.recipes import TOOL_RECIPES
# After:
from src.core.services.tool_install.data.recipes import TOOL_RECIPES
# SAME — because recipes/ is now a package, __init__.py exports TOOL_RECIPES
```

**Zero changes to any consumer.**

---

## 4. Prerequisites (Phase 0)

Before any file moves, these must be done IN the existing `recipes.py`:

### 4.1 Add missing `category` fields to 29 tools

| Tool | Section | Category to assign |
|------|---------|-------------------|
| `ruff` | Category 1 (pip) | `python` |
| `mypy` | Category 1 (pip) | `python` |
| `pytest` | Category 1 (pip) | `python` |
| `black` | Category 1 (pip) | `python` |
| `pip-audit` | Category 1 (pip) | `security` |
| `safety` | Category 1 (pip) | `security` |
| `bandit` | Category 1 (pip) | `security` |
| `eslint` | Category 2 (npm) | `node` |
| `prettier` | Category 2 (npm) | `node` |
| `cargo-audit` | Category 3 (cargo) | `rust` |
| `cargo-outdated` | Category 3 (cargo) | `rust` |
| `rustc` | Category 4 (runtimes) | `rust` |
| `skaffold` | Category 6 (snap) | `k8s` |
| `git` | Category 7 (system) | `system` |
| `make` | Category 7 (system) | `system` |
| `gzip` | Category 7 (system) | `compression` |
| `rsync` | Category 7 (system) | `system` |
| `openssl` | Category 7 (system) | `crypto` |
| `ffmpeg` | Category 7 (system) | `media` |
| `expect` | Category 7b (terminal) | `terminal` |
| `xterm` | Category 7b (terminal) | `terminal` |
| `gnome-terminal` | Category 7b (terminal) | `terminal` |
| `xfce4-terminal` | Category 7b (terminal) | `terminal` |
| `konsole` | Category 7b (terminal) | `terminal` |
| `kitty` | Category 8 (per-distro) | `terminal` |
| `npx` | Category 8 (per-distro) | `node` |
| `dig` | Category 8 (per-distro) | `network` |
| `build-essential` | Category 11b | `cpp` |
| `hugo` | Category 12 (pages) | `pages` |

### 4.2 Remove `_PIP` from `recipes.py`

Delete lines 12–15 of `recipes.py`. It's already defined in `constants.py`.
Add `from src.core.services.tool_install.data.constants import _PIP` at top.

Verify nothing breaks: `_PIP` is module-private (`_` prefix), only used
internally within recipes.py — no external consumer imports it from here.

### 4.3 Validate

Run `recipe_schema.py` validation after these changes to confirm
every recipe still passes schema checks with the new `category` values.

---

## 5. Execution Plan (Phase 1)

### Step 1: Create directory structure

```
mkdir -p data/recipes/{core,languages,devops,security,network,data_ml,specialized}
```

### Step 2: Create leaf files

For each domain group, extract matching tool entries from `recipes.py`
based on their `category` field. Each leaf file:

1. Adds `from __future__ import annotations`
2. Imports `_PIP` from `constants.py` if any tool uses it
3. Exports a single `_DOMAIN_RECIPES: dict[str, dict]` variable
4. Contains ONLY the matching tool entries — no extra logic
5. Preserves the per-tool comments

### Step 3: Create domain `__init__.py` files

Each domain folder's `__init__.py`:
1. Imports from its leaf files
2. Merges into a single domain dict
3. Exports it

### Step 4: Create `recipes/__init__.py`

Imports all domain dicts, merges into `TOOL_RECIPES`.

### Step 5: Delete `recipes.py`

Only after step 4 is verified working.

### Step 6: Validate

1. `recipe_schema.py` validation passes on merged `TOOL_RECIPES`
2. `len(TOOL_RECIPES) == 300` — no tools lost
3. All existing imports resolve
4. All tool keys present: compare `sorted(old_keys) == sorted(new_keys)`

---

## 6. Line Budget Estimates

| File | Category values | Est. tools | Est. lines |
|------|----------------|-----------|-----------|
| `core/system.py` | system, compression, process, backup | ~19 | ~475 |
| `core/shell.py` | shell, terminal | ~13 | ~325 |
| `languages/python.py` | python | ~22 | ~550* |
| `languages/node.py` | node, pages | ~11 | ~275 |
| `languages/rust.py` | rust | ~6 | ~150 |
| `languages/go.py` | go | ~6 | ~150 |
| `languages/jvm.py` | java, scala, kotlin | ~8 | ~200 |
| `languages/web.py` | ruby, php | ~7 | ~175 |
| `languages/other.py` | elixir, lua, zig, wasm, haskell, ocaml, rlang, dotnet | ~20 | ~500 |
| `devops/k8s.py` | k8s | ~10 | ~375 |
| `devops/cloud.py` | cloud, iac, hashicorp | ~17 | ~425 |
| `devops/containers.py` | container, virtualization | ~12 | ~300 |
| `devops/cicd.py` | cicd, git | ~6 | ~150 |
| `devops/monitoring.py` | monitoring | ~6 | ~150 |
| `security/tools.py` | security, crypto | ~12 | ~300 |
| `network/tools.py` | network, dns, proxy, service_discovery | ~16 | ~400 |
| `data_ml/tools.py` | ml, data_pack, database, gpu | ~20 | ~600* |
| `specialized/devtools.py` | devtools, editors, testing, taskrunner, profiling, formatting | ~25 | ~500 |
| `specialized/media_docs.py` | media, docs, messaging, logging, api, protobuf | ~19 | ~475 |
| `specialized/config.py` | config | ~4 | ~150 |

`*` = within ≤700 exception for pure data files. If they exceed, split further.

**Total**: ~20 leaf files + ~9 `__init__.py` files = ~29 files
**All under 500–700 lines of pure data, zero logic.**

---

## 7. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Import path changes | Medium | `TOOL_RECIPES` stays at same path — package `__init__.py` |
| Lost tool during move | High | Automated count check: `len(TOOL_RECIPES) == 300` |
| `_PIP` reference breaks | Low | Already in `constants.py` — just change imports |
| `plan_resolution.py` mutates dict | Medium | It mutates the merged dict — still works, refs same object |
| Schema validation fails | Low | Run `validate_all_recipes()` after merge |
| Category assignment wrong | Low | 29 tools need categories — all have obvious domains |

---

## 8. Execution Order

```
Phase 0: Prerequisites (in existing recipes.py)               ✅ COMPLETE
  0.1  Add missing category fields to 29 tools                ✅
  0.2  Remove _PIP duplication (import from constants.py)      ✅
  0.3  Validate: schema check, all tests pass                 ✅

Phase 1: Create package structure                              ✅ COMPLETE
  1.1  Create data/recipes/ directory tree                     ✅
  1.2  Create leaf files (extract tool entries by category)    ✅ (29 leaf files)
  1.3  Create domain __init__.py merge files                   ✅ (7 domain + 1 top)
  1.4  Create recipes/__init__.py top-level merge              ✅
  1.5  Delete old recipes.py                                   ✅
  1.6  Replace lazy catch-all names (other.py, web.py,         ✅ (post-review fix)
       tools.py) with proper domain-named files
  1.7  Write README with full feature showcase                 ✅

Phase 2: Validate                                              ✅ COMPLETE
  2.1  len(TOOL_RECIPES) == 300                                ✅
  2.2  sorted(keys) match original                             ✅
  2.3  No duplicate keys across files                          ✅
  2.4  All consumer imports resolve (package __init__.py)      ✅
  2.5  Updated data/README.md + tool_install/README.md refs    ✅
```

---

## 9. What This Does NOT Cover

- `remediation_handlers.py` (3,725 lines) — separate plan needed
- `tool_failure_handlers.py` (3,228 lines) — separate plan needed
- `step_executors.py` (995 lines) — separate plan needed
- `recipe_schema.py` (722 lines) — borderline, evaluate after recipes split

Each gets its own focused analysis and plan document, one at a time.
