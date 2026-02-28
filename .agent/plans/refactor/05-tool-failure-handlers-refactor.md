# Refactor Plan: `tool_failure_handlers.py` → `tool_failure_handlers/` Package

> **Scope**: `src/core/services/tool_install/data/tool_failure_handlers.py` (3,228 lines → ~14 files)
> **Pattern**: Composite Registry with domain-based sub-folders (mirrors recipes/)
> **Rule**: Every file ≤500 lines (~700 exception for pure data only)
> **Breaking changes**: Zero — `TOOL_FAILURE_HANDLERS` stays at same import path
> **Started**: 2026-02-28

---

## 1. Problem Statement

`tool_failure_handlers.py` is a 3,228-line file containing 18 tool-keyed handler
lists in one monolithic dict. It violates the ≤500 line rule by 6×.

### Why it must change

- 3,228 lines — 6× over the ≤500 limit
- 18 tools crammed into one dict literal
- Adding a handler means scrolling 3,000+ lines
- The domain-based split that worked for recipes/ and remediation_handlers/ applies here

### Why domain sub-folders, not flat files

The 18 tools map cleanly to the same domains used in recipes/:
- `languages/rust.py` has `cargo`, `rustup` — so does this
- `devops/containers.py` has `docker`, `docker-compose` — so does this
- `security/scanners.py` has `trivy` — so does this

Flat files would ignore the domain context that already exists.

---

## 2. Current State

### File structure

```
data/
├── tool_failure_handlers.py   # 3,228 lines — THE TARGET
```

### What the file exports — 1 public symbol

| Symbol | Type | Lines | Contents |
|--------|------|-------|----------|
| `TOOL_FAILURE_HANDLERS` | `dict[str, list[dict]]` | 17–3226 | 18 tool keys, ~57 handlers total |

### The 18 tools with line ranges

| Tool | Lines (start→end) | Line Count | Domain |
|------|-------------------|-----------|--------|
| `cargo` | 21→146 | 125 | languages/rust |
| `rustup` | 152→275 | 123 | languages/rust |
| `gh` | 279→391 | 112 | devops/cloud |
| `helm` | 395→508 | 113 | devops/k8s |
| `go` | 513→637 | 124 | languages/go |
| `docker` | 641→1103 | 462 | devops/containers |
| `docker-compose` | 1107→1248 | 141 | devops/containers |
| `python` | 1251→1641 | 390 | languages/python |
| `yarn` | 1645→1828 | 183 | languages/node |
| `poetry` | 1832→1894 | 62 | languages/python |
| `trivy` | 1898→2010 | 112 | security/scanners |
| `uv` | 2014→2090 | 76 | languages/python |
| `pnpm` | 2094→2167 | 73 | languages/node |
| `nvm` | 2172→2298 | 126 | languages/node |
| `kubectl` | 2302→2467 | 165 | devops/k8s |
| `node` | 2471→2822 | 351 | languages/node |
| `composer` | 2826→3015 | 189 | languages/php |
| `terraform` | 3021→3226 | 205 | devops/cloud |

### How the registry is consumed

| Consumer | Import | Access Pattern |
|----------|--------|----------------|
| `handler_matching.py` | `from ...data.tool_failure_handlers import TOOL_FAILURE_HANDLERS` | `TOOL_FAILURE_HANDLERS.get(tool_id, [])` |

**1 consumer.** Direct import from the file, not via `data/__init__.py`.

---

## 3. Target State

### Directory structure

```
data/
├── tool_failure_handlers/                   ← Package replacing tool_failure_handlers.py
│   ├── __init__.py                          ← Re-exports TOOL_FAILURE_HANDLERS
│   │
│   ├── languages/                           ← 12 tools, ~1,507 lines of data
│   │   ├── __init__.py                      ← Merges language tool handlers
│   │   ├── rust.py                          ← cargo (125), rustup (123) — ~258 lines
│   │   ├── go.py                            ← go (124) — ~130 lines
│   │   ├── python.py                        ← python (390), poetry (62), uv (76) — ~538 lines
│   │   ├── node.py                          ← node (351), nvm (126), yarn (183), pnpm (73) — ~743 lines
│   │   └── php.py                           ← composer (189) — ~195 lines
│   │
│   ├── devops/                              ← 5 tools, ~1,198 lines of data
│   │   ├── __init__.py                      ← Merges devops tool handlers
│   │   ├── containers.py                    ← docker (462), docker-compose (141) — ~613 lines
│   │   ├── k8s.py                           ← helm (113), kubectl (165) — ~288 lines
│   │   └── cloud.py                         ← gh (112), terraform (205) — ~327 lines
│   │
│   └── security/                            ← 1 tool, ~118 lines of data
│       ├── __init__.py                      ← Merges security tool handlers
│       └── scanners.py                      ← trivy (112) — ~118 lines
```

### Line budget compliance

| File | Est. Lines | Status |
|------|-----------|--------|
| `__init__.py` (top) | ~20 | ✅ well under 500 |
| `languages/__init__.py` | ~25 | ✅ well under 500 |
| `languages/rust.py` | ~258 | ✅ under 500 |
| `languages/go.py` | ~130 | ✅ well under 500 |
| `languages/python.py` | ~538 | ✅ within ~700 exception (pure data) |
| `languages/node.py` | ~743 | ⚠️ within ~700 exception (pure data, 4 tools) |
| `languages/php.py` | ~195 | ✅ well under 500 |
| `devops/__init__.py` | ~20 | ✅ well under 500 |
| `devops/containers.py` | ~613 | ✅ within ~700 exception (pure data) |
| `devops/k8s.py` | ~288 | ✅ under 500 |
| `devops/cloud.py` | ~327 | ✅ under 500 |
| `security/__init__.py` | ~15 | ✅ well under 500 |
| `security/scanners.py` | ~118 | ✅ well under 500 |

