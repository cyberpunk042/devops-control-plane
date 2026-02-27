# Infrastructure Evolution Plan — Tool Install Subsystem

> **Created:** 2026-02-26
> **Status:** All evolutions complete (A+B+C+D)
> **Trigger:** 4/296 tools audited, scaling patterns visible

---

## Current State (measured, not guessed)

| File | Lines | Size | Growth rate per tool |
|------|-------|------|---------------------|
| `data/recipes.py` | 6,195 | 251KB | ~100-200 lines/tool (recipe + on_failure) |
| `data/remediation_handlers.py` | 2,943 | 118KB | ~30-50 lines/tool (method family additions) |
| `resolver/dynamic_dep_resolver.py` | 466 | 16KB | ~5 lines/tool (KNOWN_PACKAGES entry) |

### What 4 audited tools look like

| Tool | Recipe JSON bytes | on_failure bytes | on_failure % |
|------|------------------|-----------------|-------------|
| `docker` | 12,193 | 10,781 | **88%** |
| `docker-compose` | 5,069 | 3,213 | **63%** |
| `cargo` | 4,153 | 2,667 | **64%** |
| `go` | 4,007 | 2,396 | **60%** |

### What 292 unaudited tools look like

| Metric | Count |
|--------|-------|
| Missing `cli` field | 215/296 (but code already defaults `cli = tool_id`) |
| Missing `category` | 37/296 |
| Missing `update` | 226/296 |
| Missing `on_failure` | 292/296 |
| Missing `prefer` | 285/296 |

### Install method distribution

| Method | Recipes using it | Notes |
|--------|-----------------|-------|
| `brew` | 211 | Most popular |
| `_default` | 182 | Binary download |
| `apt` | 128 | Debian/Ubuntu |
| `dnf` | 115 | Fedora/RHEL |
| `pacman` | 101 | Arch |
| `apk` | 82 | Alpine |
| `zypper` | 69 | openSUSE |
| `snap` | 23 | Canonical |
| `pip/npm/cargo` | 5 | Language PMs |

### Top method combos (34 unique combos)

| Combo | Count | Notes |
|-------|-------|-------|
| `[_default, brew]` | 86 | GitHub-released binaries |
| `[apk, apt, brew, dnf, pacman, zypper]` | 57 | System packages everywhere |
| `[_default]` | 55 | Binary download only |

---

## Evolutions Identified

### Evolution A: Extract `on_failure` from `recipes.py` ✅ DONE

**Completed:** 2026-02-26
**Result:** `recipes.py` 6,195 → 5,340 lines. `tool_failure_handlers.py` created (885 lines). All 4 tools 100% coverage.

#### Problem

`on_failure` handlers are embedded inside `TOOL_RECIPES`. This means:
1. `recipes.py` serves two responsibilities: install-logic AND remediation-data
2. 60-88% of an audited tool's recipe is remediation noise
3. At 296 tools audited, `recipes.py` would be ~40,000+ lines, mostly remediation
4. Recipe definitions (the install logic) get buried under walls of failure patterns

#### Current flow
```
recipes.py::TOOL_RECIPES["go"]["on_failure"]
    ↓ read by
handler_matching.py::_collect_all_options()  →  recipe.get("on_failure", [])
    ↓ also read by
test_remediation_coverage.py  →  recipe.get("on_failure", [])
remediation_planning.py  →  recipe passed through
```

#### Proposed change

Create `data/tool_failure_handlers.py`:
```python
# src/core/services/tool_install/data/tool_failure_handlers.py
"""
Layer 3 remediation handlers — tool-specific failures.

These are keyed by tool_id and apply ONLY to that specific tool.
They are the highest-priority layer in the handler cascade:
  Layer 3 (here) > Layer 2 (METHOD_FAMILY_HANDLERS) > Layer 1 (INFRA_HANDLERS)
"""

TOOL_FAILURE_HANDLERS: dict[str, list[dict]] = {
    "docker": [...],         # moved from TOOL_RECIPES["docker"]["on_failure"]
    "docker-compose": [...], # moved from TOOL_RECIPES["docker-compose"]["on_failure"]
    "cargo": [...],          # moved from TOOL_RECIPES["cargo"]["on_failure"]
    "go": [...],             # moved from TOOL_RECIPES["go"]["on_failure"]
}
```

Update `handler_matching.py` (1 line change):
```python
# Before:
_scan_handlers(recipe.get("on_failure", []), "recipe")

# After:
from ..data.tool_failure_handlers import TOOL_FAILURE_HANDLERS
_scan_handlers(TOOL_FAILURE_HANDLERS.get(tool_id, []), "recipe")
```

