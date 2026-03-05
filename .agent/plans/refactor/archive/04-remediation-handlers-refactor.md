# Refactor Plan: `remediation_handlers.py` → `remediation_handlers/` Package — ✅ COMPLETE

> **Scope**: `src/core/services/tool_install/data/remediation_handlers.py` (3,725 lines → 25 files)
> **Pattern**: Composite Registry with layer-based sub-folders (same as recipes/)
> **Rule**: Every file ≤500 lines (~700 exception for pure data only)
> **Breaking changes**: Zero — all 7 public symbols stay at same import path
> **Completed**: 2026-02-28

---

## 1. Problem Statement

`remediation_handlers.py` is a 3,725-line file containing 4 exported registries
plus 3 constant sets. It's a monolithic data file that violates the ≤500 line rule by 7×.

### Why it must change

- 3,725 lines — 7× over the ≤500 limit
- 19 method families crammed into one dict literal (`METHOD_FAMILY_HANDLERS`)
- 4 conceptually distinct layers in one file (method-family, infra, bootstrap, lib-map)
- Adding a handler for a new method family means scrolling 3,000+ lines
- Same domain-driven split that worked for recipes applies here

### Why the recipes pattern applies directly

The recipes refactor proved:
- One file per domain → navigational documentation
- `__init__.py` composite merge → zero consumer changes
- No lazy catch-all files → each file named for its exact contents

Same pattern. Same rules. One file per method family. One file per layer.

---

## 2. Current State

### File structure

```
data/
├── remediation_handlers.py   # 3,725 lines — THE TARGET
```

### What the file exports — 5 public symbols

| Symbol | Type | Lines | Layer | Contents |
|--------|------|-------|-------|----------|
| `VALID_STRATEGIES` | `set[str]` | 21–33 | Constants | 11 valid strategy values |
| `VALID_AVAILABILITY` | `set[str]` | 35 | Constants | 3 valid availability values |
| `VALID_CATEGORIES` | `set[str]` | 37–51 | Constants | 13 valid category values |
| `METHOD_FAMILY_HANDLERS` | `dict[str, list[dict]]` | 58–3192 | Layer 2 | 66 handlers, 131 options across 19 methods |
| `INFRA_HANDLERS` | `list[dict]` | 3197–3526 | Layer 1 | 9 handlers, 17 options |
| `BOOTSTRAP_HANDLERS` | `list[dict]` | 3531–3601 | Layer 0 | 2 handlers, 3 options |
| `LIB_TO_PACKAGE_MAP` | `dict[str, dict]` | 3608–3724 | Utility | 16 C-lib → distro-package entries |

### The 19 method families in `METHOD_FAMILY_HANDLERS`

| Method Family | Lines | Line Count | Handlers | Options |
|---------------|-------|-----------|----------|---------|
| `pip` | 60–721 | 662 | 11 | 31 |
| `pipx` | 722–819 | 98 | 2 | 3 |
| `cargo` | 820–1014 | 195 | 6 | 8 |
| `go` | 1015–1163 | 149 | 3 | 5 |
| `npm` | 1164–1692 | 529 | 12 | 23 |
| `apt` | 1693–1757 | 65 | 2 | 4 |
| `dnf` | 1758–1792 | 35 | 1 | 2 |
| `yum` | 1793–1825 | 33 | 1 | 2 |
| `snap` | 1826–1862 | 37 | 1 | 2 |
| `brew` | 1863–1895 | 33 | 1 | 2 |
| `apk` | 1896–2013 | 118 | 2 | 5 |
| `pacman` | 2014–2113 | 100 | 2 | 4 |
| `zypper` | 2114–2212 | 99 | 2 | 4 |
| `_default` | 2213–2344 | 132 | 5 | 8 |
| `gem` | 2345–2521 | 177 | 2 | 5 |
| `source` | 2522–2669 | 148 | 5 | 7 |
| `composer_global` | 2670–2790 | 121 | 2 | 4 |
| `curl_pipe_bash` | 2791–2993 | 203 | 3 | 6 |
| `github_release` | 2994–3192 | 199 | 3 | 6 |
| **TOTAL** | | **3,135** | **66** | **131** |

### How the registries are consumed