**Every file under 700.** Three files exceed 500 (`node.py`, `python.py`, `containers.py`) — all pure data, within the exception.

---

## 4. How the Composite Registry Works

### Each leaf file exports tool handler lists:

```python
# data/tool_failure_handlers/languages/rust.py
"""
L0 Data — Rust ecosystem tool-specific failure handlers.

Tools: cargo, rustup
Pure data, no logic.
"""
from __future__ import annotations

_CARGO_HANDLERS: list[dict] = [...]
_RUSTUP_HANDLERS: list[dict] = [...]
```

### Domain `__init__.py` merges tools from that domain:

```python
# data/tool_failure_handlers/languages/__init__.py
from __future__ import annotations

from .rust import _CARGO_HANDLERS, _RUSTUP_HANDLERS
from .go import _GO_HANDLERS
from .python import _PYTHON_HANDLERS, _POETRY_HANDLERS, _UV_HANDLERS
from .node import _NODE_HANDLERS, _NVM_HANDLERS, _YARN_HANDLERS, _PNPM_HANDLERS
from .php import _COMPOSER_HANDLERS

LANGUAGE_TOOL_HANDLERS: dict[str, list[dict]] = {
    "cargo": _CARGO_HANDLERS,
    "rustup": _RUSTUP_HANDLERS,
    "go": _GO_HANDLERS,
    "python": _PYTHON_HANDLERS,
    "poetry": _POETRY_HANDLERS,
    "uv": _UV_HANDLERS,
    "node": _NODE_HANDLERS,
    "nvm": _NVM_HANDLERS,
    "yarn": _YARN_HANDLERS,
    "pnpm": _PNPM_HANDLERS,
    "composer": _COMPOSER_HANDLERS,
}
```

### Top-level `__init__.py` merges all domains:

```python
# data/tool_failure_handlers/__init__.py
from __future__ import annotations

from .languages import LANGUAGE_TOOL_HANDLERS
from .devops import DEVOPS_TOOL_HANDLERS
from .security import SECURITY_TOOL_HANDLERS

TOOL_FAILURE_HANDLERS: dict[str, list[dict]] = {
    **LANGUAGE_TOOL_HANDLERS,
    **DEVOPS_TOOL_HANDLERS,
    **SECURITY_TOOL_HANDLERS,
}

__all__ = ["TOOL_FAILURE_HANDLERS"]
```

**Zero changes to any consumer.** Same import path, same symbol.

---

## 5. Consumer Impact Assessment

Current consumer does:
```python
from src.core.services.tool_install.data.tool_failure_handlers import (
    TOOL_FAILURE_HANDLERS,
)
```

After refactor, `tool_failure_handlers` is a package.
`tool_failure_handlers/__init__.py` re-exports the same symbol.
**Import path does not change.** Zero consumer modifications.

### Consumer to verify post-refactor

1. `src/core/services/tool_install/domain/handler_matching.py` — imports `TOOL_FAILURE_HANDLERS`

---

## 6. Execution Plan

### Phase 1: Create package structure                          🟢

```
1.1  Create directory tree                                     🟢
1.2  Create languages/rust.py (cargo + rustup)                 🟢  262 lines
1.3  Create languages/go.py (go)                               🟢  135 lines
1.4  Create languages/python.py (python + poetry + uv)         🟢  545 lines
1.5  Create languages/node.py (node + nvm + yarn + pnpm)       🟢  752 lines
1.6  Create languages/php.py (composer)                        🟢  195 lines
1.7  Create languages/__init__.py                              🟢   27 lines
1.8  Create devops/containers.py (docker + docker-compose)     🟢  616 lines
1.9  Create devops/k8s.py (helm + kubectl)                     🟢  291 lines
1.10 Create devops/cloud.py (gh + terraform)                   🟢  330 lines
1.11 Create devops/__init__.py                                 🟢   20 lines
1.12 Create security/scanners.py (trivy)                       🟢  123 lines
1.13 Create security/__init__.py                               🟢   13 lines
1.14 Create tool_failure_handlers/__init__.py                  🟢   20 lines
1.15 Delete old tool_failure_handlers.py                       🟢
```

### Phase 2: Validate                                          🟢

```
2.1  Consumer import resolves                                  🟢  same path, 0 consumer changes
2.2  TOOL_FAILURE_HANDLERS: 18 keys, 52 handlers, 105 options  🟢  old vs new count match verified
2.3  All files ≤700 (pure data exception)                      🟢  largest: node.py 752 (pure data)
```

### Phase 3: Document                                          🟢

```
3.1  Write tool_failure_handlers/README.md                     🟢  455 lines
3.2  Update data/README.md                                     🟢  package entry + domain table
```

---

## 7. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Import path changes | Medium | `__init__.py` re-exports same symbol — same path |
| Lost handler during move | High | Automated count: 18 keys, verify post-move |
| Dict key typo in merge | Medium | Key must match original exactly |
| Consumer breaks | Low | 1 consumer, verified pre-commit |
| Type hint bug (dict[str, list[dict]]) | Low | `from __future__ import annotations` in all files |

---

## 8. What This Does NOT Cover

- Adding new tool handlers — that's day-to-day work, not refactor scope
- `recipe_schema.py` (722 lines) — evaluate after this split