Update `test_remediation_coverage.py` (2-3 line change):
```python
# Before:
on_failure_raw = recipe.get("on_failure", [])

# After:
from src.core.services.tool_install.data.tool_failure_handlers import TOOL_FAILURE_HANDLERS
on_failure_raw = TOOL_FAILURE_HANDLERS.get(tool_id, [])
```

Remove `on_failure` from each recipe dict (mechanical deletion).

#### Files touched
| File | Change | Risk |
|------|--------|------|
| `data/tool_failure_handlers.py` | **NEW** — move all on_failure data here | Low |
| `data/recipes.py` | Remove `on_failure` from 4 recipes | Low |
| `domain/handler_matching.py` | 1-line import + lookup change | Low |
| `tests/test_remediation_coverage.py` | 2-3 line import change | Low |
| `data/recipe_schema.py` | Keep `on_failure` as valid field (backward compat) OR remove | Decide |

#### Effort: Small (< 1 hour)
#### Risk: Low (mechanical move, no logic change)
#### Migration: 4 tools to move now. Trivial.

---

### Evolution B: Shared package groups ✅ DONE

**Completed:** 2026-02-26
**Result:** `remediation_handlers.py` 2,944 → 2,896 lines. 7 duplicate package dicts replaced with 3 named groups (`build_tools`, `node_build_tools`, `epel`) in `PACKAGE_GROUPS`. All 4 tools 100% coverage.

#### Problem

`install_packages` strategy options repeat the same distro→package mappings:

| Package group | Duplicated across |
|--------------|-------------------|
| `build-essential / gcc` | `cargo`, `go`, `source` (3 copies) |
| `build-essential + node-gyp deps` | `npm/node_gyp`, `npm/elifecycle` (2 copies) |
| `epel-release` | `dnf/no_match`, `yum/no_package` (2 copies) |

At 296 tools, tools needing CGO, native Node addons, or C extensions will all
repeat the same `build-essential` family mapping. This violates DRY and creates
a maintenance hazard — if Alpine renames `build-base` to something else, we
need to find every copy.

#### Proposed change

Add `PACKAGE_GROUPS` to `dynamic_dep_resolver.py`:
```python
PACKAGE_GROUPS: dict[str, dict[str, list[str]]] = {
    "build_tools": {
        "debian": ["build-essential"],
        "rhel": ["gcc", "gcc-c++", "make"],
        "alpine": ["build-base"],
        "arch": ["base-devel"],
        "suse": ["gcc", "gcc-c++", "make"],
        "macos": ["gcc"],
    },
    "pkg_config": {
        "debian": ["pkg-config"],
        "rhel": ["pkgconf-pkg-config"],
        "alpine": ["pkgconf"],
        "arch": ["pkgconf"],
        "suse": ["pkg-config"],
        "macos": ["pkg-config"],
    },
    "epel": {
        "rhel": ["epel-release"],
    },
}
```

Handlers reference by group name:
```python
# Before:
"strategy": "install_packages",
"packages": {
    "debian": ["build-essential"],
    "rhel": ["gcc", "gcc-c++", "make"],
    "alpine": ["build-base"],
    ...  # 6 families
}

# After:
"strategy": "install_packages",
"packages": "build_tools",   # string = reference to PACKAGE_GROUPS
```

The resolver/test expands the reference at runtime.

#### Files touched
| File | Change | Risk |
|------|--------|------|
| `resolver/dynamic_dep_resolver.py` | Add `PACKAGE_GROUPS` dict | Low |
| `domain/remediation_planning.py` | Resolve string→dict in `_compute_availability` | Medium |
| `data/remediation_handlers.py` | Replace 3 duplicate dicts with group names | Low |
| `tests/test_remediation_coverage.py` | Handle string references in schema check | Low |

#### Effort: Small-Medium (1-2 hours)
#### Risk: Low-Medium (runtime resolution adds a layer)
#### When to do: When we hit 5+ duplicates of the same group. Currently at 3.

---

### Evolution C: `cli` field auto-inference & schema evolution ✅ DONE

**Completed:** 2026-02-26
**Result:** 3 redundant `cli` fields removed (cargo, go, docker). docker-compose keeps `cli: "docker"` since it genuinely differs. Convention documented: only add `cli` when it differs from tool_id.

#### Observation

215/296 recipes are missing the `cli` field. But the code ALREADY  handles this:
```python
cli = recipe.get("cli", tool_id)   # ← 10 call sites, all with fallback
```

This means `cli` is genuinely optional — the system works fine without it.
The only tools that NEED explicit `cli` are those where the binary name differs
from the tool_id (e.g., `docker-compose` → `docker`).