| Consumer | Imports | Access Pattern |
|----------|---------|----------------|
| `dev_scenarios.py` | `BOOTSTRAP_HANDLERS`, `INFRA_HANDLERS`, `METHOD_FAMILY_HANDLERS` | Direct reference — passes to planning |
| `dynamic_dep_resolver.py` | `LIB_TO_PACKAGE_MAP` | `LIB_TO_PACKAGE_MAP.get(lib_name)` |
| `recipe_schema.py` | `VALID_STRATEGIES`, `VALID_CATEGORIES` | Set membership checks |
| `handler_matching.py` | `BOOTSTRAP_HANDLERS`, `INFRA_HANDLERS`, `METHOD_FAMILY_HANDLERS` | Iterates handlers, regex matches |
| `remediation_planning.py` | `LIB_TO_PACKAGE_MAP`, `VALID_STRATEGIES` | Planning logic |

**Every consumer imports by symbol name.** Nobody imports sub-sections.
The internal organization is invisible to consumers — same as recipes.

---

## 3. Target State

### Directory structure

```
data/
├── remediation_handlers/                    ← Package replacing remediation_handlers.py
│   ├── __init__.py                          ← Re-exports all 5 public symbols
│   │
│   ├── constants.py                         ← VALID_STRATEGIES, VALID_AVAILABILITY, VALID_CATEGORIES
│   │
│   ├── method_families/                     ← Layer 2 — one file per method family
│   │   ├── __init__.py                      ← Merges all 19 → METHOD_FAMILY_HANDLERS
│   │   ├── pip.py                           ← pip (11 handlers, 31 options, ~662 lines)
│   │   ├── pipx.py                          ← pipx (2 handlers, 3 options, ~98 lines)
│   │   ├── cargo.py                         ← cargo (6 handlers, 8 options, ~195 lines)
│   │   ├── go.py                            ← go (3 handlers, 5 options, ~149 lines)
│   │   ├── npm.py                           ← npm (12 handlers, 23 options, ~529 lines)
│   │   ├── apt.py                           ← apt (2 handlers, 4 options, ~65 lines)
│   │   ├── dnf.py                           ← dnf (1 handler, 2 options, ~35 lines)
│   │   ├── yum.py                           ← yum (1 handler, 2 options, ~33 lines)
│   │   ├── snap.py                          ← snap (1 handler, 2 options, ~37 lines)
│   │   ├── brew.py                          ← brew (1 handler, 2 options, ~33 lines)
│   │   ├── apk.py                           ← apk (2 handlers, 5 options, ~118 lines)
│   │   ├── pacman.py                        ← pacman (2 handlers, 4 options, ~100 lines)
│   │   ├── zypper.py                        ← zypper (2 handlers, 4 options, ~99 lines)
│   │   ├── default.py                       ← _default scripts (5 handlers, 8 options, ~132 lines)
│   │   ├── gem.py                           ← gem (2 handlers, 5 options, ~177 lines)
│   │   ├── source.py                        ← source builds (5 handlers, 7 options, ~148 lines)
│   │   ├── composer.py                      ← composer_global (2 handlers, 4 options, ~121 lines)
│   │   ├── curl_pipe_bash.py                ← curl|bash scripts (3 handlers, 6 options, ~203 lines)
│   │   └── github_release.py                ← GitHub release downloads (3 handlers, 6 options, ~199 lines)
│   │
│   ├── infra.py                             ← Layer 1 — INFRA_HANDLERS (9 handlers, ~330 lines)
│   ├── bootstrap.py                         ← Layer 0 — BOOTSTRAP_HANDLERS (2 handlers, ~73 lines)
│   └── lib_package_map.py                   ← LIB_TO_PACKAGE_MAP (16 entries, ~120 lines)
```

### Line budget compliance

| File | Est. Lines | Status |
|------|-----------|--------|
| `constants.py` | ~52 | ✅ well under 500 |
| `method_families/pip.py` | ~662 | ✅ within ~700 exception (pure data) |
| `method_families/pipx.py` | ~98 | ✅ well under 500 |
| `method_families/cargo.py` | ~195 | ✅ well under 500 |
| `method_families/go.py` | ~149 | ✅ well under 500 |
| `method_families/npm.py` | ~529 | ✅ within ~700 exception (pure data) |
| `method_families/apt.py` | ~65 | ✅ well under 500 |
| `method_families/dnf.py` | ~35 | ✅ well under 500 |
| `method_families/yum.py` | ~33 | ✅ well under 500 |
| `method_families/snap.py` | ~37 | ✅ well under 500 |
| `method_families/brew.py` | ~33 | ✅ well under 500 |
| `method_families/apk.py` | ~118 | ✅ well under 500 |
| `method_families/pacman.py` | ~100 | ✅ well under 500 |
| `method_families/zypper.py` | ~99 | ✅ well under 500 |
| `method_families/default.py` | ~132 | ✅ well under 500 |
| `method_families/gem.py` | ~177 | ✅ well under 500 |
| `method_families/source.py` | ~148 | ✅ well under 500 |
| `method_families/composer.py` | ~121 | ✅ well under 500 |
| `method_families/curl_pipe_bash.py` | ~203 | ✅ well under 500 |
| `method_families/github_release.py` | ~199 | ✅ well under 500 |
| `infra.py` | ~330 | ✅ under 500 |
| `bootstrap.py` | ~73 | ✅ well under 500 |
| `lib_package_map.py` | ~120 | ✅ well under 500 |

**Every file under 500** except `pip.py` (~662) and `npm.py` (~529) which are pure data and within the ~700 exception.

---

## 4. How the Composite Registry Works

### Each leaf file exports its method family's handlers list:

```python
# data/remediation_handlers/method_families/pip.py
"""
L0 Data — pip method-family remediation handlers.

Handles: PEP 668, missing venv, root pip, missing pip, permission denied,
         dependency conflicts, hash mismatches, network errors, wheel build
         failures, index errors, constraint conflicts.
"""
from __future__ import annotations

_PIP_HANDLERS: list[dict] = [
    {
        "pattern": r"externally.managed.environment",
        "failure_id": "pep668",
        ...
    },
    ...
]
```

### `method_families/__init__.py` merges all 19:

```python
# data/remediation_handlers/method_families/__init__.py
from __future__ import annotations

from .pip import _PIP_HANDLERS
from .pipx import _PIPX_HANDLERS
from .cargo import _CARGO_HANDLERS
from .go import _GO_HANDLERS
from .npm import _NPM_HANDLERS
from .apt import _APT_HANDLERS
from .dnf import _DNF_HANDLERS
from .yum import _YUM_HANDLERS
from .snap import _SNAP_HANDLERS
from .brew import _BREW_HANDLERS
from .apk import _APK_HANDLERS
from .pacman import _PACMAN_HANDLERS
from .zypper import _ZYPPER_HANDLERS
from .default import _DEFAULT_HANDLERS
from .gem import _GEM_HANDLERS
from .source import _SOURCE_HANDLERS
from .composer import _COMPOSER_HANDLERS
from .curl_pipe_bash import _CURL_PIPE_BASH_HANDLERS
from .github_release import _GITHUB_RELEASE_HANDLERS

METHOD_FAMILY_HANDLERS: dict[str, list[dict]] = {
    "pip": _PIP_HANDLERS,
    "pipx": _PIPX_HANDLERS,
    "cargo": _CARGO_HANDLERS,
    "go": _GO_HANDLERS,
    "npm": _NPM_HANDLERS,
    "apt": _APT_HANDLERS,
    "dnf": _DNF_HANDLERS,
    "yum": _YUM_HANDLERS,
    "snap": _SNAP_HANDLERS,
    "brew": _BREW_HANDLERS,
    "apk": _APK_HANDLERS,
    "pacman": _PACMAN_HANDLERS,
    "zypper": _ZYPPER_HANDLERS,
    "_default": _DEFAULT_HANDLERS,
    "gem": _GEM_HANDLERS,
    "source": _SOURCE_HANDLERS,
    "composer_global": _COMPOSER_HANDLERS,
    "curl_pipe_bash": _CURL_PIPE_BASH_HANDLERS,
    "github_release": _GITHUB_RELEASE_HANDLERS,
}
```

### `remediation_handlers/__init__.py` re-exports all public symbols:

```python
# data/remediation_handlers/__init__.py
from __future__ import annotations

from .constants import VALID_STRATEGIES, VALID_AVAILABILITY, VALID_CATEGORIES
from .method_families import METHOD_FAMILY_HANDLERS
from .infra import INFRA_HANDLERS
from .bootstrap import BOOTSTRAP_HANDLERS
from .lib_package_map import LIB_TO_PACKAGE_MAP

__all__ = [
    "VALID_STRATEGIES",
    "VALID_AVAILABILITY",
    "VALID_CATEGORIES",
    "METHOD_FAMILY_HANDLERS",
    "INFRA_HANDLERS",
    "BOOTSTRAP_HANDLERS",
    "LIB_TO_PACKAGE_MAP",
]
```

**Zero changes to any consumer.** Same import path, same symbols.

---

## 5. Consumer Impact Assessment

Every consumer currently does:
```python
from src.core.services.tool_install.data.remediation_handlers import (
    METHOD_FAMILY_HANDLERS,
    INFRA_HANDLERS,
    ...
)
```

After refactor, `remediation_handlers` is a package.
`remediation_handlers/__init__.py` re-exports the same symbols.
**Import path does not change.** Zero consumer modifications.

### Consumers to verify post-refactor

1. `src/core/services/dev_scenarios.py` — imports `BOOTSTRAP_HANDLERS`, `INFRA_HANDLERS`, `METHOD_FAMILY_HANDLERS`
2. `src/core/services/tool_install/resolver/dynamic_dep_resolver.py` — imports `LIB_TO_PACKAGE_MAP`
3. `src/core/services/tool_install/data/recipe_schema.py` — imports `VALID_STRATEGIES`, `VALID_CATEGORIES`
4. `src/core/services/tool_install/domain/handler_matching.py` — imports `BOOTSTRAP_HANDLERS`, `INFRA_HANDLERS`, `METHOD_FAMILY_HANDLERS`
5. `src/core/services/tool_install/domain/remediation_planning.py` — imports `LIB_TO_PACKAGE_MAP`, `VALID_STRATEGIES`
6. `src/core/services/tool_install/data/tool_failure_handlers.py` — comment reference only, no import

---

## 6. Execution Plan

### Phase 0: Prerequisites                                    ✅ COMPLETE

None needed. File was clean — no duplicated constants or missing fields.

### Phase 1: Create package structure                          ✅ COMPLETE

```
1.1  Create directory tree                                     ✅
1.2  Create constants.py (41 lines)                            ✅
1.3  Create 19 method-family leaf files                        ✅
1.4  Create method_families/__init__.py (50 lines)             ✅
1.5  Create infra.py (341 lines)                               ✅
1.6  Create bootstrap.py (83 lines)                            ✅
1.7  Create lib_package_map.py (129 lines)                     ✅
1.8  Create remediation_handlers/__init__.py (33 lines)        ✅
1.9  Delete old remediation_handlers.py                        ✅
```

### Phase 2: Validate                                          ✅ COMPLETE

```
2.1  All consumer imports resolve                              ✅
2.2  METHOD_FAMILY_HANDLERS: 19 keys                           ✅
2.3  Total handlers: 66 + 9 + 2 = 77                           ✅
2.4  LIB_TO_PACKAGE_MAP: 16 entries                             ✅
2.5  All files ≤500 (pip 668, npm 535 — pure data exception)    ✅
```

### Phase 3: Document                                         ✅ COMPLETE

```
3.1  Write remediation_handlers/README.md                      ✅
3.2  Update data/README.md                                     ✅
3.3  Update tool_install/README.md references if needed        ✅ (no stale refs found)
```

---

## 7. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Import path changes | Medium | `__init__.py` re-exports all symbols — same path |
| Lost handler during move | High | Automated count: 66 + 9 + 2 = 77 handlers |
| Dict key typo in merge | Medium | `METHOD_FAMILY_HANDLERS["pip"]` must match original |
| Consumer breaks | Low | 5 consumers, all verified pre-commit |
| `tool_failure_handlers.py` reference | None | Comment-only reference, no import |

---

## 8. What This Does NOT Cover

- `tool_failure_handlers.py` (3,228 lines) — separate plan needed (plan 05)
- `recipe_schema.py` (722 lines) — borderline, evaluate after this split
- Adding new method families — that's day-to-day work, not refactor scope