#### Decision: No code change needed

The audit process should:
1. **Only add `cli` when it differs from `tool_id`** — don't add `cli: "go"` to the `go` recipe (it's redundant noise)
2. Document the convention: "cli defaults to tool_id; only specify when different"

#### Action item
- Update the `/tool-coverage-audit` workflow to note this convention
- When auditing future tools: remove unnecessary `cli` fields

**However:** The 4 already-audited tools DO have explicit `cli` fields even where
they're redundant (e.g., `go` has `cli: "go"`). This is harmless but noisy.
We can clean them up when convenient — no urgency.

---

### Evolution D: `update` field completion on unaudited tools ✅ DONE

**Completed:** 2026-02-26
**Result:** Runtime derivation implemented via `get_update_map()`. 189 additional recipes gain update capability without explicit `update` entries. Derivation covers 8 PMs (apt, dnf, yum, apk, pacman, zypper, brew, snap). `_default` and language PMs excluded (not derivable).

#### Observation

226/296 recipes are missing `update` commands. For most PM-based installs,
the update command is predictable from the install command:

| PM | Install | Update |
|----|---------|--------|
| `apt` | `apt-get install -y X` | `apt-get install --only-upgrade -y X` |
| `dnf` | `dnf install -y X` | `dnf upgrade -y X` |
| `brew` | `brew install X` | `brew upgrade X` |
| `snap` | `snap install X` | `snap refresh X` |
| `apk` | `apk add X` | `apk upgrade X` |
| `pacman` | `pacman -S --noconfirm X` | `pacman -S --noconfirm X` (same) |
| `zypper` | `zypper install -y X` | `zypper update -y X` |

This is a **derivable** field. Two possible approaches:

**Option 1: Generate at runtime** (no schema change)
```python
def get_update_command(recipe, method):
    explicit = recipe.get("update", {}).get(method)
    if explicit:
        return explicit
    return _derive_update_from_install(recipe["install"][method], method)
```

**Option 2: Generate once during audit** (current approach — explicit)
Add `update` entries during each tool audit.

**Recommendation:** Option 1 for PM-based methods (derivable), keep Option 2
for `_default` (not derivable — some tools have different update URLs, some
use `--update` flags, some are idempotent reinstalls).

#### Files touched (for Option 1)
| File | Change | Risk |
|------|--------|------|
| Wherever update commands are consumed | Add fallback derivation | Medium |

#### Effort: Medium (needs research on consumption points)
#### Risk: Medium (silent behavior change — must verify no tool has unusual update semantics)
#### When to do: After Evolution A, before scaling to 50+ tools

---

## Execution Order

```
1. Evolution A — Extract on_failure      ✅ DONE (2026-02-26)
   │  Result: recipes.py 6,195→5,340 lines, new tool_failure_handlers.py 885 lines
   │  All 4 tools pass at 100%
   │
2. Evolution B — Package groups           ✅ DONE (2026-02-26)
   │  Result: 7 duplicates → 3 named groups, remediation_handlers.py −48 lines
   │  All 4 tools pass at 100%
   │
3. Evolution D — Update derivation        ✅ DONE (2026-02-26)
   │  Result: get_update_map() derives PM updates, +189 tools updatable
   │
4. Evolution C — cli convention           ✅ DONE (2026-02-26)
      Result: 3 redundant cli fields removed, convention documented
```

---

## What's NOT Broken

These are patterns that scale fine. Do NOT change them:

1. **3-layer cascade** (recipe → method_family → infra) — correct architecture
2. **Handler matching regex** — simple, testable, no polymorphism needed
3. **19-preset validation** — good coverage, fast execution
4. **Per-tool spec docs** — documentation doesn't have scaling problems
5. **Method family handlers** — correct grouping, no duplication across families
6. **KNOWN_PACKAGES** — flat dict, O(1) lookup, grows linearly
7. **Recipe schema validation** — comprehensive, catches errors early

---

## Decision Questions for User

1. **Evolution A:** Approve extracting `on_failure` to `data/tool_failure_handlers.py`?
   - Alternative: Keep in recipes but accept the file size growth
   
2. **Evolution B:** Approve shared package groups when 5+ duplicates exist?
   - Alternative: Accept copy-paste, fix all copies when packages change
   
3. **Evolution D:** Approve runtime derivation for PM update commands?
   - Alternative: Keep generating them explicitly during each audit

4. **Evolution C:** Confirm convention: only add `cli` when it differs from tool_id?
   - Should we clean up the 4 redundant `cli` fields on already-audited tools?
